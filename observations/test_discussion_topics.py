import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .discussion_topic_transfer import TOPIC_FIELDS, topic_plan
from .discussion_topics import topic_rows
from .identification_issues import KIND_FIELDS
from .models import DiscussionTopic, IdentificationIssue, Species
from .table_transfer import TABLES, apply, export_table, fingerprint, plan

Topic = DiscussionTopic


class TopicFixture(TestCase):
    def setUp(self):
        self.boss = User.objects.create_superuser('boss', password='x')
        self.client.force_login(self.boss)

    def make(self, **kwargs):
        values = dict(topic='Notodoris', rank='genus', priority=2, book_treatment='in Aegires',
                      worms_treatment='accepted genus', site_treatment='Notodoris')
        values.update(kwargs)
        return Topic.objects.create(**values)


class DiscussionTopicsPageTests(TopicFixture):
    """/admin/discussion-topics/ (superusers only) lists the topics for discussion -- by default the open ones -- with
    filters by state and rank and a free search over every text, sorted by priority then topic. A row's priority and
    state change right from the list; the form adds and edits topics and the delete page asks before removing. The
    admin's index links to the page."""

    def test_superusers_only(self):
        staff = User.objects.create_user('staff', password='x', is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse('discussion-topics')).status_code, 403)
        self.assertEqual(self.client.get(reverse('discussion-topic-new')).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('discussion-topics')).status_code, 302)

    def test_list_filters_and_order(self):
        low = self.make(topic='Glaucilla', priority=3, worms_treatment='Glaucilla marginata')
        high = self.make(topic='Doridida', rank='order', priority=1)
        done = self.make(topic='Bullinidae', rank='family', status='decided')
        self.assertEqual(topic_rows(), [high, low])
        self.assertEqual(topic_rows(state='all'), [high, done, low])
        self.assertEqual(topic_rows(state='decided'), [done])
        self.assertEqual(topic_rows(rank='order'), [high])
        self.assertEqual(topic_rows(q='marginata'), [low])
        page = self.client.get(reverse('discussion-topics')).content.decode()
        self.assertIn(f'id="topic-{high.pk}"', page)
        self.assertNotIn(f'id="topic-{done.pk}"', page)
        self.assertIn(reverse('discussion-topics'), self.client.get(reverse('admin:index')).content.decode())

    def test_quick_priority_and_state_change(self):
        topic = self.make()
        response = self.client.post(reverse('discussion-topics'), {'topic': topic.pk, 'priority': '1', 'status': 'decided',
                                                                    'back': 'state=all'})
        self.assertRedirects(response, reverse('discussion-topics') + '?state=all', fetch_redirect_response=False)
        topic.refresh_from_db()
        self.assertEqual((topic.priority, topic.status), (1, 'decided'))

    def test_add_edit_and_delete(self):
        response = self.client.post(reverse('discussion-topic-new'), {
            'topic': 'Phestilla', 'rank': 'genus', 'priority': '2', 'status': 'open', 'opened_on': '2026-11-17',
            'book_treatment': 'in Tenellia', 'worms_treatment': 'accepted', 'decision': 'WoRMS'})
        self.assertEqual(response.status_code, 302)
        topic = Topic.objects.get()
        self.assertEqual((topic.topic, topic.decision), ('Phestilla', 'WoRMS'))
        self.client.post(reverse('discussion-topic-edit', args=[topic.pk]), {
            'topic': 'Phestilla', 'rank': 'genus', 'priority': '1', 'status': 'decided', 'opened_on': '2026-11-17',
            'worms_link': 'https://www.marinespecies.org/aphia.php?p=taxdetails&id=390813'})
        topic.refresh_from_db()
        self.assertEqual((topic.priority, topic.status), (1, 'decided'))
        self.assertEqual(self.client.get(reverse('discussion-topic-delete', args=[topic.pk])).status_code, 200)
        self.assertTrue(Topic.objects.exists())
        self.client.post(reverse('discussion-topic-delete', args=[topic.pk]))
        self.assertFalse(Topic.objects.exists())

    def test_topic_is_required(self):
        response = self.client.post(reverse('discussion-topic-new'), {'rank': 'genus', 'priority': '2', 'status': 'open',
                                                                      'opened_on': '2026-11-17'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Topic.objects.exists())


class DiscussionTopicTransferTests(TopicFixture):
    """The topics travel with the table transfer (table "discussions"): matched by transfer_id, a new row is created as
    it is, an existing row is updated only by a copy changed later (updated_at), a malformed file is refused."""

    def test_table_is_listed_and_exported(self):
        self.assertIn('discussions', TABLES)
        topic = self.make()
        row = export_table('discussions')['rows'][0]
        self.assertEqual(set(row), set(TOPIC_FIELDS))
        self.assertEqual(row['transfer_id'], str(topic.transfer_id))
        json.dumps(row)

    def test_round_trip(self):
        topic = self.make()
        document = export_table('discussions')
        topic.delete()
        self.assertEqual([i['action'] for i in plan(document)], ['new'])
        with patch('observations.table_transfer.create_backup', return_value=Path('test.sqlite3')):
            apply(document, fingerprint())
        copy = Topic.objects.get()
        self.assertEqual((copy.transfer_id, copy.topic, copy.book_treatment), (topic.transfer_id, 'Notodoris', 'in Aegires'))

    def test_newer_copy_updates_older_does_not(self):
        topic = self.make()
        document = export_table('discussions')
        row = document['rows'][0]
        row['status'] = 'decided'
        row['updated_at'] = (topic.updated_at + timedelta(minutes=5)).isoformat()
        item = topic_plan(document)[0]
        self.assertEqual(item['action'], 'update')
        self.assertTrue(any(c['after'] == 'decided' for c in item['changes']))
        row['updated_at'] = (topic.updated_at - timedelta(minutes=5)).isoformat()
        self.assertEqual(topic_plan(document)[0]['action'], 'same')

    def test_bad_files_are_refused(self):
        self.make()
        document = export_table('discussions')
        del document['rows'][0]['notes']
        with self.assertRaises(ValidationError):
            topic_plan(document)
        document = export_table('discussions')
        document['rows'][0]['priority'] = 9
        with self.assertRaises(ValidationError):
            topic_plan(document)


class BookEditionIssueTests(TopicFixture):
    """The identification issues have a "book_edition" kind: a name to update by the 3rd edition of Gosliner et al.
    (an undescribed species renumbered or moved since the 2nd edition); it uses the corrected-name field."""

    def test_kind_and_its_field(self):
        species = Species.objects.create(scientific_name='Aegires sp. 8', genus='Aegires', species='sp. 8')
        issue = IdentificationIssue.objects.create(kind='book_edition', species=species, corrected_name='Aegires sp. 13')
        self.assertEqual(issue.get_kind_display(), 'עדכון שם לפי המהדורה השלישית של Gosliner et al.')
        self.assertEqual(KIND_FIELDS[IdentificationIssue.Kind.BOOK_EDITION], ('corrected_name',))
        page = self.client.get(reverse('identification-issues') + '?kind=book_edition').content.decode()
        self.assertIn('Aegires sp. 13', page)


class EditionsFindingsMigrationTests(TopicFixture):
    """Migration 0106 adds the findings of the 2nd/3rd-edition and WoRMS comparison in both environments: issues by
    species name (a row whose species is missing is skipped, the corrected species is linked when it is in the
    catalogue), the topics for discussion, a fixed transfer_id per row, and nothing is added twice; an empty catalogue
    (a new or test database) gets nothing."""

    def test_empty_catalogue_gets_nothing(self):
        self.run_migration()
        self.assertFalse(IdentificationIssue.objects.exists())
        self.assertFalse(Topic.objects.exists())

    def run_migration(self):
        from importlib import import_module
        from django.apps import apps
        import_module('observations.migrations.0106_nssi3_findings').add(apps, None)

    def test_adds_rows_once(self):
        for name in ('Thecacera sp. 8', 'Goniodoridella sp. 8', 'Murphydoris cobbi', 'Goniodoris joubini', 'Pelagella joubini'):
            genus, epithet = name.split(' ', 1)
            Species.objects.create(scientific_name=name, genus=genus, species=epithet)
        self.run_migration()
        self.run_migration()
        issues = IdentificationIssue.objects
        self.assertEqual(issues.get(species__scientific_name='Thecacera sp. 8').corrected_name.split(' Pola')[0],
                         'Thecacera pikachu')
        cobbi = issues.get(species__scientific_name='Goniodoridella sp. 8')
        self.assertEqual((cobbi.kind, cobbi.corrected_species.scientific_name), ('worms_name', 'Murphydoris cobbi'))
        joubini = issues.get(species__scientific_name='Goniodoris joubini')
        self.assertEqual(joubini.corrected_species.scientific_name, 'Pelagella joubini')
        self.assertFalse(issues.filter(species__scientific_name='Aegires sp. 8').exists())  # not in this catalogue
        self.assertTrue(issues.filter(species=None, kind='other').exists())  # the missing-species list
        self.assertEqual(issues.count(), 4)
        self.assertGreaterEqual(Topic.objects.count(), 15)
        self.assertTrue(Topic.objects.filter(topic='Notodoris', worms_link__contains='531074').exists())
