# SeaSlugs.org.il — System Reference

> This document is for Claude Code and any other developer working on the SeaSlugs site. It describes
> what the system is for, how it is built, the rules it follows, and how to change it safely. It contains
> enough detail to rebuild the system from scratch.
>
> Last verified against the code: 2026-11-04 (git `main` + the news & activity page, migration `0087`).
> Repository: `https://github.com/boazl/SeaSlugs` · Local copy: `/Users/boazliebes/SeaSlugs` (macOS)
>
> Companion files: `CLAUDE.md` (short working rules, read first), `TABLE-TRANSFER.md` (data-transfer
> procedure, Hebrew), `DIVE-TRIPS.md`, `RENDER.md`, `LOCAL-COMMUNITY.md`, `GALLERY-SAMPLES.md` (historical
> setup notes; some parts are outdated, and where they conflict with this file, this file is right).

---

## 1. Purpose

**SeaSlugs** ("חינניות ים") is a bilingual (Hebrew / English) website for researching and showing sea slugs:
nudibranchs and other opisthobranchs.

- **Content:** photos and YouTube videos of sea slugs from the owner's dives and from community members,
  organised by species, by taxonomy (order → sub-order → superfamily → family → genus → species) and by
  geographic area.
- **Scientific focus:** the Israeli Mediterranean, especially Lessepsian migration (species entering
  from the Red Sea) and species turnover as the Mediterranean becomes more tropical with global warming.
  The collection itself is international (mostly the Philippines, plus the Red Sea, Solomon Islands, Fiji
  and others), and the site must never describe it as mainly Israeli.
- **Community:** members register, add observations (תצפיות), manage dive trips, and find macro-diving
  partners.
- **Owner / sole administrator:** Boaz Liebes (`boazl`). Address him in Hebrew in the masculine form. He
  writes in Hebrew. Code, comments and commit messages are in English.
- **Inspiration:** the field-guide style of putsker.co.il, but for sea slugs only.

## 2. Environments, addresses and hosting

| | Local (development) | Production |
|---|---|---|
| Where | Boaz's Mac, `/Users/boazliebes/SeaSlugs` | Render web service, `seaslugs.onrender.com` |
| Public address | `http://127.0.0.1:8000/` | **https://seaslugs.org.il/** (custom domain; `www.` too) |
| Database | `./db.sqlite3` (not in git) | `/var/data/db.sqlite3` on a Render persistent disk |
| Media | `./media/` (not in git) | `/var/data/media/` |
| Backups | `./backups/` | `/var/data/backups/` (one is made automatically before each deploy) |
| `DEBUG` | True | False (`PRODUCTION=True`) |
| Python | 3.13 (`.venv`, `.python-version` = 3.13.15) | Render's Python 3 |

**The two databases are separate copies and never sync automatically.** Code moves through git; data
moves only through the admin transfer tools (§10).

### Render configuration (see `RENDER.md`)

- **Service:** one paid instance with a persistent disk mounted at `/var/data`. Branch `main`, empty
  root directory.
- **Commands:** build `bash build.sh` (pip install + `collectstatic`), start `bash start.sh`, health check
  path `/healthz`, no pre-deploy command (the disk is not available during that phase).
- **`start.sh`:**
  1. Checks that `/var/data` exists and is writable.
  2. Makes a verified SQLite backup (`backup` API + `PRAGMA integrity_check`) to
     `/var/data/backups/before-deploy-*.sqlite3`.
  3. Runs `migrate --noinput`.
  4. Starts `gunicorn config.wsgi --workers 1 --threads 2 --timeout 300`. One worker is deliberate:
     SQLite allows a single writer.
- **Deploys:** auto-deploy on commit. A push to `main` deploys.
- **Environment variables:**
  - `DJANGO_ENV=production`
  - `DJANGO_SECRET_KEY`
  - `SEASLUGS_DATA_DIR=/var/data`
  - `DJANGO_ALLOWED_HOSTS=seaslugs.org.il,www.seaslugs.org.il` (Render adds `RENDER_EXTERNAL_HOSTNAME` itself)
  - `GOOGLE_SITE_VERIFICATION` (Search Console meta tag content)
  - `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`
  - `DEFAULT_FROM_EMAIL`
  - `NEW_USER_NOTIFICATION_EMAIL` (recipient of the new-sign-up notice)
- **Never** put secrets in the repository. `.secret_key`, `.env`, `*.sqlite3`, `media/`, `backups/`,
  `staticfiles/`, `*.docx` and Google Docs exports are in `.gitignore`. A Google Docs HTML export once
  leaked API keys into git and triggered a GitHub secret-scanning alert.

### Domain

- `seaslugs.org.il` was bought instead of the originally planned `seaslugs.co.il`.
- DNS points the domain at Render. The `django.contrib.sites` row (migration `0029`) is fixed to
  `seaslugs.org.il`, so the sitemap and robots.txt always use the real domain, whichever host served the
  request.
- Production forces HTTPS: `SECURE_SSL_REDIRECT`, secure cookies, HSTS for 3600 s, and the
  `X-Forwarded-Proto` proxy header.
- In October 2026 the Hebrew University network blocked `seaslugs.org.il` because of the reputation of
  Render's shared IP. The block was removed and the issue is closed. Cloudflare was considered and not
  adopted.

### Publishing code (the owner does this, never Claude)

- **Process:** Boaz runs `___Publish SeaSlugs.command`, which runs `scripts/publish.py`. The script:
  1. Checks that the branch is `main` and the remote is `boazl/SeaSlugs`.
  2. Refuses paths that look like a database, a backup or a secret.
  3. Fetches, and refuses if GitHub has commits the Mac lacks.
  4. Lists the files and asks for `YES`, then for a description.
  5. Runs `git add` on the listed files, commits and pushes. Render then deploys.
- **Your part:** leave changes uncommitted (or commit locally only if asked), tell Boaz which files will
  be published, and suggest a one-line English description.
- **Code only:** publishing never transfers data. Data moves through §10.

## 3. Technology stack

- **Django 5.2 LTS** (`Django==5.2.17`), a single app `observations`, project package `config`.
- **SQLite** in both environments (`OPTIONS: timeout 20`). No Postgres. Keep queries simple, and expect
  "database is locked" if two writers collide.
- **gunicorn** with **whitenoise** (static files, `CompressedManifestStaticFilesStorage`).
- **Pillow** for image validation, resizing and re-encoding. **pypdfium2** renders PDF pages to
  thumbnails.
- **Front end:**
  - Plain HTML/CSS/vanilla JS. No build step and no framework.
  - The public gallery is a hand-written single-page script in `dist/`.
  - Server-rendered pages use Django templates with inline CSS/JS.
  - YouTube videos are embedded from `youtube-nocookie.com`.
- **Analytics:** Google Analytics 4, tag `G-CPGTC09P2P`.
- **No other services:** no CDN, no queue, no cron, no external storage. Everything lives on the one
  Render disk.
- **Dependencies** (`requirements.txt`): asgiref, Django, sqlparse, gunicorn, whitenoise, Pillow,
  pypdfium2. Add new ones sparingly, pin exact versions, and remember Render installs them on every
  build.

## 4. Repository layout

```
config/
  settings.py        environment switch (PRODUCTION), DATA_DIR/MEDIA_ROOT, test-only temp MEDIA_ROOT,
                     whitenoise, logging of 500s to console, email, upload limits
  urls.py            all routes (public pages, admin tools, sitemap, robots, gallery files)
  views.py           gallery_file (serves dist/ files; renders dist/index.html as a Django template;
                     builds /catalog.js from the DB on every request), healthz, robots.txt,
                     analytics opt-out cookie
dist/                the public gallery (home page), served by config/views.gallery_file
  index.html         home page template (Django template syntax inside; server-rendered SEO text)
  app.js             gallery SPA (~1,800 lines): filters, sorts, taxonomic drill-down, cards,
                     player dialog, language switch, history/back-button, "back to gallery" (?up=)
  catalog.js         HISTORICAL static list, import source only. The live /catalog.js is generated.
  styles.css, site-header.css (shared header for all pages), youtube-fallback.js, intro-photo.jpg
observations/
  models.py          all models (see §5)
  views.py           observation form/listing, species/genus/family/order pages, trips, profile,
                     partners, photo streaming, identification files
  forms.py           SampleForm (observation), taxon-file fields for managers, image validation
  admin.py           Django admin with custom actions, filters, editable changelists
  gallery_data.py    shared species→taxon resolution (TaxonResolver) and taxon_media()
  defining.py        which observation may be a taxon row's "defining sample"
  media_transfer.py  image storage (canonical names, legacy hash names)
  image_manager.py   /admin/images/: list, compare, transfer, delete images
  folder_import.py   /admin/images/folder/: reviewed bulk import from a folder + Excel
  video_check.py, video_check_views.py  /admin/video-check/: find YouTube videos that were deleted, fix the links
  views.trip_picker_context + _trip_picker.html / _trip_picker_script.html  the observation form's trip picker (country / region / site / year filters, initTripPicker), shared with the folder and video import tools
  video_import.py    /admin/local-videos/import/: attach a trip's video files to observations (Mac file, Drive copy, YouTube)
  drive_videos.py, drive_video_views.py  /admin/drive-videos/: re-read the Google Drive ids of the video copies
  table_transfer.py, transfer_views.py, sample_transfer.py, taxon_transfer.py,
  account_transfer.py  /admin/table-transfer/: JSON export / preview / apply per table
  article_transfer.py, article_files.py, articles.py, article_render.py, article_import.py,
  article_thumbs.py  the article library (PDF and site-written articles) and genus identification files
  db_replace.py, maintenance.py, middleware.py   full DB replacement with a maintenance lock
  release_views.py   /admin/releases/: download DB + media ZIP
  sitemaps.py, seo_text.py, species_redirects.py  SEO
  home_text.py, home_content.py, home_defaults.py, home_markup.py  editable home page text
  i18n.py, templatetags/seaslugs_i18n.py  translation (the |t:lang filter, TRANSLATIONS dict, with_lang)
  names.py           scientific-name italics rule (mirrors setLatinName in app.js)
  counts.py          species/observation counter wording (mirrors app.js)
  trip_naming.py     suggested dive-trip name and code
  notifications.py   new-user email
  activity.py        activity log (signals) and the visit counter middleware (§7.4)
  news.py            the /news/ page: activity feed, posts, progress chart, management data (§7.4)
  reference_links.py admin-only iNaturalist/WoRMS link per species
  management/commands/   one-off imports and maintenance commands (§9.3)
  migrations/        0001…0083 (many are data migrations that fix the catalogue; keep them)
  templates/observations/  page templates (base.html, species_page, genus_page, taxon_page, form,
                     list, trips, trips_manage, images, transfer, releases, db_replace,
                     article_files, articles, article_page, folder_import, home_text_edit …)
  test_*.py, tests.py   ~1,000 tests (§14)
scripts/publish.py   the reviewed publish script
*.command            macOS double-click launchers (publish, release manager, migrations, ref links)
docs/                notes on removed taxon texts; this file
```

