"""Template tags for the page links of citations of Gosliner et al. (observations/book_links.py)."""
from django import template

from observations.book_links import linked_citations

register = template.Library()


@register.simple_tag(takes_context=True)
def book_cited(context, text, lang='he'):
    """The text with line breaks, plus PDF page links after book page references for a superuser on the Mac."""
    request = context.get('request')
    return linked_citations(text, getattr(request, 'user', None), lang)
