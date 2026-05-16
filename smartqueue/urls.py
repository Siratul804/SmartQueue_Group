"""URL routing and error handlers for SmartQueue."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from smartqueue import views as sq_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('apps.accounts.urls')),
    path('queue/', include('apps.queue.urls')),
    path('', include('apps.organizations.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler404 = sq_views.Handler404View.as_view()
handler403 = sq_views.Handler403View.as_view()
