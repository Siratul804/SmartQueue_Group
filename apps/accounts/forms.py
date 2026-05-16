from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User


class LoginForm(AuthenticationForm):
    """Bootstrap-styled authentication form."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.widgets.Input):
                widget.attrs.setdefault('class', 'form-control')


class SignUpForm(UserCreationForm):
    """Registration form with email and phone stored on Profile."""

    email = forms.EmailField(
        required=True,
        max_length=254,
        widget=forms.EmailInput(attrs={'class': 'form-control'}),
    )
    phone = forms.CharField(
        max_length=15,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    ROLE_CHOICES = [
        ('user', 'Public User (Book tokens)'),
        ('organizer', 'Organization Organizer (Manage queues)'),
    ]
    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        initial='user',
        label='Register as'
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'phone', 'role')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ('username', 'password1', 'password2'):
            self.fields[field_name].widget.attrs.setdefault('class', 'form-control')

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
            # Signal creates Profile; update phone and role.
            profile = user.profile
            profile.phone = self.cleaned_data['phone']
            profile.role = self.cleaned_data['role']
            profile.save()
        return user
