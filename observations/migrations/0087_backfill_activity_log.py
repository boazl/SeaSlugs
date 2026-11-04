"""Fills the new activity log (ActivityEvent, see activity.py) from what the database already holds, so the /news/
page and its filters have the site's history from the start: every public observation and its video (at the time it
was created), every gallery card as a new species (at its first observation, with the new-to-site / new-to-sea marks
worked out in time order) and every real sign-up. Runs once in each environment, from that environment's own data;
lines it adds carry detail.backfill. Reversing it removes only those lines."""
from django.db import migrations


def _label(sample):
    if sample.kind == 'collection':
        return sample.title or ''
    species = sample.species
    if not species:
        return sample.species_other or ''
    if sample.identification_qualifier and species.genus and species.species:
        name = f'{species.genus} {sample.identification_qualifier} {species.species}'
    else:
        name = species.scientific_name
    return ' '.join(p for p in (name, sample.life_stage) if p)


def backfill(apps, schema_editor):
    from observations.models import youtube_id
    Event = apps.get_model('observations', 'ActivityEvent')
    Sample = apps.get_model('observations', 'Sample')
    Area = apps.get_model('observations', 'SpeciesArea')
    User = apps.get_model('auth', 'User')
    if Event.objects.exists():
        return
    events = []
    live = (Sample.objects.filter(status='published', deleted_at__isnull=True, kind__in=('species', 'collection'))
            .select_related('species', 'trip', 'trip__region').order_by('created_at', 'pk'))
    for s in live:
        trip = s.trip
        common = dict(created_at=s.created_at, sample_id=s.pk, sample_transfer_id=s.transfer_id, user_id=s.owner_id,
                      species_id=s.species_id, country_id=trip.country_id if trip else None,
                      sea_id=trip.region.sea_id if trip and trip.region_id else None, name=_label(s)[:300], public=True)
        events.append(Event(kind='observation_added', detail={'backfill': True}, **common))
        if s.video_url:
            try: video = youtube_id(s.video_url)
            except Exception: video = s.video_url
            events.append(Event(kind='video_added', detail={'backfill': True, 'video': video}, **common))
    areas = []
    for area in Area.objects.filter(defining_sample__isnull=False).select_related('species', 'defining_sample'):
        first = (Sample.objects.filter(kind='species', status='published', deleted_at__isnull=True, species_id=area.species_id,
                                       trip__country_id=area.country_id, trip__region__sea_id=area.sea_id,
                                       undetermined_variant=area.undetermined_variant)
                 .order_by('created_at', 'pk').first()) or area.defining_sample
        areas.append((first.created_at, area.pk, area, first))
    seen_species, seen_sea = set(), set()
    for when, _, area, first in sorted(areas, key=lambda x: (x[0], x[1])):
        variant = area.undetermined_variant or ''
        events.append(Event(kind='species_new', created_at=when, public=True, species_area_id=area.pk, species_id=area.species_id,
                            country_id=area.country_id, sea_id=area.sea_id, sample_id=first.pk, sample_transfer_id=first.transfer_id,
                            user_id=first.owner_id, name=f'{area.species.scientific_name} {variant}'.strip()[:300],
                            detail={'backfill': True, 'variant': variant, 'new_to_site': area.species_id not in seen_species,
                                    'new_to_sea': (area.species_id, area.sea_id) not in seen_sea}))
        seen_species.add(area.species_id); seen_sea.add((area.species_id, area.sea_id))
    for user in User.objects.filter(is_active=True, is_superuser=False).exclude(username='boazl').exclude(password__startswith='!'):
        events.append(Event(kind='signup', created_at=user.date_joined, public=False, user_id=user.pk, name=user.username,
                            detail={'backfill': True}))
    Event.objects.bulk_create(events, batch_size=500)


def remove(apps, schema_editor):
    apps.get_model('observations', 'ActivityEvent').objects.filter(detail__backfill=True).delete()


class Migration(migrations.Migration):
    dependencies = [('observations', '0086_activity_log_news_visits'), ('auth', '0012_alter_user_first_name_max_length')]
    operations = [migrations.RunPython(backfill, remove)]
