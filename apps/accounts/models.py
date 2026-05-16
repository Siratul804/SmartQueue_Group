from django.contrib.auth.models import User
from django.db import models


class Profile(models.Model):
    """Extended user information linked one-to-one with Django's User."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    ROLE_USER = 'user'
    ROLE_ORGANIZER = 'organizer'
    ROLE_CHOICES = [
        (ROLE_USER, 'Public User'),
        (ROLE_ORGANIZER, 'Organizer'),
    ]

    phone = models.CharField(max_length=15, blank=True)
    address = models.TextField(blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_USER)

    def __str__(self):
        return f'Profile({self.user.username})'
