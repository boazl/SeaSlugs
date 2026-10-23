"""HTML of an article written on the site (Article + its ArticleBlock sections and ArticleReference list), in
one language. Text is plain with a light markup -- **bold**, *italics*, [text](link) -- and the scientific names
of catalog species are set in italics on their own (names.italicize_names): the genus and the epithet, never
cf./aff. or the author. Figures are numbered in order ("איור 1" / "Figure 1") and show the chosen observation's
photo through the site's own photo address."""
import re

from django.urls import reverse
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe

from .names import italicize_names

_LINK = re.compile(r'\[([^\]\n]+)\]\(((?:https?://|/)[^)\s]+)\)')
_BOLD = re.compile(r'\*\*(.+?)\*\*', re.S)
_ITALIC = re.compile(r'(?<![\*\w])\*(?!\s)(.+?)(?<!\s)\*(?![\*\w])', re.S)

UNTRANSLATED = {'he': 'קטע זה עדיין לא תורגם לעברית.', 'en': 'This section has not been translated into English yet.'}


def inline(text, binomials=None, names=True, lang='he'):
    """HTML of one run of marked-up text. A link to a page of this site (/...) keeps the page's language."""
    text = str(text or '')
    best = None
    for kind, pattern in (('link', _LINK), ('bold', _BOLD), ('italic', _ITALIC)):
        match = pattern.search(text)
        if match and (best is None or match.start() < best[1].start()):
            best = (kind, match)
    if best is None:
        return str(italicize_names(text, binomials)) if names else str(escape(text))
    kind, match = best
    before = inline(text[:match.start()], binomials, names, lang)
    after = inline(text[match.end():], binomials, names, lang)
    if kind == 'link':
        url = match.group(2)
        external = url.startswith('http')
        if not external and lang == 'en':
            from .templatetags.seaslugs_i18n import with_lang
            url = with_lang(url, lang)
        middle = format_html('<a href="{}"{}>{}</a>', url, mark_safe(' target="_blank" rel="noopener"') if external else '',
                             mark_safe(inline(match.group(1), binomials, names, lang)))
    elif kind == 'bold':
        middle = '<strong>' + inline(match.group(1), binomials, names, lang) + '</strong>'
    else:
        middle = '<i>' + inline(match.group(1), binomials, False, lang) + '</i>'
    return before + str(middle) + after


def plain(text):
    """The text without its markup (for an image's alt text, a summary)."""
    text = _LINK.sub(lambda m: m.group(1), str(text or ''))
    return _ITALIC.sub(lambda m: m.group(1), _BOLD.sub(lambda m: m.group(1), text)).strip()


def paragraphs(text, binomials, lang='he', lead=''):
    """<p> per paragraph (blank line between paragraphs); `lead` (HTML) opens the first one."""
    parts = [p.strip() for p in re.split(r'\n\s*\n', str(text or '').replace('\r\n', '\n')) if p.strip()] or ([''] if lead else [])
    return ''.join('<p>' + (lead if i == 0 else '') + '<br>'.join(inline(line, binomials, lang=lang) for line in part.split('\n')) + '</p>'
                   for i, part in enumerate(parts))


def table(text, binomials, lang='he'):
    rows = [[cell.strip() for cell in line.strip().strip('|').split('|')] for line in str(text or '').splitlines() if line.strip()]
    if not rows:
        return ''
    head = ''.join('<th>' + inline(c, binomials, lang=lang) + '</th>' for c in rows[0])
    body = ''.join('<tr>' + ''.join('<td>' + inline(c, binomials, lang=lang) + '</td>' for c in row) + '</tr>' for row in rows[1:])
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def bullet_list(text, binomials, lang='he'):
    items = [re.sub(r'^\s*[-•]\s*', '', line) for line in str(text or '').splitlines() if line.strip()]
    return '<ul>' + ''.join('<li>' + inline(item, binomials, lang=lang) + '</li>' for item in items) + '</ul>' if items else ''


def pick(row, field, lang):
    """(text, translated) -- the block's text in `lang`; when only the other language has it, ('', False)."""
    mine = getattr(row, f'{field}_{lang}')
    other = getattr(row, f'{field}_{"he" if lang == "en" else "en"}')
    return mine, bool(mine or not other)


def render_blocks(article, lang, binomials):
    """[(html, figure-sample-or-None)] for the article's sections in `lang`, plus whether any was untranslated."""
    from .models import ArticleBlock
    Kind = ArticleBlock.Kind
    out, figure_no, untranslated = [], 0, False
    figure_word = 'Figure' if lang == 'en' else 'איור'
    for block in article.blocks.select_related('sample').all():
        text, ok = pick(block, 'text', lang)
        if block.kind == Kind.FIGURE:
            figure_no += 1
            sample = block.sample if block.sample_id and block.sample.image and not block.sample.deleted_at else None
            caption = f'<span class="figure-number">{figure_word} {figure_no}.</span> ' + (inline(text, binomials, lang=lang) if ok else '')
            image = (format_html('<img src="{}" alt="{}" loading="lazy">', reverse('observation-photo', args=[sample.pk]), plain(text))
                     if sample else format_html('<p class="untranslated">{}</p>', 'התמונה אינה זמינה.' if lang == 'he' else 'The photo is not available.'))
            if not ok:
                untranslated = True
                caption += str(format_html('<span class="untranslated">{}</span>', UNTRANSLATED[lang]))
            out.append((f'<figure id="figure-{figure_no}">{image}<figcaption>{caption}</figcaption></figure>', sample, figure_no))
            continue
        if not ok:
            untranslated = True
            out.append((str(format_html('<p class="untranslated">{}</p>', UNTRANSLATED[lang])), None, None))
            continue
        if block.kind == Kind.HEADING:
            html = '<h2>' + inline(text, binomials, lang=lang) + '</h2>'
        elif block.kind == Kind.SUBHEADING:
            html = '<h3>' + inline(text, binomials, lang=lang) + '</h3>'
        elif block.kind == Kind.TABLE:
            html = table(text, binomials, lang)
        elif block.kind == Kind.LIST:
            html = bullet_list(text, binomials, lang)
        elif block.kind == Kind.NOTICE:
            # the title in bold, opening the first paragraph: "<p><strong>הערה על …</strong> הפרט …</p>"
            title, _ = pick(block, 'title', lang)
            lead = f'<strong>{inline(title, binomials, lang=lang)}</strong> ' if title else ''
            html = '<div class="notice">' + paragraphs(text, binomials, lang, lead) + '</div>'
        else:
            html = paragraphs(text, binomials, lang)
        out.append((html, None, None))
    return out, untranslated


def reference_list(article, binomials):
    """The numbered references, left to right (they are in English in both languages)."""
    items = []
    for ref in article.references.all():
        link = format_html(' <a href="{0}" target="_blank" rel="noopener" dir="ltr">{0}</a>', ref.url) if ref.url else ''
        items.append(f'<li>{inline(ref.text, binomials)}{link}</li>')
    return '<ol class="refs" dir="ltr" lang="en">' + ''.join(items) + '</ol>' if items else ''
