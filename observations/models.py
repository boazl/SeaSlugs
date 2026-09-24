import calendar
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
    class Meta(Named.Meta): verbose_name = 'אזור'; verbose_name_plural = 'אזורים'


class Site(Named):
    region = models.ForeignKey(Region, on_delete=models.PROTECT, verbose_name='אזור')
    class Meta(Named.Meta): verbose_name = 'אתר צלילה'; verbose_name_plural = 'אתרי צלילה'


class Species(models.Model):
    scientific_name = models.CharField('שם מדעי', max_length=200, unique=True)
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
    description_he = models.TextField('תיאור בעברית', blank=True)
    description_en = models.TextField('תיאור באנגלית', blank=True)
    link = models.URLField('קישור', blank=True)
    article_pdf = models.FileField('מאמר (PDF)', upload_to='articles/species/', blank=True, validators=[FileExtensionValidator(['pdf'])])
    class Meta:
        ordering = [models.functions.NullIf('phylogenetic_order', models.Value('')).asc(nulls_last=True), 'scientific_name']
        verbose_name = 'מין'; verbose_name_plural = 'מינים'
    def __str__(self): return self.scientific_name
    def clean(self):
        super().clean()
        errors = {}
        if self.first_observed_year and self.first_observed_year > date.today().year:
            errors['first_observed_year'] = 'שנת תצפית ראשונה אינה יכולה להיות בעתיד.'
        if self.last_observed_year and self.last_observed_year > date.today().year:
            errors['last_observed_year'] = 'שנת תצפית אחרונה אינה יכולה להיות בעתיד.'
        if self.first_observed_year and self.last_observed_year and self.last_observed_year < self.first_observed_year:
            errors['last_observed_year'] = 'שנת תצפית אחרונה אינה יכולה להיות לפני שנת התצפית הראשונה.'
        if errors: raise ValidationError(errors)


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
    link = models.URLField('קישור', blank=True)
    article_pdf = models.FileField('מאמר (PDF)', upload_to='articles/families/', blank=True, validators=[FileExtensionValidator(['pdf'])])
    class Meta:
        ordering = [models.functions.NullIf('taxonomic_order', models.Value('')).asc(nulls_last=True), 'name', 'sub_family']
        verbose_name = 'משפחה (טקסונומיה)'
        verbose_name_plural = 'משפחות (טקסונומיה)'
        constraints = [models.UniqueConstraint(fields=['name', 'sub_family'], name='unique_taxonfamily_name_sub_family')]
    def __str__(self): return f'{self.name} ({self.sub_family})' if self.sub_family else self.name


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
    link = models.URLField('קישור', blank=True)
    article_pdf = models.FileField('מאמר (PDF)', upload_to='articles/genera/', blank=True, validators=[FileExtensionValidator(['pdf'])])
    class Meta:
        ordering = [models.functions.NullIf('taxonomic_order', models.Value('')).asc(nulls_last=True), 'name']
        verbose_name = 'סוג (טקסונומיה)'
        verbose_name_plural = 'סוגים (טקסונומיה)'
    def __str__(self): return self.name


class SiteImage(models.Model):
    key = models.SlugField('מזהה', max_length=50, unique=True)
    image = models.ImageField('תמונה', upload_to='site/')
    updated_at = models.DateTimeField('עודכן', auto_now=True)
    class Meta:
        verbose_name = 'תמונת אתר'; verbose_name_plural = 'תמונות אתר'
    def __str__(self): return self.key


PHONE_VALIDATOR = RegexValidator(r'^[0-9+\-()\s]{5,30}$', 'מספר טלפון לא תקין.')


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    display_name = models.CharField('שם לתצוגה', max_length=100)
    name_en = models.CharField('שם באנגלית', max_length=150, blank=True)
    phone = models.CharField('טלפון', max_length=30, blank=True, validators=[PHONE_VALIDATOR])
    macro_diver = models.BooleanField('מעוניין במציאת שותפים לצלילת מאקרו', default=False)
    visible_to_members = models.BooleanField('הצגת הפרופיל למשתמשים רשומים', default=False)
    regions = models.ManyToManyField(Region, blank=True, verbose_name='אזורי צלילה')
    countries = models.ManyToManyField(Country, blank=True, verbose_name='מדינות צלילה')
    bio = models.TextField('על עצמי', blank=True, max_length=1500)
    class Meta: verbose_name = 'פרופיל'; verbose_name_plural = 'פרופילים'
    def __str__(self): return self.display_name


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
    reserve = models.CharField('שמורה / אתר', max_length=180, blank=True)
    sea_name = models.CharField('ים', max_length=180, blank=True)
    country = models.ForeignKey(Country, null=True, blank=True, on_delete=models.PROTECT, verbose_name='מדינה', related_name='dive_trips')
    region = models.ForeignKey(Region, null=True, blank=True, on_delete=models.PROTECT, verbose_name='אזור', related_name='dive_trips')
    photographer = models.CharField('צלם', max_length=180, blank=True)
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

    @property
    def sea(self):
        return self.region.sea if self.region_id else None

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


