"""Create a Profile row whenever a User is created."""

from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.accounts.models import Profile


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    """Ensure every User has an associated Profile."""
    if created:
        Profile.objects.create(user=instance)
    else:
        # If profile missing (e.g. legacy data), create it.
        Profile.objects.get_or_create(user=instance)
