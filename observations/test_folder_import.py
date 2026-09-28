from .folder_import import match_species,plan_row
from .models import Species,DiveTrip,Sample
from django.core.exceptions import ValidationError
from pathlib import Path
from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.base import ContentFile
from django.test import TestCase,override_settings
from django.contrib.auth.models import User
from .models import Country,Sea,Region
from PIL import Image
import tempfile,io

class FolderImportTests(TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        settings=override_settings(DATA_DIR=self.temp.name,MEDIA_ROOT=self.temp.name+'/media');settings.enable();self.addCleanup(settings.disable)
        self.user=User.objects.create_superuser('importer',password='test')
        self.country=Country.objects.create(name='Philippines');sea=Sea.objects.create(name='Pacific')
        self.region=Region.objects.create(name='Romblon',country=self.country,sea=sea)
        self.trip=DiveTrip.objects.create(title='Trip',year=2026,month=1,country=self.country,region=self.region)
        self.species=Species.objects.create(scientific_name='Micromelo undatus')
    def photo(self):
        output=io.BytesIO();Image.new('RGB',(40,30),'blue').save(output,'JPEG')
        return SimpleUploadedFile('002-Micromelo undatus 2025.jpg',output.getvalue(),content_type='image/jpeg')
    def test_matching_keeps_species_identifiers(self):
        species=[self.species,Species.objects.create(scientific_name='Elysia sp.'),Species.objects.create(scientific_name='Elysia sp. 5')]
        self.assertEqual(match_species('002-Micromelo undatus (Author, 1900).jpg',species),(self.species.pk,''))
        self.assertEqual(match_species('C16-Elysia sp. 5 2025.jpg',species),(species[-1].pk,''))
        self.assertEqual(match_species('C16-Elysia sp. 7.jpg',species),(None,''))
    def test_matching_extracts_the_undetermined_variant_letter_from_the_filename(self):
        # Two visibly distinct, still-undescribed "sp." forms of one genus share ONE bare
        # catalog row -- there is no per-form row in Species any more (see
        # Sample.undetermined_variant / split_undetermined_variant). A filename naming a
        # variant letter must still match that one row, with the letter returned alongside
        # the pk so the caller can record it on the resulting Sample; a bare, un-suffixed
        # filename matches too, with an empty variant.
        bare=Species.objects.create(scientific_name='Coryphellina sp.')
        species=[bare]
        self.assertEqual(match_species("701-Coryphellina sp.B O'Donoghue, 1929-Edit.jpg",species),(bare.pk,'B'))
        self.assertEqual(match_species('Coryphellina sp. A.jpg',species),(bare.pk,'A'))
        self.assertEqual(match_species('Coryphellina sp..jpg',species),(bare.pk,''))
    def test_matching_ignores_whether_sp_qualifier_has_a_space_before_its_number(self):
        # Filenames and the species table don't always agree on "sp.18" vs "sp. 18" --
        # a photographer's export tool may drop the space the species table uses, or add
        # one it doesn't have. Either direction must still match.
        species=[Species.objects.create(scientific_name='Tenellia sp. 18'),
                  Species.objects.create(scientific_name='Doto sp.7')]
        self.assertEqual(match_species('713-Tenellia sp.18 2023.jpg',species),(species[0].pk,''))
        self.assertEqual(match_species('713-Tenellia sp.18-Edit.jpg',species),(species[0].pk,''))
        self.assertEqual(match_species('C16-Doto sp. 7.jpg',species),(species[1].pk,''))
        # Still correctly distinguishes a different number either way.
        self.assertEqual(match_species('713-Tenellia sp.19.jpg',species),(None,''))
    def test_preview_then_create_from_trip_not_filename_year(self):
        self.client.force_login(self.user)
        response=self.client.post('/admin/images/folder/',{'action':'preview','trip':self.trip.pk,'images':self.photo()})
        self.assertEqual(Sample.objects.count(),0);self.assertIn('token',response.context)
        with patch('observations.folder_import.create_backup',return_value=Path('backup.sqlite3')):
            response=self.client.post('/admin/images/folder/',{'action':'apply','token':response.context['token'],'selected':['0'],'species_0':str(self.species),'confirm':'yes'})
        self.assertEqual(response.status_code,302)
        item=Sample.objects.get();self.assertEqual(item.trip.year,2026);self.assertEqual(item.trip.month,1);self.assertIsNone(item.day);self.assertTrue(item.image);self.assertEqual(item.trip,self.trip)
    def test_preview_flags_a_photo_already_used_by_a_different_observation(self):
        # Sample.clean() already refuses to save an image whose content matches another
        # sample's (see its image_hash duplicate check) -- but until now that check only ran
        # inside apply()'s single atomic transaction, where ONE such conflict anywhere in a
        # big batch aborted and rolled back every other row in the same submission, with no
        # indication which file was at fault. Running the same check during preview instead
        # flags just the offending row (disabling its checkbox) and leaves the rest of the
        # batch completely unaffected.
        from observations.forms import SampleForm
        raw=io.BytesIO();Image.new('RGB',(40,30),'green').save(raw,'JPEG');raw=raw.getvalue()
        # clean_image() re-encodes on every upload (even a folder-import one) -- run it once
        # here too so the "existing" sample's stored image is byte-identical to what preview
        # will independently produce for the same raw input below.
        form=SampleForm();form.cleaned_data={'image':SimpleUploadedFile('x.jpg',raw,content_type='image/jpeg')}
        processed=form.clean_image().read()
        # A DIFFERENT trip -- otherwise plan_row would (correctly) treat the new row as
        # updating this very sample's own image rather than as a conflict with another one.
        other_trip=DiveTrip.objects.create(title='Other',year=2026,country_name='Philippines',region_name='Romblon')
        other_species=Species.objects.create(scientific_name='Elysia sp.')
        existing=Sample(owner=self.user,species=other_species,trip=other_trip)
        existing.image.save('existing.jpg',ContentFile(processed),save=False)
        existing.save_reviewed()
        self.client.force_login(self.user)
        duplicate_photo=SimpleUploadedFile('317-Elysia sp. 2025.jpg',raw,content_type='image/jpeg')
        response=self.client.post('/admin/images/folder/',{'action':'preview','trip':self.trip.pk,'images':[duplicate_photo,self.photo()]})
        rows=response.context['rows']
        self.assertIn('כבר קיימת בתצפית אחרת',rows[0]['error'])
        self.assertFalse(rows[0]['checked'])
        self.assertEqual(rows[1]['error'],'')
        self.assertTrue(rows[1]['checked'])
    def test_new_sample_action_text_is_bolded_but_others_are_not(self):
        # "יצירת תצפית עם תמונה" (creating a brand-new observation) is the action worth the
        # operator's eye first when scanning a big batch, unlike replacing/completing an
        # existing one -- see the analogous highlight for the single-observation form's own
        # success message.
        existing=Sample(owner=self.user,species=self.species,trip=self.trip)
        output=io.BytesIO();Image.new('RGB',(40,30),'blue').save(output,'JPEG')
        existing.image.save('original.jpg',ContentFile(output.getvalue()),save=False)
        existing.save_reviewed()
        Species.objects.create(scientific_name='Phyllidia elegans')
        self.client.force_login(self.user)
        new_species_photo=self.photo();new_species_photo.name='403-Phyllidia elegans 2025.jpg'
        response=self.client.post('/admin/images/folder/',{'action':'preview','trip':self.trip.pk,'images':[self.photo(),new_species_photo]})
        content=response.content.decode()
        self.assertIn('<strong>יצירת תצפית עם תמונה</strong>',content)
        self.assertNotIn('<strong>החלפת תמונה קיימת</strong>',content)
        self.assertIn('החלפת תמונה קיימת',content)
    def test_species_dropdown_is_sorted_alphabetically(self):
        # The species table's default ordering is taxonomic (phylogenetic order), not
        # alphabetical -- fine for the public listing, but the autocomplete datalist backing
        # the free-text species field has hundreds of entries an operator picks from by
        # name, so it needs its own alphabetical order.
        Species.objects.create(scientific_name='Aaa species')
        Species.objects.create(scientific_name='Zzz species')
        self.client.force_login(self.user)
        response=self.client.post('/admin/images/folder/',{'action':'preview','trip':self.trip.pk,'images':self.photo()})
        content=response.content.decode()
        start=content.index('<datalist id="species-options"')
        datalist=content[start:content.index('</datalist>',start)]
        self.assertLess(datalist.index('Aaa species'),datalist.index('Micromelo undatus'))
        self.assertLess(datalist.index('Micromelo undatus'),datalist.index('Zzz species'))
    def test_preview_defaults_to_unchecked_when_the_photo_would_replace_an_existing_image(self):
        # Overwriting a sample's existing image is destructive (the previous file is
        # deleted, no backup) -- an operator must actively opt in, not just click through
        # a checkbox that was already ticked for them.
        existing=Sample(owner=self.user,species=self.species,trip=self.trip)
        output=io.BytesIO();Image.new('RGB',(40,30),'blue').save(output,'JPEG')
        existing.image.save('original.jpg',ContentFile(output.getvalue()),save=False)
        existing.save_reviewed()
        self.client.force_login(self.user)
        response=self.client.post('/admin/images/folder/',{'action':'preview','trip':self.trip.pk,'images':self.photo()})
        row=response.context['rows'][0]
        self.assertEqual(row['description'],'החלפת תמונה קיימת')
        self.assertFalse(row['checked'])
    def test_preview_defaults_to_checked_when_completing_a_video_only_sample(self):
        # No existing image means nothing is at risk of being overwritten -- this is just
        # adding the first photo to an otherwise media-complete observation, so it should
        # stay checked like a brand-new sample would.
        Sample.objects.create(owner=self.user,species=self.species,trip=self.trip,
            kind=Sample.Kind.SPECIES,status=Sample.Status.PENDING,video_url='https://youtu.be/abcdefghijk')
        self.client.force_login(self.user)
        response=self.client.post('/admin/images/folder/',{'action':'preview','trip':self.trip.pk,'images':self.photo()})
        row=response.context['rows'][0]
        self.assertEqual(row['description'],'הוספת תמונה לתצפית')
        self.assertTrue(row['checked'])
    def test_other_trip_creates_new_sample_and_same_trip_updates(self):
        item=Sample(owner=self.user,species=self.species,trip=self.trip,video_url='https://youtu.be/abcdefghijk');item.save_reviewed()
        self.assertEqual(plan_row(self.trip,self.species.pk,self.user)[1],'update')
        # a different trip for the same species is a brand-new sample, not a blocked duplicate
        other=DiveTrip.objects.create(title='Other',year=2026,country_name='Philippines',region_name='Romblon')
        self.assertEqual(plan_row(other,self.species.pk,self.user)[1],'new')
    def test_duplicate_selection_keeps_first_and_skips_second(self):
        import hashlib
        from django.core import signing
        self.client.force_login(self.user)
        second=self.photo();second.name='002-Micromelo undatus 2026.jpg'
        response=self.client.post('/admin/images/folder/',{'action':'preview','trip':self.trip.pk,'images':[self.photo(),second]})
        token=response.context['token']
        first_digest=response.context['rows'][0]['digest']
        with patch('observations.folder_import.create_backup',return_value=Path('backup.sqlite3')):
            response=self.client.post('/admin/images/folder/',{'action':'apply','token':token,'selected':['1','0'],'species_0':str(self.species),'species_1':str(self.species),'confirm':'yes'},follow=True)
        self.assertEqual(Sample.objects.count(),1)
        item=Sample.objects.get()
        self.assertEqual(hashlib.sha256(Path(item.image.path).read_bytes()).hexdigest(),first_digest)
        self.assertContains(response,'דולגו 1 תמונות כפולות')
    def test_large_folder_and_confirmation_fit_request_limits(self):
        from django.conf import settings
        from django.test import RequestFactory
        self.assertGreaterEqual(settings.DATA_UPLOAD_MAX_NUMBER_FILES,500)
        request=RequestFactory().post('/admin/images/folder/',{'images':[self.photo() for _ in range(500)]})
        self.assertEqual(len(request.FILES.getlist('images')),500)
        data={'action':'apply','token':'test','confirm':'yes','selected':[str(i) for i in range(500)]}
        data.update({f'species_{i}':str(self.species.pk) for i in range(500)})
        request=RequestFactory().post('/admin/images/folder/',data)
        self.assertEqual(len(request.POST.getlist('selected')),500)
    def test_create_missing_species_once_only_after_confirmation(self):
        self.client.force_login(self.user)
        photo=self.photo();photo.name='205-Thecacera picta-Baba, 1972.jpeg'
        second=self.photo();second.name='205-Thecacera picta 2025.jpg'
        response=self.client.post('/admin/images/folder/',{'action':'preview','trip':self.trip.pk,'images':[photo,second]})
        self.assertEqual(response.context['rows'][0]['proposed'],'Thecacera picta')
        self.assertFalse(Species.objects.filter(scientific_name='Thecacera picta').exists())
        with patch('observations.folder_import.create_backup',return_value=Path('backup.sqlite3')):
            response=self.client.post('/admin/images/folder/',{'action':'apply','token':response.context['token'],'selected':['0','1'],'species_0':'Thecacera picta','species_1':'Thecacera picta','confirm':'yes'},follow=True)
        species=Species.objects.get(scientific_name='Thecacera picta')
        self.assertEqual(species.genus,'Thecacera');self.assertEqual(species.species,'picta');self.assertEqual(species.phylogenetic_order,'205')
        self.assertEqual(Sample.objects.filter(species=species).count(),1)
        self.assertContains(response,'דולגו 1 תמונות כפולות')
    def test_completing_an_existing_pending_sample_publishes_and_registers_species_area(self):
        # An existing sample for this species+trip with no image yet (e.g. created
        # manually, or by an earlier partial import) is an 'update' match, not
        # 'new' -- but adding its image here is exactly what makes it complete,
        # so it must still get published and registered in SpeciesArea, just
        # like a brand-new sample created by this same tool would.
        from .models import SpeciesArea
        existing=Sample.objects.create(owner=self.user,species=self.species,trip=self.trip,status='pending')
        self.assertEqual(plan_row(self.trip,self.species.pk,self.user)[1],'update')
        self.assertFalse(SpeciesArea.objects.filter(species=self.species).exists())
        self.client.force_login(self.user)
        response=self.client.post('/admin/images/folder/',{'action':'preview','trip':self.trip.pk,'images':self.photo()})
        with patch('observations.folder_import.create_backup',return_value=Path('backup.sqlite3')):
            response=self.client.post('/admin/images/folder/',{'action':'apply','token':response.context['token'],'selected':['0'],'species_0':str(self.species),'confirm':'yes'})
        self.assertEqual(response.status_code,302)
        existing.refresh_from_db()
        self.assertEqual(existing.status,'published')
        self.assertTrue(SpeciesArea.objects.filter(species=self.species,country=self.country,defining_sample=existing).exists())
    def test_ignores_edit_and_year_suffixes(self):
        from .folder_import import filename_species,filename_stem
        item=Species.objects.create(scientific_name='Phyllodesmium magnum')
        for suffix in [' 2023-Edit',' 2003','-Edit','-edit','-Edit 2023',' 2023-Edit-Edit']:
            filename='727-Phyllodesmium magnum'+suffix+'.jpeg'
            self.assertEqual(filename_stem(filename),'Phyllodesmium magnum')
            self.assertEqual(filename_species(filename),'Phyllodesmium magnum')
            self.assertEqual(match_species(filename,[item]),(item.pk,''))
        self.assertEqual(filename_species('C20-Thuridilla sp. 4 (2021)-Edit.jpg'),'Thuridilla sp. 4 (2021)')
        self.assertEqual(filename_species('713-Tenellia sp. 18 2023-Edit.jpg'),'Tenellia sp. 18')

    def test_matches_despite_cf_aff_and_juvenile_qualifiers(self):
        # cf./aff. mark a tentative ID and sit between genus and epithet; juv. marks a
        # juvenile specimen and usually trails the name (sometimes right before the
        # extension, where filename_stem's own extension-stripping used to eat the
        # trailing dot off "juv." before match_species ever saw it). None of the three
        # should stop the photo from matching its already-catalogued species.
        species=[self.species]  # 'Micromelo undatus'
        self.assertEqual(match_species('Micromelo cf. undatus (Author, 1900).jpg',species),(self.species.pk,''))
        self.assertEqual(match_species('Micromelo aff. undatus (Author, 1900).jpg',species),(self.species.pk,''))
        self.assertEqual(match_species('002-Micromelo undatus juv.jpg',species),(self.species.pk,''))
        self.assertEqual(match_species('Micromelo undatus (Author, 1900) juv.jpg',species),(self.species.pk,''))
        self.assertEqual(match_species('002-Micromelo undatus juv. (Author, 1900)-Edit.jpg',species),(self.species.pk,''))
        # A genuinely new (uncatalogued) species proposal still keeps "cf." -- this isn't
        # about matching an existing row, it's the tentative-ID name for a new one.
        from .folder_import import filename_species
        self.assertEqual(filename_species('Micromelo cf. novum (Author, 1900).jpg'),'Micromelo cf. novum')
