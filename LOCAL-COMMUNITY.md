# Local community development

This change is local only. Do not run Publish SeaSlugs until you intend to deploy it.

## Pages
- `/observations/`: published observations; signed-in owners also see their pending observations. Staff with change-observation permission see deleted and pending records.
- `/observations/signup/`, `/observations/login/`: account registration and login.
- `/observations/new/`: observation submission.
- `/observations/profile/`: opt-in macro-diving profile and countries/regions.
- `/observations/partners/`: member-only directory, with country and region filters. No email addresses exposed. Messaging is not implemented.
- `/admin/`: reference data, profiles and moderation. Use a local administrator, not the separate production account.

## Initial setup
Migrations and `python manage.py setup_community` have already run locally. This command is repeatable and seeds groups, countries, seas and the requested Israeli regions without assigning privileges to users. No species or dive sites were invented. Add real reference records through admin or later import.

Before migration, a SQLite backup was created under `backups/` (ignored by Git).

## Moderation
Complete observations without any Other values are published if no published, non-deleted observation exists for the same species and region. Other observations await review. Admin approval requires resolving all Other values to reference records. Editing an observation re-evaluates its status. Deletion is soft; admin actions approve, remove and restore. Restore re-evaluates publication.

Users can edit/delete only their own non-deleted observations. Public requests cannot obtain private/deleted uploaded images through the photo endpoint. YouTube thumbnails are external public images.

## Images
JPEG/PNG/WebP uploads are limited to 10MB and 25 megapixels, resized to at most 1600px and encoded as JPEG without original metadata. Originals are not retained. Existing image files are not automatically purged when observations are removed or images replaced; a storage retention/quota policy is still needed before large-scale collection.

## Roles
New users receive New user with no staff permissions. Macro diver is a self-selected directory preference, with no elevated editing rights. Subscriber, Macro photographer and Artist are available groups, but specialized galleries/articles/art workflows are not yet implemented. Scientist receives species view/add/change permissions; admin interface access additionally requires a staff account, which only a trusted administrator should grant. Administrator group includes community permissions; user/group management remains with a superuser or explicitly authorized auth permissions. Diver is not created.

## Limits of this local version
The existing 107-video gallery remains unchanged; its records have not been imported into observations because required metadata is missing. The community forms currently use Hebrew with bilingual navigation, not the gallery's full language switch. Email verification/password recovery, messaging, articles and personal art galleries are not included in this first observation workflow.

## Checks
`python manage.py test observations` covers registration privilege isolation, hierarchy/date checks, first/repeat/Other publication, moderation completeness, owner-only edits/deletion, hidden deleted records and image resizing. `python manage.py check` checks configuration.
