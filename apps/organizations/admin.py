from django.contrib import admin

from apps.organizations.models import Organization, Service


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'type', 'is_active', 'max_daily_tokens', 'created_at')
    list_filter = ('type', 'is_active')
    search_fields = ('name', 'slug', 'address', 'email', 'phone')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'avg_service_time', 'token_prefix', 'is_active', 'created_at')
    list_filter = ('is_active', 'organization')
    search_fields = ('name', 'organization__name')
