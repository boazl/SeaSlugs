"""Superuser-only, individual image transfer and deliberate storage cleanup."""
import base64
import hashlib
import io
import json
from datetime import datetime, timezone as dt_timezone
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
from .models import Sample, SiteImage, TaxonGenus, TaxonFamily, TaxonOrder, SpeciesArea
from .forms import SampleForm

MANIFEST_FORMAT = 'seaslugs-image-manifest-v1'


SORT_OPTIONS={'alpha':'לפי סדר אלפביתי (סוג ומין)','kind':'לפי סוג התמונה','taxonomy':'לפי סדר טקסונומי','file':'לפי שם קובץ'}
# 'kind' groups the cards by what the image is for, in this order, each group alphabetical:
# genus identification files, then order, family, genus and species observations, then the
# rest (collections, uncatalogued "other" species, orphans).
KIND_GROUPS=('identification','order','suborder','superfamily','family','genus','species','other')
KIND_GROUP_LABELS=('קבצי זיהוי של סוגים','תמונות של סדרות','תמונות של תתי-סדרות','תמונות של על-משפחות','תמונות של משפחות','תמונות של סוגים','תמונות של מינים','אחר (תמונות שאינן מוצגות באף רמה)')
DEFAULT_SORT='alpha'
# one "העברת תמונות לסביבה זו" upload: up to 150 photos (a full genus set re-sent at once), 300MB
MAX_UPLOAD_FILES=150
MAX_UPLOAD_BYTES=300*1024*1024


def _row_species(row):
    """The species this image is filed under, for sorting -- the first linked sample that
    has one (almost always all of a content-addressed image's samples agree on species;
    picking the first is enough to place the row sensibly). None for an orphaned image or
    one only linked to collection/"other"/taxon-level samples."""
    for sample in row['refs']:
        if sample.species_id: return sample.species
    return None


def _row_taxon(row):
    """For a row with no species: the genus / family / order name it belongs to -- a genus,
    family or order observation's own taxon, or the genus whose identification file this
    is -- so it sorts alphabetically right next to that genus's species. None otherwise."""
    for sample in row['refs']:
        if sample.kind in (Sample.Kind.GENUS, Sample.Kind.FAMILY, Sample.Kind.ORDER) and sample.taxon_name:
            return sample.taxon_name
    return row['identification_for'][0].name if row['identification_for'] else None


def _alpha_key(species):
    # Mirrors the public gallery's alphabetical sort (dist/app.js's speciesSortCompare):
    # genus, then specific epithet, then the full scientific name as a final tie-break.
    return ((species.genus or species.scientific_name).lower(), (species.species or '').lower(), species.scientific_name.lower())


def _taxonomy_key(species):
    # Mirrors the public gallery's default (taxonomic) order (config/views.py's catalog
    # queryset, and Species.Meta.ordering): phylogenetic_order first, blank ones last.
    return (0, species.phylogenetic_order, species.scientific_name.lower()) if species.phylogenetic_order else (1, '', species.scientific_name.lower())


# Two files hold "the same photo" when their 96x54 grayscale thumbnails differ by at most
# DUPLICATE_MAX_MEAN grey levels per pixel on average; they are an exact copy (re-saved,
# re-exported or resized) when, in addition, 99.5% of pixels differ by at most
# DUPLICATE_EXACT_P995. Measured on the real media folder: exact copies score mean 0-0.03 /
# p99.5 0-2 (a resized re-encode ~1 / 10); the same photo with its caption replaced (e.g. a
# genus label instead of the species one) mean 0.2-1.3 / p99.5 13-90; a re-graded or
# different photo mean 5+.
DUPLICATE_MAX_MEAN=1.5
DUPLICATE_EXACT_P995=12
THUMB=(96,54)
_thumbnail_cache={}


def _thumbnail(path):
    """(average brightness, 12x7 preview, 96x54 grayscale bytes) of the image, cached per
    process by (path, size, mtime); None for a file Pillow can't read."""
    stat=path.stat();key=(str(path),stat.st_size,stat.st_mtime_ns)
    if key not in _thumbnail_cache:
        try:
            with Image.open(path) as image:
                image.draft('L',(THUMB[0]*3,THUMB[1]*3))
                gray=image.convert('L').resize(THUMB,Image.Resampling.BOX)
            pixels=gray.tobytes();tiny=gray.resize((12,7),Image.Resampling.BOX).tobytes()
            _thumbnail_cache[key]=(sum(pixels)/len(pixels),tiny,pixels)
        except (OSError,ValueError,Image.DecompressionBombError):
            _thumbnail_cache[key]=None
    return _thumbnail_cache[key]


