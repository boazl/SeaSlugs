# Data only. The remaining catalog authors (with year), taken from the WoRMS Taxon Match tool
# (all 70 names matched exactly, October 2026) -- the authority exactly as WoRMS lists the name,
# parentheses included. Only an EMPTY author is filled; an existing one is never overwritten.
# NOT in the list: Triopa principis-walliae (WoRMS gives no authority for it). Four names are
# listed by WoRMS as unaccepted combinations (Marionia arborescens, Eubranchus mandapamensis,
# Tenellia minor, Okenia brunneomaculata); they keep their names here -- renaming or folding
# them is a separate decision. Idempotent; the reverse does nothing.
from django.db import migrations

AUTHORS = {
    ('Plocamopherus', 'ceylonicus'): '(Kelaart, 1858)',
    ('Plocamopherus', 'maculapodium'): 'Vallès & Gosliner, 2006',
    ('Nembrotha', 'chamberlaini'): 'Gosliner & Behrens, 1997',
    ('Nembrotha', 'milleri'): 'Gosliner & Behrens, 1997',
    ('Martadoris', 'limaciformis'): '(Eliot, 1908)',
    ('Trapania', 'euryeia'): 'Gosliner & Fahey, 2008',
    ('Taringa', 'halgerda'): 'Gosliner & Behrens, 1998',
    ('Halgerda', 'batangas'): 'Carlson & Hoff, 2000',
    ('Jorunna', 'funebris'): '(Kelaart, 1858)',
    ('Jorunna', 'rubescens'): '(Bergh, 1876)',
    ('Cadlinella', 'ornatissima'): '(Risbec, 1928)',
    ('Chromodoris', 'alcalai'): 'Gosliner, 2021',
    ('Chromodoris', 'colemani'): 'Rudman, 1982',
    ('Chromodoris', 'elisabethina'): 'Bergh, 1877',
    ('Goniobranchus', 'albonares'): '(Rudman, 1990)',
    ('Goniobranchus', 'coi'): '(Risbec, 1956)',
    ('Goniobranchus', 'preciosus'): '(Kelaart, 1858)',
    ('Mexichromis', 'multituberculata'): '(Baba, 1953)',
    ('Mexichromis', 'trilineata'): '(A. Adams & Reeve, 1850)',
    ('Glossodoris', 'acosti'): 'S. B. Matsuda & Gosliner, 2018',
    ('Glossodoris', 'buko'): 'S. B. Matsuda & Gosliner, 2018',
    ('Doriprismatica', 'atromarginata'): '(Cuvier, 1804)',
    ('Ardeadoris', 'egretta'): 'Rudman, 1984',
    ('Verconia', 'simplex'): '(Pease, 1871)',
    ('Verconia', 'varians'): '(Pease, 1871)',
    ('Thorunna', 'furtiva'): 'Bergh, 1878',
    ('Hypselodoris', 'apolegma'): '(Yonow, 2001)',
    ('Hypselodoris', 'bullockii'): '(Collingwood, 1881)',
    ('Hypselodoris', 'emma'): 'Rudman, 1977',
    ('Hypselodoris', 'variobranchia'): 'Gosliner & R. F. Johnson, 2018',
    ('Miamira', 'alleni'): '(Gosliner, 1996)',
    ('Dendrodoris', 'nigra'): '(W. Stimpson, 1855)',
    ('Phyllidia', 'picta'): 'Pruvot-Fol, 1957',
    ('Phyllidia', 'varicosa'): 'Lamarck, 1801',
    ('Phyllidiella', 'granulata'): 'Brunckhorst, 1993',
    ('Phyllidiopsis', 'annae'): 'Brunckhorst, 1993',
    ('Phyllidiopsis', 'fissurata'): 'Brunckhorst, 1993',
    ('Phyllidiopsis', 'krempfi'): 'Pruvot-Fol, 1957',
    ('Phyllidiopsis', 'striata'): 'Bergh, 1889',
    ('Melibe', 'viridis'): '(Kelaart, 1858)',
    ('Marionia', 'arborescens'): 'Bergh, 1890',
    ('Coryphellina', 'lotos'): 'Korshunova, Martynov, Bakken, Evertsen, Fletcher, Mudianta, H. Saito, Lundin, Schrödl & Picton, 2017',
    ('Coryphellina', 'pseudolotos'): 'Ekimova, Deart, Antokhina, Mikhlina & Schepetov, 2022',
    ('Samla', 'bicolor'): '(Kelaart, 1858)',
    ('Samla', 'bilas'): '(Gosliner & Willan, 1991)',
    ('Samla', 'riwo'): '(Gosliner & Willan, 1991)',
    ('Eubranchus', 'mandapamensis'): '(K. P. Rao, 1968)',
    ('Tenellia', 'minor'): '(Rudman, 1981)',
    ('Unidentia', 'sandramillenae'): 'Korshunova, Martynov, Bakken, Evertsen, Fletcher, Mudianta, H. Saito, Lundin, Schrödl & Picton, 2017',
    ('Phyllodesmium', 'briareum'): '(Bergh, 1896)',
    ('Phyllodesmium', 'crypticum'): 'Rudman, 1981',
    ('Phyllodesmium', 'jakobsenae'): 'Burghardt & Wägele, 2004',
    ('Phyllodesmium', 'koehleri'): 'Burghardt, Schrödl & Wägele, 2008',
    ('Phyllodesmium', 'magnum'): 'Rudman, 1991',
    ('Phyllodesmium', 'rudmani'): 'Burghardt & Gosliner, 2006',
    ('Odontoglaja', 'guamensis'): 'Rudman, 1978',
    ('Philinopsis', 'speciosa'): 'Pease, 1860',
    ('Tubulophilinopsis', 'pilsbryi'): '(Eliot, 1900)',
    ('Sagaminopteron', 'nigropunctatum'): 'Carlson & Hoff, 1973',
    ('Sagaminopteron', 'psychedelicum'): 'Carlson & Hoff, 1974',
    ('Siphopteron', 'makisig'): 'Ong & Gosliner, 2017',
    ('Notarchus', 'indicus'): 'Schweigger, 1820',
    ('Elysia', 'grandifolia'): 'Kelaart, 1858',
    ('Thuridilla', 'albopustulosa'): 'Gosliner, 1995',
    ('Thuridilla', 'flavomaculata'): 'Gosliner, 1995',
    ('Plakobranchus', 'papua'): 'Meyers-Muñoz & van der Velde, 2016',
    ('Chromodoris', 'dianae'): 'Gosliner & Behrens, 1998',
    ('Dendrodoris', 'albobrunnea'): 'J. K. Allan, 1933',
    ('Okenia', 'brunneomaculata'): 'Gosliner, 2004',
}


def fill(apps, schema_editor):
    Species = apps.get_model('observations', 'Species')
    for (genus, epithet), author in AUTHORS.items():
        Species.objects.filter(genus=genus, species=epithet, author='').update(author=author)


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0048_nakamotoensis_and_reticulatus'),
    ]

    operations = [
        migrations.RunPython(fill, migrations.RunPython.noop),
    ]