class Sample(models.Model):
    class Kind(models.TextChoices):
        SPECIES = 'species', 'מין יחיד'
        COLLECTION = 'collection', 'אוסף מינים / מסע צלילה'
        GENUS = 'genus', 'סוג'
        FAMILY = 'family', 'משפחה'
        ORDER = 'order', 'סדרה'
    kind = models.CharField('סוג הסרטון', max_length=20, choices=Kind.choices, default=Kind.SPECIES)
    trip = models.ForeignKey(DiveTrip, verbose_name='מסע צלילה', on_delete=models.PROTECT, related_name='samples')
    title = models.CharField('כותרת הגלריה', max_length=240, blank=True)
    gallery_order = models.PositiveIntegerField(default=0)
    source_metadata = models.JSONField(default=dict, blank=True)

    class Status(models.TextChoices):
        PENDING = 'pending', 'ממתינה לאישור'
        PUBLISHED = 'published', 'מפורסמת'
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='observations', verbose_name='יוצר')
    species = models.ForeignKey(Species, null=True, blank=True, on_delete=models.PROTECT, verbose_name='מין')
    site = models.ForeignKey(Site, null=True, blank=True, on_delete=models.PROTECT, verbose_name='אתר צלילה')
    species_other = models.CharField('מין אחר', max_length=200, blank=True)
    site_other = models.CharField('אתר צלילה אחר', max_length=200, blank=True)
    day = models.PositiveSmallIntegerField('יום', null=True, blank=True, validators=[MinValueValidator(1),MaxValueValidator(31)])
    depth = models.DecimalField('עומק במטרים', max_digits=6, decimal_places=1, null=True, blank=True, validators=[MinValueValidator(0)])
    transfer_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    video_url = models.URLField('קישור YouTube', blank=True, validators=[youtube_id])
    image = models.ImageField('תמונה חלופית (רשות)', upload_to='observations/', blank=True)
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
    def __str__(self): return f'{self.title if self.kind == self.Kind.COLLECTION else self.species or self.species_other} · {self.trip.year if self.trip_id and self.trip.year else ""}'
    @property
    def photographer_name(self):
        if self.trip_id and self.trip.photographer.strip():
            return self.trip.photographer.strip()
        profile = getattr(self.owner, 'profile', None)
        return (profile.display_name.strip() if profile else '') or self.owner.get_full_name().strip() or 'שם הצלם לא צוין'
    @property
    def thumbnail(self):
        return self.image.url if self.image else (f'https://i.ytimg.com/vi/{youtube_id(self.video_url)}/hqdefault.jpg' if self.video_url else '')
    def publication_reasons(self):
        reasons = []
        if self.deleted_at: reasons.append('התצפית מסומנת כמחוקה.')
        try: self.full_clean(validate_constraints=False)
        except ValidationError as exc: reasons.extend(exc.messages)
        # A GENUS-kind sample uses species_other as its actual, permanent identification
        # (the genus name) rather than an unresolved placeholder awaiting a specific
        # species match -- only SPECIES/COLLECTION-kind samples need this nudge.
        if self.species_other and self.kind != self.Kind.GENUS: reasons.append('יש להחליף את ערך המין ״אחר״ בערך מטבלת המינים לפני פרסום (או להוסיף מין חדש דרך הפעולה הייעודית).')
        if self.site_other: reasons.append('יש להחליף את ערך אתר הצלילה ״אחר״ בערך מטבלת אתרי הצלילה לפני פרסום.')
        if not reasons and self.status == self.Status.PENDING: reasons.append('הנתונים הושלמו; נדרש אישור מנהל.')
        return reasons
    def clean(self):
        super().clean()
        errors = {}
        if not self.video_url and not self.image:
            errors['video_url'] = 'יש לספק קישור YouTube או להעלות תמונה, או את שניהם.'
        if self.kind == self.Kind.COLLECTION:
            if self.species_id or self.species_other: errors['species'] = 'סרטון אוסף אינו משויך למין יחיד. נקה את בחירת המין.'
            if not self.title.strip(): errors['title'] = 'יש להזין כותרת לסרטון האוסף.'
        if not self.trip_id: errors['trip'] = 'יש לבחור מסע צלילה.'
        elif not self.trip.year: errors['trip'] = 'למסע הנבחר אין שנה מוגדרת. יש להשלים שנה במסע הצלילה לפני פרסום.'
        self.species_other = self.species_other.strip()
        self.site_other = self.site_other.strip()
        if self.species_id and self.species_other: errors['species_other'] = 'יש לבחור מין מהרשימה או לפרט אחר, לא את שניהם.'
        if self.kind != self.Kind.COLLECTION and not self.species_id and not self.species_other: errors['species'] = 'יש לבחור מין או לפרט אחר.'
        if self.site_id and self.site_other: errors['site_other'] = 'יש לבחור אתר צלילה מהרשימה או לפרט אחר, לא את שניהם.'
        if self.site_id and self.trip_id and self.trip.region_id and self.site.region_id != self.trip.region_id:
            errors['site'] = 'אתר הצלילה אינו שייך לאזור המסע שנבחר.'
        if self.day and not (self.trip_id and self.trip.month): errors['day'] = 'יום מחייב שהוגדר חודש במסע הצלילה.'
        if self.day and self.trip_id and self.trip.year and self.trip.month:
            try: date(self.trip.year, self.trip.month, self.day)
            except ValueError: errors['day'] = 'תאריך לא תקין.'
        if errors: raise ValidationError(errors)
    def save_reviewed(self, actor=None, approve=False):
        self.full_clean(validate_constraints=False)
        with transaction.atomic():
            # Acquire SQLite's write lock before checking first occurrence.
            if self.species_id:
                Species.objects.filter(pk=self.species_id).update(scientific_name=models.F('scientific_name'))
            # Same exception as publication_reasons() above: species_other on a GENUS-kind
            # sample is the genus identification itself, not an incomplete "other" value.
            other = (bool(self.species_other) and self.kind != self.Kind.GENUS) or bool(self.site_other)
            complete = bool(self.trip_id and self.trip.year and (self.species_id if self.kind == self.Kind.SPECIES else True) and not other)
            if approve and not complete:
                raise ValidationError('לפני אישור יש להשלים את שנת המסע ולהחליף ערכי ״אחר״ בערכים מטבלאות העזר.')
            self.status = 'published' if complete and (approve or self.kind == self.Kind.SPECIES) else 'pending'
            self.approved_by = actor if approve else None
            self.approved_at = timezone.now() if approve else None
            self.save()
            if self.status == self.Status.PUBLISHED and self.kind == self.Kind.SPECIES and self.species_id and self.trip.country_id and self.trip.region_id:
                # update_or_create (not get_or_create) so an area that already exists but has
                # no defining sample yet -- e.g. after the previous one was deleted and no
                # replacement existed at that moment -- self-heals as soon as a valid sample
                # for it is published again.
                SpeciesArea.objects.update_or_create(
                    species_id=self.species_id, country_id=self.trip.country_id, sea_id=self.trip.region.sea_id,
                    defaults={'defining_sample': SpeciesArea.pick_defining_sample(
                        self.species_id, self.trip.country_id, self.trip.region.sea_id)},
                )
    def soft_delete(self, actor):
        self.deleted_at = timezone.now(); self.deleted_by = actor
        self.save(update_fields=['deleted_at','deleted_by','updated_at'])
        if self.kind == self.Kind.SPECIES and self.species_id and self.trip_id and self.trip.country_id and self.trip.region_id:
            # If this sample was defining its species in the gallery, replace it with another
            # published sample of the same species+area if one exists, else clear the field --
            # pick_defining_sample already excludes this sample now that it is marked deleted.
            SpeciesArea.objects.filter(
                species_id=self.species_id, country_id=self.trip.country_id, sea_id=self.trip.region.sea_id,
                defining_sample_id=self.pk,
            ).update(defining_sample=SpeciesArea.pick_defining_sample(
                self.species_id, self.trip.country_id, self.trip.region.sea_id))


