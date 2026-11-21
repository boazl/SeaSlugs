"""The identification-issues rows "update the name by the 3rd edition" (kind book_edition, migration 0106): the
corrected name now carries the source of the new name, as the site shows it for an undescribed species --
"Aegires sp. 13 (NSSI-3 Gosliner, Valdés & Behrens, 2026)" -- and a change of the number only (same genus) gets a low
priority; a move to another genus keeps its priority. Only rows whose identification changed between the editions
exist (a species with the same name in both editions has none). The rows of species described since the 2nd edition
(kind worms_name) already carry their author and year.
Safe in both environments: only open rows (open / checking / decided) whose corrected name is still a bare "Genus sp. N".
"""
import re

from django.db import migrations

NSSI3 = 'NSSI-3 Gosliner, Valdés & Behrens, 2026'
BARE = re.compile(r'^(?P<genus>[A-Z][a-z]+) sp\. \S+$')
LOW = 3


def forward(apps, schema_editor):
    Issue = apps.get_model('observations', 'IdentificationIssue')
    for issue in Issue.objects.filter(kind='book_edition', status__in=('open', 'checking', 'decided'), species__isnull=False):
        m = BARE.match(issue.corrected_name.strip())
        if not m:
            continue
        issue.corrected_name = f'{issue.corrected_name.strip()} ({NSSI3})'
        if m.group('genus') == (issue.species.genus or issue.species.scientific_name.split(' ')[0]):
            issue.priority = LOW
        issue.save(update_fields=['corrected_name', 'priority', 'updated_at'])


class Migration(migrations.Migration):
    dependencies = [('observations', '0117_species_publication_names')]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
