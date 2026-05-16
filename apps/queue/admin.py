from django.contrib import admin

from apps.queue.models import QueueHistory, Token


@admin.register(Token)
class TokenAdmin(admin.ModelAdmin):
    list_display = (
        'token_number',
        'organization',
        'service',
        'user',
        'status',
        'booking_date',
        'is_emergency',
        'emergency_approved',
        'archived',
        'created_at',
    )
    list_filter = ('status', 'booking_date', 'is_emergency', 'emergency_approved', 'archived', 'organization')
    search_fields = ('token_number', 'user__username', 'organization__name', 'service__name')
    autocomplete_fields = ('user', 'organization', 'service')


@admin.register(QueueHistory)
class QueueHistoryAdmin(admin.ModelAdmin):
    list_display = ('token', 'action', 'timestamp', 'performed_by')
    list_filter = ('action', 'timestamp')
    search_fields = ('token__token_number', 'notes')
