from io import BytesIO
from uuid import uuid4
from PIL import Image, ImageOps, UnidentifiedImageError
from django import forms
from django.urls import reverse
from django.utils.html import format_html
from django.core.files.base import ContentFile
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator
from .models import IDENTIFICATION_FILE_EXTENSIONS, Sample, Profile, Species, Country, Region, Site, DiveTrip, TaxonOrder, TaxonFamily, TaxonGenus, IdentificationQualifier, LifeStage, split_undetermined_variant


class SignupForm(UserCreationForm):
    first_name = forms.CharField(label='שם פרטי', max_length=150, required=False)
    last_name = forms.CharField(label='שם משפחה', max_length=150, required=False)
    email = forms.EmailField(label='דואר אלקטרוני', required=True)
    class Meta:
        model = User
        fields = ('username','first_name','last_name','email','password1','password2')


class ProfileForm(forms.ModelForm):
    # The Hebrew name lives on the linked User model itself (first_name/last_name),
    # not on Profile -- these two fields piggyback on this form so it's edited in one
    # place, and are synced onto the user in save() below rather than being real
    # Profile model fields. first_name_en/last_name_en (in Meta.fields) are the only
    # names that actually live on Profile.
    first_name = forms.CharField(label='שם פרטי', max_length=150, required=False)
    last_name = forms.CharField(label='שם משפחה', max_length=150, required=False)
    # Keep the Hebrew name fields next to their English counterparts rather than at
    # the end of the form -- Django would otherwise place explicitly declared fields
    # (first_name/last_name) after every Meta.fields model field.
    field_order = ['first_name','last_name','first_name_en','last_name_en','phone','macro_diver','visible_to_members','countries','regions','bio']
    def __init__(self, *args, lang='he', **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].initial = self.instance.user.first_name
        self.fields['last_name'].initial = self.instance.user.last_name
        if lang == 'en':
            # Field labels/help_text are translated in the template (form.html runs
            # them through the `t` filter); the countries/regions checkboxes are the
            # one part of this form whose individual choice text (Country/Region
            # names) is baked in Python instead, so it needs its own override here.
            self.fields['countries'].label_from_instance = lambda obj: obj.name_en or obj.name
            self.fields['regions'].label_from_instance = lambda obj: obj.name_en or obj.name
    def save(self, commit=True):
        profile = super().save(commit=commit)
        if commit:
            profile.user.first_name = self.cleaned_data['first_name']
            profile.user.last_name = self.cleaned_data['last_name']
            profile.user.save(update_fields=['first_name', 'last_name'])
        return profile

    class Meta:
        model = Profile
        fields = ['first_name_en','last_name_en','phone','macro_diver','visible_to_members','countries','regions','bio']
        widgets = {'countries':forms.CheckboxSelectMultiple, 'regions':forms.CheckboxSelectMultiple}


class TripChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        where = ' · '.join(x for x in [str(obj.region) if obj.region_id else obj.region_name, str(obj.country) if obj.country_id else obj.country_name] if x)
        when = f'{obj.month}/{obj.year}' if obj.month and obj.year else (str(obj.year) if obj.year else '')
        bits = ' · '.join(x for x in [where, when] if x)
        return f'{obj.title} ({bits})' if bits else obj.title


class SampleImageInput(forms.ClearableFileInput):
    """Adds a visual thumbnail next to the already-uploaded image on the observation form --
    Django's default widget only shows a text link to the file, no picture. The link and
    the thumbnail both go through the observation-photo view rather than the raw storage
    URL (widget.value.url), since production never serves MEDIA_ROOT directly and only that
    access-controlled view is guaranteed to actually show the image."""
    template_name = 'observations/widgets/sample_image_input.html'



class TaxonFileInput(forms.ClearableFileInput):
    """File input for a genus/family/order file (article PDF, identification file) edited from
    the observation form: shows the current file as a link to its public streaming view
    (production never serves MEDIA_ROOT directly), with a thumbnail for an image, plus the
    usual "clear" checkbox."""
    template_name = 'observations/widgets/taxon_file_input.html'
    link_url = ''
    show_image = False
    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context['widget']['link_url'] = self.link_url
        context['widget']['show_image'] = self.show_image
        return context


