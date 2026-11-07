"""Sign-up asks for the name in both languages, and "I am a photographer" (bilingual) is on the sign-up and profile
forms.

Rules:
- The sign-up form has the Hebrew name (the user's first/last name, labelled "בעברית") and the English name (saved to
  the profile's first_name_en/last_name_en) side by side, before the email; the help says each language's pages
  credit the photographer by its own.
- "אני צלם/ת" / "I am a photographer" puts the user in the photographer group (photographers.py) at sign-up and on
  the profile, and unticking it on the profile takes them out. Someone with observations is a photographer: the box
  stays ticked and cannot be changed. The box is shown in the page's language.
"""
from django.contrib.auth.models import Group, User
from django.test import TestCase

from .models import Country, DiveTrip, Profile, Region, Sample, Sea, Species
from .photographers import PHOTOGRAPHER_GROUP, photographer_users


def signup_data(**extra):
    data = dict(username='newdiver', email='new@example.com', first_name='נועה', last_name='כהן',
                first_name_en='Noa', last_name_en='Cohen',
                password1='really-unusual-password-731', password2='really-unusual-password-731')
    data.update(extra)
    return data


class SignupNamesTests(TestCase):
    def test_both_names_are_asked_in_order(self):
        form = self.client.get('/observations/signup/').context['form']
        self.assertEqual(list(form.fields)[:7], ['username', 'first_name', 'last_name', 'first_name_en', 'last_name_en',
                                                 'email', 'password1'])
        self.assertEqual(form.fields['first_name'].label, 'שם פרטי בעברית')

    def test_english_name_is_saved_to_the_profile(self):
        self.client.post('/observations/signup/', signup_data())
        user = User.objects.get(username='newdiver')
        self.assertEqual((user.first_name, user.last_name), ('נועה', 'כהן'))
        profile = Profile.objects.get(user=user)
        self.assertEqual((profile.first_name_en, profile.last_name_en), ('Noa', 'Cohen'))

    def test_english_labels(self):
        html = self.client.get('/observations/signup/', {'lang': 'en'}).content.decode()
        for text in ('First name (Hebrew)', 'First name (English)', 'I am a photographer',
                     'Your name is the photo credit'):
            self.assertIn(text, html)
        self.assertIn('אני צלם/ת', self.client.get('/observations/signup/', {'lang': 'he'}).content.decode())


class PhotographerCheckboxTests(TestCase):
    def test_signup_as_a_photographer(self):
        self.client.post('/observations/signup/', signup_data(is_photographer='on'))
        self.assertIn(User.objects.get(username='newdiver'), photographer_users())

    def test_signup_as_a_diver_only(self):
        self.client.post('/observations/signup/', signup_data())
        self.assertNotIn(User.objects.get(username='newdiver'), photographer_users())

    def profile_post(self, **extra):
        data = {'first_name': 'נועה', 'last_name': 'כהן', 'first_name_en': 'Noa', 'last_name_en': 'Cohen', 'phone': '', 'bio': ''}
        data.update(extra)
        return self.client.post('/observations/profile/', data)

    def test_profile_box_adds_and_removes(self):
        user = User.objects.create_user('noa', password='really-unusual-password-731')
        self.client.force_login(user)
        self.assertFalse(self.client.get('/observations/profile/').context['form'].fields['is_photographer'].initial)
        self.assertEqual(self.profile_post(is_photographer='on').status_code, 302)
        self.assertIn(user, photographer_users())
        self.assertTrue(self.client.get('/observations/profile/').context['form'].fields['is_photographer'].initial)
        self.profile_post()
        self.assertNotIn(user, photographer_users())

    def test_with_observations_the_box_stays_ticked(self):
        user = User.objects.create_user('noa', password='really-unusual-password-731')
        country = Country.objects.create(name='ישראל')
        region = Region.objects.create(name='אכזיב', country=country, sea=Sea.objects.create(name='הים התיכון'))
        trip = DiveTrip.objects.create(title='T', code='T1', year=2026, month=1, country=country, region=region)
        Sample.objects.create(owner=user, trip=trip, kind='species', species=Species.objects.create(scientific_name='X y'),
                              video_url='https://youtu.be/abcdefghijk')
        user.groups.add(Group.objects.get_or_create(name=PHOTOGRAPHER_GROUP)[0])
        self.client.force_login(user)
        field = self.client.get('/observations/profile/').context['form'].fields['is_photographer']
        self.assertTrue(field.disabled and field.initial)
        self.profile_post()                    # an unticked box cannot take them out
        self.assertIn(user, photographer_users())