Untracked local folders: `media/`, `backups/`, `staticfiles/`, `folder-import-staging/` (auto-cleaned
after one hour), `Claude outputs/`, and `_to_delete/` (files moved aside because Claude may not delete
without permission). Do not commit these.

## 5. Data model

Counts are from the local DB on 2026-10-30. Table names are Django's defaults unless shown.

### 5.1 Geography

| Model | Fields | Notes |
|---|---|---|
| `Country` (21) | `name` (he), `name_en` | |
| `Sea` (15) | `name`, `name_en`, `url_code` | e.g. "Indo Pacific - South China Sea", "Mediterranean". `url_code` is the short code in shareable gallery links (`med`; migration `0090`); permanent once links are out. |
| `Region` (22) | `name`, `name_en`, `country`, `sea`, `trip_code` | Dive region (Anilao, Romblon, Eilat…). A region belongs to one sea. `trip_code` is the letter(s) used in trip codes. |
| `Site` (50) | `name`, `name_en`, `region` | Dive site |

### 5.2 Catalogue and taxonomy

- **`Species`** (5,382 rows: a full checklist; only about 270 appear in the gallery)
  - `genus` + `species` + `author` are authoritative. `scientific_name` is derived as exactly
    "Genus species" (migration 0038).
  - Text taxonomy columns: `order`, `family`, `superfamily`.
  - `name_he`, `name_en`.
  - `is_migrant` marks a Lessepsian migrant. It is set when the species also occurs in tropical
    regions and does not depend on gallery records.
  - Records: `first_observed_year`, `last_observed_year`; size `size_from`, `size_to`, `size_max`;
    depth `depth_min`, `depth_max`.
  - Page texts in he/en: `description`, `identification`, `similar_species`, `habitat`, `food`,
    `native_range`, `introduction_route`, `med_status`, first/last record place; plus `sources`.
  - `reference_link` is an admin-only iNaturalist/WoRMS link. `articles` is M2M to `Article`.
  - Many legacy import columns exist (`source_id`, `accepted_*`, `formatted_author`, …).
- **`TaxonOrder`** (41): one table for orders, sub-orders and superfamilies.
  - Identity: `name` + `sub_order` + `superfamily` + `taxonomic_order`.
  - `rank` (order / suborder / superfamily) is computed on save.
- **`TaxonFamily`** (108): `order` FK, `name`, `sub_family`, `superfamily`.
- **`TaxonGenus`** (548): `family` FK, `name` (unique).
  - Identification files: `identification_file` / `identification_file_en` (PDF or image, ≤20 MB).
  - `identification_page` / `identification_page_en`: the PDF page used as the preview.
  - Auto-made previews: `identification_thumb` / `identification_thumb_en`.
  - `identification_caption` / `identification_caption_en` and `identification_source`.
- **Shared by all three taxon tables:** `name_he`, `name_en`, `taxonomic_order` (sort key),
  `defining_sample` FK→Sample, description/identification in he/en, `sources`, `link`, and M2M `articles`.
- **Reference tables:** `IdentificationQualifier` (cf., aff.), `LifeStage` (juv.) and `SampleKind`. The
  qualifier and life-stage tables are keyed by `code` and editable in the admin.

### 5.3 Observations and the gallery

- **`DiveTrip`** (table `dive_trips`, 49) -- may lie in the future (a planned trip, §7.6); `start_date()` / `end_date()`
  give its known dates (start day + duration, else the end of its month / year)
  - `summary_trip` (FK self, migration `0097`): a series of small trips / samplings documented separately is summed up
    by one trip (often with one video of all the species). One level: the summary trip has no summary trip, and a trip
    that sums up others has none. `trip_family()` = the trip + the trips it sums up; `series_end_date()` the last day of
    any of them. The summary trip's species are its own observations plus theirs: its trip page (with "המסע מסכם את
    המסעות" / "חלק מסדרת המסעות"), `display_species_count`, the public trips table and the gallery's trip filter
    (`/catalog.js` trips[id].sub_trips, app.js `tripFamily`). Chosen in the admin's trip form among the trips without a
    summary trip, with country / region / year filters (`DiveTripAdminForm`, `summary_trip_picker.js`); the form lists
    the trips a summary trip sums up.
  - `code` is the stable natural key, e.g. `V`, `I26Aug`. `kind` is dive or thematic.
  - `title`, `year`, `month`, `start_day`, `duration_days`.
  - `country`, `region`, `site`, plus source text columns.
  - A trip has **no sea field**: its sea is `region.sea`. It also has **no photographer**: the
    photographer is the observation's owner.
  - Taxon "library trips" `Genera`, `Families` and `Orders` hold genus/family/order observations
    (`TAXON_LIBRARY_TRIPS`).
- **`Sample`** (table `samples`, 486): **an observation**.
  - `kind`: `species` | `collection` (a dive-trip summary video) | `genus` | `family` | `order` | `planned` (a dive
    trip being planned: no media, future trip; §7.6).
  - `trip`: required except for taxon kinds. `owner`: the creator, who is the photographer.
  - Taxonomy by kind, as text: `order`, `family`, `genus`. `species` is an FK (species kind only).
    `sync_taxonomy()` fills the higher levels from the taxonomy tables.
  - `identification_qualifier` (cf./aff. code), `life_stage` (juv.).
  - `undetermined_variant`: a letter separating forms of one "Genus sp.".
  - Free text "other": `species_other` (species not yet catalogued) and `site_other`. Either blocks
    publication.
  - Media: `image` (stored photo) and/or `video_url` (YouTube). `gallery_source` FK→Sample means
    "show another observation's photo", and the image follows its source.
  - `image_hash` (sha256).
  - `transfer_id`: a UUID that stays the same in both environments and is the transfer key.
  - Other fields: `site`, `day`, `depth`, `title`, `title_en`, `note_he`, `note_en`, `gallery_order`,
    `source_metadata`, `source_id`.
  - Lifecycle: `status` (pending / published); `created_at`, `updated_at`; soft delete via `deleted_at`
    and `deleted_by`; `approved_at`, `approved_by`.
- **`SpeciesArea`** (302): **a gallery card**. In site wording this is an "observation".
  - One row per species + country + sea (+ `undetermined_variant`).
  - `defining_sample` is the observation whose photo or video represents the card.
  - `slug` is the public page URL, generated once from species+variant+country+sea and **never changed
    afterwards**, because published links must keep working. Example:
    `phyllidia-ocellata-phillipines-indo-pacific-south-china-sea`, keeping the old spelling.
  - `note_he` / `note_en` hold a remark shown on that page.
  - `chosen_sample` is the main observation a manager picked on the species page ("הפוך לתצפית הראשית",
    `observation-make-main`). While it is still a published observation of the area with a photo or video,
    `pick_defining_sample` returns it, so publishes, transfers and `rebuild()` keep it; otherwise the automatic
    pick applies. It transfers with the `speciesareas` table.

### 5.4 Content, users and other

