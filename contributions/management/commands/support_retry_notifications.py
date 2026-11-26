from django.core.management.base import BaseCommand

from contributions import notify


class Command(BaseCommand):
    help = 'Send the support e-mails still pending (a failed or skipped send).'

    def handle(self, *args, **options):
        sent = notify.retry_pending()
        if options['verbosity']:
            self.stdout.write(f'Sent {sent} pending support notification(s).')
