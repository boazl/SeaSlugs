"""Superuser-only, individual image transfer and deliberate storage cleanup."""
import base64
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
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone
from .models import Sample, SiteImage
from .forms import SampleForm

MANIFEST_FORMAT = 'seaslugs-image-manifest-v1'


SORT_OPTIONS={'file':'לפי שם קובץ','alpha':'לפי סדר אלפביתי (סוג ומין)','taxonomy':'לפי סדר טקסונומי'}


def _row_species(row):
    """The species this image is filed under, for sorting -- the first linked sample that
    has one (almost always all of a content-addressed image's samples agree on species;
    picking the first is enough to place the row sensibly). None for an orphaned image or
    one only linked to collection/"other" samples, which sort after every named species."""
    for sample in row['refs']:
        if sample.species_id: return sample.species
    return None


def _alpha_key(species):
    # Mirrors the public gallery's alphabetical sort (dist/app.js's speciesSortCompare):
    # genus, then specific epithet, then the full scientific name as a final tie-break.
    return ((species.genus or species.scientific_name).lower(), (species.species or '').lower(), species.scientific_name.lower())


def _taxonomy_key(species):
    # Mirrors the public gallery's default (taxonomic) order (config/views.py's catalog
    # queryset, and Species.Meta.ordering): phylogenetic_order first, blank ones last.
    return (0, species.phylogenetic_order, species.scientific_name.lower()) if species.phylogenetic_order else (1, '', species.scientific_name.lower())


def files(sort='file'):
    root=Path(settings.MEDIA_ROOT).resolve()
    if not root.exists(): return []
    linked={}
    for item in Sample.objects.exclude(image='').select_related('species','trip__region'):
        linked.setdefault(item.image.name,[]).append(item)
    site_images=set(SiteImage.objects.exclude(image='').values_list('image',flat=True))
    rows=[]
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root): continue
        if path.suffix.lower() not in ('.jpg','.jpeg','.png','.webp'): continue
        name=path.relative_to(root).as_posix();refs=linked.get(name,[])
        # redundant: this exact file is kept on disk for nothing -- either no sample ever
        # referenced it, or every sample that did has since been soft-deleted. A site image
        # (the homepage photo) is never redundant even with zero Sample refs, since it's
        # referenced from SiteImage, not Sample.
        redundant=name not in site_images and all(r.deleted_at for r in refs)
        rows.append({'name':name,'size':path.stat().st_size,'refs':refs,'token':signing.dumps(name,salt='image-file'),
                     'blocked':any(not r.video_url and not r.deleted_at for r in refs) or name in site_images,
                     'redundant':redundant})
    if sort in ('alpha','taxonomy'):
        key_fn=_alpha_key if sort=='alpha' else _taxonomy_key
        rows.sort(key=lambda row:(1,row['name']) if not (species:=_row_species(row)) else (0,key_fn(species)))
    return rows


def _active_image_names():
    return set(Sample.objects.exclude(image='').filter(deleted_at__isnull=True).values_list('image', flat=True).distinct())


def build_manifest():
    """A small JSON listing every active, image-bearing sample's own canonical filename
    (see Sample.canonical_image_name) -- not a hash of the file's bytes and not an opaque
    id. Once every image is stored under that scheme (trip code + kind-dependent identity,
    kept in sync between environments by table-transfer), the exact same filename names the
    exact same photo in both environments, so comparing the plain names is enough on its
    own -- and the names themselves are what the admin needs anyway, to know which file to
    go find."""
    return {'format': MANIFEST_FORMAT, 'exported_at': timezone.now().isoformat(), 'images': sorted(_active_image_names())}


