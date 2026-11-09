"""The observations forum (/forum/, forum.py) and its table transfer (forum_transfer.py)."""
import json

from django.contrib.auth.models import Permission, User
from django.test import TestCase

from .forum_transfer import FORUM_FIELDS
from .models import Country, DiveTrip, ForumMessage, Region, Sample, Sea, Species, SpeciesArea
from .table_transfer import TABLES, export_table, plan


class ForumSetup(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', password='pw-test-12345', first_name='דני', last_name='צלם')
        self.member = User.objects.create_user('member', password='pw-test-12345')
        self.other = User.objects.create_user('other', password='pw-test-12345')
        self.manager = User.objects.create_user('manager', password='pw-test-12345', is_staff=True)
        self.manager.user_permissions.add(Permission.objects.get(codename='change_sample'))
        country = Country.objects.create(name='ישראל', name_en='Israel')
        sea = Sea.objects.create(name='ים סוף', name_en='Red Sea')
        region = Region.objects.create(name='אילת', name_en='Eilat', country=country, sea=sea)
        self.trip = DiveTrip.objects.create(title='Eilat', year=2026, month=5, country=country, region=region, code='e1')
        self.species = Species.objects.create(scientific_name='Phyllidia ocellata', genus='Phyllidia', species='ocellata',
                                              author='Cuvier, 1804', family='Phyllidiidae', order='Nudibranchia')
        self.sample = Sample(owner=self.owner, trip=self.trip, species=self.species, video_url='https://youtu.be/aaaaaaaaaaa')
        self.sample.save_reviewed()
        self.slug = SpeciesArea.objects.get().slug
        self.collection = Sample(owner=self.owner, kind='collection', trip=self.trip, title='מסע אילת',
                                 video_url='https://youtu.be/ccccccccccc')
        self.collection.save_reviewed(actor=self.manager, approve=True)

    def message(self, user=None, sample=None, manager_only=False, text='שלום'):
        return ForumMessage.objects.create(observation=sample or self.sample, user=user or self.member,
                                           manager_only=manager_only, text=text)

    def page(self, query='', user=None):
        if user:
            self.client.force_login(user)
        return self.client.get('/forum/' + query).content.decode()


class ForumPageTests(ForumSetup):
    """Every discussion belongs to one observation; there is no general discussion. The page offers a kind filter
    (species observations, dive trips, taxa) and an observation picker -- observations with a discussion first, with
    their message count. With an observation chosen it shows that discussion, oldest message first, and the writing
    box; without one, all the discussions grouped by observation, the most recently active first."""

    def test_no_general_discussion(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.post('/forum/', {'audience': 'all', 'text': 'x'}).status_code, 404)
        self.assertEqual(self.client.get('/forum/?obs=general').status_code, 404)
        self.assertNotIn('דיון כללי', self.page())
        self.assertNotIn('id="write"', self.page())

    def test_picker_lists_discussed_observations_first(self):
        self.message()
        self.message()
        html = self.page()
        picker = html.split('name="obs"')[1].split('</select>')[0]
        self.assertLess(picker.index('תצפיות עם דיון'), picker.index('תצפיות נוספות'))
        self.assertIn(f'<option value="{self.sample.pk}">Phyllidia ocellata · אילת · 2026 (2)</option>', picker)
        self.assertIn(f'<option value="{self.collection.pk}">', picker.split('תצפיות נוספות')[1])

    def test_kind_filter(self):
        self.message(text='על המין')
        self.message(sample=self.collection, text='על המסע')
        html = self.page('?kind=collection')
        self.assertIn('על המסע', html)
        self.assertNotIn('על המין', html)
        picker = html.split('name="obs"')[1].split('</select>')[0]
        self.assertNotIn(f'value="{self.sample.pk}"', picker)
        html = self.page('?kind=species')
        self.assertIn('על המין', html)
        self.assertNotIn('על המסע', html)

    def test_grouped_by_observation_latest_first(self):
        first = self.message(text='ראשונה')
        self.message(sample=self.collection, text='על המסע')
        self.message(text='אחרונה')
        html = self.page()
        self.assertLess(html.index('מסע אילת</a>'), html.index('על המסע'))
        self.assertLess(html.index('ראשונה'), html.index('אחרונה'))
        # the species observation's discussion is the most recently active: shown first
        self.assertLess(html.index('ראשונה'), html.index('על המסע'))
        self.assertIn(f'id="m-{first.pk}"', html)

    def test_one_discussion(self):
        self.message(text='ראשונה')
        self.message(text='שנייה')
        self.message(sample=self.collection, text='על המסע')
        html = self.page(f'?obs={self.sample.pk}')
        self.assertLess(html.index('ראשונה'), html.index('שנייה'))
        self.assertNotIn('על המסע', html)
        self.assertIn('מנהל הדיון: דני צלם', html)
        self.assertIn(f'href="/species/{self.slug}/#obs-{self.sample.pk}"', html)
        self.assertIn('href="/trip/e1/"', self.page(f'?obs={self.collection.pk}'))

    def test_english(self):
        html = self.page(f'?obs={self.sample.pk}&lang=en')
        self.assertIn('Observations forum', html)
        self.assertIn('Discussion manager:', html)
        self.assertIn('Kind of observations', html)
        self.assertNotIn('פורום תצפיות', html.split('<main>')[1])


class ForumFilterTests(ForumSetup):
    """The picker's filters: photographer, country, region and year always; genus and species for species
    observations; the genus / family / order of a taxon observation. Each list offers the values among the observations
    matching the other filters; the picker and the grouped discussions follow all of them."""

    def setUp(self):
        super().setUp()
        country = Country.objects.create(name='פיליפינים', name_en='Philippines')
        region = Region.objects.create(name='אנילאו', name_en='Anilao', country=country, sea=Sea.objects.create(name='ים סין', name_en='South China Sea'))
        trip = DiveTrip.objects.create(title='Anilao', year=2024, month=3, country=country, region=region, code='a1')
        self.other_species = Species.objects.create(scientific_name='Chromodoris annae', genus='Chromodoris', species='annae',
                                                    author='Bergh, 1877')
        self.far = Sample(owner=self.other, trip=trip, species=self.other_species, video_url='https://youtu.be/bbbbbbbbbbb')
        self.far.save_reviewed()

    def select(self, html, name):
        return html.split(f'<select name="{name}"')[1].split('</select>')[0]

    def test_filters_offered(self):
        html = self.page()
        for name in ('photographer', 'country', 'region', 'year'):
            self.assertIn(f'<select name="{name}"', html)
        self.assertNotIn('<select name="species"', html)
        html = self.page('?kind=species')
        self.assertIn('Chromodoris annae', self.select(html, 'species'))
        self.assertIn('Chromodoris', self.select(html, 'genus'))
        self.assertNotIn('<select name="order"', html)
        self.assertIn('<select name="order"', self.page('?kind=order'))

    def test_filters_narrow_the_picker_and_each_other(self):
        html = self.page(f'?region={self.far.trip.region_id}')
        picker = self.select(html, 'obs')
        self.assertIn(f'value="{self.far.pk}"', picker)
        self.assertNotIn(f'value="{self.sample.pk}"', picker)
        self.assertIn('2024', self.select(html, 'year'))
        self.assertNotIn('2026', self.select(html, 'year'))
        self.assertIn('2026', self.select(self.page(), 'year'))
        picker = self.select(self.page(f'?kind=species&species={self.species.pk}'), 'obs')
        self.assertIn(f'value="{self.sample.pk}"', picker)
        self.assertNotIn(f'value="{self.far.pk}"', picker)

    def test_grouped_discussions_follow_the_filters(self):
        self.message(text='על אילת')
        self.message(sample=self.far, text='על אנילאו')
        html = self.page(f'?photographer={self.other.pk}')
        self.assertIn('על אנילאו', html)
        self.assertNotIn('על אילת', html)
        html = self.page('?year=2026')
        self.assertIn('על אילת', html)
        self.assertNotIn('על אנילאו', html)


class ForumVisibilityTests(ForumSetup):
    """A message for everyone is read by every visitor, signed in or not. A message for the discussion's manager only
    is read by its writer, the observation's owner (the discussion's manager) and the site managers -- nobody else.
    A discussion of an observation that is not public is seen only by its owner and the site managers."""

    def test_public_message_is_read_without_an_account(self):
        self.message(text='תצפית יפה מאוד')
        self.assertIn('תצפית יפה מאוד', self.page())
        self.assertIn('תצפית יפה מאוד', self.page(f'?obs={self.sample.pk}'))

    def test_manager_only_message(self):
        self.message(manager_only=True, text='הערה פרטית')
        self.assertNotIn('הערה פרטית', self.page())
        self.assertNotIn('הערה פרטית', self.page(user=self.other))
        for user in (self.member, self.owner, self.manager):
            self.assertIn('הערה פרטית', self.page(f'?obs={self.sample.pk}', user=user), user.username)

    def test_discussion_of_a_hidden_observation(self):
        self.message(text='על תצפית שנמחקה')
        self.sample.soft_delete(self.manager)
        self.assertEqual(self.client.get(f'/forum/?obs={self.sample.pk}').status_code, 404)
        self.assertNotIn('על תצפית שנמחקה', self.page())
        self.assertIn('על תצפית שנמחקה', self.page(f'?obs={self.sample.pk}', user=self.owner))
        self.assertIn('על תצפית שנמחקה', self.page(f'?obs={self.sample.pk}', user=self.manager))

    def test_deleted_message_is_hidden(self):
        message = self.message(text='נמחקה')
        message.deleted_at = message.created_at
        message.save()
        self.assertNotIn('נמחקה</p>', self.page(user=self.manager))


class ForumWritingTests(ForumSetup):
    """Writing needs an account. A message stores its observation, the time, the writer, whether it is for the
    discussion's manager only, an optional subject and the text. The "add a comment" button sends a visitor who is not
    signed in to the login page (which then offers sign-up) and back to the forum; from the home page (no observation)
    it leads to the observation picker."""

    def post(self, data, user=None):
        if user:
            self.client.force_login(user)
        return self.client.post('/forum/', data)

    def test_member_writes_a_message(self):
        response = self.post({'obs': self.sample.pk, 'audience': 'manager', 'subject': 'זיהוי', 'text': ' אולי זה מין אחר? '},
                             user=self.member)
        message = ForumMessage.objects.get()
        self.assertEqual((message.observation, message.user, message.manager_only, message.subject, message.text),
                         (self.sample, self.member, True, 'זיהוי', 'אולי זה מין אחר?'))
        self.assertIsNotNone(message.created_at)
        self.assertEqual(response['Location'], f'/forum/?obs={self.sample.pk}#m-{message.pk}')

    def test_empty_text_is_refused(self):
        response = self.post({'obs': self.sample.pk, 'audience': 'all', 'text': '   '}, user=self.member)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ForumMessage.objects.exists())

    def test_anonymous_cannot_write(self):
        response = self.post({'obs': self.sample.pk, 'audience': 'all', 'text': 'x'})
        self.assertTrue(response['Location'].startswith('/observations/login/?next='))
        self.assertFalse(ForumMessage.objects.exists())
        html = self.page(f'?obs={self.sample.pk}')
        self.assertIn('/observations/login/?next=', html)
        self.assertIn('/observations/signup/?next=', html)

    def test_add_comment_button(self):
        response = self.client.get(f'/forum/new/?obs={self.sample.pk}')
        self.assertEqual(response['Location'], f'/observations/login/?next=%2Fforum%2F%3Fobs%3D{self.sample.pk}%23write')
        self.assertEqual(self.client.get('/forum/new/?lang=he')['Location'], '/observations/login/?next=%2Fforum%2F%23choose')
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(f'/forum/new/?obs={self.sample.pk}&lang=en')['Location'],
                         f'/forum/?obs={self.sample.pk}&lang=en#write')
        self.assertEqual(self.client.get('/forum/new/?lang=he')['Location'], '/forum/#choose')

    def test_login_page_offers_sign_up_and_sign_up_comes_back(self):
        nxt = f'/forum/?obs={self.sample.pk}#write'
        html = self.client.get('/observations/login/', {'next': nxt}).content.decode()
        self.assertIn(f'/observations/signup/?next=%2Fforum%2F%3Fobs%3D{self.sample.pk}%23write', html)
        response = self.client.post('/observations/signup/?next=' + nxt.replace('?', '%3F').replace('=', '%3D').replace('#', '%23'), {
            'username': 'newdiver', 'email': 'n@example.com', 'password1': 'Very-long-pw-9876', 'password2': 'Very-long-pw-9876'})
        self.assertEqual(response['Location'], nxt)

    def test_sign_up_refuses_an_outside_next(self):
        response = self.client.post('/observations/signup/?next=https://evil.example/', {
            'username': 'newdiver', 'email': 'n@example.com', 'password1': 'Very-long-pw-9876', 'password2': 'Very-long-pw-9876'})
        self.assertEqual(response['Location'], '/observations/profile/')


