import json
from pathlib import Path
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from .models import TaxonOrder, TaxonFamily, TaxonGenus
from .table_transfer import TABLES, export_table, plan, fingerprint, apply

BACKUP = patch('observations.table_transfer.create_backup', return_value=Path('test.sqlite3'))


class TaxonTransferTests(TestCase):
    def setUp(self):
        self.order = TaxonOrder.objects.create(name='Nudibranchia', sub_order='Doridina', taxonomic_order='3')
        self.other_order = TaxonOrder.objects.create(name='Nudibranchia', sub_order='Cladobranchia', taxonomic_order='4')
        self.family = TaxonFamily.objects.create(name='Chromodorididae', order=self.order)
        self.genus = TaxonGenus.objects.create(name='Felimare', family=self.family, description_he='תיאור מקומי')

    def apply(self, doc):
        with BACKUP:
            return apply(doc, fingerprint())

    def test_tables_are_listed_before_species_and_carry_no_links(self):
        names = list(TABLES)
        for table in ('orders', 'families', 'genera'):
            self.assertLess(names.index(table), names.index('species'))
            for forbidden in ('order', 'family', 'defining_sample', 'article_pdf', 'id'):
                self.assertNotIn(forbidden, TABLES[table][1])

    def test_export_has_no_ids_and_round_trips_as_same(self):
        for table, count in (('orders', 2), ('families', 1), ('genera', 1)):
            doc = export_table(table)
            self.assertEqual(len(doc['rows']), count)
            self.assertNotIn('id', doc['rows'][0])
            self.assertTrue(all(item['action'] == 'same' for item in plan(doc)))

    def test_texts_update_existing_rows_by_identity(self):
        doc = export_table('genera')
        doc['rows'][0].update(description_he='תיאור חדש', description_en='New text', identification_he='סימני זיהוי',
                              sources='https://example.org/a\nhttps://example.org/b',
                              identification_caption_en='Caption', identification_source='Smith 2020')
        items = plan(doc)
        self.assertEqual(items[0]['action'], 'update')
        self.assertEqual(len(items[0]['changes']), 6)
        self.apply(doc)
        self.genus.refresh_from_db()
        self.assertEqual(self.genus.description_he, 'תיאור חדש')
        self.assertEqual(self.genus.sources, 'https://example.org/a\nhttps://example.org/b')
        self.assertEqual(self.genus.identification_caption_en, 'Caption')
        self.assertEqual(self.genus.identification_source, 'Smith 2020')
        self.assertEqual(self.genus.family_id, self.family.pk)  # links are never touched
        self.assertEqual(TaxonGenus.objects.count(), 1)
        self.assertTrue(all(item['action'] == 'same' for item in plan(doc)))

    def test_orders_and_families_are_matched_by_their_whole_identity(self):
        doc = export_table('orders')
        {r['sub_order']: r for r in doc['rows']}['Cladobranchia']['description_en'] = 'Clado text'
        self.apply(doc)
        self.order.refresh_from_db(); self.other_order.refresh_from_db()
        self.assertEqual(self.other_order.description_en, 'Clado text')
        self.assertEqual(self.order.description_en, '')
        doc = export_table('families')
        doc['rows'][0]['name_he'] = 'כרומודורידים'
        self.apply(doc)
        self.family.refresh_from_db()
        self.assertEqual(self.family.name_he, 'כרומודורידים')

    def test_missing_target_is_skipped_never_created(self):
        doc = export_table('genera')
        doc['rows'][0]['name'] = 'Nonexistent'
        items = plan(doc)
        self.assertEqual(items[0]['action'], 'skipped')
        self.assertIn('Nonexistent', items[0]['label'])
        self.apply(doc)
        self.assertEqual(TaxonGenus.objects.count(), 1)
        self.assertFalse(TaxonGenus.objects.filter(name='Nonexistent').exists())

    def test_line_endings_and_whitespace_are_normalised(self):
        doc = export_table('genera')
        doc['rows'][0]['description_he'] = '  שורה\r\nשניה \n'
        self.apply(doc)
        self.genus.refresh_from_db()
        self.assertEqual(self.genus.description_he, 'שורה\nשניה')

    def test_invalid_documents_are_rejected(self):
        def broken(change):
            doc = export_table('genera')
            change(doc)
            with self.assertRaises(ValidationError):
                plan(doc)
        broken(lambda d: d['rows'][0].update(extra='x'))
        broken(lambda d: d['rows'][0].pop('sources'))
        broken(lambda d: d['rows'][0].update(description_he=5))
        broken(lambda d: d.update(rows=d['rows'] * 2))
        broken(lambda d: d['rows'][0].update(link='not a url'))
        broken(lambda d: d.update(rows=['text']))

    def test_stale_preview_is_refused(self):
        doc = export_table('genera'); doc['rows'][0]['description_he'] = 'חדש'
        snapshot = fingerprint()
        self.genus.description_en = 'edited meanwhile'; self.genus.save()
        with BACKUP:
            with self.assertRaises(ValidationError):
                apply(doc, snapshot)

    def test_transfer_page_end_to_end(self):
        root = User.objects.create_superuser('root', 'root@example.com', 'test-pass'); self.client.force_login(root)
        page = self.client.get('/admin/table-transfer/').content.decode()
        for table in ('orders', 'families', 'genera'):
            self.assertIn(f'value="{table}"', page)
        exported = self.client.post('/admin/table-transfer/', {'action': 'export', 'table': 'genera'})
        self.assertEqual(exported['Content-Disposition'], 'attachment; filename="seaslugs-genera.json"')
        doc = exported.json(); doc['rows'][0]['description_en'] = 'From file'
        doc['rows'].append(dict(doc['rows'][0], name='Elsewhere'))
        upload = SimpleUploadedFile('g.json', json.dumps(doc).encode(), content_type='application/json')
        preview = self.client.post('/admin/table-transfer/', {'action': 'preview', 'file': upload})
        self.assertContains(preview, 'Elsewhere')
        self.assertContains(preview, 'From file')
        self.assertEqual(preview.context['changed'], 1)
        with BACKUP:
            self.client.post('/admin/table-transfer/', {'action': 'apply', 'confirm': 'yes', 'token': preview.context['token']})
        self.genus.refresh_from_db()
        self.assertEqual(self.genus.description_en, 'From file')


class TransferSizeLimitTests(TestCase):
    def upload(self, pad):
        import json
        from django.core.files.uploadedfile import SimpleUploadedFile
        doc = {'format': 'seaslugs-reference-v1', 'table': 'genera', 'rows': [], 'pad': 'x' * pad}
        return self.client.post('/admin/table-transfer/', {'action': 'preview', 'file': SimpleUploadedFile('g.json', json.dumps(doc).encode(), content_type='application/json')})

    def setUp(self):
        self.client.force_login(User.objects.create_superuser('root', 'root@example.com', 'test-pass'))

    def test_a_file_over_5mb_is_accepted_the_whole_species_table_is_about_that_big(self):
        response = self.upload(6 * 1024 * 1024)
        self.assertNotContains(response, 'גדול מ')
        self.assertIn('token', response.context)

    def test_a_huge_file_is_still_refused(self):
        self.assertContains(self.upload(21 * 1024 * 1024), 'קובץ JSON גדול מ־20MB')
