import calendar
import hashlib
import re
import uuid
from datetime import date
from urllib.parse import urlparse, parse_qs
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator, FileExtensionValidator, RegexValidator
from django.db import models, transaction
from django.utils import timezone
from django.utils.text import slugify


def normalize_sp_spacing(text):
    """Canonicalize the space between an sp./spp. qualifier and its number or single-letter
    variant marker, so 'Tenellia sp.18'/'Tenellia sp. 18' and 'Coryphellina sp.A'/
    'Coryphellina sp. A' each compare equal -- photographers' filenames and the species
    table don't always agree on whether there's a space there. The letter case stays
    case-SENSITIVE (unlike the "sp."/"spp." word itself) so an ordinary lowercase
    continuation like "sp.aff" is never mistaken for a variant marker (see
    Sample.undetermined_variant/SpeciesArea.undetermined_variant for what the marker means)."""
    return re.sub(r'\b((?i:spp?\.))\s*(\d|[A-Z](?![A-Za-z]))', r'\1 \2', text or '')


UNDETERMINED_VARIANT_RE = re.compile(r'\b((?i:spp?\.))\s([A-Z])(?![A-Za-z])')


def split_undetermined_variant(text):
    """Split off a photographer's ad hoc A/B/C... undetermined-species marker (immediately
    following an sp./spp. qualifier, e.g. 'Coryphellina sp. A') from `text`, returning
    (text_without_the_marker, the_marker) -- or (text, '') when there is none. The marker
    can be followed by further text (an author citation, a qualifier...), exactly like the
    bare "sp." qualifier itself can be, since it only marks which physical, still-undescribed
    form of the genus this observation is -- it is not part of the catalogued scientific
    name (see Sample.undetermined_variant / SpeciesArea.undetermined_variant)."""
    normalized_text = normalize_sp_spacing(text or '').strip()
    match = UNDETERMINED_VARIANT_RE.search(normalized_text)
    if not match:
        return normalized_text, ''
    stripped = normalized_text[:match.start()] + match.group(1) + normalized_text[match.end():]
    return stripped.strip(), match.group(2)


def youtube_id(url):
    p = urlparse(url)
    host = (p.hostname or '').lower()
    if p.scheme != 'https' or host not in {'youtube.com','www.youtube.com','m.youtube.com','youtu.be'}:
        raise ValidationError('יש להזין קישור HTTPS לסרטון YouTube.')
    parts = p.path.strip('/').split('/')
    value = parts[0] if host == 'youtu.be' else (parse_qs(p.query).get('v', [''])[0] if p.path == '/watch' else (parts[1] if len(parts) == 2 and parts[0] in {'shorts','embed','live'} else ''))
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', value):
        raise ValidationError('קישור הסרטון אינו תקין.')
    return value


class Named(models.Model):
    name = models.CharField('שם בעברית', max_length=180)
    name_en = models.CharField('שם באנגלית', max_length=180, blank=True)
    class Meta:
        abstract = True
        ordering = ['name']
    def __str__(self): return self.name


class Country(Named):
    class Meta(Named.Meta): verbose_name = 'מדינה'; verbose_name_plural = 'מדינות'


class Sea(Named):
    class Meta(Named.Meta): verbose_name = 'ים'; verbose_name_plural = 'ימים'


class Region(Named):
    country = models.ForeignKey(Country, on_delete=models.PROTECT, verbose_name='מדינה')
    sea = models.ForeignKey(Sea, on_delete=models.PROTECT, verbose_name='ים')
    trip_code = models.CharField('אות/ות האזור בסימון מסעות', max_length=6, blank=True,
        help_text='משמשת בסימון המסע (למשל I26Aug). אם נשאר ריק, נקבעת אוטומטית בהוספת המסע הראשון באזור.')
    class Meta(Named.Meta): verbose_name = 'אזור'; verbose_name_plural = 'אזורים'
    def clean(self):
        super().clean()
        if self.trip_code and Region.objects.filter(trip_code=self.trip_code).exclude(pk=self.pk).exists():
            raise ValidationError({'trip_code': 'האות/ות האלה כבר משמשות אזור אחר.'})


class Site(Named):
    region = models.ForeignKey(Region, on_delete=models.PROTECT, verbose_name='אזור')
    class Meta(Named.Meta): verbose_name = 'אתר צלילה'; verbose_name_plural = 'אתרי צלילה'


