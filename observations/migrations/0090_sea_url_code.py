from django.db import migrations, models

# The seas' short codes for shareable gallery links (/?area=med), matched by the Hebrew name, else the English one.
# Runs the same on the Mac and on the live site; a sea not listed here is linked as "sea-<id>" until a code is
# set in the admin.
CODES = [
    ('הים התיכון', 'Mediterranean', 'med'),
    ('ים סוף - מפרץ אילת', 'Red Sea - Gulf of Aqaba', 'eilat'),
    ('ים סוף - מיצר הדמעות', 'Red Sea - Bab el Mandeb strait (Gulf of Aden)', 'bab-el-mandeb'),
    ('אינדו-פסיפי - מערב האוקיאנוס השקט', 'Indo Pacific - Western Pacific', 'w-pacific'),
    ('אינדו-פסיפי - מערב האוקיאנוס השקט - ים מולוקה', 'Indo Pacific - Western Pacific - Molucca Sea', 'molucca'),
    ('אינדו-פסיפי - ים באלי', 'Indo Pacific - Bali Sea', 'bali'),
    ('אינדו-פסיפי - ים האלמוגים', 'Indo Pacific -Coral Sea', 'coral'),
    ('אינדו-פסיפי - ים סין הדרומי', 'Indo Pacific - South China Sea', 'south-china'),
    ('אינדו-פסיפי - מפרץ תאילנד', 'Indo Pacific - Gulf of Thailand', 'thailand'),
    ('האוקיינוס ההודי', 'Indan Ocean', 'indian'),
    ('מערב האוקיינוס ההודי', 'Western Indian Ocean', 'w-indian'),
    ('האוקיינוס השקט', 'Pacific Ocen', 'pacific'),
    ('האוקיינוס השקט - ים ביסמרק', 'Pacific Ocen - Bismarck Sea', 'bismarck'),
    ('האוקיינוס השקט - ים קורו', 'Pacific Ocen - Koro Sea', 'koro'),
    ('האוקיינוס השקט - ים שלמה', 'Pacific Ocen - Solomon Sea', 'solomon'),
]


def set_codes(apps, schema_editor):
    Sea = apps.get_model('observations', 'Sea')
    for name, name_en, code in CODES:
        if Sea.objects.filter(url_code=code).exists():
            continue
        sea = Sea.objects.filter(name=name, url_code='').first() or Sea.objects.filter(name_en=name_en, url_code='').first()
        if sea:
            sea.url_code = code
            sea.save(update_fields=['url_code'])


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0089_speciesarea_chosen_sample'),
    ]

    operations = [
        migrations.AddField(
            model_name='sea',
            name='url_code',
            field=models.SlugField(blank=True, help_text='קוד קצר באנגלית לקישורים משותפים לגלריה, למשל med ← /?area=med. אין לשנות אחרי ששותפו קישורים.', max_length=30, verbose_name='קוד בקישורי הגלריה'),
        ),
        migrations.RunPython(set_codes, migrations.RunPython.noop),
    ]
