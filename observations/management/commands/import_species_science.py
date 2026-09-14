"""Fill existing species from a read-only Excel extraction; never infer uncertain names."""
import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from observations.models import Species

FIELDS=['genus','species','author','order','family','superfamily','accepted_genus','accepted_species','common_name','transliteration','language','formatted_author','distribution']
class Command(BaseCommand):
    help='Fill blank scientific fields for exactly matched existing species from an extracted JSON file.'
    def add_arguments(self,parser):
        parser.add_argument('file');parser.add_argument('--apply',action='store_true')
    def handle(self,*args,**options):
        data=json.loads(Path(options['file']).read_text());changed=0;conflicts=[]
        with transaction.atomic():
            for row in data['updates']:
                obj=Species.objects.get(pk=row['id'])
                if obj.scientific_name!=row['scientific_name']:raise CommandError('Species name changed; extract again.')
                fields=[]
                for field in FIELDS:
                    value=row['data'].get('FormattedAuthor' if field=='formatted_author' else field,'')
                    if not value:continue
                    if getattr(obj,field) and getattr(obj,field)!=value:
                        conflicts.append(f'{obj.scientific_name}: {field}');continue
                    if not getattr(obj,field):setattr(obj,field,value);fields.append(field)
                if fields:
                    obj.full_clean();changed+=1
                    if options['apply']:obj.save(update_fields=fields)
        self.stdout.write(f'{changed} species '+('updated' if options['apply'] else 'to update'))
        self.stdout.write(f"Unmatched: {len(data['missing'])}; ambiguous: {len(data['ambiguous'])}; conflicts: {len(conflicts)}")
        for conflict in conflicts:self.stdout.write(conflict)
