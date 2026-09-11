from django.contrib import admin
from django.urls import path
from .views import gallery_file

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', gallery_file, name='gallery'),
    path('<str:filename>', gallery_file, name='gallery-file'),
]
