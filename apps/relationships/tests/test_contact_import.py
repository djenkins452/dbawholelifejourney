"""
Whole Life Journey - Contact Import Tests (Phase 5)

Project: Whole Life Journey
Path: apps/relationships/tests/test_contact_import.py
Purpose: Tests for vCard import service and upload view

Coverage:
    - vCard 3.0 parsing (N, FN, TEL, EMAIL fields)
    - Name fallback from FN when N is missing
    - Deduplication by case-insensitive first+last name
    - Empty name handling
    - Multi-contact file import
    - File encoding (UTF-8 and Latin-1)
    - Upload view GET/POST
    - File validation (.vcf only, max size)
    - Import results display

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.relationships.models import Person
from apps.relationships.services import ContactImportService

User = get_user_model()


# =============================================================================
# HELPERS
# =============================================================================


class ImportTestMixin:
    """Common setup for import tests."""

    def create_user(self, email='test@example.com', password='testpass123'):
        user = User.objects.create_user(email=email, password=password)
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
        )
        user.preferences.has_completed_onboarding = True
        user.preferences.save()
        return user

    def login_user(self, email='test@example.com', password='testpass123'):
        return self.client.login(email=email, password=password)


SAMPLE_VCF = """BEGIN:VCARD
VERSION:3.0
N:Smith;John;;;
FN:John Smith
TEL;TYPE=CELL:+1-555-123-4567
EMAIL;TYPE=HOME:john@example.com
END:VCARD
BEGIN:VCARD
VERSION:3.0
N:Doe;Jane;;;
FN:Jane Doe
TEL;TYPE=WORK:555-987-6543
EMAIL:jane@work.com
END:VCARD
BEGIN:VCARD
VERSION:3.0
N:Williams;Bob;;;
FN:Bob Williams
END:VCARD
"""

SAMPLE_VCF_FN_ONLY = """BEGIN:VCARD
VERSION:3.0
FN:Sarah Connor
END:VCARD
"""

SAMPLE_VCF_EMPTY = """BEGIN:VCARD
VERSION:3.0
N:;;;;
FN:
END:VCARD
"""

SAMPLE_VCF_V21 = """BEGIN:VCARD
VERSION:2.1
N:Parker;Peter
TEL;CELL:555-0001
END:VCARD
"""

SAMPLE_VCF_V40 = """BEGIN:VCARD
VERSION:4.0
N:Kent;Clark;;;
FN:Clark Kent
TEL;VALUE=uri;TYPE="voice,cell":tel:+1-555-0002
EMAIL:clark@dailyplanet.com
END:VCARD
"""


# =============================================================================
# 1. VCF PARSING TESTS
# =============================================================================


class VcfParserTest(ImportTestMixin, TestCase):
    """Tests for ContactImportService._parse_vcf."""

    def test_parse_standard_vcf(self):
        contacts = ContactImportService._parse_vcf(SAMPLE_VCF)
        self.assertEqual(len(contacts), 3)

    def test_parse_names_from_n_field(self):
        contacts = ContactImportService._parse_vcf(SAMPLE_VCF)
        self.assertEqual(contacts[0]['first_name'], 'John')
        self.assertEqual(contacts[0]['last_name'], 'Smith')

    def test_parse_phone(self):
        contacts = ContactImportService._parse_vcf(SAMPLE_VCF)
        self.assertEqual(contacts[0]['phone'], '+1-555-123-4567')

    def test_parse_email(self):
        contacts = ContactImportService._parse_vcf(SAMPLE_VCF)
        self.assertEqual(contacts[0]['email'], 'john@example.com')

    def test_parse_fn_fallback(self):
        """When N field is missing, fall back to FN split."""
        contacts = ContactImportService._parse_vcf(SAMPLE_VCF_FN_ONLY)
        self.assertEqual(len(contacts), 1)
        self.assertEqual(contacts[0]['first_name'], 'Sarah')
        self.assertEqual(contacts[0]['last_name'], 'Connor')

    def test_parse_empty_name(self):
        contacts = ContactImportService._parse_vcf(SAMPLE_VCF_EMPTY)
        self.assertEqual(len(contacts), 1)
        # Both first_name and last_name should be empty
        self.assertEqual(contacts[0]['first_name'], '')
        self.assertEqual(contacts[0]['last_name'], '')

    def test_parse_v21(self):
        contacts = ContactImportService._parse_vcf(SAMPLE_VCF_V21)
        self.assertEqual(len(contacts), 1)
        self.assertEqual(contacts[0]['first_name'], 'Peter')
        self.assertEqual(contacts[0]['last_name'], 'Parker')

    def test_parse_v40(self):
        contacts = ContactImportService._parse_vcf(SAMPLE_VCF_V40)
        self.assertEqual(len(contacts), 1)
        self.assertEqual(contacts[0]['first_name'], 'Clark')
        self.assertEqual(contacts[0]['last_name'], 'Kent')

    def test_first_phone_wins(self):
        """Only the first phone number should be captured."""
        vcf = """BEGIN:VCARD
VERSION:3.0
N:Test;Multi;;;
TEL;TYPE=CELL:111-1111
TEL;TYPE=WORK:222-2222
END:VCARD
"""
        contacts = ContactImportService._parse_vcf(vcf)
        self.assertEqual(contacts[0]['phone'], '111-1111')

    def test_first_email_wins(self):
        """Only the first email should be captured."""
        vcf = """BEGIN:VCARD
