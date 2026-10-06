'use strict';
const catalog = window.SEASLUGS || {};
const speciesList = catalog.species || [];
const collectionsList = catalog.collections || [];
const areaLabelsData = catalog.areas || {};
const regionLabelsData = catalog.regions || {};
const siteLabelsData = catalog.sites || {};
const tripLabelsData = catalog.trips || {};
const taxaData = catalog.taxa || { orders: {}, families: {}, genera: {} };

// How many area-rows (SpeciesArea rows -- one catalog species entry per area a species
// was observed in) each species_id has, computed once up front -- backs the "species from
// multiple areas" pseudo-area button in the area filter (see matchesAreaFilter below).
const speciesAreaCountById = new Map();
for (const sp of speciesList) speciesAreaCountById.set(sp.species_id, (speciesAreaCountById.get(sp.species_id) || 0) + 1);

let language = 'he';

const grid = document.querySelector('#grid');
const search = document.querySelector('#search');
const dialog = document.querySelector('#player');

const state = {
    area: 'all',
    regions: new Set(),
    sites: new Set(),
    photographers: new Set(),
    years: new Set(),
    // 'multi' when the "species with several observations" filter is on (a Set so the
    // sidebar's checkbox helper can drive it like the other checkbox groups).
    observations: new Set(),
    order: 'all',
    subOrder: 'all',
    superfamily: 'all',
    family: 'all',
    genus: 'all',
    collection: null,
    sort: 'taxonomic',
    // True once the visitor picks a sort by hand; until then the sort follows the area
    // (the migrant-species view defaults to observation year, every other view to taxonomic).
    sortChosen: false,
};
const multiObsOn = () => state.observations.has('multi');
// The sort a view falls back to until the visitor picks one by hand: by number of
// observations under the several-observations filter, by year under the migrant
// filter, taxonomic otherwise.
function defaultSort() {
    if (multiObsOn()) return 'count';
    return state.area === 'migrant' ? 'year' : 'taxonomic';
}

let opener = null;

const normalize = s => s.normalize('NFKC').toLocaleLowerCase().replace(/\s+/g, ' ').trim();

function areaLabelFor(key) {
    const e = areaLabelsData[key];
    if (!e) return '';
    return language === 'en' ? (e.label_en || e.label) : e.label;
}
function labelFor(id, dict) {
    const e = dict[id];
    if (!e) return '';
    return language === 'en' ? (e.label_en || e.label) : e.label;
}
// A sample/collection's credited photographer, in the page's current language: a
// registered user's name resolves per-language server-side (photographer_he/
// photographer_en in catalog.js -- see photographer_display_name in observations/
// models.py); a guest photographer with no account has no per-language variant, so
// entry.photographer (the raw, language-invariant credit text) is the fallback.
function photographerLabel(entry) {
    return (language === 'he' ? entry.photographer_he : entry.photographer_en) || entry.photographer;
}

const collectionStatus = document.createElement('div');
collectionStatus.className = 'collection-selection';
grid.before(collectionStatus);

function updateCollectionStatus() {
    collectionStatus.replaceChildren();
    if (!state.collection) return;
    const c = collectionsList.find(x => String(x.trip_id) === state.collection);
    const label = document.createElement('span');
    const description = c ? collectionTitle(c) : (labelFor(state.collection, tripLabelsData) || '');
    label.textContent = (language === 'he' ? 'מינים באוסף: ' : 'Species in collection: ') + description;
    const back = document.createElement('button');
    back.type = 'button';
    back.textContent = language === 'he' ? 'חזרה לכל הגלריה' : 'Back to full gallery';
    back.addEventListener('click', () => { state.collection = null; render(); });
    collectionStatus.append(label, back);
}

// ---- option scoping ----

// The area filter has two pseudo-area values alongside real country+sea keys ('all' plus
// one per SpeciesArea.country/sea pair): 'multi-area' (species observed in more than one
// area -- more than one SpeciesArea row) and 'migrant' (Species.is_migrant). Every place
// that used to compare sp.area === area goes through this instead, so those two behave
// exactly like picking a real area everywhere else in the sidebar/grid.
function matchesAreaFilter(sp, area) {
    if (area === 'all') return true;
    if (area === 'multi-area') return speciesAreaCountById.get(sp.species_id) > 1;
    if (area === 'migrant') return !!sp.is_migrant;
    return sp.area === area;
}
// Collections (dive-trip videos) aren't tied to one species, so "multiple areas" and
// "migrant" don't apply to them -- neither pseudo-area ever matches a collection.
function collectionMatchesArea(c, area) {
    if (area === 'all') return true;
    if (area === 'multi-area' || area === 'migrant') return false;
    return c.area === area;
}

function optionsForArea(area) {
    // Dive site and year are narrowed by the currently selected dive region(s) (a site/year
    // only shows -- and is only counted -- when it belongs to one of the checked regions), the
    // same way area narrows everything here; region/photographer/trip stay area-scoped only,
    // since narrowing those wasn't asked for and would remove options the user might still
    // want to combine across regions.
    const regionIds = new Set(), siteIds = new Set(), photographers = new Set(), trips = new Set(), years = new Set();
    for (const sp of speciesList) {
        if (!matchesAreaFilter(sp, area)) continue;
        for (const sm of sp.samples) {
            regionIds.add(sm.region);
            const inSelectedRegions = !state.regions.size || state.regions.has(sm.region);
            if (sm.site && inSelectedRegions) siteIds.add(sm.site);
            if (sm.photographer) photographers.add(sm.photographer);
            if (sm.trip_id != null) trips.add(String(sm.trip_id));
            if (sm.year != null && inSelectedRegions) years.add(String(sm.year));
        }
    }
    for (const c of collectionsList) {
        if (!collectionMatchesArea(c, area)) continue;
        regionIds.add(c.region);
        if (c.photographer) photographers.add(c.photographer);
        if (c.trip_id != null) trips.add(String(c.trip_id));
        if (c.year != null && (!state.regions.size || state.regions.has(c.region))) years.add(String(c.year));
    }
    return { regionIds, siteIds, photographers, trips, years };
}
function regionCount(area, id) {
    return speciesList.filter(sp => matchesAreaFilter(sp, area) && sp.samples.some(sm => sm.region === id)).length;
}
function siteCount(area, id) {
    return speciesList.filter(sp => matchesAreaFilter(sp, area) && sp.samples.some(sm => sm.site === id && (!state.regions.size || state.regions.has(sm.region)))).length;
}
function tripCount(area, id) {
    return speciesList.filter(sp => matchesAreaFilter(sp, area) && sp.samples.some(sm => String(sm.trip_id) === id)).length;
}
function photographerSpeciesCount(area, name) {
    let n = 0;
    for (const sp of speciesList) { if (!matchesAreaFilter(sp, area)) continue; if (sp.samples.some(sm => sm.photographer === name)) n++; }
    return n;
}
function photographerCollectionCount(area, name) {
    let n = 0;
    for (const c of collectionsList) { if (!collectionMatchesArea(c, area)) continue; if (c.photographer === name) n++; }
    return n;
}
function yearCount(area, year) {
    let n = 0;
    for (const sp of speciesList) { if (!matchesAreaFilter(sp, area)) continue; if (sp.samples.some(sm => String(sm.year) === year && (!state.regions.size || state.regions.has(sm.region)))) n++; }
    for (const c of collectionsList) { if (!collectionMatchesArea(c, area)) continue; if (String(c.year) === year && (!state.regions.size || state.regions.has(c.region))) n++; }
    return n;
}
// Each of orders/subOrders/superfamilies/families is a Map of value -> species count,
// scoped by area plus every ANCESTOR level already selected (not by a selection at its
// own level -- these are the alternatives that would appear in that level's own <select>,
// so a value can't scope itself). ordersUnclassified etc. count species that have no
// value at all for that level, within that same ancestor scope -- the "unclassified" row
// (value '') added in fillTaxonSelect below, e.g. a species with no superfamily still has
// an order and (maybe) a suborder, so it's scoped by those exactly like a real superfamily
// value would be, and its "unclassified" count moves with the order/suborder selection.
function taxonomyOptions(area, order, subOrder, superfamily, family) {
    const orders = new Map(), subOrders = new Map(), superfamilies = new Map(), families = new Map(), genera = new Map();
    let ordersUnclassified = 0, subOrdersUnclassified = 0, superfamiliesUnclassified = 0, familiesUnclassified = 0;
    const bump = (map, key) => map.set(key, (map.get(key) || 0) + 1);
    for (const sp of speciesList) {
        if (!matchesAreaFilter(sp, area)) continue;
        if (sp.order) bump(orders, sp.order); else ordersUnclassified++;
        if (order !== 'all' && sp.order !== order) continue;
        if (sp.sub_order) bump(subOrders, sp.sub_order); else subOrdersUnclassified++;
        if (subOrder !== 'all' && sp.sub_order !== subOrder) continue;
        if (sp.superfamily) bump(superfamilies, sp.superfamily); else superfamiliesUnclassified++;
        if (superfamily !== 'all' && sp.superfamily !== superfamily) continue;
        if (sp.family) bump(families, sp.family); else familiesUnclassified++;
        if (family !== 'all' && sp.family !== family) continue;
        if (sp.genus) bump(genera, sp.genus);
    }
    return { orders, subOrders, superfamilies, families, genera, ordersUnclassified, subOrdersUnclassified, superfamiliesUnclassified, familiesUnclassified };
}

