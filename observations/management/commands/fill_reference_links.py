"""Fill Species.reference_link: a page to glance at what each species looks like.

Rule: an iNaturalist taxon page when iNaturalist has a photo of that exact species; otherwise
the species' WoRMS page; species without a full binomial name get nothing (see
observations/reference_links.py). Existing links are never overwritten.

Two resumable steps, so a long run can be stopped and continued:
  --fetch   query WoRMS (batches of 50) and iNaturalist (one request per species, ~1/s) and
            append every answer to a JSON-lines cache file (default: ~/reference_links_cache.jsonl)
  --apply   write links from the cache into the LOCAL database (then move them to the live site
            with the species table export/import)
Without either flag it only reports what the cache would change.
"""
import json
import time
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from observations.models import Species
from observations import reference_links as rl


def load_cache(path):
    cache = {'worms': {}, 'inat': {}}
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.strip():
                item = json.loads(line)
                cache[item['src']][item['key']] = item['id']
    return cache


def append(path, src, key, found):
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps({'src': src, 'key': key, 'id': found}, ensure_ascii=False) + '\n')


def species_names():
    """[(Species, [names])] for every species that has a full name."""
    out = []
    # .only(): fetching never needs reference_link, so it also runs on a database that has
    # not been migrated yet (apply does need the migration).
    for sp in Species.objects.only('genus', 'species', 'accepted_genus', 'accepted_species').order_by('pk'):
        names = rl.candidate_names(sp)
        if names:
            out.append((sp, names))
    return out


def resolve(cache, names):
    worms = next((cache['worms'][n] for n in names if cache['worms'].get(n)), None)
    inat = cache['inat'].get('|'.join(names))
    return rl.best_link(worms, inat)


class Command(BaseCommand):
    help = 'Fill the species reference link (iNaturalist photo page, else WoRMS) from the web.'

    def add_arguments(self, parser):
        parser.add_argument('--cache', default=str(Path.home() / 'reference_links_cache.jsonl'))
        parser.add_argument('--fetch', action='store_true')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--limit', type=int, default=0, help='fetch at most N iNaturalist lookups (for trials)')
        parser.add_argument('--sleep', type=float, default=1.0, help='seconds between iNaturalist requests')

    def handle(self, *args, **options):
        path = Path(options['cache'])
        cache = load_cache(path)
        items = species_names()
        self.stdout.write(f'{len(items)} species have a full name.')
        if options['fetch']:
            self.fetch(path, cache, items, options['limit'], options['sleep'])
            cache = load_cache(path)
        self.report(cache, items)
        if options['apply']:
            if settings.PRODUCTION:
                raise CommandError('Apply on the local database; the live site gets the links through table transfer.')
            self.apply(cache, items)

    def fetch(self, path, cache, items, limit, pause):
        every = sorted({n for _, names in items for n in names})
        todo = [n for n in every if n not in cache['worms']]
        self.stdout.write(f'WoRMS: {len(todo)} names to look up.')
        for start in range(0, len(todo), rl.WORMS_BATCH):
            batch = todo[start:start + rl.WORMS_BATCH]
            for name, found in rl.fetch_worms(batch).items():
                append(path, 'worms', name, found)
            self.stdout.write(f'  WoRMS {min(start + rl.WORMS_BATCH, len(todo))}/{len(todo)}')
        done = 0
        pending = [names for _, names in items if '|'.join(names) not in cache['inat']]
        self.stdout.write(f'iNaturalist: {len(pending)} species to look up.')
        for names in pending:
            if limit and done >= limit:
                break
            append(path, 'inat', '|'.join(names), rl.fetch_inat(names))
            done += 1
            if done % 100 == 0:
                self.stdout.write(f'  iNaturalist {done}/{len(pending)}')
            time.sleep(pause)

    def report(self, cache, items):
        photo = worms = nothing = 0
        for _, names in items:
            kind = rl.link_kind(resolve(cache, names))
            photo += kind == 'photo'; worms += kind == 'worms'; nothing += kind == ''
        self.stdout.write(f'From the cache: {photo} iNaturalist pages, {worms} WoRMS pages, {nothing} without a link.')

    @transaction.atomic
    def apply(self, cache, items):
        changed = 0
        for sp, names in items:
            if Species.objects.filter(pk=sp.pk).exclude(reference_link='').exists():
                continue
            url = resolve(cache, names)
            if url:
                Species.objects.filter(pk=sp.pk).update(reference_link=url)
                changed += 1
        self.stdout.write(self.style.SUCCESS(f'{changed} species updated.'))
