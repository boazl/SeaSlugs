from django.contrib import admin
from django.urls import path, include
from .views import gallery_file, health
from observations.transfer_views import transfer
from observations.release_views import releases
from observations.image_manager import manager as image_manager, image_file

urlpatterns = [
    path('admin/images/',image_manager,name='image-manager'),
    path('admin/images/file/',image_file,name='image-file'),
    path('admin/releases/', releases, name='releases'),
    path('admin/table-transfer/', transfer, name='table-transfer'),
    path('observations/', include('observations.urls')),
    path('healthz', health, name='health'),
    path('admin/', admin.site.urls),
    path('', gallery_file, name='gallery'),
    path('<str:filename>', gallery_file, name='gallery-file'),
]
