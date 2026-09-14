from pathlib import Path
from unittest.mock import patch
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from .models import Species,Country,Sea,Region,Site
from .table_transfer import export_table,plan,fingerprint,apply

class TransferTests(TestCase):
    def setUp(self):
        self.species=Species.objects.create(scientific_name='Species a',name_he='ישן',source_id='source-a')
    def test_unchanged_and_partial_update(self):
        doc=export_table('species');self.assertEqual(plan(doc)[0]['action'],'same')
        doc['rows'][0]['name_he']='חדש'
        self.assertEqual(len(plan(doc)[0]['changes']),1)
        snapshot=fingerprint()
        with patch('observations.table_transfer.create_backup',return_value=Path('test.sqlite3')):apply(doc,snapshot)
        self.species.refresh_from_db();self.assertEqual(self.species.name_he,'חדש')
        self.assertEqual(Species.objects.count(),1)
        self.assertEqual(plan(doc)[0]['action'],'same')
    def test_rename_with_source_id(self):
        doc=export_table('species');doc['rows'][0]['scientific_name']='Species b'
        self.assertEqual(plan(doc)[0]['object'].pk,self.species.pk)
    def test_no_deletion_and_stale_preview(self):
        doc=export_table('species');doc['rows']=[];snapshot=fingerprint()
        with patch('observations.table_transfer.create_backup',return_value=Path('test.sqlite3')):apply(doc,snapshot)
        self.assertEqual(Species.objects.count(),1)
        self.species.name_he='changed';self.species.save()
        with patch('observations.table_transfer.create_backup',return_value=Path('test.sqlite3')):
            with self.assertRaises(ValidationError):apply(doc,snapshot)
    def test_ambiguity_invalid_schema_and_duplicate(self):
        doc=export_table('species');doc['rows']*=2
        with self.assertRaises(ValidationError):plan(doc)
        doc=export_table('species');doc['rows'][0]['id']=55
        with self.assertRaises(ValidationError):plan(doc)
        Country.objects.create(name='same');Country.objects.create(name='same')
        with self.assertRaises(ValidationError):plan(export_table('countries'))
    def test_dependency_mapping_does_not_use_pk(self):
        c=Country.objects.create(name='ישראל');sea=Sea.objects.create(name='ים תיכון')
        r=Region.objects.create(name='אכזיב',country=c,sea=sea)
        Site.objects.create(name='אתר',region=r)
        doc=export_table('sites');self.assertNotIn('id',doc['rows'][0])
        self.assertEqual(plan(doc)[0]['object'].region_id,r.pk)
        doc['rows'][0]['region']['country']='missing'
        with self.assertRaises(ValidationError):plan(doc)
    def test_access_and_export(self):
        self.assertEqual(self.client.get('/admin/table-transfer/').status_code,302)
        staff=User.objects.create_user('staff',is_staff=True);self.client.force_login(staff)
        self.assertEqual(self.client.get('/admin/table-transfer/').status_code,403)
        root=User.objects.create_superuser('root','root@example.com','test-pass');self.client.force_login(root)
        self.assertEqual(self.client.get('/admin/table-transfer/').status_code,200)
        self.assertEqual(self.client.post('/admin/table-transfer/',{'action':'export','table':'species'}).json()['rows'][0]['scientific_name'],'Species a')
    def test_scientific_species_fields_roundtrip_and_legacy_preservation(self):
        self.species.genus='Species';self.species.species='a';self.species.author='Author, 2020';self.species.save()
        doc=export_table('species');self.assertEqual(doc['rows'][0]['author'],'Author, 2020')
        self.assertEqual(plan(doc)[0]['action'],'same')
        legacy=dict(doc,rows=[{k:doc['rows'][0][k] for k in ['scientific_name','name_he','name_en','source_id']}])
        legacy['rows'][0]['name_he']='updated'
        with patch('observations.table_transfer.create_backup',return_value=Path('test.sqlite3')):apply(legacy,fingerprint())
        self.species.refresh_from_db();self.assertEqual(self.species.author,'Author, 2020')
    def test_species_admin_scientific_fields_and_hidden_import_id(self):
        user=User.objects.create_superuser('scientific-admin',password='test-password')
        self.client.force_login(user)
        response=self.client.get(f'/admin/observations/species/{self.species.pk}/change/')
        self.assertContains(response,'name="genus"');self.assertContains(response,'name="author"')
        self.assertNotContains(response,'name="source_id"')
