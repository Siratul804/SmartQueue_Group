from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.queue.models import QueueHistory, Token


class Command(BaseCommand):
    help = (
        'Auto-cancel stale waiting/called tokens from previous days and archive old completed tokens. '
        'Intended to be run once per day (e.g. via cron).'
    )

    @transaction.atomic
    def handle(self, *args, **options):
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)

        # Auto-cancel no-shows that were still waiting/called as of the end of yesterday.
        stale = Token.objects.filter(
            booking_date=yesterday,
            status__in=[Token.STATUS_WAITING, Token.STATUS_CALLED],
        )

        cancelled = 0
        for token in stale.iterator():
            token.status = Token.STATUS_CANCELLED
            token.save(update_fields=['status'])
            QueueHistory.objects.create(
                token=token,
                action='auto_cancelled',
                performed_by=None,
                notes='Auto-cancelled by reset_daily_queue (no-show cleanup)',
            )
            cancelled += 1

        archive_cutoff_date = today - timedelta(days=30)
        archived = (
            Token.objects.filter(
                status=Token.STATUS_COMPLETED,
                booking_date__lt=archive_cutoff_date,
                archived=False,
            )
            .update(archived=True)
        )

        self.stdout.write(self.style.SUCCESS(f'Cancelled stale tokens: {cancelled}'))
        self.stdout.write(self.style.SUCCESS(f'Archived completed tokens (older than 30 days): {archived}'))
