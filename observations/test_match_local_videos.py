"""Offline videos, phase 2: matching the Mac's exported video files to observations (local_videos.match_trip and
the match_local_videos command)."""
import io
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from .local_videos import normalize_video_name, candidate_names, match_trip, find_video_output_folders
from .models import Country, Sea, Region, DiveTrip, Species, Sample, IdentificationQualifier


class MatchLocalVideosTests(TestCase):
    """A file is named after the species without the author ("Chromodoris kalawakan.mov"), with cf./sp. N/variant as
    written ("Aegires sp. 7.mov"); a summary video is named like the collection's title. Case, dots, dashes and
    repeated spaces don't matter. The trip folder is the "Video Output" folder that matches most of its videos.
    The command is a dry run unless --apply; it backs up first, sets only the two fields (with update(), no save()
    side effects) and never replaces a file name already set unless --overwrite. Between two exports of the same
    name, the .mov is the default."""
    def setUp(self):
        self.owner = get_user_model().objects.create_superuser('admin', password='testing')
        country = Country.objects.create(name='Philippines'); sea = Sea.objects.create(name='Indo Pacific')
        region = Region.objects.create(name='Romblon', country=country, sea=sea)
        self.trip = DiveTrip.objects.create(code='V', title='Romblon 2026', year=2026, country=country, region=region)
        IdentificationQualifier.objects.get_or_create(code='cf.', defaults={'name': 'cf.'})
        def sample(name, video, **kw):
            genus, epithet = name.split(' ', 1)
            sp = Species.objects.create(scientific_name=name, genus=genus, species=epithet)
            s = Sample(owner=self.owner, trip=self.trip, kind=Sample.Kind.SPECIES, species=sp, status=Sample.Status.PUBLISHED,
                       video_url=f'https://youtu.be/{video}', **kw)
            s.save(); return s
        self.kala = sample('Chromodoris kalawakan', '11111111111')
        self.aegires = sample('Aegires sp. 7', '22222222222', title='Aegires sp  7')
        self.strigata = sample('Chromodoris strigata', '33333333333', identification_qualifier='cf.')
        self.missing = sample('Elysia pusilla', '44444444444')
        self.root = tempfile.TemporaryDirectory(); self.addCleanup(self.root.cleanup)
        self.folder = Path(self.root.name) / 'Romblon Island' / 'Video Output'; self.folder.mkdir(parents=True)
        for name in ('Chromodoris kalawakan.mov', 'Aegires sp. 7.mov', 'Chromodoris cf. strigata.mp4', 'Extra.mov', 'notes.txt'):
            (self.folder / name).write_bytes(b'x')
        other = Path(self.root.name) / 'Anilao 2023' / 'VideoOutput'; other.mkdir(parents=True)
        (other / 'Chromodoris kalawakan.mov').write_bytes(b'x')

    def test_normalize_and_candidates(self):
        self.assertEqual(normalize_video_name('Aegires sp. 7.MOV'), normalize_video_name('Aegires sp  7'))
        self.assertIn('chromodoris cf strigata', candidate_names(self.strigata))

    def test_match_trip(self):
        samples = [self.kala, self.aegires, self.strigata, self.missing]
        matches, unmatched, ambiguous, unused = match_trip(samples, self.folder)
        self.assertEqual({s.pk: n for s, n in matches}, {self.kala.pk: 'Chromodoris kalawakan.mov', self.aegires.pk: 'Aegires sp. 7.mov',
                                                          self.strigata.pk: 'Chromodoris cf. strigata.mp4'})
        self.assertEqual(unmatched, [self.missing]); self.assertEqual(ambiguous, []); self.assertEqual(unused, ['Extra.mov'])

    def test_place_word_suffix(self):
        """'Chromodoris quadricolor RedSea.mov' matches, 'Nembrotha sp 5' is never taken for 'Nembrotha sp.'."""
        (self.folder / 'Elysia pusilla RedSea.mov').write_bytes(b'x')
        nemb = Sample(owner=self.owner, trip=self.trip, kind=Sample.Kind.SPECIES, status=Sample.Status.PUBLISHED, video_url='https://youtu.be/55555555555',
                      species=Species.objects.create(scientific_name='Nembrotha sp.', genus='Nembrotha', species='sp.'))
        nemb.save(); (self.folder / 'Nembrotha sp. 5.mov').write_bytes(b'x')
        matches, unmatched, _, _ = match_trip([self.missing, nemb], self.folder)
        self.assertEqual([(s.pk, n) for s, n in matches], [(self.missing.pk, 'Elysia pusilla RedSea.mov')])
        self.assertEqual(unmatched, [nemb])

    def test_mov_is_the_default_between_duplicates(self):
        (self.folder / 'Chromodoris kalawakan.m4v').write_bytes(b'x')
        matches, _, ambiguous, _ = match_trip([self.kala], self.folder)
        self.assertEqual(matches[0][1], 'Chromodoris kalawakan.mov'); self.assertEqual(ambiguous, [])
        (self.folder / 'Elysia pusilla.mp4').write_bytes(b'x'); (self.folder / 'Elysia pusilla.m4v').write_bytes(b'x')
        self.assertEqual(len(match_trip([self.missing], self.folder)[2]), 1)   # no .mov: still for the owner to choose

    def test_set_by_hand(self):
        with patch('observations.management.commands.match_local_videos.create_backup', return_value=Path('b.sqlite3')):
            call_command('match_local_videos', trip='V', folder=str(self.folder), set=[f'{self.missing.pk}=Extra.mov'], apply=True, stdout=io.StringIO())
        self.missing.refresh_from_db(); self.assertEqual(self.missing.local_video_file, 'Extra.mov')

    def test_find_folders(self):
        self.assertEqual({p.parent.name for p in find_video_output_folders(self.root.name)}, {'Romblon Island', 'Anilao 2023'})

    def test_command_dry_run_then_apply(self):
        out = io.StringIO()
        call_command('match_local_videos', root=self.root.name, stdout=out)
        self.kala.refresh_from_db(); self.trip.refresh_from_db()
        self.assertEqual(self.kala.local_video_file, ''); self.assertIn('Dry run', out.getvalue())
        Sample.objects.filter(pk=self.aegires.pk).update(local_video_file='Kept.mov')
        with patch('observations.management.commands.match_local_videos.create_backup', return_value=Path('b.sqlite3')) as backup:
            call_command('match_local_videos', root=self.root.name, apply=True, stdout=io.StringIO())
        backup.assert_called_once()
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.local_video_folder, str(self.folder))   # the folder with the most matches
        values = dict(Sample.objects.values_list('pk', 'local_video_file'))
        self.assertEqual(values[self.kala.pk], 'Chromodoris kalawakan.mov')
        self.assertEqual(values[self.strigata.pk], 'Chromodoris cf. strigata.mp4')
        self.assertEqual(values[self.aegires.pk], 'Kept.mov')           # not overwritten
        self.assertEqual(values[self.missing.pk], '')
