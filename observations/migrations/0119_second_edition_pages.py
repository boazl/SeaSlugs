"""The 2nd-edition pages of the gallery's "sp. N" species, where the comparison of the editions found them (0106, 0107):
a SpeciesPublicationName of the 2nd edition with the species' own name, so its link says "appears in it under the
same name, p. N" and, for the owner on the Mac, opens the book at that page (book_links.species_book_url). A species
without a known page opens at the first page of the book that names it. Thuridilla sp. 7 is left out: which numbering
its photo follows is still being checked. Safe in both environments: only species that exist, only where missing.
"""
from importlib import import_module

from django.db import migrations

NSSI2 = 'NSSI-2 Gosliner, Valdés & Behrens, 2018'
# found by the comparison of the editions (0106) but not in 0107's texts
MORE = {'Aegires sp. 7': '67', 'Tritonia sp. 3': '257', 'Haminoea sp. 2': '350', 'Samla sp. 4': '275',
        'Phyllidia sp. 1': '212'}


def pages():
    texts = import_module('observations.migrations.0107_sp_identification_texts')
    found = dict(texts.SECOND_EDITION_PAGE)
    found.update({name: page for name, _he, _en, book, page, _as in texts.TEXTS if book == texts.B2})
    found.update(MORE)
    return found


def forward(apps, schema_editor):
    Article = apps.get_model('observations', 'Article')
    Species = apps.get_model('observations', 'Species')
    Name = apps.get_model('observations', 'SpeciesPublicationName')
    second = Article.objects.filter(short_ref=NSSI2).first()
    if second is None:
        return
    for name, page in pages().items():
        species = Species.objects.filter(scientific_name=name).first()
        if species is not None:
            Name.objects.get_or_create(species=species, article=second, defaults={'name': name, 'pages': page})
            second.species.add(species)


class Migration(migrations.Migration):
    dependencies = [('observations', '0118_book_edition_issue_names')]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