class ForumDeleteTests(ForumSetup):
    """A message is deleted (marked, hidden from the forum) by its writer, the discussion's manager or a site manager."""

    def test_who_may_delete(self):
        for user, allowed in ((self.other, False), (self.member, True), (self.owner, True), (self.manager, True)):
            message = self.message()
            self.client.force_login(user)
            response = self.client.post(f'/forum/{message.pk}/delete/')
            message.refresh_from_db()
            self.assertEqual(message.deleted_at is not None, allowed, user.username)
            self.assertEqual(response.status_code, 302 if allowed else 404)


class ForumButtonsTests(ForumSetup):
    """The species page has an "add a comment" button for its main observation and each other observation, and a link
    to the comments a visitor can read; the dive-trip page has one for its collection observation; the home page has
    one that leads to the picker; the main menu links to the forum, which is in the sitemap."""

    def test_species_page(self):
        self.message()
        self.message(manager_only=True)
        html = self.client.get(f'/species/{self.slug}/').content.decode()
        self.assertIn(f'href="/forum/new/?obs={self.sample.pk}">הוספת תגובה</a>', html)
        self.assertIn(f'href="/forum/?obs={self.sample.pk}">תגובות (1)</a>', html)
        self.client.force_login(self.owner)
        self.assertIn('תגובות (2)', self.client.get(f'/species/{self.slug}/').content.decode())
        self.assertIn(f'href="/forum/new/?obs={self.sample.pk}&amp;lang=en">Add a comment</a>',
                      self.client.get(f'/species/{self.slug}/?lang=en').content.decode())

    def test_trip_page(self):
        self.message(sample=self.collection)
        html = self.client.get('/trip/e1/').content.decode()
        self.assertIn(f'href="/forum/new/?obs={self.collection.pk}">הוספת תגובה</a>', html)
        self.assertIn(f'href="/forum/?obs={self.collection.pk}">תגובות (1)</a>', html)

    def test_home_page_and_menu(self):
        html = self.client.get('/').content.decode()
        self.assertIn('data-forum-link', html)
        self.assertIn('href="/forum/new/"', html)
        self.assertIn('href="/forum/"', html)

    def test_sitemap_and_robots(self):
        self.assertIn('/forum/</loc>', self.client.get('/sitemap.xml').content.decode())
        self.assertIn('Disallow: /forum/new/', self.client.get('/robots.txt').content.decode())


