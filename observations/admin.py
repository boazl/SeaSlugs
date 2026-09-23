from django.contrib import admin, messages
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from django.urls import reverse
from .forms import SampleForm
from .models import Country, Sea, Region, Site, Species, Profile, Sample, DiveTrip, SiteImage, SpeciesArea, TaxonOrder, TaxonFamily, TaxonGenus, SampleKind

for model in [Country,Sea,Region,Site,Profile,SiteImage,SampleKind]: admin.site.register(model)

@admin.register(Species)
class SpeciesAdmin(admin.ModelAdmin):
    list_display = ['phylogenetic_order','scientific_name','genus','species','author','family','order']
    search_fields = ['scientific_name','genus','species','author','family','name_he']
    list_filter = ['order','family','genus']
    fieldsets = [
        ('זיהוי מדעי', {'fields':['phylogenetic_order','scientific_name','genus','species','author','formatted_author','reference_author','full_species_name_with_order']}),
        ('סיווג טקסונומי', {'fields':['order','superfamily','family','accepted_genus','accepted_species']}),
        ('שמות ותפוצה', {'fields':['name_he','name_en','common_name','transliteration','language','distribution']}),
    ]

@admin.register(TaxonOrder)
class TaxonOrderAdmin(admin.ModelAdmin):
    list_display = ['taxonomic_order', 'name', 'name_he', 'sub_order', 'defining_sample']
    search_fields = ['name', 'name_he', 'sub_order']


@admin.register(TaxonFamily)
class TaxonFamilyAdmin(admin.ModelAdmin):
    list_display = ['taxonomic_order', 'name', 'name_he', 'sub_family', 'order', 'defining_sample']
    list_filter = ['order']
    search_fields = ['name', 'name_he', 'sub_family']
    autocomplete_fields = ['order']


@admin.register(TaxonGenus)
class TaxonGenusAdmin(admin.ModelAdmin):
    list_display = ['taxonomic_order', 'name', 'name_he', 'family', 'defining_sample']
    list_filter = ['family__order']
    search_fields = ['name', 'name_he']
    autocomplete_fields = ['family']


@admin.register(DiveTrip)
class DiveTripAdmin(admin.ModelAdmin):
    list_display = ['code','title','year','month','country','region','photographer','species_count']
    list_filter = ['year','country','region','photographer']
    search_fields = ['code','title','region_name','reserve','photographer']
    readonly_fields = ['source_metadata']


