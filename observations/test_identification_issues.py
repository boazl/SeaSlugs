import json
from pathlib import Path
from unittest.mock import patch
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .identification_issue_transfer import ISSUE_FIELDS, issue_plan
from .identification_issues import issue_rows
from .models import Country, DiveTrip, IdentificationIssue, Region, Sample, Sea, Species
from .table_transfer import TABLES, apply, export_table, fingerprint, plan

Issue = IdentificationIssue


class IssueFixture(TestCase):
    def setUp(self):
        self.boss = User.objects.create_superuser('boss', password='x')
        country = Country.objects.create(name='פיליפינים', name_en='Philippines')
        sea = Sea.objects.create(name='ים סין הדרומי', name_en='South China Sea')
        region = Region.objects.create(name='אנילאו', country=country, sea=sea)
        self.trip = DiveTrip.objects.create(code='H', title='T', year=2025, month=3, country=country, region=region)
        self.maculosa = Species.objects.create(scientific_name='Hypselodoris maculosa', genus='Hypselodoris', species='maculosa')
        self.aurora = Species.objects.create(scientific_name='Mexichromis aurora', genus='Mexichromis', species='aurora')
        self.n = 0
        self.first = self.observation(self.maculosa)
        self.second = self.observation(self.aurora)
        self.client.force_login(self.boss)

    def observation(self, species):
        self.n += 1
        sample = Sample(kind='species', species=species, trip=self.trip, owner=self.boss,
                        video_url=f'https://youtu.be/abcdefghi{self.n:02d}')
        sample.save_reviewed(actor=self.boss)
        return sample


class IdentificationIssueModelTests(IssueFixture):
    """An identification issue: its species follows its observation when left empty (also the second one); marking it
    fixed fills the fix date with today; a "duplicate" issue needs a second observation or species, never the same
    observation twice; a fix date before the opening date is refused. A deleted observation or species leaves the
    issue in place (SET_NULL)."""

    def test_species_follow_the_observations(self):
        issue = Issue.objects.create(kind='duplicate', observation=self.first, second_observation=self.second)
        self.assertEqual((issue.species, issue.second_species), (self.maculosa, self.aurora))

    def test_fixed_fills_the_fix_date(self):
        issue = Issue.objects.create(kind='range', species=self.maculosa, status='fixed')
        self.assertEqual(issue.fixed_on, timezone.localdate())
        kept = Issue.objects.create(kind='range', species=self.maculosa, status='fixed', fixed_on=date(2026, 1, 2))
        self.assertEqual(kept.fixed_on, date(2026, 1, 2))

    def test_duplicate_needs_a_second_one(self):
        with self.assertRaises(ValidationError):
            Issue(kind='duplicate', observation=self.first).full_clean()
        with self.assertRaises(ValidationError):
            Issue(kind='duplicate', observation=self.first, second_observation=self.first).full_clean()
        with self.assertRaises(ValidationError):
            Issue(kind='range', observation=self.first, opened_on=date(2026, 5, 1), fixed_on=date(2026, 4, 1)).full_clean()
        Issue(kind='duplicate', observation=self.first, second_species=self.aurora).full_clean()

    def test_deleting_the_species_keeps_the_issue(self):
        issue = Issue.objects.create(kind='misidentified', species=self.aurora, corrected_species=self.maculosa)
        Sample.objects.filter(species=self.maculosa).delete()
        from .models import SpeciesArea
        SpeciesArea.objects.filter(species=self.maculosa).delete()
        self.maculosa.delete()
        issue.refresh_from_db()
        self.assertIsNone(issue.corrected_species)
        self.assertEqual(issue.species, self.aurora)


