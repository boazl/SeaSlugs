"""Superuser-only, individual image transfer and deliberate storage cleanup."""
import hashlib
import io
import json
from PIL import Image, ImageOps
from django.core.files.base import ContentFile
import re
from pathlib import Path
from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import render, redirect
from .models import Sample, SiteImage
from .forms import SampleForm


def files():
    root=Path(settings.MEDIA_ROOT).resolve()
    if not root.exists(): return []
    linked={}
    for item in Sample.objects.exclude(image='').select_related('species'):
        linked.setdefault(item.image.name,[]).append(item)
    site_images=set(SiteImage.objects.exclude(image='').values_list('image',flat=True))
    rows=[]
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root): continue
        if path.suffix.lower() not in ('.jpg','.jpeg','.png','.webp'): continue
        name=path.relative_to(root).as_posix();refs=linked.get(name,[])
        rows.append({'name':name,'size':path.stat().st_size,'refs':refs,'token':signing.dumps(name,salt='image-file'),
                     'blocked':any(not r.video_url and not r.deleted_at for r in refs) or name in site_images})
    return rows


def resolve(token):
    try: name=signing.loads(token,salt='image-file')
    except signing.BadSignature: raise Http404
    root=Path(settings.MEDIA_ROOT).resolve();path=root/name
    if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file(): raise Http404
    return name,path


@staff_member_required
def image_file(request):
    if not request.user.is_superuser: raise PermissionDenied
    name,path=resolve(request.GET.get('file',''))
    item=Sample.objects.filter(image=name).first()
    filename=f'seaslugs-{item.transfer_id}.jpg' if item else path.name
    source=path.open('rb')
    if request.GET.get('download')=='1' and item:
        from .sample_transfer import sample_row
        from .table_transfer import TABLES
        # A regular JPEG carries its observation metadata to match/create the target.
        row=sample_row(item,TABLES['samples'][1]);row['image']=''
        metadata=json.dumps(row,ensure_ascii=False)
        if len(metadata.encode())>60000:
            source.close();raise Http404('נתוני התצפית גדולים מדי להעברה בתמונה.')
        with source, Image.open(path) as original:
            output=io.BytesIO();exif=Image.Exif();exif[270]='SeaSlugs:'+metadata
            ImageOps.exif_transpose(original).convert('RGB').save(output,'JPEG',quality=90,exif=exif)
        output.seek(0);source=output
    response=FileResponse(source,as_attachment=request.GET.get('download')=='1',filename=filename)
    response['Cache-Control']='private, no-store'
    return response


@staff_member_required
def manager(request):
    if not request.user.is_superuser: raise PermissionDenied
    context={'local':not settings.PRODUCTION}
    if request.method=='POST':
        try:
            action=request.POST.get('action')
            if action=='delete':
                chosen=request.POST.getlist('selected')
                if not chosen: raise ValidationError('יש לסמן תמונות.')
                selected=[resolve(token) for token in set(chosen)]
                if request.POST.get('confirm')!='yes': raise ValidationError('יש לאשר מחיקה ללא גיבוי.')
                with transaction.atomic():
                    for name,path in selected:
                        if Sample.objects.filter(image=name,video_url='',deleted_at__isnull=True).exists():
                            raise ValidationError('לא ניתן למחוק תמונה שהיא המדיה היחידה בתצפית פעילה. הוסיפו סרטון או הסירו את התצפית תחילה.')
                        if SiteImage.objects.filter(image=name).exists():
                            raise ValidationError('לא ניתן למחוק את תמונת הבית מכאן. יש להחליף או להסיר אותה דרך "תמונת הבית" למטה.')
                    # No archive or retained copy: remove files only after checking all selections.
                    for name,path in selected:
                        path.unlink()
                        Sample.objects.filter(image=name).update(image='')
                messages.success(request,f'נמחקו {len(selected)} תמונות ללא גיבוי.')
                return redirect('image-manager')
            elif action=='upload':
                uploads=request.FILES.getlist('images')
                if not uploads or len(uploads)>50: raise ValidationError('בחרו בין תמונה אחת ל־50 תמונות.')
                if sum(upload.size for upload in uploads)>100*1024*1024: raise ValidationError('עד 100MB בהעלאה אחת.')
                from .sample_transfer import sample_plan
                from .table_transfer import TABLES
                from .media_transfer import save_images
                doc={'rows':[],'_media_names':[]};images={}
                for upload in uploads:
                    try:
                        with Image.open(upload) as original: metadata=original.getexif().get(270,'')
                        if not isinstance(metadata,str) or not metadata.startswith('SeaSlugs:'): raise ValueError()
                        row=json.loads(metadata[len('SeaSlugs:'):])
                        if not isinstance(row,dict): raise ValueError()
                    except (ValueError,OSError): raise ValidationError('בחרו תמונות שהורדו מכלי ניהול התמונות. קובץ ללא נתוני תצפית ניתן להעלות בעריכת התצפית.')
                    upload.seek(0)
                    form=SampleForm();form.cleaned_data={'image':upload};content=form.clean_image();raw=content.read()
                    name='observations/transfer/'+hashlib.sha256(raw).hexdigest()+'.jpg'
                    row['image']=name;doc['rows'].append(row);doc['_media_names'].append(name);images[name]=raw
                with transaction.atomic():
                    from .models import Species
                    Species.objects.filter(pk=-1).update(scientific_name='')
                    items=sample_plan(doc,TABLES['samples'][1])
                    old_names=[]
                    for result in items:
                        candidate=result['object']
                        existing=Sample.objects.filter(pk=candidate.pk).first() if candidate.pk else None
                        if existing:
                            # Image transfer preserves all existing observation fields.
                            if existing.image and request.POST.get('replace')!='yes': raise ValidationError('יש לאשר החלפת תמונות קיימות ביעד.')
                            old_names.append(existing.image.name)
                            existing.image=candidate.image;result['object']=existing
                    save_images(images)
                    for result in items: result['object'].save()
                for old in set(old_names)-set(images):
                    if old and not Sample.objects.filter(image=old).exists():
                        root=Path(settings.MEDIA_ROOT).resolve();old_path=root/old
                        if not old_path.is_symlink() and old_path.resolve().is_relative_to(root): old_path.unlink(missing_ok=True)
                messages.success(request,f'הועברו {len(items)} תמונות. גרסאות קודמות שאינן בשימוש נמחקו ללא גיבוי.')
                return redirect('image-manager')
            elif action=='site_image':
                upload=request.FILES.get('site_image')
                if not upload: raise ValidationError('יש לבחור תמונה.')
                form=SampleForm();form.cleaned_data={'image':upload};content=form.clean_image()
                obj,created=SiteImage.objects.get_or_create(key='intro_photo')
                if not created and obj.image: obj.image.delete(save=False)
                obj.image.save(content.name,content,save=True)
                messages.success(request,'תמונת הבית עודכנה.')
                return redirect('image-manager')
        except ValidationError as exc: context['error']='; '.join(exc.messages)
    context['images']=files();context['total_bytes']=sum(r['size'] for r in context['images'])
    context['site_image']=SiteImage.objects.filter(key='intro_photo').exclude(image='').first()
    response=render(request,'observations/images.html',context);response['Cache-Control']='private, no-store';return response
