"""Reviewed, additive reference-table transfer. Never uses source database PKs."""
import hashlib
import json
import sqlite3
import uuid
from pathlib import Path
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from .models import Country, Sea, Region, Site, Species, Sample, DiveTrip, youtube_id
from django.contrib.auth import get_user_model
from .account_transfer import ACCOUNT_TABLES, account_row, account_plan

TABLES = {'species': (Species, ['scientific_name','name_he','name_en','source_id','genus','species','author','order','family','superfamily','accepted_genus','accepted_species','common_name','transliteration','language','formatted_author','distribution','phylogenetic_order','full_species_name_with_order','reference_author']),
          'countries': (Country,['name','name_en']), 'seas': (Sea,['name','name_en']),
          'regions': (Region,['name','name_en','country','sea']), 'sites': (Site,['name','name_en','region']),
          'trips': (DiveTrip, ['code','title','source_sort','year','month','start_day','duration_days','country_name','region_name','reserve','sea_name','photographer','species_count','source_metadata']),
          'samples': (Sample, ['title','kind','trip','owner','species','country','region','site','species_other','country_other','region_other','site_other','year','month','day','depth','video_url','status','source_id','gallery_order','source_metadata','transfer_id','image'])}
TABLES.update(ACCOUNT_TABLES)


def reference(obj):
    if isinstance(obj, Region): return {'name':obj.name,'country':obj.country.name}
    return obj.name


def row(obj, fields):
    if any(isinstance(obj, model) for model, _ in ACCOUNT_TABLES.values()):
        return account_row(obj, fields)
    if isinstance(obj, Sample):
        from .sample_transfer import sample_row
        return sample_row(obj, fields)
    return {f:reference(getattr(obj,f)) if f in ('country','sea','region') else getattr(obj,f) for f in fields}


def export_table(table):
    if table not in TABLES: raise ValidationError('טבלה לא נתמכת.')
    model,fields=TABLES[table]
    return {'format':'seaslugs-reference-v1','table':table,'exported_at':timezone.now().isoformat(),
            'rows':[row(obj,fields) for obj in (model.objects.filter(deleted_at__isnull=True) if table == 'samples' else model.objects.all()).order_by('pk')]}


def fingerprint():
    # Includes dependencies so a changed country/region also invalidates a preview.
    value={name:[row(obj, fields) for obj in model.objects.order_by('pk')] for name,(model,fields) in TABLES.items()}
    value['sample_lifecycle']=list(Sample.objects.order_by('pk').values('id','deleted_at','image','updated_at'))
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()


def unique(model, **lookup):
    items=list(model.objects.filter(**lookup)[:2])
    if len(items)>1: raise ValidationError('התאמה כפולה בטבלת היעד; יש לפתור אותה לפני הייבוא.')
    return items[0] if items else None


def related(field,value):
    if field=='region':
        if not isinstance(value,dict) or set(value)!= {'name','country'} or not all(isinstance(v,str) for v in value.values()): raise ValidationError('מפתח אזור לא תקין.')
        obj=unique(Region,name=value['name'],country__name=value['country'])
    else:
        if not isinstance(value,str): raise ValidationError('מפתח קשר לא תקין.')
        obj=unique(Country if field=='country' else Sea,name=value)
    if obj is None: raise ValidationError(f'חסר ערך מקושר ({field}: {value}). יש להעביר קודם את טבלת העזר שלו.')
    return obj


