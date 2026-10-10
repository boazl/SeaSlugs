"""A tiny, safe text markup for the editable home-page sections (see HomeText and the edit screen).

Everything is HTML-escaped first, then these are recognised:
  ~ text            small line above the title (hero only)
  # text            the page title (h1)
  ## text           a section heading (h2)
  1. text           numbered list (consecutive lines)
  - text            bullet list (consecutive lines)
  a blank line      ends a paragraph
  **bold**          bold text
  [text](address)   a link; the address may be a full https:// address, /path, #anchor, or one of the words
                    contribute (the add-observation page, or sign-up for a visitor that is not signed in),
                    gallery (jumps to the collection) and migrant (jumps to the collection and switches on
                    the migrant-species filter)
  [[text]]          the green "add observation" button
  {species} {observations} {israeli}   live numbers (species in the collection, observations, species
                    recorded in the Israeli Mediterranean)
"""
import re

from django.utils.html import escape
from django.utils.safestring import mark_safe

NUMBER_NAMES = ('species', 'observations', 'israeli')
_NUMBER = re.compile(r'\{(' + '|'.join(NUMBER_NAMES) + r')\}')
_BOLD = re.compile(r'\*\*(.+?)\*\*')
_BUTTON = re.compile(r'\[\[(.+?)\]\]')
_LINK = re.compile(r'\[([^\]]+)\]\(([^)\s]+)\)')
_NUMBERED = re.compile(r'^\d+\.\s+(.*)$')
_BULLET = re.compile(r'^[-*]\s+(.*)$')


def _address(raw, contribute_url):
    """(href, extra attributes) for a link address; anything unrecognised becomes a harmless '#'."""
    word = raw.lower()
    if word == 'contribute':
        return contribute_url, ''
    if word == 'gallery':
        return '#collectionTitle', ''
    if word == 'migrant':
        return '#collectionTitle', ' data-home-action="migrant"'
    if re.match(r'^(https?://|mailto:|/|#)', raw):
        return raw, ''
    return '#', ''


def _inline(text, numbers, contribute_url):
    text = _NUMBER.sub(lambda m: str(numbers.get(m.group(1), '')), text)
    text = escape(text)
    text = _BUTTON.sub(lambda m: f'<a class="btn btn-primary" href="{contribute_url}">{m.group(1)}</a>', text)

    def link(match):
        href, extra = _address(match.group(2).replace('&amp;', '&'), contribute_url)
        return f'<a href="{escape(href)}"{extra}>{match.group(1)}</a>'
    text = _LINK.sub(link, text)
    return _BOLD.sub(r'<strong>\1</strong>', text)


def render_markup(text, numbers, contribute_url, inline=False, paragraph_class=''):
    text = (text or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    if inline:
        return mark_safe(_inline(' '.join(text.split('\n')), numbers, contribute_url))
    out, paragraph, items, kind = [], [], [], None
    attrs = f' class="{paragraph_class}"' if paragraph_class else ''

    def flush():
        nonlocal paragraph, items, kind
        if paragraph:
            out.append(f'<p{attrs}>{_inline(" ".join(paragraph), numbers, contribute_url)}</p>')
        if items:
            tag = 'ol' if kind == 'ol' else 'ul'
            out.append(f'<{tag} class="steps">' + ''.join(f'<li>{_inline(i, numbers, contribute_url)}</li>' for i in items) + f'</{tag}>')
        paragraph, items, kind = [], [], None

    for line in text.split('\n'):
        line = line.strip()
        if not line:
            flush()
        elif line.startswith('## '):
            flush(); out.append(f'<h2>{_inline(line[3:], numbers, contribute_url)}</h2>')
        elif line.startswith('# '):
            flush(); out.append(f'<h1>{_inline(line[2:], numbers, contribute_url)}</h1>')
        elif line.startswith('~ '):
            flush(); out.append(f'<p class="eyebrow">{_inline(line[2:], numbers, contribute_url)}</p>')
        elif _NUMBERED.match(line) or _BULLET.match(line):
            want = 'ol' if _NUMBERED.match(line) else 'ul'
            if paragraph or (kind and kind != want):
                flush()
            kind = want
            items.append((_NUMBERED.match(line) or _BULLET.match(line)).group(1))
        else:
            if items:
                flush()
            paragraph.append(line)
    flush()
    return mark_safe('\n'.join(out))