// ---- sidebar rendering ----

function areaSpeciesCount(key) {
    return speciesList.filter(sp => matchesAreaFilter(sp, key)).length;
}
function renderAreaFilters() {
    const container = document.querySelector('#areaFilters');
    container.replaceChildren();
    // The two pseudo-area buttons (multi-area, migrant -- see matchesAreaFilter) sit
    // above the real geographic areas, right after "All areas".
    const entries = [
        ['all', language === 'he' ? 'כל האזורים' : 'All areas'],
        ['multi-area', language === 'he' ? 'מינים ממספר אזורים' : 'Species from multiple areas'],
        ['migrant', language === 'he' ? 'מינים מהגרים' : 'Mediterranean Exotic species'],
        ...Object.keys(areaLabelsData).map(k => [k, areaLabelFor(k)]),
    ];
    for (const [key, label] of entries) {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'filter';
        b.dataset.area = key;
        b.append(label);
        const count = document.createElement('small');
        count.textContent = areaSpeciesCount(key);
        b.append(count);
        const active = state.area === key;
        b.classList.toggle('active', active);
        b.setAttribute('aria-pressed', String(active));
        b.addEventListener('click', () => {
            if (state.area === key) return;
            state.area = key;
            state.regions.clear(); state.sites.clear(); state.photographers.clear(); state.years.clear();
            state.order = 'all'; state.subOrder = 'all'; state.superfamily = 'all'; state.family = 'all'; state.genus = 'all';
            if (!state.sortChosen) state.sort = defaultSort();
            syncSortControl();
            renderSidebar(); render();
        });
        container.append(b);
    }
}
function renderCheckboxGroup(container, entries, selectedSet, afterChange = render) {
    container.replaceChildren();
    for (const [value, label, count] of entries) {
        const row = document.createElement('label');
        row.className = 'filter-check';
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.value = value;
        input.checked = selectedSet.has(value);
        input.addEventListener('change', () => {
            if (input.checked) selectedSet.add(value); else selectedSet.delete(value);
            afterChange();
        });
        const text = document.createElement('span');
        text.textContent = label;
        row.append(input, text);
        if (count != null) {
            const small = document.createElement('small');
            small.textContent = count;
            row.append(small);
        }
        container.append(row);
    }
}
function fillLabeledSelect(select, entries, current, allLabel) {
    select.replaceChildren();
    const allOpt = document.createElement('option');
    allOpt.value = 'all';
    allOpt.textContent = allLabel;
    select.append(allOpt);
    for (const [value, label] of entries) {
        const opt = document.createElement('option');
        opt.value = value;
        opt.textContent = label;
        select.append(opt);
    }
    select.value = entries.some(([v]) => v === current) ? current : 'all';
}
// Order/suborder/superfamily/family selects: 'all' first, then an "unclassified" option
// (value '', the same falsy value Species.order/sub_order/superfamily/family already use
// for "not set" -- see resolve_taxon_chain in config/views.py) when at least one species
// in scope has no value at this level, then every real value sorted alphabetically -- each
// non-'all' option's label carries its species count in parens, same convention the trip
// select already uses.
function fillTaxonSelect(select, counts, unclassifiedCount, current, allLabel, unclassifiedLabel) {
    select.replaceChildren();
    const allOpt = document.createElement('option');
    allOpt.value = 'all';
    allOpt.textContent = allLabel;
    select.append(allOpt);
    const validValues = new Set(['all']);
    if (unclassifiedCount > 0) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = `${unclassifiedLabel} (${unclassifiedCount})`;
        select.append(opt);
        validValues.add('');
    }
    for (const v of [...counts.keys()].sort((a, b) => a.localeCompare(b))) {
        const opt = document.createElement('option');
        opt.value = v;
        opt.textContent = `${v} (${counts.get(v)})`;
        select.append(opt);
        validValues.add(v);
    }
    select.value = validValues.has(current) ? current : 'all';
}
function renderTaxonomySelects() {
    const unclassifiedLabel = language === 'he' ? 'ללא סיווג' : 'Unclassified';
    const area = state.area;
    const t1 = taxonomyOptions(area, 'all', 'all', 'all', 'all');
    const orderSelect = document.querySelector('#orderSelect');
    fillTaxonSelect(orderSelect, t1.orders, t1.ordersUnclassified, state.order, language === 'he' ? 'כל הסדרות' : 'All orders', unclassifiedLabel);
    if (orderSelect.value !== state.order) state.order = 'all';

    const t2 = taxonomyOptions(area, state.order, 'all', 'all', 'all');
    const subOrderGroup = document.querySelector('#subOrderGroup');
    const subOrderSelect = document.querySelector('#subOrderSelect');
    if (t2.subOrders.size || t2.subOrdersUnclassified) {
        subOrderGroup.hidden = false;
        fillTaxonSelect(subOrderSelect, t2.subOrders, t2.subOrdersUnclassified, state.subOrder, language === 'he' ? 'כל תתי-הסדרה' : 'All suborders', unclassifiedLabel);
        if (subOrderSelect.value !== state.subOrder) state.subOrder = 'all';
    } else {
        subOrderGroup.hidden = true;
        state.subOrder = 'all';
    }

    const t2b = taxonomyOptions(area, state.order, state.subOrder, 'all', 'all');
    const superfamilyGroup = document.querySelector('#superfamilyGroup');
    const superfamilySelect = document.querySelector('#superfamilySelect');
    if (t2b.superfamilies.size || t2b.superfamiliesUnclassified) {
        superfamilyGroup.hidden = false;
        fillTaxonSelect(superfamilySelect, t2b.superfamilies, t2b.superfamiliesUnclassified, state.superfamily, language === 'he' ? 'כל העל-משפחות' : 'All superfamilies', unclassifiedLabel);
        if (superfamilySelect.value !== state.superfamily) state.superfamily = 'all';
    } else {
        superfamilyGroup.hidden = true;
        state.superfamily = 'all';
    }

    const t3 = taxonomyOptions(area, state.order, state.subOrder, state.superfamily, 'all');
    const familySelect = document.querySelector('#familySelect');
    fillTaxonSelect(familySelect, t3.families, t3.familiesUnclassified, state.family, language === 'he' ? 'כל המשפחות' : 'All families', unclassifiedLabel);
    if (familySelect.value !== state.family) state.family = 'all';
    const t4 = taxonomyOptions(area, state.order, state.subOrder, state.superfamily, state.family);
    const genusSelect = document.querySelector('#genusSelect');
    fillTaxonSelect(genusSelect, t4.genera, 0, state.genus, language === 'he' ? 'כל הסוגים' : 'All genera', '');
    if (genusSelect.value !== state.genus) state.genus = 'all';
}
function renderSidebar() {
    renderAreaFilters();
    const area = state.area;
    const opts = optionsForArea(area);
    // A site or year selected while a now-deselected region was in effect can fall outside
    // the narrowed options below -- drop it rather than leaving an invisible, unclearable
    // filter in effect (the same problem the taxonomy selects guard against just below, for
    // a single dropdown value instead of a checkbox Set).
    for (const v of [...state.sites]) if (!opts.siteIds.has(v)) state.sites.delete(v);
    for (const v of [...state.years]) if (!opts.years.has(v)) state.years.delete(v);
    const regionEntries = [...opts.regionIds]
        .map(id => [id, labelFor(id, regionLabelsData), regionCount(area, id)])
        .sort((a, b) => a[1].localeCompare(b[1], language === 'he' ? 'he' : 'en'));
    renderCheckboxGroup(document.querySelector('#regionOptions'), regionEntries, state.regions, () => { renderSidebar(); render(); });
    const multiCount = speciesList.filter(sp => matchesAreaFilter(sp, area) && sp.samples.length > 1).length;
    renderCheckboxGroup(document.querySelector('#observationOptions'),
        [['multi', language === 'he' ? 'מינים עם מספר תצפיות' : 'Species with several observations', multiCount]],
        state.observations, () => {
            if (!state.sortChosen || (!multiObsOn() && state.sort === 'count')) { state.sort = defaultSort(); state.sortChosen = false; }
            syncSortControl(); render();
        });
    const siteEntries = [...opts.siteIds]
        .map(id => [id, labelFor(id, siteLabelsData), siteCount(area, id)])
        .sort((a, b) => a[1].localeCompare(b[1], language === 'he' ? 'he' : 'en'));
    renderCheckboxGroup(document.querySelector('#siteOptions'), siteEntries, state.sites);
    // Each photographer gets two count lines under the checkbox: species cards, then collections.
    const photographerEntries = [...opts.photographers]
        .map(name => [name, name, null])
        .sort((a, b) => a[1].localeCompare(b[1]));
    const photographerBox = document.querySelector('#photographerOptions');
    renderCheckboxGroup(photographerBox, photographerEntries, state.photographers);
    for (const row of [...photographerBox.querySelectorAll('.filter-check')]) {
        const name = row.querySelector('input').value;
        const rows = [
            [language === 'he' ? 'מינים' : 'Species', photographerSpeciesCount(area, name)],
            [language === 'he' ? 'אוספים' : 'Collections', photographerCollectionCount(area, name)],
        ];
        let anchor = row;
        for (const [label, count] of rows) {
            const sub = document.createElement('div');
            sub.className = 'filter-sub';
            const text = document.createElement('span');
            text.textContent = label;
            const small = document.createElement('small');
            small.textContent = count;
            sub.append(text, small);
            anchor.after(sub);
            anchor = sub;
        }
    }
    const yearEntries = [...opts.years]
        .map(year => [year, year, yearCount(area, year)])
        .sort((a, b) => Number(b[0]) - Number(a[0]));
    renderCheckboxGroup(document.querySelector('#yearOptions'), yearEntries, state.years);
    const tripEntries = [...opts.trips]
        .map(id => {
            const label = labelFor(id, tripLabelsData) || id;
            const count = tripLabelsData[id] && tripLabelsData[id].species_count;
            // Sortable text comes first, the count in parens after -- same convention as a
            // checkbox row's separate count <small>, just inlined since <option> text can't
            // contain child elements.
            return [id, count ? `${label} (${count})` : label];
        })
        .sort((a, b) => a[1].localeCompare(b[1], language === 'he' ? 'he' : 'en'));
    const tripSelect = document.querySelector('#tripSelect');
    fillLabeledSelect(tripSelect, tripEntries, state.collection || 'all', language === 'he' ? 'כל המסעות' : 'All trips');
    if (tripSelect.value === 'all') state.collection = null;
    renderTaxonomySelects();
}