class ForumTransferTests(ForumSetup):
    """The conversations move between the Mac and the live site with the table transfer (table "forum"): matched by
    transfer_id, the observation by its transfer_id and the writer by username. Only new messages and deletions travel
    (a deleted message stays deleted); a message whose observation or writer is missing is skipped; nothing is removed."""

    def document(self):
        return json.loads(json.dumps(export_table('forum')))

    def apply_plan(self, doc):
        items = plan(doc)
        for item in items:
            if item['action'] in ('new', 'update'):
                item['object'].save()
        return items

    def test_registered_after_samples(self):
        tables = list(TABLES)
        self.assertGreater(tables.index('forum'), tables.index('samples'))
        self.assertGreater(tables.index('forum'), tables.index('users'))

    def test_export_row(self):
        message = self.message(manager_only=True, text='שורה')
        row = self.document()['rows'][0]
        self.assertEqual(set(row), set(FORUM_FIELDS))
        self.assertEqual((row['transfer_id'], row['observation'], row['user'], row['manager_only'], row['text'], row['deleted_at']),
                         (str(message.transfer_id), str(self.sample.transfer_id), 'member', True, 'שורה', None))

    def test_new_message_arrives_with_its_time(self):
        message = self.message(text='מהאתר החי')
        doc = self.document()
        created, key = message.created_at, message.transfer_id
        message.delete()
        items = self.apply_plan(doc)
        self.assertEqual([i['action'] for i in items], ['new'])
        arrived = ForumMessage.objects.get(transfer_id=key)
        self.assertEqual((arrived.created_at, arrived.text, arrived.observation, arrived.user), (created, 'מהאתר החי', self.sample, self.member))
        self.assertEqual([i['action'] for i in plan(doc)], ['same'])

    def test_deletion_travels_and_wins(self):
        message = self.message()
        alive = self.document()
        message.deleted_at = message.created_at; message.deleted_by = self.owner; message.save()
        deleted = self.document()
        message.deleted_at = None; message.deleted_by = None; message.save()
        self.assertEqual([i['action'] for i in self.apply_plan(deleted)], ['update'])
        message.refresh_from_db()
        self.assertIsNotNone(message.deleted_at)
        self.assertEqual(message.deleted_by, self.owner)
        self.assertEqual([i['action'] for i in self.apply_plan(alive)], ['same'])
        message.refresh_from_db()
        self.assertIsNotNone(message.deleted_at)

    def test_missing_observation_or_writer_is_skipped(self):
        self.message(text='א')
        self.message(user=self.other, text='ב')
        doc = self.document()
        ForumMessage.objects.all().delete()
        doc['rows'][0]['observation'] = '00000000-0000-0000-0000-000000000000'
        doc['rows'][1]['user'] = 'nobody'
        items = plan(doc)
        self.assertEqual([i['action'] for i in items], ['skipped', 'skipped'])
        self.assertIn('Samples', items[0]['reason'])
        self.assertIn('Users', items[1]['reason'])

    def test_wrong_fields_refused(self):
        self.message()
        doc = self.document()
        del doc['rows'][0]['subject']
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            plan(doc)


