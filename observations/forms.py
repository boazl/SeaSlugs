from io import BytesIO
from uuid import uuid4
from PIL import Image, ImageOps, UnidentifiedImageError
from django import forms
from django.core.files.base import ContentFile
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils.html import format_html
from .models import Sample, Profile, Species, Country, Region, Site, DiveTrip


class SignupForm(UserCreationForm):
    first_name = forms.CharField(label='שם פרטי', max_length=150, required=False)
    email = forms.EmailField(label='דואר אלקטרוני', required=True)
    class Meta:
        model = User
        fields = ('username','first_name','email','password1','password2')


class ProfileForm(forms.ModelForm):
    first_name = forms.CharField(label='שם פרטי', max_length=150, required=False)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].initial = self.instance.user.first_name
    def save(self, commit=True):
        profile = super().save(commit=commit)
        if commit:
            profile.user.first_name = self.cleaned_data['first_name']
            profile.user.save(update_fields=['first_name'])
        return profile

    class Meta:
        model = Profile
        fields = ['display_name','macro_diver','visible_to_members','countries','regions','bio']
        widgets = {'countries':forms.CheckboxSelectMultiple, 'regions':forms.CheckboxSelectMultiple}


class AutocompleteWidget(forms.Widget):
    """A search-as-you-type text input backed by a JSON endpoint, standing in for a
    <select> when the choice list (e.g. thousands of species) is too large to render
    inline. The bound value stays a plain string — a pk, '', or the 'other' sentinel —
    exactly like the plain ChoiceField it replaces, so form validation is unaffected."""
    def __init__(self, search_url_name, label_for_value=None, other_value='other',
                 other_label='אחר — פירוט', placeholder='הקלידו לחיפוש…', attrs=None):
        super().__init__(attrs)
        self.search_url_name = search_url_name
        self.label_for_value = label_for_value or (lambda value: '')
        self.other_value = other_value
        self.other_label = other_label
        self.placeholder = placeholder

    def value_omitted_from_data(self, data, files, name):
        return name not in data

    def render(self, name, value, attrs=None, renderer=None):
        attrs = attrs or {}
        widget_id = attrs.get('id') or f'id_{name}'
        value = '' if value in (None, 'None') else str(value)
        if value == self.other_value:
            display = self.other_label
        elif value:
            display = self.label_for_value(value)
        else:
            display = ''
        search_id, results_id = f'{widget_id}_search', f'{widget_id}_results'
        return format_html(
            '<span class="autocomplete-wrap">'
            '<input type="text" id="{search_id}" class="autocomplete-search" autocomplete="off" '
            'placeholder="{placeholder}" value="{display}">'
            '<div class="autocomplete-results" id="{results_id}" hidden></div>'
            '</span>'
            '<input type="hidden" name="{name}" id="{widget_id}" value="{value}">'
            '<script>(window.__autocompleteQueue=window.__autocompleteQueue||[]).push([{widget_id_js}, {search_id_js}, {results_id_js}, {url_js}, {other_value_js}, {other_label_js}]);</script>',
            search_id=search_id, results_id=results_id, placeholder=self.placeholder, display=display,
            name=name, widget_id=widget_id, value=value,
            widget_id_js=_js_str(widget_id), search_id_js=_js_str(search_id), results_id_js=_js_str(results_id),
            url_js=_js_str(reverse(self.search_url_name)), other_value_js=_js_str(self.other_value),
            other_label_js=_js_str(self.other_label))


def _js_str(value):
    import json
    return json.dumps(value)


class TripChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        where = ' · '.join(x for x in [str(obj.region) if obj.region_id else obj.region_name, str(obj.country) if obj.country_id else obj.country_name] if x)
        when = f'{obj.month}/{obj.year}' if obj.month and obj.year else (str(obj.year) if obj.year else '')
        bits = ' · '.join(x for x in [where, when] if x)
        return f'{obj.title} ({bits})' if bits else obj.title