// ---- matching / search ----

function sampleMatchesFilters(sm) {
    if (state.regions.size && !state.regions.has(sm.region)) return false;
    if (state.sites.size && !(sm.site && state.sites.has(sm.site))) return false;
    if (state.photographers.size && !state.photographers.has(sm.photographer)) return false;
    if (state.years.size && !state.years.has(String(sm.year))) return false;
    return true;
}
// When a dive-trip collection and/or dive region/site/photographer filters are active,
// narrow a species' samples to the one(s) relevant to the current view -- e.g. a species
// observed on several trips or by several photographers should show/play the sample that
// actually matches what's selected, not just its overall defining sample. Each step only
// narrows if that wouldn't empty the pool (a species can qualify for the view through two
// different samples, one per criterion). Returns null when no such filter is active at all,
// so callers fall back to the species' own defining sample as before.
function scopedSamples(sp) {
    if (!(state.collection || state.regions.size || state.sites.size || state.photographers.size || state.years.size)) return null;
    let pool = sp.samples;
    if (state.collection) {
        const byTrip = pool.filter(sm => String(sm.trip_id) === state.collection);
        if (byTrip.length) pool = byTrip;
    }
    if (state.regions.size || state.sites.size || state.photographers.size || state.years.size) {
        const byGeo = pool.filter(sampleMatchesFilters);
        if (byGeo.length) pool = byGeo;
    }
    return pool;
}
function speciesSearchText(sp) {
    const parts = [sp.title, sp.name_he, sp.name_en, sp.genus, sp.family, sp.superfamily, sp.order, areaLabelsData[sp.area]?.label, areaLabelsData[sp.area]?.label_en];
    for (const sm of sp.samples) {
        const r = regionLabelsData[sm.region];
        if (r) parts.push(r.label, r.label_en);
        const s = sm.site ? siteLabelsData[sm.site] : null;
        if (s) parts.push(s.label, s.label_en);
        parts.push(sm.photographer);
    }
    return normalize(parts.filter(Boolean).join(' '));
}
function speciesMatches(sp, q) {
    if (state.collection && !sp.samples.some(sm => String(sm.trip_id) === state.collection)) return false;
    if (!matchesAreaFilter(sp, state.area)) return false;
    if (state.order !== 'all' && sp.order !== state.order) return false;
    if (state.subOrder !== 'all' && sp.sub_order !== state.subOrder) return false;
    if (state.superfamily !== 'all' && sp.superfamily !== state.superfamily) return false;
    if (state.family !== 'all' && sp.family !== state.family) return false;
    if (state.genus !== 'all' && sp.genus !== state.genus) return false;
    if ((state.regions.size || state.sites.size || state.photographers.size || state.years.size) && !sp.samples.some(sampleMatchesFilters)) return false;
    if (multiObsOn() && observationCount(sp) < 2) return false;
    if (q && !(searchByName ? speciesNameMatches(sp, q) : speciesSearchText(sp).includes(q))) return false;
    return true;
}
// Name-first search: when what's typed starts a word of some species' name (scientific,
// genus, family, order or common name), only name matches count -- so "ph" lists the
// Phyllidia, Phestilla... species rather than every species from the Philippines. When
// no name matches, the search falls back to everything (places, photographers...).
let searchByName = false;
function speciesNameText(sp) {
    return normalize([sp.title, sp.genus, sp.family, sp.superfamily, sp.order, sp.name_he, sp.name_en].filter(Boolean).join(' '));
}
function speciesNameMatches(sp, q) {
    const text = speciesNameText(sp);
    return text.startsWith(q) || text.includes(' ' + q);
}
// How many observations a species card stands for in the current view (the same number
// as its count badge): the samples matching the active filters, or all of them.
function observationCount(sp) {
    return (scopedSamples(sp) || sp.samples).length;
}
function collectionMatches(c, q) {
    if (state.collection) return false;
    if (multiObsOn()) return false;
    if (!collectionMatchesArea(c, state.area)) return false;
    if (state.regions.size && !state.regions.has(c.region)) return false;
    if (state.sites.size) return false;
    if (state.photographers.size && !state.photographers.has(c.photographer)) return false;
    if (state.years.size && !state.years.has(String(c.year))) return false;
    if (state.order !== 'all' || state.subOrder !== 'all' || state.superfamily !== 'all' || state.family !== 'all' || state.genus !== 'all') return false;
    if (q) {
        const r = regionLabelsData[c.region];
        const a = areaLabelsData[c.area];
        // Includes the card's own heading ("50 מינים · מרץ 2023"), so the species count, month
        // and year shown on the card are searchable too.
        const hay = normalize([collectionTitle(c), c.title, c.year, r?.label, r?.label_en, a?.label, a?.label_en, c.photographer, photographerLabel(c)].filter(Boolean).join(' '));
        if (!hay.includes(q)) return false;
    }
    return true;
}

