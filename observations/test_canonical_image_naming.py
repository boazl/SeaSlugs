import io
import tempfile
from pathlib import Path
from PIL import Image
from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from .models import Sample, Species, Country, Sea, Region, DiveTrip
from .media_transfer import validate_image_name, save_images


class CanonicalImageNameTests(TestCase):
    """Sample.canonical_image_name() builds the storage filename the whole project now
    agrees on: trip code + a kind-dependent identity (see the method's own docstring for
    the exact rule, which mirrors what the user asked for: species' genus+species for a
    SPECIES-kind sample, the gallery title for COLLECTION, species_other for everything
    else), slugified, with a numeric suffix only when that exact name is already taken."""
    def setUp(self):
        self.user = User.objects.create_superuser('admin', password='testing')
        self.country = Country.objects.create(name='Israel')
        self.sea = Sea.objects.create(name='Red Sea')
        self.trip = DiveTrip.objects.create(title='Eilat trip', year=2026, code='EI24',
            country=self.country, region=Region.objects.create(name='Eilat', country=self.country, sea=self.sea))

    def test_species_kind_uses_genus_and_species(self):
        species = Species.objects.create(scientific_name='Chromodoris quadricolor', genus='Chromodoris', species='quadricolor')
        sample = Sample(owner=self.user, trip=self.trip, kind=Sample.Kind.SPECIES, species=species)
        self.assertEqual(sample.canonical_image_name(), 'observations/ei24-chromodoris-quadricolor.jpg')

    def test_species_kind_without_genus_species_subfields_falls_back_to_scientific_name(self):
        species = Species.objects.create(scientific_name='Unsplit species name')
        sample = Sample(owner=self.user, trip=self.trip, kind=Sample.Kind.SPECIES, species=species)
        self.assertEqual(sample.canonical_image_name(), 'observations/ei24-unsplit-species-name.jpg')

    def test_collection_kind_uses_gallery_title(self):
        sample = Sample(owner=self.user, trip=self.trip, kind=Sample.Kind.COLLECTION, title='Night dive highlights')
        self.assertEqual(sample.canonical_image_name(), 'observations/ei24-night-dive-highlights.jpg')

    def test_collection_kind_keeps_hebrew_title_as_is(self):
        sample = Sample(owner=self.user, trip=self.trip, kind=Sample.Kind.COLLECTION, title='צלילת לילה')
        self.assertEqual(sample.canonical_image_name(), 'observations/ei24-צלילת-לילה.jpg')

    def test_genus_kind_uses_species_other(self):
        sample = Sample(owner=self.user, trip=self.trip, kind=Sample.Kind.GENUS, species_other='Chelidonura')
        self.assertEqual(sample.canonical_image_name(), 'observations/ei24-chelidonura.jpg')

    def test_family_and_order_kinds_use_species_other_too(self):
        for kind in (Sample.Kind.FAMILY, Sample.Kind.ORDER):
            sample = Sample(owner=self.user, trip=self.trip, kind=kind, species_other='Some taxon')
            self.assertEqual(sample.canonical_image_name(), 'observations/ei24-some-taxon.jpg')

    def test_colliding_name_gets_a_numeric_suffix(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            first = Sample(owner=self.user, trip=self.trip, kind=Sample.Kind.COLLECTION, title='Night dive',
                            video_url='https://youtu.be/11111111111')
            first.image.save('a.jpg', ContentFile(_jpeg_bytes('red')), save=False)
            # Production code always renames to the canonical name before saving (see
            # canonical_image_write in views.py / the upload actions in image_manager.py and
            # folder_import.py) -- do that explicitly here too, so first's stored name is
            # genuinely the one second's computation needs to collide with.
            first.image.name = first.canonical_image_name()
            first.save_reviewed()
            second = Sample(owner=self.user, trip=self.trip, kind=Sample.Kind.COLLECTION, title='Night dive',
                             video_url='https://youtu.be/22222222222')
            self.assertEqual(second.canonical_image_name(), 'observations/ei24-night-dive-2.jpg')

    def test_extra_used_names_also_avoids_a_collision_within_an_in_progress_batch(self):
        # Two brand-new (unsaved, pk=None) samples computed in the same batch can't see
        # each other via a database query -- image_manager.py's bulk upload passes the
        # names it has already claimed this batch via extra_used_names instead.
        sample = Sample(owner=self.user, trip=self.trip, kind=Sample.Kind.COLLECTION, title='Night dive')
        self.assertEqual(sample.canonical_image_name(extra_used_names={'ei24-night-dive'}), 'observations/ei24-night-dive-2.jpg')

    def test_editing_a_samples_own_existing_image_does_not_collide_with_itself(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            sample = Sample(owner=self.user, trip=self.trip, kind=Sample.Kind.COLLECTION, title='Night dive')
            sample.image.save('a.jpg', ContentFile(_jpeg_bytes('red')), save=False)
            sample.save_reviewed()
            # Recomputing the name for the SAME, already-saved sample must not bump into
            # its own current filename and get suffixed.
            self.assertEqual(sample.canonical_image_name(), 'observations/ei24-night-dive.jpg')


def _jpeg_bytes(color):
    output = io.BytesIO()
    Image.new('RGB', (40, 30), color).save(output, 'JPEG')
    return output.getvalue()


class ValidateImageNameTests(TestCase):
    def test_accepts_canonical_name(self):
        validate_image_name('observations/ei24-chromodoris-quadricolor.jpg')  # must not raise

    def test_accepts_canonical_name_with_hebrew(self):
        validate_image_name('observations/ei24-צלילת-לילה.jpg')  # must not raise

    def test_accepts_legacy_hash_name(self):
        validate_image_name('observations/transfer/' + 'a' * 64 + '.jpg')  # must not raise

    def test_rejects_path_traversal(self):
        with self.assertRaises(ValidationError):
            validate_image_name('observations/../secrets/x.jpg')

    def test_rejects_non_jpg_extension(self):
        with self.assertRaises(ValidationError):
            validate_image_name('observations/ei24-foo.png')

    def test_rejects_name_outside_observations_folder(self):
        with self.assertRaises(ValidationError):
            validate_image_name('site/intro.jpg')


class SaveImagesIdentityOverwriteTests(TestCase):
    """save_images() has two regimes: a legacy content-hash name is content-addressed (an
    existing file there must already have matching bytes -- a mismatch is corruption), while
    a canonical name is identity-addressed and may legitimately be overwritten with new
    bytes when an observation's photo is replaced (see Sample.canonical_image_name)."""
    def test_legacy_name_with_mismatched_existing_content_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            name = 'observations/transfer/' + 'b' * 64 + '.jpg'
            save_images({name: b'original bytes'})
            with self.assertRaises(ValidationError):
                save_images({name: b'different bytes'})

    def test_canonical_name_is_overwritten_with_new_content(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            from django.core.files.storage import default_storage
            name = 'observations/ei24-night-dive.jpg'
            save_images({name: b'first version'})
            save_images({name: b'second version'})  # must not raise
            with default_storage.open(name, 'rb') as f:
                self.assertEqual(f.read(), b'second version')


class SampleAdminRenameTests(TestCase):
    """SampleAdmin.save_model renames a freshly uploaded image to the canonical name before
    saving -- the one upload path (plain Django admin) that previously kept clean_image's
    own throwaway random-UUID name forever."""
    def setUp(self):
        self.user = User.objects.create_superuser('admin', password='testing')
        country = Country.objects.create(name='Israel'); sea = Sea.objects.create(name='Red Sea')
        self.trip = DiveTrip.objects.create(title='Eilat trip', year=2026, code='EI24',
            country=country, region=Region.objects.create(name='Eilat', country=country, sea=sea))
        self.species = Species.objects.create(scientific_name='Chromodoris quadricolor', genus='Chromodoris', species='quadricolor')

    def test_save_model_renames_a_freshly_uploaded_image(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            from .admin import SampleAdmin
            from django.core.files.uploadedfile import SimpleUploadedFile
            obj = Sample(owner=self.user, trip=self.trip, kind=Sample.Kind.SPECIES, species=self.species)
            obj.image = SimpleUploadedFile('whatever-random-name.jpg', _jpeg_bytes('green'), content_type='image/jpeg')

            class FakeForm:
                changed_data = ['image']
            SampleAdmin(Sample, None).save_model(request=None, obj=obj, form=FakeForm(), change=False)
            self.assertEqual(obj.image.name, 'observations/ei24-chromodoris-quadricolor.jpg')
