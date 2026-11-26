"""Every model of the contributions app reads and writes the separate support database (settings.DATABASES['support'],
<DATA_DIR>/support.sqlite3); nothing else goes there. The scientific database never holds financial data, so the
admin's full database replacement (/admin/db-replace/), table transfers and restores of db.sqlite3 cannot lose it."""

APP = 'contributions'
DB = 'support'


class SupportRouter:
    def db_for_read(self, model, **hints):
        return DB if model._meta.app_label == APP else None

    def db_for_write(self, model, **hints):
        return DB if model._meta.app_label == APP else None

    def allow_relation(self, obj1, obj2, **hints):
        if APP in (obj1._meta.app_label, obj2._meta.app_label):
            return obj1._meta.app_label == obj2._meta.app_label
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == APP:
            return db == DB
        if db == DB:
            return False
        return None
