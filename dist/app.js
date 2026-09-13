'use strict';
const videos=window.SEASLUGS.videos;
const regions={...window.SEASLUGS.regions};
let language="he";
const englishRegions={...window.SEASLUGS.regions_en};
const filters=document.querySelector('.filters');
filters.replaceChildren();
for(const [key,label] of [['all','כל האזורים'],...Object.entries(regions)]){const b=document.createElement('button');b.type='button';b.className='filter';b.dataset.region=key;b.textContent=label;filters.append(b)}
const grid=document.querySelector('#grid');
const search=document.querySelector('#search');
const dialog=document.querySelector('#player');
let selected='all';let opener=null;
const videoTitle=v=>language==='en' && v.title==='קניון אכזיב יולי 23' ? 'Akhziv Canyon · July 2023' : v.title;
const normalize=s=>s.normalize('NFKC').toLocaleLowerCase().replace(/\s+/g,' ').trim();
document.querySelector('#total').textContent=`(${videos.length})`;
for(const b of document.querySelectorAll('[data-region]')){const n=b.dataset.region==='all'?videos.length:videos.filter(v=>v.region===b.dataset.region).length;const count=document.createElement('small');count.textContent=n;b.append(count);b.addEventListener('click',()=>{selected=b.dataset.region;render()})}
function play(v,button){opener=button;document.querySelector('#playerTitle').textContent=videoTitle(v);document.querySelector('#playerRegion').textContent=regions[v.region];document.querySelector('#youtubeLink').href=`https://www.youtube.com/watch?v=${v.id}`;const frame=document.createElement('iframe');frame.src=`https://www.youtube-nocookie.com/embed/${encodeURIComponent(v.id)}?autoplay=1&rel=0`;frame.title=videoTitle(v);frame.allow='accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share';frame.allowFullscreen=true;frame.referrerPolicy='strict-origin-when-cross-origin';document.querySelector('#frame').replaceChildren(frame);dialog.showModal();document.body.style.overflow='hidden'}
function render(){const q=normalize(search.value);const found=videos.filter(v=>(selected==='all'||v.region===selected)&&normalize(videoTitle(v)+' '+v.title+' '+regions[v.region]+' '+englishRegions[v.region]+' '+window.SEASLUGS.regions[v.region]).includes(q));for(const b of document.querySelectorAll('[data-region]')){const active=b.dataset.region===selected;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active))}grid.replaceChildren();const frag=document.createDocumentFragment();found.forEach((v,index)=>{const article=document.createElement('article');article.className='card';const button=document.createElement('button');button.type='button';button.className='video-button';button.setAttribute('aria-label',`${language==='he'?'צפייה':'Watch'}: ${videoTitle(v)} — ${regions[v.region]}`);const wrap=document.createElement('span');wrap.className='image-wrap';const img=document.createElement('img');img.src=v.thumbnail;img.alt='';img.width=640;img.height=360;img.loading=index<6?'eager':'lazy';img.decoding='async';const icon=document.createElement('span');icon.className='play';icon.textContent='▶';icon.setAttribute('aria-hidden','true');wrap.append(img,icon);const info=document.createElement('span');info.className='card-info';const title=document.createElement('h3');title.textContent=videoTitle(v);if(/[\u0590-\u05ff]/.test(v.title))title.className='hebrew';const meta=document.createElement('span');meta.className='card-meta';const region=document.createElement('span');region.textContent=regions[v.region];const label=document.createElement('span');label.textContent=language==='he'?'לצפייה':'Watch';meta.append(region,label);info.append(title,meta);button.append(wrap,info);button.addEventListener('click',()=>play(v,button));article.append(button);frag.append(article)});grid.append(frag);document.querySelector('#resultCount').textContent=`${found.length} ${language==='he'?'סרטונים':found.length===1?'video':'videos'}`;document.querySelector('#empty').hidden=found.length>0}
search.addEventListener('input',render);document.querySelector('#reset').addEventListener('click',()=>{search.value='';selected='all';render();search.focus()});document.querySelector('#close').addEventListener('click',()=>dialog.close());dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close()}});dialog.addEventListener('close',()=>{document.querySelector('#frame').replaceChildren();document.body.style.overflow='';opener?.focus()});render();


