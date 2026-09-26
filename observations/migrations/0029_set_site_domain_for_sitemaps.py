# django.contrib.sites (newly added to INSTALLED_APPS for the /sitemap.xml feature -- see
# observations/sitemaps.py) ships its own migration that seeds exactly one Site row (pk
# matching settings.SITE_ID) with domain='example.com'. This migration points that row at the
# real production domain instead, so every environment's sitemap builds the same
# https://seaslugs.org.il/... URLs regardless of which host actually served the request.
from django.conf import settings
from django.db import migrations


def set_site_domain(apps, schema_editor):
    Site = apps.get_model('sites', 'Site')
    Site.objects.update_or_create(
        pk=settings.SITE_ID, defaults={'domain': 'seaslugs.org.il', 'name': 'SeaSlugs'})


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('observations', '0028_fix_region_country_when_all_its_trips_disagree'),
        ('sites', '0001_initial'),
    ]
    operations = [
        migrations.RunPython(set_site_domain, noop_reverse),
    ]
