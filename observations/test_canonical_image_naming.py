import hashlib
import io
import tempfile
from pathlib import Path
from unittest.mock import patch
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
    SPECIES-kind sample, the gallery title for COLLECTION, the order / family / genus field for everything
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

    def test_genus_kind_uses_the_genus_field(self):
        sample = Sample(owner=self.user, trip=self.trip, kind=Sample.Kind.GENUS, genus='Chelidonura')
        self.assertEqual(sample.canonical_image_name(), 'observations/ei24-chelidonura.jpg')

    def test_family_and_order_kinds_use_their_own_field(self):
        for kind, field in ((Sample.Kind.FAMILY, 'family'), (Sample.Kind.ORDER, 'order')):
            sample = Sample(owner=self.user, trip=self.trip, kind=kind, **{field: 'Some taxon'})
            self.assertEqual(sample.canonical_image_name(), 'observations/ei24-some-taxon.jpg')
        # ...and a field that does not belong to the kind is ignored.
        sample = Sample(owner=self.user, trip=self.trip, kind=Sample.Kind.FAMILY, family='Fam', genus='Gen', order='Ord')
        self.assertEqual(sample.canonical_image_name(), 'observations/ei24-fam.jpg')

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


class RenameImagesToCanonicalCommandTests(TestCase):
    """The one-off migration command (rename_images_to_canonical) is dry-run by default and
    only touches disk + the database when given --apply; it must also leave an
    already-canonical sample untouched and report (without crashing on) a sample whose file
    is missing from disk. create_backup() is patched out in every test here -- same reasoning
    as every other command test in this codebase (see test_assign_genus_defining_samples.py,
    test_taxonomy.py): it does real sqlite file I/O via a second raw connection, which is both
    irrelevant to what's under test and deadlocks against TestCase's own open transaction."""
    def setUp(self):
        patcher = patch('observations.management.commands.rename_images_to_canonical.create_backup',
                         return_value=Path('backup-stub.sqlite3'))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.user = User.objects.create_superuser('admin', password='testing')
        self.country = Country.objects.create(name='Israel')
        self.sea = Sea.objects.create(name='Red Sea')
        self.trip = DiveTrip.objects.create(title='Eilat trip', year=2026, code='EI24',
            country=self.country, region=Region.objects.create(name='Eilat', country=self.country, sea=self.sea))
        self.species = Species.objects.create(scientific_name='Chromodoris quadricolor', genus='Chromodoris', species='quadricolor')

    def _sample_with_legacy_name(self):
        sample = Sample(owner=self.user, trip=self.trip, kind=Sample.Kind.SPECIES, species=self.species)
        sample.image.save('some-random-upload-name.jpg', ContentFile(_jpeg_bytes('blue')), save=False)
        sample.save_reviewed()
        return sample

    def test_dry_run_reports_without_changing_anything(self):
        from django.core.management import call_command
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            sample = self._sample_with_legacy_name()
            old_name = sample.image.name
            out = io.StringIO()
            call_command('rename_images_to_canonical', stdout=out)
            sample.refresh_from_db()
            self.assertEqual(sample.image.name, old_name)  # untouched
            self.assertTrue((Path(folder) / old_name).is_file())  # file not moved
            self.assertFalse((Path(folder) / 'observations/ei24-chromodoris-quadricolor.jpg').exists())
            self.assertIn('1 to rename', out.getvalue())
            self.assertIn('Dry run only', out.getvalue())

    def test_apply_renames_file_and_updates_database(self):
        from django.core.management import call_command
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            sample = self._sample_with_legacy_name()
            old_name = sample.image.name
            out = io.StringIO()
            call_command('rename_images_to_canonical', '--apply', stdout=out)
            sample.refresh_from_db()
            self.assertEqual(sample.image.name, 'observations/ei24-chromodoris-quadricolor.jpg')
            self.assertFalse((Path(folder) / old_name).exists())  # old file gone
            self.assertTrue((Path(folder) / sample.image.name).is_file())  # new file in place
            self.assertIn('1 to rename', out.getvalue())

    def test_rerunning_after_apply_is_a_no_op(self):
        from django.core.management import call_command
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            self._sample_with_legacy_name()
            call_command('rename_images_to_canonical', '--apply', stdout=io.StringIO())
            out = io.StringIO()
            call_command('rename_images_to_canonical', '--apply', stdout=out)
            self.assertIn('0 to rename, 0 recovered by content hash, 1 already canonical', out.getvalue())

    def test_missing_file_on_disk_is_reported_and_left_untouched(self):
        from django.core.management import call_command
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            sample = self._sample_with_legacy_name()
            old_name = sample.image.name
            (Path(folder) / old_name).unlink()  # simulate a file that vanished from disk
            out = io.StringIO()
            call_command('rename_images_to_canonical', '--apply', stdout=out)
            sample.refresh_from_db()
            self.assertEqual(sample.image.name, old_name)  # left untouched, not renamed
            self.assertIn('missing on disk', out.getvalue())