def compare_manifest(manifest):
    """Diff this environment's own active, image-bearing samples' filenames against an
    uploaded manifest from the other environment. Returns which filenames need downloading
    from there (present there, absent here) and which need sending there (present here,
    absent there) -- informational; the admin decides what, if anything, to transfer."""
    if not isinstance(manifest, dict) or manifest.get('format') != MANIFEST_FORMAT or not isinstance(manifest.get('images'), list):
        raise ValidationError('קובץ השוואה לא תקין או גרסה לא נתמכת.')
    if not all(isinstance(name, str) for name in manifest['images']):
        raise ValidationError('קובץ השוואה לא תקין.')
    remote = set(manifest['images'])
    local = _active_image_names()
    return {'missing_here': sorted(remote - local), 'only_here': sorted(local - remote)}


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
    # The file's own stored name -- after the canonical-naming migration (trip code +
    # kind-dependent identity, see Sample.canonical_image_name) this is already the
    # meaningful, human-readable name shown throughout the admin (the image comparison's
    # own lists included), so a downloaded file can be matched back to it by eye instead of
    # carrying an opaque, unrelated identifier.
    filename=path.name
    source=path.open('rb')
    if request.GET.get('download')=='1' and item:
        from .sample_transfer import sample_row
        from .table_transfer import TABLES
        # A regular JPEG carries its observation metadata to match/create the target. EXIF's
        # ImageDescription tag (270) is ASCII-only -- Pillow silently replaces every
        # non-ASCII character with '?' on write, so a site/title/etc. containing Hebrew (or
        # any other non-ASCII text) would otherwise come back unrecoverably mangled on the
        # other end. Base64-encoding the UTF-8 JSON keeps the embedded string itself pure
        # ASCII, immune to that.
        row=sample_row(item,TABLES['samples'][1]);row['image']=''
        metadata=json.dumps(row,ensure_ascii=False)
        encoded=base64.b64encode(metadata.encode('utf-8')).decode('ascii')
        if len(encoded)>60000:
            source.close();raise Http404('נתוני התצפית גדולים מדי להעברה בתמונה.')
        with source, Image.open(path) as original:
            output=io.BytesIO();exif=Image.Exif();exif[270]='SeaSlugsB64:'+encoded
            ImageOps.exif_transpose(original).convert('RGB').save(output,'JPEG',quality=90,exif=exif)
        output.seek(0);source=output
    response=FileResponse(source,as_attachment=request.GET.get('download')=='1',filename=filename)
    response['Cache-Control']='private, no-store'
    return response


