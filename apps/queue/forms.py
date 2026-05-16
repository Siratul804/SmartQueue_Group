import mimetypes
import os

from django import forms
from django.utils import timezone
from apps.queue.models import Token


class EmergencyRequestForm(forms.ModelForm):
    """Validate emergency assistance requests including optional evidence uploads."""
    emergency_reason = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
        required=True,
        label='Reason'
    )

    class Meta:
        model = Token
        fields = ['emergency_reason', 'emergency_document']
        widgets = {
            'emergency_document': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'emergency_document': 'Supporting document (optional)',
        }

    ALLOWED_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png'}
    ALLOWED_MIME_TYPES = {'application/pdf', 'image/jpeg', 'image/png'}

    def clean_emergency_document(self):
        """Restrict uploads to small PDF/JPEG/PNG files."""
        uploaded = self.cleaned_data.get('emergency_document')
        if not uploaded:
            return uploaded

        max_bytes = 5 * 1024 * 1024
        if uploaded.size > max_bytes:
            raise forms.ValidationError('Files must be 5MB or smaller.')

        ext = os.path.splitext(uploaded.name)[1].lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            raise forms.ValidationError('Only PDF, JPG, and PNG files are allowed.')

        guessed, _ = mimetypes.guess_type(uploaded.name)
        content_type = uploaded.content_type or guessed or ''
        if content_type and content_type not in self.ALLOWED_MIME_TYPES:
            raise forms.ValidationError('Unsupported file type.')

        return uploaded

        
class TokenBookingForm(forms.Form):
    """Form to select booking date and optionally other parameters."""
    booking_date = forms.DateField(
        label='Booking Date',
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control',
            'min': timezone.localdate().isoformat()
        }),
        initial=timezone.localdate,
        required=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set the minimum date to today in the widget
        self.fields['booking_date'].widget.attrs['min'] = timezone.localdate().isoformat()

    def clean_booking_date(self):
        booking_date = self.cleaned_data.get('booking_date')
        if booking_date < timezone.localdate():
            raise forms.ValidationError('You cannot book a token for a past date.')
        
        # Limit future booking to 7 days
        if booking_date > timezone.localdate() + timezone.timedelta(days=7):
            raise forms.ValidationError('You can only book tokens up to 7 days in advance.')
            
        return booking_date
