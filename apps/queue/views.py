from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Avg, DurationField, ExpressionWrapper, F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView, DetailView, ListView, UpdateView

from apps.organizations.models import Organization, Service
from apps.queue.forms import EmergencyRequestForm, TokenBookingForm
from apps.queue.models import QueueHistory, Token, next_token_number_for_service



class UserRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Mixin to ensure the user has the 'user' role or is staff."""
    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        return self.request.user.is_staff or self.request.user.profile.role == 'user'

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied("Only public users can access this page. Organizers should use the management portal.")


def _wants_json(request) -> bool:
    """Return True when the client asked for a JSON payload (AJAX refresh)."""
    if request.GET.get('format') == 'json':
        return True
    return request.headers.get('x-requested-with', '').lower() == 'xmlhttprequest'


def _log_history(token, action, user=None, notes=''):
    QueueHistory.objects.create(token=token, action=action, performed_by=user, notes=notes)


def _active_token_count_for_user(user) -> int:
    return Token.objects.filter(
        user=user,
        status__in=[Token.STATUS_WAITING, Token.STATUS_CALLED, Token.STATUS_SERVING],
    ).count()


def _org_bookings_today_count(organization: Organization, booking_date) -> int:
    return (
        Token.objects.filter(organization=organization, booking_date=booking_date)
        .exclude(status=Token.STATUS_CANCELLED)
        .count()
    )


def _waiting_count(service: Service, booking_date) -> int:
    return Token.objects.filter(
        service=service,
        booking_date=booking_date,
        status=Token.STATUS_WAITING,
    ).count()