@staff_member_required
def manager(request):
    if not request.user.is_superuser: raise PermissionDenied
    sort=request.GET.get('sort') or 'file'
    if sort not in SORT_OPTIONS: sort='file'
    redirect_target='image-manager' if sort=='file' else f"{reverse('image-manager')}?sort={sort}"
    context={'local':not settings.PRODUCTION,'sort':sort,'sort_options':SORT_OPTIONS}
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
                        Sample.objects.filter(image=name).update(image='', image_hash='')
                messages.success(request,f'נמחקו {len(selected)} תמונות ללא גיבוי.')
                return redirect(redirect_target)
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
                        if not isinstance(metadata,str): raise ValueError()
                        if metadata.startswith('SeaSlugsB64:'):
                            row=json.loads(base64.b64decode(metadata[len('SeaSlugsB64:'):]).decode('utf-8'))
                        elif metadata.startswith('SeaSlugs:'):
                            # Older downloads, from before non-ASCII text (e.g. Hebrew site
                            # or trip names) was base64-encoded to survive EXIF's ASCII-only
                            # ImageDescription tag intact -- still readable here (and exact,
                            # for the all-ASCII case), but any non-ASCII text in one of these
                            # was already silently replaced with '?' at download time by
                            # Pillow itself; that loss can't be recovered from the file alone,
                            # only by re-downloading it now that the fix is in place.
                            row=json.loads(metadata[len('SeaSlugs:'):])
                        else: raise ValueError()
                        if not isinstance(row,dict): raise ValueError()
                    except (ValueError,OSError): raise ValidationError('בחרו תמונות שהורדו מכלי ניהול התמונות. קובץ ללא נתוני תצפית ניתן להעלות בעריכת התצפית.')
                    upload.seek(0)
                    form=SampleForm();form.cleaned_data={'image':upload};content=form.clean_image();raw=content.read()
                    name='observations/transfer/'+hashlib.sha256(raw).hexdigest()+'.jpg'
                    row['image']=name;doc['rows'].append(row);doc['_media_names'].append(name);images[name]=raw
                with transaction.atomic():
                    from .models import Species, SpeciesArea
                    Species.objects.filter(pk=-1).update(scientific_name='')
                    items=sample_plan(doc,TABLES['samples'][1])
                    old_names=[];used_in_batch=set();skip_reasons=[]
                    for row,result in zip(doc['rows'],items):
                        candidate=result['object']
                        if candidate is None:
                            # sample_plan() itself declined to resolve this one row (most
                            # often: its transfer_id matches a sample that exists here only
                            # as a soft-deleted record, with no live replacement -- see its
                            # own 'skipped' branches) rather than raising, precisely so the
                            # rest of a batch still transfers. Drop its not-yet-attached
                            # content-hash bytes (never written to disk otherwise) and
                            # report why, instead of treating a None object as a sample.
                            images.pop(row['image'],None);skip_reasons.append(result['reason']);continue
                        existing=Sample.objects.filter(pk=candidate.pk).first() if candidate.pk else None
                        final=existing or candidate
                        if existing:
                            # Image transfer preserves all existing observation fields.
                            if existing.image and request.POST.get('replace')!='yes': raise ValidationError('יש לאשר החלפת תמונות קיימות ביעד.')
                            old_names.append(existing.image.name)
                            existing.image=candidate.image
                        # Rename from the temporary content-hash name (needed above so
                        # sample_plan's own full_clean() could validate each row before any
                        # bytes were actually written to storage) to the canonical,
                        # meaningful name -- see Sample.canonical_image_name. used_in_batch
                        # keeps two new, not-yet-saved samples in this same upload from
                        # landing on the same name -- a plain database query can't see each
                        # other's pending name yet.
                        temp_name=final.image.name
                        canonical=final.canonical_image_name(extra_used_names=used_in_batch)
                        used_in_batch.add(Path(canonical).stem)
                        if canonical!=temp_name and temp_name in images:
                            images[canonical]=images.pop(temp_name)
                        final.image=canonical;result['object']=final
                    save_images(images)
                    transferred=[result for result in items if result['object'] is not None]
                    for result in transferred:
                        sample=result['object'];sample.save()
                        # Mirror Sample.save_reviewed()'s own side effect (also mirrored by
                        # table_transfer.apply() for a plain table transfer) -- a sample
                        # transferred here and already published must register itself in
                        # SpeciesArea exactly like one saved through the site normally
                        # would, otherwise it's stored correctly but never appears in the
                        # public gallery, which is driven by SpeciesArea, not Sample directly.
                        if (sample.status==Sample.Status.PUBLISHED and sample.kind==Sample.Kind.SPECIES
                                and sample.species_id and sample.trip_id
                                and sample.trip.country_id and sample.trip.resolved_sea_id):
                            SpeciesArea.objects.update_or_create(
                                species_id=sample.species_id,country_id=sample.trip.country_id,sea_id=sample.trip.resolved_sea_id,
                                undetermined_variant=sample.undetermined_variant,
                                defaults={'defining_sample':SpeciesArea.pick_defining_sample(
                                    sample.species_id,sample.trip.country_id,sample.trip.resolved_sea_id,sample.undetermined_variant)},
                            )
                for old in set(old_names)-set(images):
                    if old and not Sample.objects.filter(image=old).exists():
                        root=Path(settings.MEDIA_ROOT).resolve();old_path=root/old
                        if not old_path.is_symlink() and old_path.resolve().is_relative_to(root): old_path.unlink(missing_ok=True)
                success_message=f'הועברו {len(transferred)} תמונות. גרסאות קודמות שאינן בשימוש נמחקו ללא גיבוי.'
                if skip_reasons:
                    success_message+=f' {len(skip_reasons)} לא הועברו: '+' '.join(skip_reasons)
                messages.success(request,success_message)
                return redirect(redirect_target)
            elif action=='site_image':
                upload=request.FILES.get('site_image')
                if not upload: raise ValidationError('יש לבחור תמונה.')
                form=SampleForm();form.cleaned_data={'image':upload};content=form.clean_image()
                obj,created=SiteImage.objects.get_or_create(key='intro_photo')
                if not created and obj.image: obj.image.delete(save=False)
                obj.image.save(content.name,content,save=True)
                messages.success(request,'תמונת הבית עודכנה.')
                return redirect(redirect_target)
            elif action=='export_manifest':
                manifest=build_manifest()
                body=json.dumps(manifest,ensure_ascii=False,indent=2)
                env='local' if context['local'] else 'render'
                response=HttpResponse(body,content_type='application/json; charset=utf-8')
                response['Content-Disposition']=f'attachment; filename="seaslugs-images-{env}.json"'
                return response
            elif action=='compare_manifest':
                upload=request.FILES.get('manifest')
                if not upload: raise ValidationError('יש לבחור קובץ השוואה.')
                try: manifest=json.loads(upload.read())
                except (ValueError,UnicodeDecodeError): raise ValidationError('קובץ השוואה לא תקין.')
                context['comparison']=compare_manifest(manifest)
        except ValidationError as exc: context['error']='; '.join(exc.messages)
    context['images']=files(sort);context['total_bytes']=sum(r['size'] for r in context['images'])
    context['site_image']=SiteImage.objects.filter(key='intro_photo').exclude(image='').first()
    response=render(request,'observations/images.html',context);response['Cache-Control']='private, no-store';return response
