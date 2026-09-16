'use strict';
const catalog = window.SEASLUGS || {};
const speciesList = catalog.species || [];
const collectionsList = catalog.collections || [];
const areaLabelsData = catalog.areas || {};
const regionLabelsData = catalog.regions || {};
const siteLabelsData = catalog.sites || {};

let language = 'he';

const grid = document.querySelector('#grid');
const search = document.querySelector('#search');
const dialog = document.querySelector('#player');

const state = {
    area: 'all',
    regions: new Set(),
    sites: new Set(),
    photographers: new Set(),
    order: 'all',
    family: 'all',
    genus: 'all',
    collection: null,
};

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

const collectionStatus = document.createElement('div');
collectionStatus.className = 'collection-selection';
grid.before(collectionStatus);

function updateCollectionStatus() {
    collectionStatus.replaceChildren();
    if (!state.collection) return;
    const c = collectionsList.find(x => String(x.trip_id) === state.collection);
    const label = document.createElement('span');
    label.textContent = (language === 'he' ? 'מינים באוסף: ' : 'Species in collection: ') + (c ? collectionTitle(c) : '');
    const back = document.createElement('button');
    back.type = 'button';
    back.textContent = language === 'he' ? 'חזרה לכל הגלריה' : 'Back to full gallery';
    back.addEventListener('click', () => { state.collection = null; render(); });
    collectionStatus.append(label, back);
}

// ---- option scoping ----

function optionsForArea(area) {
    const regionIds = new Set(), siteIds = new Set(), photographers = new Set();
    for (const sp of speciesList) {
        if (area !== 'all' && sp.area !== area) continue;
        for (const sm of sp.samples) {
            regionIds.add(sm.region);
            if (sm.site) siteIds.add(sm.site);
            if (sm.photographer) photographers.add(sm.photographer);
        }
    }
    for (const c of collectionsList) {
        if (area !== 'all' && c.area !== area) continue;
        regionIds.add(c.region);
        if (c.photographer) photographers.add(c.photographer);
    }
    return { regionIds, siteIds, photographers };
}
function regionCount(area, id) {
    return speciesList.filter(sp => (area === 'all' || sp.area === area) && sp.samples.some(sm => sm.region === id)).length;
}
function siteCount(area, id) {
    return speciesList.filter(sp => (area === 'all' || sp.area === area) && sp.samples.some(sm => sm.site === id)).length;
}
function photographerCount(area, name) {
    let n = 0;
    for (const sp of speciesList) { if (area !== 'all' && sp.area !== area) continue; if (sp.samples.some(sm => sm.photographer === name)) n++; }
    for (const c of collectionsList) { if (area !== 'all' && c.area !== area) continue; if (c.photographer === name) n++; }
    return n;
}
function taxonomyOptions(area, order, family) {
    const orders = new Set(), families = new Set(), genera = new Set();
    for (const sp of speciesList) {
        if (area !== 'all' && sp.area !== area) continue;
        if (sp.order) orders.add(sp.order);
        if (order !== 'all' && sp.order !== order) continue;
        if (sp.family) families.add(sp.family);
        if (family !== 'all' && sp.family !== family) continue;
        if (sp.genus) genera.add(sp.genus);
    }
    return { orders, families, genera };
}

// ---- sidebar rendering ----

