"""Custom HTTP error pages for SmartQueue."""

from django.views.generic import TemplateView


class Handler404View(TemplateView):
    """Render a friendly 404 page."""
    template_name = '404.html'

    def get(self, request, *args, **kwargs):
        return self.render_to_response(self.get_context_data(), status=404)


class Handler403View(TemplateView):
    """Render a friendly 403 page."""
    template_name = '403.html'

    def get(self, request, *args, **kwargs):
        return self.render_to_response(self.get_context_data(), status=403)
