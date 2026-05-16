from django.db import migrations


def seed(apps, schema_editor):
    """Insert demo organizations and services for local development."""
    Organization = apps.get_model('organizations', 'Organization')
    Service = apps.get_model('organizations', 'Service')

    if Organization.objects.exists():
        return

    Organization.objects.create(
        name='City Hospital',
        slug='city-hospital',
        type='hospital',
        address='12 Health Street, Metropolis',
        phone='+10000000001',
        email='city.hospital@example.com',
        max_daily_tokens=200,
        is_active=True,
    )
    Organization.objects.create(
        name='Metro Hospital',
        slug='metro-hospital',
        type='hospital',
        address='450 River Road, Metropolis',
        phone='+10000000002',
        email='metro.hospital@example.com',
        max_daily_tokens=200,
        is_active=True,
    )
    Organization.objects.create(
        name='Global Bank',
        slug='global-bank',
        type='bank',
        address='88 Finance Avenue, Metropolis',
        phone='+10000000003',
        email='service@globalbank.example.com',
        max_daily_tokens=300,
        is_active=True,
    )
    Organization.objects.create(
        name='Community Bank',
        slug='community-bank',
        type='bank',
        address='9 Town Square, Lakeside',
        phone='+10000000004',
        email='hello@communitybank.example.com',
        max_daily_tokens=250,
        is_active=True,
    )
    Organization.objects.create(
        name='Passport Office',
        slug='passport-office',
        type='govt',
        address='Citizen Center, Capital District',
        phone='+10000000005',
        email='appointments@passport.example.gov',
        max_daily_tokens=120,
        is_active=True,
    )

    city = Organization.objects.get(slug='city-hospital')
    metro = Organization.objects.get(slug='metro-hospital')
    global_bank = Organization.objects.get(slug='global-bank')
    community = Organization.objects.get(slug='community-bank')
    passport = Organization.objects.get(slug='passport-office')

    def add_service(org, name, avg, prefix):
        Service.objects.create(
            organization=org,
            name=name,
            avg_service_time=avg,
            token_prefix=prefix,
            is_active=True,
        )

    # City Hospital
    add_service(city, 'General OPD', 12, 'G')
    add_service(city, 'Emergency', 6, 'E')
    add_service(city, 'Pharmacy', 5, 'P')

    # Metro Hospital (same service mix for consistency)
    add_service(metro, 'General OPD', 10, 'M')
    add_service(metro, 'Emergency', 8, 'X')
    add_service(metro, 'Pharmacy', 6, 'Y')

    # Global Bank
    add_service(global_bank, 'Withdrawal', 7, 'W')
    add_service(global_bank, 'Deposit', 7, 'D')
    add_service(global_bank, 'Loan Inquiry', 15, 'L')

    # Community Bank
    add_service(community, 'Withdrawal', 8, 'C')
    add_service(community, 'Deposit', 8, 'I')
    add_service(community, 'Loan Inquiry', 18, 'N')

    # Passport Office
    add_service(passport, 'New Passport', 25, 'NP')
    add_service(passport, 'Renewal', 15, 'R')


def unseed(apps, schema_editor):
    Organization = apps.get_model('organizations', 'Organization')
    Organization.objects.filter(
        slug__in=[
            'city-hospital',
            'metro-hospital',
            'global-bank',
            'community-bank',
            'passport-office',
        ]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('organizations', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