// ---- media / dialog ----

function collectionTitle(c) {
    const en = language === 'en';
    const count = c.species_count == null ? (en ? 'Species count not specified' : 'מספר המינים לא צוין') : `${c.species_count} ${en ? 'species' : 'מינים'}`;
    const month = c.month ? new Intl.DateTimeFormat(en ? 'en' : 'he', { month: 'long', timeZone: 'UTC' }).format(new Date(Date.UTC(2000, c.month - 1, 1))) : (en ? 'Month not specified' : 'חודש לא צוין');
    return `${count} · ${month} ${c.year || ''}`;
}
function sampleSubtitle(sm) {
    const monthLabel = sm.month ? new Intl.DateTimeFormat(language === 'en' ? 'en' : 'he', { month: 'long', timeZone: 'UTC' }).format(new Date(Date.UTC(2000, sm.month - 1, 1))) : '';
    const regionText = labelFor(sm.region, regionLabelsData);
    const siteText = sm.site ? labelFor(sm.site, siteLabelsData) : '';
    const dateText = [monthLabel, sm.year].filter(Boolean).join(' ');
    const location = [regionText, siteText, dateText].filter(Boolean).join(' · ');
    const credit = sm.photographer ? `${language === 'he' ? 'צילום: ' : 'Photography: '}${photographerLabel(sm)}` : '';
    return [location, credit].filter(Boolean).join(' · ');
}
function collectionSubtitle(c) {
    const regionText = labelFor(c.region, regionLabelsData);
    const credit = c.photographer ? `${language === 'he' ? 'צילום: ' : 'Photography: '}${photographerLabel(c)}` : '';
    return [regionText, credit].filter(Boolean).join(' · ');
}
function showMedia(video_id, image_url, title, subtitle) {
    document.querySelector('#playerTitle').textContent = title;
    document.querySelector('#playerRegion').textContent = subtitle;
    const container = document.querySelector('#frame');
    const link = document.querySelector('#youtubeLink');
    document.querySelector('.player-bottom').hidden = !video_id;
    container.classList.toggle('image-view', !video_id);
    container.hidden = false;
    document.querySelector('#pickerList').hidden = true;
    let media;
    if (video_id) {
        link.href = `https://www.youtube.com/watch?v=${video_id}`;
        media = document.createElement('iframe');
        media.src = `https://www.youtube-nocookie.com/embed/${encodeURIComponent(video_id)}?autoplay=1&rel=0`;
        media.title = title;
        media.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share';
        media.allowFullscreen = true;
        media.referrerPolicy = 'strict-origin-when-cross-origin';
    } else {
        media = document.createElement('img');
        media.src = image_url;
        media.alt = title;
    }
    container.replaceChildren(media);
}
function openDialog() {
    document.body.style.overflow = 'hidden';
    dialog.showModal();
}
function playSampleOf(species, sample, button) {
    if (button) opener = button;
    showMedia(sample.video_id, sample.image_url, species.title, sampleSubtitle(sample));
    openDialog();
}
function openSpeciesDialog(species, button) {
    opener = button;
    const pool = scopedSamples(species);
    const samples = pool && pool.length ? pool : species.samples;
    if (samples.length <= 1) {
        playSampleOf(species, samples[0], button);
        return;
    }
    setLatinName(document.querySelector('#playerTitle'), species.title);
    document.querySelector('#playerRegion').textContent = language === 'he' ? `${samples.length} תצפיות — לבחירה מהרשימה` : `${samples.length} observations — choose from the list`;
    document.querySelector('#frame').hidden = true;
    document.querySelector('.player-bottom').hidden = true;
    const list = document.querySelector('#pickerList');
    list.replaceChildren();
    for (const sm of samples) {
        const li = document.createElement('li');
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'picker-item';
        const thumb = document.createElement('img');
        thumb.src = sm.thumbnail;
        thumb.alt = '';
        thumb.loading = 'lazy';
        const text = document.createElement('span');
        text.textContent = sampleSubtitle(sm);
        btn.append(thumb, text);
        btn.addEventListener('click', () => playSampleOf(species, sm, btn));
        li.append(btn);
        list.append(li);
    }
    list.hidden = false;
    openDialog();
}
function playCollection(c, button) {
    opener = button;
    state.collection = String(c.trip_id);
    search.value = '';
    render();
    showMedia(c.video_id, c.image_url, collectionTitle(c), collectionSubtitle(c));
    openDialog();
}

// ---- cards / grid ----

