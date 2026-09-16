from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.db.models import Q
from django.http import Http404, FileResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.urls import reverse
from .models import Sample, Profile, Region, Site, DiveTrip, SiteImage, Species
from .forms import SignupForm, SampleForm, ProfileForm, DiveTripForm


def is_manager(user): return user.is_authenticated and user.is_staff and user.has_perm('observations.change_sample')


def trips(request):
    from django.db.models import Prefetch
    published = Sample.objects.filter(status='published', deleted_at__isnull=True, trip__isnull=False,
        trip__country__isnull=False, trip__region__isnull=False, trip__year__isnull=False,
        species_other='', site_other='').filter(Q(kind='collection', species__isnull=True) | Q(kind='species',species__isnull=False)).select_related('species','trip')
    rows = DiveTrip.objects.filter(samples__in=published).distinct().prefetch_related(Prefetch('samples',queryset=published,to_attr='public_samples'))
    return render(request, 'observations/trips.html', {'trips':rows})

@login_required
def listing(request):
    rows = Sample.objects.select_related('species','trip','trip__country','trip__region','site','owner')
    if is_manager(request.user): pass
    else:
        rows = rows.filter(deleted_at__isnull=True, owner=request.user)
    if request.GET.get('mine') and request.user.is_authenticated: rows=rows.filter(owner=request.user)
    return render(request,'observations/list.html',{'observations':rows,'manager':is_manager(request.user)})


def signup(request):
    form = SignupForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user=form.save()
        user.groups.add(Group.objects.get_or_create(name='New user')[0])
        Profile.objects.create(user=user,display_name=user.get_full_name() or user.username)
        login(request,user)
        return redirect('profile')
    return render(request,'observations/form.html',{'form':form,'title':'הרשמה / Sign up'})


@login_required
def profile(request):
    item,_=Profile.objects.get_or_create(user=request.user,defaults={'display_name':request.user.username})
    form=ProfileForm(request.POST or None,instance=item)
    if request.method=='POST' and form.is_valid():
        item=form.save()
        group=Group.objects.get_or_create(name='Macro diver')[0]
        if item.macro_diver: request.user.groups.add(group)
        else: request.user.groups.remove(group)
        messages.success(request,'הפרופיל נשמר.')
        return redirect('profile')
    return render(request,'observations/form.html',{'form':form,'title':'הפרופיל שלי / My profile'})


@login_required
def partners(request):
    rows=Profile.objects.filter(macro_diver=True,visible_to_members=True).prefetch_related('regions','countries')
    if request.GET.get('region'): rows=rows.filter(regions__id=request.GET['region'])
    if request.GET.get('country'): rows=rows.filter(countries__id=request.GET['country'])
    from .models import Country
    return render(request,'observations/partners.html',{'profiles':rows.distinct(),'regions':Region.objects.all(),'countries':Country.objects.all()})


@login_required
def species_search(request):
    from django.http import JsonResponse
    q = (request.GET.get('q') or '').strip()
    if not q:
        return JsonResponse({'results': []})
    rows = Species.objects.filter(
        Q(scientific_name__icontains=q) | Q(name_he__icontains=q) | Q(name_en__icontains=q) | Q(genus__icontains=q)
    ).order_by('scientific_name')[:30]
    results = [{'id': str(item.pk), 'label': item.scientific_name + (f' — {item.name_he}' if item.name_he else '')} for item in rows]
    return JsonResponse({'results': results})


@login_required
def edit(request,pk=None):
    item=get_object_or_404(Sample,pk=pk,owner=request.user,deleted_at__isnull=True) if pk else Sample(owner=request.user)
    initial={}
    trip_param=request.GET.get('trip')
    if trip_param and request.method!='POST': initial['trip']=trip_param
    form=SampleForm(request.POST or None,request.FILES or None,instance=item,initial=initial)
    if request.method=='POST' and form.is_valid():
        item=form.save(commit=False)
        item.save_reviewed()
        messages.success(request,'התצפית פורסמה.' if item.status=='published' else 'התצפית נשמרה וממתינה להשלמת נתונים ולאישור מנהל.')
        return redirect('observations')
    return render(request,'observations/form.html',{'form':form,'title':'תצפית / Sample','observation_form':True,
        'trip_new_url':reverse('trip-new'),
        'locations':{'trips':list(DiveTrip.objects.values('id','region_id')),'sites':list(Site.objects.values('id','region_id'))}})


@login_required
def trip_new(request):
    next_url=request.POST.get('next') or request.GET.get('next') or reverse('observation-new')
    form=DiveTripForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        trip=form.save()
        messages.success(request,'מסע הצלילה נוסף.')
        sep='&' if '?' in next_url else '?'
        return redirect(f'{next_url}{sep}trip={trip.pk}')
    return render(request,'observations/form.html',{'form':form,'title':'מסע צלילה חדש / New dive trip','trip_form':True,'next':next_url,
        'locations':{'regions':list(Region.objects.values('id','country_id'))}})


@login_required
@require_POST
def remove(request,pk):
    item=get_object_or_404(Sample,pk=pk,owner=request.user,deleted_at__isnull=True)
    item.soft_delete(request.user)
    messages.success(request,'התצפית הוסרה מהאתר. מנהל יכול לשחזר אותה.')
    return redirect('observations')


def site_image(request,key):
    item=get_object_or_404(SiteImage,key=key)
    if not item.image: raise Http404
    response=FileResponse(item.image.open('rb'),content_type='image/jpeg')
    response['Cache-Control']='public, max-age=600'
    return response


def photo(request,pk):
    item=get_object_or_404(Sample,pk=pk)
    if not (is_manager(request.user) or (not item.deleted_at and (item.status=='published' or item.owner_id==getattr(request.user,'id',None)))): raise Http404
    if not item.image: raise Http404
    response=FileResponse(item.image.open('rb'),content_type='image/jpeg')
    response['Cache-Control']='private, no-store'
    return response