class Species(models.Model):
    # DERIVED -- never typed: always "<genus> <species>" (see sync_scientific_name). genus,
    # species (the epithet, which may also carry an open-nomenclature qualifier such as
    # "cf. strigata" or "sp. 7") and author are the authoritative fields. Kept as a stored,
    # indexed column because it is the natural key for lookups, transfers and filenames.
    scientific_name = models.CharField('שם מדעי (נגזר מסוג + מין)', max_length=200, db_index=True, editable=False)
    name_he = models.CharField('שם בעברית', max_length=200, blank=True)
    name_en = models.CharField('שם באנגלית', max_length=200, blank=True)
    source_id = models.CharField('מזהה מקור לייבוא', max_length=200, blank=True, editable=False)
    genus = models.TextField('Genus — סוג', blank=True)
    species = models.TextField('Species — שם המין', blank=True)
    author = models.TextField('Author — מחבר ושנת תיאור', blank=True)
    order = models.TextField('Order — סדרה', blank=True)
    family = models.TextField('Family — משפחה', blank=True)
    superfamily = models.TextField('Superfamily — על־משפחה', blank=True)
    accepted_genus = models.TextField('Accepted genus — סוג מקובל', blank=True)
    accepted_species = models.TextField('Accepted species — מין מקובל', blank=True)
    common_name = models.TextField('Common name — שם נפוץ', blank=True)
    transliteration = models.TextField('Transliteration — תעתיק', blank=True)
    language = models.TextField('Language — שפה', blank=True)
    formatted_author = models.TextField('Formatted author — מחבר מעוצב', blank=True)
    distribution = models.TextField('Distribution — תפוצה', blank=True)
    phylogenetic_order = models.CharField('סדר אבולוציוני', max_length=40, blank=True)
    full_species_name_with_order = models.TextField('שם מלא עם סדר — מהאקסל', blank=True)
    reference_author = models.TextField('מחבר נוסף / מקור זיהוי — Author באקסל', blank=True)
    # Content for the upcoming per-species page (not from the import spreadsheet -- entered by hand).
    habitat = models.TextField('בית גידול', blank=True)
    food = models.TextField('מזון', blank=True)
    is_migrant = models.BooleanField('מין מהגר', default=False)
    first_observed_year = models.PositiveSmallIntegerField('שנת תצפית ראשונה', null=True, blank=True, validators=[MinValueValidator(1900)])
    last_observed_year = models.PositiveSmallIntegerField('שנת תצפית אחרונה', null=True, blank=True, validators=[MinValueValidator(1900)])
    # A typical size range (size_from/size_to) plus, separately, the largest individual
    # actually observed (size_max, which may exceed the typical range) -- see size_text()
    # below for how these three combine into the sentence shown on the species page.
    size_from = models.DecimalField('גודל אופייני מינימלי (מ״מ)', max_digits=6, decimal_places=1, null=True, blank=True, validators=[MinValueValidator(0)])
    size_to = models.DecimalField('גודל אופייני מקסימלי (מ״מ)', max_digits=6, decimal_places=1, null=True, blank=True, validators=[MinValueValidator(0)])
    size_max = models.DecimalField('גודל מקסימלי שנצפה (מ״מ)', max_digits=6, decimal_places=1, null=True, blank=True, validators=[MinValueValidator(0)])
    description_he = models.TextField('תיאור בעברית', blank=True)
    description_en = models.TextField('תיאור באנגלית', blank=True)
    link = models.URLField('קישור', blank=True)
    # For the site manager only (admin table): a page to glance at what the species looks like --
    # an iNaturalist taxon page with photos when one exists, otherwise its WoRMS page. Never shown
    # on the public site; filled by the fill_reference_links command and editable by hand.
    reference_link = models.URLField('קישור עזר (תמונה / WoRMS)', max_length=300, blank=True)
    article_pdf = models.FileField('מאמר (PDF)', upload_to='articles/species/', blank=True, validators=[FileExtensionValidator(['pdf'])])
    # Species-page content in both languages. habitat / food above hold the Hebrew text;
    # their English counterparts are habitat_en / food_en.
    habitat_en = models.TextField('בית גידול (אנגלית)', blank=True)
    food_en = models.TextField('מזון (אנגלית)', blank=True)
    identification_he = models.TextField('סימני זיהוי', blank=True)
    identification_en = models.TextField('סימני זיהוי (אנגלית)', blank=True)
    similar_species_he = models.TextField('מינים דומים', blank=True)
    similar_species_en = models.TextField('מינים דומים (אנגלית)', blank=True)
    native_range_he = models.TextField('תפוצה מקורית', blank=True)
    native_range_en = models.TextField('תפוצה מקורית (אנגלית)', blank=True)
    depth_min = models.PositiveSmallIntegerField('עומק מינימלי (מ׳)', null=True, blank=True)
    depth_max = models.PositiveSmallIntegerField('עומק מקסימלי (מ׳)', null=True, blank=True)
    # Migrant species: how and where it was recorded in the Mediterranean (the years are
    # first_observed_year / last_observed_year above).
    introduction_route_he = models.CharField('דרך ההגעה לים התיכון', max_length=200, blank=True)
    introduction_route_en = models.CharField('דרך ההגעה לים התיכון (אנגלית)', max_length=200, blank=True)
    med_status_he = models.CharField('מעמד בים התיכון', max_length=200, blank=True)
    med_status_en = models.CharField('מעמד בים התיכון (אנגלית)', max_length=200, blank=True)
    first_record_place_he = models.CharField('מקום התצפית הראשונה', max_length=200, blank=True)
    first_record_place_en = models.CharField('מקום התצפית הראשונה (אנגלית)', max_length=200, blank=True)
    last_record_place_he = models.CharField('מקום התצפית האחרונה', max_length=200, blank=True)
    last_record_place_en = models.CharField('מקום התצפית האחרונה (אנגלית)', max_length=200, blank=True)
    sources = models.TextField('מקורות (קישור בכל שורה)', blank=True)
    class Meta:
        ordering = [models.functions.NullIf('phylogenetic_order', models.Value('')).asc(nulls_last=True), 'scientific_name']
        verbose_name = 'מין'; verbose_name_plural = 'מינים'
    def __str__(self): return self.scientific_name
    def sync_scientific_name(self):
        """genus + species are authoritative: when both are set the scientific name is exactly
        "<genus> <species>". Compatibility for callers that only know a full name (importers
        reading filenames, the species catalog): when genus AND species are both blank they are
        split out of scientific_name (first word = genus, the rest = species); a name given
        with only one of the two is kept as typed."""
        genus, epithet = (self.genus or '').strip(), (self.species or '').strip()
        name = ' '.join((self.scientific_name or '').split())
        if not genus and not epithet and name:
            genus, _, epithet = name.partition(' ')
        if genus and epithet or not name:
            name = f'{genus} {epithet}'.strip()
        self.genus, self.species, self.scientific_name = genus, epithet, name
    @property
    def full_name(self):
        """The scientific name followed by its author and year, e.g.
        "Chromodoris strigata Rudman, 1982" -- read-only, built from the authoritative fields."""
        return f'{self.scientific_name} {(self.author or "").strip()}'.strip()
    def save(self, *args, **kwargs):
        self.sync_scientific_name()
        update_fields = kwargs.get('update_fields')
        if update_fields is not None and ({'genus', 'species'} & set(update_fields)):
            kwargs['update_fields'] = set(update_fields) | {'scientific_name'}
        super().save(*args, **kwargs)
    @classmethod
    def find_by_name(cls, text):
        """Match `text` (typed into the observation form, or extracted from a bulk-import
        filename) against the catalog: an exact case-insensitive match on scientific_name,
        falling back to a spacing-tolerant compare (normalize_sp_spacing) so 'sp.18'/'sp. 18'
        are each recognised as the same species regardless of which spacing the catalog or
        the photographer used. Two undescribed "sp." forms of one genus that the photographer
        wants to tell apart are NOT distinguished here -- see Sample.undetermined_variant /
        SpeciesArea.undetermined_variant, and split_undetermined_variant, for that."""
        text = (text or '').strip()
        if not text:
            return None
        match = cls.objects.filter(scientific_name__iexact=text).first()
        if match:
            return match
        key = normalize_sp_spacing(text).casefold()
        return next((item for item in cls.objects.all() if normalize_sp_spacing(item.scientific_name).casefold() == key), None)
    def clean(self):
        super().clean()
        self.sync_scientific_name()
        errors = {}
        if self.first_observed_year and self.first_observed_year > date.today().year:
            errors['first_observed_year'] = 'שנת תצפית ראשונה אינה יכולה להיות בעתיד.'
        if self.last_observed_year and self.last_observed_year > date.today().year:
            errors['last_observed_year'] = 'שנת תצפית אחרונה אינה יכולה להיות בעתיד.'
        if self.first_observed_year and self.last_observed_year and self.last_observed_year < self.first_observed_year:
            errors['last_observed_year'] = 'שנת תצפית אחרונה אינה יכולה להיות לפני שנת התצפית הראשונה.'
        if self.size_from is not None and self.size_to is not None and self.size_to < self.size_from:
            errors['size_to'] = 'הגודל המקסימלי האופייני אינו יכול להיות קטן מהגודל המינימלי האופייני.'
        largest_typical = self.size_to if self.size_to is not None else self.size_from
        if self.size_max is not None and largest_typical is not None and self.size_max < largest_typical:
            errors['size_max'] = 'הגודל המקסימלי שנצפה אינו יכול להיות קטן מהגודל האופייני.'
        if errors: raise ValidationError(errors)

    def size_text(self, lang='he'):
        """The species page's size sentence, built from size_from/size_to (a typical size
        range) and size_max (the largest individual actually observed, which may exceed
        that range) -- fully resolved here in Python rather than through the seaslugs_i18n
        `t` filter, since that filter is a static string lookup and can't parametrize a
        dynamic, numeric sentence like this one. Returns '' when none of the three fields
        are set (nothing to show on the page)."""
        def fmt(value):
            if value == value.to_integral_value():
                return str(int(value))
            return str(value.normalize())
        if self.size_from is not None and self.size_to is not None:
            range_text = (f'מ- {fmt(self.size_from)}מ״מ עד {fmt(self.size_to)}מ״מ' if lang != 'en'
                          else f'from {fmt(self.size_from)}mm to {fmt(self.size_to)}mm')
        elif self.size_from is not None or self.size_to is not None:
            only = self.size_from if self.size_from is not None else self.size_to
            range_text = f'{fmt(only)}מ״מ' if lang != 'en' else f'{fmt(only)}mm'
        else:
            range_text = ''
        max_text = ''
        if self.size_max is not None:
            max_text = (f'גודל מקסימלי שנצפה {fmt(self.size_max)}מ״מ' if lang != 'en'
                       else f'maximum observed size {fmt(self.size_max)}mm')
        if not range_text and not max_text:
            return ''
        label = 'גודל: ' if lang != 'en' else 'Size: '
        if range_text and max_text:
            return f'{label}{range_text} {max_text}.'
        if range_text:
            return f'{label}{range_text}.'
        return f'{max_text[0].upper()}{max_text[1:]}.' if lang == 'en' else f'{max_text}.'


class TaxonOrder(models.Model):
    # name is NOT unique on its own: a single order (e.g. "Nudibranchia") can have several rows,
    # one per sub_order -- and even the same (name, sub_order) pair can repeat across several
    # informal groups (e.g. Nudibranchia/Doridina covers both "cryptobranch" and "radula-less"
    # dorids), disambiguated by taxonomic_order. build_taxonomy_tables seeds/updates these rows
    # from the curated taxon_order_reference list in the supplement JSON; it never overwrites a
    # value the user has since edited by hand in admin.
    name = models.CharField('סדרה', max_length=150)
    name_he = models.CharField('שם בעברית', max_length=150, blank=True)
    name_en = models.CharField('שם באנגלית', max_length=150, blank=True)
    sub_order = models.CharField('תת-סדרה', max_length=150, blank=True)
    taxonomic_order = models.CharField('סדר טקסונומי', max_length=40, blank=True)
    defining_sample = models.ForeignKey('Sample', null=True, blank=True, on_delete=models.SET_NULL, related_name='+', verbose_name='דגימה מגדירה',
        help_text='הדגימה שתמונתה או סרטון היוטיוב שלה יוצגו בכותרת הסדרה בגלריה.')
    description_he = models.TextField('תיאור בעברית', blank=True)
    description_en = models.TextField('תיאור באנגלית', blank=True)
    identification_he = models.TextField('סימני זיהוי', blank=True)
    identification_en = models.TextField('סימני זיהוי (אנגלית)', blank=True)
    sources = models.TextField('מקורות (קישור בכל שורה)', blank=True)
    link = models.URLField('קישור', blank=True)
    article_pdf = models.FileField('מאמר (PDF)', upload_to='articles/orders/', blank=True, validators=[FileExtensionValidator(['pdf'])])
    class Meta:
        ordering = [models.functions.NullIf('taxonomic_order', models.Value('')).asc(nulls_last=True), 'name', 'sub_order']
        verbose_name = 'סדרה (טקסונומיה)'
        verbose_name_plural = 'סדרות (טקסונומיה)'
        # (name, sub_order) is no longer unique on its own: the real classification has cases
        # (e.g. Nudibranchia/Doridina, Nudibranchia/Cladobranchia) where the SAME name+sub_order
        # pair legitimately covers several distinct informal groups, disambiguated only by
        # taxonomic_order (see build_taxonomy_tables' taxon_order_reference seeding).
        constraints = [models.UniqueConstraint(fields=['name', 'sub_order', 'taxonomic_order'], name='unique_taxonorder_name_sub_order_taxonomic_order')]
    def __str__(self): return f'{self.name} ({self.sub_order})' if self.sub_order else self.name
    @property
    def display_sub_order(self):
        """The sub-order the gallery and the admin filters show. The phanerobranch dorids' row
        ("גלויי זים", Nudibranchia #3) is the order's blank-sub_order *base* row that
        build_taxonomy_tables and the resolver rely on, so it must stay blank in the database --
        but its species are Doridina, so they are shown there."""
        if not self.sub_order and self.name == 'Nudibranchia' and self.taxonomic_order == '3':
            return 'Doridina'
        return self.sub_order


