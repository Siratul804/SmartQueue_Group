from django.db.models import Q
from django.utils import timezone
from django.views.generic import ListView, DetailView

from apps.organizations.forms import OrganizationSearchForm
from apps.organizations.models import Organization
from apps.queue.models import Token


class OrganizationListView(ListView):
    """List active organizations with optional type filter and text search."""
    model = Organization
    template_name = 'home.html'
    context_object_name = 'organizations'

    def get_queryset(self):
        queryset = super().get_queryset().filter(is_active=True)
        self.form = OrganizationSearchForm(self.request.GET or None)
        
        if self.form.is_valid():
            query = self.form.cleaned_data.get('q', '').strip()
            org_type = self.form.cleaned_data.get('type')
            if org_type:
                queryset = queryset.filter(type=org_type)
            if query:
                queryset = queryset.filter(
                    Q(name__icontains=query)
                    | Q(address__icontains=query)
                    | Q(type__icontains=query)
                )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = self.form
        
        # Add role info to context for conditional UI
        is_organizer = False
        if self.request.user.is_authenticated:
            is_organizer = self.request.user.profile.role == 'organizer' or self.request.user.is_staff
        context['is_organizer'] = is_organizer
        
        return context


class OrganizationDetailView(DetailView):
    """Show organization details and active services with today's queue sizes."""
    model = Organization
    template_name = 'organizations/organization_detail.html'
    context_object_name = 'organization'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        organization = self.get_object()
        services = organization.services.filter(is_active=True)
        today = timezone.localdate()

        service_cards = []
        for service in services:
            waiting_today = Token.objects.filter(
                service=service,
                booking_date=today,
                status=Token.STATUS_WAITING,
            ).count()
            service_cards.append({'service': service, 'waiting_today': waiting_today})

        is_organizer = False
        if self.request.user.is_authenticated:
            is_organizer = self.request.user.is_staff or self.request.user.profile.role == 'organizer'

        context['service_cards'] = service_cards
        context['is_organizer'] = is_organizer
        return context
# hello everyone