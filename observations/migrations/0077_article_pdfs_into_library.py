"""Moves every article PDF that was uploaded straight onto a species / order / family / genus / dive trip
(the old article_pdf fields, removed in the next migration) into the article library: one Article per
file -- a file used by several rows becomes one article picked by all of them. The file stays where it
is on disk (the article simply points at it); its title starts as the file name, to be edited in the
admin. These files are scientific papers, so they are taken as the English PDF.

Also fills the notes of the two Gulf of Aqaba Phyllidia pages (only where still empty)."""
from pathlib import PurePosixPath

from django.db import migrations
from django.utils.text import slugify

OWNERS = ('Species', 'TaxonOrder', 'TaxonFamily', 'TaxonGenus', 'DiveTrip')

NOTES = {
    'phyllidia-ocellata-israel-red-sea-gulf-of-aqaba': (
        'הזיהוי אינו ודאי: ייתכן שזהו מופע של Phyllidia undula, שתועד באותו אתר — ראו מאמר.',
        'Identification uncertain: this may be a form of Phyllidia undula, recorded at the same site — see article.'),
    'phyllidia-undula-israel-red-sea-gulf-of-aqaba': (
        'מין זה תואר ב־1986 כתת־מין של Phyllidia ocellata, ומעמדו נדון עד היום. '
        'באותו אתר צולם גם פרט שמוצג כ־P. cf. ocellata — ראו מאמר.',
        'This species was described in 1986 as a subspecies of Phyllidia ocellata, and its status is still debated. '
        'A P. cf. ocellata was photographed at the same site — see article.'),
}


def unique_slug(Article, base):
    base = (slugify(base) or 'article')[:110]
    slug, n = base, 2
    while Article.objects.filter(slug=slug).exists():
        slug, n = f'{base}-{n}', n + 1
    return slug


def forwards(apps, schema_editor):
    Article = apps.get_model('observations', 'Article')
    by_file = {}
    for model_name in OWNERS:
        model = apps.get_model('observations', model_name)
        for row in model.objects.exclude(article_pdf='').exclude(article_pdf__isnull=True):
            name = row.article_pdf.name
            article = by_file.get(name)
            if article is None:
                stem = PurePosixPath(name).stem
                article = Article.objects.create(slug=unique_slug(Article, stem), title_he=stem, title_en=stem, pdf_en=name)
                by_file[name] = article
            row.articles.add(article)
    SpeciesArea = apps.get_model('observations', 'SpeciesArea')
    for slug, (note_he, note_en) in NOTES.items():
        area = SpeciesArea.objects.filter(slug=slug).first()
        if area is not None and not (area.note_he or area.note_en):
            area.note_he, area.note_en = note_he, note_en
            area.save(update_fields=['note_he', 'note_en'])


def backwards(apps, schema_editor):
    """Puts each article back on the rows that pick it (the first PDF of the article)."""
    Article = apps.get_model('observations', 'Article')
    for model_name in OWNERS:
        model = apps.get_model('observations', model_name)
        for row in model.objects.filter(articles__isnull=False).distinct():
            article = row.articles.order_by('pk').first()
            row.article_pdf = article.pdf_en.name or article.pdf_he.name
            row.save(update_fields=['article_pdf'])


class Migration(migrations.Migration):
    dependencies = [('observations', '0076_articles_library')]
    operations = [migrations.RunPython(forwards, backwards)]
