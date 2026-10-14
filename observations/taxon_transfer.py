"""Table transfer of the taxonomy tables' page content (orders -- with sub-orders and superfamilies --, families, genera): names, description,
identification and sources in Hebrew/English, plus a genus' identification caption and source.

Only the text of rows that already exist at the destination is updated: a row is matched by its
identity (below), never created -- rows carry links to other taxa that this transfer doesn't move --
and a row with no counterpart is reported as skipped. The files themselves (article PDFs, the
identification file) travel through the image manager, not here."""
from django.core.exceptions import ValidationError
from .models import TaxonOrder, TaxonFamily, TaxonGenus, Sample

PAGE_TEXTS = ['name_he', 'name_en', 'description_he', 'description_en', 'identification_he', 'identification_en', 'sources', 'link']
# The defining sample travels as the sample's fixed transfer id (never its numeric id), '' when
# the row has none. It is applied only when that sample exists at the destination; an empty value
# or a sample that has not arrived yet leaves the destination's own choice untouched.
DEFINING = 'defining_sample'

# table -> (model, identity fields, all transferred fields)
TAXON_TABLES = {
    'orders': (TaxonOrder, ['name', 'sub_order', 'superfamily', 'taxonomic_order'], ['name', 'sub_order', 'superfamily', 'taxonomic_order'] + PAGE_TEXTS + [DEFINING]),
    'families': (TaxonFamily, ['name', 'sub_family'], ['name', 'sub_family'] + PAGE_TEXTS + [DEFINING]),
    'genera': (TaxonGenus, ['name'], ['name'] + PAGE_TEXTS + ['identification_caption', 'identification_caption_en', 'identification_source', DEFINING]),
}


def taxon_plan(document):
    model, identity, fields = TAXON_TABLES[document['table']]
    result, seen = [], set()
    for number, incoming in enumerate(document['rows'], 1):
        if not isinstance(incoming, dict) or set(incoming) != set(fields):
            raise ValidationError(f'שדות לא תואמים בשורה {number}; יש לעדכן את הקוד בשתי הסביבות.')
        if not all(isinstance(v, str) for v in incoming.values()):
            raise ValidationError(f'ערך לא תקין בשורה {number}.')
        values = {f: v.replace('\r\n', '\n').strip() for f, v in incoming.items()}
        key = tuple(values[f] for f in identity)
        if key in seen:
            raise ValidationError('הקובץ מכיל רשומות כפולות לאותו יעד.')
        seen.add(key)
        label = ' / '.join(part for part in key if part)
        targets = list(model.objects.filter(**dict(zip(identity, key)))[:2])
        if len(targets) > 1:
            raise ValidationError('התאמה כפולה בטבלת היעד; יש לפתור אותה לפני הייבוא: ' + label)
        if not targets:
            result.append({'action': 'skipped', 'label': label, 'reason': 'אין שורה כזו ביעד — יש להוסיף אותה בניהול הטקסונומיה ואז לייבא שוב.'})
            continue
        from .sample_transfer import _describe
        current = targets[0].defining_sample
        before = {f: getattr(targets[0], f) for f in fields if f != DEFINING}
        before[DEFINING] = str(current.transfer_id) if current else ''
        candidate = model.objects.get(pk=targets[0].pk)
        for field, value in values.items():
            if field != DEFINING:
                setattr(candidate, field, value)
        shown = {}
        if values[DEFINING]:
            try:
                sample = Sample.objects.filter(transfer_id=values[DEFINING], deleted_at__isnull=True).first()
            except (ValidationError, ValueError):
                raise ValidationError(f'מזהה דגימה מגדירה לא תקין בשורה {number}.')
            if sample is None:
                label += ' (הדגימה המגדירה חסרה ביעד — לא שונתה; יש להעביר את Samples ולייבא שוב)'
                values[DEFINING] = before[DEFINING]
            else:
                from .defining import fits
                if not fits(candidate, sample):
                    # the sample is of the wrong level or taxon for this row here (see defining.py)
                    label += ' (הדגימה המגדירה אינה מתאימה לשורה זו ביעד — לא שונתה)'
                    values[DEFINING] = before[DEFINING]
                else:
                    candidate.defining_sample = sample
                    shown[DEFINING] = _describe(sample)
        else:
            values[DEFINING] = before[DEFINING]
        candidate.full_clean(exclude=[f.name for f in model._meta.fields if f.name not in fields])
        changes = []
        for f in fields:
            if before[f] == values[f]:
                continue
            old_text = _describe(current) if f == DEFINING and current else before[f]
            changes.append({'field': str(model._meta.get_field(f).verbose_name), 'before': old_text, 'after': shown.get(f, values[f])})
        result.append({'object': candidate, 'label': label, 'action': 'update' if changes else 'same', 'changes': changes})
    return result
