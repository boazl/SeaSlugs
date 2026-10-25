"""How the site words a count of gallery cards.

A gallery card is one SpeciesArea: a species in an area (country + sea), which the site calls an "observation".
The same species seen in two areas is two cards but one species, so every counter shows the number of distinct
species ("30 מינים"); only the gallery's "All areas" button also says how many observations they are.
dist/app.js builds the same strings (countText / observationsText)."""


def species_count(areas):
    """How many distinct species the SpeciesArea rows `areas` cover."""
    return len({a.species_id for a in areas})


def count_text(species, lang='he'):
    """'30 מינים' / '30 species' ('מין אחד' for one)."""
    if lang == 'en':
        return f'{species} species'
    return 'מין אחד' if species == 1 else f'{species} מינים'


def observations_text(species, observations, lang='he'):
    """'266 מינים ב-301 תצפיות' / '266 species in 301 observations'."""
    if lang == 'en':
        return f"{species} species in {observations} {'observation' if observations == 1 else 'observations'}"
    return f"{count_text(species)} ב-{'תצפית אחת' if observations == 1 else f'{observations} תצפיות'}"
