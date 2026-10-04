# Data only. Authors (with year) for catalog species that had none, taken from WoRMS
# (AphiaRecordsByName, October 2026) -- the authority exactly as WoRMS gives it, parentheses
# included (they mean the species was described in another genus). Only an EMPTY author is
# filled; an author that is already there is never overwritten. Names WoRMS did not settle
# (two homonyms, a superseded combination, lookups that were rate limited) are NOT in this
# list and are handled separately. Idempotent; the reverse does nothing.
from django.db import migrations

AUTHORS = {
    ('Micromelo', 'undatus'): '(Bruguière, 1792)',
    ('Pleurobranchus', 'forskalii'): 'Rüppell & Leuckart, 1828',
    ('Pleurobranchus', 'grandis'): 'Pease, 1868',
    ('Pleurobranchus', 'peronii'): 'Cuvier, 1804',
    ('Hexabranchus', 'sanguineus'): '(Rüppell & Leuckart, 1830)',
    ('Thecacera', 'picta'): 'Baba, 1972',
    ('Tambja', 'kava'): 'Pola, Padula, Gosliner & Cervera, 2014',
    ('Pelagella', 'felis'): '(Baba, 1949)',
    ('Trapania', 'miltabrancha'): 'Gosliner & Fahey, 2008',
    ('Trapania', 'vitta'): 'Gosliner & Fahey, 2008',
    ('Discodoris', 'boholiensis'): 'Bergh, 1877',
    ('Chromodoris', 'joshi'): 'Gosliner & Behrens, 1998',
    ('Goniobranchus', 'verrieri'): '(Crosse, 1875)',
    ('Hypselodoris', 'carnea'): '(Bergh, 1889)',
    ('Hypselodoris', 'maculosa'): '(Pease, 1871)',
    ('Hypselodoris', 'roo'): 'Gosliner & R. F. Johnson, 2018',
    ('Dermatobranchus', 'pustulosus'): 'van Hasselt, 1824',
    ('Cabangus', 'regius'): '(Pola & Stout, 2008)',
    ('Flabellina', 'gabinierei'): '(Vicente, 1975)',
    ('Flabellina', 'ischitana'): 'Y. Hirano & T. E. Thompson, 1990',
    ('Phyllodesmium', 'pinnatum'): 'E. Moore & Gosliner, 2009',
    ('Phyllodesmium', 'tuberculatum'): 'E. Moore & Gosliner, 2009',
    ('Pteraeolidia', 'semperi'): '(Bergh, 1870)',
    ('Chelidonura', 'hirundinina'): '(Quoy & Gaimard, 1833)',
    ('Stylocheilus', 'striatus'): '(Quoy & Gaimard, 1832)',
    ('Cyerce', 'elegans'): 'Bergh, 1870',
    ('Ercolania', 'endophytophaga'): 'K. R. Jensen, 1999',
    ('Thuridilla', 'gracilis'): '(Risbec, 1928)',
    ('Coryphellina', 'iurmanovi'): 'Korshunova, Fletcher & Martynov, 2025',
    ('Cyerce', 'basi'): 'K. Moreno, Gosliner, N. G. Wilson, Krug & Á. Valdés, 2025',
    ('Cyerce', 'blackburnae'): 'K. Moreno, Gosliner, N. G. Wilson, Krug & Á. Valdés, 2025',
    ('Marioniopsis', 'elongoviridis'): '(V. G. Smith & Gosliner, 2007)',
}


def fill(apps, schema_editor):
    Species = apps.get_model('observations', 'Species')
    for (genus, epithet), author in AUTHORS.items():
        Species.objects.filter(genus=genus, species=epithet, author='').update(author=author)


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0046_fold_fiona_pinnata_case_duplicate'),
    ]

    operations = [
        migrations.RunPython(fill, migrations.RunPython.noop),
    ]
