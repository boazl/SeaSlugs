"""Bounded ZIP transfer. Media files are immutable and never extracted by path."""
import hashlib
import io
import json
import re
import uuid
import zipfile
from pathlib import Path
from PIL import Image
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone

LIMIT = 100 * 1024 * 1024

def validate_image_name(name):
    if not isinstance(name,str) or not re.fullmatch(r'observations/transfer/[0-9a-f]{64}\.jpg',name):
        raise ValidationError('שם קובץ תמונה לא תקין.')

def export_bundle():
    from .table_transfer import export_table
    from .models import Sample
    doc=export_table('samples');output=io.BytesIO();written=set();total=0
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for row,obj in zip(doc['rows'],Sample.objects.filter(deleted_at__isnull=True).order_by('pk')):
            if not obj.image: continue
            with obj.image.open('rb') as source: data=source.read(LIMIT+1)
            if len(data)>LIMIT: raise ValidationError('תמונה גדולה מדי להעברה.')
            name='observations/transfer/'+hashlib.sha256(data).hexdigest()+'.jpg'
            row['image']=name
            if name not in written:
                total+=len(data)
                if total>LIMIT-5*1024*1024: raise ValidationError('התמונות גדולות מדי לחבילה אחת (100MB).')
                archive.writestr(name,data);written.add(name)
        archive.writestr('table.json',json.dumps(doc,ensure_ascii=False))
    if output.tell()>LIMIT: raise ValidationError('החבילה גדולה מ־100MB. יש לפצל את ההעברה לפני ייצוא.')
    return output.getvalue()

def read_bundle(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos=archive.infolist();names=[x.filename for x in infos]
            if len(names)!=len(set(names)) or len(names)>10001 or sum(x.file_size for x in infos)>LIMIT:
                raise ValidationError('חבילה כפולה או גדולה מדי.')
            if 'table.json' not in names or archive.getinfo('table.json').file_size>5*1024*1024: raise ValidationError('טבלת תצפיות חסרה או גדולה מדי.')
            doc=json.loads(archive.read('table.json'))
            if not isinstance(doc,dict) or doc.get('table')!='samples' or not isinstance(doc.get('rows'),list): raise ValidationError('נדרשת חבילת תצפיות.')
            images={}
            for name in names:
                if name=='table.json': continue
                validate_image_name(name);raw=archive.read(name)
                if hashlib.sha256(raw).hexdigest()!=Path(name).stem: raise ValidationError('בדיקת תקינות תמונה נכשלה.')
                with Image.open(io.BytesIO(raw)) as image:
                    if image.format!='JPEG' or image.width*image.height>25_000_000: raise ValidationError('תמונה לא נתמכת.')
                    image.verify()
                images[name]=raw
            needed={r.get('image') for r in doc['rows'] if isinstance(r,dict) and r.get('image')}
            if needed!=set(images): raise ValidationError('קובצי התמונות אינם תואמים לתצפיות.')
            doc['_media_names']=list(images)
            return doc,images
    except (zipfile.BadZipFile, KeyError, OSError, Image.DecompressionBombError) as exc:
        raise ValidationError('חבילת תמונות פגומה.') from exc

def stage(data):
    root=Path(settings.DATA_DIR)/'transfer-staging';root.mkdir(parents=True,exist_ok=True,mode=0o700)
    for old in root.glob('*.zip'):
        if timezone.now().timestamp()-old.stat().st_mtime>3600: old.unlink(missing_ok=True)
    name=uuid.uuid4().hex;path=root/(name+'.zip');path.write_bytes(data);path.chmod(0o600)
    return name,hashlib.sha256(data).hexdigest()

def staged(name,digest):
    if not re.fullmatch('[0-9a-f]{32}',name): raise ValidationError('אישור לא תקין.')
    path=Path(settings.DATA_DIR)/'transfer-staging'/(name+'.zip')
    try: data=path.read_bytes()
    except FileNotFoundError: raise ValidationError('החבילה פגה; העלו מחדש.')
    if hashlib.sha256(data).hexdigest()!=digest: raise ValidationError('החבילה השתנתה; העלו מחדש.')
    return path,*read_bundle(data)

def save_images(images):
    # Content-addressed files preserve old images for database-backup recovery.
    for name,data in images.items():
        if default_storage.exists(name):
            with default_storage.open(name,'rb') as existing:
                if hashlib.sha256(existing.read()).digest()!=hashlib.sha256(data).digest(): raise ValidationError('קובץ יעד אינו תקין.')
        else:
            saved=default_storage.save(name,ContentFile(data))
            if saved!=name: raise ValidationError('התנגשות בעת שמירת תמונה; נסו שוב.')
