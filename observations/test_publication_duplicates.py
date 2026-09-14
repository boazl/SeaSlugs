from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from .models import Sample, Species, Country, Region, Sea
from .table_transfer import export_table, plan


class DuplicatePublicationTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_superuser('manager',password='test-password')
        self.other=User.objects.create_user('other')
        country=Country.objects.create(name='Israel')
        sea=Sea.objects.create(name='Mediterranean')
        self.region=Region.objects.create(name='Akhziv',country=country,sea=sea)
        self.species=Species.objects.create(scientific_name='Test species')
        self.first=self.record(self.user)
        self.second=self.record(self.other)

    def record(self,owner):
        item=Sample(owner=owner,species=self.species,country=self.region.country,region=self.region,year=2026,video_url='https://youtu.be/abcdefghijk')
        item.save_reviewed();return item

    def test_manager_cannot_approve_duplicate_and_reason_visible(self):
        self.assertEqual(self.second.status,'pending')
        with self.assertRaises(ValidationError):self.second.save_reviewed(actor=self.user,approve=True)
        self.client.force_login(self.user)
        for url in ['/admin/observations/sample/',f'/admin/observations/sample/{self.second.pk}/change/']:
            response=self.client.get(url)
            self.assertContains(response,'המין כבר מפורסם באזור זה')
            self.assertContains(response,'color:#ba2121')

    def test_database_blocks_bypass_but_deleted_record_releases_slot(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Sample.objects.filter(pk=self.second.pk).update(status='published')
        self.first.soft_delete(self.user)
        self.second.save_reviewed(actor=self.user,approve=True)
        self.assertEqual(self.second.status,'published')

    def test_another_region_allowed_and_same_row_edit_allowed(self):
        self.first.title='Updated';self.first.save_reviewed()
        self.assertEqual(self.first.status,'published')
        self.second.region=Region.objects.create(name='Caesarea',country=self.region.country,sea=self.region.sea)
        self.second.save_reviewed(actor=self.user,approve=True)
        self.assertEqual(self.second.status,'published')

    def test_import_rejects_duplicate_publication(self):
        doc=export_table('samples')
        doc['rows']=[next(r for r in doc['rows'] if r['status']=='published')]
        doc['rows'][0]['video_url']='https://youtu.be/12345678901'
        import uuid
        doc['rows'][0]['transfer_id']=str(uuid.uuid4())
        with self.assertRaises(ValidationError):plan(doc)
