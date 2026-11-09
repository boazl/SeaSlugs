"""Table transfer of the observations forum (table "forum", ForumMessage): the conversations move between the Mac and
the live site in either direction with /admin/table-transfer/ (export on one side, preview and apply on the other).

- A message is matched by its `transfer_id`; its observation by the Sample's transfer_id, its writer (and whoever
  deleted it) by username. A message whose observation or writer has not reached the destination yet is skipped with
  a reason -- transfer the Samples / Users first and import the file again.
- The transfer only adds: a new message is created with its original time; an existing one is never rewritten (messages
  are not edited). A deletion travels: a message deleted at the source is marked deleted at the destination too, and a
  message deleted at the destination stays deleted (deletion wins), so transfers in both directions never revive one.
- Nothing is ever removed from the destination.
"""
import uuid
from datetime import datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import ForumMessage, Sample

FORUM_FIELDS = ['transfer_id', 'observation', 'user', 'created_at', 'manager_only', 'subject', 'text', 'deleted_at', 'deleted_by']


def _iso(value):
    return value.isoformat() if value else None


def forum_row(obj, fields=FORUM_FIELDS):
    values = {
        'transfer_id': str(obj.transfer_id),
        'observation': str(obj.observation.transfer_id) if obj.observation_id else None,
        'user': obj.user.username if obj.user_id else None,
        'created_at': _iso(obj.created_at),
        'manager_only': obj.manager_only,
        'subject': obj.subject,
        'text': obj.text,
        'deleted_at': _iso(obj.deleted_at),
        'deleted_by': obj.deleted_by.username if obj.deleted_by_id else None,
    }
    return {f: values[f] for f in fields}


def _time(value, number, field, required=True):
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise ValidationError(f'זמן לא תקין בשורה {number} ({field}).')
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        raise ValidationError(f'זמן לא תקין בשורה {number} ({field}).')
    return moment if timezone.is_aware(moment) else timezone.make_aware(moment)


def _label(values):
    when = timezone.localtime(values['created_at']).strftime('%d/%m/%Y %H:%M')
    return f"{values['user']} · {when} · {values['subject'] or values['text'][:50]}"


def forum_plan(document):
    users = get_user_model()
    result, seen = [], set()
    for number, incoming in enumerate(document['rows'], 1):
        if not isinstance(incoming, dict) or set(incoming) != set(FORUM_FIELDS):
            raise ValidationError(f'שדות לא תואמים בשורה {number}; יש לעדכן את הקוד בשתי הסביבות.')
        for field in ('transfer_id', 'observation', 'user', 'subject', 'text'):
            if not isinstance(incoming[field], str):
                raise ValidationError(f'ערך לא תקין בשורה {number} ({field}).')
        if not isinstance(incoming['manager_only'], bool):
            raise ValidationError(f'נדרש ערך בוליאני בשורה {number}: manager_only.')
        if incoming['deleted_by'] is not None and not isinstance(incoming['deleted_by'], str):
            raise ValidationError(f'ערך לא תקין בשורה {number} (deleted_by).')
        try:
            key = uuid.UUID(incoming['transfer_id'])
            observation_key = uuid.UUID(incoming['observation'])
        except ValueError:
            raise ValidationError(f'מזהה לא תקין בשורה {number}.')
        if key in seen:
            raise ValidationError('הקובץ מכיל רשומות כפולות לאותו יעד.')
        seen.add(key)
        values = {'user': incoming['user'], 'subject': incoming['subject'].strip(), 'text': incoming['text'].strip(),
                  'created_at': _time(incoming['created_at'], number, 'created_at'),
                  'deleted_at': _time(incoming['deleted_at'], number, 'deleted_at', required=False)}
        label = _label(values)
        observation = Sample.objects.filter(transfer_id=observation_key).first()
        if observation is None:
            result.append({'action': 'skipped', 'label': label,
                           'reason': 'התצפית של ההודעה חסרה ביעד — יש להעביר קודם את Samples ולייבא שוב.'})
            continue
        writer = users.objects.filter(username=incoming['user']).first()
        if writer is None:
            result.append({'action': 'skipped', 'label': label,
                           'reason': 'כותב ההודעה חסר ביעד — יש להעביר קודם את Users ולייבא שוב.'})
            continue
        deleter = users.objects.filter(username=incoming['deleted_by']).first() if incoming['deleted_by'] else None
        existing = ForumMessage.objects.filter(transfer_id=key).select_related('observation', 'user', 'deleted_by').first()
        if existing is None:
            candidate = ForumMessage(transfer_id=key, observation=observation, user=writer, created_at=values['created_at'],
                                     manager_only=incoming['manager_only'], subject=values['subject'], text=values['text'],
                                     deleted_at=values['deleted_at'], deleted_by=deleter if values['deleted_at'] else None)
            candidate.full_clean()
            after = forum_row(candidate)
            changes = [{'field': str(ForumMessage._meta.get_field(f).verbose_name), 'before': '', 'after': after[f]}
                       for f in ('observation', 'user', 'created_at', 'manager_only', 'subject', 'text', 'deleted_at') if after[f] not in (None, '', False)]
            result.append({'object': candidate, 'label': label, 'action': 'new', 'changes': changes})
        elif values['deleted_at'] and existing.deleted_at is None:
            existing.deleted_at = values['deleted_at']
            existing.deleted_by = deleter
            result.append({'object': existing, 'label': label, 'action': 'update',
                           'changes': [{'field': 'נמחקה', 'before': '', 'after': incoming['deleted_at']}]})
        else:
            result.append({'object': existing, 'label': label, 'action': 'same', 'changes': []})
    return result