function buildCollectionCard(c, index) {
    const article = document.createElement('article');
    article.className = 'card';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'video-button';
    const title = collectionTitle(c);
    button.setAttribute('aria-label', `${language === 'he' ? 'בחירת אוסף' : 'Select collection'}: ${title}`);
    const wrap = document.createElement('span');
    wrap.className = 'image-wrap';
    const img = document.createElement('img');
    img.src = c.thumbnail;
    img.alt = '';
    img.width = 640; img.height = 360;
    img.loading = index < 6 ? 'eager' : 'lazy';
    img.decoding = 'async';
    const icon = document.createElement('span');
    icon.className = 'play';
    icon.textContent = c.video_id ? '▶' : '⤢';
    icon.setAttribute('aria-hidden', 'true');
    wrap.append(img, icon);
    const info = document.createElement('span');
    info.className = 'card-info';
    const h3 = document.createElement('h3');
    h3.className = 'hebrew';
    h3.textContent = title;
    const credit = document.createElement('span');
    credit.className = 'photographer';
    if (c.photographer) credit.textContent = (language === 'he' ? 'צילום: ' : 'Photography: ') + photographerLabel(c);
    const meta = document.createElement('span');
    meta.className = 'card-meta';
    const region = document.createElement('span');
    // Filtered to a single region: its name is already the filter, so don't repeat it.
    if (state.regions.size !== 1) region.textContent = labelFor(c.region, regionLabelsData);
    const label = document.createElement('span');
    label.textContent = language === 'he' ? 'צפייה באוסף' : 'View collection';
    meta.append(region, label);
    info.append(h3, credit, meta);
    button.append(wrap, info);
    button.addEventListener('click', () => playCollection(c, button));
    article.append(button);
    return article;
}
// Scientific names are shown with the genus and the species epithet in italics and everything
// else (cf./aff., "sp. 7", the variant letter, the author) in roman -- the same rule as
// observations/names.py (name_html), which renders the server-side pages.
function setLatinName(el, text) {
    el.textContent = '';
    const tokens = String(text || '').split(/\s+/).filter(Boolean);
    const italic = tokens.map(() => false);
    if (tokens.length && /^[A-Z][a-z]+$/.test(tokens[0])) {
        italic[0] = true;
        let i = 1;
        if (tokens.length > 1 && /^(cf|aff)\.?$/i.test(tokens[1])) i = 2;
        if (i < tokens.length && /^[a-z][a-z-]+$/.test(tokens[i]) && !/^spp?$/.test(tokens[i])) italic[i] = true;
    }
    let run = [];
    const flush = () => {
        if (!run.length) return;
        const i = document.createElement('i');
        i.textContent = run.join(' ');
        if (el.childNodes.length) el.append(' ');
        el.append(i);
        run = [];
    };
    for (let k = 0; k < tokens.length; k++) {
        if (italic[k]) { run.push(tokens[k]); continue; }
        flush();
        if (el.childNodes.length) el.append(' ');
        el.append(tokens[k]);
    }
    flush();
}

