from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.utils.html import format_html, format_html_join
from django.urls import reverse
from .forms import SampleForm
from .models import Country, Sea, Region, Site, Species, Profile, Sample, DiveTrip

for model in [Country,Sea,Region,Site,Profile]: admin.site.register(model)

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

@admin.register(DiveTrip)
class DiveTripAdmin(admin.ModelAdmin):
    list_display = ['code','title','year','month','country_name','region_name','photographer','species_count']
    list_filter = ['year','country_name','photographer']
    search_fields = ['code','title','region_name','reserve','photographer']
    readonly_fields = ['source_metadata']

@admin.register(Sample)
class SampleAdmin(admin.ModelAdmin):
    form = SampleForm
    list_display=['id','title','kind','species','trip','region','year','owner','status','publication_warning','deleted_at']
    list_filter=['status','kind','trip','region','deleted_at']
    search_fields=['title','species__scientific_name','species_other','owner__username','source_id']
    readonly_fields=['publication_warning','source_metadata','source_id','status','created_at','updated_at','deleted_at','deleted_by','approved_at','approved_by']
    actions=['approve','soft_remove','restore']
    def has_delete_permission(self,request,obj=None): return False
    @admin.display(description='סיבת אי־פרסום')
    def publication_warning(self,obj):
        if not obj or not obj.pk: return '—'
        reasons = obj.publication_reasons()
        if not reasons: return '—'
        text = format_html_join('', '<div>{}</div>', ((reason,) for reason in reasons))
        duplicate = obj.publication_duplicate()
        link = format_html('<a href="{}">פתיחת התצפית הקיימת</a>',reverse('admin:observations_sample_change',args=[duplicate.pk])) if duplicate else ''
        return format_html('<div style="color:#ba2121;font-weight:600">{}{}</div>',text,link)
    def save_model(self,request,obj,form,change): obj.save_reviewed()
    @admin.action(description='אישור פרסום לאחר השלמת הנתונים',permissions=['change'])
    def approve(self,request,queryset):
        for item in queryset.filter(deleted_at__isnull=True):
            try: item.save_reviewed(actor=request.user,approve=True)
            except ValidationError as exc: self.message_user(request,f'{item}: {exc}',messages.ERROR)
    @admin.action(description='סימון כמחוקה',permissions=['change'])
    def soft_remove(self,request,queryset):
        for item in queryset: item.soft_delete(request.user)
    @admin.action(description='שחזור לבדיקה מחדש',permissions=['change'])
    def restore(self,request,queryset):
        for item in queryset:
            item.deleted_at=None;item.deleted_by=None
            item.save_reviewed()