class IdentificationIssuesPageTests(IssueFixture):
    """/admin/identification-issues/ (superusers only) lists the issues -- by default the active ones (open + being
    checked) -- with filters by state, kind and priority, a free search (species names, notes, observation number),
    sorted by priority. A row's priority and state change right from the list. The form adds and edits issues
    (observations by number, species by scientific name from the catalogue), the delete page asks before removing.
    An issue about a species alone shows the species' gallery observation (photo and links).
    The admin's index links to the page."""

    def url(self, name='identification-issues', *args):
        return reverse(name, args=args)

    def test_superusers_only(self):
        staff = User.objects.create_user('staff', password='x', is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(self.url()).status_code, 403)
        self.assertEqual(self.client.get(self.url('identification-issue-new')).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url()).status_code, 302)

    def test_list_filters_and_order(self):
        low = Issue.objects.create(kind='range', species=self.maculosa, priority=3, notes='Western Indian Ocean only')
        high = Issue.objects.create(kind='duplicate', observation=self.first, second_observation=self.second, priority=1)
        done = Issue.objects.create(kind='worms_name', species=self.aurora, status='fixed', corrected_name='Mexichromis aurora')
        self.assertEqual(issue_rows(), [high, low])
        self.assertEqual(issue_rows(state='all'), [high, low, done])
        self.assertEqual(issue_rows(state='fixed'), [done])
        self.assertEqual(issue_rows(kind='range'), [low])
        self.assertEqual(issue_rows(priority='1'), [high])
        self.assertEqual(issue_rows(q='indian'), [low])
        self.assertEqual(issue_rows(q='aurora'), [high])
        self.assertEqual(issue_rows(q=str(self.second.pk)), [high])
        page = self.client.get(self.url()).content.decode()
        self.assertIn(f'id="issue-{high.pk}"', page)
        self.assertNotIn(f'id="issue-{done.pk}"', page)
        self.assertIn(reverse('observation-edit', args=[self.first.pk]), page)
        self.assertIn(f'#obs-{self.second.pk}', page)  # the observation on its species page
        self.assertIn(reverse('identification-issues'), self.client.get(reverse('admin:index')).content.decode())

    def test_species_only_issue_shows_the_species_observation(self):
        issue = Issue.objects.create(kind='worms_name', species=self.aurora, corrected_name='Mexichromis aurora')
        rows = issue_rows()
        from .identification_issues import _species_samples
        _species_samples(rows)
        self.assertEqual(rows[0].species_sample, self.second)
        with_obs = Issue.objects.create(kind='range', observation=self.first)
        _species_samples([with_obs])
        self.assertIsNone(with_obs.species_sample)
        page = self.client.get(self.url()).content.decode()
        self.assertIn('תצפית של המין בגלריה', page)
        self.assertIn(reverse('observation-edit', args=[self.second.pk]), page)

    def test_quick_priority_and_state_change(self):
        issue = Issue.objects.create(kind='range', species=self.maculosa)
        response = self.client.post(self.url(), {'issue': issue.pk, 'priority': '1', 'status': 'fixed', 'back': 'state=all'})
        self.assertRedirects(response, self.url() + '?state=all', fetch_redirect_response=False)
        issue.refresh_from_db()
        self.assertEqual((issue.priority, issue.status, issue.fixed_on), (1, 'fixed', timezone.localdate()))

    def test_add_edit_and_delete(self):
        response = self.client.post(self.url('identification-issue-new'), {
            'kind': 'duplicate', 'priority': '1', 'status': 'open', 'opened_on': '2026-11-17',
            'observation': self.first.pk, 'second_observation': self.second.pk, 'notes': 'The same photo'})
        self.assertEqual(response.status_code, 302)
        issue = Issue.objects.get()
        self.assertEqual((issue.species, issue.second_species, issue.priority), (self.maculosa, self.aurora, 1))
        response = self.client.post(self.url('identification-issue-edit', issue.pk), {
            'kind': 'misidentified', 'priority': '2', 'status': 'checking', 'opened_on': '2026-11-17',
            'observation': self.first.pk, 'species': 'Hypselodoris maculosa', 'corrected_species': 'mexichromis aurora',
            'notes': 'x'})
        self.assertEqual(response.status_code, 302)
        issue.refresh_from_db()
        self.assertEqual((issue.kind, issue.corrected_species, issue.status), ('misidentified', self.aurora, 'checking'))
        page = self.client.get(self.url('identification-issue-edit', issue.pk)).content.decode()
        self.assertIn('value="Mexichromis aurora"', page)
        self.assertIn('<datalist id="species-names">', page)
        self.assertEqual(self.client.get(self.url('identification-issue-delete', issue.pk)).status_code, 200)
        self.assertTrue(Issue.objects.exists())
        self.client.post(self.url('identification-issue-delete', issue.pk))
        self.assertFalse(Issue.objects.exists())

    def test_form_errors(self):
        response = self.client.post(self.url('identification-issue-new'), {
            'kind': 'misidentified', 'priority': '2', 'status': 'open', 'opened_on': '2026-11-17',
            'species': 'Nonexistent thing', 'observation': '999999'})
        self.assertEqual(response.status_code, 200)
        page = response.content.decode()
        self.assertIn('לא נמצא בקטלוג המינים', page)
        self.assertIn('אין תצפית עם המספר הזה', page)
        response = self.client.post(self.url('identification-issue-new'), {
            'kind': 'other', 'priority': '2', 'status': 'open', 'opened_on': '2026-11-17'})
        self.assertIn('יש לציין תצפית, מין או הערה', response.content.decode())
        self.assertFalse(Issue.objects.exists())

    def test_new_form_for_an_observation(self):
        page = self.client.get(self.url('identification-issue-new') + f'?observation={self.first.pk}&kind=range').content.decode()
        self.assertIn(f'value="{self.first.pk}"', page)
        self.assertIn('<option value="range" selected>', page)


