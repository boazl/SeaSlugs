"""Articles without a picture (a site-written article with no figure, and no PDF preview) show a table icon instead of
an empty image -- in the article library and in the article links on the site's pages."""
from django.template.loader import render_to_string
from django.test import TestCase

from .articles import article_links
from .models import Article, ArticleBlock


class ArticleTableIconTests(TestCase):
    """No picture: a table icon (inline SVG), never an <img> with an empty address."""

    def setUp(self):
        self.article = Article.objects.create(slug='visayas-2027-schedule', title_he='לוח זמנים: ויסאיאס 2027')
        ArticleBlock.objects.create(article=self.article, kind=ArticleBlock.Kind.TABLE, position=10,
                                    text_he='יום | אתר\n1 | בוהול')

    def test_library(self):
        html = self.client.get('/articles/').content.decode()
        item = html.split(f'id="{self.article.slug}"')[1].split('</li>')[0]
        self.assertIn('class="article-icon"', item)
        self.assertNotIn('src=""', item)

    def test_links_on_pages(self):
        links = article_links([self.article], 'he')
        self.assertEqual(links[0]['thumb_url'], '')
        html = render_to_string('observations/_article_links.html', {'links': links, 'lang': 'he'})
        self.assertIn('class="article-icon"', html)
        self.assertNotIn('<img', html)
