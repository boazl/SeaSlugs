"""Reviewed folder import. Excel and original images are never modified."""
import hashlib
import json
import re
import unicodedata
import uuid
from pathlib import Path
from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.shortcuts import render,redirect
from django.utils import timezone
from .forms import SampleForm
from .models import Sample, Species, DiveTrip, Country, Region
from .table_transfer import fingerprint,create_backup
from .media_transfer import save_images


def normalized(value):
    return ' '.join(unicodedata.normalize('NFC',value).split())


def filename_stem(filename):
    text=normalized(Path(filename).stem)
    # Strip only trailing export labels and bare years, not numbered sp. IDs
    # or parenthesized taxonomic qualifiers such as sp. 4 (2021).
    while True:
        cleaned=re.sub(r'(?:[ _-]+edit|[ _-]+(?:19|20)\d{2})$', '', text, flags=re.IGNORECASE).rstrip()
        if cleaned==text:break
        text=cleaned
    return re.sub(r'^[A-Za-z]*\d+[ ._-]+','',text)


def filename_species(filename):
    text=filename_stem(filename)
    match=re.match(r'^([A-Za-z]+\s+(?:cf\.\s+)?(?:spp?\.(?:\s+(?:\d{1,3}(?!\d)|[A-Z](?![A-Za-z])))?|[A-Za-z][a-z]+(?:-[a-z]+)*))',text)
    if not match:return ''
    name=match.group(1)
    if re.search(r'sp\.\s+\d+$',name):
        qualifier=re.match(r'^\s+(\(\d{4}\))',text[len(name):])
        if qualifier:name+=' '+qualifier.group(1)
    return name


def match_species(filename,species):
    stem=filename_stem(filename)
    matches=[]
    for item in species:
        aliases={normalized(item.scientific_name),re.sub(r'\s+\([^)]*\)$','',normalized(item.scientific_name))}
        for alias in aliases:
            if not stem.casefold().startswith(alias.casefold()):continue
            tail=stem[len(alias):]
            if not tail or re.match(r'^(?:[-(]|\s+(?:\(|juv\.|\d{4}\b|[A-ZÀ-Ý]))',tail):
                # A prefix must not swallow another species qualifier or sp. identifier.
                rest=tail.strip()
                if rest.startswith(('cf.','sp.')) or re.match(r'^\d{1,3}\b',rest):continue
                matches.append((len(alias),item.pk))
    if not matches:return None
    longest=max(x[0] for x in matches);ids={pk for size,pk in matches if size==longest}
    return ids.pop() if len(ids)==1 else None


def location(trip):
    pairs=set(trip.samples.filter(country__isnull=False,region__isnull=False,deleted_at__isnull=True).values_list('country_id','region_id'))
    if len(pairs)==1:return next(iter(pairs))
    from django.db.models import Q
    candidates=list(Region.objects.filter(Q(name__iexact=trip.region_name)|Q(name_en__iexact=trip.region_name)).filter(Q(country__name__iexact=trip.country_name)|Q(country__name_en__iexact=trip.country_name)))
    if len(candidates)==1:return candidates[0].country_id,candidates[0].pk
    raise ValidationError('לא ניתן לזהות מדינה ואזור יחידים למסע. יש להשלים את נתוני המסע או את שיוך התצפיות שלו.')


def plan_row(trip,species_id,owner):
    country,region=location(trip)
    matches=list(Sample.objects.filter(kind='species',species_id=species_id,region_id=region,deleted_at__isnull=True))
    same=[s for s in matches if s.trip_id==trip.pk]
    if len(same)>1:raise ValidationError('כמה תצפיות לאותו מין במסע; יש לפתור בניהול.')
    if same:return same[0],'update'
    if any(s.status=='published' for s in matches):raise ValidationError('המין כבר מפורסם באזור במסע אחר. לא ניצור פרסום כפול ולא נשנה את שיוך המסע שלו.')
    return Sample(owner=owner,species_id=species_id,trip=trip,country_id=country,region_id=region,year=trip.year,month=trip.month),'new'


