"""Voluntary financial support via PayPal (support.py, support.html, support_thank_you.html)."""
import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from .models import Country, DiveTrip, Region, Sample, Sea, Species, SpeciesArea

PAYPAL = 'https://www.paypal.com/ncp/payment/ZPWK3CE7KPCU2'
ON = override_settings(SUPPORT_ENABLED=True, PAYPAL_SUPPORT_URL=PAYPAL)
OFF = override_settings(SUPPORT_ENABLED=False, PAYPAL_SUPPORT_URL=PAYPAL)


@ON
class SupportPageTests(TestCase):
    """/support/ answers 200 to anyone (no sign-in) in Hebrew (RTL) and English (LTR, ?lang=en), with the texts the
    owner wrote, one link to the PayPal payment page from settings.PAYPAL_SUPPORT_URL, no amount field of its own,
    no claim of being a charity, the Section 46 disclaimer, and its own title, meta description, canonical and
    hreflang."""

    def test_hebrew_page_for_an_anonymous_visitor(self):
        response = self.client.get('/support/')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('<html lang="he" dir="rtl">', html)
        self.assertIn('<h1 id="support-title">תמיכה בפרויקט SeaSlugs</h1>', html)
        self.assertIn('<title>תמיכה בפרויקט חקר חשופיות הים | SeaSlugs</title>', html)
        self.assertIn('האתר פתוח לכלל הציבור ללא תשלום.', html)
        self.assertIn('תמיכה בפרויקט באמצעות PayPal', html)
        self.assertIn('אינה מזכה בהטבת מס לפי סעיף 46', html)
        description = re.search(r'<meta name="description" content="([^"]+)"', html).group(1)
        for term in ('חשופיות הים', 'חינניות הים', 'הים התיכון'):
            self.assertIn(term, description)

    def test_english_page(self):
        html = self.client.get('/support/?lang=en').content.decode()
        self.assertIn('<html lang="en" dir="ltr">', html)
        self.assertIn('<title>Support Sea Slug Research | SeaSlugs</title>', html)
        self.assertIn('Support the SeaSlugs Project', html)
        self.assertIn('Support the Project via PayPal', html)
        self.assertIn('not eligible for Israeli tax deductions under Section 46', html)
        self.assertIn('The website is freely accessible to everyone.', html)
        self.assertNotIn('תמיכה בפרויקט באמצעות PayPal', html)

    def test_paypal_link(self):
        html = self.client.get('/support/').content.decode()
        self.assertIn(f'id="support-paypal" href="{PAYPAL}"', html)
        self.assertNotIn('<input', re.search(r'<div class="support">.*?</div>\s*<script>', html, re.S).group(0))

    def test_never_presents_itself_as_a_charity(self):
        html = self.client.get('/support/?lang=en').content.decode().lower()
        for phrase in ('registered charity', 'non-profit', 'nonprofit', 'tax-deductible', 'donation receipt'):
            self.assertNotIn(phrase, html)

    def test_canonical_and_hreflang(self):
        html = self.client.get('/support/?lang=en').content.decode()
        self.assertRegex(html, r'<link rel="canonical" href="https://[^"]+/support/\?lang=en">')
        self.assertRegex(html, r'<link rel="alternate" hreflang="he" href="https://[^"]+/support/">')

    def test_signed_in_member_also_sees_it(self):
        user = get_user_model().objects.create_user('member', password='pw')
        self.client.force_login(user)
        self.assertEqual(self.client.get('/support/').status_code, 200)

    @override_settings(PAYPAL_SUPPORT_URL='https://evil.example.com/pay')
    def test_a_non_paypal_link_counts_as_no_link(self):
        self.assertEqual(self.client.get('/support/').status_code, 404)

    @override_settings(PAYPAL_SUPPORT_URL='http://www.paypal.com/ncp/payment/X')
    def test_a_plain_http_link_counts_as_no_link(self):
        self.assertEqual(self.client.get('/support/').status_code, 404)


class SupportSwitchTests(TestCase):
    """SUPPORT_ENABLED switches the option without a code change: off -> /support/ is 404, no menu or footer link,
    no sitemap entry; on -> all of them. The thank-you page (PayPal's return address) stays reachable either way."""

    @OFF
    def test_off(self):
        self.assertEqual(self.client.get('/support/').status_code, 404)
        self.assertNotIn('/support/', self.client.get('/forum/').content.decode())
        self.assertNotIn('/support/', self.client.get('/').content.decode())
        self.assertNotIn('/support/', self.client.get('/sitemap.xml').content.decode())
        self.assertEqual(self.client.get('/support/thank-you/').status_code, 200)

    @ON
    def test_on(self):
        self.assertEqual(self.client.get('/support/').status_code, 200)
        self.assertIn('href="/support/"', self.client.get('/forum/').content.decode())
        self.assertIn('/support/</loc>', self.client.get('/sitemap.xml').content.decode())

    def test_settings_default_follows_the_environment(self):
        # Unset: off in production, on locally (config/settings.py).
        source = (settings.BASE_DIR / 'config' / 'settings.py').read_text()
        self.assertIn('SUPPORT_ENABLED = (_support_enabled in ("1", "true", "yes", "on")) if _support_enabled else not PRODUCTION', source)
        self.assertIn('PAYPAL_SUPPORT_URL = os.environ.get("PAYPAL_SUPPORT_URL"', source)


