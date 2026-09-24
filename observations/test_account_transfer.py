from pathlib import Path
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth.models import User, Group, Permission
from django.core.exceptions import ValidationError
from .models import Profile, Country, Sea, Region
from .table_transfer import export_table, plan, apply, fingerprint


class AccountTransferTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('manager', password='known-password')
        self.group = Group.objects.create(name='Scientist')
        self.group.permissions.add(Permission.objects.get(codename='view_species'))
        self.user.groups.add(self.group)

    def execute(self, doc):
        with patch('observations.table_transfer.create_backup', return_value=Path('backup.sqlite3')):
            return apply(doc, fingerprint(), actor=self.user)

    def test_password_preserved_and_new_user_without_password(self):
        doc = export_table('users')
        self.assertNotIn('password', doc['rows'][0])
        doc['rows'][0]['first_name'] = 'Updated'
        self.execute(doc)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('known-password'))
        self.assertEqual(plan(doc)[0]['action'], 'same')
        doc['rows'][0].update(username='new-member', is_staff=False, is_superuser=False)
        self.execute(doc)
        user = User.objects.get(username='new-member')
        self.assertFalse(user.has_usable_password())
        self.assertEqual(list(user.groups.values_list('name',flat=True)), ['Scientist'])

    def test_group_permissions_and_missing_dependencies(self):
        doc = export_table('groups')
        self.assertEqual(plan(doc)[0]['action'], 'same')
        doc['rows'][0]['permissions'] = []
        self.execute(doc)
        self.assertFalse(self.group.permissions.exists())
        doc['rows'][0]['permissions'] = ['missing.model.permission']
        with self.assertRaises(ValidationError): plan(doc)

    def test_profile_relationships(self):
        country = Country.objects.create(name='Israel')
        sea = Sea.objects.create(name='Red Sea')
        region = Region.objects.create(name='Eilat',country=country,sea=sea)
        profile = Profile.objects.create(user=self.user,first_name_en='Boaz',macro_diver=True)
        profile.countries.add(country); profile.regions.add(region)
        doc = export_table('profiles')
        self.assertEqual(plan(doc)[0]['action'],'same')
        doc['rows'][0].update(bio='New bio',regions=[])
        self.execute(doc)
        profile.refresh_from_db()
        self.assertEqual(profile.bio,'New bio')
        self.assertFalse(profile.regions.exists())

    def test_self_lockout_and_stale_preview_blocked(self):
        doc = export_table('users'); doc['rows'][0]['is_superuser'] = False
        with self.assertRaises(ValidationError): self.execute(doc)
        doc = export_table('groups'); snapshot = fingerprint()
        self.user.groups.clear()
        with patch('observations.table_transfer.create_backup', return_value=Path('backup.sqlite3')):
            with self.assertRaises(ValidationError): apply(doc,snapshot,actor=self.user)
