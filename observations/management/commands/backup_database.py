import sqlite3
from django.core.management.base import BaseCommand, CommandError
from observations.table_transfer import create_backup


class Command(BaseCommand):
    help = 'Create and verify an online SQLite backup in the current environment (database only).'

    def handle(self, *args, **options):
        backup = create_backup()
        with sqlite3.connect(backup) as connection:
            if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise CommandError('Backup integrity check failed.')
        self.stdout.write(str(backup))
