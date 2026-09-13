from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from .forms import SampleForm
from .models import Country, Sea, Region, Site, Species, Profile, Sample

for model in [Country,Sea,Region,Site,Species,Profile]: admin.site.register(model)

@admin.register(Sample)
class SampleAdmin(admin.ModelAdmin):
    form = SampleForm
    list_display=['id','title','species','region','year','owner','status','deleted_at']
    list_filter=['status','region','deleted_at']
    search_fields=['title','species__scientific_name','species_other','owner__username','source_id']
    readonly_fields=['source_metadata','source_id','status','created_at','updated_at','deleted_at','deleted_by','approved_at','approved_by']
    actions=['approve','soft_remove','restore']
    def has_delete_permission(self,request,obj=None): return False
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