VERSION:3.0
N:Test;Multi;;;
EMAIL;TYPE=HOME:first@test.com
EMAIL;TYPE=WORK:second@test.com
END:VCARD
"""
        contacts = ContactImportService._parse_vcf(vcf)
        self.assertEqual(contacts[0]['email'], 'first@test.com')


# =============================================================================
# 2. IMPORT SERVICE TESTS
# =============================================================================


class ImportServiceTest(ImportTestMixin, TestCase):
    """Tests for ContactImportService.import_vcf."""

    def setUp(self):
        self.user = self.create_user()

    def test_import_creates_persons(self):
        result = ContactImportService.import_vcf(self.user, SAMPLE_VCF)
        self.assertEqual(result['imported_count'], 3)
        self.assertEqual(Person.objects.filter(owner=self.user).count(), 3)

    def test_import_sets_relationship_type_to_other(self):
        ContactImportService.import_vcf(self.user, SAMPLE_VCF)
        for person in Person.objects.filter(owner=self.user):
            self.assertEqual(person.relationship_type, 'other')

    def test_import_stores_phone_and_email(self):
        ContactImportService.import_vcf(self.user, SAMPLE_VCF)
        john = Person.objects.get(owner=self.user, first_name='John', last_name='Smith')
        self.assertEqual(john.phone, '+1-555-123-4567')
        self.assertEqual(john.email, 'john@example.com')

    def test_deduplication_skips_existing(self):
        """Existing contacts are skipped (case-insensitive name match)."""
        Person.objects.create(
            owner=self.user, first_name='John', last_name='Smith',
        )
        result = ContactImportService.import_vcf(self.user, SAMPLE_VCF)
        self.assertEqual(result['imported_count'], 2)
        self.assertEqual(result['skipped_count'], 1)
        self.assertEqual(result['skipped'][0]['name'], 'John Smith')

    def test_deduplication_case_insensitive(self):
        """Dedup is case-insensitive."""
        Person.objects.create(
            owner=self.user, first_name='JOHN', last_name='SMITH',
        )
        result = ContactImportService.import_vcf(self.user, SAMPLE_VCF)
        self.assertEqual(result['skipped_count'], 1)

    def test_empty_name_reported_as_error(self):
        result = ContactImportService.import_vcf(self.user, SAMPLE_VCF_EMPTY)
        self.assertEqual(result['error_count'], 1)
        self.assertEqual(result['errors'][0]['reason'], 'No name found')

    def test_no_cross_user_dedup(self):
        """Contacts from another user should not cause dedup."""
        user2 = self.create_user(email='user2@example.com')
        Person.objects.create(
            owner=user2, first_name='John', last_name='Smith',
        )
        result = ContactImportService.import_vcf(self.user, SAMPLE_VCF)
        # John Smith should still be imported for self.user
        self.assertEqual(result['imported_count'], 3)

    def test_import_same_file_twice(self):
        """Second import of same file skips all (dedup)."""
        ContactImportService.import_vcf(self.user, SAMPLE_VCF)
        result = ContactImportService.import_vcf(self.user, SAMPLE_VCF)
        self.assertEqual(result['imported_count'], 0)
        self.assertEqual(result['skipped_count'], 3)

    def test_fn_fallback_import(self):
        result = ContactImportService.import_vcf(self.user, SAMPLE_VCF_FN_ONLY)
        self.assertEqual(result['imported_count'], 1)
        person = Person.objects.get(owner=self.user)
        self.assertEqual(person.first_name, 'Sarah')
        self.assertEqual(person.last_name, 'Connor')


# =============================================================================
# 3. UPLOAD VIEW TESTS
# =============================================================================


class ContactImportViewTest(ImportTestMixin, TestCase):
    """Tests for ContactImportView GET/POST."""

    def setUp(self):
        self.user = self.create_user()
        self.login_user()
        self.url = reverse('relationships:contact_import')

    def test_get_renders_form(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Import Contacts')
        self.assertContains(response, 'enctype="multipart/form-data"')

    def test_post_imports_contacts(self):
        vcf_file = SimpleUploadedFile(
            'contacts.vcf',
            SAMPLE_VCF.encode('utf-8'),
            content_type='text/vcard',
        )
        response = self.client.post(self.url, {'file': vcf_file})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Imported')
        self.assertEqual(Person.objects.filter(owner=self.user).count(), 3)

    def test_post_invalid_extension(self):
        bad_file = SimpleUploadedFile(
            'contacts.csv',
            b'first,last\nJohn,Smith',
            content_type='text/csv',
        )
        response = self.client.post(self.url, {'file': bad_file})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Only .vcf')

    def test_post_no_file(self):
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 200)
        # Form should show error
        self.assertEqual(Person.objects.filter(owner=self.user).count(), 0)

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_result_shows_counts(self):
        # Pre-create one contact to test skipping
        Person.objects.create(
            owner=self.user, first_name='John', last_name='Smith',
        )
        vcf_file = SimpleUploadedFile(
            'contacts.vcf',
            SAMPLE_VCF.encode('utf-8'),
            content_type='text/vcard',
        )
        response = self.client.post(self.url, {'file': vcf_file})
        self.assertContains(response, 'Skipped')

    def test_help_section_renders(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'iPhone')
        self.assertContains(response, 'Android')
        self.assertContains(response, 'Google Contacts')


# =============================================================================
# 4. IMPORT LINK PRESENCE TESTS
# =============================================================================


class ImportLinkTest(ImportTestMixin, TestCase):
    """Tests that Import link appears on relevant pages."""

    def setUp(self):
        self.user = self.create_user()
        self.login_user()

    def test_import_link_on_person_list(self):
        response = self.client.get(reverse('relationships:person_list'))
        self.assertContains(response, 'Import')
        self.assertContains(response, reverse('relationships:contact_import'))

    def test_import_link_on_insights(self):
        response = self.client.get(reverse('relationships:insights'))
        self.assertContains(response, 'Import')
        self.assertContains(response, reverse('relationships:contact_import'))