def _compare(a,b):
    """'exact', 'caption' (same photo, different caption/markings) or None."""
    if sum(abs(x-y) for x,y in zip(a[1],b[1]))/len(a[1])>DUPLICATE_MAX_MEAN*4: return None
    diffs=[abs(x-y) for x,y in zip(a[2],b[2])]
    if sum(diffs)/len(diffs)>DUPLICATE_MAX_MEAN: return None
    return 'exact' if sorted(diffs)[int(len(diffs)*.995)]<=DUPLICATE_EXACT_P995 else 'caption'


def _mark_duplicates(rows,paths):
    """row['duplicates']: [(other file name, 'exact')] for every other file holding the very same
    image -- an exact copy (re-saved, re-exported or resized); the same photo with a different
    caption or marking is a different image and is not listed. Only images of similar overall brightness are compared in full."""
    for row in rows: row['duplicates']=[]
    thumbs=sorted(((t,row) for row,path in zip(rows,paths) if (t:=_thumbnail(path))),key=lambda item:item[0][0])
    for i,(thumb,row) in enumerate(thumbs):
        for other_thumb,other in thumbs[i+1:]:
            if other_thumb[0]-thumb[0]>DUPLICATE_MAX_MEAN: break
            # only identical content counts: the same photo with a different caption is a different image
            if _compare(thumb,other_thumb)=='exact':
                row['duplicates'].append((other['name'],'exact'));other['duplicates'].append((row['name'],'exact'))


def _search_text(row):
    """Everything a card can be found by in the page's search box: file name, the linked
    observations' names, years and regions, and the genus of an identification file."""
    parts=[row['name']]
    for sample in row['refs']:
        parts+=[str(sample.taxon_name or ''),sample.genus,sample.family,sample.order]
        if sample.species_id: parts+=[sample.species.genus,sample.species.scientific_name]
        if sample.trip_id:
            parts+=[sample.trip.title,str(sample.trip.year or '')]
            if sample.trip.region_id: parts.append(sample.trip.region.name)
    for genus in row['identification_for']: parts+=[genus.name,genus.name_he]
    return ' '.join(p for p in parts if p).lower()


LIBRARY_PREFIXES={'genera-':'genus','families-':'family','orders-':'order'}
LEVEL_KINDS=('order','suborder','superfamily','family','genus','species')


def taxon_levels():
    """{file name: [level, ...]} -- every taxon page ("level": an order / sub-order /
    superfamily, a family, a genus, a species in an area) that shows each image. A level shows
    the images of its own observations (an order-, family- or genus-kind observation of that
    taxon; for a species, its observations in that area) -- each one's alternate image or
    gallery image; only when none of them has one, the image of the level's defining sample.
    A level is {'kind', 'label', 'url'}."""
    observations={}
    for sample in Sample.objects.filter(deleted_at__isnull=True).exclude(image='').select_related('trip'):
        if sample.kind=='order' and sample.order: key=('order',sample.order)
        elif sample.kind=='family' and sample.family: key=('family',sample.family)
        elif sample.kind=='genus' and sample.genus: key=('genus',sample.genus)
        elif sample.kind=='species' and sample.species_id and sample.trip_id and sample.trip.country_id and sample.trip.sea_id:
            key=('species',sample.species_id,sample.trip.country_id,sample.trip.sea_id,sample.undetermined_variant)
        else: continue
        observations.setdefault(key,set()).add(sample.image.name)
    def own_or_defining(key,defining):
        if key in observations: return observations[key]
        if defining and not defining.deleted_at and defining.image: return {defining.image.name}
        return set()
    levels={}
    def add(names,level):
        for name in names: levels.setdefault(name,[]).append(level)
    for row in TaxonOrder.objects.select_related('defining_sample'):
        own=not row.sub_order and not row.superfamily
        add(own_or_defining(('order',row.name) if own else ('order-row',row.pk),row.defining_sample),
            {'kind':row.rank,'label':row.own_name,'url':reverse('order-page',args=[row.pk])})
    for row in TaxonFamily.objects.select_related('defining_sample'):
        add(own_or_defining(('family',row.name) if not row.sub_family else ('family-row',row.pk),row.defining_sample),
            {'kind':'family','label':f'{row.name} ({row.sub_family})' if row.sub_family else row.name,'url':reverse('family-page',args=[row.name])})
    for row in TaxonGenus.objects.select_related('defining_sample'):
        add(own_or_defining(('genus',row.name),row.defining_sample),{'kind':'genus','label':row.name,'url':reverse('genus-page',args=[row.name])})
    for area in SpeciesArea.objects.select_related('species','country','sea','defining_sample'):
        key=('species',area.species_id,area.country_id,area.sea_id,area.undetermined_variant)
        label=f'{area.species.scientific_name}{" "+area.undetermined_variant if area.undetermined_variant else ""} · {area.country.name}'
        add(own_or_defining(key,area.defining_sample),{'kind':'species','label':label,'url':reverse('species-page',args=[area.slug]) if area.slug else ''})
    return levels