class IdentificationIssueTransferTests(IssueFixture):
    """The identification issues travel with the table transfer (table "identissues"): matched by transfer_id, the
    observations by their transfer_id and the species by scientific name; a row whose observation or species is missing
    is skipped with a reason; an existing row is updated only by a copy changed later (updated_at); nothing is removed."""

    def make(self, **kwargs):
        values = dict(kind='duplicate', observation=self.first, second_observation=self.second, priority=1, notes='same photo')
        values.update(kwargs)
        return Issue.objects.create(**values)

    def test_table_is_listed_and_exported(self):
        self.assertIn('identissues', TABLES)
        issue = self.make()
        row = export_table('identissues')['rows'][0]
        self.assertEqual(set(row), set(ISSUE_FIELDS))
        self.assertEqual(row['observation'], str(self.first.transfer_id))
        self.assertEqual(row['second_species'], 'Mexichromis aurora')
        json.dumps(row)
        self.assertEqual(row['transfer_id'], str(issue.transfer_id))

    def test_new_row_and_round_trip(self):
        issue = self.make()
        document = export_table('identissues')
        issue.delete()
        items = plan(document)
        self.assertEqual([i['action'] for i in items], ['new'])
        with patch('observations.table_transfer.create_backup', return_value=Path('test.sqlite3')):
            apply(document, fingerprint())
        copy = Issue.objects.get()
        self.assertEqual((copy.transfer_id, copy.observation, copy.second_species, copy.notes),
                         (issue.transfer_id, self.first, self.aurora, 'same photo'))

    def test_newer_copy_updates_older_does_not(self):
        issue = self.make()
        document = export_table('identissues')
        row = document['rows'][0]
        row['status'] = 'fixed'; row['fixed_on'] = (issue.opened_on + timedelta(days=1)).isoformat()
        row['updated_at'] = (issue.updated_at + timedelta(minutes=5)).isoformat()
        items = issue_plan(document)
        self.assertEqual(items[0]['action'], 'update')
        self.assertTrue(any(c['after'] == 'fixed' for c in items[0]['changes']))
        row['updated_at'] = (issue.updated_at - timedelta(minutes=5)).isoformat()
        self.assertEqual(issue_plan(document)[0]['action'], 'same')

    def test_missing_references_skip_the_row(self):
        self.make()
        document = export_table('identissues')
        Issue.objects.all().delete()
        document['rows'][0]['second_species'] = 'Not in the catalogue'
        item = issue_plan(document)[0]
        self.assertEqual(item['action'], 'skipped')
        self.assertIn('חסר ביעד', item['reason'])

    def test_bad_files_are_refused(self):
        self.make()
        document = export_table('identissues')
        del document['rows'][0]['notes']
        with self.assertRaises(ValidationError):
            issue_plan(document)


class IdentificationFindingsMigrationTests(IssueFixture):
    """Migration 0104 adds Claude's findings of 2026-11-17 in both environments: observations by transfer_id, species by
    scientific name, a fixed transfer_id per row; a row whose species is missing is skipped and an existing row is never
    added twice."""

    def run_migration(self):
        from importlib import import_module
        from django.apps import apps
        import_module('observations.migrations.0104_identification_issue_findings').add_findings(apps, None)

    def test_adds_found_rows_once(self):
        Sample.objects.filter(pk=self.first.pk).update(transfer_id='616c9a85-5c16-4437-b06f-9228277d47bc')
        Sample.objects.filter(pk=self.second.pk).update(transfer_id='36ae91eb-14f6-4fe2-976e-05cf9e71caec')
        self.run_migration()
        self.run_migration()
        issue = Issue.objects.get()
        self.assertEqual((issue.kind, issue.priority, issue.observation, issue.second_observation, issue.second_species),
                         ('duplicate', 1, self.first, self.second, self.aurora))
        self.assertIn('Mexichromis aurora', issue.notes)


