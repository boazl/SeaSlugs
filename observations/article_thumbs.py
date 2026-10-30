"""Small preview images of article PDFs (the first page), shown next to each article link.

Made automatically when a PDF is uploaded (Article.save) and, for articles that predate this, the first
time the preview is asked for (articles.article_thumb). Rendered with pypdfium2; a PDF that cannot be
rendered simply has no preview and the page shows a document icon instead."""
import io
import logging

from django.core.files.base import ContentFile

log = logging.getLogger(__name__)
THUMB_WIDTH = 200      # px; shown at 64px, so sharp on high-density screens too


IDENTIFICATION_THUMB_WIDTH = 600     # px; the genus page shows it up to ~300px wide


def render_first_page(field_file, width=THUMB_WIDTH):
    """JPEG bytes of the first page of the PDF in `field_file`, or None when it cannot be rendered."""
    return render_page(field_file, 1, width)


def render_page(field_file, number, width=THUMB_WIDTH):
    """JPEG bytes of page `number` (1 = first; past the end = the last page) of the PDF in `field_file`,
    or None when it cannot be rendered."""
    try:
        import pypdfium2 as pdfium
        with field_file.open('rb') as handle:
            data = handle.read()
        document = pdfium.PdfDocument(data)
        try:
            page = document[min(max(int(number or 1), 1), len(document)) - 1]
            image = page.render(scale=width / page.get_width()).to_pil().convert('RGB')
        finally:
            document.close()
        buffer = io.BytesIO()
        image.save(buffer, 'JPEG', quality=80, optimize=True)
        return buffer.getvalue()
    except Exception as error:       # a damaged or unusual PDF must never break saving or showing the article
        log.warning('No preview for %s: %s', getattr(field_file, 'name', field_file), error)
        return None


def ensure_thumbnail(article, lang):
    """The preview file of the article's PDF in `lang` -- made and stored now when missing -- or None."""
    pdf, thumb = getattr(article, 'pdf_' + lang), getattr(article, 'thumb_' + lang)
    if not pdf:
        return None
    if thumb and thumb.storage.exists(thumb.name):
        return thumb
    data = render_first_page(pdf)
    if not data:
        return None
    thumb.save(f'{article.slug}-{lang}.jpg', ContentFile(data), save=False)
    type(article).objects.filter(pk=article.pk).update(**{'thumb_' + lang: thumb.name})
    return thumb


def ensure_identification_thumbnail(genus, code):
    """The preview file of the genus' identification PDF in `code` ('he' / 'en') -- its chosen page, made
    and stored now when missing -- or None (no file, an image -- shown as itself -- or a PDF that cannot be rendered)."""
    source = genus.identification_file_in(code)
    field = 'identification_thumb' + genus.IDENTIFICATION_SUFFIX[code]
    thumb = getattr(genus, field)
    if not source or not source.name.lower().endswith('.pdf'):
        return None
    if thumb and thumb.storage.exists(thumb.name):
        return thumb
    page = genus.identification_page_in(code)
    data = render_page(source, page, IDENTIFICATION_THUMB_WIDTH)
    if not data:
        return None
    from django.utils.text import slugify
    thumb.save(f'{slugify(genus.name) or "genus"}-{code}-p{page}.jpg', ContentFile(data), save=False)
    type(genus).objects.filter(pk=genus.pk).update(**{field: thumb.name})
    return thumb