def files(sort=DEFAULT_SORT):
    root=Path(settings.MEDIA_ROOT).resolve()
    if not root.exists(): return []
    linked={}
    for item in Sample.objects.exclude(image='').select_related('species','trip__region'):
        linked.setdefault(item.image.name,[]).append(item)
    site_images=set(SiteImage.objects.exclude(image='').values_list('image',flat=True))
    # A genus's identification file (the diagram / plate shown in "סימני זיהוי" on the genus
    # page) lives in the same media folder but is referenced from TaxonGenus, not Sample --
    # it is in use, never redundant, and must not be deleted from here.
    identification={}
    for genus in TaxonGenus.objects.exclude(identification_file=''):
        identification.setdefault(genus.identification_file.name,[]).append(genus)
    rows=[];paths=[];levels=taxon_levels()
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root): continue
        if path.suffix.lower() not in ('.jpg','.jpeg','.png','.webp'): continue
        name=path.relative_to(root).as_posix();refs=linked.get(name,[]);genera=identification.get(name,[])
        # redundant: this exact file is kept on disk for nothing -- either no sample ever
        # referenced it, or every sample that did has since been soft-deleted. A site image
        # (the homepage photo) or a genus identification file is never redundant even with
        # zero Sample refs, since it's referenced from SiteImage / TaxonGenus, not Sample.
        redundant=name not in site_images and not genera and all(r.deleted_at for r in refs)
        row={'name':name,'size':path.stat().st_size,'refs':refs,'token':signing.dumps(name,salt='image-file'),
             'identification_for':genera,
             'blocked':any(not r.video_url and not r.deleted_at for r in refs) or name in site_images or bool(genera),
             'redundant':redundant}
        row['levels']=levels.get(name,[]);row['level_count']=len(row['levels'])
        # naming rule: genera-*.jpg belongs to genus observations only, families-*.jpg to family
        # ones, orders-*.jpg to order ones (their library trips -- see TAXON_LIBRARY_TRIPS); any
        # other photo to species / collection observations
        prefix=next((p for p in LIBRARY_PREFIXES if Path(name).name.startswith(p)),'')
        row['library_prefix']=prefix
        expected=LIBRARY_PREFIXES.get(prefix)
        row['kind_mismatch']=[r for r in refs if not r.deleted_at and
                              (r.kind!=expected if expected else r.kind in LIBRARY_PREFIXES.values())]
        # a genus / family / order observation's own photo under a wrong name (e.g. notrip-x.jpg)
        # can be renamed right here to its level's name (genera- / families- / orders-)
        owners=[r for r in refs if not r.deleted_at and not r.gallery_source_id and r.kind in LIBRARY_PREFIXES.values()]
        row['rename_to']=owners[0].canonical_image_name() if row['kind_mismatch'] and len(owners)==1 else ''
        row['search']=_search_text(row)+' '+' '.join(l['label'].lower() for l in row['levels'])
        rows.append(row);paths.append(path)
    _mark_duplicates(rows,paths)
    if sort=='alpha':
        def alpha(row):
            if species:=_row_species(row): return (0,_alpha_key(species))
            if taxon:=_row_taxon(row): return (0,(taxon.lower(),'',taxon.lower()))
            return (1,(row['name'].lower(),))
        rows.sort(key=alpha)
    elif sort=='kind':
        # One card per level that shows the image (an image on two levels appears twice --
        # the badge on it counts its levels); identification files and images on no level
        # keep a single card in their own groups.
        cards=[]
        for row in rows:
            if row['identification_for']:
                cards.append(dict(row,level=None,group=0,sort_label=row['identification_for'][0].name.lower()))
            for level in row['levels']:
                cards.append(dict(row,level=level,group=1+LEVEL_KINDS.index(level['kind']),sort_label=level['label'].lower()))
            if not row['levels'] and not row['identification_for']:
                cards.append(dict(row,level=None,group=len(KIND_GROUPS)-1,sort_label='\uffff'))
        cards.sort(key=lambda c:(c['group'],c['sort_label'],c['name'].lower()))
        counts={}
        for card in cards:
            card['group_label']=KIND_GROUP_LABELS[card['group']];counts[card['group']]=counts.get(card['group'],0)+1
        for card in cards: card['group_count']=counts[card['group']]
        return cards
    elif sort=='taxonomy':
        rows.sort(key=lambda row:(1,row['name']) if not (species:=_row_species(row)) else (0,_taxonomy_key(species)))
    return rows


