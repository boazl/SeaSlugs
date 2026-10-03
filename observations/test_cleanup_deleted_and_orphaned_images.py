import hashlib
import io
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.test import TestCase, override_settings

from .models import Country, DiveTrip, Region, Sample, Sea, Species


class CleanupDeletedAndOrphanedImagesTests(TestCase):
    """cleanup_deleted_and_orphaned_images is the follow-up to rename_images_to_canonical for
    the two things that command deliberately never touches: files no sample (active or
    deleted) references at all, and a soft-deleted sample's own still-un-renamed image file
    (left alone so the admin's "restore" action still has a photo to bring back)."""
    def setUp(self):
        patcher = patch('observations.management.commands.cleanup_deleted_and_orphaned_images.create_backup',
                         return_value=Path('backup-stub.sqlite3'))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.user = User.objects.create_superuser('admin', password='testing')
        self.country = Country.objects.create(name='Israel')
        self.sea = Sea.objects.create(name='Red Sea')
        self.trip = DiveTrip.objects.create(title='Eilat trip', year=2026, code='EI24',
            country=self.country, region=Region.objects.create(name='Eilat', country=self.country, sea=self.sea))
        self.species = Species.objects.create(scientific_name='Chromodoris quadricolor', genus='Chromodoris', species='quadricolor')

    def _deleted_sample(self, content=b'deleted-photo', video_url='https://youtu.be/11111111111'):
        sample = Sample(owner=self.user, trip=self.trip, kind=Sample.Kind.SPECIES, species=self.species, video_url=video_url)
        legacy_name = 'observations/transfer/' + hashlib.sha256(content).hexdigest() + '.jpg'
        default_storage.save(legacy_name, ContentFile(content))
        sample.image.name = legacy_name
        sample.save_reviewed()
        sample.soft_delete(self.user)
        return sample, legacy_name

    def test_dry_run_changes_nothing(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            sample, legacy_name = self._deleted_sample()
            default_storage.save('observations/truly-orphaned.jpg', ContentFile(b'nobody-points-at-me'))
            out = io.StringIO()
            call_command('cleanup_deleted_and_orphaned_images', stdout=out)
            sample.refresh_from_db()
            self.assertEqual(sample.image.name, legacy_name)
            self.assertTrue((Path(folder) / legacy_name).is_file())
            self.assertTrue((Path(folder) / 'observations/truly-orphaned.jpg').is_file())
            self.assertIn('1 to delete', out.getvalue())
            self.assertIn('1 to rename', out.getvalue())
            self.assertIn('Dry run only', out.getvalue())

    def test_apply_deletes_orphan_and_renames_deleted_sample_image(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            sample, legacy_name = self._deleted_sample()
            default_storage.save('observations/truly-orphaned.jpg', ContentFile(b'nobody-points-at-me'))
            out = io.StringIO()
            call_command('cleanup_deleted_and_orphaned_images', '--apply', stdout=out)

            self.assertFalse((Path(folder) / 'observations/truly-orphaned.jpg').exists())  # orphan gone

            sample.refresh_from_db()
            self.assertEqual(sample.image.name, 'observations/ei24-chromodoris-quadricolor-deleted-sample.jpg')
            self.assertFalse((Path(folder) / legacy_name).exists())  # old name gone
            self.assertEqual((Path(folder) / sample.image.name).read_bytes(), b'deleted-photo')
            self.assertIn('1 deleted', out.getvalue())
            self.assertIn('1 to rename', out.getvalue())

    def test_rerunning_after_apply_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            self._deleted_sample()
            call_command('cleanup_deleted_and_orphaned_images', '--apply', stdout=io.StringIO())
            out = io.StringIO()
            call_command('cleanup_deleted_and_orphaned_images', '--apply', stdout=out)
            self.assertIn('0 to rename, 0 recovered by content hash, 1 already done', out.getvalue())
            self.assertIn('0 deleted', out.getvalue())

    def test_an_existing_file_already_at_the_target_name_is_overwritten(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            sample, legacy_name = self._deleted_sample()
            stale_path = Path(folder) / 'observations/ei24-chromodoris-quadricolor-deleted-sample.jpg'
            stale_path.parent.mkdir(parents=True, exist_ok=True)
            stale_path.write_bytes(b'stale leftover content')

            call_command('cleanup_deleted_and_orphaned_images', '--apply', stdout=io.StringIO())

            sample.refresh_from_db()
            self.assertEqual(sample.image.name, 'observations/ei24-chromodoris-quadricolor-deleted-sample.jpg')
            self.assertEqual(stale_path.read_bytes(), b'deleted-photo')  # overwritten, not left stale

    def test_active_samples_image_is_never_touched_or_treated_as_orphaned(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            active = Sample(owner=self.user, trip=self.trip, kind=Sample.Kind.SPECIES, species=self.species)
            default_storage.save('observations/ei24-chromodoris-quadricolor.jpg', ContentFile(b'active-photo'))
            active.image.name = 'observations/ei24-chromodoris-quadricolor.jpg'
            active.save_reviewed()
            out = io.StringIO()
            call_command('cleanup_deleted_and_orphaned_images', '--apply', stdout=out)
            active.refresh_from_db()
            self.assertEqual(active.image.name, 'observations/ei24-chromodoris-quadricolor.jpg')
            self.assertTrue((Path(folder) / active.image.name).is_file())
            self.assertIn('0 deleted', out.getvalue())

    def test_two_deleted_samples_sharing_one_file_each_get_their_own_copy(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            shared_name = 'observations/transfer/' + hashlib.sha256(b'shared-deleted-photo').hexdigest() + '.jpg'
            default_storage.save(shared_name, ContentFile(b'shared-deleted-photo'))
            first = Sample(owner=self.user, trip=self.trip, kind=Sample.Kind.SPECIES, species=self.species,
                            video_url='https://youtu.be/22222222222')
            first.image.name = shared_name
            first.save_reviewed()
            first.soft_delete(self.user)

            species2 = Species.objects.create(scientific_name='Goniobranchus fidelis', genus='Goniobranchus', species='fidelis')
            second = Sample(owner=self.user, trip=self.trip, kind=Sample.Kind.SPECIES, species=species2,
                             video_url='https://youtu.be/33333333333')
            second.image.name = shared_name
            second.save()  # a plain save(), matching how a legacy shared-image row would have been created
            second.soft_delete(self.user)

            out = io.StringIO()
            call_command('cleanup_deleted_and_orphaned_images', '--apply', stdout=out)

            first.refresh_from_db(); second.refresh_from_db()
            self.assertEqual(first.image.name, 'observations/ei24-chromodoris-quadricolor-deleted-sample.jpg')
            self.assertEqual(second.image.name, 'observations/ei24-goniobranchus-fidelis-deleted-sample.jpg')
            self.assertEqual((Path(folder) / first.image.name).read_bytes(), b'shared-deleted-photo')
            self.assertEqual((Path(folder) / second.image.name).read_bytes(), b'shared-deleted-photo')
            self.assertFalse((Path(folder) / shared_name).exists())
            self.assertIn('2 to rename', out.getvalue())

    def test_recovers_a_deleted_samples_image_stolen_by_an_active_siblings_rename(self):
        # Mirrors the real bug this project's own database hit: an earlier, move-based version
        # of rename_images_to_canonical stole a shared file out from under a DELETED sample
        # (which that command never even looks at) when an ACTIVE sibling sample sharing the
        # same photo was renamed first.
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            active = Sample(owner=self.user, trip=self.trip, kind=Sample.Kind.SPECIES, species=self.species)
            active.image.save('observations/ei24-chromodoris-quadricolor.jpg', ContentFile(b'stolen-photo'), save=False)
            active.save_reviewed()

            species2 = Species.objects.create(scientific_name='Goniobranchus fidelis', genus='Goniobranchus', species='fidelis')
            deleted = Sample(owner=self.user, trip=self.trip, kind=Sample.Kind.SPECIES, species=species2,
                              video_url='https://youtu.be/44444444444')
            vanished_name = 'observations/transfer/' + hashlib.sha256(b'stolen-photo').hexdigest() + '.jpg'
            deleted.image.name = vanished_name
            deleted.save()
            deleted.soft_delete(self.user)
            self.assertFalse((Path(folder) / vanished_name).exists())  # confirms the damage

            out = io.StringIO()
            call_command('cleanup_deleted_and_orphaned_images', '--apply', stdout=out)

            deleted.refresh_from_db()
            self.assertEqual(deleted.image.name, 'observations/ei24-goniobranchus-fidelis-deleted-sample.jpg')
            self.assertEqual((Path(folder) / deleted.image.name).read_bytes(), b'stolen-photo')
            active.refresh_from_db()
            self.assertTrue((Path(folder) / active.image.name).is_file())  # untouched, still needed
            self.assertIn('1 recovered by content hash', out.getvalue())
            self.assertNotIn('missing on disk', out.getvalue())

    def test_a_deleted_samples_truly_absent_file_is_reported_missing(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            sample = Sample(owner=self.user, trip=self.trip, kind=Sample.Kind.SPECIES, species=self.species)
            vanished_name = 'observations/transfer/' + hashlib.sha256(b'never-existed').hexdigest() + '.jpg'
            sample.image.name = vanished_name
            sample.save()
            sample.soft_delete(self.user)

            out = io.StringIO()
            call_command('cleanup_deleted_and_orphaned_images', '--apply', stdout=out)
            sample.refresh_from_db()
            self.assertEqual(sample.image.name, vanished_name)  # left untouched
            self.assertIn('missing on disk', out.getvalue())
