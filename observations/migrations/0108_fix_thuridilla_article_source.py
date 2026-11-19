"""The author line (Article.source) of the Thuridilla phylogeny article (Martín-Hervás et al., 2021) was copied from
the PDF with broken accents: "M. R. Mart ın-Herv as" (a wide space and a dotless i instead of í and á).
Fixed to "M. R. Martín-Hervás" in both environments. Only the exact broken text is changed; safe to run anywhere."""
from django.db import migrations

SLUG = 'a-molecular-phylogeny-of-thuridilla-bergh-1872-sea-slugs-gastropoda-sacoglossa-reveals-a-case-of-flamboyant-and-cryptic'
BROKEN = 'M. R. Mart ın-Herv as'
FIXED = 'M. R. Martín-Hervás'


def fix(apps, schema_editor):
    Article = apps.get_model('observations', 'Article')
    for article in Article.objects.filter(slug=SLUG, source__contains=BROKEN):
        article.source = article.source.replace(BROKEN, FIXED)
        article.save(update_fields=['source'])


class Migration(migrations.Migration):
    dependencies = [('observations', '0107_sp_identification_texts')]
    operations = [migrations.RunPython(fix, migrations.RunPython.noop)]
