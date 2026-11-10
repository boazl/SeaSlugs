"""Editing a site-written article on the site itself (not in the admin) -- for the organizer of a dive trip the
article belongs to, e.g. the schedule of a planned trip (planned_trips.py).

- **Who:** the owner of the trip's discussion observation (its planning, else its collection observation:
  forum.trip_observation) for an article picked by that trip, and the site managers. Only articles written on the
  site (sections); a PDF article is managed in the admin.
- **What:** the titles and subtitles in both languages, and the sections: kind, order, title and text in Hebrew and
  English; sections can be added and deleted. A table section takes `|`-separated cells or a table pasted from Excel
  (article_render.table_rows). Figures (a section showing an observation's photo) are kept as they are and edited in
  the admin by a manager.
- `/articles/<slug>/edit/`; the article page shows "עריכת מאמר" -- the admin for staff, this page for the organizer.
"""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.forms import inlineformset_factory
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .i18n import get_lang
from .models import Article, ArticleBlock
from .templatetags.seaslugs_i18n import with_lang


def can_edit_on_site(user, article):
    if not (user.is_authenticated and article.is_written):
        return False
    from .forum import is_site_manager, trip_observation
    if is_site_manager(user):
        return True
    for trip in article.trips.all():
        owner_sample = trip_observation(trip)
        if owner_sample is not None and owner_sample.owner_id == user.pk and owner_sample.deleted_at is None:
            return True
    return False


class ArticleSiteForm(forms.ModelForm):
    class Meta:
        model = Article
        fields = ['title_he', 'title_en', 'subtitle_he', 'subtitle_en']

    def clean(self):
        data = super().clean()
        if not ((data.get('title_he') or '').strip() or (data.get('title_en') or '').strip()):
            raise forms.ValidationError('יש למלא כותרת בעברית או באנגלית.')
        return data


class BlockForm(forms.ModelForm):
    kind = forms.ChoiceField(choices=[c for c in ArticleBlock.Kind.choices if c[0] != ArticleBlock.Kind.FIGURE], label='סוג הקטע')

    class Meta:
        model = ArticleBlock
        fields = ['position', 'kind', 'title_he', 'title_en', 'text_he', 'text_en']
        widgets = {'text_he': forms.Textarea(attrs={'rows': 6}), 'text_en': forms.Textarea(attrs={'rows': 6})}


class BlockFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        kept = [f for f in self.forms if f.cleaned_data and not f.cleaned_data.get('DELETE')
                and ((f.cleaned_data.get('text_he') or '').strip() or (f.cleaned_data.get('text_en') or '').strip()
                     or (f.cleaned_data.get('title_he') or '').strip() or (f.cleaned_data.get('title_en') or '').strip())]
        figures = self.instance.blocks.filter(kind=ArticleBlock.Kind.FIGURE).exists() if self.instance.pk else False
        if not kept and not figures:
            raise forms.ValidationError('למאמר צריך לפחות קטע אחד עם תוכן.')


Blocks = inlineformset_factory(Article, ArticleBlock, form=BlockForm, formset=BlockFormSet, extra=1, can_delete=True)


@login_required
def article_edit(request, slug):
    lang = get_lang(request)
    article = get_object_or_404(Article, slug=slug)
    if not can_edit_on_site(request.user, article):
        raise Http404
    queryset = article.blocks.exclude(kind=ArticleBlock.Kind.FIGURE).order_by('position', 'pk')
    form = ArticleSiteForm(request.POST or None, instance=article)
    blocks = Blocks(request.POST or None, instance=article, queryset=queryset, prefix='blocks')
    if request.method == 'POST' and form.is_valid() and blocks.is_valid():
        form.save()
        saved = blocks.save(commit=False)
        for block in blocks.deleted_objects:
            block.delete()
        for block in saved:
            if not any((block.text_he.strip(), block.text_en.strip(), block.title_he.strip(), block.title_en.strip())):
                continue            # an empty new section is not added
            block.article = article
            block.save()
        messages.success(request, 'המאמר נשמר.')
        return redirect(with_lang(reverse('article-page', args=[article.slug]), lang))
    return render(request, 'observations/article_edit.html', {
        'article': article, 'form': form, 'blocks': blocks,
        'figures': article.blocks.filter(kind=ArticleBlock.Kind.FIGURE).count(),
        'back_url': with_lang(reverse('article-page', args=[article.slug]), lang)})
