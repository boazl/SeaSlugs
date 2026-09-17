from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.db.models import Q
from django.http import Http404, FileResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.urls import reverse
from .models import Sample, Profile, Region, Site, DiveTrip, SiteImage, Species, Country
from .forms import SignupForm, SampleForm, ProfileForm, DiveTripForm


def is_manager(user): return user.is_authenticated and user.is_staff and user.has_perm('observations.change_sample')


def trips(request):
    from django.db.models import Prefetch
    published = Sample.objects.filter(status='published', deleted_at__isnull=True, trip__isnull=False,
        trip__country__isnull=False, trip__region__isnull=False, trip__year__isnull=False,
        species_other='', site_other='').filter(Q(kind='collection', species__isnull=True) | Q(kind='species',species__isnull=False)).select_related('species','trip')
    rows = DiveTrip.objects.filter(samples__in=published).distinct().prefetch_related(Prefetch('samples',queryset=published,to_attr='public_samples'))
    return render(request, 'observations/trips.html', {'trips':rows})

SORT_OPTIONS = {
    'newest': ('-created_at',),
    'oldest': ('created_at',),
    'trip_desc': ('-trip__year', '-trip__month', '-created_at'),
    'trip_asc': ('trip__year', 'trip__month', 'created_at'),
    'species': ('species__scientific_name', '-created_at'),
}


@login_required
def listing(request):
    from django.contrib.auth import get_user_model

    def as_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    manager = is_manager(request.user)
    visible = Sample.objects.all() if manager else Sample.objects.filter(deleted_at__isnull=True, owner=request.user)
    rows = visible.select_related('species', 'trip', 'trip__country', 'trip__region', 'site', 'owner')
    if request.GET.get('mine') and request.user.is_authenticated:
        rows = rows.filter(owner=request.user)
    get = request.GET
    if get.get('kind') in ('species', 'collection'):
        rows = rows.filter(kind=get['kind'])
    if get.get('status') in ('pending', 'published'):
        rows = rows.filter(status=get['status'])
    country_id = as_int(get.get('country'))
    if country_id is not None:
        rows = rows.filter(trip__country_id=country_id)
    region_id = as_int(get.get('region'))
    if region_id is not None:
        rows = rows.filter(trip__region_id=region_id)
    year = as_int(get.get('year'))
    if year is not None:
        rows = rows.filter(trip__year=year)
    # order/family/genus/photographer/owner are typed into free-text autocomplete fields
    # (some have hundreds of possible values, so a <select> isn't practical) -- icontains
    # keeps a partial or not-quite-exact typed value still useful as a search.
    if get.get('order'):
        rows = rows.filter(species__order__icontains=get['order'])
    if get.get('family'):
        rows = rows.filter(species__family__icontains=get['family'])
    if get.get('genus'):
        rows = rows.filter(species__genus__icontains=get['genus'])
    if get.get('photographer'):
        rows = rows.filter(trip__photographer__icontains=get['photographer'])
    if manager and get.get('owner'):
        rows = rows.filter(owner__username__icontains=get['owner'])
    sort = get.get('sort') if get.get('sort') in SORT_OPTIONS else 'newest'
    rows = rows.order_by(*SORT_OPTIONS[sort])

    def options(field, **extra):
        # .order_by() clears Sample's default Meta.ordering (-created_at) before the
        # values_list/distinct -- otherwise Django silently adds created_at to the
        # SELECT DISTINCT columns (needed to support the implicit ORDER BY), which
        # defeats distinct() and produces duplicate option values in the dropdowns.
        return sorted(v for v in visible.filter(**extra).exclude(**{field: ''}).order_by().values_list(field, flat=True).distinct() if v)

    present_kinds = set(visible.order_by().values_list('kind', flat=True).distinct())
    present_statuses = set(visible.order_by().values_list('status', flat=True).distinct())

    context = {
        'observations': rows,
        'manager': manager,
        'sort': sort,
        'filters': get,
        # A filter whose data holds only zero or one distinct value is never useful --
        # narrowing it can't change the result set -- so each list below is only rendered
        # by the template when it has more than one option (see list.html's length checks).
        'kind_choices': [(v, label) for v, label in Sample.Kind.choices if v in present_kinds],
        'status_choices': [(v, label) for v, label in Sample.Status.choices if v in present_statuses],
        'countries': Country.objects.filter(dive_trips__samples__in=visible).distinct().order_by('name'),
        'regions': Region.objects.filter(dive_trips__samples__in=visible).distinct().order_by('name'),
        'years': sorted((v for v in visible.exclude(trip__year__isnull=True).order_by().values_list('trip__year', flat=True).distinct() if v), reverse=True),
        'orders': options('species__order'),
        'families': options('species__family'),
        'genera': options('species__genus'),
        'photographers': options('trip__photographer'),
    }
    if manager:
        context['owners'] = list(get_user_model().objects.filter(observations__in=visible).distinct().order_by('username').values_list('username', flat=True))
    return render(request, 'observations/list.html', context)


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
    rows = Species.objects.all()
    if q:
        rows = rows.filter(
            Q(scientific_name__icontains=q) | Q(name_he__icontains=q) | Q(name_en__icontains=q) | Q(genus__icontains=q)
        )
    # An empty q still returns a page of species (rather than nothing) so the species
    # picker on the observation form behaves like an open dropdown you can browse by
    # clicking, not only a search box that stays empty until you type something.
    rows = rows.order_by('scientific_name')[:40]
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
        if 'image' in form.changed_data and item.image:
            # Store by content hash, exactly like the bulk folder importer and the
            # image manager, so the same photo always resolves to the same image
            # reference whether it was uploaded here or arrived through a transfer.
            import hashlib
            from .media_transfer import save_images
            raw=item.image.read();name='observations/transfer/'+hashlib.sha256(raw).hexdigest()+'.jpg'
            save_images({name:raw});item.image=name
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