def _active_image_names():
    """Filenames of active, image-bearing samples whose file is actually in this
    environment's media folder. A table transfer copies a sample's image *name* without its
    file, so the other environment can hold a sample pointing at a photo it doesn't have --
    listing names alone made such a missing photo look "already synced" on both sides."""
    root=Path(settings.MEDIA_ROOT).resolve()
    names=set(Sample.objects.exclude(image='').filter(deleted_at__isnull=True).values_list('image', flat=True).distinct())
    return {name for name in names if (root/name).is_file() and (root/name).resolve().is_relative_to(root)}


def _image_assignments():
    """{transfer_id: image name} for every active sample, image-bearing or not -- which photo
    each observation shows. transfer_id is the same in both environments (table transfer
    keeps it), so this catches an observation that uses an image in one environment and has
    none, or a different one, in the other -- e.g. a family observation given an existing
    genus photo here, a change neither the file list (that photo exists in both) nor a table
    transfer (which carries a sample's fields, not its image) brings across."""
    root=Path(settings.MEDIA_ROOT).resolve();result={}
    for transfer_id,name in Sample.objects.filter(deleted_at__isnull=True).values_list('transfer_id','image'):
        result[str(transfer_id)]=name if name and (root/name).is_file() else ''
    return result


_content_hash_cache={}


def _file_details():
    """{file name: [sha256 of its bytes, modification time, size in bytes, picture]} for every active sample's image
    present here -- so the comparison also catches a file both environments have under the
    same name but with different content (e.g. a genus photo re-captioned in one of them)."""
    root=Path(settings.MEDIA_ROOT).resolve();result={}
    for name in _active_image_names():
        path=root/name;stat=path.stat();key=(name,stat.st_size,stat.st_mtime_ns)
        if key not in _content_hash_cache:
            _content_hash_cache[key]=hashlib.sha256(path.read_bytes()).hexdigest()
        thumb=_thumbnail(path)
        # picture: the 96x54 grayscale thumbnail (base64) -- the same photo saved again (every
        # download / transfer re-encodes the JPEG) has other bytes but the same picture
        result[name]=[_content_hash_cache[key],int(stat.st_mtime),stat.st_size,base64.b64encode(thumb[2]).decode('ascii') if thumb else '']
    return result


def build_manifest():
    """A small JSON listing every active, image-bearing sample's own canonical filename
    (see Sample.canonical_image_name) -- not a hash of the file's bytes and not an opaque
    id. Once every image is stored under that scheme (trip code + kind-dependent identity,
    kept in sync between environments by table-transfer), the exact same filename names the
    exact same photo in both environments, so comparing the plain names is enough on its
    own -- and the names themselves are what the admin needs anyway, to know which file to
    go find. 'assignments' adds which image each observation uses (see _image_assignments)."""
    return {'format': MANIFEST_FORMAT, 'exported_at': timezone.now().isoformat(), 'images': sorted(_active_image_names()),
            'assignments': _image_assignments(),'files': _file_details()}


