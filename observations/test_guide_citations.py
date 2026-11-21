"""Guides and other publications linked to species by their sources (guide_citations.py, migrations 0117 / 0118)."""
import json
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.contrib import admin
from django.core.files.uploadedfile import SimpleUploadedFile

from . import article_transfer
from .guide_citations import link_species
from .models import Article, Species, SpeciesPublicationName
from .test_bibliography import Fixture

NSSI2 = 'NSSI-2 Gosliner, Valdés & Behrens, 2018'
NSSI3 = 'NSSI-3 Gosliner, Valdés & Behrens, 2026'


def guides():
    return (Article.objects.create(slug='nssi-2', title_en='NSSI 2nd edition', kind='guide', short_ref=NSSI2,
                                   citation='Gosliner et al. (2018).'),
            Article.objects.create(slug='nssi-3', title_en='NSSI 3rd edition', kind='guide', short_ref=NSSI3,
                                   citation='Gosliner et al. (2026).'))


class PublicationNameTests(Fixture):
    """A species is linked to a publication of the library by its sources only, like the papers that describe species:
    by its name source (every gallery "sp. N" was named by the 2nd edition of Gosliner, Valdés & Behrens) and by a
    name under which it appears in a publication (SpeciesPublicationName, e.g. its 3rd-edition name and pages) -- not
    by a citation in its texts. The link then says how the species appears there ("Appears in it as Marioniopsis
    sp. 11, pp. 282-283", or "under the same name"), on the species page and in the library; the guide counts as used
    on the article-files page; saving a species in the admin adds the links (never removes one); the names travel
    with the article transfer."""

    def test_links_by_sources_not_by_texts(self):
        g2, g3 = guides()
        sp = self.species('Marionia sp. 6', name_source=NSSI2,
                          identification_en='Small. (after Gosliner, Valdés & Behrens 2026, 3rd ed., pp. 282-283)')
        self.assertEqual(link_species(sp), [g2])
        SpeciesPublicationName.objects.create(species=sp, article=g3, name='Marioniopsis sp. 11', pages='282-283')
        self.assertEqual(link_species(sp), [g3])
        self.assertEqual(link_species(sp), [])
        from .article_files import unused_articles
        self.assertFalse({g2, g3} & set(unused_articles()))

    def test_species_page_and_library_say_how_the_species_appears(self):
        g2, g3 = guides()
        renamed = self.species('Marionia sp. 6', name_source=NSSI2)
        same = self.species('Tenellia sp. 18', name_source=NSSI2)
        SpeciesPublicationName.objects.create(species=renamed, article=g3, name='Marioniopsis sp. 11', pages='282-283')
        SpeciesPublicationName.objects.create(species=same, article=g3, name='Tenellia sp. 18', pages='328-329')
        for sp in (renamed, same):
            link_species(sp)
            self.observe(sp)
        page = self.client.get(f'/species/{renamed.areas.get().slug}/?lang=en').content.decode()
        self.assertIn('Appears in it as <bdi dir="ltr"><i>Marioniopsis</i> sp. 11</bdi>, <bdi>pp. 282-283</bdi>', page)
        self.assertIn('(Source: <a class="name-source" href="/articles/?lang=en#nssi-2"', page)
        page = self.client.get(f'/species/{same.areas.get().slug}/?lang=he').content.decode()
        self.assertIn('מופיע בו באותו שם, <bdi>עמ׳ 328-329</bdi>', page)
        library = self.client.get('/articles/?lang=en').content.decode()
        self.assertIn('(as <bdi dir="ltr"><i>Marioniopsis</i> sp. 11</bdi>, <bdi>pp. 282-283</bdi>)', library)
        self.assertIn('(same name, <bdi>pp. 328-329</bdi>)', library)
        self.assertEqual(library.count('<i>Tenellia</i> sp. 18'), 2)       # source of the name (2nd) + shown on (3rd)

    def test_admin_save_adds_the_links_and_keeps_hand_picked_ones(self):
        g2, g3 = guides()
        paper = Article.objects.create(slug='paper', title_en='Paper', kind='description', citation='X (2020).')
        sp = self.species('Tenellia sp. 17', name_source=NSSI2)
        SpeciesPublicationName.objects.create(species=sp, article=g3, name='Tenellia sp. 15', pages='328-329')
        form = SimpleNamespace(instance=sp, save_m2m=lambda: sp.articles.set([paper]))   # the form's own picks
        admin.site._registry[Species].save_related(None, form, [], True)
        self.assertEqual(set(sp.articles.all()), {paper, g2, g3})

    def test_transfer_carries_the_names(self):
        _g2, g3 = guides()
        sp = self.species('Tenellia sp. 17', name_source=NSSI2)
        SpeciesPublicationName.objects.create(species=sp, article=g3, name='Tenellia sp. 15', pages='328-329')
        entry = article_transfer.article_entry(g3)
        self.assertEqual(entry['species_names'], [['Tenellia sp. 17', 'Tenellia sp. 15', '328-329']])
        document = article_transfer.article_document(g3)
        SpeciesPublicationName.objects.all().delete()
        g3.species.clear()
        upload = SimpleUploadedFile('nssi-3.article.json', json.dumps(document).encode())
        with patch('observations.table_transfer.create_backup', return_value=Path('test.sqlite3')):
            article_transfer.receive([upload])
        self.assertEqual(list(sp.publication_names.values_list('name', 'pages')), [('Tenellia sp. 15', '328-329')])
        self.assertIn(g3, sp.articles.all())
        old = {k: v for k, v in entry.items() if k != 'species_names'}
        self.assertTrue(article_transfer._valid_entry(old))
        self.assertFalse(article_transfer._valid_entry({**entry, 'species_names': [['x', '', '']]}))