- **`Article`**
  - `slug`, he/en titles, subtitles, bylines and editorial notes, `link`.
  - `pdf_he`, `pdf_en` (≤20 MB) and auto previews `thumb_he`, `thumb_en`.
  - `published_on`, `show_on_home`.
  - It is either a PDF article or an article **written on the site**, made of `ArticleBlock` sections
    (heading, subheading, paragraph, figure → Sample, table, list, notice) plus `ArticleReference`
    entries. A table block is one row per line with cells separated by `|`, or a table copied from Excel and pasted as
    is (tab-separated; quoted cells may hold line breaks; `article_render.table_rows`). Excel files themselves are not
    uploaded.
  - **Edited on the site** (`article_edit.py`, `/articles/<slug>/edit/`) by the organizer of a dive trip that picks the
    article (the owner of the trip's planning / collection observation) and the managers: titles, subtitles and the
    sections (add, delete, kind, order, he/en text); figures stay (admin). The article page's "עריכת מאמר" leads there
    for the organizer and to the admin for staff. An article without a picture is listed without a thumbnail box.
  - Picked from the library by species, taxa and dive trips through their `articles` M2M.
- **`Profile`**: `user` 1:1. `must_change_password` (migration `0098`): a temporary password a manager set -- the
  member is sent to `/observations/password/` (`views.password_change`, `PasswordChangeRequiredMiddleware`) from every
  page until they choose their own (logout passes); ticked on the user's admin page; per environment (passwords and
  this mark never travel). Every member can change their password from the profile page.
  - English name, `phone`.
  - `macro_diver` and `visible_to_members` control the partners directory.
  - `bio` and `bio_en` ("about me" in Hebrew / English, migration `0100`; the partners page shows the page's
    language, else the other; both travel with the profiles table -- an older file without `bio_en` keeps the
    destination's), `trip_code` (the photographer letter), and M2M `regions` and `countries`.
- **`HomeText`**: (`key`, `lang`) → editable home-page section text.
- **`SiteImage`**: (`key`) → home intro photo.
- **`ActivityEvent`**, **`NewsPost`**, **`DailyPageView`**, **`DailyVisitor`**: the activity log, the manager's
  news posts and the visit counter (§7.4). Per environment; none of them travels between the Mac and the site.
- **`ForumMessage`** (migration `0094`): a message in the observations forum (§7.5): `observation` FK→Sample (required),
  `created_at`, `user`, `manager_only`, `subject` (optional), `text`, soft delete `deleted_at`/`deleted_by`, and
  `transfer_id` (UUID, the transfer key). Travels with the table transfer (table `forum`, §10.2).
- **Users:** Django `auth.User` with groups created by `setup_community` (migration `0099` deleted the unused New user,
  Subscriber and Artist):
  - **Macro diver** -- the partners list (`views.partners`, `test_partners.py`) shows members who ticked "interested in
    finding macro diving partners" (`Profile.macro_diver`) and "show my profile to members" **and** are in this group.
    Tick and group follow each other both ways (`models._sync_macro_diver`, an `m2m_changed` signal; the profile form
    adds / removes the group): a manager removes someone from the list by removing them from the group.
  - **Macro photographer** -- the photographers (below). **Scientist** / **Administrator** -- admin permissions (species /
    all observation tables except delete) for staff members.
  - **Photographers** (`photographers.py`, `test_guest_photographers.py`): an observation always belongs to a
    user, its photographer. The photographers are the **"Macro photographer" group** -- not every member (divers
    only are not). A member joins it with the bilingual "אני צלם/ת" / "I am a photographer" box on the sign-up
    or profile form (unticking leaves it; locked on with observations -- `test_photographer_checkbox.py`), by a
    manager (the admin's user page) or with his first observation; migration
    `0093` added everyone who had observations. A **guest photographer** (no account of their own) is an inactive
    user in the group (migration `0092` put the existing inactive users there). A manager sets one up on
    `/observations/photographers/new/` (no password; username from the English name) and can later make them
    active. On the observation form a manager chooses the photographer (`photographer_users()`: the group, plus an
    edited observation's current owner; `?photographer=` preselects, and the add-trip / species / photographer links keep it); the quick trip
    form's photographer (it names the trip) offers the same users.

## 6. Core domain rules (the logic most bugs touch)

1. **Publication** (`Sample.save_reviewed`, `is_complete`, `publication_reasons`)
   - An observation is *complete* when:
     - its trip has a year (not needed for taxon kinds);
     - a species-kind observation has a catalogued species;
     - there is no `species_other` or `site_other`.
   - A complete species observation is **published automatically**.
   - Collections need a manager's approval, except when a manager saves them.
   - A manager's save of a complete observation, including a taxon observation, publishes it.
   - Incomplete observations stay `pending`. The admin actions are approve / soft-remove / restore.
2. **The gallery card (`SpeciesArea`)**
   - Publishing a species observation calls `update_or_create` on its SpeciesArea and picks a defining
     sample (`SpeciesArea.pick_defining_sample`).
   - When an observation is deleted, unpublished or moved, the area it leaves gets a new defining sample,
     or none.
   - A manager's chosen main observation (`SpeciesArea.chosen_sample`) wins over the automatic pick while it is valid.
   - On the species page an "other observation" card shows its region next to the year when it differs from the
     main observation's region.
   - Only published, non-deleted defining samples that have a photo or video are shown
     (`gallery_data.taxon_media`).
3. **Defining samples for taxon rows** (`defining.py`): a row is represented by an observation one level
   below it.

   | Row | Represented by |
   |---|---|
   | SpeciesArea | a species-kind observation of that species in that area |
   | genus | a species of the genus |
   | family | a genus-kind observation |
   | order / sub-order / superfamily | a family-kind observation |

   - If the level below has nothing, the next level down is used.
   - A taxon's *own-kind* observation (for example a genus-kind observation of Phyllidia) is shown
     first on its page (`display_sample`).
   - `Sample.save` repairs the affected rows.
4. **Taxonomy follows WoRMS only**
   - Real ranks only. Informal groups are removed.
   - Gallery hierarchy: orders → sub-orders + "Others" → superfamilies + "Others" → families +
     "Others" → genera → species.
   - Every order holds *all* its species. A rank that a group lacks entirely is skipped.
   - Hebrew group names translate the Latin names; they are not separate groups.
   - All ranks behave alike: each has a defining photo, a page, a gallery card and navigation buttons.
5. **Changing an observation's species** (`test_species_change`)
   - The change is made in place: the same row and the same `transfer_id`.
   - The species it leaves stops showing it.
   - The photo is replaced by the re-labelled one or kept on purpose, and name collisions are handled.
   - After saving, the user lands on a page that exists.
6. **One observation per species per trip**: submitting the same species on the same trip folds into
   the existing observation (`views.edit`).
7. **Counting words** (`counts.py`, mirrored in app.js)
   - "תצפית" = a SpeciesArea; "מינים" = distinct species.
   - Every counter shows species only.
   - The one exception is the gallery's "כל האזורים" button: "266 מינים ב-301 תצפיות".
   - The news page (§7.4) is the other exception, decided by the owner: "תצפיות חדשות" counts published observation
     records, including repeat observations of a species in an area and trip collections (411 records = 351 cards
     + 46 repeats + 14 collections on 2026-11-04). "מינים חדשים" = species new to the site, "מינים חדשים לאזור" = new
     cards.
8. **Scientific names** (`names.py` and `setLatinName` in app.js)
   - Only genus + epithet are in italics. cf./aff., "sp. 7", the variant letter, the author and the
     life stage are upright.
   - Every fully named species must have an author; `sp.` rows are exempt.
   - Merge duplicate species into the accepted WoRMS name.
   - When checking a species list against the catalogue, fix the catalogue, not the list.
   - The name labels burned into photos (Photoshop, Helvetica Neue faux italic, label fully slanted)
     are a deliberate design and must **not** be flagged.
9. **Language** (§7.3)
   - Each page shows exactly one language.
   - The choice persists across pages.
   - Every page has the same header.
10. **Dive-trip planning** (`planned_trips.py`, §7.6): a `planned` observation has a title, a trip with a year and a
    month, no media; it publishes itself; never in the gallery. Species and collection observations cannot be added to
    a trip that has not started (`Sample.clean`).
11. **Hebrew terms**
    - "חינניות ים" (singular "חיננית ים") = sea slugs, the umbrella term. "חשופיות" = nudibranchs only.
      Never use "חשופיות ים" as the umbrella term.
    - Adding: "הוספת תצפית" / "הוסיפו תצפית" ("Add an observation"), never "תרמו".

## 7. Public site

### 7.1 Pages and URLs

| URL | What |
|---|---|
| `/` (`?lang=en`) | Home page + gallery. `dist/index.html` is rendered server-side with home texts, SEO text, sections in both languages as JSON, and articles; then `app.js` runs the gallery. `/index.html` → 301 `/`. |
| `/catalog.js` | `window.SEASLUGS = {species, collections, areas, regions, sites, trips, taxa}`, built from the DB per request (`no-store`). |
| `/species/<slug>/` | Species-in-area page: hero video or photo, facts, all observations of that SpeciesArea, articles, note, share link. |
| `/genus/<name>/` | Genus page: description, identification text, identification file (preview of a chosen PDF page in a box; the box opens the PDF at that page; he/en file with fallback), species cards, sources. |
| `/trip/<code>/` | Dive-trip page (`trip_page.py`, keyed by the permanent `DiveTrip.code`): the trip's collection observation -- video, photo, for managers the local / Google Drive copy and an edit button -- the trip's place, date, description and articles, then one card per species observed on the trip (a species is observed at most once per trip, so no count), each linking to that observation on its species page (`#obs-<pk>`). 404 without a published collection observation that the gallery shows. The gallery's collection card and the trips page's video card open it; listed in the sitemap. |
| `/family/<name>/`, `/order/<pk>/` | Taxon pages (template `taxon_page.html`). An order's base-row page holds the whole order. Old Nudibranchia group pages `/order/14,16,17` → 301. |
| `/genus/<name>/identification/[<lang>/]`, `…/<lang>/preview.jpg` | Identification file stream and its page preview |
| `/articles/`, `/articles/<slug>/`, `/articles/<slug>/<lang>.pdf` and `.jpg` | Article library |
| `/observations/` | Members' listing (filters, sort). Owners also see their pending observations; managers see everything. |
| `/observations/new/`, `<pk>/edit/`, `<pk>/remove/`, `<pk>/action/`, `<pk>/photo/` | Observation form and actions. `photo/` is the **only** way images are served in production (access-controlled). |
| `/observations/trips/` | Public dive trips: trip videos, then a sortable table with expandable species rows; a species picture opens that observation on its species page (`#obs-<pk>`) |
| `/observations/trips/manage/`, `trips/add/`, `trips/suggest/` | Trip management for members (suggested name/code, see `trip_naming.py`) |
| `/observations/signup/`, `login/`, `logout/`, `profile/`, `partners/` | Community (sign-up asks the name in Hebrew and in English) |
| `/observations/home-text/` | Manager editor for home-page sections |
| `/sitemap.xml`, `/robots.txt`, `/healthz` | SEO and health |
| `/analytics/exclude/`, `/analytics/include/` | Owner's GA opt-out cookie (not linked anywhere); also stops the site's own visit counter |
| `/observations/trips/#planning` | The dive trips page's "תכנון מסעות צלילה" section (§7.6) |
| `/planning/`, `/planning/<trip code>/` | The open plannings; one planning's page (§7.6) |
| `/forum/trip/<trip code>/` | One dive trip's discussion to send to people, without the forum's picker; a summary trip's page holds its series (§7.5) |
| `/news/` | News & activity (§7.4): public activity feed, posts, planned trips, progress chart; management data for staff |
| `/forum/` (`?kind=…`, `?obs=<pk>`), `/forum/new/`, `/forum/<pk>/delete/` | Observations forum (§7.5) |

### 7.2 The gallery (`dist/app.js`)

- **Data:** `/catalog.js` (species with samples, areas, taxa dictionaries, `order_pages`).
- **State object:** `area`, `regions`, `sites`, `photographers`, `years`, `observations` (multi filter),
  `level`, `drill`, `order`…`genus`, `collection`, `sort`, `sortChosen`.
- **Area buttons:** all areas, species from multiple areas, Mediterranean exotic (migrants), and
  per-sea buttons. Sidebar filters: region, site, photographer, year, several observations.
  Managers, under the alphabetical sort only: photo / video filters (`media`: video with no photo, photo with no
  video, video with no Google Drive copy -- the page carries the Drive ids as `#drive-videos`).
- **Collection cards** open the trip page (`/trip/<code>/`); its "This trip in the gallery" button (`/?sort=alpha&trip=<id>`)
  filters the gallery to the trip.
- **Sorts:** taxonomic (default), alphabetical, observation year (only under the migrant filter), number
  of observations (only under the multi filter).
- **Taxonomic drill-down**
  - Cards per rank, framed by rank colour: order `#5555ff` 8px … genus `#ffffff` 2px; species cards are
    unframed.
  - Clicking an order, sub-order, superfamily or family card drills in (`state.drill={level,id}`,
    `nextLevel()` skips ranks that add nothing, but never the genus: when one genus is left, even with one species, its genus card is shown).
  - **Clicking a genus card opens the genus page.**
    In a filtered view (trip, region, site, photographer, year, area, search…) the card carries the filter:
    `/genus/<name>/?areas=<area ids>&samples=<matching observation ids>&trip=<trip id>` (`genusPageHref`).
    The genus page (`views.genus_page_focus`) then lists those species first, each card with the matching
    observation's photo and count, a link to all the species, and the genus's other species as small cards.
  - "Others" cards collect species missing the shown rank.
- **Player dialog:** opens a video or photo. `youtube-fallback.js` swaps a video that cannot be embedded
  (IFrame API `onError`, for example error 150) for the photo, with a "Watch on YouTube" link. The same
  happens on the species, genus and taxon pages.
- **History**
  - Each view change is a `history.pushState` entry, so the browser Back button returns to the previous
    gallery view. The view and scroll position live in `history.state`; search typing replaces the entry
    instead of adding one.
  - The view is also kept in `sessionStorage` (`seaslugs-gallery-view`) for `?restore=1`.
- **Shareable links** (`galleryQuery` / `galleryUrl` / `applyGalleryQuery`, `test_gallery_links.py`)
  - The address bar always holds the view on screen, e.g. the Mediterranean species alphabetically:
    `/?area=med&sort=alpha`. Opening such a link draws that view.
  - Parameters: `area` (a sea's `url_code`, or `sea-<id>` without one; `multi`, `migrant`), `sort` (only when
    chosen by hand), `level`, `in=<rank>:<key>` + `others=<ranks>` (taxon drilled into), `region`, `site`,
    `photographer`, `year` (repeated per ticked box), `obs=multi`, `trip`, `trips=hide` (the sidebar's "Dive trip
    collections" unticked: no collection cards; not offered in the taxonomic view), `q`. `lang` is kept. Unknown values
    are skipped.
  - On load: `?restore` / `?up` first, then the history entry's view, then the link's parameters.
  - A manager's gallery has a "copy a link to this view" button (`#copyLink`; `is_manager` in the page context).
- **Mediterranean bounty banner** (`test_bounty_banner.py`): beside the controls panel (`index.html` `.controls-row`,
  `[data-bounty]`; one line with the panel on a computer -- the same height from 1300px -- and above it on a phone),
  "₪200 for a photo of a Mediterranean species not among the N observations on the site" + a line that the photos
  are for scientific publication and the photographer is credited. N is the live species count of the area with
  code `med` (`fillBountyBanners`); hidden without one. It opens `/?area=med&sort=alpha&trips=hide` in place.
- **"Back to the gallery" on pages:** `/?restore=1&up=<rank>:<key>` (built by `views.gallery_up_url`).
  The gallery opens one rank above the page's taxon, among its siblings:

  | Page | `up` value | Gallery shows |
  |---|---|---|
  | species | `genus:<pk>` | the genera of its family |
  | genus | `genus:<pk>` | the genera of its family |
  | family | `family:<pk>` | the families of its superfamily or sub-order |
  | order / sub-order / superfamily | `order:<name>`, `suborder:<value>`, `superfamily:<value>` | the rank above |

  - It keeps the visitor's filters unless they would hide the taxon, and scrolls to its card.
- **Duplicated logic:** the italics rule, the count wording and the translations are duplicated
  server-side and in `app.js`. **Change both** (tests check some of this).

### 7.3 Language

- Hebrew is the default (`/`, RTL). English is `?lang=en`.
- `LanguagePreferenceMiddleware` stores an explicit `?lang=` in the `seaslugs_lang` cookie (1 year).
  The `language` context processor exposes `lang`.
- **Which language a page is in** (`i18n.get_lang`, `test_browser_language.py`): `?lang=` first, then the
  cookie (so a chosen language stays from page to page), then on a first visit the browser's language
  (`i18n.browser_lang`, Accept-Language): Hebrew only when the browser's first choice is Hebrew (`he`/`iw`),
  English otherwise. No header, crawlers and link-preview fetchers get Hebrew. Responses without `?lang=` vary
  on `Cookie, Accept-Language`.
  - `/` is only ever served in Hebrew: an English visitor (cookie or browser) gets a 302 to `/?lang=en`, the
    other parameters kept. `?lang=he` never redirects.
  - The manager's "copy link" button in the gallery drops `lang`, so a recipient gets their own language.
- **Server strings:** templates write Hebrew literals through `{{ "…"|t:lang }}`. English values live in
  `TRANSLATIONS` in `templatetags/seaslugs_i18n.py`.
  - **`test_template_translations` fails if a `|t` literal has no English entry**, so add one with every
    new Hebrew UI string.
  - `with_lang` adds `?lang=en` to internal links.
- **Gallery strings:** `app.js` has its own lookup and swaps both languages without a reload.
- The header (`dist/site-header.css`, `account_menu.html`) is identical on all pages: brand, credit
  line, icon menu, language button and opening panel.

### 7.4 News & activity page and the activity log (`activity.py`, `news.py`, migrations `0086`–`0087`)

- **Activity log (`ActivityEvent`)** is written by model signals, so every path is covered (form, admin, table/image
  transfer, scripts). **Each environment keeps its own log**: on the live site an observation enters the log when it
  is transferred there; the log itself is never transferred.
  - `observation_added` (species or collection observation becomes public for the first time, once per `transfer_id`),
    `video_added` (once per YouTube id), `species_new` (a new SpeciesArea; `detail.new_to_site` / `new_to_sea`),
    `species_changed` (species / cf. / variant of a public observation; old and new names), `observation_updated`
    (photo hash, notes, site, depth, day, titles, life stage; folded into one line per 24 h; saves within 10 minutes
    of adding are part of adding), `signup` and `login` (private).
  - Not logged: pending observations, taxon-kind observations, `SpeciesArea.rebuild()` (`activity.suppressed()`),
    accounts with an unusable password (table transfer) or inactive guests, and the owner (superusers and
    `ACTIVITY_EXCLUDED_USERNAMES`, default `boazl`).
  - Migration `0087` back-fills the log from existing data (`detail.backfill`).
- **Visit counter** (`activity.VisitCounterMiddleware`): views of public HTML pages per page per day
  (`DailyPageView`) and visitors per day (`DailyVisitor`, a salted daily hash of IP + browser; no cookie). Skips
  `/admin/`, bots, the owner, and the `exclude_analytics=1` cookie. Counting can never break a page.
  Every browser the owner signs in on gets that cookie automatically (`activity.mark_owner_browser`,
  `test_owner_browser_uncounted.py`), so it stays uncounted -- here and in GA -- after signing out.
- **`/news/`** (public, in the sitemap, linked from the main menu as "חדשות ופעילות"):
  - **Posts** (`NewsPost`, written in the admin of each site, simple markup like the home texts) and **planned dive
    trips** (`NewsPost` kind `trip`, shown until `trip_end`; `DiveTrip` cannot hold a future year).
  - **Period:** "last week" by default (the month list then shows the current month); otherwise a month and/or year
    from two lists, which offer only years and months with activity. "All months" = the whole chosen year. A sea
    (area) filter applies to the feed and the chart.
  - **Tiles** (a tile whose value is 0 is hidden): new observations (records, see §6.7), new videos, new species
    (species new to the site), new species in an area (new cards), identification changes, updated observations.
  - **Feed:** new species = species new to the site, each once, with a small photo, date and name only; new videos as
    cards that open the observation (its species page); new observations as small picture cards; identification
    changes (old ← new); updated observations. Only lines whose observation / card is still public.
  - **Progress chart** (since the first observation, follows the sea filter): one bar a day across a fixed width,
    the running totals at the end of the day; the observations bar behind the species bar, same width, no gaps, solid
    colours; the species number written upright and bold inside its bar only on days it changes; y axis from 0 with
    a faint grid every 20, labelled with the observation totals the bars reach (close values nudged apart, a crowded
    one left out); x axis month names with the year under its months.
  - **Slideshow** (`/news/slideshow/`, open to everyone): a red ▶ above the new-videos tile opens it with the same
    period and sea. The new videos play oldest first, in a loop, from YouTube through the IFrame player API embedded
    from `www.youtube.com` (the owner checked: no ads), moving on when a video ends; one that cannot be embedded is
    skipped. Nothing passes through Render. A manager on the Mac plays the offline copy instead wherever this computer
    has one (`local_videos.statuses` = `ok`, `/observations/<pk>/local-video/`), so it also works without internet
    (YouTube-only videos are then skipped); `?source=youtube` makes a manager use YouTube for everything. The caption
    and buttons sit under the video; full screen shows the video alone; previous/next arrows exist only in full screen, as
    clear strips down each side that show the arrow on hover and for 2.5 s after entering full screen or changing video
    (faintly visible on touch screens). YouTube's own full-screen button is off (`fs: 0`): it would hide the arrows. Where the browser has no element full screen (iPhone Safari) the stage fills the
    window instead, with a ✕ to close. After a click inside the YouTube player the keyboard focus returns to the page,
    so the keys keep working: arrows, space, `f`, Esc.
  - **Managers** also see visits (today / 7 / 30 days, a daily chart, top pages), sign-ups, the users table (joined,
    last login, logins in 30 days, observations), visitors by country over 30 days (`test_visitor_countries.py`),
    recent logins and, last, the photographers table (the photographer group, and anyone with a published
    observation; 0 for none yet; guests marked: name, email, phone, published observations;
    `test_news_photographers.py`).
  - **Countries:** `DailyVisitor.country` (code only) and `.views`, set by `geo.country_of`: the `CF-IPCountry`
    header if present, else the DB-IP Country Lite database (CC BY 4.0) at `geoip/country.mmdb`, downloaded on every
    deploy by `build.sh` → `scripts/fetch_geoip.py` (never fails the build; not in git). On the Mac the visitors are
    local addresses, so their country is unknown.

### 7.5 Observations forum (`forum.py`, `forum.html`, `_forum_observation.html`, `_forum_message.html`, `test_forum.py`)

- **What:** members write criticism, remarks, plans and discussion about observations. **Every discussion belongs to one
  observation** (a Sample of any kind); there is no general discussion.
- **The page `/forum/`:** filters (`forum.observation_filters`) that narrow the observation picker and the discussions:
  kind (`?kind=species|collection|planned|genus|family|order`, `KIND_FILTERS`), photographer, country, region, year and,
  by kind (`TAXON_FACETS`), genus + species (species observations) or the genus / family / order of a taxon
  observation. Each list offers the values among the observations matching the other filters; a change resubmits and
  clears the chosen observation (a kind change also the taxon filters). The picker lists the matching observations
  with a discussion first (with their message count), then the others, alphabetically. With `?obs=<pk>`: the
  observation (photo, name, place, date, discussion manager, a link to its page -- the species/taxon page, the
  dive-trip page of a collection, the planning section for a planned trip), its whole discussion oldest first, and the
  writing box (`#write`). Without one (the landing page): the matching observations that have a discussion, the most
  recently active first, 30 groups a page (`forum.discussion_groups`). Each is a row (photo, name, place, date,
  discussion manager, the latest message's time and writer, the message count; it opens the discussion) with its
  messages open beneath and a +/- button that folds them (open by default). A series of dive trips is one group: the
  summary trip's discussion, then its trips' discussions by date, indented; its +/- folds the whole series.
  A dive trip's row (its planning or collection observation) opens the trip's own page `/forum/trip/<code>/`. In the main menu as "פורום" and in the sitemap.
- **A trip's own discussion page** `/forum/trip/<trip code>/` (`forum.forum_trip`), to send to people: no filters,
  picker or headings. The trip's discussion (its planning, else its collection observation) and, for a summary trip,
  its trips' discussions by date, indented, all open with +/-; one writing box (a choice of trip in a series) that
  returns here (`next`). The address in the browser is the link to send (no copy button); "לדיון בפורום" in the planning section and
  page leads here. The forum page itself has no headings (the page title stays).
- **A closed dive-trip planning** (its date has passed): gone from the forum for everyone but its owner and the site
  managers, and nobody can write in it ("הדיון נסגר").
- **Discussion manager** = the observation's owner (photographer).
- **Reading:** a message "for everyone" is public (no account needed). A "manager only" message is seen by its writer, the
  discussion manager and the site managers (`views.is_manager`). A discussion of a pending or deleted observation is
  seen only by its owner and the site managers (404 for others).
- **Writing** needs an account. "הוספת תגובה" / "Add a comment" buttons: the species page (the main observation in the
  top button row, each other observation on its card, with "תגובות (N)" = the messages this visitor can read), the
  dive-trip page (its collection observation) and the home page's gallery head. They go to `/forum/new/?obs=<pk>`
  (from the home page without `obs`: to the picker, `#choose`); a visitor who is not signed in goes to the login page
  (`?next=` back there), which then offers sign-up (only when there is a `next`), and sign-up honours a safe `next`.
- **Deleting** (button on the message): its writer, the discussion manager or a site manager; marks `deleted_at`.
  Messages' text is never edited; in the admin (`ForumMessageAdmin`) a manager may change only the writer (a
  message posted on someone's behalf) and the deletion mark -- on each site separately (the transfer does not rewrite
  an existing message).
- **Email** (`notifications.notify_forum_message`, migration `0095`): a message written in the forum emails the
  observation's owner and the discussion's other writers who ticked "שליחת מייל כשמגיעה תגובה חדשה בפורום" on their
  profile (`Profile.forum_email`, off by default, per environment -- not in the profiles transfer); never the writer; a
  manager-only message goes to the owner alone. Transferred messages send nothing. Failures are only logged.
- **Transfer:** table `forum` in `/admin/table-transfer/` (`forum_transfer.py`), in both directions; additive, deletion
  wins, nothing removed; skips a message whose observation or writer is missing at the destination (TABLE-TRANSFER.md).

### 7.6 Dive-trip planning (`planned_trips.py`, `test_planned_trips.py`, migration `0096`)

- **Kind `planned`** ("תכנון מסע צלילות"): an observation of a dive trip that has not happened yet. Its DiveTrip holds
  the future date (year and month required; start day and duration optional); the observation has a title (and may have
  notes and a site) and **no media**. Any member adds one with the observation form (kind "תכנון מסע צלילות";
  `/observations/new/?kind=planned` preselects it; the form hides the media, day and depth fields); it publishes itself.
- **Shown** only in the forum (its owner manages the discussion) and in the "תכנון מסעות צלילה" section at the top of
  the dive trips page (`views.planning_rows`): title, dates, place, organizer, notes, links to the discussion, "add a
  comment" and, for its owner / managers, edit; a "תכנון מסע חדש" button. Never in the gallery, the species / taxon /
  trip pages, the sitemap or the news log (they select their kinds explicitly).
- **Closing:** after the trip's last day (`Sample.planning_open` False) the planning leaves the section and the forum,
  and its discussion is closed. The form refuses to save a planning whose trip has ended (`SampleForm.clean`); the
  model does not (the table transfer must still carry a closed one).
- **Becoming a dive trip:** its owner or a manager edits it, chooses "אוסף מינים / מסע צלילה" and adds a video or photo:
  the same row (same `transfer_id`, same discussion) becomes a regular collection (a member's waits for approval).
- **Transfer:** travels with the samples table (natural key: trip + title, like a collection; no media needed).
- **Addresses:** `/planning/` (the open plannings, the same section as on the dive trips page) and
  `/planning/<trip code>/` (keyed by the trip's permanent code): dates, place, organizer, notes, the trip's articles,
  the series links, the discussion with "add a comment". One planning per trip (`Sample.clean`). A closed planning's
  page answers its owner and the managers only (404 for others); once the planning became a dive trip with a page, the
  address answers 301 → `/trip/<code>/`. In the sitemap (the list and each open planning); the planning section, the
  forum and the series links point there.
- **A series** (DiveTrip.summary_trip): a planning on the summary trip opens a planning (discussion) for each trip of the
  series that has not ended (`sync_sub_plannings`: when the series planning is saved, and when a trip joins the summary
  trip in the admin); same owner, the trip's title. The series stays open until its last trip ends; the planning
  section shows the trips' plannings inside the series card (full width) with the trip's articles (e.g. a schedule);
  the forum links the series and its trips' discussions and shows the trip's articles.

## 8. Storage of media and documents

All uploads live under `MEDIA_ROOT` (`media/` locally, `/var/data/media/` in production). **Production
never serves `MEDIA_ROOT` directly.** Every file goes through a view that checks visibility and sends
`ETag` with `Cache-Control: public, no-cache`, so a replaced file shows at once.

| Folder | Contents | Served by |
|---|---|---|
| `observations/` | Observation photos, **canonical names**: `<trip code>-<identity>.jpg` (`Sample.canonical_image_name`): species = genus+epithet, collection = title, taxon kinds = library trip (`genera-`, `families-`, `orders-`). `-2`, `-3` on collision. Legacy content-hash names still exist. | `/observations/<pk>/photo/` |
| `articles/`, `articles/thumbs/` | Article PDFs and first-page JPEG previews (pypdfium2, 200 px) | `/articles/<slug>/<lang>.pdf` and `.jpg` |
| `identification/genera/`, `identification/thumbs/` | Genus identification files (PDF/JPG/PNG/WebP/GIF ≤20 MB) and previews of the chosen page (600 px, `<genus>-<lang>-p<N>.jpg`) | `/genus/<name>/identification/…` |
| `site/` | Home intro photo (`SiteImage`) | `/site-image/<key>.jpg` |

- **Uploads:** JPEG/PNG/WebP, ≤10 MB and ≤25 MP. They are resized to ≤1600 px and re-encoded as JPEG
  without metadata. Originals are not kept.
- **Videos:** never stored. Only YouTube URLs are kept, embedded via `youtube-nocookie`. Thumbnails come
  from `i.ytimg.com`.
- **Local (offline) video copies** (`local_videos.py`): the Mac keeps the exported files that were uploaded to
  YouTube. `DiveTrip.local_video_folder` = the absolute Mac folder, `Sample.local_video_file` = the bare file name in
  it. Both travel through table transfer (an older row without them keeps the target's value). Only the Mac can
  reach the files.
  - Status per video observation: `ok`, `missing` (not set), `not_found` (folder here, file not), `unreachable`
    (folder not on this machine -- the live site), `none` (no YouTube video).
  - Manager only: the gallery page carries `{sample id: status}` (`<script id="local-videos">`); `app.js` marks the
    ▶ red for `missing`/`not_found`/`unreachable` (no copy that plays here; `drive` and `ok` are not red). The species page shows a local `<video>` box (main observation) and a "local
    video" link (other observations), or a red "no local copy" note.
  - `/observations/<pk>/local-video/` serves the file to managers with HTTP Range (Safari needs 206).
  - Filling: `python manage.py match_local_videos` (dry run; `--apply`, `--trip/--folder/--set ID=FILE`; launcher
    `_Match local videos.command`) and the page `/admin/local-videos/`. Matching is by species name without the
    author (cf./sp. N/variant/juv. as written, optional place word like "RedSea"); `.mov` wins over a second export.
  - **Live site:** `copy_to_drive` (launcher `_Copy SeaSlugs to Google Drive.command`) copies the site (without
    `.venv`, `.git`, `.env`, `.secret_key`; the DB as an online backup) and every local video to the Google Drive
    folder `SeaSlugs.org.il`, videos under `Videos/<path under home>` (mirrored). Only `Videos` is shared
    ("anyone with the link"). `fill_drive_video_ids` (launcher `_Fill Drive video ids.command`) reads each copy's
    Drive id (xattr `com.google.drivefs.item-id#S`) into `Sample.drive_video_id` (new ids replace old ones, ids of copies that are gone are emptied; also the page `/admin/drive-videos/`), which travels with the samples
    table. Where the Mac file is unreachable but a Drive id exists (status `drive`), a manager sees Drive's player
    (`/file/d/<id>/preview`) instead of the red mark.
- **Cleanup of replaced or cleared files**
  - The `_delete_replaced_files` pre-save signal deletes the old file unless another row still uses it.
    It applies to Article PDFs and thumbs and to all TaxonGenus file fields.
  - The observation form deletes the old photo itself.
- **Orphans:** removed deliberately in the admin (image manager "redundant", article-files page) or with
  `cleanup_deleted_and_orphaned_images`. The image manager protects every file a TaxonGenus field
  references (`IDENTIFICATION_FIELDS`).
- **Tests** use a throw-away `MEDIA_ROOT` (set in settings when `argv[1]=='test'`). Never let tests write
  into `media/`.

## 9. Management tools

### 9.1 Django admin (`/admin/`, staff)

- **Samples:** editable changelist, cascading dropdowns, status/pending filters, and actions approve /
  soft remove / restore. Restore explains itself when the observation has no media.
- **Species:** editable columns (`is_migrant`, names, author, family, order, observed years), a
  reference-link column, and "view on site" buttons for each SpeciesArea page.
- **TaxonOrder / TaxonFamily / TaxonGenus**
  - Two taxonomy filters: order by name, then sub-order/superfamily, with gallery counts.
  - Defining-sample choices limited to rows that fit, a "view on site" button, and the genus action
    "refresh defining samples".
- **SpeciesArea:** defining-sample choice and the action "rebuild all".
- **DiveTrip:** inline samples. **Region:** `trip_code`. **Article** (with sections). **Users:** with
  Profile.
- **Reference tables:** qualifiers, life stages, countries, seas, regions, sites.

### 9.2 Custom admin pages (superuser)

| URL | Purpose |
|---|---|
| `/admin/images/` | Image manager: every media image with the observations using it, sort by file/alpha/taxonomy, kind groups, redundant-image detection, safe delete, rename. **Compare with the other environment** (export a list, upload it on the other side) and **transfer images** (up to 150 photos / 300 MB per upload). A downloaded photo carries every live observation that shows it (owner first, then gallery-image users such as a trip collection); the upload creates/updates all of them and links the others to the owner's file. |
| `/admin/images/folder/` | Folder import: reviewed bulk import of a folder of images with an Excel sheet. One species selector per image (≤500). Staging in `folder-import-staging/`, auto-cleaned. |
| `/admin/table-transfer/` | Table transfer (§10.2) |
| `/admin/local-videos/import/` | Video import by dive trip (Mac only): pick the trip and its Mac video folder; each video file gets a row with its observation (the one holding the file, else the match by species name, else a new species or trip-collection observation with species/cf./juv. guessed from the file name plus site, day, depth), the existing observation's fields, the Mac path, the Drive copy path and id, and a required YouTube link. Only rows of files that belong to a live observation and are not attached to it yet are selected and shown; the others (new observation, deleted observation, already attached) sit in a closed list below with their counts. A file of a deleted observation of the trip (no live one) is offered with it; choosing it restores the observation. Saving (backup, one transaction; nothing saved if any selected row is invalid; a link YouTube reports deleted is refused) sets the trip's folder, writes video_url / local_video_file / drive_video_id, creates the new observations (a manager's save publishes), then copies missing files into Drive and reads their ids (not yet uploaded -> `/admin/drive-videos/` later). Then transfer the samples table. |
| `/admin/drive-videos/` | Google Drive video ids (Mac only): rescans the Drive copies' ids (`drive_videos.py`, the same scan as `fill_drive_video_ids`). A replaced file is a new Drive file, so the stored id showed the old preview and did not play. Sorts each observation into same / update (new id) / clear (copy gone, or no local file) / waiting (copy not uploaded yet: id kept) / missing (no copy); one button backs up and saves update + clear. Then transfer the samples table. |
| `/admin/video-check/` | YouTube video check: a scan asks YouTube's oEmbed about every live observation's video (200 ok, 404/400 deleted, 401/403 private or embedding blocked, no answer = check failed; parallel, no API key). The problem ids are kept in the session; each observation still using one gets: update the link (re-uploaded video: must exist and be unused; local/Drive copies kept; not logged as a new video), remove the link (only with a photo; clears the local/Drive copy fields) or delete the observation (only without a photo; soft delete). Per environment: transfer the samples table or scan on both sides. |
| `/admin/local-videos/` | Local (offline) video copies: per-trip Mac folder, each video observation's file (auto-match pre-selected), automatic fill, local playback (§8) |
| `/admin/article-files/` | Article PDFs and genus identification files: which row uses each, open, delete orphans and unused library articles, article transfer between environments |
| `/admin/releases/` | Download a ZIP of a verified DB backup plus all media (and the count and size of the backups folder; automatic `table-transfer-*` backups are kept 7 days, always at least the newest 5, hand-named ones never pruned) (contains private data; never upload it to GitHub). Mac launcher: `Release Manager.command`. |
| `/admin/db-replace/` | Full DB replacement: back up → lock the site (flag file, `MaintenanceModeMiddleware`; staff, `/admin/` and `/healthz` pass) → download live DB → upload replacement + missing images → review → apply → release |
| `/observations/home-text/` | Edit home-page sections, per language, in a small markup (`home_markup.py`: `#`, `##`, lists, `**bold**`, `[text](link)` with keywords `contribute`, `gallery`, `migrant`, and `[[text]]` for the green button). Clearing a section restores the default. |

### 9.3 Management commands (`python manage.py …`)

- **Maintenance**
  - `backup_database`: verified online backup.
  - `assign_genus_defining_samples`: fix every taxon row's defining sample.
  - `backfill_species_area_slugs`.
  - `build_taxonomy_tables`: build TaxonOrder, TaxonFamily and TaxonGenus from Species.
  - `rename_images_to_canonical`.
  - `cleanup_deleted_and_orphaned_images`.
  - `fill_reference_links`: iNaturalist/WoRMS lookups, resumable. Launcher:
    `_Fill species reference links.command`.
  - `test_email`.
  - `setup_community`: groups and geography seed; repeatable.
- **Imports** (local only; most were one-off migrations from the owner's Excel workbook)
  - `import_species_catalog`, `import_species_science`, `import_gallery_species`.
  - `import_gallery_samples`, `import_dive_trips`, `import_missing_no_video_samples`.
  - `fill_philippines_trip_gaps`, `redistribute_philippines_samples`, `reconcile_defining_samples`.
  - `import_genus_texts` (CSV), `import_article_html` (two HTML files → site-written article).
  - `plan_philippines_2027`: the planned Visayas series of Feb–Mar 2027 (sea, regions, liveaboard sites, summary trip +
    3 trips, plannings, opening forum messages, schedule article). Run on the Mac on 2026-11-10; refuses to run twice.
  - All of them default to a dry run, need `--apply`, and back up first.

## 10. Moving data between the Mac and the site

The owner curates data mostly on the Mac and moves it to production. Rules that hold for every tool:

- Rows are matched by **natural keys**, never by database ids: trip `code`, `Sample.transfer_id`,
  species `source_id` or scientific name, location names with their parent, taxon identity, article
  slug, username.
- Every apply step **previews** the changes, makes a **verified SQLite backup**, and applies in **one
  transaction**.
- Approvals expire after 30 minutes and are bound to the user.
- **Both environments must run the same code version** when a transfer format changes.
- The "ZIP of observations and images" mechanism was **cancelled**. Never suggest it again.

### 10.1 Order of a full sync (`TABLE-TRANSFER.md`)

1. Users (accounts without passwords or sessions).
2. Countries, seas, regions, sites. Optionally a **full location sync** with merges and deletions.
3. Qualifiers, life stages, species.
4. Trips.
5. Orders, families, genera (page texts only; rows must already exist; matched by identity).
6. Samples. Images move separately in the image manager, and **image files through the samples table
   are blocked**.
   - Deleted observations travel with a `deleted` mark.
   - Optional "permanent delete" removes deleted observations that are missing from the file.
7. SpeciesArea (needs Samples; the slug of an existing row is never overwritten).
8. Taxonomy tables again, to apply defining samples now that the samples exist.
9. Forum (`forum`): the conversations, in both directions (needs Users and Samples).

### 10.2 Table transfer details

- Export a single table as JSON. Import up to 20 MB and 10,000 rows. The preview shows additions and
  before/after values.
- The format is checked strictly: "fields do not match" means the two environments run different code.
- **Forum messages** (table `forum`, last): matched by `transfer_id`, observation by Sample `transfer_id`, users by
  username; only new messages and deletions travel (see §7.5).
- **Trips** carry `summary_trip` by code; a summary trip that is new in the same file is linked after all rows are
  saved; a file from before the field keeps the destination's value.
- Some fields are **not** transferred and are set per environment by migration or admin: `Region.trip_code`,
  `Profile.trip_code`, taxon files and the identification preview pages.

### 10.3 What does not travel through table transfer

- `Sea.url_code` (gallery link codes): set by migration `0090` on each site, else in the admin on each site.

- Article PDFs travel through the article transfer on `/admin/article-files/`.
- Genus identification files and their preview page numbers are uploaded directly on each site, in the
  observation edit form of the genus observation or in the admin.

## 11. SEO and Google

Done between 2026-09-26 and 2026-10-11:

1. **`/sitemap.xml`** (`django.contrib.sitemaps`, `SITEMAPS` in `observations/sitemaps.py`): the home
   page, the news page, plus species, genus, family and order pages. It lists **only pages that answer 200**, applying
   the same rule as the page views. HTTPS on the Site domain.
2. **`/robots.txt`**
   - Disallows `/admin/`, `/analytics/`, the members-only listing (`/observations/$`), and the forms,
     autocomplete, login, profile, partners, trip-management and home-text pages.
   - Keeps `/observations/trips/` and `/observations/<pk>/photo/` crawlable; the photo is every page's
     `og:image`.
   - Points to the sitemap.
3. **Canonical, hreflang and Open Graph** (`_share_meta.html`)
   - The canonical is the page's own URL.
   - hreflang: he = `/x/`, en = `/x/?lang=en`, x-default = he.
   - Open Graph: `og:title`, `description`, `image`, `locale` and `locale:alternate`; Twitter
     `summary_large_image`.
   - **One address per language.**
4. **SEO phase 1** (`test_seo_phase1`)
   - Genus sitemap = page rule; `/index.html` → 301 `/`.
   - `?lang=en` kept in navigation links.
   - Species `<title>` includes the place.
   - Meta descriptions are built from the data when no text exists (`seo_text.py`).
5. **SEO phase 2:** the home page's language, title, description, canonical and hreflang are rendered
   by the server, not by JS.
6. **SEO phase 3** (`test_home_content`): the home page's readable content is server-rendered in the
   URL's language: hero, "what are sea slugs", the Mediterranean project, how to contribute, the numbers
   line, the footer invitation, and a collapsed block of crawlable links to groups and Israeli species.
   Both languages are embedded for the JS switch.
7. **Google Search Console**
   - Ownership is verified with the HTML meta tag. The content comes from the `GOOGLE_SITE_VERIFICATION`
     environment variable; blank means no tag.
   - After the GSC audit on 2026-10-08, **historical species URLs got verified 301 redirects**
     (`species_redirects.py`). The manifest pairs exact old→new URLs, keyed by an observation's
     `transfer_id` so a reused slug can never redirect to an unrelated population.
   - Retired URLs (the Philippines spelling fix, old Nudibranchia group pages) also return 301.
8. **Google Analytics 4** (`G-CPGTC09P2P`)
   - On every public page, **not** on `/admin/` tools.
   - Skipped when the `exclude_analytics=1` cookie is set (the owner's personal opt-out via
     `/analytics/exclude/`).
   - `test_analytics` guards this.
9. **Slugs never change once published.** A rename must keep the old URL working with a 301.

When adding a public page type: add it to the sitemap only for the rows that answer 200, give it
canonical/hreflang/OG meta via `_share_meta.html`, put the GA snippet (with the opt-out check) in it,
make all text go through `|t:lang`, and add an English translation.

## 12. Security and privacy

- **Roles:** members edit and delete only their own non-deleted observations. Managers (staff with
  `change_sample`) see and edit everything. Superusers get the custom admin pages.
- **Images and private records:** photos of pending or deleted observations are not served to the
  public. Production never exposes `MEDIA_ROOT`.
- **Partners directory:** members only and opt-in (`visible_to_members`). No email addresses are
  exposed.
- **Transfers:** no passwords, sessions or permissions are transferred. Release ZIPs and backups hold
  private data.
- **Error logging:** errors (500) are logged to the console with a traceback (Render logs). There is no
  email to admins.
- **Uploads:** content is validated (Pillow format checks, PDF/extension validators, size limits).
  An HTML file in the article folders is only ever shown as plain text.

## 13. How to work on this project (rules for Claude Code)

1. **Never push and never publish.** Boaz publishes. Do not run `git push`, `git stash` or `git reset`
   on his working tree, and do not commit unless asked.
   - Cowork's Linux VM cannot delete files in the connected folder without permission. A git command
     there can therefore leave `.git/index.lock` behind. Remove only a lock you created yourself.
2. **Look before you change.** Read the relevant module docstring and the tests named after the feature.
   Most modules start with a docstring that explains the *why*.
3. **Keep the mirrored logic in step:** names italics, counts, translations, the drill-down rules
   (`app.js` ⇄ Python).
4. **Data changes:**
   - Write **migrations** for schema and catalogue fixes. Data migrations are the normal way to fix the
     catalogue, and they must be safe to run in both environments.
   - Back up `db.sqlite3` to `backups/` before you migrate locally.
   - Remember production runs the migration on the next deploy.
5. **Bilingual by default:** every new user-facing string goes through `|t:lang` with an English entry,
   or into `app.js`'s language table. Every page shows one language. Add `?lang=en` to internal links.
6. **Respect the wording and catalogue rules** in §6.
7. **Ask before deleting** files or rows, or making irreversible data operations.
8. **Every feature or fix gets regression tests** in a `test_<feature>.py` module. Explain the rule in the
   class docstring.
9. **Before saying "done":**
   - `python manage.py check`
   - `python manage.py makemigrations --check --dry-run` (should only fail when you meant to add a
     migration)
   - the test modules you touched, plus the full suite (§14)
   - for UI changes, a look in the browser at `http://127.0.0.1:8000/` in both languages
10. **Tell Boaz what to publish:** the list of changed files and a suggested commit description, plus any
    data he must transfer or set on the live site (§10.3).

## 14. Tests

Run everything: `python manage.py test observations` (about 1,000 tests, 1–3 minutes). Single module:
`python manage.py test observations.test_genus_page`.

- Settings switch tests to a temporary `MEDIA_ROOT` and plain static storage.
- Email uses Django's in-memory backend.
- In Cowork's Linux VM, one long run of the whole suite sometimes hangs. Run module by module instead
  (a loop over `observations/test_*.py` plus `observations.tests`). Every module passes on its own.

Catalogue of test modules (test count) and what each guards:

| Module | # | Guards |
|---|---|---|
| `tests` | 67 | Core workflow: registration privileges, first/repeat/Other publication, moderation completeness, owner-only edit/delete, hidden deleted records, image resizing, language cookie, listing defaults/filters |
| `test_sample_taxonomy` | 65 | Sample order/family/genus/species by kind, cf./aff./juv., full name, image file name, form, transfer format compatibility |
| `test_genus_page` | 58 | Genus page: identification file, captions, back/edit buttons, taxon pages' buttons, save messages |
| `test_genus_page_filter` | 8 | The gallery's filter carried to the genus page: filtered species first with their matching observations, the others as small cards, stale parameters ignored |
| `test_media_transfer` | 57 | One observation per species per trip; image storage, canonical names, replacing photos, environment image comparison and transfer |
| `test_trip_species_links` | 2 | Trip page species pictures open the observation on its species page |
| `test_summary_trips` | 14 | Summary trips: one-level rules, admin choices and filters, species of the series (trip page, count, trips table, gallery filter), trips transfer, series planning (sub-plannings, joining later, open until the last trip, planning section and forum), Excel-pasted tables, the plan_philippines_2027 command |
| `test_planned_trips` | 16 | Dive-trip planning: no media, title + year/month, self-publishing, no media observation on a future trip, trip dates, form (?kind=planned, past trip refused, conversion to a collection keeps the discussion), trips page section, not in the gallery, forum open/closed |
| `test_forum` | 39 | Observations forum: per-observation discussions only, kind / photographer / place / year / taxon filters and picker, grouped view, who reads public / manager-only messages, writing needs an account, login → sign-up → back, delete rights, species/trip/home buttons, sitemap/robots, the `forum` table transfer |
| `test_news_activity` | 31 | Activity log events, visit counter exclusions, /news/ page, posts, backfill |
| `test_articles` | 73 | Article library, sections on pages, PDFs, previews, site-written articles, home articles |
| `test_home_content` | 47 | SEO phase 3: server-rendered home content in both languages, editable home texts |
| `test_gallery` | 37 | `/observations/` filters, manager-only owner filter, sort, dropdown options |
| `test_trip_manage` | 33 | Trip management page, filters, suggested name and code |
| `test_trips` | 31 | Public trips page, profile/sign-up translations, trip lists |
| `test_species_areas` | 28 | Trip sea = region sea, site lookup, SpeciesArea behaviour |
| `test_taxonomy` | 28 | Taxonomy tables, resolver |
| `test_canonical_image_naming` | 26 | `canonical_image_name()` rules and collisions |
| `test_species_change` | 25 | Changing an observation's species in place |
| `test_seo_phase1` | 25 | Sitemap rules, `/index.html` 301, lang in links, species titles and descriptions |
| `test_taxon_files_form` | 24 | Manager-only taxon texts/articles/identification file on the observation form |
| `test_db_replace` | 21 | Full DB replacement and the maintenance lock |
| `test_species_redirects` | 20 | Historical 301 redirects |
| `test_species_admin` | 17 | Editable species changelist |
| `test_order_page_whole_order` | 17 | Order page holds the whole order; back-to-gallery `?up=` links |
| `test_folder_import` | 16 | Folder import |
| `test_existing_image` | 15 | Reusing another observation's gallery image (`gallery_source`) |
| `test_reference_links` | 15 | iNaturalist/WoRMS matching |
| `test_taxon_transfer`, `test_transfer` | 15+15 | Table transfer of taxon texts and reference tables |
| `test_article_files` | 13 | Article/identification files page |
| `test_analytics` | 12 | GA tag on public pages only, opt-out cookie |
| `test_seo` | 12 | Canonical/hreflang/OG, robots |
| `test_photographer_users` | 12 | Photographer = observation owner, guest users |
| `test_location_sync` | 9 | Full location (region/site) sync |
| `test_names` | 9 | Italics rule server and JS |
| `test_species_page_edit_buttons` | 9 | Edit observation/species buttons |
| `test_speciesarea_transfer` | 9 | SpeciesArea transfer |
| `test_taxon_order_filter` | 8 | Admin taxonomy filters |
| `test_cleanup_deleted_and_orphaned_images` | 8 | Orphan cleanup command |
| `test_collection_title_en` | 7 | English collection titles, trip-filter years |
| `test_species_add`, `test_species_observation_counts` | 7+7 | Adding species; counters wording |
| `test_assign_genus_defining_samples`, `test_import_genus_texts`, `test_signup_email`, `test_sitemap`, `test_genus_placeholder_migration` | 6 each | as named |
| `test_genus_identification_bilingual` | 5 | he/en identification files, preview page, fallback, image as own preview |
| `test_account_transfer`, `test_releases`, `test_card_media_marks` | 5 each | as named |
| `test_gallery_order_media_source`, `test_gallery_others_source`, `test_taxon_card_frames`, `test_listing_filter_layout`, `test_species_list_check_migration` | 4 each | gallery card media, "Others" cards, rank frames, listing CSS, catalogue fix |
| `test_listing_genus_filter`, `test_manager_auto_publish`, `test_sample_changelist_form`, `test_taxon_samples_stay_published`, `test_trip_sea_removal`, `test_library_image_repair`, `test_coryphellina_merge_migration`, `test_worms_suborders_migration` | 3 each | as named |
| `test_superfamilies_into_orders_migration`, `test_names_and_fossils_migration`, `test_sample_status_filter` | 2 each | as named |
| `test_trip_picker_tools` | 3 | The import tools pick the trip like the observation form (filters, labels, add-trip link, no library trips) |
| `test_video_import` | 12 | Video import: matching and guesses, required YouTube link, save/create/copy to Drive, all-or-nothing, duplicates |
| `test_backup_retention` | 4 | Automatic backups pruned: 7 days, at least the newest 5, hand-made ones kept; releases page summary |
| `test_drive_video_ids` | 6 | Drive id rescan: same/update/clear/waiting/missing, page and command save, nothing without the Drive folder |
| `test_video_check` | 12 | YouTube video check: status mapping, scan lists only problems, remove link / delete / update rules |
| `test_template_translations`, `test_error_logging`, `test_samples_follow_taxonomy_migration`, `test_species_name_migration`, `test_worms_family_cleanup_migration` | 1 each | every `\|t` literal has English; 500s are logged; data migrations |

**Browser checks** (no automated JS test runner):

- Open the local site and use the browser's JS console. `state`, `render()`, `history.state` and
  `window.SEASLUGS` are global.
- Verify both languages, mobile width, and the Back button.
- `node -e "new Function(require('fs').readFileSync('dist/app.js','utf8'))"` is a quick syntax check
  for `app.js`.

## 15. Debugging playbook

| Symptom | Where to look |
|---|---|
| A species is missing from the gallery | Its SpeciesArea `defining_sample` (published? not deleted? has media?), trip has year/country/region→sea, no `species_other`/`site_other`. Admin action "rebuild all" on SpeciesArea. |
| A taxon card or page shows the wrong or no photo | `defining.py` rules, the row's `defining_sample`, `assign_genus_defining_samples`, the genus admin action |
| A page answers 404 but should exist | Page views 404 when no live species/media exists; the sitemap applies the same rule |
| "This video is unavailable" in a player | The YouTube video blocks embedding (error 150/101, often a copyright claim). The site now falls back to the photo. The fix is in YouTube Studio (Restrictions, Allow embedding). |
| An English page shows Hebrew | Missing `TRANSLATIONS` entry (run `test_template_translations`) or the `app.js` table |
| Language lost between pages | Links must use `with_lang`; check the `seaslugs_lang` cookie |
| Transfer: "fields do not match" | The environments run different code. Publish first. |
| Transfer blocked: "missing reference" / "sample missing" | Transfer the parent table or Samples first (§10.1) |
| 500 on Render | Render logs (traceback on console). Reproduce locally with a copy of the DB from `/admin/releases/` or `/admin/db-replace/` |
| "database is locked" | A long write overlaps another; SQLite with one gunicorn worker. Keep writes in short transactions. |
| A file shows the old version | Views send `no-cache` + ETag; check the file was really replaced and the old one deleted (`_delete_replaced_files`) |
| A Render deploy fails at start | `start.sh` refuses if `/var/data` is missing or the backup's integrity check fails |

## 16. Rebuilding from scratch (outline)

1. **Project:** Django 5.2 project `config` and app `observations`. Settings as in §3, with
   `PRODUCTION` from the environment, `DATA_DIR` (and so the DB and MEDIA) on `SEASLUGS_DATA_DIR`,
   whitenoise, logging, and the test-only temporary `MEDIA_ROOT`.
2. **Models of §5**, in this order:
   1. geography
   2. Species
   3. taxonomy tables
   4. DiveTrip
   5. Sample with `transfer_id`, soft delete and status
   6. SpeciesArea with stable slugs
   7. Article / ArticleBlock / ArticleReference
   8. Profile
   9. HomeText / SiteImage
   10. reference tables
3. **Domain logic of §6:** `save_reviewed`, `pick_defining_sample`, `defining.py`, `sync_taxonomy`,
   canonical image names, `_delete_replaced_files`. Write the tests together with the logic.
4. **Public pages of §7.1**, with `_share_meta.html` and the `|t:lang` filter. Photo, file and PDF
   streaming views with ETag/no-cache.
5. **The gallery:**
   - `dist/index.html`, rendered as a Django template, with the home sections.
   - `/catalog.js` generated from the DB.
   - `app.js` with state, filters, sorts, the drill-down, history and `?up=`.
   - `youtube-fallback.js`.
6. **Community:** sign-up/login (Django auth), profile, partners, observation form with image
   processing, trips management.
7. **Admin:** model admins and the custom pages of §9.2. Transfer tools of §10, all with preview, backup,
   transaction and natural keys.
8. **SEO of §11:** sitemap, robots, redirects, GA with opt-out, Search Console tag.
9. **Deploy of §2:** Render with a disk, `build.sh`, `start.sh` (backup → migrate → gunicorn), the custom
   domain, and the publish script.

## 17. Open items and ideas

- The scientific focus (Lessepsian migration, species turnover) is shown only as a filter (migrants,
  first/last seen years) and a home-page section. Analysis pages are a future goal.
- Article on *Phyllidia ocellata* (one species or a species complex?) as a bilingual site article.
- Email verification, password recovery and member messaging are not implemented.
- `config/views.py` still has its own inline copy of the species→taxon resolution. It should use
  `gallery_data.py`.
- Storage quotas and retention for uploaded images are not defined.

## 18. Facts to confirm with the owner (not visible in the code)

- Domain registrar and DNS provider for `seaslugs.org.il`, and the exact DNS records.
- Render plan name, disk size and region.
- Search Console property type (domain vs URL-prefix) and whether the sitemap was submitted there.
- The SMTP provider used for `EMAIL_HOST`.
