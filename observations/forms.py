from io import BytesIO
from uuid import uuid4
from PIL import Image, ImageOps, UnidentifiedImageError
from django import forms
from django.core.files.base import ContentFile
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
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


class TripChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        where = ' · '.join(x for x in [str(obj.region) if obj.region_id else obj.region_name, str(obj.country) if obj.country_id else obj.country_name] if x)
        when = f'{obj.month}/{obj.year}' if obj.month and obj.year else (str(obj.year) if obj.year else '')
        bits = ' · '.join(x for x in [where, when] if x)
        return f'{obj.title} ({bits})' if bits else obj.title


class SampleForm(forms.ModelForm):
    # A native text input backed by a <datalist> (rendered in form.html from
    # species_options) rather than a <select> -- there can be hundreds of species, and
    # this is the same open-dropdown-with-autocomplete pattern used for the genus filter
    # on the observations list page. The submitted value is the scientific name itself
    # (matched case-insensitively in clean() below), not a pk. It must match an existing
    # species exactly -- species_other (below) is the deliberate, separate escape hatch
    # for a species that isn't catalogued yet, so a typo here can't silently turn into an
    # "unidentified species" record.
    species = forms.CharField(label='מין', required=False, widget=forms.TextInput(attrs={
        'list': 'species-options', 'autocomplete': 'off', 'placeholder': 'הקלידו לחיפוש…'}))
    site = forms.ChoiceField(label='אתר צלילה',required=False)
    trip = TripChoiceField(label='מסע צלילה', queryset=DiveTrip.objects.all(), help_text='לא מוצא/ת את המסע? אפשר להוסיף מסע חדש ולחזור לכאן.')
    class Meta:
        model = Sample
        fields = ['title','kind','species','species_other','trip','site','site_other','day','depth','video_url','image']
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['kind'].required = False
        self.fields['video_url'].help_text = 'אפשר להשאיר ריק כאשר מעלים תמונה. ניתן להוסיף סרטון בהמשך.'
        if self.instance.pk:
            self.initial['species'] = self.instance.species.scientific_name if self.instance.species_id else ''
        self.fields['species_other'].help_text = 'אם המין לא נמצא ברשימה שלמעלה, אפשר לפרט כאן במקום לבחור מהרשימה.'
        self.fields['site'].choices = [('', 'בחרו…')] + [(str(x.pk), str(x)) for x in Site.objects.all()] + [('other','אחר — פירוט')]
        if self.instance.pk:
            self.initial['site'] = str(self.instance.site_id or ('other' if self.instance.site_other else ''))
        self.fields['site_other'].widget.attrs['data-other-for'] = 'site'
        self.fields['image'].help_text = 'JPEG, PNG או WebP, עד 10MB ועד 25 מיליון פיקסלים. מומלץ צילום רוחבי 1920×1080 ומעלה. נשמור JPEG עד 1920×1080, ללא חיתוך או הגדלת תמונה קטנה. תמונה שהועלתה תשמש כתצוגה מקדימה לסרטון; ללא סרטון תיפתח התמונה המלאה. ללא תמונה נשתמש בתצוגה המקדימה של YouTube. העלו רק תמונות שיש לכם הרשאה לפרסם.'
    def clean(self):
        data = super().clean()
        data['kind'] = data.get('kind') or Sample.Kind.SPECIES

        # species_other, if filled in, always wins -- it's a deliberate manual override.
        # Otherwise, whatever was typed into species must match an existing species
        # exactly (case-insensitively); if it doesn't, that's a validation error rather
        # than a silent fallback, since a typo or a near-miss must not quietly become an
        # "unidentified species" record.
        species_text = (data.get('species') or '').strip()
        other_text = (data.get('species_other') or '').strip()
        if other_text:
            data['species'] = None
            data['species_other'] = other_text
        elif species_text:
            match = Species.objects.filter(scientific_name__iexact=species_text).first()
            if match:
                data['species'] = match
                data['species_other'] = ''
            else:
                self.add_error('species', 'לא נמצא מין תואם ברשימה. יש לבחור מין קיים, או למלא "מין אחר".')
                data['species'] = None
        else:
            data['species'] = None
            data['species_other'] = ''

        value = data.get('site')
        if value == 'other':
            if not data.get('site_other','').strip(): self.add_error('site_other','יש לפרט את הערך האחר.')
            data['site'] = None
        elif value:
            try:
                data['site'] = Site.objects.get(pk=value)
            except (Site.DoesNotExist, ValueError, TypeError):
                self.add_error('site','ערך לא תקין.')
                data['site'] = None
            else:
                data['site_other'] = ''
        else:
            data['site'] = None
            data['site_other'] = ''
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
