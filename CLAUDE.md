# CLAUDE.md — SeaSlugs.org.il

The full system reference is **`docs/SYSTEM.md`**. Read it before planning a feature or fixing a bug.

## What this is

- **Site:** a bilingual (Hebrew default, English with `?lang=en`) Django 5.2 + SQLite site about sea
  slugs ("חינניות ים").
- **Main parts:**
  - a public gallery (`dist/app.js`, data from the generated `/catalog.js`)
  - per-species, genus, family and order pages
  - a member community (observations, dive trips, partners)
  - admin tools for moving data between the Mac and production
- **Hosting:** Render (`seaslugs.onrender.com`), domain **https://seaslugs.org.il/**.
- **Owner:** Boaz Liebes. In Hebrew, address him in the masculine form.

## Commands

```sh
source .venv/bin/activate
python manage.py runserver 127.0.0.1:8000
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test observations                      # ~1,000 tests
python manage.py test observations.test_genus_page      # one module
node -e "new Function(require('fs').readFileSync('dist/app.js','utf8'))"   # app.js syntax check
```

## Hard rules

1. **Never `git push` or publish.** Boaz publishes with `___Publish SeaSlugs.command`, which pushes to
   `main` and auto-deploys to Render. Do not commit unless asked. Do not `git stash` or `git reset` his
   working tree. At the end, list the changed files and suggest a one-line commit description.
2. **Code only travels through git.** The local and production databases are separate. Data moves only
   through the admin transfer tools (`/admin/table-transfer/`, `/admin/images/`, `/admin/article-files/`).
   Tell Boaz what data he must transfer or set on the live site. Never suggest the cancelled "ZIP of
   observations and images" mechanism.
3. **Never commit** `db.sqlite3`, `media/`, `backups/`, `.secret_key`, `.env`, `*.docx` or Google Docs
   exports. Back up `db.sqlite3` to `backups/` before running migrations locally.
4. **Every change gets regression tests** in `observations/test_<feature>.py`, with the rule in the class
   docstring. Run the touched modules, then the whole suite. If a full run hangs in the Linux VM, run it
   module by module.
5. **Bilingual by default.**
   - Hebrew template literals go through `{{ "…"|t:lang }}` with an English entry in
     `observations/templatetags/seaslugs_i18n.py` (`test_template_translations` enforces this).
   - Internal links use `|with_lang:lang`.
   - Every page shows one language only, with the same header everywhere.
6. **Keep the mirrored logic in step** between Python and `dist/app.js`:
   - name italics (`names.py` ⇄ `setLatinName`)
   - count wording (`counts.py` ⇄ `countText`)
   - translations
7. **Published URLs never change:** `SpeciesArea.slug` is permanent. A rename needs a 301
   (`species_redirects.py`).
8. Ask before deleting files or rows, or before any irreversible data operation.

## Domain rules (details in `docs/SYSTEM.md` §6)

- **Terms:**
  - "חינניות ים" = sea slugs; "חשופיות" = nudibranchs only.
  - "הוספת תצפית" / "Add an observation".
  - "תצפית" in the gallery = a SpeciesArea (species in an area); "מינים" = distinct species.
  - Counters show species only. The exception is "כל האזורים": "N מינים ב-M תצפיות".
- **Names:** scientific names are italic for genus + epithet only, never for cf./aff./sp./author/juv.
  Every full species needs an author. Merge duplicates into the WoRMS accepted name. When checking a
  list, fix the catalogue, not the list. The labels burned into photos are deliberately fully slanted;
  don't flag them.
- **Taxonomy:** WoRMS ranks only:
  orders → sub-orders + Others → superfamilies + Others → families + Others → genera → species.
  All ranks behave alike: a defining photo, a page, a card and navigation buttons.
- **Gallery navigation:** a genus card opens the genus page. "Back to the gallery" goes one rank above
  the page's taxon (`/?restore=1&up=<rank>:<key>`). The browser Back button returns to the previous
  gallery view.
- **Publication:** a complete species observation publishes itself, and a manager's save publishes.
  Otherwise it stays pending. Publishing creates or updates the SpeciesArea and its defining sample.
- **Changing an observation's species** happens in place: same row, same `transfer_id`.
