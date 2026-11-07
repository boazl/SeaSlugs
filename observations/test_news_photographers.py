"""The /news/ page's manager section ends with a table of photographers: everyone with a published observation on the
site (an observation's photographer is its owner; guest photographers' inactive accounts included), with name,
email, phone and the number of published observations -- most observations first. Visitors and members never see it."""
from django.contrib.auth.models import User

from .models import Profile, Sample
from .test_news_activity import Base


class PhotographersTableTests(Base):
    def setUp(self):
        super().setUp()
        self.member.email = 'dana@example.com'
        self.member.save()
        Profile.objects.update_or_create(user=self.member, defaults={'phone': '050-1234567'})
        self.guest = User.objects.create_user('guest', first_name='רון', last_name='צלם', email='ron@example.com',
                                              is_active=False)
        self.observe()
        self.observe(species=self.varicosa, video='bbbbbbbbbbb')
        Sample(owner=self.guest, trip=self.trip_ph, species=self.ocellata, video_url='https://youtu.be/ccccccccccc').save_reviewed()
        pending = Sample(owner=self.guest, trip=self.trip, species=self.varicosa, video_url='https://youtu.be/ddddddddddd')
        pending.save()   # not published: not counted
        self.manager = User.objects.create_superuser('boss', password='pw-test-12345')

    def page(self, lang='he'):
        return self.client.get('/news/', {'lang': lang}).content.decode()

    def table(self, html):
        start = html.index('id="photographers"')
        return html[start:html.index('</table>', start)]

    def test_manager_sees_the_photographers_with_contact_details_and_counts(self):
        self.client.force_login(self.manager)
        table = self.table(self.page())
        self.assertIn('צלמים (2)', table)
        self.assertIn('<a href="mailto:dana@example.com">dana@example.com</a>', table)
        self.assertIn('<a href="tel:050-1234567">050-1234567</a>', table)
        self.assertIn('ron@example.com', table)   # a guest photographer (inactive account) is listed too
        rows = table.split('<tr>')[2:]
        self.assertIn('דנה ים', rows[0])
        self.assertIn('<td class="num">2</td>', rows[0])
        self.assertIn('<td class="num">1</td>', rows[1])   # the pending observation is not counted
        self.assertIn('<td dir="ltr" style="text-align:start">—</td>', rows[1])   # no phone

    def test_english_headings(self):
        self.client.force_login(self.manager)
        table = self.table(self.page('en'))
        for heading in ('Photographers', 'Email', 'Phone', 'Observations on the site'):
            self.assertIn(heading, table)

    def test_not_shown_to_visitors_or_members(self):
        self.assertNotIn('id="photographers"', self.page())
        self.client.force_login(self.member)
        html = self.page()
        self.assertNotIn('id="photographers"', html)
        self.assertNotIn('dana@example.com', html)
