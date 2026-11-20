"""The original description of every described species in the gallery, as entries of the articles library (kind
"description", bibliography only -- no PDF): the publication in which the species was described (for a species since
moved to another genus, the description of its original combination), as WoRMS records it ("original description"
sources, read on 2026-11-20 through the WoRMS REST service; observations/data/original_descriptions.json keeps the
data, with the page and the original name of each species). Each entry links to its source (DOI, Biodiversity Heritage
Library page, else its WoRMS source page) and is picked by the species it describes, so it shows on their pages and in
the library's "תיאור והגדרת מינים" section. 214 of the 221 described gallery species (139 publications).
Safe in both environments: an entry is created only when missing (by slug), and only species links are added.
"""
import json
from datetime import date
from pathlib import Path

from django.db import migrations

DATA = Path(__file__).resolve().parent.parent / 'data' / 'original_descriptions.json'


def forward(apps, schema_editor):
    Article = apps.get_model('observations', 'Article')
    Species = apps.get_model('observations', 'Species')
    for entry in json.loads(DATA.read_text(encoding='utf-8')):
        species = list(Species.objects.filter(scientific_name__in=[s['name'] for s in entry['species']]))
        if not species:
            continue
        article = Article.objects.filter(slug=entry['slug']).first()
        if article is None:
            article = Article.objects.create(slug=entry['slug'], kind='description', title_en=entry['title'],
                                             source=entry['source'], citation=entry['citation'], link=entry['link'][:300],
                                             published_on=date(2026, 11, 20))
        article.species.add(*species)


class Migration(migrations.Migration):
    dependencies = [('observations', '0113_bibliography_and_sp_marks')]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