ALIGN_SALT='image-manager-align-names'
_SAFE_IMAGE_NAME=re.compile(r'observations/[^/\\]+\.(?:jpe?g|png|webp)',re.IGNORECASE)


def _same_picture(path,remote):
    """Is the local file the very picture the other environment's file entry describes? Equal bytes, or
    the same 96x54 grayscale fingerprint (a download / upload re-encodes the JPEG)."""
    if remote and hashlib.sha256(path.read_bytes()).hexdigest()==remote[0]: return True
    thumb=_thumbnail(path)
    if not thumb or not remote or len(remote)<4 or not remote[3]: return False
    try: theirs=base64.b64decode(remote[3])
    except ValueError: return False
    if len(theirs)!=len(thumb[2]): return False
    diffs=sorted(abs(x-y) for x,y in zip(thumb[2],theirs))
    return sum(diffs)/len(diffs)<=DUPLICATE_MAX_MEAN and diffs[int(len(diffs)*.995)]<=DUPLICATE_EXACT_P995


def _rename_conflict(pairs,olds=None):
    """Why the renames {old: new} can't all be done here, or '' -- a new name may only be taken (by a
    file or by any sample, deleted ones included) when it is itself one of the names being renamed away
    (two observations whose names are swapped between the environments)."""
    root=Path(settings.MEDIA_ROOT).resolve();olds=set(pairs) if olds is None else olds
    if len(set(pairs.values()))!=len(pairs): return 'שני קבצים מקבלים אותו שם.'
    for old,new in pairs.items():
        if not (_SAFE_IMAGE_NAME.fullmatch(old) and _SAFE_IMAGE_NAME.fullmatch(new)): return 'שם קובץ לא תקין.'
        if not (root/old).is_file(): return f'הקובץ {old} לא נמצא.'
        if new in olds: continue
        if (root/new).exists() or Sample.objects.filter(image=new).exists(): return f'השם {new} כבר תפוס כאן.'
    return ''


def align_names(pairs):
    """Renames each local file old -> new (the name the same picture has in the other environment) and
    points every sample showing it -- its owner and the observations showing it as a gallery image -- at
    the new name. In two steps through temporary names, so swapped names work too."""
    problem=_rename_conflict(pairs)
    if problem: raise ValidationError(problem)
    root=Path(settings.MEDIA_ROOT).resolve();temp={}
    with transaction.atomic():
        for i,old in enumerate(sorted(pairs)):
            temp[old]=f'observations/align-tmp-{i}-{Path(old).name}'
            (root/old).replace(root/temp[old])
            Sample.objects.filter(image=old).update(image=temp[old])
        for old,new in pairs.items():
            (root/temp[old]).replace(root/new)
            Sample.objects.filter(image=temp[old]).update(image=new)
    return len(pairs)


