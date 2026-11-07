"""Photographers: the users an observation can belong to.

An observation always belongs to a user (Sample.owner), its photographer. The photographers are the users in the
"Macro photographer" group -- not every member is one (some are divers only). Among them may be people without an
account of their own -- *guest photographers*: inactive users in the group (no password, cannot sign in), set up by a
manager (photographer_new) so that a manager can add their photos under their name. A guest can later become a
member simply by being made active.

Who joins the group: a member is added by a manager (the admin's user page), or by himself when he adds his first
observation (mark_photographer); migration 0093 added everyone who already had observations.

Managers choose the photographer on the observation form and the quick trip form from photographer_users().
"""
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils.text import slugify

PHOTOGRAPHER_GROUP = 'Macro photographer'


def photographer_users(also=()):
    """The photographer group's users, active or not; `also` adds given user ids (an edited observation's current
    owner, so opening an old observation never changes its photographer by itself)."""
    User = get_user_model()
    condition = Q(groups__name=PHOTOGRAPHER_GROUP)
    extra = [pk for pk in also if pk]
    if extra:
        condition |= Q(pk__in=extra)
    return User.objects.filter(condition).distinct().order_by('first_name', 'last_name', 'username')


def mark_photographer(user):
    """Whoever has an observation is a photographer: puts the user in the group (if not there yet)."""
    from django.contrib.auth.models import Group
    if user and user.pk and not user.groups.filter(name=PHOTOGRAPHER_GROUP).exists():
        user.groups.add(Group.objects.get_or_create(name=PHOTOGRAPHER_GROUP)[0])


def photographer_label(user):
    name = user.get_full_name() or user.username
    return name if user.is_active else f'{name} (צלם אורח)'


def guest_username(first_en, last_en):
    """A free username for a guest photographer, like the existing ones ("oren.kline")."""
    User = get_user_model()
    base = '.'.join(part for part in (slugify(first_en), slugify(last_en)) if part)[:140] or 'photographer'
    candidate, n = base, 2
    while User.objects.filter(username__iexact=candidate).exists():
        candidate, n = f'{base}-{n}', n + 1
    return candidate
