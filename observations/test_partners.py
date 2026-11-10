"""The macro diving partners page (/observations/partners/) in both languages."""
from django.contrib.auth.models import User
from django.test import TestCase

from .models import Country, Profile, Region, Sea


class PartnersPageTests(TestCase):
    """The page shows one language: headings, filters and the empty message through the translations, each member's
    name, countries and regions in the page's language; only members who chose to be listed."""

    def setUp(self):
        country = Country.objects.create(name='פיליפינים', name_en='Philippines')
        self.region = Region.objects.create(name='אנילאו', name_en='Anilao', country=country, sea=Sea.objects.create(name='ים סין'))
        diver = User.objects.create_user('diver', password='a-valid-password-927', first_name='דנה', last_name='כהן')
        profile = Profile.objects.create(user=diver, first_name_en='Dana', last_name_en='Cohen', macro_diver=True,
                                         visible_to_members=True, bio='Nudibranchs')
        profile.countries.add(country); profile.regions.add(self.region)
        from django.contrib.auth.models import Group
        self.group = Group.objects.get_or_create(name='Macro diver')[0]
        diver.groups.add(self.group)
        self.diver = diver
        hidden = User.objects.create_user('hidden', password='a-valid-password-927', first_name='נסתר')
        Profile.objects.create(user=hidden, macro_diver=True, visible_to_members=False)
        self.client.force_login(diver)

    def test_english(self):
        html = self.client.get('/observations/partners/?lang=en').content.decode()
        main = html.split('<main>')[1]
        self.assertIn('Macro diving partners', main)
        self.assertIn('Dana Cohen', main)
        self.assertIn('Philippines', main)
        self.assertIn('Anilao', main)
        self.assertIn('name="lang" value="en"', main)
        self.assertNotRegex(main.split('<div class="cards">')[0].replace('נסתר', ''), r'[֐-׿]')
        self.assertNotIn('נסתר', main)

    def test_hebrew_and_filter(self):
        html = self.client.get('/observations/partners/?lang=he').content.decode()
        self.assertIn('דנה כהן', html)
        self.assertIn('פיליפינים', html)
        self.assertIn('אין פרופילים להצגה', self.client.get(f'/observations/partners/?region={self.region.pk + 99}').content.decode())
        self.assertEqual(self.client.get('/observations/partners/?region=x').status_code, 200)


class MacroDiverGroupTests(TestCase):
    """A member is listed only with the profile's tick and "show my profile" and in the "Macro diver" group. The tick
    and the group follow each other: removing a member from the group in the admin unticks them (off the list), adding
    ticks them; the profile form adds / removes the group. The unused groups (New user, Subscriber, Artist) are gone and
    sign-up adds none."""

    def setUp(self):
        from django.contrib.auth.models import Group
        self.group = Group.objects.get_or_create(name='Macro diver')[0]
        self.diver = User.objects.create_user('zoch', password='a-valid-password-927', first_name='זוחמיר')
        Profile.objects.create(user=self.diver, macro_diver=True, visible_to_members=True)
        self.diver.groups.add(self.group)
        self.viewer = User.objects.create_user('viewer', password='a-valid-password-927')
        self.client.force_login(self.viewer)

    def listed(self):
        return 'זוחמיר' in self.client.get('/observations/partners/?lang=he').content.decode()

    def test_group_removal_takes_off_the_list(self):
        self.assertTrue(self.listed())
        self.diver.groups.remove(self.group)
        self.assertFalse(Profile.objects.get(user=self.diver).macro_diver)
        self.assertFalse(self.listed())
        self.diver.groups.add(self.group)
        self.assertTrue(Profile.objects.get(user=self.diver).macro_diver)
        self.assertTrue(self.listed())
        self.group.user_set.remove(self.diver)
        self.assertFalse(Profile.objects.get(user=self.diver).macro_diver)

    def test_admin_group_change(self):
        admin = User.objects.create_superuser('boss', 'b@example.org', 'a-valid-password-927')
        self.client.force_login(admin)
        page = self.client.get(f'/admin/auth/user/{self.diver.pk}/change/')
        form = page.context['adminform'].form
        data = {k: v for k, v in form.initial.items() if v is not None and k not in ('groups', 'user_permissions', 'password')}
        data.update({'date_joined_0': '2026-01-01', 'date_joined_1': '00:00:00', 'last_login_0': '', 'last_login_1': '',
                     'profile-TOTAL_FORMS': '1', 'profile-INITIAL_FORMS': '1', 'profile-MIN_NUM_FORMS': '0', 'profile-MAX_NUM_FORMS': '1',
                     'profile-0-id': str(self.diver.profile.pk), 'profile-0-user': str(self.diver.pk)})
        data = {k: (str(v) if not isinstance(v, bool) else ('on' if v else '')) for k, v in data.items()}
        data = {k: v for k, v in data.items() if v != ''}
        self.client.post(f'/admin/auth/user/{self.diver.pk}/change/', data)    # groups left empty
        self.assertFalse(self.diver.groups.filter(name='Macro diver').exists())
        self.assertFalse(Profile.objects.get(user=self.diver).macro_diver)

    def test_tick_without_group_not_listed(self):
        self.diver.groups.remove(self.group)
        Profile.objects.filter(user=self.diver).update(macro_diver=True)
        self.assertFalse(self.listed())

    def test_profile_form_adds_the_group(self):
        self.diver.groups.remove(self.group)
        self.client.force_login(self.diver)
        self.client.post('/observations/profile/', {'first_name': 'זוחמיר', 'macro_diver': 'on', 'visible_to_members': 'on'})
        self.assertTrue(self.diver.groups.filter(name='Macro diver').exists())

    def test_unused_groups_removed_and_signup_adds_none(self):
        import importlib
        from django.apps import apps
        from django.contrib.auth.models import Group
        Group.objects.create(name='New user'); Group.objects.create(name='Artist')
        lone = User.objects.create_user('lone', password='a-valid-password-927')
        Profile.objects.create(user=lone, macro_diver=True)
        importlib.import_module('observations.migrations.0099_macro_diver_group_and_unused_groups').forwards(apps, None)
        self.assertFalse(Group.objects.filter(name__in=['New user', 'Artist']).exists())
        self.assertFalse(Profile.objects.get(user=lone).macro_diver)          # ticked without the group
        self.assertTrue(Profile.objects.get(user=self.diver).macro_diver)
        self.client.logout()
        self.client.post('/observations/signup/', {'username': 'newdiver', 'email': 'n@example.com',
                                                   'password1': 'Very-long-pw-9876', 'password2': 'Very-long-pw-9876'})
        self.assertFalse(User.objects.get(username='newdiver').groups.exists())