// Keep the original Hebrew copy from the HTML as the source for switching back.
const translations = [
    ['.brand-he', 'Sea slugs'],
    ['.credit', 'Macro photography · Stills and video'],
    ['.eyebrow', 'Through the lens, beneath the sea'],
    ['.intro-copy', 'Encounters with sea slugs, dive after dive. A video collection from Romblon, the Red Sea and the Mediterranean.'],
    ['.search > span', 'Search'],
    ['#empty h3', 'No videos found'],
    ['#empty p', 'Try a different name or choose another region.'],
    ['#reset', 'Clear search and filters'],
    ['footer p', 'Photography: Boaz Liebes · Videos hosted on YouTube'],
    ['footer > span:last-child', 'Sea slugs, up close.'],
    ['.player-bottom > span', 'If the video does not load, watch it on YouTube.'],
    ['#youtubeLink', 'Watch on YouTube ↗'],
].map(([selector, en]) => {
    const element = document.querySelector(selector);
    return {element, he: element.cloneNode(true), en};
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
    Object.assign(regions, en ? englishRegions : window.SEASLUGS.regions);
    translations.forEach(item => {
        if (en) item.element.textContent = item.en;
        else item.element.replaceChildren(...Array.from(item.he.childNodes, node => node.cloneNode(true)));
    });
    heading.replaceChildren();
    if (en) {
        heading.append('Science and art.', document.createElement('br'));
        const span = document.createElement('span');
        span.textContent = 'Diversity and migration dynamics: a key to tracking changes in the marine environment.';
        heading.append(span);
    } else {
        heading.append(...Array.from(originalHeading.childNodes, node => node.cloneNode(true)));
    }
    collectionHeading.textContent = en ? 'Video collection ' : originalCollectionHeading;
    search.placeholder = en ? 'Species or video name…' : 'שם המין או הסרטון…';
    search.setAttribute('aria-label', en ? 'Search by species or video name' : 'חיפוש לפי שם המין או הסרטון');
    document.querySelector('.filters').setAttribute('aria-label', en ? 'Filter by region' : 'סינון לפי אזור');
    document.querySelector('.brand').setAttribute('aria-label', en ? 'SeaSlugs — Home' : 'SeaSlugs — דף הבית');
    document.querySelector('#close').setAttribute('aria-label', en ? 'Close video' : 'סגירת הסרטון');
    for (const button of document.querySelectorAll('[data-region]')) {
        const count = button.querySelector('small');
        button.replaceChildren(button.dataset.region === 'all' ? (en ? 'All regions' : 'כל האזורים') : regions[button.dataset.region], count);
    }
    languageButton.textContent = en ? 'עברית' : 'English';
    languageButton.lang = en ? 'he' : 'en';
    languageButton.setAttribute('aria-label', en ? 'Switch to Hebrew' : 'מעבר לאנגלית');
    document.title = en ? 'SeaSlugs — Sea slugs | Boaz Liebes' : originalTitle;
    description.content = en ? 'Sea slug videos by Boaz Liebes. Explore Romblon, the Red Sea and the Mediterranean.' : originalDescription;
    const url = new URL(window.location.href);
    url.searchParams.set('lang', language);
    window.history.replaceState(null, '', url);
    try { localStorage.setItem('seaslugs-language', language); } catch (_) {}
    render();
}
languageButton.addEventListener('click', () => setLanguage(language === 'he' ? 'en' : 'he'));
let preferredLanguage = 'he';
try { preferredLanguage = localStorage.getItem('seaslugs-language') || 'he'; } catch (_) {}
setLanguage(new URLSearchParams(window.location.search).get('lang') || preferredLanguage);
