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


class BookTokenView(UserRequiredMixin, TemplateView):
    """Book a queue token after validating daily limits and abuse protections."""
    template_name = 'queue/book_token.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        org_slug = self.kwargs.get('org_slug')
        service_id = self.kwargs.get('service_id')
        
        organization = get_object_or_404(Organization, slug=org_slug, is_active=True)
        service = get_object_or_404(Service, pk=service_id, organization=organization, is_active=True)
        
        booking_date = timezone.localdate()
        bookings_today = _org_bookings_today_count(organization, booking_date)
        waiting = _waiting_count(service, booking_date)
        avg_time = int(service.avg_service_time or 0)
        est_wait_minutes = (waiting + 1) * avg_time
        active_for_user = _active_token_count_for_user(self.request.user)
        
        form = TokenBookingForm(self.request.GET or None)

        context.update({
            'organization': organization,
            'service': service,
            'bookings_today': bookings_today,
            'max_daily': organization.max_daily_tokens,
            'waiting': waiting,
            'est_wait_minutes': est_wait_minutes,
            'active_for_user': active_for_user,
            'form': form,
        })
        return context

    def post(self, request, *args, **kwargs):
        org_slug = self.kwargs.get('org_slug')
        service_id = self.kwargs.get('service_id')
        organization = get_object_or_404(Organization, slug=org_slug, is_active=True)
        service = get_object_or_404(Service, pk=service_id, organization=organization, is_active=True)

        form = TokenBookingForm(request.POST)
        if not form.is_valid():
            # If form is invalid, we probably want to re-render with errors
            # For simplicity in this view, I'll redirect back with messages or just handle it here
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
            return redirect('queue:book_token', org_slug=org_slug, service_id=service_id)

        booking_date = form.cleaned_data['booking_date']
        active_for_user = _active_token_count_for_user(request.user)
        bookings_on_date = _org_bookings_today_count(organization, booking_date)
        
        if active_for_user >= 3:
            messages.error(request, 'You already have 3 active tokens. Cancel one before booking again.')
            return redirect('queue:my_tokens')

        if bookings_on_date >= organization.max_daily_tokens:
            messages.error(
                request,
                f'This organization has reached its maximum number of tokens for {booking_date}. Please try another date.',
            )
            return redirect('queue:book_token', org_slug=org_slug, service_id=service_id)

        waiting = _waiting_count(service, booking_date)
        avg_time = int(service.avg_service_time or 0)
        est_wait_minutes = (waiting + 1) * avg_time

        try:
            with transaction.atomic():
                token_number = next_token_number_for_service(service, booking_date)
                # If booking for future, estimated time might be different logic, 
                # but let's keep it simple: today + wait or date + start_time + wait
                # For now, if it's today, use timezone.now(), else use date at 9 AM?
                # Actually, the model uses DateTimeField for estimated_time.
                if booking_date == timezone.localdate():
                    base_time = timezone.now()
                else:
                    # Default to 9 AM on that day
                    base_time = timezone.make_aware(timezone.datetime.combine(booking_date, timezone.datetime.min.time().replace(hour=9)))
                
                estimated_time = base_time + timedelta(minutes=est_wait_minutes)
                token = Token.objects.create(
                    token_number=token_number,
                    service=service,
                    user=request.user,
                    organization=organization,
                    status=Token.STATUS_WAITING,
                    estimated_time=estimated_time,
                    booking_date=booking_date,
                )
        except IntegrityError:
            messages.error(
                request,
                'We could not reserve that token because of a conflict. Please try again in a moment.',
            )
            return redirect('organizations:organization_detail', slug=organization.slug)

        _log_history(token, 'created', user=request.user, notes=f'Token booked for {booking_date}')
        messages.success(
            request,
            f'Your token {token.token_number} has been booked for {booking_date}.',
        )
        return redirect('queue:token_status', token_id=token.pk)


class TokenStatusView(LoginRequiredMixin, DetailView):
    """Display live token status; supports JSON polling for lightweight refresh."""
    model = Token
    pk_url_kwarg = 'token_id'
    template_name = 'queue/token_status.html'
    context_object_name = 'token'

    def get_queryset(self):
        return Token.objects.select_related('organization', 'service')

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        is_organizer = self.object.organization.organizers.filter(pk=request.user.id).exists()
        
        if not (request.user.is_staff or self.object.user_id == request.user.id or is_organizer):
            raise PermissionDenied('You do not have permission to view this token.')

        booking_date = self.object.booking_date
        total_waiting = Token.objects.filter(
            service_id=self.object.service_id,
            booking_date=booking_date,
            status=Token.STATUS_WAITING,
        ).count()

        position = self.object.get_current_position() or 0
        wait_minutes = self.object.get_wait_time()

        progress = 0
        if total_waiting > 0 and position:
            # Progress represents how far through the queue you are.
            # If you are at position 1, you are almost there.
            progress = min(100, int(round(((total_waiting - position + 1) / total_waiting) * 100)))

        if _wants_json(request):
            return JsonResponse({
                'status': self.object.status,
                'position': position,
                'wait_minutes': wait_minutes,
                'total_waiting': total_waiting,
                'progress': progress,
                'token_number': self.object.token_number,
                'is_emergency': self.object.is_emergency,
                'emergency_approved': self.object.emergency_approved,
            })

        context = self.get_context_data(
            object=self.object,
            position=position,
            wait_minutes=wait_minutes,
            total_waiting=total_waiting,
            progress=progress,
            is_organizer=is_organizer,
            is_staff_or_organizer=(request.user.is_staff or is_organizer),
        )
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        is_organizer = self.object.organization.organizers.filter(pk=request.user.id).exists()
        
        if not (request.user.is_staff or is_organizer):
            raise PermissionDenied('Only staff or organizers can manually update token status.')

        new_status = request.POST.get('status')
        if new_status in [choice[0] for choice in Token.STATUS_CHOICES]:
            old_status = self.object.status
            self.object.status = new_status
            
            if new_status == Token.STATUS_CALLED and old_status != Token.STATUS_CALLED:
                self.object.called_at = timezone.now()
            elif new_status == Token.STATUS_COMPLETED and old_status != Token.STATUS_COMPLETED:
                self.object.completed_at = timezone.now()
                
            self.object.save()
            _log_history(self.object, f'status_changed_{new_status}', user=request.user, notes=f'Manually changed from {old_status}')
            messages.success(request, f'Token status updated to {self.object.get_status_display()}.')
        else:
            messages.error(request, 'Invalid status.')

        next_url = request.POST.get('next')
        if next_url:
            return redirect(next_url)
        return redirect('queue:token_status', token_id=self.object.pk)


class MyTokensView(UserRequiredMixin, ListView):
    """List the current user's tokens split into active and historical sections."""
    model = Token
    template_name = 'queue/my_tokens.html'
    context_object_name = 'tokens'

    def get_queryset(self):
        return Token.objects.filter(user=self.request.user).select_related('organization', 'service')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tokens = context['tokens']
        active_statuses = [Token.STATUS_WAITING, Token.STATUS_CALLED, Token.STATUS_SERVING]
        
        active = [t for t in tokens if t.status in active_statuses]
        history = [t for t in tokens if t.status not in active_statuses]

        active.sort(key=lambda t: t.created_at)
        history.sort(key=lambda t: t.created_at, reverse=True)

        context['active_tokens'] = active
        context['history_tokens'] = history
        return context