class RenameImagesToCanonicalSharedImageTests(TestCase):
    """Two Sample rows can legitimately point at the exact same stored image file -- most
    often a species sample and that genus's own "defining sample" (see
    assign_genus_defining_samples), which deliberately reuses one of its member species'
    photo instead of its own upload. Each still gets its own distinct canonical name, so the
    shared file must be copied to every sample that needs it before it is ever removed --
    not moved away by whichever sample happens to be processed first (a real bug an earlier
    version of this command had, caught against this project's own database: 19 genus-kind
    defining samples were left pointing at a file a sibling species sample's rename had
    already moved out from under them)."""
    def setUp(self):
        patcher = patch('observations.management.commands.rename_images_to_canonical.create_backup',
                         return_value=Path('backup-stub.sqlite3'))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.user = User.objects.create_superuser('admin', password='testing')
        self.country = Country.objects.create(name='Israel')
        self.sea = Sea.objects.create(name='Red Sea')
        self.trip = DiveTrip.objects.create(title='Eilat trip', year=2026, code='EI24',
            country=self.country, region=Region.objects.create(name='Eilat', country=self.country, sea=self.sea))
        self.species = Species.objects.create(scientific_name='Chromodoris quadricolor', genus='Chromodoris', species='quadricolor')

    def _two_samples_sharing_one_image(self, folder):
        # Sample.clean()'s duplicate-image check deliberately only fires when a sample's own
        # image is actually changing (see the comment above it): it accepts that legacy rows
        # already sharing one photo predate the check. A genus-kind "defining sample" row is
        # exactly that -- Sample.save()'s own docstring notes it is saved with a plain
        # .save(), never through save_reviewed() / full_clean() -- so this mirrors that real
        # construction rather than going through validation that a real defining sample
        # never does either.
        from django.core.files.storage import default_storage
        shared_name = 'observations/transfer/' + hashlib.sha256(b'shared-photo').hexdigest() + '.jpg'
        default_storage.save(shared_name, ContentFile(b'shared-photo'))
        species_sample = Sample(owner=self.user, trip=self.trip, kind=Sample.Kind.SPECIES, species=self.species)
        species_sample.image.name = shared_name
        species_sample.save_reviewed()
        genus_sample = Sample(owner=self.user, trip=self.trip, kind=Sample.Kind.GENUS, genus='Chromodoris',
                               video_url='https://youtu.be/00000000001')
        genus_sample.image.name = shared_name
        genus_sample.save()
        return species_sample, genus_sample, shared_name

    def test_both_samples_get_their_own_independent_canonical_copy(self):
        from django.core.management import call_command
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            species_sample, genus_sample, shared_name = self._two_samples_sharing_one_image(folder)
            out = io.StringIO()
            call_command('rename_images_to_canonical', '--apply', stdout=out)
            species_sample.refresh_from_db(); genus_sample.refresh_from_db()
            self.assertEqual(species_sample.image.name, 'observations/ei24-chromodoris-quadricolor.jpg')
            self.assertEqual(genus_sample.image.name, 'observations/ei24-chromodoris.jpg')
            # each sample's own file physically exists, with the shared content
            self.assertEqual((Path(folder) / species_sample.image.name).read_bytes(), b'shared-photo')
            self.assertEqual((Path(folder) / genus_sample.image.name).read_bytes(), b'shared-photo')
            # the old shared source is gone -- nothing points at it by that name any more
            self.assertFalse((Path(folder) / shared_name).exists())
            self.assertIn('2 to rename', out.getvalue())

    def test_dry_run_on_shared_image_does_not_touch_disk(self):
        from django.core.management import call_command
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            species_sample, genus_sample, shared_name = self._two_samples_sharing_one_image(folder)
            call_command('rename_images_to_canonical', stdout=io.StringIO())
            self.assertTrue((Path(folder) / shared_name).is_file())  # shared source untouched
            species_sample.refresh_from_db(); genus_sample.refresh_from_db()
            self.assertEqual(species_sample.image.name, shared_name)
            self.assertEqual(genus_sample.image.name, shared_name)


