"""The name under which a species appears in a publication (SpeciesPublicationName), and the editions of Gosliner,
Valdés & Behrens set straight:
- Every gallery "sp. N" was named by the 2nd edition (2018): the labels on the photos say so. Migration 0110 gave 14 of
  them the 3rd edition (2026) as their name source because the number is the same there; they go back to NSSI-2.
- The 3rd edition is linked only to the species it has a name for, with that name and its pages: the 3rd-edition
  accounts found by the comparison of the editions (0106, each checked by the same photograph in both editions) and
  used for the identification texts (0107) -- the same name for 14 species, a new number, genus or a described name
  for 19 (e.g. Marionia sp. 6 -> Marioniopsis sp. 11). Species not found in the 3rd edition are not linked to it.
- The links 0116 made from citations in the texts are removed: a guide stays linked to a species only by the species'
  name source, by a name in it, or -- never here -- by hand (no guide was picked by hand before 0116).
Safe in both environments: species found by scientific name, a name source changed only while it is still NSSI-3, a
name written only where missing.
"""
from importlib import import_module

import django.db.models.deletion
from django.db import migrations, models

NSSI2 = 'NSSI-2 Gosliner, Valdés & Behrens, 2018'
NSSI3 = 'NSSI-3 Gosliner, Valdés & Behrens, 2026'


def forward(apps, schema_editor):
    Article = apps.get_model('observations', 'Article')
    Species = apps.get_model('observations', 'Species')
    Name = apps.get_model('observations', 'SpeciesPublicationName')
    Species.objects.filter(name_source=NSSI3).update(name_source=NSSI2)
    third = Article.objects.filter(short_ref=NSSI3).first()
    if third is not None:
        texts = import_module('observations.migrations.0107_sp_identification_texts')
        for name, _he, _en, book, page, as_name in texts.TEXTS:
            species = Species.objects.filter(scientific_name=name).first()
            if book == texts.B3 and species is not None:
                Name.objects.get_or_create(species=species, article=third, defaults={'name': as_name, 'pages': page})
    for guide in Article.objects.filter(kind='guide'):
        named = set(Name.objects.filter(article=guide).values_list('species_id', flat=True))
        source = (guide.short_ref or '').strip()
        for species in list(guide.species.all()):
            if species.pk not in named and not (source and (species.name_source or '').strip() == source):
                guide.species.remove(species)
        if source:
            guide.species.add(*Species.objects.filter(name_source=source))
        guide.species.add(*Species.objects.filter(pk__in=named))


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0116_link_guides_to_species'),
    ]

    operations = [
        migrations.CreateModel(
            name='SpeciesPublicationName',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, verbose_name='השם בפרסום')),
                ('pages', models.CharField(blank=True, max_length=40, verbose_name='עמודים')),
                ('article', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='species_names', to='observations.article', verbose_name='פרסום')),
                ('species', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='publication_names', to='observations.species', verbose_name='מין')),
            ],
            options={
                'verbose_name': 'שם המין בפרסום',
                'verbose_name_plural': 'שם המין בפרסומים (למשל במהדורה השלישית)',
                'ordering': ['article__slug'],
                'constraints': [models.UniqueConstraint(fields=('species', 'article'), name='unique_species_publication_name')],
            },
        ),
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
