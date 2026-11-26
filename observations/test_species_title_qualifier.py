from django.contrib.auth.models import User
from django.test import TestCase

from .models import Country, DiveTrip, LifeStage, Region, Sample, Sea, Species, SpeciesArea


class SpeciesTitleQualifierTests(TestCase):
    """The species page heading names the main observation as identified -- its cf./aff. and life stage before the
    author ("Phyllidia cf. alyta juv. Yonow, 1996"), as on the photo label; an extra observation shows its own heading
    only when it differs from the main one, also with the stage before the author."""

    def setUp(self):
        LifeStage.objects.get_or_create(code='juv.', defaults={'name': 'צעיר'})
        self.owner = User.objects.create_user('owner', password='x')
        png = Country.objects.create(name='פפואה גינאה החדשה', name_en='Papua New Guinea')
        sea = Sea.objects.create(name='ים ביסמרק', name_en='Bismarck Sea')
        self.region = Region.objects.create(name='Madang', country=png, sea=sea)
        self.png = png
        self.species = Species.objects.create(scientific_name='Phyllidia alyta', genus='Phyllidia', species='alyta',
                                              author='Yonow, 1996')

    def observe(self, code, **fields):
        trip = DiveTrip.objects.create(code=code, title=code, year=1998, month=1, country=self.png, region=self.region)
        s = Sample(owner=self.owner, species=self.species, trip=trip, video_url=f'https://youtu.be/3000000000{len(code)}')
        s.save_reviewed()
        Sample.objects.filter(pk=s.pk).update(**fields)
        return s

    def test_heading_shows_cf_and_stage(self):
        self.observe('Z2', identification_qualifier='cf.', life_stage='juv.')
        html = self.client.get(f'/species/{SpeciesArea.objects.get().slug}/').content.decode()
        self.assertIn('<h1 dir="ltr"><i>Phyllidia</i> cf. <i>alyta</i> juv. <span class="species-author">Yonow, 1996</span>', html)

    def test_plain_extra_observation_gets_its_own_heading(self):
        main = self.observe('Z2', identification_qualifier='cf.')
        extra = self.observe('Z22')
        area = SpeciesArea.objects.get()
        SpeciesArea.objects.filter(pk=area.pk).update(defining_sample=main)
        html = self.client.get(f'/species/{area.slug}/').content.decode()
        card = html[html.index(f'id="obs-{extra.pk}"'):]
        self.assertIn('<h3 class="sample-name" dir="ltr"><i>Phyllidia alyta</i>', card[:card.index('</article>')])

    def test_gallery_and_genus_cards_show_cf_and_stage(self):
        from .models import TaxonGenus
        TaxonGenus.objects.create(name='Phyllidia')
        self.observe('Z2', identification_qualifier='cf.', life_stage='juv.')
        self.assertEqual(SpeciesArea.objects.get().display_name, 'Phyllidia cf. alyta juv.')
        self.assertIn('"title": "Phyllidia cf. alyta juv."', self.client.get('/catalog.js').content.decode())
        self.assertIn('<i>Phyllidia</i> cf. <i>alyta</i> juv.', self.client.get('/genus/Phyllidia/').content.decode())

