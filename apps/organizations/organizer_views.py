from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import TemplateView, ListView, UpdateView, CreateView, DeleteView, DetailView
from django.db.models import Count, Q

from apps.organizations.models import Organization, Service
from apps.queue.models import Token


class OrganizerRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Mixin to ensure the user is an organizer for the specified organization."""
    def test_func(self):
        org_slug = self.kwargs.get('slug') or self.kwargs.get('org_slug')
        if not org_slug:
            # Try to get from service if applicable
            service_id = self.kwargs.get('service_id')
            if service_id:
                service = get_object_or_404(Service, pk=service_id)
                organization = service.organization
            else:
                return False
        else:
            organization = get_object_or_404(Organization, slug=org_slug)
        
        return self.request.user.is_staff or organization.organizers.filter(pk=self.request.user.pk).exists()

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied("You are not an organizer for this organization.")


class OrganizerDashboardView(OrganizerRequiredMixin, DetailView):
    """Main dashboard for organization organizers."""
    model = Organization
    template_name = 'organizations/organizer/dashboard.html'
    context_object_name = 'organization'
    slug_url_kwarg = 'slug'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        organization = self.get_object()
        today = timezone.localdate()
        
        # Stats
        all_tokens = Token.objects.filter(organization=organization)
        tokens_today = all_tokens.filter(booking_date=today)
        
        context['waiting_today'] = all_tokens.filter(status=Token.STATUS_WAITING).count()
        context['serving_today'] = all_tokens.filter(status=Token.STATUS_SERVING).count()
        context['completed_today'] = tokens_today.filter(status=Token.STATUS_COMPLETED).count()
        context['cancelled_today'] = tokens_today.filter(status=Token.STATUS_CANCELLED).count()
        
        # Recent Bookings
        context['recent_bookings'] = Token.objects.filter(
            organization=organization
        ).select_related('service', 'user').order_by('-created_at')[:10]
        
        # Services status
        context['services'] = organization.services.annotate(
            waiting_count=Count('tokens', filter=Q(tokens__status=Token.STATUS_WAITING))
        )
        
        # Active Bookings (Waiting, Called, Serving)
        context['today_bookings'] = Token.objects.filter(
            organization=organization,
            status__in=[Token.STATUS_WAITING, Token.STATUS_CALLED, Token.STATUS_SERVING]
        ).select_related('service', 'user').order_by('created_at')
        
        return context


class OrganizerBookingListView(OrganizerRequiredMixin, ListView):
    """Full list of bookings for maintenance and updates."""
    model = Token
    template_name = 'organizations/organizer/booking_list.html'
    context_object_name = 'tokens'
    paginate_by = 20

    def get_queryset(self):
        org_slug = self.kwargs.get('slug')
        organization = get_object_or_404(Organization, slug=org_slug)
        queryset = Token.objects.filter(organization=organization).select_related('service', 'user').order_by('-booking_date', '-created_at')
        
        # Filtering
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
            
        date = self.request.GET.get('date')
        if date:
            queryset = queryset.filter(booking_date=date)
            
        service_id = self.request.GET.get('service')
        if service_id:
            queryset = queryset.filter(service_id=service_id)
            
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        org_slug = self.kwargs.get('slug')
        organization = get_object_or_404(Organization, slug=org_slug)
        context['organization'] = organization
        context['services'] = organization.services.all()
        context['status_choices'] = Token.STATUS_CHOICES
        return context


class OrganizerServiceListView(OrganizerRequiredMixin, ListView):
    """Manage services for the organization."""
    model = Service
    template_name = 'organizations/organizer/service_list.html'
    context_object_name = 'services'

    def get_queryset(self):
        org_slug = self.kwargs.get('slug')
        organization = get_object_or_404(Organization, slug=org_slug)
        return organization.services.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        org_slug = self.kwargs.get('slug')
        context['organization'] = get_object_or_404(Organization, slug=org_slug)
        return context


class OrganizerServiceCreateView(OrganizerRequiredMixin, CreateView):
    model = Service
    template_name = 'organizations/organizer/service_form.html'
    fields = ['name', 'avg_service_time', 'token_prefix', 'is_active']

    def form_valid(self, form):
        org_slug = self.kwargs.get('slug')
        organization = get_object_or_404(Organization, slug=org_slug)
        form.instance.organization = organization
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('organizations:organizer_service_list', kwargs={'slug': self.kwargs.get('slug')})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['organization'] = get_object_or_404(Organization, slug=self.kwargs.get('slug'))
        context['title'] = "Add New Service"
        return context


class OrganizerServiceUpdateView(OrganizerRequiredMixin, UpdateView):
    model = Service
    template_name = 'organizations/organizer/service_form.html'
    fields = ['name', 'avg_service_time', 'token_prefix', 'is_active']
    pk_url_kwarg = 'service_id'

    def get_success_url(self):
        return reverse_lazy('organizations:organizer_service_list', kwargs={'slug': self.kwargs.get('slug')})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['organization'] = get_object_or_404(Organization, slug=self.kwargs.get('slug'))
        context['title'] = "Edit Service"
        return context


class OrganizerProfileUpdateView(OrganizerRequiredMixin, UpdateView):
    model = Organization
    template_name = 'organizations/organizer/organization_form.html'
    fields = ['name', 'type', 'address', 'phone', 'email', 'max_daily_tokens', 'is_active']
    slug_url_kwarg = 'slug'

    def get_success_url(self):
        return reverse_lazy('organizations:organizer_dashboard', kwargs={'slug': self.object.slug})


class OrganizerOrganizationListView(LoginRequiredMixin, ListView):
    """List of organizations managed by the current user."""
    model = Organization
    template_name = 'organizations/organizer/my_organizations.html'
    context_object_name = 'organizations'

    def get_queryset(self):
        return self.request.user.managed_organizations.all()

    def dispatch(self, request, *args, **kwargs):
        if not (request.user.is_staff or (hasattr(request.user, 'profile') and request.user.profile.role == 'organizer')):
            raise PermissionDenied("You must be an organizer to view this page.")
        return super().dispatch(request, *args, **kwargs)


class OrganizationCreateView(LoginRequiredMixin, CreateView):
    """Allow an organizer to create a new organization."""
    model = Organization
    template_name = 'organizations/organizer/organization_form.html'
    fields = ['name', 'type', 'address', 'phone', 'email', 'max_daily_tokens']

    def dispatch(self, request, *args, **kwargs):
        if not (request.user.is_staff or (hasattr(request.user, 'profile') and request.user.profile.role == 'organizer')):
            raise PermissionDenied("You must be an organizer to create an organization.")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        # Link the creator as an organizer
        self.object.organizers.add(self.request.user)
        return response

    def get_success_url(self):
        return reverse_lazy('organizations:organizer_dashboard', kwargs={'slug': self.object.slug})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = "Create Your Organization"
        return context
# hello 