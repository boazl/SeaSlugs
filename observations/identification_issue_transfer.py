"""Table transfer of the identification-issues table (table "identissues", IdentificationIssue): the manager's worklist
moves between the Mac and the live site in either direction with /admin/table-transfer/.

- A row is matched by its `transfer_id`; its observations by the Sample's transfer_id and its species by scientific
  name. A row whose observation or species has not reached the destination yet is skipped with a reason -- transfer the
  Samples / species first and import the file again.
- A new row is created as it is (its dates included). An existing row is updated only when the file's copy was changed
  later (`updated_at`), so moving an older file never undoes a newer edit on the other side.
- Nothing is ever removed from the destination: a row deleted on one side is deleted on the other by hand.
"""
import uuid
from datetime import date, datetime

from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import IdentificationIssue, Sample, Species

ISSUE_FIELDS = ['transfer_id', 'kind', 'status', 'priority', 'opened_on', 'fixed_on', 'observation', 'species',
                'second_observation', 'second_species', 'corrected_species', 'corrected_name', 'native_range',
                'research_link', 'reporter', 'notes', 'created_at', 'updated_at', 'recommendation', 'decision',
                'action_video', 'action_photo', 'action_observation', 'action_delete', 'action_catalog']
OBSERVATION_FIELDS = ('observation', 'second_observation')
SPECIES_FIELDS = ('species', 'second_species', 'corrected_species')
TEXT_FIELDS = ('kind', 'status', 'corrected_name', 'native_range', 'research_link', 'reporter', 'notes')
# the review and the work (added later): a row from an older file lacks them and the destination keeps its own
WORK_FIELDS = ('recommendation', 'decision', 'action_video', 'action_photo', 'action_observation', 'action_delete', 'action_catalog')
# the fields compared and shown in the preview (everything but the key and the bookkeeping times)
COMPARED = [f for f in ISSUE_FIELDS if f not in ('transfer_id', 'created_at', 'updated_at')]


def issue_row(obj, fields=ISSUE_FIELDS):
    values = {'transfer_id': str(obj.transfer_id), 'kind': obj.kind, 'status': obj.status, 'priority': obj.priority,
              'opened_on': obj.opened_on.isoformat() if obj.opened_on else None,
              'fixed_on': obj.fixed_on.isoformat() if obj.fixed_on else None,
              'corrected_name': obj.corrected_name, 'native_range': obj.native_range, 'research_link': obj.research_link,
              'reporter': obj.reporter, 'notes': obj.notes, **{f: getattr(obj, f) for f in WORK_FIELDS},
              'created_at': obj.created_at.isoformat() if obj.created_at else None,
              'updated_at': obj.updated_at.isoformat() if obj.updated_at else None}
    for f in OBSERVATION_FIELDS:
        sample = getattr(obj, f) if getattr(obj, f'{f}_id') else None
        values[f] = str(sample.transfer_id) if sample else None
    for f in SPECIES_FIELDS:
        species = getattr(obj, f) if getattr(obj, f'{f}_id') else None
        values[f] = species.scientific_name if species else None
    return {f: values[f] for f in fields}


def _moment(value, number, field):
    if not isinstance(value, str):
        raise ValidationError(f'זמן לא תקין בשורה {number} ({field}).')
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        raise ValidationError(f'זמן לא תקין בשורה {number} ({field}).')
    return moment if timezone.is_aware(moment) else timezone.make_aware(moment)


def _day(value, number, field, required):
    if value is None and not required:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValidationError(f'תאריך לא תקין בשורה {number} ({field}).')


def issue_plan(document):
    result, seen = [], set()
    for number, incoming in enumerate(document['rows'], 1):
        if not isinstance(incoming, dict) or not (set(ISSUE_FIELDS) - set(WORK_FIELDS) <= set(incoming) <= set(ISSUE_FIELDS)):
            raise ValidationError(f'שדות לא תואמים בשורה {number}; יש לעדכן את הקוד בשתי הסביבות.')
        for field in TEXT_FIELDS:
            if not isinstance(incoming[field], str):
                raise ValidationError(f'ערך לא תקין בשורה {number} ({field}).')
        for field in OBSERVATION_FIELDS + SPECIES_FIELDS:
            if incoming[field] is not None and not isinstance(incoming[field], str):
                raise ValidationError(f'ערך לא תקין בשורה {number} ({field}).')
        if not isinstance(incoming['priority'], int) or incoming['priority'] not in IdentificationIssue.Priority.values:
            raise ValidationError(f'עדיפות לא תקינה בשורה {number}.')
        try:
            key = uuid.UUID(incoming['transfer_id'])
            sample_keys = {f: uuid.UUID(incoming[f]) if incoming[f] else None for f in OBSERVATION_FIELDS}
        except (TypeError, ValueError):
            raise ValidationError(f'מזהה לא תקין בשורה {number}.')
        if key in seen:
            raise ValidationError('הקובץ מכיל רשומות כפולות לאותו יעד.')
        seen.add(key)
        label = f"{incoming['species'] or incoming['observation'] or ''} · {incoming['kind']} · {incoming['opened_on']}"
        refs, missing = {}, None
        for f, sample_key in sample_keys.items():
            refs[f] = Sample.objects.filter(transfer_id=sample_key).first() if sample_key else None
            if sample_key and refs[f] is None:
                missing = 'תצפית של הרשומה חסרה ביעד — יש להעביר קודם את Samples ולייבא שוב.'
        for f in SPECIES_FIELDS:
            refs[f] = Species.objects.filter(scientific_name=incoming[f]).first() if incoming[f] else None
            if incoming[f] and refs[f] is None:
                missing = missing or f'המין {incoming[f]} חסר ביעד — יש להעביר קודם את טבלת המינים ולייבא שוב.'
        if missing:
            result.append({'action': 'skipped', 'label': label, 'reason': missing})
            continue
        values = {f: incoming[f] for f in TEXT_FIELDS}
        for f in WORK_FIELDS:
            if f in incoming:
                if not isinstance(incoming[f], str):
                    raise ValidationError(f'ערך לא תקין בשורה {number} ({f}).')
                values[f] = incoming[f]
        values.update(refs, priority=incoming['priority'],
                      opened_on=_day(incoming['opened_on'], number, 'opened_on', True),
                      fixed_on=_day(incoming['fixed_on'], number, 'fixed_on', False),
                      created_at=_moment(incoming['created_at'], number, 'created_at'),
                      updated_at=_moment(incoming['updated_at'], number, 'updated_at'))
        existing = IdentificationIssue.objects.filter(transfer_id=key).first()
        target = existing or IdentificationIssue(transfer_id=key)
        before = issue_row(existing) if existing else {}
        if existing and values['updated_at'] <= existing.updated_at:
            result.append({'object': existing, 'label': label, 'action': 'same', 'changes': []})
            continue
        for f, v in values.items():
            setattr(target, f, v)
        target.full_clean(exclude=['transfer_id'])
        after = issue_row(target)
        changes = [{'field': str(IdentificationIssue._meta.get_field(f).verbose_name), 'before': before.get(f) or '',
                    'after': after[f] if after[f] is not None else ''} for f in COMPARED if before.get(f) != after[f]]
        if existing and not changes:
            result.append({'object': existing, 'label': label, 'action': 'same', 'changes': []})
            continue
        result.append({'object': target, 'label': label, 'action': 'update' if existing else 'new', 'changes': changes})
    return result
