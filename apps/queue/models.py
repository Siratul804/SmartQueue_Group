import re
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class Token(models.Model):
    """A user's place in line for a specific service on a given calendar day."""

    STATUS_WAITING = 'waiting'
    STATUS_CALLED = 'called'
    STATUS_SERVING = 'serving'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_WAITING, 'Waiting'),
        (STATUS_CALLED, 'Called'),
        (STATUS_SERVING, 'Serving'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    token_number = models.CharField(max_length=20)
    service = models.ForeignKey('organizations.Service', on_delete=models.CASCADE, related_name='tokens')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tokens')
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.CASCADE,
        related_name='tokens',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_WAITING)
    created_at = models.DateTimeField(auto_now_add=True)
    estimated_time = models.DateTimeField(null=True, blank=True)
    called_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    is_emergency = models.BooleanField(default=False)
    emergency_reason = models.TextField(blank=True)
    emergency_document = models.FileField(upload_to='emergency_docs/', blank=True, null=True)
    emergency_approved = models.BooleanField(default=False)
    # booking_date supports per-day uniqueness and reporting without relying on created_at timezone edges.
    booking_date = models.DateField()
    archived = models.BooleanField(default=False)

    class Meta:
        ordering = ['created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['service', 'token_number', 'booking_date'],
                name='uniq_token_number_per_service_day',
            ),
        ]

    def __str__(self):
        return f'{self.token_number} ({self.status})'

    def get_current_position(self):
        """
        Return 1-based queue position among waiting tokens for this service/day.

        Returns None when this token is not currently waiting.
        """
        if self.status != self.STATUS_WAITING:
            return None

        waiting_ids = list(
            Token.objects.filter(
                service_id=self.service_id,
                booking_date=self.booking_date,
                status=self.STATUS_WAITING,
            )
            .order_by('created_at', 'id')
            .values_list('id', flat=True)
        )

        try:
            return waiting_ids.index(self.id) + 1
        except ValueError:
            return None

    def get_wait_time(self):
        """Estimated minutes until service based on position and average service time."""
        position = self.get_current_position()
        if position is None:
            return 0
        avg = getattr(self.service, 'avg_service_time', None) or 0
        return int(position) * int(avg)