class ForumEmailTests(ForumSetup):
    """A new message written in the forum emails the observation's owner and the discussion's other writers -- only
    those who ticked "email me" on their profile (off by default), with an email address; never the writer. A message
    for the discussion's manager only goes to the owner alone. Messages arriving through the transfer send nothing."""

    def setUp(self):
        super().setUp()
        from .models import Profile
        for user, email in ((self.owner, 'owner@example.com'), (self.member, 'member@example.com'), (self.other, 'other@example.com')):
            user.email = email; user.save()
            Profile.objects.create(user=user, forum_email=True)

    def write(self, user, audience='all', text='הודעה'):
        from django.core import mail
        mail.outbox = []
        self.client.force_login(user)
        self.client.post('/forum/', {'obs': self.sample.pk, 'audience': audience, 'text': text})
        return sorted(m.to[0] for m in mail.outbox)

    def test_owner_and_participants(self):
        self.assertEqual(self.write(self.member), ['owner@example.com'])
        self.assertEqual(self.write(self.other), ['member@example.com', 'owner@example.com'])
        self.assertEqual(self.write(self.owner), ['member@example.com', 'other@example.com'])

    def test_manager_only_message_goes_to_the_owner_alone(self):
        self.write(self.member)
        self.assertEqual(self.write(self.other, audience='manager'), ['owner@example.com'])

    def test_only_when_asked_on_the_profile(self):
        from .models import Profile
        Profile.objects.filter(user=self.owner).update(forum_email=False)
        self.assertEqual(self.write(self.member), [])

    def test_email_content(self):
        from django.core import mail
        self.write(self.member, text='אולי זה מין אחר?')
        message = mail.outbox[0]
        self.assertIn('Phyllidia ocellata', message.subject)
        self.assertIn('אולי זה מין אחר?', message.body)
        self.assertIn(f'http://testserver/forum/?obs={self.sample.pk}#m-', message.body)

    def test_profile_checkbox(self):
        from .models import Profile
        Profile.objects.filter(user=self.other).update(forum_email=False)
        self.client.force_login(self.other)
        html = self.client.get('/observations/profile/').content.decode()
        self.assertIn('name="forum_email"', html)
        self.assertIn('Email me when a new comment arrives in the forum', self.client.get('/observations/profile/?lang=en').content.decode())

    def test_transfer_sends_nothing(self):
        from django.core import mail
        message = self.message()
        doc = json.loads(json.dumps(export_table('forum')))
        message.delete()
        mail.outbox = []
        for item in plan(doc):
            item['object'].save()
        self.assertEqual(mail.outbox, [])