class SpeciesArea(models.Model):
    """Links a Species to a country+sea it has been observed in, together with the
    sample that defines how it is presented in the gallery (photo/thumbnail)."""
    species = models.ForeignKey(Species, on_delete=models.CASCADE, related_name='areas', verbose_name='מין')
    country = models.ForeignKey(Country, on_delete=models.PROTECT, verbose_name='מדינה')
    sea = models.ForeignKey(Sea, on_delete=models.PROTECT, verbose_name='ים')
    defining_sample = models.ForeignKey(Sample, null=True, blank=True, on_delete=models.SET_NULL, related_name='+', verbose_name='דגימה מגדירה',
        help_text='הדגימה שתמונתה או שרטון היוטיוב שלה יוצגו בכרטיס המין בגלריה. ניתן לבחור דגימה אחרת מבין דגימות המין באזור זה.')
    # Identifies this species+area's own dedicated public page (species name is not unique
    # on its own across areas -- the same species observed in two areas gets two pages).
    # Generated once from species+country+sea and left alone after that so published URLs
    # stay stable; blank it out in admin to force a fresh one (e.g. after a rename).
    slug = models.SlugField('כתובת בעמוד', max_length=220, unique=True, null=True, blank=True,
        help_text='נוצר אוטומטית משם המין+המדינה+הים בשמירה הראשונה. השאר ריק ליצירה אוטומטית, או הזן ידנית לדריסה.')
    class Meta:
        constraints = [models.UniqueConstraint(fields=['species','country','sea'], name='unique_species_area')]
        verbose_name = 'מין באזור'; verbose_name_plural = 'מינים באזורים'
    def __str__(self):
        return f'{self.species} · {self.country} · {self.sea}'
    def _generate_slug(self):
        country_part = self.country.name_en or self.country.name
        sea_part = self.sea.name_en or self.sea.name
        base = slugify(f'{self.species.scientific_name} {country_part} {sea_part}') or 'area'
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
    def pick_defining_sample(species_id, country_id, sea_id):
        """Best sample to represent this species in this country+sea: prefer one with an
        uploaded image over a video-only one, only among published/non-deleted samples,
        tie-broken by whichever was created first."""
        candidates = list(Sample.objects.filter(
            kind=Sample.Kind.SPECIES, species_id=species_id, status=Sample.Status.PUBLISHED,
            deleted_at__isnull=True, trip__country_id=country_id, trip__region__sea_id=sea_id,
        ).order_by('created_at', 'pk'))
        if not candidates:
            return None
        with_image = [c for c in candidates if c.image]
        return (with_image or candidates)[0]

    @staticmethod
    def next_candidate(species_id, country_id, sea, exclude_pk):
        """Describes what would take over as the defining sample for this species+area if
        the sample identified by exclude_pk stopped being it: the most recently created
        OTHER published, non-deleted sample of the species there that has media (an image
        or a video), if one exists; otherwise whether some other (media-less) sample of
        the species exists there at all, or none at all. Used both to preview the outcome
        on the observation form (species_area_status) and to actually carry it out when
        releasing a sample from its species (views.observation_action) -- the two must
        agree, so both go through this one method."""
        others = Sample.objects.filter(
            kind=Sample.Kind.SPECIES, species_id=species_id, status=Sample.Status.PUBLISHED,
            deleted_at__isnull=True, trip__country_id=country_id, trip__region__sea=sea,
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
        that currently exist: one row per species+country+sea with at least one published
        sample, each pointing at pick_defining_sample's choice. Safe to re-run at any time
        -- only this table is touched, Sample data is never changed."""
        with transaction.atomic():
            SpeciesArea.objects.all().delete()
            keys = Sample.objects.filter(
                kind=Sample.Kind.SPECIES, status=Sample.Status.PUBLISHED, deleted_at__isnull=True,
                species__isnull=False, species_other='', site_other='',
                trip__country__isnull=False, trip__region__isnull=False,
            ).order_by().values_list('species_id', 'trip__country_id', 'trip__region__sea_id').distinct()
            # .order_by() clears Sample's default ordering (Meta.ordering = ['-created_at']);
            # without it Django silently adds created_at to the SELECT DISTINCT columns to
            # support that ordering, which defeats the intended (species,country,sea) dedup
            # and can raise a UNIQUE-constraint IntegrityError below when two samples for the
            # same species+area have different created_at timestamps.
            count = 0
            for species_id, country_id, sea_id in keys:
                defining = SpeciesArea.pick_defining_sample(species_id, country_id, sea_id)
                if defining:
                    SpeciesArea.objects.create(species_id=species_id, country_id=country_id, sea_id=sea_id, defining_sample=defining)
                    count += 1
        return count
