"""Import gallery labels, without asserting taxonomic identification or validity."""
import json
import re
import unicodedata
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from observations.models import Species
from observations.table_transfer import create_backup

GENERAL = {'Romblon 2026 SlideShow', 'קניון אכזיב יולי 23'}

def label(title):
    value = ' '.join(unicodedata.normalize('NFKC', title).split())
    value = re.sub(r'\s+(juv\.?|RedSea)$', '', value, flags=re.I)
    value = re.sub(r'\b(sp|cf)\.?\b\.?', lambda m:m.group(1)+'.', value)
    return value.strip()

def match_key(name):
    return label(re.sub(r'\s*\([^()]*\)\s*$', '', name)).casefold()

class Command(BaseCommand):
    help = 'Preview gallery species import; --apply adds missing labels to the local DB.'
    def add_arguments(self, parser):parser.add_argument('--apply',action='store_true')
    def handle(self,*args,**options):
        if settings.PRODUCTION:raise CommandError('This import is intended for the local development database only.')
        text=(settings.BASE_DIR/'dist/catalog.js').read_text()
        prefix='window.SEASLUGS = '
        if not text.startswith(prefix):raise CommandError('Unexpected catalog format.')
        catalog=json.loads(text[len(prefix):].strip().removesuffix(';'))
        existing={}
        for item in Species.objects.all():existing.setdefault(match_key(item.scientific_name),[]).append(item)
        rows=[];seen=set();skipped=[]
        for video in catalog['videos']:
            title=' '.join(unicodedata.normalize('NFKC',video['title']).split())
            if title in GENERAL:skipped.append(title);continue
            name=label(title)
            if not re.fullmatch(r'[A-Z][a-z]+ (?:[a-z]+|(?:sp\.|cf\.)(?: [A-Za-z0-9]+)?)', name):
                raise CommandError('Unrecognized title requiring manual review: '+title)
            key=match_key(name)
            if len(existing.get(key,[]))>1:raise CommandError('Ambiguous existing species: '+name)
            if key in seen:continue
            seen.add(key)
            rows.append((name,existing.get(key,[None])[0]))
        new=[name for name,obj in rows if obj is None]
        self.stdout.write(f'Gallery labels: {len(rows)}; existing: {len(rows)-len(new)}; new: {len(new)}; general videos skipped: {len(skipped)}')
        if not options['apply']:
            for name in new:self.stdout.write('+ '+name)
            return
        backup=create_backup()
        with transaction.atomic():
            for name in new:Species.objects.create(scientific_name=name)
        report={'backup':backup.name,'added':new,'matched':[{'gallery':name,'existing':obj.scientific_name,'id':obj.pk} for name,obj in rows if obj], 'skipped':skipped,'note':'Labels copied from gallery; sp./cf. remain provisional. No external taxonomic verification performed.'}
        path=Path(settings.DATA_DIR)/'backups'/(backup.stem+'-species-import.json')
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2))
        self.stdout.write(self.style.SUCCESS(f'Added {len(new)} species labels. Report: {path}'))
