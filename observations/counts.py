"""How the site words a count of gallery cards.

A gallery card stands for one SpeciesArea: a species in an area (country + sea). The site calls
such a card an "observation" (תצפית) when it counts them, so the same species seen in two areas
is two observations but one species. Showing only one of the two numbers confused visitors, so
every count shows both: "30 מינים (50 תצפיות)", and in the small badges and chips "30 (50)".
dist/app.js builds the same strings for the gallery (countText / countCompact)."""


def species_count(areas):
    """How many distinct species the SpeciesArea rows `areas` cover."""
    return len({a.species_id for a in areas})


def count_text(species, observations, lang='he', full=False):
    """'30 מינים (50 תצפיות)' / '30 species (50 observations)' for headings and facts. When the two numbers are equal
    (every species is seen in one area only) it is just '30 מינים' -- `full` keeps both ('30 מינים (30 תצפיות)'),
    as the tooltips do."""
    if lang == 'en':
        sp = f'{species} species'
        ob = f"{observations} {'observation' if observations == 1 else 'observations'}"
    else:
        sp = 'מין אחד' if species == 1 else f'{species} מינים'
        ob = 'תצפית אחת' if observations == 1 else f'{observations} תצפיות'
    return sp if species == observations and not full else f'{sp} ({ob})'


def count_compact(species, observations):
    """'30 (50)' -- species, then observations in parentheses; one number when they are equal
    (each species is then seen in exactly one area, so the two counts say the same thing)."""
    return str(species) if species == observations else f'{species} ({observations})'
