from django.contrib.auth.models import User
from django.test import TestCase

from .models import TaxonFamily, TaxonGenus, TaxonOrder


class TaxonOrderFilterLabelTests(TestCase):
    """The order filter on the genus/family changelists: several TaxonOrder rows share a name
    (Nudibranchia/Cladobranchia x3), so each option also shows its Hebrew name and superfamilies."""

    def setUp(self):
        self.client.force_login(User.objects.create_superuser('manager', password='x'))
        self.aeolid = TaxonOrder.objects.create(name='Nudibranchia', sub_order='Cladobranchia', taxonomic_order='8', name_he='חשופיות אונות')
        self.dendro = TaxonOrder.objects.create(name='Nudibranchia', sub_order='Cladobranchia', taxonomic_order='7', name_he='חשופיות אילן')
        f1 = TaxonFamily.objects.create(name='Flabellinidae', order=self.aeolid, superfamily='Fionoidea')
        TaxonFamily.objects.create(name='Facelinidae', order=self.aeolid, superfamily='Aeolidioidea')
        TaxonFamily.objects.create(name='Tethydidae', order=self.dendro, superfamily='Dendronotoidea')
        TaxonFamily.objects.create(name='Heroidae', order=self.dendro, superfamily='\\N')   # import artifact
        TaxonGenus.objects.create(name='Flabellina', family=f1)

    def labels(self, url):
        html = self.client.get(url).content.decode()
        return html

    def test_genus_filter_tells_same_named_rows_apart(self):
        html = self.labels('/admin/observations/taxongenus/')
        self.assertIn('Nudibranchia (Cladobranchia) · חשופיות אונות · Aeolidioidea, Fionoidea', html)
        self.assertIn('Nudibranchia (Cladobranchia) · חשופיות אילן · Dendronotoidea', html)
        self.assertNotIn('Dendronotoidea, \\N', html)

    def test_title_says_what_the_counts_count(self):
        self.assertIn('לפי סדרה (בסוגריים: מספר הסוגים)', self.labels('/admin/observations/taxongenus/'))
        self.assertIn('בסוגריים: מספר המשפחות', self.labels('/admin/observations/taxonfamily/'))

    def test_family_filter_is_labelled_too(self):
        self.assertIn('חשופיות אילן · Dendronotoidea', self.labels('/admin/observations/taxonfamily/'))

    def test_filtering_still_works(self):
        html = self.labels(f'/admin/observations/taxongenus/?family__order__id__exact={self.aeolid.pk}')
        self.assertIn('Flabellina', html)
        html = self.labels(f'/admin/observations/taxongenus/?family__order__id__exact={self.dendro.pk}')
        self.assertNotIn('>Flabellina<', html)
