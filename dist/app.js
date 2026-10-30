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
    // Taxonomic drill-down (taxonomic sort only): which rank the gallery shows cards for --
    // 'order' (the default), 'family', 'genus' or 'species' -- and, once the visitor has
    // clicked into a taxon card (or picked a taxon in the search), that taxon: {level, id}.
    level: 'order',
    drill: null,
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
    if (state.drill) {
        const label = document.createElement('span');
        const trip = state.collection ? collectionsList.find(x => String(x.trip_id) === state.collection) : null;
        label.textContent = (language === 'he' ? 'מוצג: ' : 'Showing: ') + drillLabel(state.drill)
            + (state.collection ? (language === 'he' ? ' · באוסף: ' : ' · in collection: ') + (trip ? collectionName(trip) : (labelFor(state.collection, tripLabelsData) || '')) : '');
        // Up one rank (to the parent taxon this one was drilled from), and all the way up.
        const parent = drillParent(state.drill);
        const up = document.createElement('button');
        up.type = 'button';
        up.textContent = parent
            ? (language === 'he' ? 'חזרה ל־' : 'Back to ') + drillLabel(parent)
            : (language === 'he' ? 'חזרה לכל הסדרות' : 'Back to all orders');
        up.addEventListener('click', () => {
            if (parent) {
                state.drill = parent;
                setLevel(nextLevel(parent.blanks && parent.blanks.length ? parent.blanks[parent.blanks.length - 1] : parent.level, drillMembers(parent)));
            } else {
                state.drill = null; setLevel('order');
            }
            render();
        });
        collectionStatus.append(label, up);
        if (parent) {
            const top = document.createElement('button');
            top.type = 'button';
            top.className = 'secondary';
            top.textContent = language === 'he' ? 'כל הסדרות' : 'All orders';
            top.addEventListener('click', () => { state.drill = null; setLevel('order'); render(); });
            collectionStatus.append(top);
        }
        return;
    }
    if (!state.collection) return;
    const c = collectionsList.find(x => String(x.trip_id) === state.collection);
    const label = document.createElement('span');
    const description = c ? collectionName(c) : (labelFor(state.collection, tripLabelsData) || '');
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
            // A trip is offered only when one of its observations fits the place (region, site)
            // and year already chosen above it in the sidebar.
            if (sm.trip_id != null && inSelectedRegions && (!state.sites.size || (sm.site && state.sites.has(sm.site)))
                && (!state.years.size || state.years.has(String(sm.year)))) trips.add(String(sm.trip_id));
            if (sm.year != null && inSelectedRegions) years.add(String(sm.year));
        }
    }
    for (const c of collectionsList) {
        if (!collectionMatchesArea(c, area)) continue;
        regionIds.add(c.region);
        if (c.photographer) photographers.add(c.photographer);
        const collectionInRegion = !state.regions.size || state.regions.has(c.region);
        if (c.trip_id != null && collectionInRegion && !state.sites.size
            && (!state.years.size || state.years.has(String(c.year)))) trips.add(String(c.trip_id));
        if (c.year != null && collectionInRegion) years.add(String(c.year));
    }
    return { regionIds, siteIds, photographers, trips, years };
}
// A gallery card is a species in an area (the site calls that an "observation"), so the same species seen in two
// areas is two cards. Every counter therefore shows the number of distinct SPECIES ("30 מינים"); only the "All
// areas" button also says how many observations they are ("266 מינים ב-301 תצפיות"). The same wording is built
// server-side by observations/counts.py.
function speciesIn(list) { return new Set(list.map(sp => sp.species_id)).size; }
function countText(species) {
    if (language === 'en') return `${species} species`;
    return species === 1 ? 'מין אחד' : `${species} מינים`;
}
function countCompact(species) { return String(species); }
function observationsText(species, observations) {
    if (language === 'en') return `${species} species in ${observations} ${observations === 1 ? 'observation' : 'observations'}`;
    return `${countText(species)} ב-${observations === 1 ? 'תצפית אחת' : observations + ' תצפיות'}`;
}
// {compact} for a list of species cards: how many distinct species they hold.
function tally(list) {
    return { compact: countCompact(speciesIn(list)), title: '', species: speciesIn(list), observations: list.length };
}
function regionCount(area, id) {
    return tally(speciesList.filter(sp => matchesAreaFilter(sp, area) && sp.samples.some(sm => sm.region === id)));
}
function siteCount(area, id) {
    return tally(speciesList.filter(sp => matchesAreaFilter(sp, area) && sp.samples.some(sm => sm.site === id && (!state.regions.size || state.regions.has(sm.region)))));
}
function tripCount(area, id) {
    return tally(speciesList.filter(sp => matchesAreaFilter(sp, area) && sp.samples.some(sm => String(sm.trip_id) === id)));
}
function photographerSpeciesCount(area, name) {
    return tally(speciesList.filter(sp => matchesAreaFilter(sp, area) && sp.samples.some(sm => sm.photographer === name)));
}
function photographerCollectionCount(area, name) {
    let n = 0;
    for (const c of collectionsList) { if (!collectionMatchesArea(c, area)) continue; if (c.photographer === name) n++; }
    return n;
}
function yearCount(area, year) {
    return tally(speciesList.filter(sp => matchesAreaFilter(sp, area) && sp.samples.some(sm => String(sm.year) === year && (!state.regions.size || state.regions.has(sm.region)))));
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
    // Each value (and each "unclassified" row) holds the species cards it covers and their distinct species,
    // so the select shows "Doridina (12)" -- the number of species.
    const acc = () => ({ ids: new Set(), n: 0 });
    const add = (a, sp) => { a.ids.add(sp.species_id); a.n++; };
    const ordersUnclassified = acc(), subOrdersUnclassified = acc(), superfamiliesUnclassified = acc(), familiesUnclassified = acc();
    const bump = (map, key, sp) => { if (!map.has(key)) map.set(key, acc()); add(map.get(key), sp); };
    for (const sp of speciesList) {
        if (!matchesAreaFilter(sp, area)) continue;
        if (sp.order) bump(orders, sp.order, sp); else add(ordersUnclassified, sp);
        if (order !== 'all' && sp.order !== order) continue;
        if (sp.sub_order) bump(subOrders, sp.sub_order, sp); else add(subOrdersUnclassified, sp);
        if (subOrder !== 'all' && sp.sub_order !== subOrder) continue;
        if (sp.superfamily) bump(superfamilies, sp.superfamily, sp); else add(superfamiliesUnclassified, sp);
        if (superfamily !== 'all' && sp.superfamily !== superfamily) continue;
        if (sp.family) bump(families, sp.family, sp); else add(familiesUnclassified, sp);
        if (family !== 'all' && sp.family !== family) continue;
        if (sp.genus) bump(genera, sp.genus, sp);
    }
    return { orders, subOrders, superfamilies, families, genera, ordersUnclassified, subOrdersUnclassified, superfamiliesUnclassified, familiesUnclassified };
}