class TaxonFamily(models.Model):
    # Same pattern as TaxonOrder.name: name is not unique alone, so a family can have several
    # rows, one per sub_family. (name, sub_family) is the unique pair.
    order = models.ForeignKey(TaxonOrder, on_delete=models.PROTECT, null=True, blank=True, related_name='families', verbose_name='סדרה')
    name = models.CharField('משפחה', max_length=150)
    name_he = models.CharField('שם בעברית', max_length=150, blank=True)
    name_en = models.CharField('שם באנגלית', max_length=150, blank=True)
    sub_family = models.CharField('תת-משפחה', max_length=150, blank=True)
    superfamily = models.CharField('על-משפחה', max_length=150, blank=True)
    taxonomic_order = models.CharField('סדר טקסונומי', max_length=40, blank=True)
    defining_sample = models.ForeignKey('Sample', null=True, blank=True, on_delete=models.SET_NULL, related_name='+', verbose_name='דגימה מגדירה',
        help_text='הדגימה שתמונתה או סרטון היוטיוב שלה יוצגו בכותרת המשפחה בגלריה.')
    description_he = models.TextField('תיאור בעברית', blank=True)
    description_en = models.TextField('תיאור באנגלית', blank=True)
    identification_he = models.TextField('סימני זיהוי', blank=True)
    identification_en = models.TextField('סימני זיהוי (אנגלית)', blank=True)
    sources = models.TextField('מקורות (קישור בכל שורה)', blank=True)
    link = models.URLField('קישור', blank=True)
    article_pdf = models.FileField('מאמר (PDF)', upload_to='articles/families/', blank=True, validators=[FileExtensionValidator(['pdf'])])
    class Meta:
        ordering = [models.functions.NullIf('taxonomic_order', models.Value('')).asc(nulls_last=True), 'name', 'sub_family']
        verbose_name = 'משפחה (טקסונומיה)'
        verbose_name_plural = 'משפחות (טקסונומיה)'
        constraints = [models.UniqueConstraint(fields=['name', 'sub_family'], name='unique_taxonfamily_name_sub_family')]
    def __str__(self): return f'{self.name} ({self.sub_family})' if self.sub_family else self.name


IDENTIFICATION_FILE_EXTENSIONS = ['pdf', 'jpg', 'jpeg', 'png', 'webp', 'gif']
IDENTIFICATION_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp', 'gif'}
IDENTIFICATION_FILE_MAX_BYTES = 15 * 1024 * 1024


def validate_identification_file_size(value):
    # Also runs against an already-stored file when a genus is re-saved; if that file is
    # missing from disk (e.g. after a database replace) the check must not break the save.
    try:
        size = value.size
    except (OSError, ValueError):
        return
    if size > IDENTIFICATION_FILE_MAX_BYTES:
        raise ValidationError('קובץ הזיהוי גדול מדי (עד 15MB).')


class TaxonGenus(models.Model):
    family = models.ForeignKey(TaxonFamily, on_delete=models.PROTECT, null=True, blank=True, related_name='genera', verbose_name='משפחה')
    name = models.CharField('סוג', max_length=150, unique=True)
    name_he = models.CharField('שם בעברית', max_length=150, blank=True)
    name_en = models.CharField('שם באנגלית', max_length=150, blank=True)
    taxonomic_order = models.CharField('סדר טקסונומי', max_length=40, blank=True)
    defining_sample = models.ForeignKey('Sample', null=True, blank=True, on_delete=models.SET_NULL, related_name='+', verbose_name='דגימה מגדירה',
        help_text='הדגימה שתמונתה או סרטון היוטיוב שלה יוצגו בכותרת הסוג ובאוסף המינים שלו בגלריה.')
    description_he = models.TextField('תיאור בעברית', blank=True)
    description_en = models.TextField('תיאור באנגלית', blank=True)
    identification_he = models.TextField('סימני זיהוי', blank=True)
    identification_en = models.TextField('סימני זיהוי (אנגלית)', blank=True)
    sources = models.TextField('מקורות (קישור בכל שורה)', blank=True)
    link = models.URLField('קישור', blank=True)
    article_pdf = models.FileField('מאמר (PDF)', upload_to='articles/genera/', blank=True, validators=[FileExtensionValidator(['pdf'])])
    # One scientific identification file for the genus -- a diagram, plate of photos or key
    # for telling its species apart: a PDF or an image (see IDENTIFICATION_FILE_EXTENSIONS).
    identification_file = models.FileField('קובץ זיהוי (PDF או תמונה)', upload_to='identification/genera/', blank=True,
        validators=[FileExtensionValidator(IDENTIFICATION_FILE_EXTENSIONS), validate_identification_file_size],
        help_text='תרשים, לוח תמונות או מפתח לזיהוי המינים בסוג: PDF או תמונה (JPG, PNG, WebP, GIF), עד 15MB.')
    identification_caption = models.CharField('כיתוב לקובץ הזיהוי', max_length=300, blank=True)
    identification_caption_en = models.CharField('כיתוב לקובץ הזיהוי (אנגלית)', max_length=300, blank=True)
    identification_source = models.CharField('מקור קובץ הזיהוי', max_length=300, blank=True,
        help_text='למשל: שם המחבר, הספר או המאמר שממנו נלקח התרשים.')
    class Meta:
        ordering = [models.functions.NullIf('taxonomic_order', models.Value('')).asc(nulls_last=True), 'name']
        verbose_name = 'סוג (טקסונומיה)'
        verbose_name_plural = 'סוגים (טקסונומיה)'
    def __str__(self): return self.name
    @property
    def identification_is_image(self):
        name = self.identification_file.name if self.identification_file else ''
        return name.rsplit('.', 1)[-1].lower() in IDENTIFICATION_IMAGE_EXTENSIONS
    @staticmethod
    def pick_defining_sample(name):
        """Best genus-kind sample to represent a genus by this exact name: prefer one with
        an uploaded image over a video-only one, only among published/non-deleted genus-kind
        samples identifying this genus, tie-broken by whichever was created first. Same
        algorithm as SpeciesArea.pick_defining_sample above and the assign_genus_defining_
        samples management command's own copy (kept separate on purpose -- see gallery_data.
        py's note on this codebase's convention of small local copies over cross-module
        coupling for this kind of picking logic)."""
        candidates = list(Sample.objects.filter(
            kind=Sample.Kind.GENUS, genus=name, status=Sample.Status.PUBLISHED, deleted_at__isnull=True,
        ).order_by('created_at', 'pk'))
        candidates = [c for c in candidates if c.image or c.video_url]
        if not candidates:
            return None
        with_image = [c for c in candidates if c.image]
        return (with_image or candidates)[0]


def taxon_kind_defining_sample(kind, name):
    """Best published FAMILY- or ORDER-kind sample for the taxon of this name: one with an
    uploaded image over a video-only one, oldest first -- the same rule as
    TaxonGenus.pick_defining_sample."""
    field = 'family' if kind == Sample.Kind.FAMILY else 'order'
    candidates = [c for c in Sample.objects.filter(
        kind=kind, **{field: name}, status=Sample.Status.PUBLISHED, deleted_at__isnull=True,
    ).order_by('created_at', 'pk') if c.image or c.video_url]
    with_image = [c for c in candidates if c.image]
    return (with_image or candidates or [None])[0]