class IssueWorkflowTests(IssueFixture):
    """The work on an issue: review (open / checking) -> a recommendation and a decision with the work it needs (video,
    photo, observation, deletion, catalogue -- each "needed" then "done"; state "decided", listed under "to fix") ->
    handled ("fixed"), which is refused while any of its work is still pending. Older transfer files without these
    fields are still read."""

    def test_states_filters_and_closing(self):
        review = Issue.objects.create(kind='range', species=self.maculosa)
        tofix = Issue.objects.create(kind='duplicate', observation=self.first, second_observation=self.second, status='decided',
                                     recommendation='Same photo', decision='Keep M. aurora', action_photo='needed', action_delete='needed')
        self.assertEqual(issue_rows(), [tofix, review])
        self.assertEqual(issue_rows(state='review'), [review])
        self.assertEqual(issue_rows(state='tofix'), [tofix])
        self.assertEqual(issue_rows(q='keep m. aurora'), [tofix])
        self.client.post(reverse('identification-issues'), {'issue': tofix.pk, 'status': 'fixed'})
        tofix.refresh_from_db()
        self.assertEqual(tofix.status, 'decided')
        with self.assertRaises(ValidationError):
            Issue(kind='other', notes='x', status='fixed', action_video='needed').full_clean()
        Issue.objects.filter(pk=tofix.pk).update(action_photo='done', action_delete='done')
        self.client.post(reverse('identification-issues'), {'issue': tofix.pk, 'status': 'fixed'})
        tofix.refresh_from_db()
        self.assertEqual((tofix.status, tofix.fixed_on), ('fixed', timezone.localdate()))
        page = self.client.get(reverse('identification-issues') + '?state=all').content.decode()
        self.assertIn('✓ עריכת התמונה (כיתוב)', page)

    def test_older_transfer_rows_without_the_work_fields(self):
        issue = Issue.objects.create(kind='range', species=self.maculosa, decision='kept here')
        document = export_table('identissues')
        row = document['rows'][0]
        for f in ('recommendation', 'decision', 'action_video', 'action_photo', 'action_observation', 'action_delete', 'action_catalog'):
            del row[f]
        row['notes'] = 'changed'
        row['updated_at'] = (issue.updated_at + timedelta(minutes=1)).isoformat()
        item = issue_plan(document)[0]
        self.assertEqual(item['action'], 'update')
        self.assertEqual(item['object'].decision, 'kept here')


class ApplyIssueReviewsTests(IssueFixture):
    """apply_issue_reviews writes the reviews kept in observations/data/issue_reviews.json: a recommendation / decision
    only into an empty field, a state only on an issue still under review; dry run unless --apply."""

    def test_writes_only_empty_fields_and_review_states(self):
        from io import StringIO
        from unittest.mock import patch
        from django.core.management import call_command
        from .management.commands import apply_issue_reviews as command
        fresh = Issue.objects.create(kind='range', species=self.maculosa)
        edited = Issue.objects.create(kind='range', species=self.aurora, recommendation='mine', status='decided')
        reviews = [{'transfer_id': str(fresh.transfer_id), 'recommendation': 'R', 'decision': 'D', 'status': 'checking'},
                   {'transfer_id': str(edited.transfer_id), 'recommendation': 'R2', 'status': 'checking'}]
        with patch.object(command, 'DATA') as data, patch('observations.table_transfer.create_backup'):
            data.read_text.return_value = json.dumps(reviews)
            call_command('apply_issue_reviews', stdout=StringIO())
            fresh.refresh_from_db()
            self.assertEqual(fresh.recommendation, '')
            call_command('apply_issue_reviews', '--apply', stdout=StringIO())
        fresh.refresh_from_db(); edited.refresh_from_db()
        self.assertEqual((fresh.recommendation, fresh.decision, fresh.status), ('R', 'D', 'checking'))
        self.assertEqual((edited.recommendation, edited.status), ('mine', 'decided'))
        self.assertTrue(json.loads(command.DATA.read_text(encoding='utf-8')))     # the real file is valid JSON