@ON
class SupportNavigationTests(TestCase):
    """The "תמיכה בפרויקט" / "Support the Project" link is in the shared main menu (account_menu.html, on every
    public page: gallery, species, genus, taxon, trip and community pages) and in the gallery's footer, in the page's
    language -- but never on the management tools under /admin/."""

    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('admin', password='pw')

    def test_menu_link_on_a_community_page_in_both_languages(self):
        he = self.client.get('/news/').content.decode()
        self.assertIn('href="/support/"', he)
        self.assertIn('data-he="תמיכה בפרויקט" data-en="Support the Project">תמיכה בפרויקט</span>', he)
        en = self.client.get('/news/?lang=en').content.decode()
        self.assertIn('href="/support/?lang=en"', en)
        self.assertIn('>Support the Project</span>', en)

    def test_gallery_menu_and_footer(self):
        html = self.client.get('/').content.decode()
        self.assertIn('<a class="footer-support" href="/support/" data-support-link', html)
        menu = html.split('id="accountMenuList"')[1].split('</nav>')[0]
        self.assertIn('href="/support/"', menu)
        en = self.client.get('/?lang=en').content.decode()
        self.assertIn('href="/support/?lang=en" data-support-link', en)
        self.assertIn('>Support the Project</a>', en)

    def test_every_standalone_public_template_uses_the_shared_menu(self):
        # species, genus, taxon and trip pages do not extend base.html; they include the same menu.
        templates = settings.BASE_DIR / 'observations' / 'templates' / 'observations'
        for name in ('base.html', 'species_page.html', 'genus_page.html', 'taxon_page.html', 'trip_page.html'):
            self.assertIn("{% include 'observations/account_menu.html' %}", (templates / name).read_text(), name)
        self.assertIn("{% include 'observations/account_menu.html' %}", (settings.BASE_DIR / 'dist' / 'index.html').read_text())
        self.assertIn('{% if support_link %}', (templates / 'account_menu.html').read_text())

    def test_not_on_the_admin_tools(self):
        self.client.force_login(self.admin)
        for url in ('/admin/images/', '/admin/table-transfer/', '/admin/releases/'):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('/support/', response.content.decode(), url)
        self.assertIn('href="/support/"', self.client.get('/observations/').content.decode())

    def test_app_js_swaps_the_footer_link_language(self):
        js = (settings.BASE_DIR / 'dist' / 'app.js').read_text()
        self.assertIn("document.querySelectorAll('[data-forum-link], [data-support-link]')", js)


class ThankYouPageTests(TestCase):
    """/support/thank-you/ (PayPal's auto-return address): a thank-you in Hebrew or English -- the language the
    visitor used before PayPal comes back through the seaslugs_lang cookie -- with a button back to the home page;
    no sign-in; noindex, follow; never in the sitemap; and nothing that treats the visit as a payment (no amount, no
    transaction id, no "verified")."""

    def test_hebrew(self):
        response = self.client.get('/support/thank-you/')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('<html lang="he" dir="rtl">', html)
        self.assertIn('תודה על תמיכתך בפרויקט SeaSlugs!', html)
        self.assertIn('<a class="button" href="/">חזרה לאתר</a>', html)

    def test_english(self):
        html = self.client.get('/support/thank-you/?lang=en').content.decode()
        self.assertIn('<html lang="en" dir="ltr">', html)
        self.assertIn('Thank you for supporting the SeaSlugs Project!', html)
        self.assertIn('<a class="button" href="/?lang=en">Return to SeaSlugs</a>', html)

    @ON
    def test_language_chosen_before_paypal_is_kept(self):
        self.client.get('/support/?lang=en')  # sets the seaslugs_lang cookie
        html = self.client.get('/support/thank-you/').content.decode()
        self.assertIn('Thank you for supporting the SeaSlugs Project!', html)

    def test_noindex(self):
        response = self.client.get('/support/thank-you/')
        self.assertIn('<meta name="robots" content="noindex, follow">', response.content.decode())
        self.assertEqual(response['X-Robots-Tag'], 'noindex, follow')

    @ON
    def test_never_in_the_sitemap(self):
        self.assertNotIn('thank-you', self.client.get('/sitemap.xml').content.decode())

    def test_shows_no_payment_details(self):
        html = self.client.get('/support/thank-you/?lang=en&amt=50&tx=ABC123&st=Completed').content.decode()
        for text in ('ABC123', 'Completed', '50', 'verified', 'receipt', 'transaction'):
            self.assertNotIn(text, html.split('<main>')[1])


