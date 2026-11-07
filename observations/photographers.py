"""Photographers: the users an observation can belong to.

An observation always belongs to a user (Sample.owner), its photographer. Besides the site's members, a photographer
may be someone without an account of their own -- a *guest photographer*: an inactive user in the "Macro photographer"
group (no password, cannot sign in), set up by a manager (photographer_new) so that a manager can add that person's
photos under their name. A guest can later become a member simply by being made active.

Managers choose the photographer on the observation form and the quick trip form from photographer_users(): every
active user plus the inactive ones in the group.
"""
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils.text import slugify

PHOTOGRAPHER_GROUP = 'Macro photographer'


def photographer_users():
    User = get_user_model()
    return (User.objects.filter(Q(is_active=True) | Q(groups__name=PHOTOGRAPHER_GROUP)).distinct()
            .order_by('first_name', 'last_name', 'username'))


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
