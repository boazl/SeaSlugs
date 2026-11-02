"""Fill DiveTrip.local_video_folder and Sample.local_video_file from the video folders on the Mac.

Default is a dry run (a report only); --apply backs up the database first and writes the matches.

    python manage.py match_local_videos                       # search ~ for "Video Output" folders, report
    python manage.py match_local_videos --apply
    python manage.py match_local_videos --trip V --folder "/Users/boazliebes/Romblon Island/Video Output" --apply

Without --folder, each trip that has YouTube videos gets the "Video Output" folder (found under --root) that
matches the most of its observations; a trip whose folder is already set keeps it. A file name that is already
filled is never changed unless --overwrite is given.
"""
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from observations.models import DiveTrip, Sample
from observations.local_videos import find_video_output_folders, match_trip, validate_local_video_folder, validate_local_video_file
from observations.table_transfer import create_backup


class Command(BaseCommand):
    help = 'Match the local (Mac) video files to the observations that have a YouTube video.'

    def add_arguments(self, parser):
        parser.add_argument('--root', default='~', help='Where to look for "Video Output" folders (default: home folder).')
        parser.add_argument('--trip', help='Only this trip code.')
        parser.add_argument('--folder', help='The trip\'s folder (with --trip).')
        parser.add_argument('--set', action='append', default=[], metavar='ID=FILE',
            help='With --trip/--folder: give observation #ID this file name by hand (repeatable), e.g. --set 105="Romblon 2026 SlideShow.mov".')
        parser.add_argument('--overwrite', action='store_true', help='Replace file names / folders that are already set.')
        parser.add_argument('--apply', action='store_true', help='Write the matches (after a backup).')

    def handle(self, *args, **opts):
        if opts['folder'] and not opts['trip']: raise CommandError('--folder needs --trip.')
        if opts['set'] and not opts['folder']: raise CommandError('--set needs --trip and --folder.')
        videos = Sample.objects.filter(deleted_at__isnull=True, trip__isnull=False).exclude(video_url='').select_related('trip', 'species')
        if opts['trip']: videos = videos.filter(trip__code=opts['trip'])
        by_trip = {}
        for sample in videos.order_by('trip__code', 'pk'): by_trip.setdefault(sample.trip, []).append(sample)
        if not by_trip: raise CommandError('No observations with a YouTube video were found.')
        folders = None
        plan = []   # (trip, folder, matches, unmatched, ambiguous, unused)
        for trip, samples in by_trip.items():
            if opts['folder']:
                validate_local_video_folder(opts['folder']); folder = Path(opts['folder']).expanduser()
            elif trip.local_video_folder and not opts['overwrite']:
                folder = Path(trip.local_video_folder).expanduser()
            else:
                if folders is None: folders = find_video_output_folders(opts['root'])
                scored = sorted(((len(match_trip(samples, f)[0]), str(f)) for f in folders), reverse=True)
                folder = Path(scored[0][1]) if scored and scored[0][0] else None
            if folder is None:
                plan.append((trip, None, [], samples, [], [])); continue
            matches, unmatched, ambiguous, unused = match_trip(samples, folder)
            for item in opts['set']:
                pk, sep, name = item.partition('=')
                sample = next((x for x in samples if str(x.pk) == pk.strip()), None)
                if not sep or sample is None: raise CommandError(f'--set {item}: no observation #{pk} with a video in trip {trip.code}.')
                validate_local_video_file(name)
                if not (folder / name).is_file(): raise CommandError(f'--set {item}: the file is not in {folder}.')
                matches = [m for m in matches if m[0] is not sample] + [(sample, name)]
                unmatched = [x for x in unmatched if x is not sample]
                ambiguous = [a for a in ambiguous if a[0] is not sample]
                unused = [n for n in unused if n != name]
            plan.append((trip, folder, matches, unmatched, ambiguous, unused))

        writes = 0
        for trip, folder, matches, unmatched, ambiguous, unused in plan:
            total = len(matches) + len(unmatched) + len(ambiguous)
            self.stdout.write(self.style.MIGRATE_HEADING(f'\n[{trip.code}] {trip.title} — {total} videos'))
            if folder is None:
                self.stdout.write(self.style.WARNING('  No folder found. Use --trip %s --folder "<path>".' % trip.code)); continue
            self.stdout.write(f'  Folder: {folder}' + ('' if str(folder) == trip.local_video_folder else '   (will be set)'))
            self.stdout.write(self.style.SUCCESS(f'  Matched: {len(matches)}'))
            for sample, name in matches:
                note = '' if sample.local_video_file in ('', name) else f'   (now: {sample.local_video_file}' + (', kept)' if not opts['overwrite'] else ', replaced)')
                self.stdout.write(f'    #{sample.pk} {sample.taxon_name or sample.title} -> {name}{note}')
            for sample, names in ambiguous:
                self.stdout.write(self.style.WARNING(f'  Several files for #{sample.pk} {sample.taxon_name or sample.title}: {", ".join(names)}'))
            for sample in unmatched:
                self.stdout.write(self.style.ERROR(f'  No file for #{sample.pk} {sample.taxon_name or sample.title}'))
            if unused: self.stdout.write(f'  Files not used by any observation of this trip ({len(unused)}): ' + ', '.join(unused))

        if not opts['apply']:
            self.stdout.write('\nDry run — nothing was written. Run again with --apply to save.'); return
        backup = create_backup()
        self.stdout.write(f'\nBackup: {backup}')
        with transaction.atomic():
            for trip, folder, matches, *_ in plan:
                if folder is None: continue
                if str(folder) != trip.local_video_folder:
                    DiveTrip.objects.filter(pk=trip.pk).update(local_video_folder=str(folder)); writes += 1
                for sample, name in matches:
                    if sample.local_video_file == name or (sample.local_video_file and not opts['overwrite']): continue
                    # update(): only this one column -- no save() side effects (publication, defining samples...)
                    Sample.objects.filter(pk=sample.pk).update(local_video_file=name); writes += 1
        self.stdout.write(self.style.SUCCESS(f'Saved {writes} changes.'))
