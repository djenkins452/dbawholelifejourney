# Generated migration for biometric login feature

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0014_add_show_whats_new'),
    ]

    operations = [
        # Add biometric_login_enabled preference
        migrations.AddField(
            model_name='userpreferences',
            name='biometric_login_enabled',
            field=models.BooleanField(
                default=False,
                help_text='Enable Face ID, Touch ID, or device biometrics for quick login',
            ),
        ),
        # Create WebAuthnCredential model for storing biometric credentials
        migrations.CreateModel(
            name='WebAuthnCredential',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('credential_id', models.BinaryField(help_text='Unique identifier for this credential (from authenticator)')),
                ('credential_id_b64', models.CharField(help_text='Base64-encoded credential ID for lookups', max_length=500, unique=True)),
                ('public_key', models.BinaryField(help_text='COSE public key from authenticator')),
                ('sign_count', models.PositiveIntegerField(default=0, help_text='Signature counter from authenticator')),
                ('device_name', models.CharField(blank=True, help_text="User-friendly name for this device (e.g., 'iPhone 15')", max_length=100)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('last_used_at', models.DateTimeField(blank=True, null=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='webauthn_credentials', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'WebAuthn credential',
                'verbose_name_plural': 'WebAuthn credentials',
                'ordering': ['-created_at'],
            },
        ),
    ]