class EditionsMigrationTests(Fixture):
    """Migration 0117: the 14 "sp. N" that 0110 gave the 3rd edition as name source go back to the 2nd (the labels on
    the photos say 2018); the 3rd edition gets the names of 0107's 3rd-edition accounts and is linked only to those
    species; the links 0116 made from citations in texts are removed. Safe to run again."""

    def test_migration(self):
        g2, g3 = guides()
        same = self.species('Tenellia sp. 18', name_source=NSSI3)
        renamed = self.species('Marionia sp. 6', name_source=NSSI2)
        absent = self.species('Atagema sp. 13', name_source=NSSI2)
        letter = self.species('Okenia sp. B')
        for sp in (same, renamed, absent, letter):          # what 0116 linked by the texts
            sp.articles.add(g2, g3)
        migration = import_module('observations.migrations.0117_species_publication_names')
        for _ in range(2):
            migration.forward(apps, None)
        same.refresh_from_db()
        self.assertEqual(same.name_source, NSSI2)
        self.assertEqual(set(g2.species.all()), {same, renamed, absent})
        self.assertEqual(set(g3.species.all()), {same, renamed})
        self.assertEqual(list(renamed.publication_names.values_list('name', 'pages')), [('Marioniopsis sp. 11', '282-283')])
        self.assertEqual(list(same.publication_names.values_list('name', 'pages')), [('Tenellia sp. 18', '328-329')])
        self.assertFalse(absent.publication_names.exists())


class EditionIssuesMigrationTests(Fixture):
    """Migration 0118: the open "update the name by the 3rd edition" issues get the source of the new name with the
    corrected name ("Aegires sp. 13 (NSSI-3 Gosliner, Valdés & Behrens, 2026)"); a change of number only (same genus)
    gets a low priority, a move to another genus keeps its own. Closed rows, rows without a bare "Genus sp. N" and
    other kinds are left alone; safe to run again."""

    def test_migration(self):
        from .models import IdentificationIssue as Issue
        number = Issue.objects.create(kind='book_edition', priority=1, species=self.species('Aegires sp. 8'),
                                      corrected_name='Aegires sp. 13')
        genus = Issue.objects.create(kind='book_edition', priority=1, species=self.species('Marionia sp. 6'),
                                     corrected_name='Marioniopsis sp. 11')
        closed = Issue.objects.create(kind='book_edition', priority=1, status='fixed', species=self.species('Tenellia sp. 17'),
                                      corrected_name='Tenellia sp. 15')
        missing = Issue.objects.create(kind='book_edition', priority=2, species=self.species('Stiliger sp. 1'))
        worms = Issue.objects.create(kind='worms_name', priority=1, species=self.species('Thecacera sp. 8'),
                                     corrected_name='Thecacera pikachu Pola et al., 2026')
        migration = import_module('observations.migrations.0118_book_edition_issue_names')
        for _ in range(2):
            migration.forward(apps, None)
        rows = {i.pk: (i.corrected_name, i.priority) for i in Issue.objects.all()}
        self.assertEqual(rows[number.pk], (f'Aegires sp. 13 ({NSSI3})', 3))
        self.assertEqual(rows[genus.pk], (f'Marioniopsis sp. 11 ({NSSI3})', 1))
        self.assertEqual(rows[closed.pk], ('Tenellia sp. 15', 1))
        self.assertEqual(rows[missing.pk], ('', 2))
        self.assertEqual(rows[worms.pk], ('Thecacera pikachu Pola et al., 2026', 1))
