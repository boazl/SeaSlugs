from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from observations.models import Country, Sea, Region
class Command(BaseCommand):
    help='Create initial role groups and geographic reference data, without assigning users.'
    def handle(self,*args,**options):
        for name in ['New user','Subscriber','Macro diver','Macro photographer','Artist','Scientist','Administrator']:
            group,_=Group.objects.get_or_create(name=name)
            if name=='Scientist': group.permissions.add(*Permission.objects.filter(content_type__app_label='observations',codename__in=['view_species','add_species','change_species']))
            if name=='Administrator': group.permissions.add(*Permission.objects.filter(content_type__app_label='observations').exclude(codename__startswith='delete_'))
        israel,_=Country.objects.get_or_create(name='ישראל',defaults={'name_en':'Israel'})
        for he,en in [('פיליפינים','Philippines'),('אינדונזיה','Indonesia')]: Country.objects.get_or_create(name=he,defaults={'name_en':en})
        med,_=Sea.objects.get_or_create(name='הים התיכון',defaults={'name_en':'Mediterranean'})
        red,_=Sea.objects.get_or_create(name='ים סוף',defaults={'name_en':'Red Sea'})
        for he,en,sea in [('אילת','Eilat',red),('קיסריה','Caesarea',med),('אכזיב','Akhziv',med),('אשקלון','Ashkelon',med),('אשדוד','Ashdod',med)]:
            Region.objects.get_or_create(name=he,country=israel,defaults={'name_en':en,'sea':sea})
        self.stdout.write('Roles and locations ready. No users were granted administrator access.')
