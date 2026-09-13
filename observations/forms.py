from io import BytesIO
from uuid import uuid4
from PIL import Image, ImageOps, UnidentifiedImageError
from django import forms
from django.core.files.base import ContentFile
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Sample, Profile, Species, Country, Region, Site


class SignupForm(UserCreationForm):
    email = forms.EmailField(label='דואר אלקטרוני', required=True)
    class Meta:
        model = User
        fields = ('username','email','password1','password2')


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['display_name','macro_diver','visible_to_members','countries','regions','bio']
        widgets = {'countries':forms.CheckboxSelectMultiple, 'regions':forms.CheckboxSelectMultiple}


class SampleForm(forms.ModelForm):
    year = forms.IntegerField(label='שנה', min_value=1900)
    species = forms.ChoiceField(label='מין')
    country = forms.ChoiceField(label='מדינה')
    region = forms.ChoiceField(label='אזור')
    site = forms.ChoiceField(label='אתר צלילה',required=False)
    class Meta:
        model = Sample
        fields = ['title','species','species_other','country','country_other','region','region_other','site','site_other','year','month','day','depth','video_url','image']
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        for name, model in [('species',Species),('country',Country),('region',Region),('site',Site)]:
            self.fields[name].choices = [('', 'בחרו…')] + [(str(x.pk), str(x)) for x in model.objects.all()] + [('other','אחר — פירוט')]
            if self.instance.pk:
                self.initial[name] = str(getattr(self.instance,name+'_id') or ('other' if getattr(self.instance,name+'_other') else ''))
            self.fields[name+'_other'].widget.attrs['data-other-for'] = name
        self.fields['image'].help_text = 'ללא העלאה נשתמש בתמונה המקדימה של YouTube. JPEG, PNG או WebP, עד 10MB; התמונה תוקטן ל־1600 פיקסלים.'
    def clean(self):
        data = super().clean()
        for name, model in [('species',Species),('country',Country),('region',Region),('site',Site)]:
            value = data.get(name)
            if value == 'other':
                if not data.get(name+'_other','').strip(): self.add_error(name+'_other','יש לפרט את הערך האחר.')
                data[name] = None
            elif value:
                data[name] = model.objects.get(pk=value)
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
                image.thumbnail((1600,1600))
                output = BytesIO()
                image.save(output,format='JPEG',quality=80,optimize=True)
            return ContentFile(output.getvalue(),name=f'{uuid4().hex}.jpg')
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            raise forms.ValidationError('יש להעלות תמונת JPEG, PNG או WebP תקינה, עד 25 מיליון פיקסלים.')
