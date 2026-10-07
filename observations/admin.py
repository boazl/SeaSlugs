from django import forms
from django.contrib import admin, messages
from django.utils.html import escape as html_escape
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.urls import reverse
from .forms import SampleForm, SampleChangelistForm, taxonomy_for_form, species_name_options
from .models import Country, Sea, Region, Site, Species, Profile, Sample, DiveTrip, SiteImage, SpeciesArea, TaxonOrder, TaxonFamily, TaxonGenus, SampleKind, IdentificationQualifier, LifeStage

for model in [Country,Sea,Region,Site,Profile,SiteImage,SampleKind]: admin.site.register(model)


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'פרופיל'
    fields = ['first_name_en','last_name_en','phone','macro_diver','visible_to_members','countries','regions','bio']
    filter_horizontal = ['countries','regions']


admin.site.unregister(User)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = [ProfileInline]

class DatalistTextInput(forms.TextInput):
    """A plain single-line text input paired with an HTML5 <datalist> of suggested
    values -- a dropdown-with-autocomplete UX for a free-text field, without constraining
    it to a fixed choice list (existing values outside the list still save/display fine).
    Species.order/family are plain TextFields, not ForeignKeys to TaxonOrder/TaxonFamily
    (those curated tables are matched against this text elsewhere, e.g. build_taxonomy_
    tables) -- turning them into a *real* ForeignKey-backed autocomplete like TaxonFamily.
    order/TaxonGenus.family use would need a schema migration and touches everywhere this
    text is read (templates, the catalog.js builder, management commands, tests), so this
    keeps the storage and every other code path unchanged."""
    def __init__(self, datalist_options=(), attrs=None):
        super().__init__(attrs)
        self.datalist_options = list(datalist_options)
    def render(self, name, value, attrs=None, renderer=None):
        attrs = dict(attrs or {})
        list_id = f"{attrs.get('id', name)}__datalist"
        attrs['list'] = list_id
        input_html = super().render(name, value, attrs, renderer)
        options_html = ''.join(f'<option value="{html_escape(opt)}">' for opt in self.datalist_options)
        # mark_safe: SafeString + str is a plain str, which the admin's change form would escape
        return mark_safe(input_html + f'<datalist id="{list_id}">{options_html}</datalist>')


class SpeciesAdminForm(forms.ModelForm):
    """genus + species are what a species IS (the scientific name is derived from them), so
    the admin insists on both -- the model itself stays lenient for importers that only know
    a full name (see Species.sync_scientific_name)."""
    class Meta:
        model = Species
        fields = '__all__'
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['genus'].required = True
        self.fields['species'].required = True
        self.fields['genus'].widget = forms.TextInput()
        self.fields['species'].widget = forms.TextInput()
        self.fields['species'].help_text = 'אפשר לכלול סימון זהות פתוחה, למשל "cf. strigata" או "sp. 7".'


