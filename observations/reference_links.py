"""Reference links for the species table (admin only -- never shown on the public site).

For every species with a full binomial name this finds a page where one can glance at what the
species looks like: an iNaturalist taxon page when iNaturalist holds a photo of that exact
species, otherwise the species' WoRMS page. Species without a full name ("Chromodoris sp.",
"Hypselodoris cf. bullockii") get nothing -- a picture of the wrong animal is worse than none.

This module holds the pure matching logic and thin HTTP helpers; the management command
fill_reference_links drives them and keeps a resumable cache.
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

WORMS_BATCH = 50
WORMS_API = 'https://www.marinespecies.org/rest/AphiaRecordsByNames'
INAT_API = 'https://api.inaturalist.org/v1/taxa'
USER_AGENT = 'seaslugs.org.il reference-link builder (boazl@savion.huji.ac.il)'

_GENUS = re.compile(r'^[A-Z][a-z]+$')
_EPITHET = re.compile(r'^[a-z][a-z-]+$')
_NOT_AN_EPITHET = {'sp', 'spp', 'cf', 'aff'}


def is_full_name(genus, species):
    """A real binomial: a clean genus and a clean epithet (no 'sp.', 'sp. 7', 'cf. x')."""
    genus, species = (genus or '').strip(), (species or '').strip()
    return bool(_GENUS.match(genus) and _EPITHET.match(species) and species not in _NOT_AN_EPITHET)


def candidate_names(species):
    """The names to look up for a Species row: its own binomial first, then the accepted
    name when that differs. Empty when the species has no full name of its own."""
    if not is_full_name(species.genus, species.species):
        return []
    names = [f'{species.genus.strip()} {species.species.strip()}']
    if is_full_name(species.accepted_genus, species.accepted_species):
        accepted = f'{species.accepted_genus.strip()} {species.accepted_species.strip()}'
        if accepted != names[0]:
            names.append(accepted)
    return names


def worms_url(aphia_id):
    return f'https://www.marinespecies.org/aphia.php?p=taxdetails&id={int(aphia_id)}'


def inat_url(taxon_id):
    return f'https://www.inaturalist.org/taxa/{int(taxon_id)}'


def parse_worms(records, name):
    """records: the list of Aphia records WoRMS returned for one name (None / [] if unknown).
    Returns the AphiaID of the accepted record for that name, or None. A synonym resolves to
    the accepted taxon (valid_AphiaID), so the link always opens the current name's page."""
    wanted = name.lower()
    best = None
    for rec in records or []:
        if not isinstance(rec, dict) or (rec.get('scientificname') or '').lower() != wanted:
            continue
        if rec.get('rank') not in (None, 'Species'):
            continue
        target = rec.get('valid_AphiaID') or rec.get('AphiaID')
        if not target:
            continue
        if rec.get('status') == 'accepted':
            return target
        best = best or target
    return best


def parse_inat(results, names):
    """results: the 'results' list of an iNaturalist /v1/taxa query. Returns the taxon id of a
    species-rank, active taxon whose name is one of `names` AND that has a photo; else None."""
    wanted = {n.lower() for n in names}
    for taxon in results or []:
        if taxon.get('rank') != 'species' or taxon.get('is_active') is False:
            continue
        if (taxon.get('name') or '').lower() in wanted and taxon.get('default_photo'):
            return taxon.get('id')
    return None


def best_link(worms_id, inat_id):
    """The user's rule: a picture page when one exists, otherwise WoRMS, otherwise nothing."""
    if inat_id:
        return inat_url(inat_id)
    if worms_id:
        return worms_url(worms_id)
    return ''


def link_kind(url):
    """'photo' / 'worms' / '' -- what an existing link points to (for the admin column)."""
    if 'inaturalist.org' in (url or ''):
        return 'photo'
    if 'marinespecies.org' in (url or ''):
        return 'worms'
    return ''


# -- HTTP helpers (the command and the tests can inject replacements) ----------------------

def get_json(url, retries=4, pause=5.0):
    last = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read().decode('utf-8')
                return json.loads(body) if body.strip() else None
        except urllib.error.HTTPError as error:
            if error.code == 204:       # WoRMS: nothing found
                return None
            last = error
            time.sleep(pause * (attempt + 1) * (6 if error.code == 429 else 1))
        except Exception as error:      # network hiccup: wait and retry
            last = error
            time.sleep(pause * (attempt + 1))
    raise last


def fetch_worms(names):
    """{name: aphia_id or None} for up to WORMS_BATCH names in one request."""
    query = '&'.join('scientificnames[]=' + urllib.parse.quote(n) for n in names) + '&marine_only=false'
    data = get_json(f'{WORMS_API}?{query}')
    out = {}
    for name, records in zip(names, data or [[] for _ in names]):
        out[name] = parse_worms(records, name)
    return out


def fetch_inat(names):
    """iNaturalist taxon id (with a photo) for the first of `names` that has one, else None."""
    for name in names:
        url = f'{INAT_API}?' + urllib.parse.urlencode({'q': name, 'rank': 'species', 'per_page': 5, 'is_active': 'true'})
        found = parse_inat((get_json(url) or {}).get('results'), names)
        if found:
            return found
    return None
