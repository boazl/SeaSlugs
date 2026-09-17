"""Natural-key transfer of video samples; never transfers credentials or grants roles."""
from decimal import Decimal, InvalidOperation
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from .models import Sample, Species, Country, Region, Site, DiveTrip, youtube_id


def sample_row(obj, fields):
    result = {}
    for field in fields:
        if field == 'trip':
            result[field] = obj.trip.code if obj.trip_id else None
            continue
        value = getattr(obj, field)
        if field in ('transfer_id','image'): value = str(value)
        elif field == 'owner': value = value.get_username()
        elif field == 'species': value = value.scientific_name if value else None
        elif field == 'site': value = {'name': value.name, 'region': value.region.name, 'country': value.region.country.name} if value else None
        elif field == 'depth': value = str(value) if value is not None else None
        result[field] = value
    return result


def sample_plan(document, fields):
    from .table_transfer import unique
    result = []; seen = set(); targets = set()
    for incoming in document['rows']:
        if isinstance(incoming, dict) and set(incoming) == set(fields)-{'transfer_id','image'}:
            import uuid
            incoming = dict(incoming, transfer_id=str(uuid.uuid5(uuid.NAMESPACE_URL,incoming.get('video_url',''))), image='')
        if not isinstance(incoming, dict) or set(incoming) != set(fields):
            raise ValidationError('שדות Samples אינם תואמים. יש לעדכן קוד בשתי הסביבות.')
        values = dict(incoming)
        for field in fields:
            if field not in ('day','depth','gallery_order','species','site','trip','source_metadata') and not isinstance(values[field], str):
                raise ValidationError('ערך טקסט לא תקין: ' + field)
        if not isinstance(values['source_metadata'], dict): raise ValidationError('מידע מקור לא תקין.')
        if values['trip'] is not None:
            if not isinstance(values['trip'],str): raise ValidationError('קוד מסע לא תקין.')
            values['trip'] = unique(DiveTrip, code=values['trip'])
            if values['trip'] is None: raise ValidationError('מסע חסר ביעד. יש להעביר מסעות לפני Samples.')
        import uuid
        try: identity = str(uuid.UUID(values['transfer_id']))
        except (ValueError, TypeError): raise ValidationError('מזהה תצפית לא תקין.')
        if identity in seen: raise ValidationError('תצפית כפולה בקובץ.')
        seen.add(identity)
        obj = unique(Sample, transfer_id=identity)
        video = youtube_id(values['video_url']) if values['video_url'] else None
        candidates = [x for x in Sample.objects.exclude(video_url='') if video and youtube_id(x.video_url) == video]
        if len(candidates)>1: raise ValidationError('לסרטון כמה תצפיות ביעד. יש לפתור את הכפילות.')
        if obj and candidates and obj.pk != candidates[0].pk: raise ValidationError('מזהה התצפית והסרטון מצביעים על רשומות שונות.')
        obj = obj or (candidates[0] if candidates else None)
        if obj and obj.pk in targets: raise ValidationError('כמה רשומות מצביעות על אותו יעד.')
        if obj: targets.add(obj.pk)
        if obj and obj.deleted_at: raise ValidationError('תצפית היעד מחוקה; יש לבדוק אותה בניהול לפני העברה.')
        if obj: values['transfer_id'] = str(obj.transfer_id)
        if document.get('media_mode')=='separate':
            # Plain table transfers never copy, remove, or replace target image references --
            # actual image files travel separately, through image management.
            values['image'] = obj.image.name if obj and obj.image else ''
            if not values['video_url'] and not values['image']:
                result.append({'object':None,'label':values['title'] or incoming.get('species') or identity,
                               'action':'skipped','changes':[],
                               'reason':'התצפית לא הועברה: חסרה תמונה ביעד ואין סרטון. העבירו את התמונה דרך ניהול התמונות ואז ייבאו שוב.'})
                continue
        elif values['image']:
            # The image manager's own transfer flow (not plain table transfer): the doc's
            # rows carry a freshly content-hashed image name that will be written by this
            # same request, listed in _media_names.
            from .media_transfer import validate_image_name
            validate_image_name(values['image'])
            if values['image'] not in document.get('_media_names', []):
                from django.core.files.storage import default_storage
                if not default_storage.exists(values['image']): raise ValidationError('קובץ תמונה חסר; יש להעביר דרך ניהול התמונות.')
        values['owner'] = unique(get_user_model(), username=values['owner'])
        if values['owner'] is None: raise ValidationError('משתמש חסר ביעד: ' + incoming['owner'] + '. יש ליצור אותו או להתאים שם משתמש לפני ההעברה.')
        for field in ('species','site'):
            value = values[field]
            if value is None: continue
            if field == 'species':
                if not isinstance(value, str): raise ValidationError('שם מין לא תקין.')
                values[field] = unique(Species, scientific_name=value)
            else:
                if not isinstance(value, dict) or set(value) != {'name','region','country'} or not all(isinstance(v,str) for v in value.values()): raise ValidationError('מפתח אתר לא תקין.')
                values[field] = unique(Site, name=value['name'], region__name=value['region'], region__country__name=value['country'])
            if values[field] is None: raise ValidationError('חסר ערך בטבלת עזר: ' + field)
        for field in ('day','gallery_order'):
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
                for field in ('species','trip'):
                    errors.pop(field, None)
            if errors: raise ValidationError(errors)
        if candidate.status == 'published' and (candidate.species_other or candidate.site_other):
            raise ValidationError('אין לפרסם רשומה עם ערכי אחר.')
        before = sample_row(obj, fields) if obj else {}
        after = sample_row(candidate, fields)
        changes = [{'field':str(Sample._meta.get_field(f).verbose_name),'before':before.get(f,''),'after':after[f]} for f in fields if before.get(f) != after[f]]
        result.append({'object':candidate,'label':candidate.title or str(candidate),'action':'new' if obj is None else 'update' if changes else 'same','changes':changes})
    return result
