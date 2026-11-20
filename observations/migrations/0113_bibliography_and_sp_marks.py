"""The articles library as a bibliography, and every undescribed species in the gallery with a marked name and a source.

1. Library entries (Article.kind / citation / short_ref): the two editions of Gosliner, Valdés & Behrens, "Nudibranch &
   Sea Slug Identification -- Indo-Pacific" are added as identification guides (bibliography entries only, no PDF);
   the existing papers get their kind, their full reference (checked against Crossref) and the short form that species
   cite them by -- so "(Source: NSSI-2 ...)" on a species page links to its entry. Only empty fields are filled.
2. Coryphellina sp. 1 and Thuridilla sp. 7: their numbers are the 2nd edition's (the label on their photos).
3. A bare "Genus sp." is an unidentified animal, like the owner's lettered marks: each gallery card of one gets a mark --
   its card's variant letter when it has one, else the next free letter in the genus ("Okenia sp." beside "Okenia sp. A"
   becomes "Okenia sp. B") -- in place: a species with a single card is renamed; a card whose mark is already a catalogue
   row with no observations of its own moves to that row ("Phyllidiella sp." A / B). Observations keep their rows and
   transfer ids; the card keeps its row and its published URL (slug); the variant letter is folded into the name.
   Each marked species gets its source: the site observation that defines it (as in migration 0111).
Safe in both environments: everything is found by name or slug and done only where still needed.
"""
import re
from datetime import date

from django.db import migrations

NSSI2 = 'NSSI-2 Gosliner, Valdés & Behrens, 2018'
NSSI3 = 'NSSI-3 Gosliner, Valdés & Behrens, 2026'

BOOKS = [
    {'slug': 'nssi-2-gosliner-valdes-behrens-2018', 'short_ref': NSSI2,
     'title_en': 'Nudibranch & Sea Slug Identification – Indo-Pacific (2nd edition)',
     'title_he': 'Nudibranch & Sea Slug Identification – Indo-Pacific (מהדורה שנייה)',
     'source': 'Gosliner, Valdés & Behrens, 2018', 'link': '',
     'citation': 'Gosliner, T.M., Valdés, Á. & Behrens, D.W. (2018). Nudibranch & Sea Slug Identification – Indo-Pacific. '
                 '2nd edition. New World Publications, Jacksonville, FL. 451 pp. ISBN 978-1-878348-67-8.'},
    {'slug': 'nssi-3-gosliner-valdes-behrens-2026', 'short_ref': NSSI3,
     'title_en': 'Nudibranch & Sea Slug Identification – Indo-Pacific (3rd edition)',
     'title_he': 'Nudibranch & Sea Slug Identification – Indo-Pacific (מהדורה שלישית)',
     'source': 'Gosliner, Valdés & Behrens, 2026', 'link': 'https://fishid.com/nudiindo.html',
     'citation': 'Gosliner, T.M., Valdés, Á. & Behrens, D.W. (2026). Nudibranch & Sea Slug Identification – Indo-Pacific. '
                 '3rd edition. New World Publications, Jacksonville, FL.'},
]

# slug -> (kind, short reference, full reference, link when none)
PAPERS = {
    'zookeys-1006-001': ('description', 'Yonow, 2020',
        'Yonow, N. (2020). Red Sea Opisthobranchia 6: Phyllidiidae and their paradorid mimic: new species and new records '
        '(Heterobranchia, Nudibranchia, Doridina). ZooKeys 1006: 1–34.', 'https://doi.org/10.3897/zookeys.1006.59732'),
    'coryphellina': ('description', 'Ekimova et al., 2022',
        'Ekimova, I., Deart, Y., Antokhina, T., Mikhlina, A. & Schepetov, D. (2022). Stripes matter: integrative systematics '
        'of Coryphellina rubrolineata species complex (Gastropoda: Nudibranchia) from Vietnam. Diversity 14(4): 294.',
        'https://doi.org/10.3390/d14040294'),
    'phyllidiidae_from_papua_new_guinea': ('description', 'Domínguez et al., 2007',
        'Domínguez, M., Quintas, P. & Troncoso, J.S. (2007). Phyllidiidae (Opisthobranchia: Nudibranchia) from Papua New '
        'Guinea with the description of a new species of Phyllidiella. American Malacological Bulletin 22(1): 89–117.',
        'https://doi.org/10.4003/0740-2783-22.1.89'),
    'a-molecular-phylogeny-of-thuridilla-bergh-1872-sea-slugs-gastropoda-sacoglossa-reveals-a-case-of-flamboyant-and-cryptic':
        ('description', 'Martín-Hervás et al., 2021',
         'Martín-Hervás, M.R., Carmona, L., Malaquias, M.A.E., Krug, P.J., Gosliner, T.M. & Cervera, J.L. (2021). A molecular '
         'phylogeny of Thuridilla Bergh, 1872 sea slugs (Gastropoda, Sacoglossa) reveals a case of flamboyant and cryptic '
         'radiation in the marine realm. Cladistics 37(6): 647–676. https://doi.org/10.1111/cla.12465',
         'https://doi.org/10.1111/cla.12465'),
    'origin-and-biogeography-of-the-colourful-sap-sucking-sea-slugs-genus-thuridilla-bergh-1872-mollusca-gastropoda-heterobra':
        ('general', 'Martín-Hervás et al., 2025',
         'Martín-Hervás, M.R., Carmona, L., Krug, P.J., Gosliner, T.M., Cervera, J.L. & Malaquias, M.A.E. (2025). Origin and '
         'biogeography of the colourful sap-sucking sea slugs genus Thuridilla Bergh, 1872 (Mollusca, Gastropoda, '
         'Heterobranchia). Journal of Biogeography 52(10).', 'https://doi.org/10.1111/jbi.15171'),
    'extreme-autotomy-and-whole-body-regeneration-in-photosynthetic-sea-slugs': ('general', 'Mitoh & Yusa, 2021',
        'Mitoh, S. & Yusa, Y. (2021). Extreme autotomy and whole-body regeneration in photosynthetic sea slugs. '
        'Current Biology 31(5): R233–R234.', 'https://doi.org/10.1016/j.cub.2021.01.014'),
}
BOOK_NUMBERS = {'Coryphellina sp. 1': NSSI2, 'Thuridilla sp. 7': NSSI2}
LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'