@staff_member_required
def folder_import(request):
    if not request.user.is_superuser:raise PermissionDenied
    context={'trips':DiveTrip.objects.all(),'species':Species.objects.all(),'local':not settings.PRODUCTION}
    root=Path(settings.DATA_DIR)/'folder-import-staging'
    if request.method=='POST':
        try:
            if request.POST.get('action')=='preview':
                trip=DiveTrip.objects.get(pk=request.POST.get('trip'))
                if not trip.year:raise ValidationError('במסע חסרה שנה.')
                location(trip)
                entries=[];localpath=request.POST.get('folder','').strip()
                if localpath and request.FILES.getlist('images'):
                    raise ValidationError('נבחרו גם נתיב תיקייה וגם קבצים. בחרו מקור אחד: נקו את הנתיב כדי להשתמש בקבצים שנבחרו.')
                if localpath:
                    if settings.PRODUCTION:raise ValidationError('נתיב מקומי זמין רק במק. באתר השתמשו בבחירת תיקייה.')
                    directory=Path(localpath).expanduser()
                    if not directory.is_dir():raise ValidationError('התיקייה לא נמצאה.')
                    entries=[(p.name,p) for p in sorted(directory.iterdir()) if p.is_file() and not p.is_symlink() and p.suffix.lower() in ('.jpg','.jpeg','.png','.webp')]
                else:entries=[(f.name,f) for f in request.FILES.getlist('images') if Path(f.name).suffix.lower() in ('.jpg','.jpeg','.png','.webp')]
                if not entries or len(entries)>500:raise ValidationError('בחרו תיקייה עם 1–500 תמונות JPEG, PNG או WebP.')
                root.mkdir(parents=True,exist_ok=True,mode=0o700)
                # Expired staging is temporary working data, not image backups.
                import shutil
                for old in root.iterdir():
                    if old.is_dir() and not old.is_symlink() and timezone.now().timestamp()-old.stat().st_mtime>3600:shutil.rmtree(old)
                stage=root/uuid.uuid4().hex;stage.mkdir(mode=0o700);rows=[];species=list(Species.objects.all());total=0
                try:
                    for number,(name,source) in enumerate(entries):
                        row={'index':number,'filename':name,'species_id':match_species(name,species),'error':'','proposed':filename_species(name)}
                        try:
                            size=source.stat().st_size if isinstance(source,Path) else source.size
                            if size>10*1024*1024:raise ValidationError('תמונה גדולה מ־10MB.')
                            raw=source.read_bytes() if isinstance(source,Path) else source.read()
                            upload=SimpleUploadedFile(name,raw,content_type='image/jpeg')
                            form=SampleForm();form.cleaned_data={'image':upload};content=form.clean_image();raw=content.read()
                            total+=len(raw)
                            if total>100*1024*1024:raise ValidationError('היבוא גדול מ־100MB לאחר הקטנה; פצלו לתיקיות.')
                            (stage/f'{number}.jpg').write_bytes(raw);row['digest']=hashlib.sha256(raw).hexdigest()
                            if row['species_id']:
                                item,row['action']=plan_row(trip,row['species_id'],request.user)
                                row['description']='החלפת תמונה קיימת' if item.image else 'הוספת תמונה לתצפית' if item.pk else 'יצירת תצפית עם תמונה'
                            else:row['description']='יצירת מין חדש ותצפית עם תמונה' if row['proposed'] else 'לא זוהה שם — בחרו מין קיים'
                        except ValidationError as exc:row['error']='; '.join(exc.messages)
                        rows.append(row)
                    picked=set()
                    for row in rows:
                        key=row['species_id'] or normalized(row['proposed']).casefold()
                        row['checked']=bool(key and not row['error'] and key not in picked)
                        if row['checked']:picked.add(key)
                        elif row['species_id'] and not row['error']:row['description']+=' — תמונה נוספת לאותו מין, לא נבחרה'
                    snapshot=fingerprint();manifest={'trip':trip.pk,'rows':rows,'snapshot':snapshot,'user':request.user.pk}
                    raw=json.dumps(manifest,ensure_ascii=False).encode();(stage/'manifest.json').write_bytes(raw)
                    token=signing.dumps({'stage':stage.name,'digest':hashlib.sha256(raw).hexdigest(),'user':request.user.pk},salt='folder-import')
                    context.update(rows=rows,token=token,chosen_trip=trip)
                except Exception:
                    shutil.rmtree(stage);raise
            elif request.POST.get('action')=='apply':
                if request.POST.get('confirm')!='yes':raise ValidationError('יש לאשר את התמונות והשינויים.')
                token=signing.loads(request.POST.get('token',''),salt='folder-import',max_age=1800)
                if token['user']!=request.user.pk:raise PermissionDenied
                if not re.fullmatch('[a-f0-9]{32}',token['stage']):raise ValidationError('אישור לא תקין.')
                stage=root/token['stage'];raw=(stage/'manifest.json').read_bytes()
                if hashlib.sha256(raw).hexdigest()!=token['digest']:raise ValidationError('ההכנה השתנתה; בצעו בדיקה מחדש.')
                manifest=json.loads(raw);trip=DiveTrip.objects.get(pk=manifest['trip'])
                selected=set(request.POST.getlist('selected'));prepared=[];seen=set();skipped=0
                for row in manifest['rows']:
                    if str(row['index']) not in selected:continue
                    if row['error']:raise ValidationError(row['error'])
                    choice=request.POST.get('species_'+str(row['index']))
                    proposal=None
                    if choice=='new':
                        proposed=normalized(request.POST.get('new_name_'+str(row['index']),''))
                        if not proposed or len(proposed)>200 or filename_species(proposed+'.jpg')!=proposed:
                            raise ValidationError('שם מין חדש לא תקין. יש להזין סוג ומין בלבד, עם sp. או cf. לפי הצורך.')
                        matches=[item for item in Species.objects.all() if normalized(item.scientific_name).casefold()==proposed.casefold()]
                        if len(matches)>1:raise ValidationError('שם המין מתאים לכמה רשומות קיימות.')
                        species=matches[0] if matches else None
                        if not species:
                            genus,epithet=proposed.split(' ',1)
                            prefix=re.match(r'^([A-Za-z]*\d+)[ ._-]',row['filename'])
                            proposal={'scientific_name':proposed,'genus':genus,'species':epithet,'phylogenetic_order':prefix.group(1) if prefix else ''}
                    else:species=Species.objects.get(pk=choice)
                    key=species.pk if species else proposed.casefold()
                    if key in seen:
                        skipped+=1
                        continue
                    seen.add(key)
                    image=(stage/f"{row['index']}.jpg").read_bytes()
                    if hashlib.sha256(image).hexdigest()!=row['digest']:raise ValidationError('התמונה השתנתה; בצעו בדיקה מחדש.')
                    prepared.append((species.pk if species else None,proposal,image))
                if not prepared:raise ValidationError('לא סומנו תמונות.')
                create_backup();old_names=[];created_species=0
                with transaction.atomic():
                    Species.objects.filter(pk=-1).update(scientific_name='')
                    if fingerprint()!=manifest['snapshot']:raise ValidationError('הנתונים השתנו מאז הבדיקה. בחרו תיקייה ובדקו מחדש.')
                    for species_id,proposal,image in prepared:
                        if species_id is None:
                            species=Species(**proposal);species.full_clean();species.save();species_id=species.pk;created_species+=1
                        item,action=plan_row(trip,species_id,request.user);old_names.append(item.image.name)
                        name='observations/transfer/'+hashlib.sha256(image).hexdigest()+'.jpg'
                        item.image=name;item.full_clean(validate_constraints=False)
                        save_images({name:image})
                        if action=='new':item.save_reviewed(actor=request.user)
                        else:item.save(update_fields=['image','updated_at'])
                media=Path(settings.MEDIA_ROOT).resolve()
                for name in set(old_names):
                    if name and not Sample.objects.filter(image=name).exists():
                        path=media/name
                        if not path.is_symlink() and path.resolve().is_relative_to(media):path.unlink(missing_ok=True)
                import shutil
                shutil.rmtree(stage)
                messages.success(request,f'נוצרו {created_species} מינים חדשים. יובאו {len(prepared)} תמונות; דולגו {skipped} תמונות כפולות. נשמרה הראשונה שנבחרה לכל מין לפי סדר הרשימה. תמונות קודמות שאינן בשימוש נמחקו ללא גיבוי תמונה.')
                return redirect('image-manager')
        except (ValidationError,ValueError,DiveTrip.DoesNotExist,Species.DoesNotExist,signing.BadSignature,OSError) as exc:
            context['error']='; '.join(exc.messages) if isinstance(exc,ValidationError) else 'הנתונים או הקבצים אינם זמינים. יש לבחור תיקייה ולבדוק מחדש.'
    response=render(request,'observations/folder_import.html',context);response['Cache-Control']='private, no-store';return response
