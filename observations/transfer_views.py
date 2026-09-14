import json
from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.shortcuts import render, redirect
from .table_transfer import TABLES,export_table,plan,fingerprint,apply

class UploadForm(forms.Form):
    file=forms.FileField(label='קובץ טבלה (JSON) או חבילת תצפיות ותמונות (ZIP)')

@staff_member_required
def transfer(request):
    # Reference transfer can modify several domain records; reserve it for superusers.
    if not request.user.is_superuser:raise PermissionDenied
    context={'tables':[(k,str(v[0]._meta.verbose_name_plural)) for k,v in TABLES.items()], 'form':UploadForm(), 'local':not settings.PRODUCTION}
    if request.method=='POST':
        try:
            action=request.POST.get('action')
            if action=='export_media':
                from .media_transfer import export_bundle
                response=HttpResponse(export_bundle(),content_type='application/zip')
                response['Content-Disposition']='attachment; filename="seaslugs-samples-images.zip"'
                response['Cache-Control']='no-store'
                return response
            if action=='export':
                doc=export_table(request.POST.get('table'))
                if doc['table']=='samples' and any(row.get('image') for row in doc['rows']):
                    raise ValidationError('התצפיות כוללות תמונות. השתמשו בכפתור הורדת תצפיות ותמונות (ZIP).')
                response=HttpResponse(json.dumps(doc,ensure_ascii=False,indent=2),content_type='application/json; charset=utf-8')
                response['Content-Disposition']=f'attachment; filename="seaslugs-{doc["table"]}.json"'
                response['Cache-Control']='no-store'
                return response
            if action=='preview':
                form=UploadForm(request.POST,request.FILES);context['form']=form
                if form.is_valid():
                    upload=form.cleaned_data['file']
                    from .media_transfer import LIMIT, read_bundle, stage
                    if upload.size>LIMIT:raise ValidationError('הקובץ גדול מ־100MB.')
                    raw=upload.read();bundle=None
                    if raw.startswith(b'PK'):
                        doc,images=read_bundle(raw)
                        bundle=stage(raw)
                    else:
                        if len(raw)>5*1024*1024:raise ValidationError('קובץ JSON גדול מ־5MB.')
                        doc=json.loads(raw.decode('utf-8'))
                        if isinstance(doc,dict): doc.pop('_media_names',None)
                    snapshot=fingerprint();items=plan(doc)
                    context.update(items=items,table_name=str(TABLES[doc['table']][0]._meta.verbose_name_plural),
                                   changed=sum(i['action']!='same' for i in items),unchanged=sum(i['action']=='same' for i in items),
                                   token=signing.dumps({'doc':None if bundle else doc,'bundle':bundle,'snapshot':snapshot,'user':request.user.pk},salt='table-transfer',compress=True))
            elif action=='apply':
                data=signing.loads(request.POST.get('token',''),salt='table-transfer',max_age=1800)
                if data['user']!=request.user.pk:raise PermissionDenied
                if request.POST.get('confirm')!='yes':raise ValidationError('יש לאשר את העדכון.')
                images={};path=None;doc=data['doc']
                if data.get('bundle'):
                    from .media_transfer import staged
                    path,doc,images=staged(*data['bundle'])
                items,backup=apply(doc,data['snapshot'],actor=request.user,images=images)
                if path: path.unlink(missing_ok=True)
                messages.success(request,f"הועברו {sum(i['action']!='same' for i in items)} רשומות חדשות או מעודכנות. נוצר גיבוי: {backup}")
                return redirect('table-transfer')
        except (ValidationError,ValueError,UnicodeError,signing.BadSignature) as exc:
            context['error']='; '.join(exc.messages) if isinstance(exc,ValidationError) else 'קובץ או אישור לא תקין/פג תוקף. העלו את הקובץ מחדש.'
    response=render(request,'observations/transfer.html',context)
    response['Cache-Control']='no-store'
    return response
