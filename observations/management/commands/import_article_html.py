"""manage.py import_article_html <slug> <hebrew.html> <english.html> --figures 413,458,102,412 [--drop-pdfs]

Reads an article prepared as two HTML pages into an article written on the site (see observations/article_import.py).
An existing article with that slug keeps its address and the pages that pick it; its sections are replaced."""
from django.core.management.base import BaseCommand, CommandError

from observations.article_import import import_article
from observations.models import Article, Sample


class Command(BaseCommand):
    help = 'Import a bilingual article from two HTML pages into an article written on the site.'

    def add_arguments(self, parser):
        parser.add_argument('slug')
        parser.add_argument('hebrew')
        parser.add_argument('english')
        parser.add_argument('--figures', default='', help='The observation numbers of the figures, in order, comma separated.')
        parser.add_argument('--drop-pdfs', action='store_true', help='Remove the PDFs uploaded to the article (the page prints to PDF).')

    def handle(self, slug, hebrew, english, figures, drop_pdfs, **options):
        try:
            ids = [int(x) for x in figures.split(',') if x.strip()]
        except ValueError:
            raise CommandError('--figures: מספרי תצפיות מופרדים בפסיק.')
        samples = []
        for pk in ids:
            sample = Sample.objects.filter(pk=pk, deleted_at__isnull=True).first()
            if sample is None:
                raise CommandError(f'תצפית {pk} לא נמצאה.')
            samples.append(sample)
        with open(hebrew, encoding='utf-8') as he, open(english, encoding='utf-8') as en:
            he_html, en_html = he.read(), en.read()
        article = Article.objects.filter(slug=slug).first() or Article(slug=slug)
        try:
            import_article(article, he_html, en_html, samples, drop_pdfs=drop_pdfs)
        except ValueError as exc:
            raise CommandError(str(exc))
        self.stdout.write(f'{article}: {article.blocks.count()} קטעים, {article.references.count()} מקורות.')