@admin.register(Species)
class SpeciesAdmin(admin.ModelAdmin):
    form = SpeciesAdminForm
    readonly_fields = ['scientific_name', 'full_name_display']
    @admin.display(description='שם מלא כולל מחבר (נגזר)')
    def full_name_display(self, obj):
        return obj.full_name if obj and obj.pk else '—'
    list_display = ['phylogenetic_order','scientific_name','is_migrant','name_he','name_en','first_observed_year','last_observed_year','genus','species','author','family','order']
    # Migrant status is checked far more often than any other field is edited here, so it's
    # editable straight from the changelist (a checkbox + one "Save" for the whole page) --
    # no need to open a species' full change form just to flag it as migrant.
    list_editable = ['is_migrant','name_he','name_en','first_observed_year','last_observed_year','author','family','order']
    search_fields = ['scientific_name','genus','species','author','family','name_he']
    list_filter = ['order','family','genus','is_migrant']
    fieldsets = [
        ('זיהוי מדעי', {'fields':['phylogenetic_order','genus','species','author','scientific_name','full_name_display','formatted_author','reference_author','full_species_name_with_order']}),
        ('סיווג טקסונומי', {'fields':['order','superfamily','family','accepted_genus','accepted_species']}),
        ('שמות ותפוצה', {'fields':['name_he','name_en','common_name','transliteration','language','distribution']}),
        ('תוכן לעמוד המין', {'fields':['description_he','description_en','identification_he','identification_en','similar_species_he','similar_species_en','size_from','size_to','size_max','link','article_pdf']}),
        ('בית גידול ותזונה', {'fields':['habitat','habitat_en','food','food_en','depth_min','depth_max','native_range_he','native_range_en']}),
        ('מין מהגר — הים התיכון', {'fields':['is_migrant','first_observed_year','first_record_place_he','first_record_place_en','last_observed_year','last_record_place_he','last_record_place_en','med_status_he','med_status_en','introduction_route_he','introduction_route_en']}),
        ('מקורות', {'fields':['sources']}),
    ]
    def _order_options(self):
        canonical = TaxonOrder.objects.exclude(name='').values_list('name', flat=True)
        existing = Species.objects.exclude(order='').values_list('order', flat=True)
        return sorted(set(canonical) | set(existing))
    def _family_options(self):
        canonical = TaxonFamily.objects.exclude(name='').values_list('name', flat=True)
        existing = Species.objects.exclude(family='').values_list('family', flat=True)
        return sorted(set(canonical) | set(existing))
    # Compact inputs for the changelist only (the full change form keeps its normal width):
    # the Hebrew/English names were taking far more of the row than they need, and the two
    # observed-year columns only ever hold four digits.
    changelist_input_widths = {'name_he': '9em', 'name_en': '9em', 'first_observed_year': '5em', 'last_observed_year': '5em'}
    def get_changelist_form(self, request, **kwargs):
        # Through Meta.widgets (not by editing base_fields): the changelist formset builds a
        # subclass of this form and regenerates its model fields, which would drop such edits.
        widgets = {name: (forms.NumberInput(attrs={'min': 1900, 'style': f'width:{width}'}) if name.endswith('_year')
                          else forms.TextInput(attrs={'style': f'width:{width}'}))
                   for name, width in self.changelist_input_widths.items()}
        return super().get_changelist_form(request, widgets=widgets, **kwargs)
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        # author/family/order are plain TextFields, which Django would otherwise render as
        # a multi-line Textarea -- a single-line TextInput fits the changelist row (and the
        # change-form field) far better than that. family/order additionally get a
        # datalist of known values (see DatalistTextInput) so picking an existing
        # order/family doesn't mean retyping it from memory.
        if db_field.name == 'author':
            kwargs['widget'] = forms.TextInput
        elif db_field.name == 'order':
            kwargs['widget'] = DatalistTextInput(datalist_options=self._order_options())
        elif db_field.name == 'family':
            kwargs['widget'] = DatalistTextInput(datalist_options=self._family_options())
        return super().formfield_for_dbfield(db_field, request, **kwargs)

@admin.register(IdentificationQualifier)
class IdentificationQualifierAdmin(admin.ModelAdmin):
    # The values offered by a sample's "סימון זהות לא ודאית" field -- add new ones here.
    list_display = ['code', 'name', 'name_en']
    search_fields = ['code', 'name', 'name_en']


@admin.register(LifeStage)
class LifeStageAdmin(admin.ModelAdmin):
    # The values offered by a sample's "שלב חיים" field -- add new ones here.
    list_display = ['code', 'name', 'name_en']
    search_fields = ['code', 'name', 'name_en']


class TaxonOrderListFilter(admin.RelatedFieldListFilter):
    """Filter by order row, labelled so rows that share a name can be told apart. TaxonOrder has
    several rows per order name (Nudibranchia/Doridina, Nudibranchia/Cladobranchia, ...), so the
    plain name reads like duplicates: each option also shows the group's Hebrew name and the
    superfamilies of its families. The counts beside the options are the rows of the list
    being filtered (genera or families), which the title says."""
    counted = 'הסוגים'

    def field_choices(self, field, request, model_admin):
        superfamilies = {}
        for order_id, superfamily in TaxonFamily.objects.exclude(superfamily='').values_list('order_id', 'superfamily'):
            if order_id and '\\' not in superfamily:    # a few rows hold the import artifact "\N"
                superfamilies.setdefault(order_id, set()).add(superfamily)
        orders = {o.pk: o for o in TaxonOrder.objects.all()}
        choices = []
        for pk, label in super().field_choices(field, request, model_admin):
            order = orders.get(pk)
            if order is not None:
                parts = [str(order)]
                if order.name_he: parts.append(order.name_he)
                if superfamilies.get(pk): parts.append(', '.join(sorted(superfamilies[pk])))
                label = ' · '.join(parts)
            choices.append((pk, label))
        return choices

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title = f'סדרה (בסוגריים: מספר {self.counted})'