TAXON_FILE_MAX_BYTES = 15 * 1024 * 1024


def validate_taxon_file_size(value):
    if getattr(value, 'size', 0) > TAXON_FILE_MAX_BYTES:
        raise forms.ValidationError('הקובץ גדול מדי (עד 15MB).')


class ReferenceSelect(forms.Select):
    """A <select> whose values come from an admin-editable reference table, with an "add a value"
    link to that table's admin page when `add_url` is set (managers only)."""
    add_url = None
    def render(self, name, value, attrs=None, renderer=None):
        html = super().render(name, value, attrs, renderer)
        if self.add_url:
            html += format_html(' <a href="{}" target="_blank" rel="noopener">+ הוספת ערך חדש לרשימה</a>', self.add_url)
        return html


def reference_choices(model):
    return [('', 'ללא')] + [(row.code, str(row)) for row in model.objects.all()]


def reference_field(model, label, help_text=''):
    """Choice field over a CodedReference table; the model's `code` is what the sample stores."""
    return forms.ChoiceField(label=label, required=False, widget=ReferenceSelect, help_text=help_text,
                             choices=lambda: reference_choices(model))


def taxonomy_for_form():
    """The order -> family -> genus chain (from the taxonomy tables) and each catalogued
    species' author, for the cascading taxonomy fields (observation form and Samples admin,
    see observations/_taxonomy_cascade.html). Species themselves are listed separately (see
    species_name_options); a species' genus is the first word of its name."""
    families = TaxonFamily.objects.select_related('order')
    return {
        'orders': sorted({o.name for o in TaxonOrder.objects.all()}),
        'families': sorted({(f.name, f.order.name if f.order_id else '') for f in families}),
        'genera': sorted({(g.name, g.family.name if g.family_id else '', g.family.order.name if g.family_id and g.family.order_id else '')
                          for g in TaxonGenus.objects.select_related('family__order')}),
        'authors': {s.scientific_name: s.author.strip() for s in Species.objects.exclude(author='').only('scientific_name', 'author')},
    }


def species_name_options():
    return [str(item) for item in Species.objects.order_by('scientific_name')]


def resolve_species(genus, text):
    """Find the catalogued species for the genus + species (epithet) fields.

    `text` is the epithet only ("strigata", "cf. strigata", "sp. 7", "sp. A" -- a trailing
    letter after "sp." is the photographer's own undetermined-variant marker, split off here);
    a full "Genus epithet" name typed (or posted by older clients) in it is accepted too.
    Returns (species_or_None, variant)."""
    genus, text = (genus or '').strip(), (text or '').strip()
    if not text: return None, ''
    candidates = [f'{genus} {text}', text] if genus else [text]
    for candidate in candidates:
        base, variant = split_undetermined_variant(candidate)
        match = Species.find_by_name(base)
        if match: return match, variant
    return None, ''


def species_epithet_with_variant(sample):
    """What the species field shows when editing: the epithet only (the genus has its own
    field), plus the photographer's undetermined-variant letter if the sample has one."""
    return f'{sample.species.species} {sample.undetermined_variant}'.strip() if sample.species_id else ''


