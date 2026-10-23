"""The note "identification uncertain" on the Gulf of Aqaba Phyllidia ocellata page (filled by 0077) is about
that one observation, not the whole species+area page: it moves to the page's defining observation. Only
the note exactly as 0077 wrote it moves, and only onto an observation without a note of its own."""
from django.db import migrations

SLUG = 'phyllidia-ocellata-israel-red-sea-gulf-of-aqaba'
NOTE_HE = 'הזיהוי אינו ודאי: ייתכן שזהו מופע של Phyllidia undula, שתועד באותו אתר — ראו מאמר.'
NOTE_EN = 'Identification uncertain: this may be a form of Phyllidia undula, recorded at the same site — see article.'


def forwards(apps, schema_editor):
    SpeciesArea = apps.get_model('observations', 'SpeciesArea')
    area = SpeciesArea.objects.filter(slug=SLUG, note_he=NOTE_HE, note_en=NOTE_EN).select_related('defining_sample').first()
    sample = area.defining_sample if area else None
    if sample is None or sample.note_he or sample.note_en:
        return
    sample.note_he, sample.note_en = NOTE_HE, NOTE_EN
    sample.save(update_fields=['note_he', 'note_en'])
    area.note_he = area.note_en = ''
    area.save(update_fields=['note_he', 'note_en'])


def backwards(apps, schema_editor):
    SpeciesArea = apps.get_model('observations', 'SpeciesArea')
    area = SpeciesArea.objects.filter(slug=SLUG, note_he='', note_en='').select_related('defining_sample').first()
    sample = area.defining_sample if area else None
    if sample is not None and sample.note_he == NOTE_HE and sample.note_en == NOTE_EN:
        area.note_he, area.note_en = NOTE_HE, NOTE_EN
        area.save(update_fields=['note_he', 'note_en'])
        sample.note_he = sample.note_en = ''
        sample.save(update_fields=['note_he', 'note_en'])


class Migration(migrations.Migration):
    dependencies = [('observations', '0080_sample_note')]
    operations = [migrations.RunPython(forwards, backwards)]
