"""Small, cheap per-request context additions used by templates site-wide."""
from .maintenance import is_locked


def maintenance_status(request):
    # Exposed unconditionally (cheap: just a file-exists check); templates gate its
    # display behind `user.is_superuser` themselves, same as the other admin-only links.
    return {'site_locked': is_locked()}