class TaxonTextField(forms.CharField):
    """A taxon's page text edited in a textarea. Browsers submit line breaks as CRLF, so a text
    stored with LF would look changed on every save: compare, and store, with LF."""
    def to_python(self, value):
        return super().to_python(value).replace('\r\n', '\n')


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
        'list': 'species-options', 'autocomplete': 'off', 'placeholder': 'הקלידו לחיפוש…'}),
        help_text='שם המין בלבד, בלי הסוג (הסוג בשדה שלמעלה). אפשר לכלול cf. / sp. 7 וכד׳ כפי שהם רשומים ברשימת המינים.')
    # The taxonomic cascade: order -> family -> genus -> species. Which of them is available
    # depends on the kind (form.html's script enables/disables them live, and
    # Sample.sync_taxonomy() normalises on the server). Each is a text input with a <datalist>
    # that the script narrows by the level above it.
    full_name = forms.CharField(label='השם המדעי המלא (כולל מחבר ותוספות)', required=False, disabled=True,
        widget=forms.TextInput(attrs={'size': 60}),
        help_text='מתעדכן אוטומטית לפי הסדרה/המשפחה/הסוג/המין שנבחרו, סימון הזהות (cf./aff.) ושלב החיים.')
    identification_qualifier = reference_field(IdentificationQualifier, 'סימון זהות לא ודאית',
        'cf. = דומה ל…, aff. = קרוב ל… — מוצג בין הסוג למין. רק בדגימה מסוג ״מין״. הערכים נשמרים בטבלת העזר.')
    life_stage = reference_field(LifeStage, 'שלב חיים', 'למשל juv. = פרט צעיר — מוצג אחרי השם. הערכים נשמרים בטבלת העזר.')
    site = forms.ChoiceField(label='אתר צלילה',required=False)
    trip = TripChoiceField(label='מסע צלילה', queryset=DiveTrip.objects.all(), required=False, help_text='לא מוצא/ת את המסע? אפשר להוסיף מסע חדש ולחזור לכאן.')
    class Meta:
        model = Sample
        fields = ['title','kind','order','family','genus','species','full_name','identification_qualifier','life_stage','species_other','trip','site','site_other','day','depth','video_url','image']
        widgets = {'image': SampleImageInput,
                   'order': forms.TextInput(attrs={'list': 'order-options', 'autocomplete': 'off', 'placeholder': 'הקלידו לחיפוש…'}),
                   'family': forms.TextInput(attrs={'list': 'family-options', 'autocomplete': 'off', 'placeholder': 'הקלידו לחיפוש…'}),
                   'genus': forms.TextInput(attrs={'list': 'genus-options', 'autocomplete': 'off', 'placeholder': 'הקלידו לחיפוש…'})}
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['kind'].required = False
        self.initial['full_name'] = self.instance.taxon_full_name if self.instance.pk else ''
        self.fields['video_url'].help_text = 'אפשר להשאיר ריק כאשר מעלים תמונה. ניתן להוסיף סרטון בהמשך.'
        if self.instance.pk:
            # The undetermined_variant letter (if any) lives on the Sample, not the Species
            # it points to (see Sample.undetermined_variant) -- append it back onto the
            # displayed text so re-editing shows exactly what was typed, and clean() below
            # round-trips it the same way it does on first entry.
            self.initial['species'] = species_epithet_with_variant(self.instance)
        self.fields['species_other'].help_text = 'אם המין לא נמצא ברשימה שלמעלה, אפשר לפרט כאן במקום לבחור מהרשימה.'
        self.fields['site'].choices = [('', 'בחרו…')] + [(str(x.pk), str(x)) for x in Site.objects.all()] + [('other','אחר — פירוט')]
        if self.instance.pk:
            self.initial['site'] = str(self.instance.site_id or ('other' if self.instance.site_other else ''))
        self.fields['site_other'].widget.attrs['data-other-for'] = 'site'
        # Whether this sample is the species' defining (gallery-representative) sample is
        # now checked live against the current species+trip fields (see form.html and
        # views.species_area_status), since either one changing changes the answer.
        self.fields['image'].help_text = 'JPEG, PNG או WebP, עד 10MB ועד 25 מיליון פיקסלים. מומלץ צילום רוחבי 1920×1080 ומעלה. נשמור JPEG עד 1920×1080, ללא חיתוך או הגדלת תמונה קטנה. תמונה שהועלתה תשמש כתצוגה מקדימה לסרטון; ללא סרטון תיפתח התמונה המלאה. ללא תמונה נשתמש בתצוגה המקדימה של YouTube. העלו רק תמונות שיש לכם הרשאה לפרסם.'
        # An order/family/genus observation describes a taxon, not a dive: the trip (and what hangs on it,
        # the dive site and day) isn't asked for. Disabled fields keep whatever the observation already
        # has, so editing an old one never wipes its trip. The picker script mirrors this live.
        self.fields['trip'].widget.attrs['required'] = True   # browser-side check; a disabled field is exempt from it
        kind_now = (self.data.get('kind') if self.is_bound else None) or self.initial.get('kind') or self.instance.kind
        if kind_now in self.TAXON_KINDS:
            for name in ('trip', 'site', 'site_other', 'day'):
                self.fields[name].disabled = True
            self.fields['trip'].help_text = 'לא נדרש לתצפית ברמת סדרה, משפחה או סוג.'
    TAXON_KINDS = (Sample.Kind.ORDER, Sample.Kind.FAMILY, Sample.Kind.GENUS)

    @staticmethod
    def taxon_for(kind, order='', family='', genus=''):
        """The TaxonOrder / TaxonFamily / TaxonGenus row a taxon-level sample stands for (None
        when its name has no row in the taxonomy tables). A family with sub-family rows is
        represented by its plain row, as on the family page."""
        if kind == Sample.Kind.GENUS and genus:
            return TaxonGenus.objects.filter(name=genus).first()
        if kind == Sample.Kind.FAMILY and family:
            rows = list(TaxonFamily.objects.filter(name=family))
            return next((r for r in rows if not r.sub_family), rows[0] if rows else None)
        if kind == Sample.Kind.ORDER and order:
            return TaxonOrder.objects.filter(name=order).first()
        return None

    def enable_taxon_files(self):
        """Managers only (these texts and files are shared page content, not the sample's own):
        adds the page content of the order/family/genus this sample stands for -- description,
        identification and sources (Hebrew and English) and an article PDF for any of the three,
        plus the identification file with its caption and source for a genus -- so they can be
        edited right here instead of in the admin."""
        for attr, label, rows in self.TAXON_TEXT_FIELDS:
            self.fields['taxon_' + attr] = TaxonTextField(required=False, label=label,
                widget=forms.Textarea(attrs={'rows': rows, 'data-taxon-file': 'any'}),
                help_text='קישור בכל שורה (אפשר להוסיף טקסט לפני הקישור).' if attr == 'sources' else '')
        pdf = [FileExtensionValidator(['pdf']), validate_taxon_file_size]
        self.fields['taxon_article_pdf'] = forms.FileField(required=False, label='מאמר (PDF) של הסדרה / המשפחה / הסוג',
            widget=TaxonFileInput(attrs={'accept': 'application/pdf', 'data-taxon-file': 'any'}), validators=pdf)
        self.fields['taxon_identification_file'] = forms.FileField(required=False, label='קובץ זיהוי של הסוג (PDF או תמונה)',
            widget=TaxonFileInput(attrs={'data-taxon-file': 'genus'}),
            validators=[FileExtensionValidator(IDENTIFICATION_FILE_EXTENSIONS), validate_taxon_file_size],
            help_text='תרשים, לוח תמונות או מפתח לזיהוי המינים בסוג: PDF או תמונה (JPG, PNG, WebP, GIF), עד 15MB.')
        self.fields['taxon_identification_caption'] = forms.CharField(required=False, max_length=300, label='כיתוב לקובץ הזיהוי',
            widget=forms.TextInput(attrs={'data-taxon-file': 'genus'}))
        self.fields['taxon_identification_caption_en'] = forms.CharField(required=False, max_length=300, label='כיתוב לקובץ הזיהוי (אנגלית)',
            widget=forms.TextInput(attrs={'data-taxon-file': 'genus', 'dir': 'ltr'}))
        self.fields['taxon_identification_source'] = forms.CharField(required=False, max_length=300, label='מקור קובץ הזיהוי',
            widget=forms.TextInput(attrs={'data-taxon-file': 'genus'}))
        instance = self.instance
        if instance.pk:
            kind, order, family, genus = instance.kind, instance.order, instance.family, instance.genus
        else:   # a new observation opened from a taxon page: kind and name arrive as initial values
            kind, order, family, genus = (self.initial.get(k) or '' for k in ('kind', 'order', 'family', 'genus'))
        taxon = self.taxon_for(kind, order, family, genus)
        if taxon is not None:
            for attr, _label, _rows in self.TAXON_TEXT_FIELDS:
                self.initial['taxon_' + attr] = getattr(taxon, attr)
            self.initial['taxon_article_pdf'] = taxon.article_pdf or None
            if kind == Sample.Kind.GENUS:
                self.initial['taxon_identification_file'] = taxon.identification_file or None
                self.initial['taxon_identification_caption'] = taxon.identification_caption
                self.initial['taxon_identification_caption_en'] = taxon.identification_caption_en
                self.initial['taxon_identification_source'] = taxon.identification_source
                self.fields['taxon_identification_file'].widget.link_url = reverse('genus-identification', args=[taxon.name])
                self.fields['taxon_identification_file'].widget.show_image = taxon.identification_is_image
                self.fields['taxon_article_pdf'].widget.link_url = reverse('genus-article', args=[taxon.name])
            elif kind == Sample.Kind.FAMILY:
                self.fields['taxon_article_pdf'].widget.link_url = reverse('family-article', args=[taxon.name])
            else:
                self.fields['taxon_article_pdf'].widget.link_url = reverse('order-article', args=[taxon.pk])

    # (TaxonOrder/Family/Genus attribute, label, textarea rows) -- the page texts every taxon-level sample can edit
    TAXON_TEXT_FIELDS = (
        ('description_he', 'תיאור בעברית (של הסדרה / המשפחה / הסוג)', 5),
        ('description_en', 'תיאור באנגלית (של הסדרה / המשפחה / הסוג)', 5),
        ('identification_he', 'סימני זיהוי בעברית', 4),
        ('identification_en', 'סימני זיהוי באנגלית', 4),
        ('sources', 'מקורות', 3),
    )
    TAXON_FILE_FIELDS = (tuple('taxon_' + attr for attr, _l, _r in TAXON_TEXT_FIELDS)
                         + ('taxon_article_pdf', 'taxon_identification_file', 'taxon_identification_caption', 'taxon_identification_caption_en', 'taxon_identification_source'))
    # the identification file, its captions and its source exist for genera only
    GENUS_ONLY_FIELDS = ('taxon_identification_file', 'taxon_identification_caption', 'taxon_identification_caption_en', 'taxon_identification_source')

    def clean_taxon_files(self, data):
        """Rejects an upload/clear that has no taxon row to attach to or that does not match
        the sample's kind (the fields stay on the page while the kind select changes)."""
        if 'taxon_article_pdf' not in self.fields:
            return
        touched = [n for n in self.TAXON_FILE_FIELDS if n in self.changed_data]
        if not touched:
            return
        kind = data.get('kind')
        if kind not in self.TAXON_KINDS:
            self.add_error(touched[0], 'קבצים אלה מתאימים רק לדגימה מסוג סדרה, משפחה או סוג.')
            return
        if kind != Sample.Kind.GENUS and any(n in self.GENUS_ONLY_FIELDS for n in touched):
            self.add_error(next(n for n in touched if n in self.GENUS_ONLY_FIELDS), 'קובץ זיהוי, כיתוב ומקור זמינים רק בסוג.')
            return
        if self.taxon_for(kind, data.get('order') or '', data.get('family') or '', data.get('genus') or '') is None:
            self.add_error(touched[0], 'לא נמצאה שורה בטבלת הטקסונומיה לסדרה/משפחה/סוג שנבחרו — יש להוסיף אותה בניהול.')

    def save_taxon_files(self, sample):
        """After the sample is saved: store/clear the order/family/genus files submitted with it."""
        if 'taxon_article_pdf' not in self.fields or sample.kind not in self.TAXON_KINDS:
            return None
        taxon = self.taxon_for(sample.kind, sample.order, sample.family, sample.genus)
        if taxon is None:
            return None
        changed = []
        def apply(attr, field):
            if field not in self.changed_data:
                return
            value = self.cleaned_data.get(field)
            current = getattr(taxon, attr)
            if current:
                current.delete(save=False)
            if value:
                setattr(taxon, attr, value)
            changed.append(attr)
        apply('article_pdf', 'taxon_article_pdf')
        for attr, _label, _rows in self.TAXON_TEXT_FIELDS:
            if 'taxon_' + attr in self.changed_data:
                setattr(taxon, attr, self.cleaned_data.get('taxon_' + attr) or '')
                changed.append(attr)
        if sample.kind == Sample.Kind.GENUS:
            apply('identification_file', 'taxon_identification_file')
            for attr, field in (('identification_caption', 'taxon_identification_caption'), ('identification_caption_en', 'taxon_identification_caption_en'),
                            ('identification_source', 'taxon_identification_source')):
                if field in self.changed_data:
                    setattr(taxon, attr, self.cleaned_data.get(field) or '')
                    changed.append(attr)
        if changed:
            taxon.save(update_fields=changed)
        return taxon

    def enable_add_links(self):
        """Show an "add a value" link next to the two reference-table selects (managers only --
        the tables are edited in the admin)."""
        for name, model in (('identification_qualifier', 'identificationqualifier'), ('life_stage', 'lifestage')):
            self.fields[name].widget.add_url = reverse(f'admin:observations_{model}_add')
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
        if data['kind'] in (Sample.Kind.ORDER, Sample.Kind.FAMILY, Sample.Kind.GENUS):
            # A taxon-level sample is identified by its order / family / genus field; a species
            # (or "other species") left over from switching kinds does not apply.
            species_text = other_text = ''
            data['species_other'] = ''
        # instance.undetermined_variant only ever comes from the catalog-match branch
        # below -- reset it up front so a switch to species_other, or clearing the
        # field, drops any letter left over from a previous edit of this instance.
        self.instance.undetermined_variant = ''
        if other_text:
            data['species'] = None
            data['species_other'] = other_text
        elif species_text:
            match, variant = resolve_species(data.get('genus'), species_text)
            if match:
                data['species'] = match
                data['species_other'] = ''
                self.instance.undetermined_variant = variant
            else:
                self.add_error('species', 'לא נמצא מין תואם ברשימה (ביחד עם הסוג שנבחר). יש לבחור מין קיים, או למלא "מין אחר".')
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
        self.clean_taxon_files(data)
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