class TaxonOrderFamilyListFilter(TaxonOrderListFilter):
    counted = 'המשפחות'


@admin.register(TaxonOrder)
class TaxonOrderAdmin(admin.ModelAdmin):
    list_display = ['taxonomic_order', 'name', 'name_he', 'name_en', 'sub_order', 'defining_sample']
    search_fields = ['name', 'name_he', 'name_en', 'sub_order']


@admin.register(TaxonFamily)
class TaxonFamilyAdmin(admin.ModelAdmin):
    list_display = ['taxonomic_order', 'name', 'name_he', 'name_en', 'sub_family', 'superfamily', 'order', 'defining_sample']
    list_filter = [('order', TaxonOrderFamilyListFilter)]
    search_fields = ['name', 'name_he', 'name_en', 'sub_family', 'superfamily']
    autocomplete_fields = ['order']


@admin.register(TaxonGenus)
class TaxonGenusAdmin(admin.ModelAdmin):
    list_display = ['taxonomic_order', 'name', 'name_he', 'name_en', 'family', 'defining_sample']
    list_filter = [('family__order', TaxonOrderListFilter)]
    search_fields = ['name', 'name_he', 'name_en']
    autocomplete_fields = ['family']
    fieldsets = [
        ('זיהוי וסיווג', {'fields': ['name', 'name_he', 'name_en', 'family', 'taxonomic_order', 'defining_sample']}),
        ('תיאור וזיהוי', {'fields': ['description_he', 'description_en', 'identification_he', 'identification_en']}),
        ('קובץ זיהוי (תרשים, תמונות או מפתח)', {'fields': ['identification_file', 'identification_caption', 'identification_caption_en', 'identification_source']}),
        ('מקורות וקבצים', {'fields': ['sources', 'link', 'article_pdf']}),
    ]
    actions = ['refresh_defining_samples']
    @admin.action(description='עדכון דגימה מגדירה לכל הסוגים מתוך דגימות ה"סוג" הקיימות (מתעלם מהבחירה)')
    def refresh_defining_samples(self, request, queryset):
        from io import StringIO
        from django.core.management import call_command
        output = StringIO()
        call_command('assign_genus_defining_samples', '--apply', stdout=output)
        messages.success(request, output.getvalue().strip())


@admin.register(DiveTrip)
class DiveTripAdmin(admin.ModelAdmin):
    list_display = ['code','title','kind','year','month','country','region','site','species_count']
    list_filter = ['kind','year','country','region','site']
    search_fields = ['code','title','region_name','reserve','site__name']
    readonly_fields = ['source_metadata']

    # Narrows the "region" options to the selected country and the "site" options to the
    # selected region, fetched from views.divetrip_locations. See divetrip_admin.js. (A trip's
    # sea is its region's sea -- there is no sea field on the trip.)
    class Media:
        js = ['observations/js/divetrip_admin.js']


@admin.register(SpeciesArea)
class SpeciesAreaAdmin(admin.ModelAdmin):
    list_display = ['species','undetermined_variant','country','sea','defining_sample','slug']
    list_filter = ['country','sea']
    search_fields = ['species__scientific_name','undetermined_variant','slug']
    autocomplete_fields = []
    actions = ['rebuild_all']
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'defining_sample' and getattr(self, '_obj', None):
            # Only samples that would actually qualify to show the species in the gallery --
            # published, not deleted, matching this row's species+country+sea+variant.
            kwargs['queryset'] = Sample.objects.filter(kind='species', species_id=self._obj.species_id, status='published',
                trip__country_id=self._obj.country_id, trip__region__sea_id=self._obj.sea_id, deleted_at__isnull=True,
                undetermined_variant=self._obj.undetermined_variant)
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

