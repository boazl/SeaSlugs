from django.apps import AppConfig


class ContributionsConfig(AppConfig):
    """Voluntary financial support received through PayPal (IPN). Its tables live in their own SQLite file
    (DATABASES['support'], router.SupportRouter) so a full replacement of the scientific database never touches them."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'contributions'
    verbose_name = 'תמיכות כספיות'