class SiteImage(models.Model):
    key = models.SlugField('מזהה', max_length=50, unique=True)
    image = models.ImageField('תמונה', upload_to='site/')
    updated_at = models.DateTimeField('עודכן', auto_now=True)
    class Meta:
        verbose_name = 'תמונת אתר'; verbose_name_plural = 'תמונות אתר'
    def __str__(self): return self.key


class HomeText(models.Model):
    """A home-page text edited on the edit screen (views.home_text_edit): one row per section and language,
    replacing the default wording of observations/home_defaults.py. No row = the default."""
    key = models.CharField('מזהה', max_length=40)
    lang = models.CharField('שפה', max_length=2)
    content = models.TextField('תוכן')
    updated_at = models.DateTimeField('עודכן', auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['key', 'lang'], name='unique_home_text')]
        verbose_name = 'טקסט בדף הבית'; verbose_name_plural = 'טקסטים בדף הבית'
    def __str__(self): return f'{self.key} ({self.lang})'


PHONE_VALIDATOR = RegexValidator(r'^[0-9+\-()\s]{5,30}$', 'מספר טלפון לא תקין.')


class Profile(models.Model):
    """The Hebrew name (first/last) lives on the built-in User model itself
    (user.first_name / user.last_name) -- these are only the English counterparts,
    since not every user has (or needs) an English name on file. See
    given_name_for/full_name_for below for how the two languages combine for display."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    first_name_en = models.CharField('שם פרטי באנגלית', max_length=150, blank=True)
    last_name_en = models.CharField('שם משפחה באנגלית', max_length=150, blank=True)
    phone = models.CharField('טלפון', max_length=30, blank=True, validators=[PHONE_VALIDATOR])
    macro_diver = models.BooleanField('מעוניין במציאת שותפים לצלילת מאקרו', default=False)
    visible_to_members = models.BooleanField('הצגת הפרופיל למשתמשים רשומים', default=False)
    regions = models.ManyToManyField(Region, blank=True, verbose_name='אזורי צלילה')
    countries = models.ManyToManyField(Country, blank=True, verbose_name='מדינות צלילה')
    bio = models.TextField('על עצמי', blank=True, max_length=1500)
    trip_code = models.CharField('אות הצלם בסימון מסעות', max_length=4, blank=True,
        help_text='האות שמופיעה בתחילת סימון מסע של הצלם. ריק = בלי אות (בעל האתר).')
    class Meta: verbose_name = 'פרופיל'; verbose_name_plural = 'פרופילים'
    def __str__(self): return self.user.get_full_name() or self.user.username


def given_name_for(user, lang):
    """The name to greet someone by (first name only): the Hebrew first name on
    their account in Hebrew mode, their profile's English first name in English
    mode -- each mode falling back to whichever language is actually set, since
    a user is not required to have both."""
    profile = getattr(user, 'profile', None)
    he_first = (user.first_name or '').strip()
    en_first = (profile.first_name_en.strip() if profile and profile.first_name_en else '')
    return (en_first or he_first) if lang == 'en' else (he_first or en_first)


def full_name_for(user, lang):
    """The full name to credit someone by (e.g. a photographer credit): same
    language preference and fallback as given_name_for, but first+last together."""
    profile = getattr(user, 'profile', None)
    he_full = user.get_full_name().strip()
    en_full = ''
    if profile:
        en_full = f'{profile.first_name_en} {profile.last_name_en}'.strip()
    return (en_full or he_full) if lang == 'en' else (he_full or en_full)


class DiveTrip(models.Model):
    class Kind(models.TextChoices):
        DIVE = 'dive', 'מסע צלילה'
        THEMATIC = 'thematic', 'אוסף נושאי'
    code = models.CharField('קוד מסע', max_length=40, unique=True, default=uuid.uuid4)
    kind = models.CharField('סוג המסע', max_length=20, choices=Kind.choices, default=Kind.DIVE,
        help_text='מסע צלילה רגיל, לעומת אוסף נושאי של מינים (למשל מינים מהגרים לספסיאניים) שאינו בהכרח צלילה בודדת.')
    title = models.CharField('שם המסע', max_length=400)
    source_sort = models.CharField('מיון במקור', max_length=100, blank=True)
    year = models.PositiveSmallIntegerField('שנה', null=True, blank=True, validators=[MinValueValidator(1900)])
    month = models.PositiveSmallIntegerField('חודש', null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(12)])
    start_day = models.PositiveSmallIntegerField('יום התחלה', null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(31)])
    duration_days = models.PositiveSmallIntegerField('מספר ימים', null=True, blank=True, validators=[MinValueValidator(1)])
    country_name = models.CharField('מדינה כפי שנרשמה במקור', max_length=180, blank=True)
    region_name = models.CharField('אזור כפי שנרשם במקור', max_length=180, blank=True)
    sea_name = models.CharField('ים כפי שנרשם במקור', max_length=180, blank=True)
    country = models.ForeignKey(Country, null=True, blank=True, on_delete=models.PROTECT, verbose_name='מדינה', related_name='dive_trips')
    region = models.ForeignKey(Region, null=True, blank=True, on_delete=models.PROTECT, verbose_name='אזור', related_name='dive_trips')
    reserve = models.CharField('שמורה / אתר (טקסט חופשי)', max_length=180, blank=True)
    # Reuses the existing Site table (already has the full country/region/sea hierarchy)
    # instead of a separate Reserve lookup table. The admin's cascading filter only lets you
    # pick a site that belongs to the trip's own region -- see divetrip_admin.js.
    site = models.ForeignKey(Site, null=True, blank=True, on_delete=models.PROTECT, verbose_name='שמורה / אתר', related_name='dive_trips')
    species_count = models.PositiveIntegerField('מספר מינים שנצפו במסע', null=True, blank=True, help_text='מספר מדווח לכל המסע; אינו מספר הסרטונים באתר. השאר ריק אם אינו ידוע.')
    source_metadata = models.JSONField(default=dict, blank=True)
    description_he = models.TextField('תיאור בעברית', blank=True)
    description_en = models.TextField('תיאור באנגלית', blank=True)
    link = models.URLField('קישור', blank=True)
    article_pdf = models.FileField('מאמר (PDF)', upload_to='articles/trips/', blank=True, validators=[FileExtensionValidator(['pdf'])])

    class Meta:
        db_table = 'dive_trips'
        ordering = ['-year', '-month', 'title']
        verbose_name = 'מסע צלילה'
        verbose_name_plural = 'מסעות צלילה'

    def __str__(self): return f'{self.title} [{self.code}]'

    @property
    def display_species_count(self):
        """Number of distinct species actually visible on the public site when this trip's
        collection is opened (published, non-deleted, real samples only). Always computed
        live from the gallery data -- the self-reported species_count field above is kept
        only as a reference value from the source spreadsheet and is never shown on the site."""
        return self.samples.filter(
            kind='species', status='published', deleted_at__isnull=True, species__isnull=False,
            species_other='', site_other='',
        ).order_by().values('species_id').distinct().count()

    # A trip has no sea of its own: the sea is its region's sea (Region.sea is the single
    # source of truth). A trip without a region (e.g. a thematic collection not tied to one
    # place) is simply in no sea.
    @property
    def sea(self):
        return self.region.sea if self.region_id else None

    @property
    def sea_id(self):
        return self.region.sea_id if self.region_id else None

    def clean(self):
        super().clean()
        if self.year and self.year > date.today().year:
            raise ValidationError({'year': 'השנה אינה יכולה להיות בעתיד.'})
        if self.start_day:
            if not self.year or not self.month: raise ValidationError({'start_day':'יום התחלה מחייב שנה וחודש.'})
            try: date(self.year, self.month, self.start_day)
            except ValueError: raise ValidationError({'start_day':'תאריך התחלה לא תקין.'})


class SampleKind(Named):
    """Bilingual reference table describing the values Sample.kind can hold. Sample.kind stays
    a plain CharField (not a real FK here) on purpose: it is compared to plain strings and the
    Kind.* constants in ~25 places across views/forms/admin/management commands/tests and the
    public gallery API, so converting it to a ForeignKey would touch all of those. This table
    exists to give each kind an admin-editable, bilingual label."""
    code = models.SlugField('קוד', max_length=20, unique=True)
    class Meta(Named.Meta):
        verbose_name = 'סוג דגימה'
        verbose_name_plural = 'סוגי דגימה'


class CodedReference(Named):
    """Reference table of short abbreviations used on samples: `code` is the abbreviation as
    shown after/within the name ("cf.", "juv."), `name`/`name_en` explain it. Admin-editable, so
    new values are added there."""
    code = models.CharField('קיצור', max_length=8, unique=True)
    class Meta(Named.Meta):
        abstract = True
        ordering = ['code']
    def __str__(self): return f'{self.code} — {self.name}' if self.name else self.code


class IdentificationQualifier(CodedReference):
    """Open-nomenclature qualifiers for an observation's identification: cf. ("compare with"),
    aff. ("close to")... shown between the genus and the species. See Sample.identification_qualifier."""
    class Meta(CodedReference.Meta):
        verbose_name = 'סימון זהות לא ודאית'
        verbose_name_plural = 'סימוני זהות לא ודאית (cf., aff.)'


class LifeStage(CodedReference):
    """Life stage of the observed animal: juv. (juvenile)... shown after the name. See Sample.life_stage."""
    class Meta(CodedReference.Meta):
        verbose_name = 'שלב חיים'
        verbose_name_plural = 'שלבי חיים (juv.)'


# English fallback labels for Sample.Kind, used both to seed/refresh SampleKind (the
# admin-editable bilingual reference table -- see build_taxonomy_tables) and, in views.py,
# as a fallback for the observations listing's English mode when that table is empty
# (e.g. a fresh install that hasn't run the management command yet).
KIND_EN_NAMES = {
    'species': 'Species',
    'collection': 'Collection (dive trip)',
    'genus': 'Genus',
    'family': 'Family',
    'order': 'Order',
}



class Sample(models.Model):
    class Kind(models.TextChoices):
        SPECIES = 'species', 'מין יחיד'
        COLLECTION = 'collection', 'אוסף מינים / מסע צלילה'
        GENUS = 'genus', 'סוג'
        FAMILY = 'family', 'משפחה'
        ORDER = 'order', 'סדרה'
    kind = models.CharField('סוג הסרטון', max_length=20, choices=Kind.choices, default=Kind.SPECIES)
    # Required for every kind except an order/family/genus observation (see clean()): those describe a
    # taxon, not a dive, and may have no trip.
    trip = models.ForeignKey(DiveTrip, verbose_name='מסע צלילה', on_delete=models.PROTECT, related_name='samples', null=True, blank=True)
    title = models.CharField('כותרת הגלריה', max_length=240, blank=True)
    gallery_order = models.PositiveIntegerField(default=0)
    source_metadata = models.JSONField(default=dict, blank=True)

    class Status(models.TextChoices):
        PENDING = 'pending', 'ממתינה לאישור'
        PUBLISHED = 'published', 'מפורסמת'
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='observations', verbose_name='יוצר')
    # The observation's taxonomic identification, one field per level. Which of them apply
    # depends on `kind` (see Sample.sync_taxonomy): an ORDER sample has only an order, a FAMILY
    # sample an order+family, a GENUS sample also a genus, a SPECIES sample all four. Higher
    # levels always agree with the lower ones (a genus fixes its family, a family its order).
    # Names are stored as text -- like Species.order/family/genus -- because order and family
    # names are not unique in the taxonomy tables (sub-orders / sub-families).
    order = models.CharField('סדרה', max_length=150, blank=True)
    family = models.CharField('משפחה', max_length=150, blank=True)
    genus = models.CharField('סוג', max_length=150, blank=True)
    species = models.ForeignKey(Species, null=True, blank=True, on_delete=models.PROTECT, verbose_name='מין')
    # Open-nomenclature qualifier shown between genus and species ("Genus cf. species") and a
    # life-stage note shown after the name ("Genus species juv.") -- facts about THIS
    # observation, so they live on the sample rather than on the catalog species. Both hold the
    # abbreviation (the `code`) of a row of the admin-editable reference tables
    # IdentificationQualifier / LifeStage -- new values are added there -- and are checked
    # against them (Sample.sync_taxonomy). Plain strings rather than ForeignKeys for the same
    # reason as Sample.kind (see SampleKind).
    identification_qualifier = models.CharField('סימון זהות לא ודאית', max_length=8, blank=True)
    life_stage = models.CharField('שלב חיים', max_length=8, blank=True)
    site = models.ForeignKey(Site, null=True, blank=True, on_delete=models.PROTECT, verbose_name='אתר צלילה')
    # Only for a SPECIES-kind sample whose species is not (yet) in the species table.
    species_other = models.CharField('מין אחר', max_length=200, blank=True)
    # A genuinely distinct, undescribed species is sometimes only recorded as "Genus sp."
    # in the species catalog (Species), with no way to tell two visibly distinct "sp."
    # forms of one genus apart there. When the photographer has found two (or more) such
    # forms, they mark this observation with a letter (A, B, C...) so it isn't folded
    # together with the other form's observations in the gallery (SpeciesArea is keyed by
    # species+country+sea+this field -- see SpeciesArea.undetermined_variant) -- entered
    # per-observation, not on the catalog itself, since the letters are only meaningful as
    # the photographer's own bookkeeping, not a real taxonomic split of the species (see
    # split_undetermined_variant for how it's recognised from typed/filename text).
    undetermined_variant = models.CharField('סימון מין לא מזוהה (sp.) — א׳/ב׳/A/B וכו׳', max_length=10, blank=True,
        help_text='כשיש כמה מינים שונים מאותו סוג שכולם רשומים כ"sp." ברשימת המינים הרשמית, אפשר לסמן כאן אות '
                   '(A, B, C…) כדי שהאתר לא יאחד את התצפית הזו עם תצפיות של הצורה האחרת מאותו סוג בגלריה.')
    site_other = models.CharField('אתר צלילה אחר', max_length=200, blank=True)
    day = models.PositiveSmallIntegerField('יום', null=True, blank=True, validators=[MinValueValidator(1),MaxValueValidator(31)])
    depth = models.DecimalField('עומק במטרים', max_digits=6, decimal_places=1, null=True, blank=True, validators=[MinValueValidator(0)])
    transfer_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    video_url = models.URLField('קישור YouTube', blank=True, validators=[youtube_id])
    image = models.ImageField('תמונה חלופית (רשות)', upload_to='observations/', blank=True)
    # SHA-256 of the image's bytes (recomputed in clean() whenever an image is present) -- lets
    # clean() detect "this exact photo/video was already entered as a different sample" without
    # caring what storage path/filename it ended up under (uploads that don't go through the
    # content-hash-named storage convention used elsewhere, e.g. a plain admin upload, still get
    # caught).
    image_hash = models.CharField(max_length=64, blank=True, default='', editable=False, db_index=True)
    status = models.CharField('מצב פרסום', choices=Status.choices, default=Status.PENDING, max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    source_id = models.CharField('מזהה מקור לייבוא', max_length=200, blank=True)
    class Meta:
        ordering = ['-created_at']
        db_table = 'samples'
        verbose_name = 'דגימה / תצפית'; verbose_name_plural = 'Samples — דגימות ותצפיות'
    def __str__(self): return f'{self.taxon_name} · {self.trip.year if self.trip_id and self.trip.year else ""}'
    @property
    def taxon_name(self):
        """The name that identifies this observation, taken from the field that matches its
        kind: the title of a collection, the order / family / genus of a taxon-level sample, the
        species (or the not-yet-catalogued 'other' species) of a species sample. This is also
        the identifying part of the image's file name."""
        if self.kind == self.Kind.COLLECTION: return self.title
        if self.kind == self.Kind.ORDER: return self.order
        if self.kind == self.Kind.FAMILY: return self.family
        if self.kind == self.Kind.GENUS: return self.genus
        return str(self.species) if self.species_id else self.species_other
    def taxon_parts(self):
        """(name, author, life stage) -- the three pieces taxon_full_name joins; the author is
        only ever non-empty for a catalogued species."""
        if self.kind == self.Kind.SPECIES and self.species_id:
            sp = self.species
            if self.identification_qualifier and sp.genus and sp.species:
                name = f'{sp.genus} {self.identification_qualifier} {sp.species}'
            else:
                name = sp.scientific_name
            return name, (sp.author or '').strip(), self.life_stage
        return self.taxon_name, '', self.life_stage if self.kind != self.Kind.COLLECTION else ''
    def _taxon_text(self, with_author):
        name, author, stage = self.taxon_parts()
        return ' '.join(p for p in (name, author if with_author else '', stage) if p)
    @property
    def taxon_full_name(self):
        """Read-only full name for display: genus, the open-nomenclature qualifier, the epithet,
        the author and the life stage -- e.g. "Chromodoris cf. strigata Rudman, 1982 juv.".
        Taxon-level samples show just their taxon name."""
        return self._taxon_text(True)
    @property
    def taxon_label(self):
        """taxon_full_name without the author -- the heading used in lists."""
        return self._taxon_text(False)
    @property
    def photographer_name(self):
        """The photographer of an observation is always its creator (owner) -- a trip has no
        photographer of its own. Photos by someone else are uploaded under that person's own
        account (a guest photographer is simply an inactive user) on a separate trip."""
        return full_name_for(self.owner, 'he') or 'שם הצלם לא צוין'
    def photographer_display_name(self, lang='he', registered_users=None):
        """Language-aware version of photographer_name (see seaslugs_i18n.photographer_name,
        the template filter that calls this): the owner's full name in the page's language,
        preferring the Profile's English name in English mode -- the same way the nav greeting
        does (see full_name_for). `registered_users` is accepted only so older callers keep
        working."""
        return full_name_for(self.owner, lang) or 'שם הצלם לא צוין'
    @property
    def thumbnail(self):
        return self.image.url if self.image else (f'https://i.ytimg.com/vi/{youtube_id(self.video_url)}/hqdefault.jpg' if self.video_url else '')
    def canonical_image_name(self, extra_used_names=()):
        """Human-meaningful, cross-environment-stable storage filename for this sample's
        image: the trip's own code (an admin-managed, human-chosen string -- see
        DiveTrip.code -- kept in sync between environments by table-transfer) plus an
        identifying part that depends on kind -- the species' genus+species binomial for
        an ordinary SPECIES-kind sample, the gallery title for a COLLECTION-kind one, and
        the free-text species_other identification for every other kind (GENUS/FAMILY/
        ORDER). Unlike an upload-time random UUID or a hash of the image's own bytes, this
        stays legible when browsing the media folder directly, and -- because every part
        of it is itself kept in sync across environments -- resolves to the very same name
        in both environments once the sample itself has been transferred, which is also
        what lets the image-manager's environment comparison work by filename alone.

        extra_used_names: names already claimed by other rows in the same in-progress
        batch (not yet saved, so a plain database query wouldn't see them) -- passed by
        image_manager.py's bulk upload action to keep two new samples in one batch from
        being assigned the same name."""
        if self.kind == self.Kind.SPECIES and self.species_id:
            identity = f'{self.species.genus} {self.species.species}'.strip() or self.species.scientific_name
        else:
            # taxon_name already picks the field that matches the kind: the collection's
            # title, the order / family / genus of a taxon-level sample, or the free-text
            # not-yet-catalogued species.
            identity = self.taxon_name
        trip_code = self.trip.code if self.trip_id else 'notrip'
        base = slugify(f'{trip_code} {identity}', allow_unicode=True) or f'sample-{self.pk or "new"}'
        candidate = base; n = 2
        qs = Sample.objects.exclude(pk=self.pk) if self.pk else Sample.objects.all()
        while candidate in extra_used_names or qs.filter(image=f'observations/{candidate}.jpg').exists():
            candidate = f'{base}-{n}'; n += 1
        return f'observations/{candidate}.jpg'
    def sync_taxonomy(self, strict=False):
        """Make order/family/genus/species consistent with the sample's kind and with each other.

        Which fields apply depends on `kind`: ORDER keeps only the order; FAMILY the family (and
        its order); GENUS also the genus; SPECIES the species too (a catalogued species fixes its
        genus, family and order); COLLECTION none of them. Fields that do not apply are cleared;
        higher levels that are blank are filled in from the lower ones through the taxonomy
        tables (a genus knows its family, a family its order).

        Returns {field: message} for what is inconsistent or missing. strict=False (used by
        save()) only normalises and fills in; strict=True (used by clean()) also reports
        conflicts -- e.g. a family that does not belong to the chosen order -- and a missing
        identification for the kind. Names that are not in the taxonomy tables are accepted as
        typed (there is nothing to check them against)."""
        errors = {}
        K = self.Kind
        for field in ('order', 'family', 'genus', 'species_other'):
            setattr(self, field, ' '.join((getattr(self, field) or '').split()))
        if self.kind == K.COLLECTION:
            self.order = self.family = self.genus = ''
            self.identification_qualifier = self.life_stage = ''
            return errors
        if self.kind != K.SPECIES:
            self.species = None; self.species_other = ''; self.identification_qualifier = ''
        if self.kind in (K.ORDER, K.FAMILY): self.genus = ''
        if self.kind == K.ORDER: self.family = ''
        if self.kind == K.SPECIES and self.species_id:
            sp = self.species
            self.species_other = ''
            # The catalogued species gives the genus; family and order come from the taxonomy
            # tables through that genus (below) -- the species' own free-text family/order are
            # only a fallback, since its `order` can be a different classification level
            # ("Doridida") than TaxonOrder's names ("Nudibranchia").
            self.genus, self.family, self.order = sp.genus or '', '', ''
        if self.genus and self.kind in (K.GENUS, K.SPECIES):
            tg = TaxonGenus.objects.select_related('family__order').filter(name=self.genus).first()
            if tg and tg.family_id:
                if not self.family: self.family = tg.family.name
                elif self.family != tg.family.name and self.kind == K.GENUS:
                    errors['family'] = f'הסוג {self.genus} שייך למשפחה {tg.family.name}, לא ל{self.family}.'
                if tg.family.order_id and self.family == tg.family.name:
                    if not self.order: self.order = tg.family.order.name
                    elif self.order != tg.family.order.name and self.kind == K.GENUS:
                        errors['order'] = f'הסוג {self.genus} שייך לסדרה {tg.family.order.name}, לא ל{self.order}.'
        if self.kind == K.SPECIES and self.species_id:
            self.family = self.family or self.species.family or ''
            self.order = self.order or self.species.order or ''
        if self.family and self.kind != K.COLLECTION:
            orders = {f.order.name for f in TaxonFamily.objects.select_related('order').filter(name=self.family) if f.order_id}
            if orders:
                if not self.order and len(orders) == 1: self.order = next(iter(orders))
                elif self.order and self.order not in orders and self.kind in (K.FAMILY, K.GENUS):
                    errors['order'] = f'המשפחה {self.family} שייכת לסדרה {" / ".join(sorted(orders))}, לא ל{self.order}.'
        if strict:
            for field, table in (('identification_qualifier', IdentificationQualifier), ('life_stage', LifeStage)):
                value = getattr(self, field)
                if value and not table.objects.filter(code=value).exists():
                    errors[field] = f'הערך "{value}" אינו קיים בטבלת העזר. אפשר להוסיף אותו שם.'
            if self.kind == K.ORDER and not self.order: errors['order'] = 'יש לבחור סדרה.'
            if self.kind == K.FAMILY and not self.family: errors['family'] = 'יש לבחור משפחה.'
            if self.kind == K.GENUS and not self.genus: errors['genus'] = 'יש לבחור סוג.'
            if self.kind == K.SPECIES and not self.species_id and not self.species_other: errors['species'] = 'יש לבחור מין או לפרט אחר.'
        return errors
    def publication_reasons(self):
        reasons = []
        if self.deleted_at: reasons.append('התצפית מסומנת כמחוקה.')
        try: self.full_clean(validate_constraints=False)
        except ValidationError as exc: reasons.extend(exc.messages)
        # species_other only ever holds a SPECIES-kind sample's not-yet-catalogued species
        # (taxon-level samples keep their identification in order/family/genus).
        if self.species_other: reasons.append('יש להחליף את ערך המין ״אחר״ בערך מטבלת המינים לפני פרסום (או להוסיף מין חדש דרך הפעולה הייעודית).')
        if self.site_other: reasons.append('יש להחליף את ערך אתר הצלילה ״אחר״ בערך מטבלת אתרי הצלילה לפני פרסום.')
        if not reasons and self.status == self.Status.PENDING: reasons.append('הנתונים הושלמו; נדרש אישור מנהל.')
        return reasons
    def clean(self):
        super().clean()
        errors = {}
        # The stored values before this edit, so the duplicate-media checks below only fire
        # when a photo/video is actually being newly entered/replaced -- not on every unrelated
        # re-save of a sample whose media hasn't changed (which would otherwise wrongly relitigate
        # legacy rows that predate this check, e.g. two samples that intentionally share one photo
        # showing two different species).
        original = Sample.objects.filter(pk=self.pk).values('image', 'video_url').first() if self.pk else None
        # An order/family/genus observation may have no media of its own: its page and gallery card
        # then borrow the picture of one of the observations a level below.
        if not self.video_url and not self.image and self.kind not in (self.Kind.ORDER, self.Kind.FAMILY, self.Kind.GENUS):
            errors['video_url'] = 'יש לספק קישור YouTube או להעלות תמונה, או את שניהם.'
        if self.kind == self.Kind.COLLECTION:
            if self.species_id or self.species_other: errors['species'] = 'סרטון אוסף אינו משויך למין יחיד. נקה את בחירת המין.'
            if not self.title.strip(): errors['title'] = 'יש להזין כותרת לסרטון האוסף.'
        taxon_level = self.kind in (self.Kind.ORDER, self.Kind.FAMILY, self.Kind.GENUS)
        if not self.trip_id:
            if not taxon_level: errors['trip'] = 'יש לבחור מסע צלילה.'
        elif not self.trip.year: errors['trip'] = 'למסע הנבחר אין שנה מוגדרת. יש להשלים שנה במסע הצלילה לפני פרסום.'
        self.site_other = self.site_other.strip()
        if self.kind == self.Kind.SPECIES and self.species_id and (self.species_other or '').strip():
            errors['species_other'] = 'יש לבחור מין מהרשימה או לפרט אחר, לא את שניהם.'
        # Normalise the taxonomy fields to the sample's kind (fields that don't apply are
        # cleared, higher levels are filled in from the lower ones) and report conflicts.
        for field, message in self.sync_taxonomy(strict=True).items(): errors.setdefault(field, message)
        # A single trip may not carry two non-deleted SPECIES-kind samples for the exact same
        # catalogued species -- species_other (an unresolved, free-text identification) is
        # deliberately excluded, since matching that reliably would mean fuzzy text comparison
        # rather than a real FK. This is deliberately a hard block ONLY when editing an
        # EXISTING sample (self.pk is set) into a collision with a different one -- silently
        # overwriting a different observation than the one being edited would be surprising.
        # A brand-new observation (self.pk is None) never reaches this error at all: the web
        # observation form (views.edit) checks for the very same collision itself, earlier,
        # and folds the submission into the existing sample (updating its image/video) instead
        # of ever calling full_clean() on a second, colliding new instance.
        self.undetermined_variant = (self.undetermined_variant or '').strip()
        if self.pk and self.kind == self.Kind.SPECIES and self.species_id and self.trip_id:
            duplicate = Sample.objects.exclude(pk=self.pk).filter(
                kind=self.Kind.SPECIES, species_id=self.species_id, trip_id=self.trip_id, deleted_at__isnull=True,
                undetermined_variant=self.undetermined_variant,
            ).first()
            if duplicate:
                errors['species'] = f'מין זה כבר נקלט למסע זה בתצפית קיימת ({duplicate}). אי אפשר לקלוט אותו מין פעמיים באותו מסע.'
        if self.site_id and self.site_other: errors['site_other'] = 'יש לבחור אתר צלילה מהרשימה או לפרט אחר, לא את שניהם.'
        if self.site_id and self.trip_id and self.trip.region_id and self.site.region_id != self.trip.region_id:
            errors['site'] = 'אתר הצלילה אינו שייך לאזור המסע שנבחר.'
        if self.day and not (self.trip_id and self.trip.month): errors['day'] = 'יום מחייב שהוגדר חודש במסע הצלילה.'
        if self.day and self.trip_id and self.trip.year and self.trip.month:
            try: date(self.trip.year, self.trip.month, self.day)
            except ValueError: errors['day'] = 'תאריך לא תקין.'
        if self.image:
            # The content-hash storage naming convention used everywhere an image actually
            # gets uploaded (the observation edit form, the folder importer, the image
            # manager's re-upload flow -- see media_transfer.py/folder_import.py) sets
            # self.image to that not-yet-written path and calls clean() before the file is
            # actually saved to storage, so self.image.read() would raise FileNotFoundError
            # in that window. The hash is already spelled out in the filename in that case,
            # so read it straight from there instead of touching the file.
            hash_from_name = re.fullmatch(r'observations/transfer/([0-9a-f]{64})\.jpg', self.image.name)
            if hash_from_name:
                digest = hash_from_name.group(1)
            else:
                try:
                    self.image.seek(0)
                    digest = hashlib.sha256(self.image.read()).hexdigest()
                    self.image.seek(0)
                except (FileNotFoundError, OSError):
                    digest = None
            if digest:
                self.image_hash = digest
                image_changed = not original or original['image'] != self.image.name
                if image_changed:
                    duplicate = Sample.objects.exclude(pk=self.pk).filter(deleted_at__isnull=True, image_hash=digest).first()
                    if duplicate and not getattr(self, '_shared_image', False): errors['image'] = f'התמונה הזו כבר קיימת בתצפית אחרת ({duplicate}). לא ניתן להשתמש באותה תמונה פעמיים.'
        else:
            self.image_hash = ''
        if self.video_url:
            video_changed = not original or original['video_url'] != self.video_url
            if video_changed:
                try: video_id = youtube_id(self.video_url)
                except ValidationError: video_id = None
                if video_id:
                    duplicate = None
                    others = Sample.objects.exclude(pk=self.pk).filter(deleted_at__isnull=True).exclude(video_url='')
                    for other in others:
                        try: other_video_id = youtube_id(other.video_url)
                        except ValidationError: continue
                        if other_video_id == video_id: duplicate = other; break
                    if duplicate: errors['video_url'] = f'הסרטון הזה כבר קיים בתצפית אחרת ({duplicate}). לא ניתן להשתמש באותו סרטון פעמיים.'
        if errors: raise ValidationError(errors)
    def save(self, *args, **kwargs):
        if kwargs.get('update_fields') is None: self.sync_taxonomy()
        super().save(*args, **kwargs)
        # A GENUS-kind sample is a purpose-built photo/video for its whole genus -- keep the
        # genus it identifies pointed at the current best genus-kind sample for it on every
        # save, not just through save_reviewed() below: sample transfer (image_manager.py /
        # sample_transfer.py) saves genus-kind samples with a plain .save() and never goes
        # through save_reviewed() at all, and soft_delete() below is itself just a save()
        # call that sets deleted_at -- both need this to stay in sync, so it belongs here
        # rather than duplicated in each caller.
        if self.kind == self.Kind.GENUS and self.genus:
            TaxonGenus.objects.filter(name=self.genus).update(
                defining_sample=TaxonGenus.pick_defining_sample(self.genus))
        # FAMILY- and ORDER-kind samples are likewise purpose-built media for a family / order
        # page. Unlike genera, those taxa usually already show a species photo picked by
        # build_taxonomy_tables, so a family/order-kind sample replaces it when one exists,
        # and a stale family/order-kind pick (deleted / unpublished) is cleared -- the page
        # then falls back to one of its species' photos (views.taxon_hero_media).
        for kind, model, name in ((self.Kind.FAMILY, TaxonFamily, self.family), (self.Kind.ORDER, TaxonOrder, self.order)):
            if self.kind == kind and name:
                rows = model.objects.filter(name=name)
                picked = taxon_kind_defining_sample(kind, name)
                if picked:
                    rows.update(defining_sample=picked)
                else:
                    rows.filter(defining_sample__kind=kind).update(defining_sample=None)
    def save_reviewed(self, actor=None, approve=False):
        self.full_clean(validate_constraints=False)
        with transaction.atomic():
            # Acquire SQLite's write lock before checking first occurrence.
            if self.species_id:
                Species.objects.filter(pk=self.species_id).update(scientific_name=models.F('scientific_name'))
            other = bool(self.species_other) or bool(self.site_other)
            taxon_level = self.kind in (self.Kind.ORDER, self.Kind.FAMILY, self.Kind.GENUS)
            complete = bool((taxon_level and not self.trip_id or self.trip_id and self.trip.year) and (self.species_id if self.kind == self.Kind.SPECIES else True) and not other)
            if approve and not complete:
                raise ValidationError('לפני אישור יש להשלים את שנת המסע ולהחליף ערכי ״אחר״ בערכים מטבלאות העזר.')
            self.status = 'published' if complete and (approve or self.kind == self.Kind.SPECIES) else 'pending'
            self.approved_by = actor if approve else None
            self.approved_at = timezone.now() if approve else None
            self.save()
            if self.status == self.Status.PUBLISHED and self.kind == self.Kind.SPECIES and self.species_id and self.trip.country_id and self.trip.sea_id:
                # update_or_create (not get_or_create) so an area that already exists but has
                # no defining sample yet -- e.g. after the previous one was deleted and no
                # replacement existed at that moment -- self-heals as soon as a valid sample
                # for it is published again.
                SpeciesArea.objects.update_or_create(
                    species_id=self.species_id, country_id=self.trip.country_id, sea_id=self.trip.sea_id,
                    undetermined_variant=self.undetermined_variant,
                    defaults={'defining_sample': SpeciesArea.pick_defining_sample(
                        self.species_id, self.trip.country_id, self.trip.sea_id, self.undetermined_variant)},
                )
    def soft_delete(self, actor):
        self.deleted_at = timezone.now(); self.deleted_by = actor
        self.save(update_fields=['deleted_at','deleted_by','updated_at'])
        if self.kind == self.Kind.SPECIES and self.species_id and self.trip_id and self.trip.country_id and self.trip.sea_id:
            # If this sample was defining its species in the gallery, replace it with another
            # published sample of the same species+area if one exists, else clear the field --
            # pick_defining_sample already excludes this sample now that it is marked deleted.
            SpeciesArea.objects.filter(
                species_id=self.species_id, country_id=self.trip.country_id, sea_id=self.trip.sea_id,
                undetermined_variant=self.undetermined_variant, defining_sample_id=self.pk,
            ).update(defining_sample=SpeciesArea.pick_defining_sample(
                self.species_id, self.trip.country_id, self.trip.sea_id, self.undetermined_variant))


