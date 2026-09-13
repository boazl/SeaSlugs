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
    source_id = models.CharField('מזהה מקור לייבוא', max_length=200, blank=True)
    class Meta:
        ordering = ['scientific_name']
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


class Sample(models.Model):
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
    video_url = models.URLField('קישור YouTube', validators=[youtube_id])
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
    def __str__(self): return f'{self.species or self.species_other} · {self.year}'
    @property
    def thumbnail(self):
        return self.image.url if self.image else f'https://i.ytimg.com/vi/{youtube_id(self.video_url)}/hqdefault.jpg'
    def clean(self):
        super().clean()
        errors = {}
        if not self.year: errors['year'] = 'יש להשלים שנה לפני פרסום.'
        for name in ('species','country','region','site'):
            other = getattr(self, name+'_other').strip()
            setattr(self, name+'_other', other)
            if getattr(self, name+'_id') and other: errors[name+'_other'] = 'יש לבחור ערך מהרשימה או אחר, לא את שניהם.'
            if name != 'site' and not getattr(self,name+'_id') and not other: errors[name] = 'יש לבחור ערך או לפרט אחר.'
        if self.region_id and self.country_id != self.region.country_id: errors['region'] = 'האזור אינו שייך למדינה שנבחרה.'
        if self.site_id and self.region_id != self.site.region_id: errors['site'] = 'האתר אינו שייך לאזור שנבחר.'
        if self.year and self.year > date.today().year: errors['year'] = 'השנה אינה יכולה להיות בעתיד.'
        if self.day and not self.month: errors['day'] = 'יום מחייב בחירת חודש.'
        if self.year and self.month and self.day:
            try: date(self.year,self.month,self.day)
            except ValueError: errors['day'] = 'תאריך לא תקין.'
        if errors: raise ValidationError(errors)
    def save_reviewed(self, actor=None, approve=False):
        self.full_clean()
        with transaction.atomic():
            # Acquire SQLite's write lock before checking first occurrence.
            if self.species_id:
                Species.objects.filter(pk=self.species_id).update(scientific_name=models.F('scientific_name'))
            other = any(getattr(self,n+'_other') for n in ('species','country','region','site'))
            complete = self.species_id and self.country_id and self.region_id and not other
            if approve and not complete: raise ValidationError('לפני אישור יש להחליף את ערכי האחר בערכים מטבלאות העזר.')
            existing = Sample.objects.filter(species_id=self.species_id,region_id=self.region_id,status='published',deleted_at__isnull=True).exclude(pk=self.pk).exists()
            self.status = 'published' if complete and (approve or not existing) else 'pending'
            self.approved_by = actor if approve else None
            self.approved_at = timezone.now() if approve else None
            self.save()
    def soft_delete(self, actor):
        self.deleted_at = timezone.now(); self.deleted_by = actor
        self.save(update_fields=['deleted_at','deleted_by','updated_at'])
