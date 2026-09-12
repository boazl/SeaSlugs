# Render deployment

Use Python 3, branch main, empty Root Directory, the selected paid single instance and a persistent disk mounted at /var/data.

- Build Command: `bash build.sh`
- Start Command: `bash start.sh`
- Health Check Path: `/healthz`
- Pre-Deploy Command: empty (the disk is unavailable during this phase)
- Auto-Deploy: Off initially

Environment variables:
- DJANGO_ENV = production
- DJANGO_SECRET_KEY = generate a new random secret in Render
- SEASLUGS_DATA_DIR = /var/data

Render provides RENDER_EXTERNAL_HOSTNAME automatically. When connecting a custom domain, add DJANGO_ALLOWED_HOSTS=seaslugs.org.il,www.seaslugs.org.il. Test the Render URL before changing DNS.

The first deployment creates a NEW SQLite database. The Mac database and administrator are preserved locally, not uploaded through Git. Create a production administrator in the Render Shell with `python manage.py createsuperuser`. Code deployments do not replace the production database.

Media is configured under /var/data/media. The current gallery embeds YouTube videos; a media upload/serving interface and a database download interface are not implemented yet.

Do not copy an active SQLite file directly: create a consistent backup using SQLite's backup API before downloading. Local and production databases are separate copies and do not synchronize automatically.

The start script runs migrations at runtime after the persistent disk is available. Disk-backed deployments briefly interrupt service. Keep independent database backups before schema changes.