class DropdownAllValuesFilter(admin.AllValuesFieldListFilter):
    """Filter by a text column's existing values as a compact <select> (instead of one link
    per value -- a column like genus has hundreds of them)."""
    template = 'admin/dropdown_filter.html'


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
    list_display=['id','title','kind','order','family','genus','species','identification_qualifier','life_stage','trip_code','owner','status','publication_warning','deleted_at']
    # Like the Species list, the identification columns are editable straight from the list.
    list_editable=['order','family','genus','species','identification_qualifier','life_stage']
    # Long lists of values (genera, publication reasons...) are compact dropdowns, not one link
    # per value, so the filter panel stays narrow (see templates/admin/observations/sample/change_list.html).
    list_filter=['status','kind',('order',DropdownAllValuesFilter),('family',DropdownAllValuesFilter),('genus',DropdownAllValuesFilter),TripCodeListFilter,PublicationReasonListFilter,'deleted_at']
    list_per_page=100
    def get_changelist_form(self,request,**kwargs):
        # order/family/genus/species are plain inputs bound to ONE shared <datalist> each (rendered
        # once by the list template) rather than a datalist per row -- 100 rows x hundreds of
        # genera would make the page heavy.
        class Form(SampleChangelistForm):
            class Meta(SampleChangelistForm.Meta):
                widgets={'order':forms.TextInput(attrs={'list':'sample-order-options','size':14,'autocomplete':'off'}),
                         'family':forms.TextInput(attrs={'list':'sample-family-options','size':16,'autocomplete':'off'}),
                         'genus':forms.TextInput(attrs={'list':'sample-genus-options','size':14,'autocomplete':'off'})}
        return Form
    def changelist_view(self,request,extra_context=None):
        extra_context=dict(extra_context or {})
        extra_context['sample_datalists']={
            'order':sorted(set(TaxonOrder.objects.exclude(name='').values_list('name',flat=True))|set(Sample.objects.exclude(order='').values_list('order',flat=True))),
            'family':sorted(set(TaxonFamily.objects.exclude(name='').values_list('name',flat=True))|set(Sample.objects.exclude(family='').values_list('family',flat=True))),
            'genus':sorted(set(TaxonGenus.objects.exclude(name='').values_list('name',flat=True))),
            'species':sorted(set(Species.objects.exclude(species='').values_list('species',flat=True))),
        }
        return super().changelist_view(request,extra_context)
    def get_form(self,request,obj=None,change=False,**kwargs):
        form=super().get_form(request,obj,change=change,**kwargs)
        class AdminSampleForm(form):
            def __init__(self,*args,**kw):
                super().__init__(*args,**kw)
                self.enable_add_links()
        return AdminSampleForm
    def render_change_form(self,request,context,*args,**kwargs):
        # The same cascading order -> family -> genus -> species fields as the observation form
        # (templates/observations/_taxonomy_cascade.html, included by this model's change_form).
        context['taxonomy']=taxonomy_for_form()
        context['species_options']=species_name_options()
        return super().render_change_form(request,context,*args,**kwargs)
    search_fields=['title','species__scientific_name','species_other','order','family','genus','owner__username','source_id','trip__title']
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
    def save_model(self,request,obj,form,change):
        # A freshly uploaded image here is still an uncommitted in-memory file (clean_image's
        # own throwaway UUID name) -- write it under the canonical name (see
        # Sample.canonical_image_name) explicitly, exactly like every other way of attaching
        # an image already does (the public form, the bulk folder importer, the image
        # manager's transfer upload; admin was the one path that didn't). This can't be done
        # by just renaming obj.image.name and letting save() below write it normally: Django's
        # own upload_to machinery re-joins that prefix onto whatever name an uncommitted file
        # has at save time, which would double it, since canonical_image_name() already
        # returns a path that includes the observations/ prefix.
        if 'image' in form.changed_data and obj.image:
            from .media_transfer import save_images
            raw=obj.image.read();name=obj.canonical_image_name()
            save_images({name:raw});obj.image=name
        obj.save_reviewed()
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
