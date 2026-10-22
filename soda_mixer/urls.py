"""URL configuration for soda_mixer project."""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse

def readyz(request):
    return HttpResponse("OK", content_type="text/plain", status=200)

def livez(request):
    return HttpResponse("OK", content_type="text/plain", status=200)

def healthz(request):
    return HttpResponse("OK", content_type="text/plain", status=200)

urlpatterns = [
    path('readyz', readyz, name='readyz'),
    path('readyz/', readyz, name='readyz_slash'),
    path('livez', livez, name='livez'),
    path('livez/', livez, name='livez_slash'),
    path('healthz', healthz, name='healthz'),
    path('healthz/', healthz, name='healthz_slash'),
    path('admin/', admin.site.urls),
    path('', include('soda_mixer.flavors.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
