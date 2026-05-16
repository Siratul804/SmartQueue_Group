from django.conf import settings
from django.db import models
from django.utils.text import slugify


class Organization(models.Model):
    """An institution that offers queueable services."""

    TYPE_HOSPITAL = 'hospital'
    TYPE_BANK = 'bank'
    TYPE_GOVT = 'govt'
    TYPE_CHOICES = [
        (TYPE_HOSPITAL, 'Hospital'),
        (TYPE_BANK, 'Bank'),
        (TYPE_GOVT, 'Government'),
    ]

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    address = models.TextField()
    phone = models.CharField(max_length=15)
    email = models.EmailField()
    max_daily_tokens = models.IntegerField(default=100)
    is_active = models.BooleanField(default=True)
    organizers = models.ManyToManyField(
        settings.AUTH_USER_MODEL, 
        related_name='managed_organizations', 
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Generate a unique slug from the name when missing."""
        if not self.slug:
            base = slugify(self.name) or 'organization'
            slug = base
            counter = 1
            while Organization.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{counter}'
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)


class Service(models.Model):
    """A bookable counter/service within an organization."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='services')
    name = models.CharField(max_length=200)
    avg_service_time = models.IntegerField(default=10, help_text='Minutes per person')
    token_prefix = models.CharField(max_length=5, default='A')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.organization.name} — {self.name}'