class RenameImagesToCanonicalHashRecoveryTests(TestCase):
    """Repairs the exact damage the move-based bug above already did to a live database: a
    sample whose recorded image path is a legacy content-hash name that no longer exists on
    disk (because an earlier, buggy run already moved that file away under a sibling sample),
    recovered by finding today's copy of that same content elsewhere in the media folder."""
    def setUp(self):
        patcher = patch('observations.management.commands.rename_images_to_canonical.create_backup',
                         return_value=Path('backup-stub.sqlite3'))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.user = User.objects.create_superuser('admin', password='testing')
        self.country = Country.objects.create(name='Israel')
        self.sea = Sea.objects.create(name='Red Sea')
        self.trip = DiveTrip.objects.create(title='Eilat trip', year=2026, code='EI24',
            country=self.country, region=Region.objects.create(name='Eilat', country=self.country, sea=self.sea))

    def test_sample_with_a_vanished_legacy_name_is_recovered_by_content_hash(self):
        from django.core.management import call_command
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            # The species sample already ran through a (correct) earlier rename -- its file
            # sits at its own canonical name, content known.
            species = Species.objects.create(scientific_name='Chromodoris quadricolor', genus='Chromodoris', species='quadricolor')
            species_sample = Sample(owner=self.user, trip=self.trip, kind=Sample.Kind.SPECIES, species=species)
            species_sample.image.save('observations/ei24-chromodoris-quadricolor.jpg', ContentFile(b'shared-photo'), save=False)
            species_sample.save_reviewed()

            # The genus sample is exactly the damage the old bug left behind: its database
            # value is still the legacy hash name, and that file no longer exists anywhere
            # except (now, under a different name) as the species sample's own copy above.
            genus_sample = Sample(owner=self.user, trip=self.trip, kind=Sample.Kind.GENUS, genus='Chromodoris',
                                   video_url='https://youtu.be/00000000002')
            vanished_name = 'observations/transfer/' + hashlib.sha256(b'shared-photo').hexdigest() + '.jpg'
            genus_sample.image.name = vanished_name
            genus_sample.save()  # a plain save(), matching how a real defining sample is created (no full_clean)
            self.assertFalse((Path(folder) / vanished_name).exists())  # confirms the damage

            out = io.StringIO()
            call_command('rename_images_to_canonical', '--apply', stdout=out)

            genus_sample.refresh_from_db()
            self.assertEqual(genus_sample.image.name, 'observations/ei24-chromodoris.jpg')
            self.assertEqual((Path(folder) / genus_sample.image.name).read_bytes(), b'shared-photo')
            # the species sample's own file is untouched -- it's still legitimately needed there
            species_sample.refresh_from_db()
            self.assertTrue((Path(folder) / species_sample.image.name).is_file())
            self.assertIn('1 recovered by content hash', out.getvalue())
            self.assertNotIn('missing on disk', out.getvalue())

    def test_a_truly_absent_file_with_no_match_anywhere_is_still_reported_missing(self):
        from django.core.management import call_command
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            species = Species.objects.create(scientific_name='Chromodoris quadricolor', genus='Chromodoris', species='quadricolor')
            sample = Sample(owner=self.user, trip=self.trip, kind=Sample.Kind.SPECIES, species=species)
            vanished_name = 'observations/transfer/' + hashlib.sha256(b'never-existed').hexdigest() + '.jpg'
            sample.image.name = vanished_name
            sample.save_reviewed()

            out = io.StringIO()
            call_command('rename_images_to_canonical', '--apply', stdout=out)
            sample.refresh_from_db()
            self.assertEqual(sample.image.name, vanished_name)  # left untouched
            self.assertIn('missing on disk', out.getvalue())
