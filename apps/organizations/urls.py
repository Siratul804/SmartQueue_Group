from django.urls import path

from apps.organizations import views, organizer_views

app_name = 'organizations'

urlpatterns = [
    # Public views
    path('', views.OrganizationListView.as_view(), name='organization_list'),
    path('<slug:slug>/', views.OrganizationDetailView.as_view(), name='organization_detail'),

    # Organizer Portal
    path('organizer/<slug:slug>/dashboard/', organizer_views.OrganizerDashboardView.as_view(), name='organizer_dashboard'),
    path('organizer/<slug:slug>/bookings/', organizer_views.OrganizerBookingListView.as_view(), name='organizer_booking_list'),
    path('organizer/<slug:slug>/services/', organizer_views.OrganizerServiceListView.as_view(), name='organizer_service_list'),
    path('organizer/<slug:slug>/services/add/', organizer_views.OrganizerServiceCreateView.as_view(), name='organizer_service_create'),
    path('organizer/<slug:slug>/services/<int:service_id>/edit/', organizer_views.OrganizerServiceUpdateView.as_view(), name='organizer_service_update'),
    path('organizer/<slug:slug>/profile/', organizer_views.OrganizerProfileUpdateView.as_view(), name='organizer_profile_update'),
    
    # New Organizer Self-Service
    path('organizer/my-organizations/', organizer_views.OrganizerOrganizationListView.as_view(), name='organizer_org_list'),
    path('organizer/create-organization/', organizer_views.OrganizationCreateView.as_view(), name='organization_create'),
]
#hello