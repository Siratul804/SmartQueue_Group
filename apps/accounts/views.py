from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, TemplateView

from apps.accounts.forms import SignUpForm
from apps.queue.models import Token


class SignUpView(CreateView):
    """Handle user registration; log the user in on success."""
    form_class = SignUpForm
    template_name = 'registration/signup.html'
    success_url = reverse_lazy('accounts:login_redirect')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('organizations:organization_list')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        messages.success(self.request, 'Welcome! Your account has been created.')
        return response


class ProfileView(LoginRequiredMixin, TemplateView):
    """Show profile details and a compact list of the user's tokens."""
    template_name = 'accounts/profile.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tokens = (
            Token.objects.filter(user=self.request.user)
            .select_related('organization', 'service')
            .order_by('-created_at')
        )
        context['profile'] = self.request.user.profile
        context['tokens'] = tokens
        
        # Managed organizations for organizers
        if self.request.user.profile.role == 'organizer' or self.request.user.is_staff:
            context['managed_organizations'] = self.request.user.managed_organizations.all()
            
        return context


class RedirectAfterLoginView(LoginRequiredMixin, View):
    """Redirect users based on their role after successful login."""
    def get(self, request, *args, **kwargs):
        if request.user.is_staff or request.user.profile.role == 'organizer':
            managed_orgs = request.user.managed_organizations.all()
            if managed_orgs.count() == 1:
                return redirect('organizations:organizer_dashboard', slug=managed_orgs.first().slug)
            # If multiple or zero organizations, send to their own organizations list
            return redirect('organizations:organizer_org_list')
        
        # Default for regular users
        return redirect('organizations:organization_list')
