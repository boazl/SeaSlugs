"""Which publications of the library a species is linked to by its sources (Species.articles), so they show in the
species page's articles section and count as used on the article-files page -- the way the papers that describe
species are linked (migration 0114):

  - the publication that names an undescribed species: the one whose short reference (Article.short_ref) is the
    species' name source (Species.name_source) -- for the gallery's "sp. N" the 2nd edition of Gosliner, Valdés &
    Behrens, which named every one of them (the labels on the photos say 2018);
  - every publication that has a name for the species (SpeciesPublicationName): e.g. the 3rd edition, which shows
    the same animal as Marioniopsis sp. 11 -- its link on the site says so.

A citation in a species' texts does not link (the identification texts quote the 3rd edition for species named by the
2nd). Links are only ever added here, never removed (the manager may also pick a publication by hand).
"""


def cited_articles(species, Article):
    """The publications the species is linked to by its sources (see the module's docstring)."""
    found = []
    source = (species.name_source or '').strip()
    if source:
        found += list(Article.objects.filter(short_ref=source))
    found += [n.article for n in species.publication_names.select_related('article')]
    return found


def link_species(species, Article=None):
    """Adds to the species the publications it cites (see the module's docstring); returns those added."""
    if Article is None:
        from .models import Article
    have = set(species.articles.values_list('pk', flat=True))
    added = []
    for article in cited_articles(species, Article):
        if article.pk not in have:
            have.add(article.pk)
            added.append(article)
    if added:
        species.articles.add(*added)
    return added


def publication_names(species, lang):
    """{article pk: {'name', 'same' (the site's own name), 'pages' (as text in `lang`)}} -- how the species appears in
    each publication that has a name for it."""
    found = {}
    for entry in species.publication_names.all():
        pages = entry.pages.strip()
        if pages:
            pages = f'עמ׳ {pages}' if lang == 'he' else f"{'pp.' if '-' in pages else 'p.'} {pages}"
        found[entry.article_id] = {'name': entry.name.strip(), 'pages': pages,
                                   'same': entry.name.strip() == species.scientific_name.strip()}
    return found