function buildSpeciesCard(sp, index) {
    const article = document.createElement('article');
    article.className = 'card';
    // Real navigation to the species' own dedicated, crawlable page when one exists
    // (every species+area does, once slugs have been backfilled) -- otherwise (older
    // data without a slug, in theory) fall back to the in-page preview dialog.
    const button = sp.slug ? document.createElement('a') : document.createElement('button');
    if (sp.slug) button.href = `/species/${sp.slug}/`;
    else button.type = 'button';
    button.className = 'video-button';
    const common = language === 'he' ? (sp.name_he || sp.name_en) : (sp.name_en || sp.name_he);
    button.setAttribute('aria-label', `${language === 'he' ? 'צפייה' : 'Watch'}: ${sp.title}${common ? ' — ' + common : ''}`);
    // When a collection and/or region/site/photographer filter is active, show the
    // sample that actually matches the current view here too -- the species' overall
    // defining sample may belong to a different trip, region, site or photographer.
    const pickSamples = scopedSamples(sp);
    const cardSample = pickSamples && pickSamples.length === 1 ? pickSamples[0] : null;
    const wrap = document.createElement('span');
    wrap.className = 'image-wrap';
    const img = document.createElement('img');
    img.src = (pickSamples ? pickSamples[0] : sp).thumbnail;
    img.alt = '';
    img.width = 640; img.height = 360;
    img.loading = index < 6 ? 'eager' : 'lazy';
    img.decoding = 'async';
    const icon = document.createElement('span');
    icon.className = 'play';
    icon.textContent = (pickSamples ? pickSamples[0] : sp).video_id ? '▶' : '⤢';
    icon.setAttribute('aria-hidden', 'true');
    wrap.append(img, icon);
    const displayCount = pickSamples ? pickSamples.length : sp.samples.length;
    if (displayCount > 1) {
        const badge = document.createElement('span');
        badge.className = 'count-badge';
        badge.textContent = displayCount;
        badge.setAttribute('aria-hidden', 'true');
        wrap.append(badge);
    }
    const info = document.createElement('span');
    info.className = 'card-info';
    const h3 = document.createElement('h3');
    setLatinName(h3, sp.title);
    if (sp.author) {
        const author = document.createElement('span');
        author.className = 'card-author';
        author.textContent = sp.author;
        h3.append(' ', author);
    }
    const sub = document.createElement('span');
    sub.className = 'common-name';
    if (common) sub.textContent = common;
    const credit = document.createElement('span');
    credit.className = 'photographer';
    const creditSample = cardSample || (sp.samples.length === 1 ? sp.samples[0] : null);
    if (creditSample && creditSample.photographer) {
        credit.textContent = (language === 'he' ? 'צילום: ' : 'Photography: ') + photographerLabel(creditSample);
    }
    const meta = document.createElement('span');
    meta.className = 'card-meta';
    const area = document.createElement('span');
    // Where/when the card's own photo was taken, e.g. "Anilao, 2017" -- more useful
    // here than the country+sea area label, which is already shown by the area filter
    // above the grid and can span many regions/years. Uses the current view's own
    // sample when one is scoped in, otherwise the species' defining sample.
    const regionSrc = pickSamples ? pickSamples[0] : sp;
    const regionLabel = labelFor(regionSrc.region, regionLabelsData);
    // Filtered to a single region: its name is already the filter, so show only the year.
    const regionFiltered = state.regions.size === 1;
    area.textContent = regionFiltered && regionSrc.year ? String(regionSrc.year)
        : regionLabel && regionSrc.year ? `${regionLabel}, ${regionSrc.year}` : areaLabelFor(sp.area);
    const label = document.createElement('span');
    label.textContent = displayCount > 1 && !cardSample
        ? (language === 'he' ? `${displayCount} תצפיות` : `${displayCount} observations`)
        : (language === 'he' ? 'לצפייה' : 'Watch');
    // Place/year and the photographer share one line ("אנילאו, 2023 · צילום: ..."); the
    // "watch" / "N observations" label stays on the other side and wraps below if it must.
    const where = document.createElement('span');
    where.className = 'card-where';
    where.append(area);
    if (credit.textContent) where.append(' · ', credit);
    meta.append(where, label);
    info.append(h3);
    if (common) info.append(sub);
    // Under the migrant-species filter: when the species was first and last recorded in
    // the Mediterranean (Species.first/last_observed_year).
    if (state.area === 'migrant' && (sp.first_observed_year || sp.last_observed_year)) {
        const years = document.createElement('span');
        years.className = 'card-years';
        // One row per date, the year in bold; the grid lines the years up one under the other.
        const addYear = (labelHe, labelEn, year) => {
            if (!year) return;
            const label = document.createElement('span');
            label.textContent = language === 'he' ? labelHe : labelEn;
            const value = document.createElement('strong');
            value.textContent = year;
            years.append(label, ' ', value, ' ');
        };
        addYear('נצפה לראשונה בים התיכון', 'Mediterranean first sight', sp.first_observed_year);
        addYear('נראה לאחרונה', 'Last seen', sp.last_observed_year);
        info.append(years);
    }
    info.append(meta);
    button.append(wrap, info);
    if (!sp.slug) button.addEventListener('click', () => openSpeciesDialog(sp, button));
    article.append(button);
    return article;
}
// Thin group-heading panel shown above the first card of a new order/family/genus group
// when browsing in taxonomic order -- text like "סדרה - [שם הסדרה]", plus a small preview
// icon when that taxon has a defining sample with media (see catalog.taxa).
function renderTaxonPanel(level, id) {
    const dict = level === 'order' ? taxaData.orders : level === 'family' ? taxaData.families : taxaData.genera;
    const entry = dict ? dict[id] : null;
    const levelLabel = level === 'order' ? (language === 'he' ? 'סדרה' : 'Order')
        : level === 'family' ? (language === 'he' ? 'משפחה' : 'Family')
        : (language === 'he' ? 'סוג' : 'Genus');
    const name = entry ? (language === 'en' ? (entry.label_en || entry.label) : entry.label) : '';
    const title = `${levelLabel} - ${name}`;
    // Every order, family and genus has its own public page (order by id, since one order
    // name can have several rows; family and genus by name) -- the panel links straight to it.
    const href = !entry ? '' : level === 'order' ? `/order/${encodeURIComponent(id)}/`
        : `/${level}/${encodeURIComponent(entry.name)}/`;
    const panel = document.createElement(href ? 'a' : 'div');
    panel.className = `taxon-panel taxon-panel-${level}${href ? ' taxon-panel-clickable' : ''}`;
    if (href) {
        panel.href = href + (language === 'en' ? '?lang=en' : '');
        panel.setAttribute('aria-label', title);
    }
    if (entry && entry.thumbnail) {
        const img = document.createElement('img');
        img.src = entry.thumbnail;
        img.alt = '';
        img.loading = 'lazy';
        panel.append(img);
    }
    const text = document.createElement('span');
    text.textContent = title;
    panel.append(text);
    return panel;
}
function speciesSortKey(sp) {
    return normalize(sp.genus || sp.title || '');
}
function speciesSortCompare(a, b) {
    const ga = speciesSortKey(a), gb = speciesSortKey(b);
    if (ga !== gb) return ga.localeCompare(gb, 'he');
    const ea = normalize(a.epithet || ''), eb = normalize(b.epithet || '');
    if (ea !== eb) return ea.localeCompare(eb, 'he');
    return normalize(a.title || '').localeCompare(normalize(b.title || ''), 'he');
}
// Observation-year sort: earliest first record in the Mediterranean first (the order the
// species arrived in); species with no recorded year come last, alphabetical among themselves.
function speciesYearKey(sp) {
    const y = sp.first_observed_year || sp.last_observed_year;
    return y || Infinity;
}
function speciesYearCompare(a, b) {
    const ya = speciesYearKey(a), yb = speciesYearKey(b);
    if (ya !== yb) return ya < yb ? -1 : 1;
    const la = a.last_observed_year || Infinity, lb = b.last_observed_year || Infinity;
    if (la !== lb) return la < lb ? -1 : 1;
    return speciesSortCompare(a, b);
}
// Number-of-observations sort: most observations first, taxonomic order among equals.
function speciesCountCompare(a, b) {
    const ca = observationCount(a), cb = observationCount(b);
    if (ca !== cb) return cb - ca;
    return speciesSortCompare(a, b);
}
// The observation-year sort only makes sense for the migrant species, so its <option> is in
// the sort menu only while that area filter is active (removed, not just hidden: Safari
// ignores `hidden` on options). Leaving the migrant view while sorted by year falls back to
// the taxonomic order.
const sortSelect = document.querySelector('#sortSelect');
const yearSortOption = sortSelect.querySelector('option[value="year"]');
// Likewise the number-of-observations sort is offered only under its own filter.
const countSortOption = sortSelect.querySelector('option[value="count"]');
function syncSortControl() {
    if (state.area === 'migrant') {
        if (!yearSortOption.parentNode) sortSelect.append(yearSortOption);
    } else {
        if (state.sort === 'year') { state.sort = defaultSort(); state.sortChosen = false; }
        yearSortOption.remove();
    }
    if (multiObsOn()) {
        if (!countSortOption.parentNode) sortSelect.append(countSortOption);
    } else {
        if (state.sort === 'count') { state.sort = defaultSort(); state.sortChosen = false; }
        countSortOption.remove();
    }
    sortSelect.value = state.sort;
}
function render() {
    updateCollectionStatus();
    const q = normalize(search.value);
    searchByName = !!q && speciesList.some(sp => speciesNameMatches(sp, q));
    const filteredCollections = collectionsList.filter(c => collectionMatches(c, q));
    let filteredSpecies = speciesList.filter(sp => speciesMatches(sp, q));
    if (state.sort === 'alpha') filteredSpecies = [...filteredSpecies].sort(speciesSortCompare);
    if (state.sort === 'year') filteredSpecies = [...filteredSpecies].sort(speciesYearCompare);
    if (state.sort === 'count') filteredSpecies = [...filteredSpecies].sort(speciesCountCompare);
    grid.replaceChildren();
    const frag = document.createDocumentFragment();
    if (filteredCollections.length) {
        const heading = document.createElement('h2');
        heading.className = 'gallery-group-title';
        heading.textContent = language === 'he' ? 'אוספי מסעות צלילה' : 'Dive trip collections';
        frag.append(heading);
        filteredCollections.forEach((c, i) => frag.append(buildCollectionCard(c, i)));
    }
    if (filteredSpecies.length) {
        const heading = document.createElement('h2');
        heading.className = 'gallery-group-title';
        heading.textContent = language === 'he' ? 'מינים' : 'Species';
        frag.append(heading);
        let prev = null;
        filteredSpecies.forEach((sp, i) => {
            if (state.sort === 'taxonomic') {
                const orderChanged = !prev || prev.taxon_order_id !== sp.taxon_order_id;
                const familyChanged = orderChanged || prev.taxon_family_id !== sp.taxon_family_id;
                const genusChanged = familyChanged || prev.taxon_genus_id !== sp.taxon_genus_id;
                if (sp.taxon_order_id && orderChanged) frag.append(renderTaxonPanel('order', sp.taxon_order_id));
                if (sp.taxon_family_id && familyChanged) frag.append(renderTaxonPanel('family', sp.taxon_family_id));
                if (sp.taxon_genus_id && genusChanged) frag.append(renderTaxonPanel('genus', sp.taxon_genus_id));
                prev = sp;
            }
            frag.append(buildSpeciesCard(sp, i));
        });
    }
    grid.append(frag);
    const total = filteredSpecies.length + filteredCollections.length;
    document.querySelector('#resultCount').textContent = language === 'he' ? `${total} פריטים` : `${total} ${total === 1 ? 'item' : 'items'}`;
    document.querySelector('#empty').hidden = total > 0;
    updateFilterToggleCount();
}

// ---- mobile filter drawer ----

const filterToggle = document.querySelector('#filterToggle');
const filterSidebar = document.querySelector('#filterSidebar');
const filterClose = document.querySelector('#filterClose');
const filterToggleCount = document.querySelector('#filterToggleCount');
function closeFilterDrawer() {
    filterSidebar.classList.remove('open');
    filterToggle?.setAttribute('aria-expanded', 'false');
    document.body.style.overflow = '';
}
function openFilterDrawer() {
    filterSidebar.classList.add('open');
    filterToggle?.setAttribute('aria-expanded', 'true');
    document.body.style.overflow = 'hidden';
}
function updateFilterToggleCount() {
    if (!filterToggleCount) return;
    // state.area is excluded here: the area chips now live in their own always-visible
    // bar above the gallery (see .area-filter-bar), not inside the collapsible drawer this
    // toggle/badge refers to, so counting it here would over-count what's actually hidden.
    let n = state.regions.size + state.sites.size + state.photographers.size + state.years.size + state.observations.size;
    if (state.order !== 'all') n++;
    if (state.subOrder !== 'all') n++;
    if (state.superfamily !== 'all') n++;
    if (state.family !== 'all') n++;
    if (state.genus !== 'all') n++;
    filterToggleCount.textContent = String(n);
    filterToggleCount.hidden = n === 0;
}
filterToggle?.addEventListener('click', () => {
    if (filterSidebar.classList.contains('open')) closeFilterDrawer(); else openFilterDrawer();
});
filterClose?.addEventListener('click', closeFilterDrawer);
document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && filterSidebar.classList.contains('open')) { closeFilterDrawer(); filterToggle?.focus(); }
});