class SampleForm(forms.ModelForm):
    species = forms.CharField(label='מין', required=False, widget=AutocompleteWidget('species-search'))
    site = forms.ChoiceField(label='אתר צלילה',required=False)
    trip = TripChoiceField(label='מסע צלילה', queryset=DiveTrip.objects.all(), help_text='לא מוצא/ת את המסע? אפשר להוסיף מסע חדש ולחזור לכאן.')
    class Meta:
        model = Sample
        fields = ['title','kind','species','species_other','trip','site','site_other','day','depth','video_url','image']
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['kind'].required = False
        self.fields['video_url'].help_text = 'אפשר להשאיר ריק כאשר מעלים תמונה. ניתן להוסיף סרטון בהמשך.'
        self.fields['species'].widget.label_for_value = lambda pk: str(Species.objects.filter(pk=pk).first() or '')
        self.fields['site'].choices = [('', 'בחרו…')] + [(str(x.pk), str(x)) for x in Site.objects.all()] + [('other','אחר — פירוט')]
        for name in ['species','site']:
            if self.instance.pk:
                self.initial[name] = str(getattr(self.instance,name+'_id') or ('other' if getattr(self.instance,name+'_other') else ''))
            self.fields[name+'_other'].widget.attrs['data-other-for'] = name
        self.fields['image'].help_text = 'JPEG, PNG או WebP, עד 10MB ועד 25 מיליון פיקסלים. מומלץ צילום רוחבי 1920×1080 ומעלה. נשמור JPEG עד 1920×1080, ללא חיתוך או הגדלת תמונה קטנה. תמונה שהועלתה תשמש כתצוגה מקדימה לסרטון; ללא סרטון תיפתח התמונה המלאה. ללא תמונה נשתמש בתצוגה המקדימה של YouTube. העלו רק תמונות שיש לכם הרשאה לפרסם.'
    def clean(self):
        data = super().clean()
        data['kind'] = data.get('kind') or Sample.Kind.SPECIES
        for name, model in [('species',Species),('site',Site)]:
            value = data.get(name)
            if value == 'other':
                if not data.get(name+'_other','').strip(): self.add_error(name+'_other','יש לפרט את הערך האחר.')
                data[name] = None
            elif value:
                try:
                    data[name] = model.objects.get(pk=value)
                except (model.DoesNotExist, ValueError, TypeError):
                    self.add_error(name,'ערך לא תקין.')
                    data[name] = None
                else:
                    data[name+'_other'] = ''
            else:
                data[name] = None
                data[name+'_other'] = ''
        return data
    def clean_image(self):
        file = self.cleaned_data.get('image')
        if not file or not hasattr(file, 'content_type'): return file
        if file.size > 10 * 1024 * 1024: raise forms.ValidationError('התמונה גדולה מ־10MB.')
        try:
            file.seek(0)
            with Image.open(file) as original:
                if original.format not in {'JPEG','PNG','WEBP'} or original.width * original.height > 25_000_000:
                    raise ValueError()
                image = ImageOps.exif_transpose(original).convert('RGB')
                image.thumbnail((1920,1080), Image.Resampling.LANCZOS)
                output = BytesIO()
                image.save(output,format='JPEG',quality=80,optimize=True)
            return ContentFile(output.getvalue(),name=f'{uuid4().hex}.jpg')
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            raise forms.ValidationError('יש להעלות תמונת JPEG, PNG או WebP תקינה, עד 25 מיליון פיקסלים.')


class DiveTripForm(forms.ModelForm):
    country = forms.ChoiceField(label='מדינה')
    region = forms.ChoiceField(label='אזור')
    class Meta:
        model = DiveTrip
        fields = ['title','country','region','year','month','start_day','duration_days','photographer','reserve']
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['region'].help_text = 'רשימת האזורים מסוננת לפי המדינה שנבחרה.'
        for name, model in [('country',Country),('region',Region)]:
            self.fields[name].choices = [('', 'בחרו…')] + [(str(x.pk), str(x)) for x in model.objects.all()]
            if self.instance.pk:
                self.initial[name] = str(getattr(self.instance,name+'_id') or '')
    def clean(self):
        data = super().clean()
        for name, model in [('country',Country),('region',Region)]:
            value = data.get(name)
            data[name] = model.objects.get(pk=value) if value else None
        if data.get('region') and data.get('country') and data['region'].country_id != data['country'].id:
            self.add_error('region', 'האזור אינו שייך למדינה שנבחרה.')
        return data
    def save(self, commit=True):
        trip = super().save(commit=False)
        if trip.country_id: trip.country_name = trip.country.name_en or trip.country.name
        if trip.region_id: trip.region_name = trip.region.name_en or trip.region.name
        if commit: trip.save()
        return trip