class SampleChangelistForm(forms.ModelForm):
    """The inline-editable columns of the Samples admin list (like the Species list): order,
    family, genus and species (epithet only) plus the cf./aff. and juv. markers. The species
    column is looked up through genus + epithet exactly like the observation form does; only a
    SPECIES-kind sample has one."""
    species = forms.CharField(label='מין', required=False, widget=forms.TextInput(attrs={'size': 12, 'list': 'sample-species-options', 'autocomplete': 'off'}))
    identification_qualifier = forms.ChoiceField(label='סימון זהות', required=False,
        choices=lambda: [('', '—')] + [(r.code, r.code) for r in IdentificationQualifier.objects.all()])
    life_stage = forms.ChoiceField(label='שלב חיים', required=False,
        choices=lambda: [('', '—')] + [(r.code, r.code) for r in LifeStage.objects.all()])
    class Meta:
        model = Sample
        fields = ['order', 'family', 'genus', 'species', 'identification_qualifier', 'life_stage']
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk: self.initial['species'] = species_epithet_with_variant(self.instance)
    def clean(self):
        data = super().clean()
        if self.instance.kind != Sample.Kind.SPECIES:
            data['species'] = None
            return data
        text = (data.get('species') or '').strip()
        if text:
            match, variant = resolve_species(data.get('genus'), text)
            if match:
                data['species'] = match
                self.instance.undetermined_variant = variant
            else:
                self.add_error('species', 'לא נמצא מין תואם ברשימה (ביחד עם הסוג).')
                data['species'] = None
        else:
            data['species'] = None
            self.instance.undetermined_variant = ''
        return data


class DiveTripForm(forms.ModelForm):
    country = forms.ChoiceField(label='מדינה')
    region = forms.ChoiceField(label='אזור')
    class Meta:
        model = DiveTrip
        fields = ['title','country','region','year','month','start_day','duration_days','reserve']
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