@ON
class SupportAnalyticsTests(TestCase):
    """GA4 through the site's existing tag only (no second tag): support_page_view and support_paypal_click on the
    support page, support_thank_you_view on the thank-you page, with language / payment_provider (/ currency on the
    click) and nothing personal; never a purchase event or a revenue value; and still no tag under /admin/."""

    def test_events_on_the_support_page(self):
        html = self.client.get('/support/?lang=en').content.decode()
        self.assertEqual(html.count('googletagmanager.com/gtag/js'), 1)
        self.assertIn("gtag('event', 'support_page_view', params)", html)
        self.assertIn("var params = {language: 'en', payment_provider: 'paypal'};", html)
        self.assertIn("gtag('event', 'support_paypal_click', {", html)
        self.assertIn("currency: 'ILS'", html)

    def test_event_on_the_thank_you_page(self):
        html = self.client.get('/support/thank-you/').content.decode()
        self.assertEqual(html.count('googletagmanager.com/gtag/js'), 1)
        self.assertIn("gtag('event', 'support_thank_you_view', {language: 'he', payment_provider: 'paypal'});", html)

    def test_no_purchase_or_revenue(self):
        for url in ('/support/', '/support/thank-you/'):
            html = self.client.get(url).content.decode()
            self.assertNotIn("'purchase'", html)
            self.assertNotIn('value:', html)
            self.assertNotIn('transaction_id', html)

    def test_opt_out_cookie_still_removes_the_tag(self):
        self.client.cookies['exclude_analytics'] = '1'
        html = self.client.get('/support/').content.decode()
        self.assertNotIn('googletagmanager.com/gtag/js', html)

    def test_admin_tools_still_have_no_tag(self):
        self.client.force_login(get_user_model().objects.create_superuser('admin', password='pw'))
        response = self.client.get('/admin/table-transfer/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('googletagmanager.com/gtag/js', response.content.decode())


@ON
class SupportPhotoTests(TestCase):
    """The support page's picture comes from the site's own photos: the defining photo of a published Mediterranean
    gallery observation, Israel first, with the species name (genus + epithet in italics) linking to its species page
    and the photographer's credit; no picture (and no error) when there is none, never an outside image."""

    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('admin', password='pw')
        israel = Country.objects.create(name='ישראל', name_en='Israel')
        med = Sea.objects.create(name='ים התיכון', name_en='Mediterranean Sea')
        philippines = Country.objects.create(name='פיליפינים', name_en='Philippines')
        scs = Sea.objects.create(name='ים סין הדרומי', name_en='South China Sea')
        self.trips = {
            'med': DiveTrip.objects.create(code='M', title='שדות ים', year=2024, month=6, country=israel,
                                           region=Region.objects.create(name='ישראל - צפון', name_en='Israel - North', country=israel, sea=med)),
            'ph': DiveTrip.objects.create(code='P', title='אנילאו', year=2024, month=3, country=philippines,
                                          region=Region.objects.create(name='פיליפינים - אנילאו', name_en='Philippines - Anilao', country=philippines, sea=scs)),
        }

    def observe(self, name, trip, image=True):
        species = Species.objects.create(scientific_name=name, genus=name.split()[0], species=name.split()[1], author='Author, 1900')
        sample = Sample(owner=self.admin, kind='species', trip=self.trips[trip], species=species, video_url=f'https://youtu.be/{str(Species.objects.count()).zfill(11)}')
        sample.save_reviewed(actor=self.admin, approve=True)
        if image:
            Sample.objects.filter(pk=sample.pk).update(image='samples/x.jpg')
        return sample

    def test_no_photo_no_picture(self):
        html = self.client.get('/support/').content.decode()
        self.assertNotIn('class="support-photo"', html)

    def test_mediterranean_photo_from_the_site(self):
        self.observe('Chromodoris annae', 'ph')
        sample = self.observe('Cratena peregrina', 'med')
        area = SpeciesArea.objects.get(species=sample.species)
        html = self.client.get('/support/').content.decode()
        self.assertIn(f'<img src="/observations/{sample.pk}/photo/" alt="Cratena peregrina"', html)
        self.assertIn(f'<a href="/species/{area.slug}/" dir="ltr"><i>Cratena peregrina</i></a>', html)
        self.assertNotIn('Chromodoris annae', html)

    def test_only_outside_the_mediterranean_means_no_picture(self):
        self.observe('Chromodoris annae', 'ph')
        self.assertNotIn('class="support-photo"', self.client.get('/support/').content.decode())


class SupportPrivacyTests(TestCase):
    """No payment data is kept: the feature adds no model, table or migration."""

    def test_no_new_model(self):
        source = (settings.BASE_DIR / 'observations' / 'support.py').read_text()
        self.assertNotIn('models.Model', source)
        migrations = [p.name for p in (settings.BASE_DIR / 'observations' / 'migrations').glob('*.py')]
        self.assertFalse([m for m in migrations if 'support' in m or 'donat' in m or 'payment' in m])