@admin.register(SpeciesArea)
class SpeciesAreaAdmin(admin.ModelAdmin):
    list_display = ['species','country','sea','defining_sample']
    list_filter = ['country','sea']
    search_fields = ['species__scientific_name']
    autocomplete_fields = []
    actions = ['rebuild_all']
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'defining_sample' and getattr(self, '_obj', None):
            # Only samples that would actually qualify to show the species in the gallery --
            # published, not deleted, matching this row's species+country+sea.
            kwargs['queryset'] = Sample.objects.filter(kind='species', species_id=self._obj.species_id, status='published',
                trip__country_id=self._obj.country_id, trip__region__sea_id=self._obj.sea_id, deleted_at__isnull=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    def get_form(self, request, obj=None, **kwargs):
        self._obj = obj
        return super().get_form(request, obj, **kwargs)
    @admin.action(description='בנייה מחדש של כל הטבלה מהדגימות המפורסמות הקיימות (מתעלם מהבחירה; מוחק ובונה מחדש את כל הרשומות)')
    def rebuild_all(self, request, queryset):
        from .table_transfer import create_backup
        backup = create_backup()
        count = SpeciesArea.rebuild()
        messages.success(request, f'הטבלה נבנתה מחדש: {count} רשומות. נוצר גיבוי: {backup.name}')


def reason_number_map():
    mapping = cache.get('sample_reason_number_map')
    if mapping is None:
        reasons = set()
        for obj in Sample.objects.all(): reasons.update(obj.publication_reasons())
        mapping = {text: i+1 for i, text in enumerate(sorted(reasons))}
        cache.set('sample_reason_number_map', mapping, 30)
    return mapping

class TripCodeListFilter(admin.SimpleListFilter):
    title = 'מסע צלילה'
    parameter_name = 'trip'
    template = 'admin/dropdown_filter.html'
    def lookups(self, request, model_admin):
        return [(t.pk, str(t)) for t in DiveTrip.objects.order_by('code')]
    def queryset(self, request, queryset):
        return queryset.filter(trip_id=self.value()) if self.value() else queryset

class PublicationReasonListFilter(admin.SimpleListFilter):
    title = 'סיבת אי־פרסום'
    parameter_name = 'reason'
    template = 'admin/dropdown_filter.html'
    def lookups(self, request, model_admin):
        mapping = reason_number_map()
        return [(str(num), f'{num} — {text}') for text, num in sorted(mapping.items(), key=lambda kv: kv[1])]
    def queryset(self, request, queryset):
        value = self.value()
        if not value: return queryset
        by_number = {num: text for text, num in reason_number_map().items()}
        text = by_number.get(int(value))
        if not text: return queryset.none()
        return queryset.filter(pk__in=[obj.pk for obj in queryset if text in obj.publication_reasons()])

@admin.register(Sample)
class SampleAdmin(admin.ModelAdmin):
    form = SampleForm
    list_display=['id','title','kind','species','trip_code','owner','status','publication_warning','deleted_at']
    list_filter=['status','kind',TripCodeListFilter,PublicationReasonListFilter,'deleted_at']
    search_fields=['title','species__scientific_name','species_other','owner__username','source_id','trip__title']
    readonly_fields=['publication_warning','source_metadata','source_id','status','created_at','updated_at','deleted_at','deleted_by','approved_at','approved_by']
    actions=['approve','soft_remove','restore']
    def has_delete_permission(self,request,obj=None): return False
    @admin.display(description='מסע צלילה',ordering='trip__code')
    def trip_code(self,obj): return obj.trip.code if obj.trip_id else '—'
    @admin.display(description='סיבת אי־פרסום')
    def publication_warning(self,obj):
        if not obj or not obj.pk: return '—'
        reasons = obj.publication_reasons()
        if not reasons: return '—'
        mapping = reason_number_map()
        numbers = ', '.join(str(mapping.get(r, '?')) for r in reasons)
        tooltip = ' | '.join(reasons)
        return format_html('<span style="color:#ba2121;font-weight:600" title="{}">{}</span>', tooltip, numbers)
    def save_model(self,request,obj,form,change): obj.save_reviewed()
    @admin.action(description='אישור פרסום לאחר השלמת הנתונים',permissions=['change'])
    def approve(self,request,queryset):
        # A soft-deleted sample keeps whatever status it had when it was deleted (deletion
        # never touches that field), so it can still show "מפורסמת" here even though it's
        # excluded from the site -- easy to mistake for "already fine". Approving it is a
        # no-op on purpose (it should come back through "שחזור לבדיקה מחדש" first, which
        # re-validates it), but doing that silently just looks like the button didn't work.
        skipped = queryset.filter(deleted_at__isnull=False).count()
        for item in queryset.filter(deleted_at__isnull=True):
            try: item.save_reviewed(actor=request.user,approve=True)
            except ValidationError as exc: self.message_user(request,f'{item}: {exc}',messages.ERROR)
        if skipped:
            self.message_user(request,f'{skipped} תצפיות מחוקות דולגו ונשארו מחוקות — יש לשחזר אותן קודם ("שחזור לבדיקה מחדש").',messages.WARNING)
    @admin.action(description='סימון כמחוקה',permissions=['change'])
    def soft_remove(self,request,queryset):
        for item in queryset: item.soft_delete(request.user)
    @admin.action(description='שחזור לבדיקה מחדש',permissions=['change'])
    def restore(self,request,queryset):
        for item in queryset:
            item.deleted_at=None;item.deleted_by=None
            item.save_reviewed()