class SpeciesArea(models.Model):
    """Links a Species to a country+sea it has been observed in, together with the
    sample that defines how it is presented in the gallery (photo/thumbnail).

    A species+country+sea can be split into more than one row when the photographer has
    marked some of its observations there with an undetermined_variant letter (see
    Sample.undetermined_variant): each letter (and the unmarked '' case) gets its own row,
    its own gallery card and its own public page, since the letters mark forms the
    photographer has deliberately chosen not to fold together even though the catalog
    only has one "Genus sp." entry for all of them."""
    species = models.ForeignKey(Species, on_delete=models.CASCADE, related_name='areas', verbose_name='מין')
    country = models.ForeignKey(Country, on_delete=models.PROTECT, verbose_name='מדינה')
    sea = models.ForeignKey(Sea, on_delete=models.PROTECT, verbose_name='ים')
    undetermined_variant = models.CharField('סימון מין לא מזוהה (sp.) — א׳/ב׳/A/B וכו׳', max_length=10, blank=True,
        help_text='מועתק מתצפיות (Sample.undetermined_variant) שסומנו באותה אות -- שורה נפרדת לכל אות, כדי שלא '
                   'תתמזג עם תצפיות של צורה אחרת מאותו סוג באותו אזור.')
    defining_sample = models.ForeignKey(Sample, null=True, blank=True, on_delete=models.SET_NULL, related_name='+', verbose_name='דגימה מגדירה',
        help_text='הדגימה שתמונתה או שרטון היוטיוב שלה יוצגו בכרטיס המין בגלריה. ניתן לבחור דגימה אחרת מבין דגימות המין באזור זה.')
    # Identifies this species+area's own dedicated public page (species name is not unique
    # on its own across areas -- the same species observed in two areas gets two pages).
    # Generated once from species+country+sea(+variant) and left alone after that so
    # published URLs stay stable; blank it out in admin to force a fresh one (e.g. after a
    # rename).
    slug = models.SlugField('כתובת בעמוד', max_length=220, unique=True, null=True, blank=True,
        help_text='נוצר אוטומטית משם המין+המדינה+הים בשמירה הראשונה. השאר ריק ליצירה אוטומטית, או הזן ידנית לדריסה.')
    class Meta:
        constraints = [models.UniqueConstraint(fields=['species','country','sea','undetermined_variant'], name='unique_species_area')]
        verbose_name = 'מין באזור'; verbose_name_plural = 'מינים באזורים'
    def __str__(self):
        label = f'{self.species} {self.undetermined_variant}'.strip()
        return f'{label} · {self.country} · {self.sea}'
    def _generate_slug(self):
        country_part = self.country.name_en or self.country.name
        sea_part = self.sea.name_en or self.sea.name
        base = slugify(f'{self.species.scientific_name} {self.undetermined_variant} {country_part} {sea_part}') or 'area'
        candidate = base
        n = 2
        qs = SpeciesArea.objects.exclude(pk=self.pk) if self.pk else SpeciesArea.objects.all()
        while qs.filter(slug=candidate).exists():
            candidate = f'{base}-{n}'
            n += 1
        return candidate
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._generate_slug()
        super().save(*args, **kwargs)

    @staticmethod
    def pick_defining_sample(species_id, country_id, sea_id, undetermined_variant=''):
        """Best sample to represent this species(+variant) in this country+sea: prefer one
        with an uploaded image over a video-only one, only among published/non-deleted
        samples, tie-broken by whichever was created first."""
        # A trip's sea is its region's sea (DiveTrip.sea).
        sea_match = models.Q(trip__region__sea_id=sea_id)
        candidates = list(Sample.objects.filter(
            models.Q(kind=Sample.Kind.SPECIES, species_id=species_id, status=Sample.Status.PUBLISHED,
                     deleted_at__isnull=True, trip__country_id=country_id, undetermined_variant=undetermined_variant) & sea_match,
        ).order_by('created_at', 'pk'))
        if not candidates:
            return None
        with_image = [c for c in candidates if c.image]
        return (with_image or candidates)[0]

    @staticmethod
    def next_candidate(species_id, country_id, sea, exclude_pk, undetermined_variant=''):
        """Describes what would take over as the defining sample for this species+area if
        the sample identified by exclude_pk stopped being it: the most recently created
        OTHER published, non-deleted sample of the species(+variant) there that has media
        (an image or a video), if one exists; otherwise whether some other (media-less)
        sample of the species(+variant) exists there at all, or none at all. Used both to
        preview the outcome on the observation form (species_area_status) and to actually
        carry it out when releasing a sample from its species (views.observation_action) --
        the two must agree, so both go through this one method."""
        sea_match = models.Q(trip__region__sea=sea)
        others = Sample.objects.filter(
            models.Q(kind=Sample.Kind.SPECIES, species_id=species_id, status=Sample.Status.PUBLISHED,
                     deleted_at__isnull=True, trip__country_id=country_id, undetermined_variant=undetermined_variant) & sea_match,
        ).exclude(pk=exclude_pk)
        with_media = others.exclude(image='', video_url='').order_by('-created_at', '-pk').first()
        if with_media:
            return {'kind': 'with_media', 'sample': with_media}
        if others.exists():
            return {'kind': 'without_media'}
        return {'kind': 'single'}

    @staticmethod
    def rebuild():
        """Delete every SpeciesArea row and regenerate it from scratch from the samples
        that currently exist: one row per species+country+sea+undetermined_variant with at
        least one published sample, each pointing at pick_defining_sample's choice. Safe to
        re-run at any time -- only this table is touched, Sample data is never changed."""
        with transaction.atomic():
            SpeciesArea.objects.all().delete()
            # A trip's sea is its region's sea (DiveTrip.sea), so a trip without a region
            # contributes no species area.
            keys = Sample.objects.filter(
                kind=Sample.Kind.SPECIES, status=Sample.Status.PUBLISHED, deleted_at__isnull=True,
                species__isnull=False, species_other='', site_other='',
                trip__country__isnull=False, trip__region__isnull=False,
            ).order_by().values_list('species_id', 'trip__country_id', 'trip__region__sea_id', 'undetermined_variant').distinct()
            # .order_by() clears Sample's default ordering (Meta.ordering = ['-created_at']);
            # without it Django silently adds created_at to the SELECT DISTINCT columns to
            # support that ordering, which defeats the intended (species,country,sea,variant)
            # dedup and can raise a UNIQUE-constraint IntegrityError below when two samples
            # for the same species+area have different created_at timestamps.
            count = 0
            for species_id, country_id, sea_id, variant in keys:
                defining = SpeciesArea.pick_defining_sample(species_id, country_id, sea_id, variant)
                if defining:
                    SpeciesArea.objects.create(species_id=species_id, country_id=country_id, sea_id=sea_id,
                                                undetermined_variant=variant, defining_sample=defining)
                    count += 1
        return count


