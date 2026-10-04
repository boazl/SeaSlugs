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
