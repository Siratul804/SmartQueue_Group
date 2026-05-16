from django.urls import path

from apps.queue import views

app_name = 'queue'

urlpatterns = [
    path('book/<slug:org_slug>/<int:service_id>/', views.BookTokenView.as_view(), name='book_token'),
    path('status/<int:token_id>/', views.TokenStatusView.as_view(), name='token_status'),
    path('my-tokens/', views.MyTokensView.as_view(), name='my_tokens'),
    path('emergency/<int:token_id>/', views.EmergencyRequestView.as_view(), name='emergency_request'),
    path('cancel/<int:token_id>/', views.CancelTokenView.as_view(), name='cancel_token'),
    path('admin/org/<int:org_id>/', views.AdminDashboardView.as_view(), name='admin_dashboard'),
    path('admin/call/<int:org_id>/', views.CallNextTokenView.as_view(), name='call_next_token'),
    path('admin/start/<int:token_id>/', views.StartServiceView.as_view(), name='start_service'),
    path('admin/complete/<int:token_id>/', views.CompleteServiceView.as_view(), name='complete_service'),
    path('admin/approve-emergency/<int:token_id>/', views.ApproveEmergencyView.as_view(), name='approve_emergency'),
]
