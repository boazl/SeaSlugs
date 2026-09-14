import calendar
import re
import uuid
from datetime import date
from urllib.parse import urlparse, parse_qs
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models, transaction
from django.utils import timezone


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
    class Meta:
        ordering = [models.functions.NullIf('phylogenetic_order', models.Value('')).asc(nulls_last=True), 'scientific_name']
        verbose_name = 'מין'; verbose_name_plural = 'מינים'
    def __str__(self): return self.scientific_name


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    display_name = models.CharField('שם לתצוגה', max_length=100)
    macro_diver = models.BooleanField('מעוניין במציאת שותפים לצלילת מאקרו', default=False)
    visible_to_members = models.BooleanField('הצגת הפרופיל למשתמשים רשומים', default=False)
    regions = models.ManyToManyField(Region, blank=True, verbose_name='אזורי צלילה')
    countries = models.ManyToManyField(Country, blank=True, verbose_name='מדינות צלילה')
    bio = models.TextField('על עצמי', blank=True, max_length=1500)
    class Meta: verbose_name = 'פרופיל'; verbose_name_plural = 'פרופילים'
    def __str__(self): return self.display_name


class DiveTrip(models.Model):
    code = models.CharField('קוד מסע', max_length=40, unique=True, default=uuid.uuid4)
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
    photographer = models.CharField('צלם', max_length=180, blank=True)
    species_count = models.PositiveIntegerField('מספר מינים שנצפו במסע', null=True, blank=True, help_text='מספר מדווח לכל המסע; אינו מספר הסרטונים באתר. השאר ריק אם אינו ידוע.')
    source_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'dive_trips'
        ordering = ['-year', '-month', 'title']
        verbose_name = 'מסע צלילה'
        verbose_name_plural = 'מסעות צלילה'

    def __str__(self): return f'{self.title} [{self.code}]'

    @property
    def display_species_count(self):
        if self.species_count is not None:
            return self.species_count
        return self.samples.filter(kind='species', deleted_at__isnull=True, species__isnull=False).order_by().values('species_id').distinct().count()

    def clean(self):
        super().clean()
        if self.start_day:
            if not self.year or not self.month: raise ValidationError({'start_day':'יום התחלה מחייב שנה וחודש.'})
            try: date(self.year, self.month, self.start_day)
            except ValueError: raise ValidationError({'start_day':'תאריך התחלה לא תקין.'})


