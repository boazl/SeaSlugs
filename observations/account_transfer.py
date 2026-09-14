"""Account transfer without passwords, sessions or database IDs."""
import copy
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from .models import Profile, Country, Region

User = get_user_model()
ACCOUNT_TABLES = {
    'groups': (Group, ['name', 'permissions']),
    'users': (User, ['username','first_name','last_name','email','is_active','is_staff','is_superuser','groups','user_permissions']),
    'profiles': (Profile, ['user','display_name','macro_diver','visible_to_members','bio','countries','regions']),
}

def permission_key(obj):
    return '.'.join((obj.content_type.app_label, obj.content_type.model, obj.codename))

def account_row(obj, fields):
    result = {}
    for field in fields:
        value = getattr(obj, field)
        if field in ('permissions','user_permissions'):
            value = sorted(permission_key(p) for p in value.select_related('content_type').all())
        elif field in ('groups','countries'): value = sorted(value.values_list('name', flat=True))
        elif field == 'regions': value = list(value.order_by('country__name','name').values('name','country__name'))
        elif field == 'user': value = value.username
        result[field] = value
    return result

def resolve_many(field, values):
    from .table_transfer import unique
    if not isinstance(values, list): raise ValidationError('נדרשת רשימה: ' + field)
    result = []
    for value in values:
        if field == 'regions':
            if not isinstance(value, dict) or set(value) != {'name','country__name'} or not all(isinstance(v,str) for v in value.values()): raise ValidationError('אזור לא תקין.')
            obj = unique(Region, **value)
        else:
            if not isinstance(value, str): raise ValidationError('ערך קשר לא תקין.')
            if field in ('permissions','user_permissions'):
                parts = value.split('.')
                if len(parts) != 3: raise ValidationError('מפתח הרשאה לא תקין.')
                obj = unique(Permission, content_type__app_label=parts[0], content_type__model=parts[1], codename=parts[2])
            else: obj = unique(Group if field == 'groups' else Country, name=value)
        if obj is None: raise ValidationError(f'ערך מקושר חסר ביעד ({field}: {value}). יש להעביר את טבלת העזר קודם.')
        if obj in result: raise ValidationError('קשר כפול בקובץ.')
        result.append(obj)
    return result

def account_plan(document):
    from .table_transfer import unique
    model, fields = ACCOUNT_TABLES[document['table']]
    result = []; seen = set()
    for incoming in document['rows']:
        if not isinstance(incoming, dict) or set(incoming) != set(fields): raise ValidationError('שדות החשבון אינם תואמים לגרסת הכלי.')
        values = {}; many = {}
        for field, value in incoming.items():
            if field in ('permissions','user_permissions','groups','countries','regions'):
                many[field] = resolve_many(field, value)
            elif field in ('is_active','is_staff','is_superuser','macro_diver','visible_to_members'):
                if type(value) is not bool: raise ValidationError('נדרש ערך כן/לא: ' + field)
                values[field] = value
            else:
                if not isinstance(value,str): raise ValidationError('נדרש טקסט: ' + field)
                values[field] = value
        key = 'username' if model is User else 'user' if model is Profile else 'name'
        identity = values[key]
        if identity in seen: raise ValidationError('רשומה כפולה בקובץ: ' + identity)
        seen.add(identity)
        if model is Profile:
            values['user'] = unique(User, username=identity)
            if values['user'] is None: raise ValidationError('יש להעביר תחילה את המשתמש: ' + identity)
        obj = unique(model, **{key:values[key]})
        candidate = copy.copy(obj) if obj else model()
        for field,value in values.items(): setattr(candidate,field,value)
        if model is User and obj is None: candidate.set_unusable_password()
        candidate.full_clean()
        before = account_row(obj, fields) if obj else {}
        after = dict(incoming)
        for field in many:
            if field == 'regions': after[field] = sorted(after[field], key=lambda x:(x['country__name'], x['name']))
            else: after[field] = sorted(after[field])
        changes = [{'field':str(model._meta.get_field(f).verbose_name),'before':before.get(f,''),'after':after[f]} for f in fields if before.get(f) != after[f]]
        result.append({'object':candidate,'many':many,'label':identity,'action':'new' if obj is None else 'update' if changes else 'same','changes':changes})
    return result
