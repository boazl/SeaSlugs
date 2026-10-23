"""Reads a bilingual article prepared as two HTML pages (Hebrew and English, the same structure) into an article
written on the site: its title, subtitle, credit and editorial note, its sections (ArticleBlock) and its references.
Only what is inside <article class="article-body"> is read. Inline formatting becomes the site's light markup
(<i>/<em> -> *italics*, <strong> -> **bold**, <a> -> [text](link)); a figure's photo is the observation given for
it (the figures' observation numbers differ between the environments, so they are passed in, in order); the
"observations on the site" list is kept as written, its links to this site made relative (the page adds the
visitor's language), so they work in both environments."""
import re
from html.parser import HTMLParser

SITE_URL = re.compile(r'^https?://(?:www\.)?seaslugs\.org\.il(?=/)')
REFERENCE_HEADINGS = {'מקורות וקישורים', 'References and links'}


class Node:
    def __init__(self, tag, attrs=None, parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs or {}), parent, []

    @property
    def classes(self):
        return set((self.attrs.get('class') or '').split())

    def elements(self):
        return [c for c in self.children if isinstance(c, Node)]

    def find(self, tag):
        for child in self.elements():
            if child.tag == tag:
                return child
            found = child.find(tag)
            if found:
                return found
        return None

    def find_all(self, tag):
        out = []
        for child in self.elements():
            if child.tag == tag:
                out.append(child)
            out += child.find_all(tag)
        return out


VOID = {'img', 'br', 'hr', 'meta', 'link', 'input'}


class TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node('root')
        self.current = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.current)
        self.current.children.append(node)
        if tag not in VOID:
            self.current = node

    def handle_endtag(self, tag):
        node = self.current
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.current = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def parse(html):
    builder = TreeBuilder()
    builder.feed(html)
    for node in builder.root.find_all('article'):
        if 'article-body' in node.classes:
            return node
    raise ValueError('לא נמצא <article class="article-body"> בקובץ.')


def markup(node):
    """The node's content as the site's light markup, whitespace collapsed."""
    def walk(n):
        if isinstance(n, str):
            return n
        inner = ''.join(walk(c) for c in n.children)
        if n.tag in ('i', 'em'):
            return f'*{inner.strip()}*' if inner.strip() else inner
        if n.tag in ('strong', 'b'):
            return f'**{inner.strip()}**' if inner.strip() else inner
        if n.tag == 'a' and n.attrs.get('href'):
            href = n.attrs['href']
            if SITE_URL.match(href):        # a page of this site: relative, without the language
                href = re.sub(r'[?&]lang=(?:he|en)$', '', SITE_URL.sub('', href))
            return f'[{inner.strip()}]({href})'
        if n.tag == 'br':
            return '\n'
        return inner
    text = walk(node)
    return '\n'.join(' '.join(line.split()) for line in text.split('\n')).strip()


_FIGURE_NUMBER = re.compile(r'^\s*(?:איור|Figure)\s+\d+\.\s*')


def read(html):
    """{'title', 'subtitle', 'byline', 'editorial', 'blocks': [(kind, title, text)], 'references': [text]} of one language."""
    article = parse(html)
    result = {'title': '', 'subtitle': '', 'byline': '', 'editorial': '', 'blocks': [], 'references': []}
    blocks = result['blocks']
    in_references = False
    for node in article.elements():
        tag, classes = node.tag, node.classes
        if tag == 'h1':
            result['title'] = ' '.join(markup(node).replace('*', '').split())
        elif tag == 'p' and 'subtitle' in classes:
            result['subtitle'] = markup(node)
        elif tag == 'p' and 'byline' in classes:
            result['byline'] = markup(node)
        elif tag == 'p' and 'editorial' in classes:
            result['editorial'] = markup(node)
        elif tag == 'h2':
            heading = markup(node)
            in_references = heading in REFERENCE_HEADINGS
            if not in_references:
                blocks.append(('heading', '', heading))
        elif tag in ('ul', 'ol') and (in_references or 'refs' in classes):
            result['references'] += [markup(li) for li in node.elements() if li.tag == 'li']
        elif tag == 'h3':
            blocks.append(('subheading', '', markup(node)))
        elif tag == 'p':
            text = markup(node)
            if blocks and blocks[-1][0] == 'paragraph':      # consecutive paragraphs: one section
                blocks[-1] = ('paragraph', '', blocks[-1][2] + '\n\n' + text)
            else:
                blocks.append(('paragraph', '', text))
        elif tag == 'figure':
            caption = node.find('figcaption')
            blocks.append(('figure', '', _FIGURE_NUMBER.sub('', markup(caption)) if caption else ''))
        elif tag == 'div' and 'table-wrap' in classes or tag == 'table':
            rows = []
            for tr in node.find_all('tr'):
                rows.append(' | '.join(markup(cell) for cell in tr.elements() if cell.tag in ('th', 'td')))
            blocks.append(('table', '', '\n'.join(rows)))
        elif tag == 'ul':
            blocks.append(('list', '', '\n'.join(markup(li) for li in node.elements() if li.tag == 'li')))
        elif tag == 'div' and 'notice' in classes:
            paragraphs = [p for p in node.elements() if p.tag == 'p'] or [node]
            title, texts = '', []
            for i, p in enumerate(paragraphs):
                text = markup(p)
                if i == 0:
                    match = re.match(r'^\*\*(.+?)\*\*\s*', text)
                    if match:
                        title, text = match.group(1), text[match.end():]
                if text:
                    texts.append(text)
            blocks.append(('notice', title, '\n\n'.join(texts)))
    return result


def import_article(article, he_html, en_html, figure_samples, drop_pdfs=False):
    """Fills `article` (an Article, saved or not) from the two pages; `figure_samples` are the observations of
    the figures, in order. Its sections and references are replaced. Returns the article."""
    from .models import ArticleBlock, ArticleReference
    he, en = read(he_html), read(en_html)
    if [b[0] for b in he['blocks']] != [b[0] for b in en['blocks']]:
        raise ValueError('המבנה של שני הקבצים שונה (סדר הקטעים אינו זהה).')
    figures = sum(1 for b in he['blocks'] if b[0] == 'figure')
    if len(figure_samples) != figures:
        raise ValueError(f'במאמר {figures} איורים, אבל נמסרו {len(figure_samples)} תצפיות.')
    article.title_he, article.title_en = he['title'], en['title']
    article.subtitle_he, article.subtitle_en = he['subtitle'], en['subtitle']
    article.byline_he, article.byline_en = he['byline'], en['byline']
    article.editorial_he, article.editorial_en = he['editorial'], en['editorial']
    if drop_pdfs:
        article.pdf_he = article.pdf_en = ''
    article.save()
    article.blocks.all().delete()
    article.references.all().delete()
    samples = iter(figure_samples)
    for i, ((kind, title_he, text_he), (_k, title_en, text_en)) in enumerate(zip(he['blocks'], en['blocks']), 1):
        ArticleBlock.objects.create(article=article, position=i * 10, kind=kind, title_he=title_he, title_en=title_en,
                                    text_he=text_he, text_en=text_en, sample=next(samples) if kind == 'figure' else None)
    for i, text in enumerate(en['references'] or he['references'], 1):     # the references are the same in both
        ArticleReference.objects.create(article=article, position=i * 10, text=text)
    return article