// ---- mobile account menu ----

const accountMenuToggle = document.querySelector('.account-menu-toggle');
const accountMenuList = document.querySelector('.account-menu-list');
if (accountMenuToggle && accountMenuList) {
    accountMenuToggle.addEventListener('click', () => {
        const open = accountMenuList.classList.toggle('open');
        accountMenuToggle.setAttribute('aria-expanded', String(open));
    });
    document.addEventListener('click', e => {
        if (!accountMenuList.classList.contains('open')) return;
        if (accountMenuList.contains(e.target) || accountMenuToggle.contains(e.target)) return;
        accountMenuList.classList.remove('open');
        accountMenuToggle.setAttribute('aria-expanded', 'false');
    });
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape' && accountMenuList.classList.contains('open')) {
            accountMenuList.classList.remove('open');
            accountMenuToggle.setAttribute('aria-expanded', 'false');
            accountMenuToggle.focus();
        }
    });
}

// ---- search autocomplete ----
// Suggestions under the search box as you type: species (scientific and common names),
// genera, families, dive sites and regions. Picking a species that has a single page goes
// straight to it; anything else fills the box and filters the gallery as usual.
const suggestBox = document.createElement('ul');
suggestBox.id = 'searchSuggest';
suggestBox.className = 'search-suggest';
suggestBox.setAttribute('role', 'listbox');
suggestBox.hidden = true;
search.closest('.collection-head').append(suggestBox);
search.setAttribute('role', 'combobox');
search.setAttribute('aria-autocomplete', 'list');
search.setAttribute('aria-controls', 'searchSuggest');
search.setAttribute('aria-expanded', 'false');
search.spellcheck = false;
let suggestItems = [], suggestActive = -1;
const SUGGEST_KINDS = { genus: 0, family: 1, species: 2, common: 3, site: 4, region: 5 };
function suggestKindLabel(kind) {
    const he = { common: 'שם עממי', genus: 'סוג', family: 'משפחה', site: 'אתר צלילה', region: 'אזור צלילה' };
    const en = { common: 'Common name', genus: 'Genus', family: 'Family', site: 'Dive site', region: 'Dive region' };
    return (language === 'he' ? he : en)[kind] || '';
}
function buildSuggestCandidates() {
    const out = new Map();   // dedupe by kind + text
    const add = (kind, text, extra = {}) => {
        if (!text) return;
        const key = kind + '|' + normalize(text);
        const prev = out.get(key);
        if (prev) { prev.slugs.add(extra.slug); return; }
        out.set(key, { kind, text, norm: normalize(text), slugs: new Set([extra.slug]), latin: !!extra.latin });
    };
    for (const sp of speciesList) {
        add('species', sp.title, { slug: sp.slug, latin: true });
        const common = language === 'he' ? sp.name_he : sp.name_en;
        if (common) add('common', common, { slug: sp.slug });
        add('genus', sp.genus, { latin: true });
        add('family', sp.family);
    }
    const lbl = e => e && (language === 'en' ? (e.label_en || e.label) : e.label);
    for (const id in siteLabelsData) add('site', lbl(siteLabelsData[id]));
    for (const id in regionLabelsData) add('region', lbl(regionLabelsData[id]));
    return [...out.values()];
}
function suggestRank(c, q) {
    if (c.norm.startsWith(q)) return 0;
    if (c.norm.split(' ').some(w => w.startsWith(q))) return 1;
    return c.norm.includes(q) ? 2 : -1;
}
function closeSuggest() {
    suggestBox.hidden = true;
    suggestBox.replaceChildren();
    suggestItems = []; suggestActive = -1;
    search.setAttribute('aria-expanded', 'false');
    search.removeAttribute('aria-activedescendant');
}
function updateSuggest() {
    const q = normalize(search.value);
    if (q.length < 2) { closeSuggest(); return; }
    suggestItems = buildSuggestCandidates()
        .map(c => ({ c, r: suggestRank(c, q) }))
        .filter(x => x.r >= 0 && x.c.norm !== q)
        .sort((a, b) => a.r - b.r || SUGGEST_KINDS[a.c.kind] - SUGGEST_KINDS[b.c.kind] || a.c.text.localeCompare(b.c.text, language === 'he' ? 'he' : 'en'))
        .map(x => x.c);   // every match, however many: the chips wrap onto more rows
    if (!suggestItems.length) { closeSuggest(); return; }
    suggestActive = -1;
    suggestBox.replaceChildren(...suggestItems.map((c, i) => {
        const li = document.createElement('li');
        li.id = 'searchSuggest-' + i;
        li.setAttribute('role', 'option');
        const name = document.createElement('span');
        name.className = 'suggest-name';
        if (c.latin) { setLatinName(name, c.text); name.dir = 'ltr'; } else name.textContent = c.text;
        li.append(name);
        const kind = suggestKindLabel(c.kind);
        if (kind) { const k = document.createElement('small'); k.textContent = kind; li.append(k); }
        li.addEventListener('mousedown', e => e.preventDefault());   // keep focus in the box
        li.addEventListener('click', () => pickSuggest(i));
        return li;
    }));
    suggestBox.hidden = false;
    search.setAttribute('aria-expanded', 'true');
}
function highlightSuggest(i) {
    suggestActive = i;
    [...suggestBox.children].forEach((li, j) => li.setAttribute('aria-selected', String(j === i)));
    if (i >= 0) { search.setAttribute('aria-activedescendant', 'searchSuggest-' + i); suggestBox.children[i].scrollIntoView({ block: 'nearest' }); }
    else search.removeAttribute('aria-activedescendant');
}
// Picking a suggestion fills the box and filters the gallery to it (the same as typing it
// in full), then brings the results into view.
function pickSuggest(i) {
    const c = suggestItems[i];
    if (!c) return;
    search.value = c.text;
    closeSuggest();
    render();
    document.querySelector('#resultCount').scrollIntoView({ behavior: 'smooth', block: 'start' });
}
search.addEventListener('input', updateSuggest);
search.addEventListener('focus', updateSuggest);
search.addEventListener('blur', () => setTimeout(() => { if (!suggestBox.contains(document.activeElement)) closeSuggest(); }, 150));
search.addEventListener('keydown', e => {
    if (suggestBox.hidden) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); highlightSuggest((suggestActive + 1) % suggestItems.length); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); highlightSuggest(suggestActive <= 0 ? suggestItems.length - 1 : suggestActive - 1); }
    else if (e.key === 'Enter' && suggestActive >= 0) { e.preventDefault(); pickSuggest(suggestActive); }
    else if (e.key === 'Escape') { e.preventDefault(); closeSuggest(); }
});

