"""Automatic database backups (table_transfer.create_backup, made before every data change in the admin tools) are
pruned after each new one: all from the last 7 days are kept, and always at least the newest 5; backups saved by hand
under other names are never deleted. The releases page shows how many backups there are and their total size."""
import os
import tempfile
import time
from pathlib import Path

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from .table_transfer import create_backup, prune_backups, backups_summary


class BackupRetentionTests(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.now = time.time()

    def make(self, name, days_old):
        path = self.root / name; path.write_bytes(b'x' * 10)
        stamp = self.now - days_old * 86400; os.utime(path, (stamp, stamp)); return path

    def test_keeps_last_week_and_newest_five(self):
        old = [self.make(f'table-transfer-old{n}.sqlite3', 10 + n) for n in range(8)]
        manual = self.make('db-before-0086.sqlite3', 60)
        deleted = prune_backups(self.root, now=self.now)
        self.assertEqual(sorted(deleted), sorted(old[5:]))
        self.assertTrue(all(p.exists() for p in old[:5])); self.assertTrue(manual.exists())

    def test_recent_ones_all_kept(self):
        recent = [self.make(f'table-transfer-r{n}.sqlite3', n * 0.5) for n in range(9)]
        self.make('table-transfer-old.sqlite3', 30)
        prune_backups(self.root, now=self.now)
        self.assertTrue(all(p.exists() for p in recent))
        self.assertFalse((self.root / 'table-transfer-old.sqlite3').exists())

    def test_create_backup_prunes(self):
        with override_settings(BACKUPS_DIR=self.root):
            old = [self.make(f'table-transfer-old{n}.sqlite3', 20) for n in range(6)]
            backup = create_backup()
        self.assertTrue(backup.exists())
        self.assertEqual(sum(p.exists() for p in old), 4)            # the new one + 4 old = the newest 5

    def test_summary_and_releases_page(self):
        self.make('table-transfer-a.sqlite3', 1); self.make('db-before-x.sqlite3', 1)
        with override_settings(BACKUPS_DIR=self.root):
            self.assertEqual(backups_summary()['count'], 2); self.assertEqual(backups_summary()['automatic'], 1)
            self.client.force_login(User.objects.create_superuser('boss', password='pw'))
            self.assertContains(self.client.get('/admin/releases/'), '2 קבצים')