// ---- sidebar rendering ----

function areaSpeciesCount(key) {
    return tally(speciesList.filter(sp => matchesAreaFilter(sp, key)));
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
        const areaTally = areaSpeciesCount(key);
        // Only "All areas" also says how many observations the species are.
        count.textContent = key === 'all' ? observationsText(areaTally.species, areaTally.observations) : areaTally.compact;
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
    for (const [value, label, count, tip] of entries) {
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
            if (tip) row.title = tip;
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
    const accText = a => countCompact(a.ids.size);
    if (unclassifiedCount.n > 0) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = `${unclassifiedLabel} (${accText(unclassifiedCount)})`;
        select.append(opt);
        validValues.add('');
    }
    for (const v of [...counts.keys()].sort((a, b) => a.localeCompare(b))) {
        const opt = document.createElement('option');
        opt.value = v;
        opt.textContent = `${v} (${accText(counts.get(v))})`;
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
    if (t2.subOrders.size || t2.subOrdersUnclassified.n) {
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
    if (t2b.superfamilies.size || t2b.superfamiliesUnclassified.n) {
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
        .map(id => { const t = regionCount(area, id); return [id, labelFor(id, regionLabelsData), t.compact, t.title]; })
        .sort((a, b) => a[1].localeCompare(b[1], language === 'he' ? 'he' : 'en'));
    renderCheckboxGroup(document.querySelector('#regionOptions'), regionEntries, state.regions, () => { renderSidebar(); render(); });
    const multiCount = tally(speciesList.filter(sp => matchesAreaFilter(sp, area) && sp.samples.length > 1));
    renderCheckboxGroup(document.querySelector('#observationOptions'),
        [['multi', language === 'he' ? 'מינים עם מספר תצפיות' : 'Species with several observations', multiCount.compact, multiCount.title]],
        state.observations, () => {
            if (!state.sortChosen || (!multiObsOn() && state.sort === 'count')) { state.sort = defaultSort(); state.sortChosen = false; }
            syncSortControl(); render();
        });
    const siteEntries = [...opts.siteIds]
        .map(id => { const t = siteCount(area, id); return [id, labelFor(id, siteLabelsData), t.compact, t.title]; })
        .sort((a, b) => a[1].localeCompare(b[1], language === 'he' ? 'he' : 'en'));
    renderCheckboxGroup(document.querySelector('#siteOptions'), siteEntries, state.sites, () => { renderSidebar(); render(); });
    // Each photographer gets two count lines under the checkbox: species cards, then collections.
    const photographerEntries = [...opts.photographers]
        .map(name => [name, name, null])
        .sort((a, b) => a[1].localeCompare(b[1]));
    const photographerBox = document.querySelector('#photographerOptions');
    renderCheckboxGroup(photographerBox, photographerEntries, state.photographers);
    for (const row of [...photographerBox.querySelectorAll('.filter-check')]) {
        const name = row.querySelector('input').value;
        const photographerTally = photographerSpeciesCount(area, name);
        const rows = [
            [language === 'he' ? 'מינים' : 'Species', photographerTally.compact],
            [language === 'he' ? 'אוספים' : 'Collections', photographerCollectionCount(area, name)],
        ];
        let anchor = row;
        for (const [label, count, tip] of rows) {
            const sub = document.createElement('div');
            sub.className = 'filter-sub';
            const text = document.createElement('span');
            text.textContent = label;
            const small = document.createElement('small');
            small.textContent = count;
            if (tip) sub.title = tip;
            sub.append(text, small);
            anchor.after(sub);
            anchor = sub;
        }
    }
    const yearEntries = [...opts.years]
        .map(year => { const t = yearCount(area, year); return [year, year, t.compact, t.title]; })
        .sort((a, b) => Number(b[0]) - Number(a[0]));
    renderCheckboxGroup(document.querySelector('#yearOptions'), yearEntries, state.years, () => { renderSidebar(); render(); });
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
    if (state.drill && !inDrill(sp, state.drill)) return false;
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
        const hay = normalize([collectionTitle(c), c.title, c.title_en, c.year, r?.label, r?.label_en, a?.label, a?.label_en, c.photographer, photographerLabel(c)].filter(Boolean).join(' '));
        if (!hay.includes(q)) return false;
    }
    return true;
}

// ---- media / dialog ----

// The collection's gallery title in the page's language -- or the only one filled in ('' when none).
function galleryTitle(c) {
    const first = language === 'en' ? c.title_en : c.title, second = language === 'en' ? c.title : c.title_en;
    return ((first || '').trim() || (second || '').trim());
}
// What a collection is called: its gallery title, else its species count and date.
function collectionName(c) {
    return galleryTitle(c) || collectionTitle(c);
}
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
// The marks on a species card: an arrows mark when any of its observations is a photo and a triangle
// when any is a video -- both marks when it has both kinds.
function mediaMarks(samples) {
    const hasVideo = samples.some(s => s.video_id);
    const hasPhoto = samples.some(s => s.image_url) || !hasVideo;
    const mark = document.createElement('span');
    mark.setAttribute('aria-hidden', 'true');
    if (hasPhoto && hasVideo) {
        // One circle for both kinds: the triangle top-left, the arrows bottom-right.
        mark.className = 'play play-both';
        const video = document.createElement('b'); video.textContent = '▶';
        const photo = document.createElement('i'); photo.textContent = '⤢';
        mark.append(video, photo);
    } else {
        mark.className = 'play';
        mark.textContent = hasVideo ? '▶' : '⤢';
    }
    return [mark];
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
    if (video_id && window.youtubeFallback) window.youtubeFallback(media, image_url, title);
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
// The collection's gallery only: its species, filtered to that trip, without the media dialog.
function openCollectionGallery(c) {
    state.collection = String(c.trip_id);
    search.value = '';
    render();
    document.querySelector('#resultCount').scrollIntoView({ behavior: 'smooth', block: 'start' });
}
function playCollection(c, button) {
    opener = button;
    state.collection = String(c.trip_id);
    search.value = '';
    render();
    showMedia(c.video_id, c.image_url, collectionName(c), [galleryTitle(c) ? collectionTitle(c) : '', collectionSubtitle(c)].filter(Boolean).join(' · '));
    openDialog();
}

// ---- cards / grid ----

function buildCollectionCard(c, index) {
    const article = document.createElement('article');
    article.className = 'card';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'video-button';
    const title = collectionName(c);
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
    // with a gallery title, the species count and date move to a line of their own under it
    const summary = document.createElement('span');
    summary.className = 'collection-summary';
    if (galleryTitle(c)) summary.textContent = collectionTitle(c);
    const credit = document.createElement('span');
    credit.className = 'photographer';
    if (c.photographer) credit.textContent = (language === 'he' ? 'צילום: ' : 'Photography: ') + photographerLabel(c);
    const meta = document.createElement('span');
    meta.className = 'card-meta';
    const region = document.createElement('span');
    // Filtered to a single region: its name is already the filter, so don't repeat it.
    if (state.regions.size !== 1) region.textContent = labelFor(c.region, regionLabelsData);
    meta.append(region);
    info.append(h3);
    if (summary.textContent) info.append(summary);
    info.append(credit);
    info.append(meta);
    button.append(wrap, info);
    button.addEventListener('click', () => playCollection(c, button));
    // "View collection": straight to the collection's gallery, without opening its video / photo first
    // (a separate button -- a button can't sit inside the card's button; styles.css puts it on the meta line).
    const view = document.createElement('button');
    view.type = 'button';
    view.className = 'collection-view';
    view.textContent = language === 'he' ? 'צפייה באוסף' : 'View collection';
    view.setAttribute('aria-label', `${view.textContent}: ${title}`);
    view.addEventListener('click', () => openCollectionGallery(c));
    article.classList.add('collection-card');
    article.append(button, view);
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
    if (sp.slug) button.href = `/species/${sp.slug}/` + (language === 'en' ? '?lang=en' : '');
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
    wrap.append(img, ...mediaMarks(pickSamples || sp.samples));
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
// Dive trip collections are always listed by country, then chronologically (year, month) within it --
// whatever sort the species below use, alphabetical included.
function collectionCompare(a, b) {
    const loc = language === 'he' ? 'he' : 'en';
    const ca = (language === 'he' ? a.country : a.country_en) || '', cb = (language === 'he' ? b.country : b.country_en) || '';
    if (ca !== cb) return ca.localeCompare(cb, loc);
    if ((a.year || 0) !== (b.year || 0)) return (a.year || 0) - (b.year || 0);
    if ((a.month || 0) !== (b.month || 0)) return (a.month || 0) - (b.month || 0);
    return collectionName(a).localeCompare(collectionName(b), loc);
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
// ---- taxonomic drill-down ----
// Ranks, top to bottom: order (e.g. Nudibranchia), sub-order (Doridina / Cladobranchia),
// superfamily, family, genus, species. order / sub-order / superfamily are text fields on
// the species; family / genus are the curated taxon tables (by id).
const LEVELS = ['order', 'suborder', 'superfamily', 'family', 'genus', 'species'];
const levelControl = document.querySelector('.level-select');
const levelSelect = document.querySelector('#levelSelect');
function setLevel(level) {
    state.level = LEVELS.includes(level) ? level : 'order';
    levelSelect.value = state.level;
}
// The species' own value at a rank ('' when it has none).
function rankKey(sp, level) {
    switch (level) {
        case 'order': return sp.order || '';
        case 'suborder': return sp.sub_order || '';
        case 'superfamily': return sp.superfamily || '';
        case 'family': return sp.taxon_family_id ? String(sp.taxon_family_id) : '';
        case 'genus': return sp.taxon_genus_id ? String(sp.taxon_genus_id) : '';
        default: return sp.slug || sp.title;
    }
}
// The card a species falls under at a rank: its own value there, or -- when it has none
// (e.g. no sub-order outside Nudibranchia) -- the nearest rank above that it does have.
function cardKey(sp, level) {
    for (let i = LEVELS.indexOf(level); i >= 0; i--) {
        const key = rankKey(sp, LEVELS[i]);
        if (key) return { level: LEVELS[i], key };
    }
    return { level: 'species', key: rankKey(sp, 'species') };
}
function taxonEntry(level, id) {
    const dict = level === 'group' ? taxaData.orders : level === 'family' ? taxaData.families : level === 'genus' ? taxaData.genera
        : level === 'superfamily' ? taxaData.superfamilies : null;
    return dict ? dict[id] : null;
}
// The curated media of an order / sub-order card (a superfamily card's comes from taxaData.superfamilies): an order card is keyed by the order NAME, its page
// row (the one holding the defining sample) is found through order_pages; a sub-order card by the
// sub_order value of its row. Nothing found -> the card falls back to its first species' photo.
function orderRowEntry(level, key) {
    const orders = taxaData.orders || {};
    if (level === 'order') {
        const id = (taxaData.order_pages || {})[key];
        return id !== undefined ? orders[String(id)] : null;
    }
    if (level === 'suborder') return Object.values(orders).find(e => e.sub_value === key) || null;
    return null;
}
const ORDER_COMMON = { Nudibranchia: ['חשופיות', 'Nudibranchs'] };
function taxonLabel(level, key) {
    const e = taxonEntry(level, key);
    if (e) return language === 'en' ? (e.label_en || e.label) : e.label;
    if (level === 'order') {
        // A true order with a single curated group borrows that group's (named) label.
        const groups = new Set(speciesList.filter(sp => sp.order === key).map(sp => sp.taxon_order_id).filter(Boolean));
        if (groups.size === 1) return taxonLabel('group', String([...groups][0]));
        const common = ORDER_COMMON[key];
        return common ? `${key} (${language === 'en' ? common[1] : common[0]})` : key;
    }
    return key;
}
// "(7 פריטים)" after a group heading: the number of cards in the group (the gallery's item count
// lives here; #resultCount stays only for screen readers -- see styles.css).
// `species` (the cards' species cards) adds the number of species they hold: "(7 פריטים) · 250 מינים" over taxon
// cards, and just "250 מינים" over species cards (where an item is a species in an area, not a species).
function groupCount(n, species, perCard = false) {
    const span = document.createElement('span');
    span.className = 'group-count';
    const total = species ? countText(speciesIn(species)) : '';
    if (perCard && total) { span.textContent = total; span.className = ''; return span; }
    const items = language === 'he' ? `${n} פריטים` : `${n} ${n === 1 ? 'item' : 'items'}`;
    span.textContent = total ? ` (${items}) · ${total}` : ` (${items})`;
    return span;
}
function rankName(level) {
    const names = { order: ['סדרה', 'Order'], suborder: ['תת־סדרה', 'Suborder'],
        superfamily: ['על־משפחה', 'Superfamily'], family: ['משפחה', 'Family'], genus: ['סוג', 'Genus'], species: ['מין', 'Species'] };
    return (names[level] || names.species)[language === 'en' ? 1 : 0];
}
// The next rank worth showing below `level` for these species: a rank where they don't all
// share one value (or lack one) adds nothing and is skipped -- Sacoglossa has no sub-order
// and a single superfamily, so it opens straight onto its families.
function nextLevel(level, species) {
    for (let i = LEVELS.indexOf(level) + 1; i < LEVELS.length - 1; i++) {
        const keys = new Set(species.map(sp => rankKey(sp, LEVELS[i])).filter(Boolean));
        if (keys.size > 1) return LEVELS[i];
    }
    return 'species';
}
// A drilled-into taxon {level, id}, optionally narrowed to its "Others": the species with no
// value at the ranks listed in `blanks` (e.g. nudibranchs with no sub-order).
function inDrill(sp, drill) {
    if (rankKey(sp, drill.level) !== String(drill.id)) return false;
    return !(drill.blanks || []).some(rank => rankKey(sp, rank));
}
function drillMembers(drill) { return speciesList.filter(sp => inDrill(sp, drill)); }
function drillLabel(drill) {
    return taxonLabel(drill.level, drill.id) + (drill.blanks && drill.blanks.length ? ' · ' + othersLabel() : '');
}
function othersLabel() { return language === 'he' ? 'אחרים' : 'Others'; }
// The taxon one rank up from a drilled-into one: the nearest higher rank whose taxon holds
// more species than this one (ranks that add nothing are skipped, as when drilling down).
// null when the next step up is the top -- all orders.
function drillParent(drill) {
    // The "Others" of a taxon (its species with no value at some rank) goes back up to the taxon.
    if (drill.blanks && drill.blanks.length) {
        const blanks = drill.blanks.slice(0, -1);
        return blanks.length ? { level: drill.level, id: drill.id, blanks } : { level: drill.level, id: drill.id };
    }
    const members = speciesList.filter(sp => rankKey(sp, drill.level) === drill.id);
    if (!members.length) return null;
    // Among ranks holding the same species (e.g. Sacoglossa and its single superfamily),
    // the highest one is the parent -- the same taxon the visitor drilled down from.
    let parent = null, parentSize = 0;
    for (let i = LEVELS.indexOf(drill.level) - 1; i >= 0; i--) {
        const key = rankKey(members[0], LEVELS[i]);
        if (!key) continue;
        const size = speciesList.filter(sp => rankKey(sp, LEVELS[i]) === key).length;
        if (!parent && size > members.length) { parent = { level: LEVELS[i], id: key }; parentSize = size; }
        else if (parent && size === parentSize) parent = { level: LEVELS[i], id: key };
        else if (parent) break;
    }
    return parent;
}
// One card per taxon at the chosen rank holding at least one filtered species, in taxonomic
// order, with a heading for each order above it. Clicking a card drills into that taxon at
// the next informative rank. Returns the number of cards drawn.
function renderTaxonLevel(species, level, frag) {
    // Only for ranks BELOW the drilled one: at the drilled rank itself (a picked genus shown at
    // genus level) the card is the taxon itself, not a leftover.
    const drillIndex = state.drill ? LEVELS.indexOf(state.drill.level) : -1;
    // Inside a chosen taxon, a rank that none of its species has (e.g. the sub-order of Sacoglossa)
    // is skipped: the next rank down is shown instead.
    if (state.drill) {
        while (level !== 'species' && LEVELS.indexOf(level) > drillIndex && !species.some(sp => rankKey(sp, level))) {
            level = LEVELS[LEVELS.indexOf(level) + 1];
        }
    }
    grid.dataset.level = level;
    const heading = document.createElement('h2');
    heading.className = 'gallery-group-title';
    heading.textContent = rankName(level);
    frag.append(heading);
    const groups = new Map();   // keeps first-seen (= taxonomic) order
    // Below the order, a species with no value at this rank gets an "Others" card (one per order
    // when browsing every order, one in all inside a chosen taxon) instead of a card of some higher
    // rank, so every order holds all of its species. The "Others" card drills on to the next rank.
    const below = LEVELS.indexOf(level) > drillIndex;
    for (const sp of species) {
        let ck = cardKey(sp, level);
        if (below && level !== 'order' && level !== 'species' && !rankKey(sp, level)) ck = { level, key: '', others: true };
        const id = ck.others ? 'others:' + (state.drill ? '' : (sp.order || '')) : ck.level + ':' + ck.key;
        if (!groups.has(id)) groups.set(id, { ...ck, first: sp, members: [] });
        groups.get(id).members.push(sp);
    }
    // "Others" last: they are the leftovers of the taxon being browsed.
    // (inside its own order, when several orders are listed).
    const orderRank = new Map();
    for (const g of groups.values()) if (!orderRank.has(g.first.order || '')) orderRank.set(g.first.order || '', orderRank.size);
    const ordered = [...groups.values()].sort((a, b) =>
        (orderRank.get(a.first.order || '') - orderRank.get(b.first.order || '')) || ((a.others ? 1 : 0) - (b.others ? 1 : 0)));
    let prevOrder = null, n = 0;
    for (const g of ordered) {
        const order = g.first.order || '';
        if (level !== 'order' && order && order !== prevOrder) {
            const h = document.createElement('h3');
            h.className = 'taxon-level-heading';
            h.textContent = taxonLabel('order', order);
            frag.append(h);
        }
        prevOrder = order;
        frag.append(g.level === 'species' ? buildSpeciesCard(g.first, n) : buildTaxonCard(g.level, g.key, g.members, n, g.others));
        n++;
    }
    heading.append(groupCount(n, species));
    return n;
}
function buildTaxonCard(level, key, members, index, others) {
    const entry = others ? {} : (taxonEntry(level, key) || orderRowEntry(level, key) || {});
    const article = document.createElement('article');
    article.className = `card taxon-card taxon-level-${level}`;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'video-button';
    const label = others ? othersLabel() : taxonLabel(level, key);
    button.setAttribute('aria-label', `${language === 'he' ? 'הצגת' : 'Show'}: ${label}`);
    const wrap = document.createElement('span');
    wrap.className = 'image-wrap';
    const img = document.createElement('img');
    img.src = entry.thumbnail || members[0].thumbnail;
    img.alt = '';
    img.width = 640; img.height = 360;
    img.loading = index < 6 ? 'eager' : 'lazy';
    const badge = document.createElement('span');
    badge.className = 'count-badge';
    const memberTally = tally(members);
    badge.textContent = memberTally.compact;
    badge.setAttribute('aria-hidden', 'true');
    wrap.append(img, badge);
    const info = document.createElement('span');
    info.className = 'card-info';
    const h3 = document.createElement('h3');
    h3.className = 'hebrew';
    h3.textContent = label;
    const meta = document.createElement('span');
    meta.className = 'card-meta';
    const rank = document.createElement('span');
    const rankText = others ? (language === 'he' ? 'ללא ' + rankName(level) : 'No ' + rankName(level).toLowerCase()) : rankName(level);
    rank.textContent = rankText + ' · ' + countText(speciesIn(members));
    meta.append(rank);
    info.append(h3, meta);
    button.append(wrap, info);
    button.addEventListener('click', () => {
        // A genus opens its own page (description, identification, its species with their details) --
        // a fuller view than the gallery's species cards of that genus.
        if (level === 'genus' && !others && href) {
            saveGalleryView(); keepScrollInHistory();
            window.location.href = href + (language === 'en' ? '?lang=en' : '');
            return;
        }
        if (others && state.drill) state.drill = { ...state.drill, blanks: [...(state.drill.blanks || []), level] };
        else if (others) state.drill = { level: 'order', id: members[0].order || '', blanks: [level] };
        else state.drill = { level, id: String(key) };
        setLevel(nextLevel(level, members));
        render();
        document.querySelector('#resultCount').scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    article.append(button);
    // The taxon's own page, as a separate link (a link can't sit inside the drill button).
    // Every rank has its own page: family / genus by name, order / sub-order / superfamily by the id of their
    // row in the orders table (an order's page is that of its base row, see order_pages).
    let href = '';
    if (others) href = '';
    else if ((level === 'family' || level === 'genus') && entry.name) href = `/${level}/${encodeURIComponent(entry.name)}/`;
    else if ((level === 'suborder' || level === 'superfamily') && entry.pk) href = `/order/${entry.pk}/`;
    else if (level === 'order') {
        // The order's own page lists every species of the order, whichever curated group they sit in.
        const pageId = (taxaData.order_pages || {})[key];
        if (pageId) href = `/order/${pageId}/`;
        else {
            const groups = new Set(members.map(sp => sp.taxon_order_id).filter(Boolean));
            if (groups.size === 1) href = `/order/${[...groups][0]}/`;
        }
    }
    if (href) {
        const page = document.createElement('a');
        page.className = 'taxon-card-page';
        page.href = href + (language === 'en' ? '?lang=en' : '');
        page.textContent = language === 'he' ? 'לדף ↗' : 'Page ↗';
        article.append(page);
    }
    return article;
}
levelSelect.addEventListener('change', e => { setLevel(e.target.value); render(); });

// ---- remembering the gallery view ----
// The pages of the taxa (order ... genus) and of the species have a "back to the gallery" button that comes back
// to "/?restore=1": the gallery then returns to the view the visitor left -- the same rank and taxon, the same
// filters, search and place on the page. The view lives in this tab's sessionStorage; a plain visit to "/" is
// always a fresh gallery.
const GALLERY_VIEW_KEY = 'seaslugs-gallery-view';
const GALLERY_VIEW_SETS = ['regions', 'sites', 'photographers', 'years', 'observations'];
function saveGalleryView() {
    try {
        const saved = { ...state };
        GALLERY_VIEW_SETS.forEach(k => { saved[k] = [...state[k]]; });
        sessionStorage.setItem(GALLERY_VIEW_KEY, JSON.stringify({ state: saved, search: search.value, scrollY: window.scrollY }));
    } catch (_) {}
}
// Applies the saved view when the page was opened with ?restore=1; returns the scroll position to go back to.
function restoreGalleryView() {
    const params = new URLSearchParams(window.location.search);
    if (!params.has('restore')) return null;
    params.delete('restore');
    const query = params.toString();
    window.history.replaceState(null, '', window.location.pathname + (query ? '?' + query : '') + window.location.hash);
    let saved = null;
    try { saved = JSON.parse(sessionStorage.getItem(GALLERY_VIEW_KEY)); } catch (_) {}
    if (!saved || !saved.state) return null;
    Object.assign(state, saved.state);
    GALLERY_VIEW_SETS.forEach(k => { state[k] = new Set(saved.state[k] || []); });
    search.value = saved.search || '';
    syncSortControl();
    levelSelect.value = state.level;
    return saved.scrollY || 0;
}
window.addEventListener('pagehide', () => { saveGalleryView(); keepScrollInHistory(); });

// ---- "back to the gallery" from a page: one level up ----
// A species / genus / family / order page links back to "/?up=<rank>:<key>" (e.g. up=genus:12): the gallery
// opens in the taxonomic view one rank above that page's taxon -- among its siblings, e.g. the genera of its
// family -- keeping the visitor's area and filters unless they would hide that taxon.
const FRESH_VIEW = { ...state, regions: null, sites: null, photographers: null, years: null, observations: null };
let upFocus = null;      // the card to bring into view once the gallery is drawn
function applyUpParam() {
    const params = new URLSearchParams(window.location.search);
    const up = params.get('up');
    if (!up) return false;
    params.delete('up');
    const query = params.toString();
    window.history.replaceState(null, '', window.location.pathname + (query ? '?' + query : '') + window.location.hash);
    const cut = up.indexOf(':');
    const from = { level: up.slice(0, cut), id: up.slice(cut + 1) };
    if (cut < 1 || !LEVELS.includes(from.level) || from.level === 'species') return false;
    const parent = drillParent(from);
    state.sort = 'taxonomic'; state.sortChosen = true; state.collection = null;
    search.value = '';
    state.drill = parent;
    setLevel(parent ? nextLevel(parent.level, drillMembers(parent)) : 'order');
    // filters that would hide the taxon itself are dropped
    if (!speciesList.some(sp => rankKey(sp, from.level) === from.id && speciesMatches(sp, ''))) {
        Object.keys(FRESH_VIEW).forEach(k => { if (FRESH_VIEW[k] !== null && !['sort', 'sortChosen', 'drill', 'level'].includes(k)) state[k] = FRESH_VIEW[k]; });
        GALLERY_VIEW_SETS.forEach(k => { state[k] = new Set(); });
    }
    syncSortControl();
    levelSelect.value = state.level;
    upFocus = from;
    return true;
}
// After drawing: scroll to the card of the taxon the visitor came from (its page link).
function focusUpCard() {
    if (!upFocus) return;
    const from = upFocus; upFocus = null;
    const entry = taxonEntry(from.level, from.id);
    let link = null;
    if ((from.level === 'family' || from.level === 'genus') && entry && entry.name) link = document.querySelector(`.taxon-card-page[href^="/${from.level}/${encodeURIComponent(entry.name)}/"]`);
    const card = link ? link.closest('article') : null;
    window.requestAnimationFrame(() => (card || document.querySelector('#resultCount')).scrollIntoView({ block: card ? 'center' : 'start' }));
}

// ---- the browser's back / forward buttons ----
// Every change of view (area, sort, level, a taxon clicked into, filters) is its own entry in the browser's
// history, so "back" returns to the previous view of the gallery. The entry keeps the view and the place on the
// page, so coming back from a species / taxon page with "back" also lands on the view that was left. Typing in
// the search box updates the current entry rather than adding one per keystroke.
if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
let applyingHistory = false;
function galleryEntry() {
    const saved = { ...state };
    GALLERY_VIEW_SETS.forEach(k => { saved[k] = [...state[k]]; });
    return { state: saved, search: search.value };
}
function sameView(a, b) {
    return !!a && !!b && JSON.stringify(a.state) === JSON.stringify(b.state);
}
function keepScrollInHistory() {
    const entry = history.state && history.state.gallery;
    if (entry) history.replaceState({ ...history.state, gallery: { ...entry, scrollY: window.scrollY } }, '', window.location.href);
}
function recordGalleryHistory() {
    if (applyingHistory) return;
    const entry = galleryEntry();
    const current = history.state && history.state.gallery;
    if (!current || sameView(current, entry)) {
        // first render, or the search text only: update this entry in place
        history.replaceState({ ...(history.state || {}), gallery: { ...entry, scrollY: current ? current.scrollY || 0 : 0 } }, '', window.location.href);
        return;
    }
    keepScrollInHistory();
    history.pushState({ gallery: { ...entry, scrollY: 0 } }, '', window.location.href);
}
function applyGalleryEntry(entry) {
    Object.assign(state, entry.state);
    GALLERY_VIEW_SETS.forEach(k => { state[k] = new Set(entry.state[k] || []); });
    search.value = entry.search || '';
    syncSortControl();
    levelSelect.value = state.level;
}
window.addEventListener('popstate', e => {
    const entry = e.state && e.state.gallery;
    if (!entry || !entry.state) return;
    applyGalleryEntry(entry);
    applyingHistory = true;
    try { renderSidebar(); render(); } finally { applyingHistory = false; }
    window.requestAnimationFrame(() => window.scrollTo(0, entry.scrollY || 0));
});
// The page was loaded again for an entry that already has a view (back / forward from another page, or a reload).
function restoreFromHistory() {
    const entry = history.state && history.state.gallery;
    if (!entry || !entry.state) return null;
    applyGalleryEntry(entry);
    return entry.scrollY || 0;
}

function render() {
    updateCollectionStatus();
    const q = normalize(search.value);
    searchByName = !!q && speciesList.some(sp => speciesNameMatches(sp, q));
    // The taxonomic view browses taxa, not dive-trip collections; the level selector applies
    // to it under every filter, a single dive trip's collection included.
    const taxonomic = state.sort === 'taxonomic';
    const level = taxonomic ? state.level : 'species';
    levelControl.hidden = !taxonomic;
    const filteredCollections = taxonomic ? [] : collectionsList.filter(c => collectionMatches(c, q)).sort(collectionCompare);
    let filteredSpecies = speciesList.filter(sp => speciesMatches(sp, q));
    if (state.sort === 'alpha') filteredSpecies = [...filteredSpecies].sort(speciesSortCompare);
    if (state.sort === 'year') filteredSpecies = [...filteredSpecies].sort(speciesYearCompare);
    if (state.sort === 'count') filteredSpecies = [...filteredSpecies].sort(speciesCountCompare);
    grid.replaceChildren();
    grid.dataset.level = '';       // set by renderTaxonLevel: the rank the cards are of (styles.css sizes them by it)
    const frag = document.createDocumentFragment();
    if (filteredCollections.length) {
        const heading = document.createElement('h2');
        heading.className = 'gallery-group-title';
        heading.textContent = language === 'he' ? 'אוספי מסעות צלילה' : 'Dive trip collections';
        frag.append(heading);
        filteredCollections.forEach((c, i) => frag.append(buildCollectionCard(c, i)));
        heading.append(groupCount(filteredCollections.length));
    }
    let cardCount = filteredSpecies.length;
    if (filteredSpecies.length && level !== 'species') {
        cardCount = renderTaxonLevel(filteredSpecies, level, frag);
    } else if (filteredSpecies.length) {
        const heading = document.createElement('h2');
        heading.className = 'gallery-group-title';
        // Each card is one observation: the heading says how many species and observations they are.
        heading.append(groupCount(filteredSpecies.length, filteredSpecies, true));
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
    const total = cardCount + filteredCollections.length;
    document.querySelector('#resultCount').textContent = language === 'he' ? `${total} פריטים` : `${total} ${total === 1 ? 'item' : 'items'}`;
    document.querySelector('#empty').hidden = total > 0;
    updateFilterToggleCount();
    saveGalleryView();
    recordGalleryHistory();
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
const SUGGEST_KINDS = { order: 0, suborder: 1, superfamily: 2, family: 3, genus: 4, species: 5, common: 6, site: 7, region: 8 };
function suggestKindLabel(kind) {
    const he = { common: 'שם עממי', order: 'סדרה', suborder: 'תת־סדרה', superfamily: 'על־משפחה', genus: 'סוג', family: 'משפחה', site: 'אתר צלילה', region: 'אזור צלילה' };
    const en = { common: 'Common name', order: 'Order', suborder: 'Suborder', superfamily: 'Superfamily', genus: 'Genus', family: 'Family', site: 'Dive site', region: 'Dive region' };
    return (language === 'he' ? he : en)[kind] || '';
}
function buildSuggestCandidates() {
    const out = new Map();   // dedupe by kind + text
    const add = (kind, text, extra = {}) => {
        if (!text) return;
        const key = kind + '|' + normalize(text);
        const prev = out.get(key);
        if (prev) { prev.slugs.add(extra.slug); return; }
        out.set(key, { kind, text, norm: normalize(text), slugs: new Set([extra.slug]), latin: !!extra.latin, id: extra.id });
    };
    for (const sp of speciesList) {
        add('species', sp.title, { slug: sp.slug, latin: true });
        const common = language === 'he' ? sp.name_he : sp.name_en;
        if (common) add('common', common, { slug: sp.slug });
        add('genus', sp.genus, { latin: true, id: sp.taxon_genus_id });
        add('family', sp.family, { id: sp.taxon_family_id });
    }
    const lbl = e => e && (language === 'en' ? (e.label_en || e.label) : e.label);
    for (const id in siteLabelsData) add('site', lbl(siteLabelsData[id]));
    for (const sp of speciesList) {
        add('order', sp.order, { latin: true, id: sp.order });
        add('suborder', sp.sub_order, { latin: true, id: sp.sub_order });
        add('superfamily', sp.superfamily, { latin: true, id: sp.superfamily });
    }
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
    if (['order', 'suborder', 'superfamily', 'family', 'genus'].includes(c.kind) && c.id) {
        // A taxon: show that taxon itself, at its own rank (the drill-down's starting point).
        search.value = '';
        state.drill = { level: c.kind, id: String(c.id) };
        setLevel(c.kind);
    } else {
        search.value = c.text;
        setLevel('species');
    }
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
document.querySelector('#total').textContent = `(${countText(speciesIn(speciesList))})`;
// Typing a name searches species, so the view switches to the species level.
search.addEventListener('input', () => { if (search.value.trim() && state.level !== 'species') setLevel('species'); render(); });
document.querySelector('#reset').addEventListener('click', () => {
    search.value = '';
    state.area = 'all'; state.regions.clear(); state.sites.clear(); state.photographers.clear(); state.years.clear(); state.observations.clear();
    state.order = 'all'; state.subOrder = 'all'; state.superfamily = 'all'; state.family = 'all'; state.genus = 'all'; state.collection = null;
    state.sort = 'taxonomic'; state.sortChosen = false; syncSortControl();
    state.drill = null; setLevel('order');
    renderSidebar(); render(); search.focus();
});
document.querySelector('#orderSelect').addEventListener('change', e => { if (e.target.value !== 'all') setLevel('order'); state.order = e.target.value; state.subOrder = 'all'; state.superfamily = 'all'; state.family = 'all'; state.genus = 'all'; renderTaxonomySelects(); render(); });
document.querySelector('#subOrderSelect').addEventListener('change', e => { if (e.target.value !== 'all') setLevel('suborder'); state.subOrder = e.target.value; state.superfamily = 'all'; state.family = 'all'; state.genus = 'all'; renderTaxonomySelects(); render(); });
document.querySelector('#superfamilySelect').addEventListener('change', e => { if (e.target.value !== 'all') setLevel('superfamily'); state.superfamily = e.target.value; state.family = 'all'; state.genus = 'all'; renderTaxonomySelects(); render(); });
document.querySelector('#familySelect').addEventListener('change', e => { if (e.target.value !== 'all') setLevel('family'); state.family = e.target.value; state.genus = 'all'; renderTaxonomySelects(); render(); });
document.querySelector('#genusSelect').addEventListener('change', e => { if (e.target.value !== 'all') setLevel('genus'); state.genus = e.target.value; render(); });
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
    ['.search > span', 'Search'],
    ['.sort-order > span', 'Sort'],
    ['#empty h3', 'No items found'],
    ['#empty p', 'Try a different name or choose another region.'],
    ['#reset', 'Clear search and filters'],
    ['footer p', 'Photography: Boaz Liebes · Videos hosted on YouTube'],
    ['.footer-tagline', 'Sea slugs, up close.'],
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
// The home page's text sections (hero, "what are sea slugs", the project, how to contribute, the
// numbers line, the link block, the footer invitation) are rendered by the server in the language of the
// URL; both languages are embedded as JSON so the language button can swap them without a reload
// (observations/home_content.py). A section is only replaced when it is in the other language.
const homeContent = JSON.parse(document.getElementById('home-content').textContent);
function applyHomeSections() {
    document.querySelectorAll('[data-home-section]').forEach(element => {
        if (element.dataset.lang !== language) {
            const html = (homeContent[language] || {})[element.dataset.homeSection];
            if (html != null) {
                element.innerHTML = html;
                element.dataset.lang = language;
            }
        }
    });
}
document.addEventListener('click', event => {
    const link = event.target.closest('[data-home-action="migrant"]');
    if (!link) return;
    // The link also jumps to the gallery (its href); here the migrant-species view is switched on.
    document.querySelector('#areaFilters button[data-area="migrant"]')?.click();
});
const collectionHeading = document.querySelector('#collectionTitle').firstChild;
const originalCollectionHeading = collectionHeading.textContent;
const description = document.querySelector('meta[name="description"]');
const seoText = JSON.parse(document.getElementById('seo-text').textContent);
const languageButton = document.createElement('button');
languageButton.type = 'button';
languageButton.className = 'language-switch';
document.querySelector('.masthead').append(languageButton);

// The visitor's language is remembered in the same cookie the server-rendered pages read (seaslugs_lang), so
// moving between the gallery, the trips, the observations and the profile pages keeps the language whichever page
// the button was pressed on. (localStorage is kept as a fallback for browsers that refuse cookies.)
function readLanguageCookie() {
    const match = document.cookie.match(/(?:^|;\s*)seaslugs_lang=(he|en)/);
    return match ? match[1] : null;
}
function rememberLanguage(value) {
    try { document.cookie = `seaslugs_lang=${value}; path=/; max-age=31536000; SameSite=Lax`; } catch (_) {}
    try { localStorage.setItem('seaslugs-language', value); } catch (_) {}
}
// The links of the main navigation were rendered for the page's first language: point them at the current one.
function keepMenuLinksInLanguage() {
    document.querySelectorAll('.account-menu a[href^="/"]').forEach(link => {
        const url = new URL(link.getAttribute('href'), window.location.origin);
        if (language === 'en') url.searchParams.set('lang', 'en'); else url.searchParams.delete('lang');
        link.setAttribute('href', url.pathname + url.search + url.hash);
    });
}

function setLanguage(value) {
    language = value === 'en' ? 'en' : 'he';
    const en = language === 'en';
    document.documentElement.lang = language;
    document.documentElement.dir = en ? 'ltr' : 'rtl';
    translations.forEach(item => {
        if (en) item.element.textContent = item.en;
        else item.element.replaceChildren(...Array.from(item.he.childNodes, node => node.cloneNode(true)));
    });
    applyHomeSections();
    // The main navigation (observations/templates/observations/account_menu.html) carries both languages.
    document.querySelectorAll('.account-menu [data-he][data-en]').forEach(element => {
        element.textContent = en ? element.dataset.en : element.dataset.he;
    });
    document.querySelectorAll('.account-menu [data-aria-he][data-aria-en]').forEach(element => {
        element.setAttribute('aria-label', en ? element.dataset.ariaEn : element.dataset.ariaHe);
    });
    document.querySelectorAll('.account-menu [data-title-he][data-title-en]').forEach(element => {
        element.title = en ? element.dataset.titleEn : element.dataset.titleHe;
    });
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
    levelControl.querySelector('span').textContent = en ? 'Level' : 'רמה';
    levelSelect.setAttribute('aria-label', en ? 'Gallery level' : 'רמת התצוגה');
    LEVELS.forEach(v => { levelSelect.querySelector(`option[value="${v}"]`).textContent = rankName(v); });
    countSortOption.textContent = en ? 'Number of observations (most first)' : 'מספר תצפיות (מהגדול לקטן)';
    yearSortOption.textContent = en ? 'Observation year (earliest first)' : 'שנת תצפית (מהמוקדם למאוחר)';
    languageButton.textContent = en ? 'עברית' : 'English';
    languageButton.lang = en ? 'he' : 'en';
    languageButton.setAttribute('aria-label', en ? 'Switch to Hebrew' : 'מעבר לאנגלית');
    // The title and description of each language come from the page itself (observations/home_text.py),
    // so what the server rendered and what the button swaps in are the same text.
    document.title = seoText[language].title;
    description.content = seoText[language].description;
    const url = new URL(window.location.href);
    url.searchParams.set('lang', language);
    window.history.replaceState(window.history.state, '', url);
    rememberLanguage(language);
    keepMenuLinksInLanguage();
    renderSidebar();
    render();
}
languageButton.addEventListener('click', () => setLanguage(language === 'he' ? 'en' : 'he'));
let preferredLanguage = 'he';
try { preferredLanguage = localStorage.getItem('seaslugs-language') || 'he'; } catch (_) {}
let restoredScroll = restoreGalleryView();
if (applyUpParam()) restoredScroll = null;
else if (restoredScroll === null) restoredScroll = restoreFromHistory();
setLanguage(new URLSearchParams(window.location.search).get('lang') || readLanguageCookie() || preferredLanguage);
if (restoredScroll) window.requestAnimationFrame(() => window.scrollTo(0, restoredScroll));
focusUpCard();