syncSortControl();
document.querySelector('#total').textContent = `(${speciesList.length})`;
search.addEventListener('input', render);
document.querySelector('#reset').addEventListener('click', () => {
    search.value = '';
    state.area = 'all'; state.regions.clear(); state.sites.clear(); state.photographers.clear(); state.years.clear(); state.observations.clear();
    state.order = 'all'; state.subOrder = 'all'; state.superfamily = 'all'; state.family = 'all'; state.genus = 'all'; state.collection = null;
    state.sort = 'taxonomic'; state.sortChosen = false; syncSortControl();
    renderSidebar(); render(); search.focus();
});
document.querySelector('#orderSelect').addEventListener('change', e => { state.order = e.target.value; state.subOrder = 'all'; state.superfamily = 'all'; state.family = 'all'; state.genus = 'all'; renderTaxonomySelects(); render(); });
document.querySelector('#subOrderSelect').addEventListener('change', e => { state.subOrder = e.target.value; state.superfamily = 'all'; state.family = 'all'; state.genus = 'all'; renderTaxonomySelects(); render(); });
document.querySelector('#superfamilySelect').addEventListener('change', e => { state.superfamily = e.target.value; state.family = 'all'; state.genus = 'all'; renderTaxonomySelects(); render(); });
document.querySelector('#familySelect').addEventListener('change', e => { state.family = e.target.value; state.genus = 'all'; renderTaxonomySelects(); render(); });
document.querySelector('#genusSelect').addEventListener('change', e => { state.genus = e.target.value; render(); });
document.querySelector('#tripSelect').addEventListener('change', e => { state.collection = e.target.value === 'all' ? null : e.target.value; render(); });
document.querySelector('#sortSelect').addEventListener('change', e => { state.sort = e.target.value; state.sortChosen = true; render(); });
document.querySelector('#close').addEventListener('click', () => dialog.close());
dialog.addEventListener('click', e => {
    if (e.target === dialog) {
        const r = dialog.getBoundingClientRect();
        if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) dialog.close();
    }
});
dialog.addEventListener('close', () => {
    document.querySelector('#frame').replaceChildren();
    document.querySelector('#frame').hidden = false;
    const list = document.querySelector('#pickerList');
    list.hidden = true;
    list.replaceChildren();
    document.body.style.overflow = '';
    opener?.focus();
});

// ---- bilingual UI ----

const translations = [
    ['.brand-he', 'Sea slugs'],
    ['.credit', 'Macro photography · Stills and video'],
    ['.eyebrow', 'Through the lens, beneath the sea'],
    ['.intro-copy', 'Search, watch and publish new species here — and find macro diving partners too.'],
    ['.search > span', 'Search'],
    ['.sort-order > span', 'Sort'],
    ['#empty h3', 'No items found'],
    ['#empty p', 'Try a different name or choose another region.'],
    ['#reset', 'Clear search and filters'],
    ['footer p', 'Photography: Boaz Liebes · Videos hosted on YouTube'],
    ['footer > span:last-child', 'Sea slugs, up close.'],
    ['.player-bottom > span', 'If the video does not load, watch it on YouTube.'],
    ['#youtubeLink', 'Watch on YouTube ↗'],
    ['#filterSidebarTitle', 'Filters'],
    ['#filterToggleLabel', 'Filters'],
    ['#areaGroupTitle', 'Area'],
    ['#regionGroupTitle', 'Dive region'],
    ['#observationGroupTitle', 'Observations'],
    ['#siteGroupTitle', 'Dive site'],
    ['#tripGroupTitle', 'Dive trip'],
    ['#photographerGroupTitle', 'Photographer'],
    ['#yearGroupTitle', 'Year'],
    ['#orderGroupTitle', 'Order'],
    ['#subOrderGroupTitle', 'Suborder'],
    ['#superfamilyGroupTitle', 'Superfamily'],
    ['#familyGroupTitle', 'Family'],
    ['#genusGroupTitle', 'Genus'],
].map(([selector, en]) => {
    const element = document.querySelector(selector);
    return { element, he: element.cloneNode(true), en };
});
const heading = document.querySelector('h1');
const originalHeading = heading.cloneNode(true);
const collectionHeading = document.querySelector('#collectionTitle').firstChild;
const originalCollectionHeading = collectionHeading.textContent;
const originalTitle = document.title;
const description = document.querySelector('meta[name="description"]');
const originalDescription = description.content;
const languageButton = document.createElement('button');
languageButton.type = 'button';
languageButton.className = 'language-switch';
document.querySelector('.masthead').append(languageButton);

function setLanguage(value) {
    language = value === 'en' ? 'en' : 'he';
    const en = language === 'en';
    document.documentElement.lang = language;
    document.documentElement.dir = en ? 'ltr' : 'rtl';
    translations.forEach(item => {
        if (en) item.element.textContent = item.en;
        else item.element.replaceChildren(...Array.from(item.he.childNodes, node => node.cloneNode(true)));
    });
    heading.replaceChildren();
    if (en) {
        heading.append('Home for sea slug enthusiasts');
    } else {
        heading.append(...Array.from(originalHeading.childNodes, node => node.cloneNode(true)));
    }
    collectionHeading.textContent = en ? 'Gallery ' : originalCollectionHeading;
    search.placeholder = en ? 'Species or video name…' : 'שם המין או הסרטון…';
    search.setAttribute('aria-label', en ? 'Search by species or video name' : 'חיפוש לפי שם המין או הסרטון');
    document.querySelector('#areaFilters').setAttribute('aria-label', en ? 'Filter by area' : 'סינון לפי אזור');
    document.querySelector('#filterSidebar').setAttribute('aria-label', en ? 'Filters' : 'סינון');
    document.querySelector('.brand').setAttribute('aria-label', en ? 'SeaSlugs — Home' : 'SeaSlugs — דף הבית');
    document.querySelector('#close').setAttribute('aria-label', en ? 'Close video' : 'סגירת התצוגה');
    document.querySelector('#filterClose').setAttribute('aria-label', en ? 'Close filters' : 'סגירת הסינון');
    document.querySelector('#sortSelect').setAttribute('aria-label', en ? 'Sort species' : 'מיון המינים');
    document.querySelector('#sortSelect option[value="taxonomic"]').textContent = en ? 'Taxonomic order' : 'סדר טקסונומי';
    document.querySelector('#sortSelect option[value="alpha"]').textContent = en ? 'Alphabetical (genus then species)' : 'אלפביתי (סוג ואז מין)';
    countSortOption.textContent = en ? 'Number of observations (most first)' : 'מספר תצפיות (מהגדול לקטן)';
    yearSortOption.textContent = en ? 'Observation year (earliest first)' : 'שנת תצפית (מהמוקדם למאוחר)';
    languageButton.textContent = en ? 'עברית' : 'English';
    languageButton.lang = en ? 'he' : 'en';
    languageButton.setAttribute('aria-label', en ? 'Switch to Hebrew' : 'מעבר לאנגלית');
    document.title = en ? 'SeaSlugs — Sea slugs | Boaz Liebes' : originalTitle;
    description.content = en ? 'Sea slug videos by Boaz Liebes. Explore Romblon, the Red Sea and the Mediterranean.' : originalDescription;
    const url = new URL(window.location.href);
    url.searchParams.set('lang', language);
    window.history.replaceState(null, '', url);
    try { localStorage.setItem('seaslugs-language', language); } catch (_) {}
    renderSidebar();
    render();
}
languageButton.addEventListener('click', () => setLanguage(language === 'he' ? 'en' : 'he'));
let preferredLanguage = 'he';
try { preferredLanguage = localStorage.getItem('seaslugs-language') || 'he'; } catch (_) {}
setLanguage(new URLSearchParams(window.location.search).get('lang') || preferredLanguage);
