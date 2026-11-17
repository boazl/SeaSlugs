"""Page links for citations of Gosliner, Valdés & Behrens, "Nudibranch & Sea Slug Identification -- Indo-Pacific".

The owner keeps personal PDF copies of the 2nd (2018) and 3rd (2026) editions, in English and Hebrew, on the Mac
(settings.BOOK_PDF_DIR). Where a text cites a page of the book -- a species' identification text, an identification
issue's notes -- a superuser on the Mac gets small links after the page number that open that edition's PDF, in either
language, at the right page. Everyone else, and the live site (where the folder does not exist), sees the plain text:
the books are never served to anyone but the owner.

- The edition of a page reference is the nearest edition mark before it in the text ("מהדורה 3", "השלישית",
  "3rd ed.", "2026" / "מהדורה 2", "השנייה", "2nd ed.", "2018"); a page with no edition mark before it gets no link.
- PDF page from book page: 2nd edition one book page per PDF page, after the cover (book page + 1); 3rd edition
  two-page spreads after the cover and the title page (book page // 2 + 2).
- A link opens /admin/book/<edition>/<lang>/<pdf page>/, a page viewer that shows that PDF page as an image (rendered
  with pypdfium2), with previous / next, the other language and the whole PDF -- a PDF reader such as the Adobe
  Acrobat extension ignores "#page=N", so the page is never left to the reader. All the links open in one named tab
  ("seaslugs-book"), so clicking another citation reuses it.
- /admin/book/<edition>/<lang>/ serves the whole PDF. Everything is for superusers only.
"""
import io
import re
from pathlib import Path

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.html import escape
from django.utils.safestring import mark_safe

FILES = {
    ('2', 'en'): 'NSSI2_Nudibranch_Sea_Slug_ID_Indo-Pacific_2nd_ed_ENG.pdf',
    ('2', 'he'): 'NSSI2_Nudibranch_Sea_Slug_ID_Indo-Pacific_2nd_ed_HEB.pdf',
    ('3', 'en'): 'NSSI3_Nudibranch_Sea_Slug_ID_Indo-Pacific_3rd_ed_ENG.pdf',
    ('3', 'he'): 'NSSI3_Nudibranch_Sea_Slug_ID_Indo-Pacific_3rd_ed_HEB.pdf',
}
EDITION_MARKS = [('3', re.compile(r'מהדורה\s*3|השלישית|3rd ed|\b2026\b')),
                 ('2', re.compile(r'מהדורה\s*2|השנייה|2nd ed|\b2018\b'))]
PAGE = re.compile(r"(?:עמ['׳]|pp?\.)\s*(\d{1,3})(?:\s*[-–]\s*\d{1,3})?")


def book_file(edition, lang):
    folder = getattr(settings, 'BOOK_PDF_DIR', None)
    if not folder or not str(folder):
        return None
    path = Path(folder) / FILES.get((edition, lang), '')
    return path if path.is_file() else None


def pdf_page(edition, page):
    page = int(page)
    return page + 1 if edition == '2' else page // 2 + 2


def _edition_before(text, end):
    """The edition of the nearest edition mark that ends before `end`, else None."""
    best, where = None, -1
    for edition, mark in EDITION_MARKS:
        for m in mark.finditer(text, 0, end):
            if m.start() > where:
                best, where = edition, m.start()
    return best


def linked_citations(text, user, lang='he'):
    """The text as safe HTML (line breaks kept), with page links after each book page reference -- for a superuser,
    and only when that edition's PDFs are on this computer."""
    text = text or ''
    show = bool(user and getattr(user, 'is_superuser', False))
    out, last = [], 0
    for m in PAGE.finditer(text) if show else ():
        edition = _edition_before(text, m.start())
        links = []
        for file_lang, label in sorted([('he', 'עב'), ('en', 'EN')], key=lambda x: x[0] != lang):
            if edition and book_file(edition, file_lang):
                url = reverse('book-page', args=[edition, file_lang, pdf_page(edition, m.group(1))])
                links.append(f'<a class="book-link" href="{url}" target="seaslugs-book" '
                             f'title="{"מהדורה" if lang == "he" else "Edition"} {edition}">{label}</a>')
        out.append(escape(text[last:m.end()]))
        if links:
            out.append(' <span class="book-links">[' + '·'.join(links) + ']</span>')
        last = m.end()
    out.append(escape(text[last:]))
    return mark_safe(''.join(out).replace('\r\n', '\n').replace('\n', '<br>'))


@staff_member_required
def book_pdf(request, edition, lang):
    path = _checked(request, edition, lang)
    return FileResponse(open(path, 'rb'), content_type='application/pdf', filename=path.name, as_attachment=False)

LANG_NAMES = {'he': 'עברית', 'en': 'English'}


def _pages_in(path):
    import pypdfium2 as pdfium
    document = pdfium.PdfDocument(str(path))
    try:
        return len(document)
    finally:
        document.close()


def _checked(request, edition, lang):
    if not request.user.is_superuser:
        raise PermissionDenied
    path = book_file(edition, lang)
    if path is None:
        raise Http404
    return path


@staff_member_required
def book_page(request, edition, lang, page):
    """One page of the book, shown as an image, with previous / next, the other language and the whole PDF."""
    path = _checked(request, edition, lang)
    total = _pages_in(path)
    page = min(max(int(page), 1), total)
    other = 'en' if lang == 'he' else 'he'
    return render(request, 'observations/book_page.html', {
        'edition': edition, 'lang': lang, 'page': page, 'total': total, 'file_name': path.name,
        'image_url': reverse('book-page-image', args=[edition, lang, page]),
        'previous_url': reverse('book-page', args=[edition, lang, page - 1]) if page > 1 else '',
        'next_url': reverse('book-page', args=[edition, lang, page + 1]) if page < total else '',
        'other_url': reverse('book-page', args=[edition, other, page]) if book_file(edition, other) else '',
        'other_name': LANG_NAMES[other], 'pdf_url': reverse('book-pdf', args=[edition, lang])})


@staff_member_required
def book_page_image(request, edition, lang, page):
    """The PDF page as a JPEG, about 1600 pixels wide."""
    path = _checked(request, edition, lang)
    import pypdfium2 as pdfium
    document = pdfium.PdfDocument(str(path))
    try:
        if not 1 <= int(page) <= len(document):
            raise Http404
        sheet = document[int(page) - 1]
        image = sheet.render(scale=1600 / sheet.get_width()).to_pil().convert('RGB')
    finally:
        document.close()
    buffer = io.BytesIO()
    image.save(buffer, 'JPEG', quality=85)
    response = HttpResponse(buffer.getvalue(), content_type='image/jpeg')
    response['Cache-Control'] = 'private, max-age=86400'
    return response
