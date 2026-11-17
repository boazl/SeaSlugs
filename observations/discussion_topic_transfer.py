"""Table transfer of the "topics for discussion" table (table "discussions", DiscussionTopic): moves between the Mac and
the live site in either direction with /admin/table-transfer/.

- A row is matched by its `transfer_id`; it refers to nothing else, so it never waits for another table.
- A new row is created as it is (its dates included). An existing row is updated only when the file's copy was changed
  later (`updated_at`), so moving an older file never undoes a newer edit on the other side.
- Nothing is ever removed from the destination: a row deleted on one side is deleted on the other by hand.
"""
import uuid
from datetime import date, datetime

from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import DiscussionTopic

TOPIC_FIELDS = ['transfer_id', 'topic', 'rank', 'status', 'priority', 'opened_on', 'book_treatment', 'worms_treatment',
                'site_treatment', 'decision', 'sources', 'worms_link', 'notes', 'created_at', 'updated_at']
TEXT_FIELDS = ('topic', 'rank', 'status', 'book_treatment', 'worms_treatment', 'site_treatment', 'decision', 'sources',
               'worms_link', 'notes')
COMPARED = [f for f in TOPIC_FIELDS if f not in ('transfer_id', 'created_at', 'updated_at')]


def topic_row(obj, fields=TOPIC_FIELDS):
    values = {f: getattr(obj, f) for f in TEXT_FIELDS}
    values.update(transfer_id=str(obj.transfer_id), priority=obj.priority,
                  opened_on=obj.opened_on.isoformat() if obj.opened_on else None,
                  created_at=obj.created_at.isoformat() if obj.created_at else None,
                  updated_at=obj.updated_at.isoformat() if obj.updated_at else None)
    return {f: values[f] for f in fields}


def _moment(value, number, field):
    try:
        moment = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValidationError(f'זמן לא תקין בשורה {number} ({field}).')
    return moment if timezone.is_aware(moment) else timezone.make_aware(moment)


def topic_plan(document):
    result, seen = [], set()
    priorities = {value for value, _ in DiscussionTopic._meta.get_field('priority').choices}
    for number, incoming in enumerate(document['rows'], 1):
        if not isinstance(incoming, dict) or set(incoming) != set(TOPIC_FIELDS):
            raise ValidationError(f'שדות לא תואמים בשורה {number}; יש לעדכן את הקוד בשתי הסביבות.')
        for field in TEXT_FIELDS:
            if not isinstance(incoming[field], str):
                raise ValidationError(f'ערך לא תקין בשורה {number} ({field}).')
        if incoming['priority'] not in priorities or not isinstance(incoming['priority'], int):
            raise ValidationError(f'עדיפות לא תקינה בשורה {number}.')
        try:
            key = uuid.UUID(incoming['transfer_id'])
            opened_on = date.fromisoformat(incoming['opened_on'])
        except (TypeError, ValueError):
            raise ValidationError(f'מזהה או תאריך לא תקין בשורה {number}.')
        if key in seen:
            raise ValidationError('הקובץ מכיל רשומות כפולות לאותו יעד.')
        seen.add(key)
        values = {f: incoming[f] for f in TEXT_FIELDS}
        values.update(priority=incoming['priority'], opened_on=opened_on,
                      created_at=_moment(incoming['created_at'], number, 'created_at'),
                      updated_at=_moment(incoming['updated_at'], number, 'updated_at'))
        existing = DiscussionTopic.objects.filter(transfer_id=key).first()
        label = incoming['topic']
        if existing and values['updated_at'] <= existing.updated_at:
            result.append({'object': existing, 'label': label, 'action': 'same', 'changes': []})
            continue
        target = existing or DiscussionTopic(transfer_id=key)
        before = topic_row(existing) if existing else {}
        for f, v in values.items():
            setattr(target, f, v)
        target.full_clean(exclude=['transfer_id'])
        after = topic_row(target)
        changes = [{'field': str(DiscussionTopic._meta.get_field(f).verbose_name), 'before': before.get(f) or '',
                    'after': after[f] if after[f] is not None else ''} for f in COMPARED if before.get(f) != after[f]]
        if existing and not changes:
            result.append({'object': existing, 'label': label, 'action': 'same', 'changes': []})
            continue
        result.append({'object': target, 'label': label, 'action': 'update' if existing else 'new', 'changes': changes})
    return result