# --- uploaded files that are replaced or cleared must not stay on disk ---------------------------
# The public observation form already deletes the old file itself; the Django admin ("לסלק" ticked,
# or a new file chosen) only drops the reference and leaves the old PDF behind as an orphan. This
# removes it for every save path. The file is kept when another row still points at the same name.
_REPLACEABLE_FILES = ((Species, ('article_pdf',)), (TaxonOrder, ('article_pdf',)), (TaxonFamily, ('article_pdf',)),
                      (TaxonGenus, ('article_pdf', 'identification_file')), (DiveTrip, ('article_pdf',)))


def _delete_replaced_files(sender, instance, update_fields=None, **kwargs):
    if not instance.pk:
        return
    previous = sender.objects.filter(pk=instance.pk).first()
    if previous is None:
        return
    for field in dict(_REPLACEABLE_FILES)[sender]:
        if update_fields is not None and field not in update_fields:
            continue
        old = getattr(previous, field)
        if not old or old.name == (getattr(instance, field).name or ''):
            continue
        if sender.objects.filter(**{field: old.name}).exclude(pk=instance.pk).exists():
            continue
        try:
            old.storage.delete(old.name)
        except OSError:
            pass


for _model, _fields in _REPLACEABLE_FILES:
    models.signals.pre_save.connect(_delete_replaced_files, sender=_model, dispatch_uid='delete_replaced_files_%s' % _model.__name__)