class Sample(models.Model):
    class Kind(models.TextChoices):
        SPECIES = 'species', 'מין יחיד'
        COLLECTION = 'collection', 'אוסף מינים / מסע צלילה'
    kind = models.CharField('סוג הסרטון', max_length=20, choices=Kind.choices, default=Kind.SPECIES)
    trip = models.ForeignKey(DiveTrip, verbose_name='מסע צלילה', null=True, blank=True, on_delete=models.PROTECT, related_name='samples')
    title = models.CharField('כותרת הגלריה', max_length=240, blank=True)
    gallery_order = models.PositiveIntegerField(default=0)
    source_metadata = models.JSONField(default=dict, blank=True)

    class Status(models.TextChoices):
        PENDING = 'pending', 'ממתינה לאישור'
        PUBLISHED = 'published', 'מפורסמת'
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='observations', verbose_name='יוצר')
    species = models.ForeignKey(Species, null=True, blank=True, on_delete=models.PROTECT, verbose_name='מין')
    country = models.ForeignKey(Country, null=True, blank=True, on_delete=models.PROTECT, verbose_name='מדינה')
    region = models.ForeignKey(Region, null=True, blank=True, on_delete=models.PROTECT, verbose_name='אזור')
    site = models.ForeignKey(Site, null=True, blank=True, on_delete=models.PROTECT, verbose_name='אתר צלילה')
    species_other = models.CharField('מין אחר', max_length=200, blank=True)
    country_other = models.CharField('מדינה אחרת', max_length=200, blank=True)
    region_other = models.CharField('אזור אחר', max_length=200, blank=True)
    site_other = models.CharField('אתר צלילה אחר', max_length=200, blank=True)
    year = models.PositiveSmallIntegerField('שנה', null=True, blank=True, validators=[MinValueValidator(1900)])
    month = models.PositiveSmallIntegerField('חודש', null=True, blank=True, validators=[MinValueValidator(1),MaxValueValidator(12)])
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
        constraints = [models.UniqueConstraint(fields=['species','region'], condition=models.Q(kind='species',status='published',deleted_at__isnull=True), name='unique_published_species_region')]
        verbose_name = 'דגימה / תצפית'; verbose_name_plural = 'Samples — דגימות ותצפיות'
    def __str__(self): return f'{self.title if self.kind == self.Kind.COLLECTION else self.species or self.species_other} · {self.year or ""}'
    @property
    def photographer_name(self):
        if self.trip_id and self.trip.photographer.strip():
            return self.trip.photographer.strip()
        profile = getattr(self.owner, 'profile', None)
        return (profile.display_name.strip() if profile else '') or self.owner.get_full_name().strip() or 'שם הצלם לא צוין'
    @property
    def thumbnail(self):
        return self.image.url if self.image else (f'https://i.ytimg.com/vi/{youtube_id(self.video_url)}/hqdefault.jpg' if self.video_url else '')
    def publication_duplicate(self):
        if self.kind != self.Kind.SPECIES or not self.species_id or not self.region_id:
            return None
        return Sample.objects.filter(kind='species',species_id=self.species_id,region_id=self.region_id,status='published',deleted_at__isnull=True).exclude(pk=self.pk).first()

    def publication_reasons(self):
        reasons = []
        duplicate = self.publication_duplicate()
        if duplicate: reasons.append(f'המין כבר מפורסם באזור זה בתצפית מספר {duplicate.pk}. לא ניתן לאשר פרסום כפול.')
        if self.deleted_at: reasons.append('התצפית מסומנת כמחוקה.')
        try: self.full_clean(validate_constraints=False)
        except ValidationError as exc: reasons.extend(exc.messages)
        if any(getattr(self,n+'_other') for n in ('species','country','region','site')):
            reasons.append('יש להחליף ערכי ״אחר״ בערכים מטבלאות העזר לפני פרסום.')
        if not reasons and self.status == self.Status.PENDING: reasons.append('הנתונים הושלמו; נדרש אישור מנהל.')
        return reasons
    def clean(self):
        super().clean()
        errors = {}
        if not self.video_url and not self.image:
            errors['video_url'] = 'יש לספק קישור YouTube או להעלות תמונה, או את שניהם.'
        if self.kind == self.Kind.COLLECTION:
            if self.species_id or self.species_other: errors['species'] = 'סרטון אוסף אינו משויך למין יחיד. נקה את בחירת המין.'
            if not self.trip_id: errors['trip'] = 'יש לבחור מסע צלילה לסרטון אוסף.'
            if not self.title.strip(): errors['title'] = 'יש להזין כותרת לסרטון האוסף.'
        if not self.year: errors['year'] = 'יש להשלים שנה לפני פרסום.'
        for name in ('species','country','region','site'):
            other = getattr(self, name+'_other').strip()
            setattr(self, name+'_other', other)
            if getattr(self, name+'_id') and other: errors[name+'_other'] = 'יש לבחור ערך מהרשימה או אחר, לא את שניהם.'
            if name != 'site' and not (name == 'species' and self.kind == self.Kind.COLLECTION) and not getattr(self,name+'_id') and not other: errors[name] = 'יש לבחור ערך או לפרט אחר.'
        if self.region_id and self.country_id != self.region.country_id: errors['region'] = 'האזור אינו שייך למדינה שנבחרה.'
        if self.site_id and self.region_id != self.site.region_id: errors['site'] = 'האתר אינו שייך לאזור שנבחר.'
        if self.year and self.year > date.today().year: errors['year'] = 'השנה אינה יכולה להיות בעתיד.'
        if self.day and not self.month: errors['day'] = 'יום מחייב בחירת חודש.'
        if self.year and self.month and self.day:
            try: date(self.year,self.month,self.day)
            except ValueError: errors['day'] = 'תאריך לא תקין.'
        if errors: raise ValidationError(errors)
    def save_reviewed(self, actor=None, approve=False):
        self.full_clean(validate_constraints=False)
        with transaction.atomic():
            # Acquire SQLite's write lock before checking first occurrence.
            if self.species_id:
                Species.objects.filter(pk=self.species_id).update(scientific_name=models.F('scientific_name'))
            other = any(getattr(self,n+'_other') for n in ('species','country','region','site'))
            complete = (self.trip_id if self.kind == self.Kind.COLLECTION else self.species_id) and self.country_id and self.region_id and not other
            if approve and not complete: raise ValidationError('לפני אישור יש להחליף את ערכי האחר בערכים מטבלאות העזר.')
            duplicate = self.publication_duplicate()
            if approve and duplicate:
                raise ValidationError(f'המין כבר מפורסם באזור זה בתצפית מספר {duplicate.pk}. לא ניתן לאשר פרסום כפול.')
            existing = duplicate is not None
            self.status = 'published' if complete and (approve or (self.kind == self.Kind.SPECIES and not existing)) else 'pending'
            self.approved_by = actor if approve else None
            self.approved_at = timezone.now() if approve else None
            self.save()
    def soft_delete(self, actor):
        self.deleted_at = timezone.now(); self.deleted_by = actor
        self.save(update_fields=['deleted_at','deleted_by','updated_at'])