def compare_manifest(manifest):
    """Diff this environment's own active, image-bearing samples' filenames against an
    uploaded manifest from the other environment. Returns which filenames need downloading
    from there (present there, absent here) and which need sending there (present here,
    absent there) -- informational; the admin decides what, if anything, to transfer --
    plus, when the other side's manifest has assignments (older exports don't), the
    observations present in both whose image differs."""
    if not isinstance(manifest, dict) or manifest.get('format') != MANIFEST_FORMAT or not isinstance(manifest.get('images'), list):
        raise ValidationError('קובץ השוואה לא תקין או גרסה לא נתמכת.')
    if not all(isinstance(name, str) for name in manifest['images']):
        raise ValidationError('קובץ השוואה לא תקין.')
    remote_assignments=manifest.get('assignments')
    if remote_assignments is not None and (not isinstance(remote_assignments,dict)
            or not all(isinstance(k,str) and isinstance(v,str) for k,v in remote_assignments.items())):
        raise ValidationError('קובץ השוואה לא תקין.')
    remote = set(manifest['images'])
    local = _active_image_names()
    remote_files=manifest.get('files')
    if remote_files is not None and (not isinstance(remote_files,dict) or not all(
            isinstance(k,str) and isinstance(v,list) and len(v) in (2,3,4) and isinstance(v[0],str) and all(isinstance(x,int) for x in v[1:3])
            and (len(v)<4 or isinstance(v[3],str)) for k,v in remote_files.items())):
        raise ValidationError('קובץ השוואה לא תקין.')
    result={'missing_here': sorted(remote - local), 'only_here': sorted(local - remote), 'assignments_checked': remote_assignments is not None, 'different_image': [],
            'contents_checked': remote_files is not None, 'different_content': []}
    if remote_files:
        result['encoding_only']=0
        for name,(digest,mtime,size,picture) in sorted(_file_details().items()):
            if name in remote_files and remote_files[name][0]!=digest:
                there=remote_files[name]
                if len(there)>3 and there[3] and picture:
                    # other bytes: is it another picture, or the same one saved again?
                    try: theirs=base64.b64decode(there[3])
                    except ValueError: theirs=b''
                    mine=base64.b64decode(picture)
                    if len(theirs)==len(mine):
                        diffs=sorted(abs(x-y) for x,y in zip(mine,theirs))
                        if sum(diffs)/len(diffs)<=DUPLICATE_MAX_MEAN and diffs[int(len(diffs)*.995)]<=DUPLICATE_EXACT_P995:
                            result['encoding_only']+=1; continue
                result['different_content'].append({'name':name,'newer':'here' if mtime>there[1] else 'there' if mtime<there[1] else '',
                    'size_here':size,'size_there':there[2] if len(there)>2 else None,
                    'mtime_here':datetime.fromtimestamp(mtime,tz=dt_timezone.utc),'mtime_there':datetime.fromtimestamp(there[1],tz=dt_timezone.utc)})
        result['different_content_names']=[row['name'] for row in result['different_content']]
    if remote_assignments:
        local_assignments=_image_assignments()
        differing=[tid for tid,name in local_assignments.items() if tid in remote_assignments and remote_assignments[tid]!=name]
        samples={str(s.transfer_id):s for s in Sample.objects.filter(transfer_id__in=differing).select_related('species','trip')}
        rows=[{'sample':samples[tid],'here':local_assignments[tid],'there':remote_assignments[tid]} for tid in differing if tid in samples]
        result['different_image']=sorted(rows,key=lambda r:str(r['sample'].taxon_name or '').lower())
        # the same picture under another file name in the two environments: offer to take the other's name
        root=Path(settings.MEDIA_ROOT).resolve();pairs={}
        for row in rows:
            here,there=row['here'],row['there']
            row['same_picture']=bool(here and there and remote_files and there in remote_files and (root/here).is_file()
                                     and _same_picture(root/here,remote_files[there]))
            if row['same_picture'] and pairs.get(here,there)==there: pairs[here]=there
            elif row['same_picture']: row['same_picture']=False; pairs.pop(here,None)
        if len(set(pairs.values()))!=len(pairs): pairs={}
        while True:     # drop the pairs that can't be done (until what's left can), keep the rest
            kept={o:n for o,n in pairs.items() if not _rename_conflict({o:n},set(pairs))}
            if kept==pairs: break
            pairs=kept
        for row in rows: row['renamable']=row['here'] in pairs
        result['align_pairs']=sorted(pairs.items())
        result['align_token']=signing.dumps(pairs,salt=ALIGN_SALT) if pairs else ''
    return result


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
    sort=request.GET.get('sort') or DEFAULT_SORT
    if sort not in SORT_OPTIONS: sort=DEFAULT_SORT
    redirect_target='image-manager' if sort==DEFAULT_SORT else f"{reverse('image-manager')}?sort={sort}"
    context={'local':not settings.PRODUCTION,'sort':sort,'sort_options':SORT_OPTIONS}
    if request.method=='POST':
        try:
            action='rename' if request.POST.get('rename_file') else request.POST.get('action')
            if action=='rename':
                name,path=resolve(request.POST['rename_file'])
                owners=[r for r in Sample.objects.filter(image=name,deleted_at__isnull=True,gallery_source__isnull=True)
                        if r.kind in LIBRARY_PREFIXES.values()]
                if len(owners)!=1: raise ValidationError('אפשר לשנות כאן רק שם של תמונה של תצפית אחת מסוג סוג, משפחה או סדרה.')
                new_name=owners[0].canonical_image_name()
                if new_name==name: raise ValidationError('לקובץ כבר יש את השם המתאים.')
                from .media_transfer import save_images
                with transaction.atomic():
                    save_images({new_name:path.read_bytes()})
                    # the owner and every observation showing it as a gallery image
                    Sample.objects.filter(image=name).update(image=new_name)
                path.unlink()
                messages.success(request,f'שם הקובץ שונה: {name} ← {new_name}')
                return redirect(redirect_target)
            if action=='delete':
                chosen=request.POST.getlist('selected')
                if not chosen: raise ValidationError('יש לסמן תמונות.')
                selected=[resolve(token) for token in set(chosen)]
                if request.POST.get('confirm')!='yes': raise ValidationError('יש לאשר מחיקה ללא גיבוי.')
                with transaction.atomic():
                    for name,path in selected:
                        if Sample.objects.filter(image=name,video_url='',deleted_at__isnull=True).exists():
                            raise ValidationError('לא ניתן למחוק תמונה שהיא המדיה היחידה בתצפית פעילה. הוסיפו סרטון או הסירו את התצפית תחילה.')
                        if TaxonGenus.objects.filter(identification_file=name).exists():
                            raise ValidationError('לא ניתן למחוק קובץ זיהוי של סוג מכאן. יש להחליף או להסיר אותו בעריכת הסוג.')
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
                if not uploads or len(uploads)>MAX_UPLOAD_FILES: raise ValidationError(f'בחרו בין תמונה אחת ל־{MAX_UPLOAD_FILES} תמונות.')
                if sum(upload.size for upload in uploads)>MAX_UPLOAD_BYTES: raise ValidationError(f'עד {MAX_UPLOAD_BYTES//(1024*1024)}MB בהעלאה אחת.')
                from .sample_transfer import sample_plan, _describe
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
                    items=sample_plan(doc,TABLES['samples'][1],restore_deleted=False)
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
                        if existing and existing.image and request.POST.get('replace')!='yes':
                            # Skip only this row instead of aborting the whole batch: one
                            # image whose target sample already has one (and so needs
                            # explicit replace confirmation) must not block every other
                            # image in the same upload -- including ones for brand-new
                            # samples with no existing image to protect at all.
                            images.pop(row['image'],None)
                            skip_reasons.append(f'התצפית ביעד ({_describe(existing)}) כבר כוללת תמונה. '
                                                 'יש לסמן את תיבת "לאשר החלפת תמונות קיימות" ולהעלות שוב כדי להחליף אותה.')
                            result['object']=None;continue
                        final=existing or candidate
                        if existing:
                            # Image transfer preserves all existing observation fields.
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
                                and sample.trip.country_id and sample.trip.sea_id):
                            SpeciesArea.objects.update_or_create(
                                species_id=sample.species_id,country_id=sample.trip.country_id,sea_id=sample.trip.sea_id,
                                undetermined_variant=sample.undetermined_variant,
                                defaults={'defining_sample':SpeciesArea.pick_defining_sample(
                                    sample.species_id,sample.trip.country_id,sample.trip.sea_id,sample.undetermined_variant)},
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
            elif action=='align_names':
                try: pairs=signing.loads(request.POST.get('pairs',''),salt=ALIGN_SALT,max_age=3600)
                except signing.BadSignature: raise ValidationError('יש להריץ שוב את ההשוואה.')
                if not isinstance(pairs,dict) or not pairs: raise ValidationError('אין קבצים לשינוי שם.')
                count=align_names(pairs)
                messages.success(request,f'שמות {count} קבצים שונו לשמות שבסביבה השנייה.')
                return redirect(redirect_target)
            elif action=='compare_manifest':
                upload=request.FILES.get('manifest')
                if not upload: raise ValidationError('יש לבחור קובץ השוואה.')
                try: manifest=json.loads(upload.read())
                except (ValueError,UnicodeDecodeError): raise ValidationError('קובץ השוואה לא תקין.')
                context['comparison']=compare_manifest(manifest)
        except ValidationError as exc: context['error']='; '.join(exc.messages)
    context['images']=files(sort)
    unique={r['name']:r['size'] for r in context['images']}
    context['file_count']=len(unique);context['total_bytes']=sum(unique.values())
    context['site_image']=SiteImage.objects.filter(key='intro_photo').exclude(image='').first()
    response=render(request,'observations/images.html',context);response['Cache-Control']='private, no-store';return response
