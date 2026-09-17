from django.urls import path
from django.contrib.auth import views as auth
from . import views
urlpatterns=[
 path('trips/',views.trips,name='dive-trips'),
 path('',views.listing,name='observations'),
 path('new/',views.edit,name='observation-new'),
 path('species-search/',views.species_search,name='species-search'),
 path('species-area-status/',views.species_area_status,name='species-area-status'),
 path('trips/new/',views.trip_new,name='trip-new'),
 path('<int:pk>/edit/',views.edit,name='observation-edit'),
 path('<int:pk>/remove/',views.remove,name='observation-remove'),
 path('<int:pk>/photo/',views.photo,name='observation-photo'),
 path('signup/',views.signup,name='signup'),
 path('login/',auth.LoginView.as_view(template_name='observations/login.html'),name='login'),
 path('logout/',auth.LogoutView.as_view(),name='logout'),
 path('profile/',views.profile,name='profile'),
 path('partners/',views.partners,name='partners'),
]
