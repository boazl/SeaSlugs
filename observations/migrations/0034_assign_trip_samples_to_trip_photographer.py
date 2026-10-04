# Step 1 of 2 replacing the Photographer table with the Users table.
#
# The model is now: the photographer of an observation is always its creator (Sample.owner).
# A trip no longer has a photographer of its own. So that no credit changes, every
# observation of a trip that named a photographer is handed to that photographer's user
# account. The name is matched against existing users by Hebrew full name, English (Profile)
# full name or username; someone nobody matches gets a new INACTIVE user (no usable password,
# cannot log in). Nothing is deleted here -- the old columns and table go in the next
# migration. (Data and schema are split because PostgreSQL refuses to mix them in one
# transaction.)

import re

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import migrations


def _norm(value):
    return re.sub(r'\s+', ' ', (value or '').strip()).casefold()


class _Users:
    def __init__(self, apps):
        self.User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))
        self.Profile = apps.get_model('observations', 'Profile')
        self.users = list(self.User.objects.all())
        self.profiles = {p.user_id: p for p in self.Profile.objects.all()}
        self.keys = {}
        for user in self.users:
            self._index(user)

    def _index(self, user):
        profile = self.profiles.get(user.pk)
        names = [f'{user.first_name} {user.last_name}', user.username]
        if profile:
            names.append(f'{profile.first_name_en} {profile.last_name_en}')
        for name in names:
            key = _norm(name)
            if not key: continue
            # a key shared by two different users is ambiguous -- match neither
            self.keys[key] = user if self.keys.get(key, user) == user else None

    def find(self, *names):
        for name in names:
            user = self.keys.get(_norm(name))
            if user: return user
        # "שבי רוטמן" vs the account "בת-שבע (שבי) רוטמן": same last name and the typed first
        # name is contained in the account's first name. Only accepted when exactly one
        # account fits.
        for name in names:
            parts = _norm(name).split(' ')
            if len(parts) < 2: continue
            first, last = ' '.join(parts[:-1]), parts[-1]
            fits = [u for u in self.users if _norm(u.last_name) == last and first and first in _norm(u.first_name)]
            if len(fits) == 1: return fits[0]
        return None

    def create_guest(self, name_he, name_en=''):
        """An inactive account standing in for a photographer who never registered."""
        he = ' '.join((name_he or '').split()); en = ' '.join((name_en or '').split())
        source = en or he
        parts = he.rsplit(' ', 1) if he else []
        first_he, last_he = (parts[0], parts[1]) if len(parts) == 2 else (he, '')
        en_parts = en.rsplit(' ', 1) if en else []
        first_en, last_en = (en_parts[0], en_parts[1]) if len(en_parts) == 2 else (en, '')
        base = re.sub(r'[^\w.\-]+', '.', source.casefold()).strip('.') or 'photographer'
        username, n = base[:140], 1
        while self.User.objects.filter(username=username).exists():
            n += 1; username = f'{base[:130]}.{n}'
        user = self.User.objects.create(username=username, first_name=first_he[:150], last_name=last_he[:150],
                                        is_active=False, password=make_password(None))
        if first_en or last_en:
            self.Profile.objects.create(user=user, first_name_en=first_en, last_name_en=last_en)
            self.profiles[user.pk] = self.Profile.objects.get(user=user)
        self.users.append(user); self._index(user)
        return user


def trip_photographers_become_sample_owners(apps, schema_editor):
    DiveTrip = apps.get_model('observations', 'DiveTrip')
    Photographer = apps.get_model('observations', 'Photographer')
    Sample = apps.get_model('observations', 'Sample')
    users = _Users(apps)
    by_row = {}
    for trip in DiveTrip.objects.order_by('pk'):
        text = (trip.photographer or '').strip()
        user = users.find(text) if text else None
        if user is None and trip.photographer_fk_id:
            if trip.photographer_fk_id not in by_row:
                row = Photographer.objects.get(pk=trip.photographer_fk_id)
                by_row[row.pk] = users.find(row.name, row.name_en) or users.create_guest(row.name, row.name_en)
            user = by_row[trip.photographer_fk_id]
        if user is None and text:
            user = users.create_guest(text)
        if user is not None:
            Sample.objects.filter(trip_id=trip.pk).exclude(owner_id=user.pk).update(owner_id=user.pk)


def sample_owners_back_to_trip_photographers(apps, schema_editor):
    """Reverse (best effort): a trip whose observations all belong to one user gets that
    user back as its photographer (free text and lookup row). Earlier owners are not
    restored -- they were overwritten by the forward step."""
    DiveTrip = apps.get_model('observations', 'DiveTrip')
    Photographer = apps.get_model('observations', 'Photographer')
    Sample = apps.get_model('observations', 'Sample')
    Profile = apps.get_model('observations', 'Profile')
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))
    for trip in DiveTrip.objects.all():
        owner_ids = set(Sample.objects.filter(trip_id=trip.pk).values_list('owner_id', flat=True))
        if len(owner_ids) != 1: continue
        user = User.objects.get(pk=owner_ids.pop())
        profile = Profile.objects.filter(user=user).first()
        he = f'{user.first_name} {user.last_name}'.strip() or user.username
        en = f'{profile.first_name_en} {profile.last_name_en}'.strip() if profile else ''
        row = Photographer.objects.filter(name=he).first() or Photographer.objects.create(name=he, name_en=en)
        DiveTrip.objects.filter(pk=trip.pk).update(photographer=en or he, photographer_fk=row)


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0033_species_size_from_species_size_max_species_size_to'),
    ]

    operations = [
        migrations.RunPython(trip_photographers_become_sample_owners, sample_owners_back_to_trip_photographers),
    ]