def bibliography(apps):
    Article = apps.get_model('observations', 'Article')
    for book in BOOKS:
        if not Article.objects.filter(slug=book['slug']).exists():
            Article.objects.create(kind='guide', published_on=date(2026, 11, 20), **book)
    for slug, (kind, short_ref, citation, link) in PAPERS.items():
        article = Article.objects.filter(slug=slug).first()
        if article is None:
            continue
        if not article.citation.strip():
            article.kind, article.citation = kind, citation
        if not article.short_ref.strip():
            article.short_ref = short_ref
        if not article.link:
            article.link = link
        article.save(update_fields=['kind', 'citation', 'short_ref', 'link'])


def site_source(apps, species):
    Sample = apps.get_model('observations', 'Sample')
    Profile = apps.get_model('observations', 'Profile')
    samples = list(Sample.objects.filter(species=species, kind='species', status='published', deleted_at__isnull=True)
                   .select_related('trip__region', 'owner'))
    if not samples:
        return ''
    first = min(samples, key=lambda s: (s.trip.year or 9999, s.trip.month or 13, s.trip.start_day or 99, s.pk))
    owner, trip, name = first.owner, first.trip, ''
    if owner is not None:
        profile = Profile.objects.filter(user=owner).first()
        name = f'{profile.first_name_en} {profile.last_name_en}'.strip() if profile else ''
        name = name or f'{owner.first_name} {owner.last_name}'.strip()
    region = (trip.region.name_en or trip.region.name) if trip.region_id else ''
    return 'SeaSlugs.org.il observation: ' + ', '.join(p for p in (name, region, str(trip.year or '')) if p)


def mark_bare_sp(apps):
    Species = apps.get_model('observations', 'Species')
    Sample = apps.get_model('observations', 'Sample')
    SpeciesArea = apps.get_model('observations', 'SpeciesArea')
    for area in SpeciesArea.objects.filter(species__species__in=['sp.', 'sp']).select_related('species').order_by('pk'):
        bare = area.species
        taken = {s.strip() for s in Species.objects.filter(genus=bare.genus).values_list('species', flat=True)}
        letter = area.undetermined_variant.strip().upper()
        target = Species.objects.filter(genus=bare.genus, species=f'sp. {letter}').first() if letter else None
        if target is not None and Sample.objects.filter(species=target).exists():
            target, letter = None, ''        # that mark is already in use by other observations: take a free letter
        if not letter or (target is None and f'sp. {letter}' in taken):
            letter = next(l for l in LETTERS if f'sp. {l}' not in taken)
        epithet = f'sp. {letter}'
        samples = Sample.objects.filter(species=bare, kind='species', trip__country=area.country_id,
                                        trip__region__sea=area.sea_id, undetermined_variant=area.undetermined_variant)
        others = Sample.objects.filter(species=bare).exclude(pk__in=samples.values('pk')).exists() \
            or SpeciesArea.objects.filter(species=bare).exclude(pk=area.pk).exists()
        if target is None and not others:
            Species.objects.filter(pk=bare.pk).update(species=epithet, scientific_name=f'{bare.genus} {epithet}')
            target = Species.objects.get(pk=bare.pk)
        elif target is None:
            values = {f.attname: getattr(bare, f.attname) for f in Species._meta.concrete_fields
                      if f.attname not in ('id', 'source_id', 'name_source')}
            values.update(species=epithet, scientific_name=f'{bare.genus} {epithet}')
            target = Species.objects.create(**values)
        samples.update(species=target, undetermined_variant='')
        SpeciesArea.objects.filter(pk=area.pk).update(species=target, undetermined_variant='')
        if not target.name_source:
            source = site_source(apps, target)
            if source:
                Species.objects.filter(pk=target.pk).update(name_source=source)


def forward(apps, schema_editor):
    Species = apps.get_model('observations', 'Species')
    if not Species.objects.exists():
        return  # an empty database (a new install, the test database): no catalogue to cite
    bibliography(apps)
    for name, source in BOOK_NUMBERS.items():
        Species.objects.filter(scientific_name=name, name_source='').update(name_source=source)
    mark_bare_sp(apps)


class Migration(migrations.Migration):
    dependencies = [('observations', '0112_article_bibliography')]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