def plan(document):
    if not isinstance(document,dict) or document.get('format')!='seaslugs-reference-v1' or document.get('table') not in TABLES or not isinstance(document.get('rows'),list): raise ValidationError('קובץ העברה לא תקין או גרסה לא נתמכת.')
    if len(document['rows'])>10000: raise ValidationError('עד 10,000 רשומות בהעברה.')
    if document['table'] in ACCOUNT_TABLES:
        return account_plan(document)
    if document['table'] == 'samples':
        from .sample_transfer import sample_plan
        return sample_plan(document, TABLES['samples'][1])
    model,fields=TABLES[document['table']]
    result=[]; seen=set(); targets=set()
    if model is Species and document['rows'] and all(isinstance(r,dict) and {'scientific_name','name_he','name_en','source_id'}<=set(r)<=set(fields) and set(r)==set(document['rows'][0]) for r in document['rows']):
        fields=[f for f in fields if f in document['rows'][0]]
    for number,incoming in enumerate(document['rows'],1):
        if not isinstance(incoming,dict) or set(incoming)!=set(fields): raise ValidationError(f'שדות לא תואמים בשורה {number}; יש לעדכן את הקוד בשתי הסביבות.')
        values={}
        for f,v in incoming.items():
            if f in ('country','sea','region'): values[f]=related(f,v)
            elif model is DiveTrip and f in ('year','month','start_day','duration_days','species_count'):
                if v is not None and type(v) is not int: raise ValidationError('נדרש מספר שלם: '+f)
                values[f] = v
            elif model is DiveTrip and f == 'source_metadata':
                if not isinstance(v,dict): raise ValidationError('מידע מקור לא תקין.')
                values[f] = v
            elif not isinstance(v,str): raise ValidationError(f'ערך לא תקין בשורה {number}.')
            else: values[f]=v.strip()
        if model is Species:
            source=unique(model,source_id=values['source_id']) if values['source_id'] else None
            named=unique(model,scientific_name=values['scientific_name'])
            if source and named and source.pk!=named.pk: raise ValidationError('מזהה המקור והשם המדעי מצביעים על מינים שונים.')
            obj=source or named
            if obj and obj.source_id and values['source_id']!=obj.source_id: raise ValidationError('מזהי מקור שונים עבור אותו מין; נדרשת התאמה ידנית.')
            identity=values['source_id'] or values['scientific_name']
        elif model is DiveTrip:
            obj=unique(model,code=values['code'])
            identity=values['code']
        else:
            lookup={'name':values['name']}
            if model is Region:lookup['country']=values['country']
            if model is Site:lookup['region']=values['region']
            obj=unique(model,**lookup)
            identity=json.dumps({k:str(v) for k,v in lookup.items()},sort_keys=True)
        if identity in seen or (obj and obj.pk in targets): raise ValidationError('הקובץ מכיל רשומות כפולות לאותו יעד.')
        seen.add(identity)
        if obj: targets.add(obj.pk)
        before=row(obj,fields) if obj else {}
        candidate=model(pk=obj.pk if obj else None,**values)
        if model is Species and obj:
            for field in TABLES['species'][1]:
                if field not in values: setattr(candidate,field,getattr(obj,field))
        if obj: candidate._state.adding = False
        candidate.full_clean()
        after=row(candidate,fields)
        changes=[{'field':str(model._meta.get_field(f).verbose_name),'before':before.get(f,''),'after':after[f]} for f in fields if before.get(f)!=after[f]]
        result.append({'object':candidate,'label':str(candidate),'action':'new' if obj is None else 'update' if changes else 'same','changes':changes})
    return result


def create_backup():
    # Backup the SQLite database, never overwrite either database file.
    root=Path(settings.DATA_DIR)/'backups';root.mkdir(parents=True,exist_ok=True)
    backup=root/f'table-transfer-{timezone.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}.sqlite3'
    with sqlite3.connect(str(settings.DATABASES['default']['NAME'])) as source, sqlite3.connect(backup) as target:source.backup(target)
    backup.chmod(0o600)
    return backup


def apply(document, expected, actor=None, images=None):
    backup = create_backup()
    with transaction.atomic():
        # A write statement obtains SQLite's reservation before re-reading preview state.
        Species.objects.filter(pk=-1).update(scientific_name=F('scientific_name'))
        if fingerprint()!=expected:raise ValidationError('הנתונים השתנו מאז התצוגה המקדימה. יש ליצור תצוגה חדשה.')
        items=plan(document)
        if images:
            from .media_transfer import save_images
            save_images(images)
        if document['table'] == 'users':
            for item in items:
                user = item['object']
                if actor and user.pk == actor.pk and not (user.is_active and user.is_staff and user.is_superuser):
                    raise ValidationError('לא ניתן להסיר את גישת המנהל שמבצע את ההעברה. יש לבצע שינוי זה דרך מנהל אחר.')
        for item in items:
            if item['action']!='same':
                item['object'].save()
                for field, values in item.get('many', {}).items():
                    getattr(item['object'],field).set(values)
    return items,backup.name
