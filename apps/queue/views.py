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

class EmergencyRequestView(UserRequiredMixin, UpdateView):
    """Allow a user to submit an emergency assistance request for a waiting token."""
    model = Token
    form_class = EmergencyRequestForm
    template_name = 'queue/emergency_request.html'
    pk_url_kwarg = 'token_id'

    def get_queryset(self):
        return Token.objects.select_related('organization')

    def dispatch(self, request, *args, **kwargs):
        token = self.get_object()
        if token.user_id != request.user.id:
            raise PermissionDenied('You can only request emergency help for your own tokens.')
        if token.status != Token.STATUS_WAITING:
            messages.error(request, 'Emergency requests can only be submitted while your token is waiting.')
            return redirect('queue:token_status', token_id=token.pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        token = form.save(commit=False)
        token.is_emergency = True
        token.emergency_approved = False
        token.save(update_fields=['emergency_reason', 'emergency_document', 'is_emergency', 'emergency_approved'])
        
        _log_history(token, 'emergency_submitted', user=self.request.user, notes='Emergency request submitted')

        send_mail(
            subject=f'[SmartQueue] Emergency request for token {token.token_number}',
            message=(
                f'User: {self.request.user.username}\n'
                f'Organization: {token.organization.name}\n'
                f'Service: {token.service.name}\n'
                f'Reason:\n{token.emergency_reason}\n'
            ),
            from_email=None,
            recipient_list=[token.organization.email],
            fail_silently=True,
        )

        messages.success(self.request, 'Your emergency request has been submitted for staff review.')
        return redirect('queue:token_status', token_id=token.pk)


class StaffRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        if self.request.user.is_staff:
            return True
            
        # Also allow organizers for their own organization
        org_id = self.kwargs.get('org_id')
        if org_id:
            return Organization.objects.filter(pk=org_id, organizers=self.request.user).exists()
            
        token_id = self.kwargs.get('token_id')
        if token_id:
            # We avoid full get_object_or_404 here to keep test_func lightweight, 
            # but we need to know the organization.
            return Token.objects.filter(pk=token_id, organization__organizers=self.request.user).exists()

        return False
    
    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied('Staff access is required for this page.')


class AdminDashboardView(StaffRequiredMixin, DetailView):
    """Operational dashboard for counter staff."""
    model = Organization
    pk_url_kwarg = 'org_id'
    template_name = 'queue/admin_dashboard.html'
    context_object_name = 'organization'

    def get_queryset(self):
        return Organization.objects.filter(is_active=True)

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        booking_date = timezone.localdate()

        waiting_qs = (
            Token.objects.filter(organization=self.object, status=Token.STATUS_WAITING)
            .select_related('service', 'user')
            .order_by('created_at', 'id')
        )

        serving = (
            Token.objects.filter(organization=self.object, status=Token.STATUS_SERVING)
            .select_related('service', 'user')
            .order_by('-called_at', '-id')
            .first()
        )

        called = (
            Token.objects.filter(organization=self.object, status=Token.STATUS_CALLED)
            .select_related('service', 'user')
            .order_by('-called_at', '-id')
            .first()
        )

        waiting_rows = []
        for idx, t in enumerate(waiting_qs, start=1):
            waiting_rows.append({
                'position': idx,
                'token': t,
                'wait_minutes': t.get_wait_time(),
            })

        emergency_qs = (
            Token.objects.filter(
                organization=self.object,
                is_emergency=True,
                emergency_approved=False,
                status=Token.STATUS_WAITING,
            )
            .select_related('service', 'user')
            .order_by('-created_at')
        )

        tokens_today = Token.objects.filter(organization=self.object, booking_date=booking_date)
        completed_today = tokens_today.filter(status=Token.STATUS_COMPLETED).count()
        cancelled_today = tokens_today.filter(status=Token.STATUS_CANCELLED).count()

        avg_wait = (
            tokens_today.filter(status=Token.STATUS_COMPLETED, completed_at__isnull=False)
            .annotate(
                wait_seconds=ExpressionWrapper(
                    F('completed_at') - F('created_at'),
                    output_field=DurationField(),
                )
            )
            .aggregate(avg=Avg('wait_seconds'))
            .get('avg')
        )
        avg_wait_minutes = round(avg_wait.total_seconds() / 60, 1) if avg_wait else None

        if _wants_json(request):
            return JsonResponse({
                'waiting_count': waiting_qs.count(),
                'served_today': completed_today,
                'cancelled_today': cancelled_today,
                'total_tokens_today': tokens_today.count(),
                'avg_wait_minutes': avg_wait_minutes,
                'serving_token_number': serving.token_number if serving else '',
                'called_token_number': called.token_number if called else '',
            })

        context = self.get_context_data(
            object=self.object,
            waiting_rows=waiting_rows,
            serving=serving,
            called=called,
            emergency_tokens=emergency_qs,
            waiting_count=waiting_qs.count(),
            served_today=completed_today,
            cancelled_today=cancelled_today,
            total_tokens_today=tokens_today.count(),
            avg_wait_minutes=avg_wait_minutes,
        )
        return self.render_to_response(context)


class CallNextTokenView(StaffRequiredMixin, View):
    """Mark the oldest waiting token as called."""
    def post(self, request, org_id):
        organization = get_object_or_404(Organization, pk=org_id, is_active=True)
        booking_date = timezone.localdate()

        next_token = (
            Token.objects.filter(
                organization=organization,
                status=Token.STATUS_WAITING,
            )
            .order_by('created_at', 'id')
            .first()
        )

        if not next_token:
            messages.info(request, 'There are no waiting tokens to call right now.')
            return redirect('queue:admin_dashboard', org_id=org_id)

        next_token.status = Token.STATUS_CALLED
        next_token.called_at = timezone.now()
        next_token.save(update_fields=['status', 'called_at'])
        _log_history(next_token, 'called', user=request.user, notes='Called by staff')

        messages.success(request, f'Called token {next_token.token_number}.')
        return redirect('queue:admin_dashboard', org_id=org_id)


class StartServiceView(StaffRequiredMixin, View):
    """Move a called token into serving state."""
    def post(self, request, token_id):
        token = get_object_or_404(Token, pk=token_id)
        if token.status != Token.STATUS_CALLED:
            messages.error(request, 'Only a called token can be started.')
            return redirect('queue:admin_dashboard', org_id=token.organization_id)

        token.status = Token.STATUS_SERVING
        token.save(update_fields=['status'])
        _log_history(token, 'serving', user=request.user, notes='Service started')

        messages.success(request, f'Started serving {token.token_number}.')
        return redirect('queue:admin_dashboard', org_id=token.organization_id)


class CompleteServiceView(StaffRequiredMixin, View):
    """Complete a token that is currently being served."""
    def post(self, request, token_id):
        token = get_object_or_404(Token, pk=token_id)
        if token.status != Token.STATUS_SERVING:
            messages.error(request, 'Only a serving token can be completed.')
            return redirect('queue:admin_dashboard', org_id=token.organization_id)

        token.status = Token.STATUS_COMPLETED
        token.completed_at = timezone.now()
        token.save(update_fields=['status', 'completed_at'])
        _log_history(token, 'completed', user=request.user, notes='Service completed')

        messages.success(request, f'Completed {token.token_number}.')
        return redirect('queue:admin_dashboard', org_id=token.organization_id)


class CancelTokenView(LoginRequiredMixin, View):
    """Cancel a waiting token for the owner or staff."""
    def post(self, request, token_id):
        token = get_object_or_404(Token, pk=token_id)
        is_organizer = token.organization.organizers.filter(pk=request.user.id).exists()

        if not (request.user.is_staff or token.user_id == request.user.id or is_organizer):
            raise PermissionDenied('You cannot cancel this token.')

        if token.status != Token.STATUS_WAITING:
            messages.error(request, 'Only waiting tokens can be cancelled.')
            if is_organizer:
                return redirect('organizations:organizer_booking_list', slug=token.organization.slug)
            if request.user.is_staff:
                return redirect('queue:admin_dashboard', org_id=token.organization_id)
            return redirect('queue:my_tokens')

        token.status = Token.STATUS_CANCELLED
        token.save(update_fields=['status'])
        _log_history(token, 'cancelled', user=request.user, notes='Cancelled')

        messages.success(request, f'Token {token.token_number} has been cancelled.')
        if is_organizer:
            return redirect('organizations:organizer_booking_list', slug=token.organization.slug)
        if request.user.is_staff:
            return redirect('queue:admin_dashboard', org_id=token.organization_id)
        return redirect('queue:my_tokens')


class ApproveEmergencyView(StaffRequiredMixin, View):
    """Approve an emergency request and prioritize the token in the waiting queue."""
    def post(self, request, token_id):
        token = get_object_or_404(Token.objects.select_related('user', 'organization', 'service'), pk=token_id)
        is_organizer = token.organization.organizers.filter(pk=request.user.id).exists()

        if token.status != Token.STATUS_WAITING:
            messages.error(request, 'Emergency approval is only valid for waiting tokens.')
            if is_organizer:
                return redirect('organizations:organizer_booking_list', slug=token.organization.slug)
            return redirect('queue:admin_dashboard', org_id=token.organization_id)

        if not token.is_emergency:
            messages.error(request, 'This token does not have an emergency request.')
            if is_organizer:
                return redirect('organizations:organizer_booking_list', slug=token.organization.slug)
            return redirect('queue:admin_dashboard', org_id=token.organization_id)

        token.emergency_approved = True
        token.save(update_fields=['emergency_approved'])
        token.move_to_front_of_waiting_queue()
        _log_history(token, 'emergency_approved', user=request.user, notes='Emergency approved; prioritized')

        send_mail(
            subject=f'[SmartQueue] Emergency approved for token {token.token_number}',
            message=(
                f'Hello {token.user.username},\n\n'
                f'Your emergency request for token {token.token_number} at {token.organization.name} '
                f'was approved. Staff will assist you as soon as possible.\n'
            ),
            from_email=None,
            recipient_list=[token.user.email] if token.user.email else [],
            fail_silently=True,
        )

        messages.success(request, f'Emergency approved for {token.token_number}.')
        if is_organizer:
            return redirect('organizations:organizer_booking_list', slug=token.organization.slug)
        return redirect('queue:admin_dashboard', org_id=token.organization_id)