function areaSpeciesCount(key) {
    return key === 'all' ? speciesList.length : speciesList.filter(sp => sp.area === key).length;
}
function renderAreaFilters() {
    const container = document.querySelector('#areaFilters');
    container.replaceChildren();
    const entries = [['all', language === 'he' ? 'כל האזורים' : 'All areas'], ...Object.keys(areaLabelsData).map(k => [k, areaLabelFor(k)])];
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
            state.regions.clear(); state.sites.clear(); state.photographers.clear();
            state.order = 'all'; state.family = 'all'; state.genus = 'all';
            renderSidebar(); render();
        });
        container.append(b);
    }
}
function renderCheckboxGroup(container, entries, selectedSet) {
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
            render();
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
function fillSelect(select, values, current, allLabel) {
    select.replaceChildren();
    const allOpt = document.createElement('option');
    allOpt.value = 'all';
    allOpt.textContent = allLabel;
    select.append(allOpt);
    const sorted = [...values].sort((a, b) => a.localeCompare(b));
    for (const v of sorted) {
        const opt = document.createElement('option');
        opt.value = v;
        opt.textContent = v;
        select.append(opt);
    }
    select.value = sorted.includes(current) ? current : 'all';
}
function renderTaxonomySelects() {
    const area = state.area;
    const t1 = taxonomyOptions(area, 'all', 'all');
    const orderSelect = document.querySelector('#orderSelect');
    fillSelect(orderSelect, t1.orders, state.order, language === 'he' ? 'כל הסדרות' : 'All orders');
    if (orderSelect.value !== state.order) state.order = 'all';
    const t2 = taxonomyOptions(area, state.order, 'all');
    const familySelect = document.querySelector('#familySelect');
    fillSelect(familySelect, t2.families, state.family, language === 'he' ? 'כל המשפחות' : 'All families');
    if (familySelect.value !== state.family) state.family = 'all';
    const t3 = taxonomyOptions(area, state.order, state.family);
    const genusSelect = document.querySelector('#genusSelect');
    fillSelect(genusSelect, t3.genera, state.genus, language === 'he' ? 'כל הסוגים' : 'All genera');
    if (genusSelect.value !== state.genus) state.genus = 'all';
}
function renderSidebar() {
    renderAreaFilters();
    const area = state.area;
    const opts = optionsForArea(area);
    const regionEntries = [...opts.regionIds]
        .map(id => [id, labelFor(id, regionLabelsData), regionCount(area, id)])
        .sort((a, b) => a[1].localeCompare(b[1], language === 'he' ? 'he' : 'en'));
    renderCheckboxGroup(document.querySelector('#regionOptions'), regionEntries, state.regions);
    const siteEntries = [...opts.siteIds]
        .map(id => [id, labelFor(id, siteLabelsData), siteCount(area, id)])
        .sort((a, b) => a[1].localeCompare(b[1], language === 'he' ? 'he' : 'en'));
    renderCheckboxGroup(document.querySelector('#siteOptions'), siteEntries, state.sites);
    const photographerEntries = [...opts.photographers]
        .map(name => [name, name, photographerCount(area, name)])
        .sort((a, b) => a[1].localeCompare(b[1]));
    renderCheckboxGroup(document.querySelector('#photographerOptions'), photographerEntries, state.photographers);
    renderTaxonomySelects();
}

// ---- matching / search ----

function sampleMatchesGeo(sm) {
    if (state.regions.size && !state.regions.has(sm.region)) return false;
    if (state.sites.size && !(sm.site && state.sites.has(sm.site))) return false;
    if (state.photographers.size && !state.photographers.has(sm.photographer)) return false;
    return true;
}
function speciesSearchText(sp) {
    const parts = [sp.title, sp.name_he, sp.name_en, sp.genus, sp.family, sp.order, areaLabelsData[sp.area]?.label, areaLabelsData[sp.area]?.label_en];
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
    if (state.area !== 'all' && sp.area !== state.area) return false;
    if (state.order !== 'all' && sp.order !== state.order) return false;
    if (state.family !== 'all' && sp.family !== state.family) return false;
    if (state.genus !== 'all' && sp.genus !== state.genus) return false;
    if ((state.regions.size || state.sites.size || state.photographers.size) && !sp.samples.some(sampleMatchesGeo)) return false;
    if (q && !speciesSearchText(sp).includes(q)) return false;
    return true;
}
function collectionMatches(c, q) {
    if (state.collection) return false;
    if (state.area !== 'all' && c.area !== state.area) return false;
    if (state.regions.size && !state.regions.has(c.region)) return false;
    if (state.sites.size) return false;
    if (state.photographers.size && !state.photographers.has(c.photographer)) return false;
    if (state.order !== 'all' || state.family !== 'all' || state.genus !== 'all') return false;
    if (q) {
        const r = regionLabelsData[c.region];
        const a = areaLabelsData[c.area];
        const hay = normalize([c.title, r?.label, r?.label_en, a?.label, a?.label_en, c.photographer].filter(Boolean).join(' '));
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
    const credit = sm.photographer ? `${language === 'he' ? 'צילום: ' : 'Photography: '}${sm.photographer}` : '';
    return [location, credit].filter(Boolean).join(' · ');
}
function collectionSubtitle(c) {
    const regionText = labelFor(c.region, regionLabelsData);
    const credit = c.photographer ? `${language === 'he' ? 'צילום: ' : 'Photography: '}${c.photographer}` : '';
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
    if (species.samples.length <= 1) {
        playSampleOf(species, species.samples[0], button);
        return;
    }
    document.querySelector('#playerTitle').textContent = species.title;
    document.querySelector('#playerRegion').textContent = language === 'he' ? `${species.samples.length} תצפיות — לבחירה מהרשימה` : `${species.samples.length} observations — choose from the list`;
    document.querySelector('#frame').hidden = true;
    document.querySelector('.player-bottom').hidden = true;
    const list = document.querySelector('#pickerList');
    list.replaceChildren();
    for (const sm of species.samples) {
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
    if (c.photographer) credit.textContent = (language === 'he' ? 'צילום: ' : 'Photography: ') + c.photographer;
    const meta = document.createElement('span');
    meta.className = 'card-meta';
    const region = document.createElement('span');
    region.textContent = labelFor(c.region, regionLabelsData);
    const label = document.createElement('span');
    label.textContent = language === 'he' ? 'צפייה באוסף' : 'View collection';
    meta.append(region, label);
    info.append(h3, credit, meta);
    button.append(wrap, info);
    button.addEventListener('click', () => playCollection(c, button));
    article.append(button);
    return article;
}
function buildSpeciesCard(sp, index) {
    const article = document.createElement('article');
    article.className = 'card';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'video-button';
    const common = language === 'he' ? (sp.name_he || sp.name_en) : (sp.name_en || sp.name_he);
    button.setAttribute('aria-label', `${language === 'he' ? 'צפייה' : 'Watch'}: ${sp.title}${common ? ' — ' + common : ''}`);
    const wrap = document.createElement('span');
    wrap.className = 'image-wrap';
    const img = document.createElement('img');
    img.src = sp.thumbnail;
    img.alt = '';
    img.width = 640; img.height = 360;
    img.loading = index < 6 ? 'eager' : 'lazy';
    img.decoding = 'async';
    const icon = document.createElement('span');
    icon.className = 'play';
    icon.textContent = sp.video_id ? '▶' : '⤢';
    icon.setAttribute('aria-hidden', 'true');
    wrap.append(img, icon);
    if (sp.samples.length > 1) {
        const badge = document.createElement('span');
        badge.className = 'count-badge';
        badge.textContent = sp.samples.length;
        badge.setAttribute('aria-hidden', 'true');
        wrap.append(badge);
    }
    const info = document.createElement('span');
    info.className = 'card-info';
    const h3 = document.createElement('h3');
    h3.textContent = sp.title;
    const sub = document.createElement('span');
    sub.className = 'common-name';
    if (common) sub.textContent = common;
    const credit = document.createElement('span');
    credit.className = 'photographer';
    if (sp.samples.length === 1 && sp.samples[0].photographer) {
        credit.textContent = (language === 'he' ? 'צילום: ' : 'Photography: ') + sp.samples[0].photographer;
    }
    const meta = document.createElement('span');
    meta.className = 'card-meta';
    const area = document.createElement('span');
    area.textContent = areaLabelFor(sp.area);
    const label = document.createElement('span');
    label.textContent = sp.samples.length > 1
        ? (language === 'he' ? `${sp.samples.length} תצפיות` : `${sp.samples.length} observations`)
        : (language === 'he' ? 'לצפייה' : 'Watch');
    meta.append(area, label);
    info.append(h3);
    if (common) info.append(sub);
    info.append(credit, meta);
    button.append(wrap, info);
    button.addEventListener('click', () => openSpeciesDialog(sp, button));
    article.append(button);
    return article;
}
function render() {
    updateCollectionStatus();
    const q = normalize(search.value);
    const filteredCollections = collectionsList.filter(c => collectionMatches(c, q));
    const filteredSpecies = speciesList.filter(sp => speciesMatches(sp, q));
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
        filteredSpecies.forEach((sp, i) => frag.append(buildSpeciesCard(sp, i)));
    }
    grid.append(frag);
    const total = filteredSpecies.length + filteredCollections.length;
    document.querySelector('#resultCount').textContent = language === 'he' ? `${total} פריטים` : `${total} ${total === 1 ? 'item' : 'items'}`;
    document.querySelector('#empty').hidden = total > 0;
}

document.querySelector('#total').textContent = `(${speciesList.length})`;
search.addEventListener('input', render);
document.querySelector('#reset').addEventListener('click', () => {
    search.value = '';
    state.area = 'all'; state.regions.clear(); state.sites.clear(); state.photographers.clear();
    state.order = 'all'; state.family = 'all'; state.genus = 'all'; state.collection = null;
    renderSidebar(); render(); search.focus();
});
document.querySelector('#orderSelect').addEventListener('change', e => { state.order = e.target.value; state.family = 'all'; state.genus = 'all'; renderTaxonomySelects(); render(); });
document.querySelector('#familySelect').addEventListener('change', e => { state.family = e.target.value; state.genus = 'all'; renderTaxonomySelects(); render(); });
document.querySelector('#genusSelect').addEventListener('change', e => { state.genus = e.target.value; render(); });
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
    ['#empty h3', 'No items found'],
    ['#empty p', 'Try a different name or choose another region.'],
    ['#reset', 'Clear search and filters'],
    ['footer p', 'Photography: Boaz Liebes · Videos hosted on YouTube'],
    ['footer > span:last-child', 'Sea slugs, up close.'],
    ['.player-bottom > span', 'If the video does not load, watch it on YouTube.'],
    ['#youtubeLink', 'Watch on YouTube ↗'],
    ['#filterSidebarTitle', 'Filters'],
    ['#areaGroupTitle', 'Area'],
    ['#regionGroupTitle', 'Dive region'],
    ['#siteGroupTitle', 'Dive site'],
    ['#photographerGroupTitle', 'Photographer'],
    ['#orderGroupTitle', 'Order'],
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
