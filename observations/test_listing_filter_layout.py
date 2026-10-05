import re
from django.contrib.auth.models import User
from django.test import TestCase


class ListingFilterLayoutTests(TestCase):
    """At half-screen width the observations filters were cramped and touching: the global
    `select{min-width:230px}` is wider than the 200px grid track, so each select overflowed
    into its neighbour. The filter form must make its controls fill their own grid cell."""
    def setUp(self):
        self.user = User.objects.create_user('u', password='x')
        self.client.force_login(self.user)
        self.html = self.client.get('/observations/').content.decode()

    def _rule(self, selector):
        match = re.search(re.escape(selector) + r'\{([^}]*)\}', self.html)
        self.assertIsNotNone(match, selector)
        return match.group(1)

    def test_filter_controls_fill_their_grid_cell_instead_of_overflowing(self):
        rule = self._rule('.filter-row select,.filter-row input[type=text]')
        self.assertIn('width:100%', rule)
        self.assertIn('min-width:0', rule)

    def test_filter_grid_has_generous_gaps_and_a_panel_frame(self):
        rule = self._rule('.filter-row')
        self.assertIn('gap:18px 24px', rule)
        self.assertIn('padding:18px', rule)
        self.assertIn('margin:0 0 28px', rule)

    def test_buttons_get_their_own_full_width_row(self):
        self.assertIn('grid-column:1/-1', self._rule('.filter-actions'))

    def test_mine_checkbox_label_is_laid_out_inline(self):
        self.assertIn('class="filter-check"', self.html)
        self.assertIn('flex-direction:row', self._rule('.filter-row label.filter-check'))
