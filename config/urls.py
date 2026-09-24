from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from .views import gallery_file, health
from observations.transfer_views import transfer
from observations.release_views import releases
from observations.image_manager import manager as image_manager, image_file

from observations.folder_import import folder_import
from observations.views import site_image, species_page, species_article
from observations.db_replace import db_replace, db_replace_download

urlpatterns = [
    path('admin/images/folder/',folder_import,name='folder-import'),
    path('admin/images/',image_manager,name='image-manager'),
    path('admin/images/file/',image_file,name='image-file'),
    path('admin/releases/', releases, name='releases'),
    path('admin/table-transfer/', transfer, name='table-transfer'),
    path('admin/db-replace/', db_replace, name='db-replace'),
    path('admin/db-replace/download/', db_replace_download, name='db-replace-download'),
    path('observations/', include('observations.urls')),
    path('healthz', health, name='health'),
    path('site-image/<slug:key>.jpg', site_image, name='site-image'),
    path('species/<slug:slug>/', species_page, name='species-page'),
    path('species/<slug:slug>/article.pdf', species_article, name='species-article'),
    path('admin/', admin.site.urls),
    path('', gallery_file, name='gallery'),
    path('<str:filename>', gallery_file, name='gallery-file'),
]

if settings.DEBUG:
    # Local dev only -- production never serves MEDIA_ROOT directly (Sample.image and
    # SiteImage.image are only ever meant to be reached through the access-controlled
    # observation-photo/site-image views), but Django's own admin and form widgets (e.g.
    # ClearableFileInput's "Currently: <a>" link on the image field) link straight to
    # image.url, which is MEDIA_URL + name -- so without this, following that link 404s.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
