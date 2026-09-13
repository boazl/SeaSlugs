"""Natural-key transfer of video samples; never transfers credentials or grants roles."""
from decimal import Decimal, InvalidOperation
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from .models import Sample, Species, Country, Region, Site, youtube_id


def sample_row(obj, fields):
    result = {}
    for field in fields:
        value = getattr(obj, field)
        if field == 'owner': value = value.get_username()
        elif field == 'species': value = value.scientific_name if value else None
        elif field == 'country': value = value.name if value else None
        elif field == 'region': value = {'name': value.name, 'country': value.country.name} if value else None
        elif field == 'site': value = {'name': value.name, 'region': value.region.name, 'country': value.region.country.name} if value else None
        elif field == 'depth': value = str(value) if value is not None else None
        result[field] = value
    return result


def sample_plan(document, fields):
    from .table_transfer import unique, related
    result = []; seen = set()
    for incoming in document['rows']:
        if not isinstance(incoming, dict) or set(incoming) != set(fields):
            raise ValidationError('שדות Samples אינם תואמים. יש לעדכן קוד בשתי הסביבות.')
        values = dict(incoming)
        for field in fields:
            if field not in ('year','month','day','depth','gallery_order','species','country','region','site','source_metadata') and not isinstance(values[field], str):
                raise ValidationError('ערך טקסט לא תקין: ' + field)
        if not isinstance(values['source_metadata'], dict): raise ValidationError('מידע מקור לא תקין.')
        video = youtube_id(values['video_url'])
        if video in seen: raise ValidationError('סרטון כפול בקובץ.')
        seen.add(video)
        candidates = [x for x in Sample.objects.all() if youtube_id(x.video_url) == video]
        if len(candidates) > 1: raise ValidationError('לסרטון יש כמה רשומות ביעד; יש לפתור את הכפילות.')
        obj = candidates[0] if candidates else None
        if obj and (obj.deleted_at or obj.image):
            raise ValidationError('רשומת היעד מחוקה או כוללת קובץ תמונה; נדרשת בדיקה ידנית: ' + str(obj))
        values['owner'] = unique(get_user_model(), username=values['owner'])
        if values['owner'] is None: raise ValidationError('משתמש חסר ביעד: ' + incoming['owner'] + '. יש ליצור אותו או להתאים שם משתמש לפני ההעברה.')
        for field in ('species','country','region','site'):
            value = values[field]
            if value is None: continue
            if field == 'species':
                if not isinstance(value, str): raise ValidationError('שם מין לא תקין.')
                values[field] = unique(Species, scientific_name=value)
            elif field == 'site':
                if not isinstance(value, dict) or set(value) != {'name','region','country'} or not all(isinstance(v,str) for v in value.values()): raise ValidationError('מפתח אתר לא תקין.')
                values[field] = unique(Site, name=value['name'], region__name=value['region'], region__country__name=value['country'])
            else: values[field] = related(field, value)
            if values[field] is None: raise ValidationError('חסר ערך בטבלת עזר: ' + field)
        for field in ('year','month','day','gallery_order'):
            if values[field] is not None and type(values[field]) is not int: raise ValidationError('נדרש מספר שלם: '+field)
        try: values['depth'] = Decimal(str(values['depth'])) if values['depth'] is not None else None
        except InvalidOperation: raise ValidationError('עומק לא תקין.')
        if values['status'] not in ('pending','published'): raise ValidationError('מצב פרסום לא תקין.')
        candidate = Sample(**values)
        if obj:
            candidate.pk = obj.pk; candidate._state.adding = False
            for field in ('created_at','approved_by_id','approved_at'):
                setattr(candidate,field,getattr(obj,field))
        try: candidate.full_clean()
        except ValidationError as exc:
            # Incomplete legacy drafts may transfer, but cannot become public.
            errors = dict(exc.message_dict)
            if candidate.status == 'pending':
                for field in ('species','country','region','year'):
                    if not getattr(candidate, field): errors.pop(field, None)
            if errors: raise ValidationError(errors)
        if candidate.status == 'published' and any(getattr(candidate,n+'_other') for n in ('species','country','region','site')):
            raise ValidationError('אין לפרסם רשומה עם ערכי אחר.')
        before = sample_row(obj, fields) if obj else {}
        after = sample_row(candidate, fields)
        changes = [{'field':str(Sample._meta.get_field(f).verbose_name),'before':before.get(f,''),'after':after[f]} for f in fields if before.get(f) != after[f]]
        result.append({'object':candidate,'label':candidate.title or str(candidate),'action':'new' if obj is None else 'update' if changes else 'same','changes':changes})
    return result
