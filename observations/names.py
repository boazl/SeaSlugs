"""Scientific names in italics: genus and species epithet are italic, everything else
(the qualifier cf./aff., "sp. 7", a variant letter, the author, the life stage) is roman.
dist/app.js has the same rule (setLatinName) for the gallery cards -- keep the two in step."""
import re
from django.utils.html import escape
from django.utils.safestring import mark_safe

QUALIFIERS = {'cf.', 'aff.', 'cf', 'aff'}
GENUS_RE = re.compile(r"^[A-Z][a-z]+$")
EPITHET_RE = re.compile(r"^[a-z][a-z-]+$")


def italic_flags(tokens):
    """One bool per token: True when the token belongs to the italic part of the name."""
    flags = [False] * len(tokens)
    if not tokens or not GENUS_RE.match(tokens[0]): return flags
    flags[0] = True
    i = 1
    if len(tokens) > 1 and tokens[1].lower() in QUALIFIERS: i = 2
    if i < len(tokens) and EPITHET_RE.match(tokens[i]) and not re.match(r'^spp?$', tokens[i]): flags[i] = True
    return flags


def name_html(text):
    """HTML for a species name with the genus and epithet in <i>."""
    tokens = str(text or '').split()
    flags = italic_flags(tokens)
    out, run = [], []

    def flush():
        if run:
            out.append('<i>' + ' '.join(run) + '</i>')
            run.clear()
    for token, ital in zip(tokens, flags):
        if ital: run.append(escape(token))
        else:
            flush()
            out.append(escape(token))
    flush()
    return mark_safe(' '.join(out))


# A binomial inside running text: a genus (or its initial, "P.") then an epithet, optionally with cf./aff. between.
_TEXT_NAME_RE = re.compile(r'\b([A-Z][a-z]+|[A-Z]\.)(\s+(?:cf\.|aff\.))?\s+([a-z][a-z-]+)\b')


def known_binomials():
    """{(genus, epithet)} of every catalog species with a plain epithet -- the names italicize_names recognises."""
    from .models import Species
    pairs = set()
    for genus, epithet in Species.objects.values_list('genus', 'species'):
        genus, epithet = (genus or '').strip(), (epithet or '').strip()
        if GENUS_RE.match(genus) and EPITHET_RE.match(epithet):
            pairs.add((genus, epithet))
    return pairs


def italicize_names(text, binomials=None):
    """Escaped HTML of free text (a page note, an article title) with each scientific name in it set the way
    name_html sets a name: genus and epithet in <i>, a cf./aff. between them roman. Only names of catalog
    species are touched -- in full ("Phyllidia ocellata") or with the genus abbreviated ("P. cf. ocellata") --
    so ordinary words that merely look like a binomial ("This species") stay roman."""
    if binomials is None:
        binomials = known_binomials()
    initials = {(genus[0] + '.', epithet) for genus, epithet in binomials}
    source = str(text or '')
    out, pos = [], 0
    for match in _TEXT_NAME_RE.finditer(source):
        genus, qualifier, epithet = match.group(1), match.group(2) or '', match.group(3)
        if (genus, epithet) not in binomials and (genus, epithet) not in initials:
            continue
        out.append(escape(source[pos:match.start()]))
        if qualifier:
            out.append(f'<i>{escape(genus)}</i>{escape(qualifier)} <i>{escape(epithet)}</i>')
        else:
            out.append(f'<i>{escape(genus)} {escape(epithet)}</i>')
        pos = match.end()
    out.append(escape(source[pos:]))
    return mark_safe(''.join(out))
