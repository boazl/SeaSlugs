"""Table transfer of the taxonomy tables' page content (orders, families, genera): names, description,
identification and sources in Hebrew/English, plus a genus' identification caption and source.

Only the text of rows that already exist at the destination is updated: a row is matched by its
identity (below), never created -- rows carry links to other taxa that this transfer doesn't move --
and a row with no counterpart is reported as skipped. The files themselves (article PDFs, the
identification file) travel through the image manager, not here."""
from django.core.exceptions import ValidationError
from .models import TaxonOrder, TaxonFamily, TaxonGenus

PAGE_TEXTS = ['name_he', 'name_en', 'description_he', 'description_en', 'identification_he', 'identification_en', 'sources', 'link']

# table -> (model, identity fields, all transferred fields)
TAXON_TABLES = {
    'orders': (TaxonOrder, ['name', 'sub_order', 'taxonomic_order'], ['name', 'sub_order', 'taxonomic_order'] + PAGE_TEXTS),
    'families': (TaxonFamily, ['name', 'sub_family'], ['name', 'sub_family'] + PAGE_TEXTS),
    'genera': (TaxonGenus, ['name'], ['name'] + PAGE_TEXTS + ['identification_caption', 'identification_caption_en', 'identification_source']),
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
        before = {f: getattr(targets[0], f) for f in fields}
        candidate = model.objects.get(pk=targets[0].pk)
        for field, value in values.items():
            setattr(candidate, field, value)
        candidate.full_clean(exclude=[f.name for f in model._meta.fields if f.name not in fields])
        changes = [{'field': str(model._meta.get_field(f).verbose_name), 'before': before[f], 'after': values[f]}
                   for f in fields if before[f] != values[f]]
        result.append({'object': candidate, 'label': label, 'action': 'update' if changes else 'same', 'changes': changes})
    return result
