# -*- coding: utf-8 -*-
"""
Admin Guide Tests

Tests for the Admin Guide documentation system:
1. Model tests (creation, ordering, constraints)
2. View access tests (staff required, 200/404)
3. Content tests (sidebar, markdown rendering)
4. Edit tests (editable vs non-editable)
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.admin_console.models import AdminGuideSection, AdminGuideArticle
from apps.admin_console.tests.test_admin_console import AdminTestMixin

User = get_user_model()


class AdminGuideModelTests(TestCase):
    """Test AdminGuideSection and AdminGuideArticle models."""

    def test_section_creation(self):
        section = AdminGuideSection.objects.create(
            section_key='test-section',
            title='Test Section',
            icon='📄',
            order=10,
        )
        self.assertEqual(section.section_key, 'test-section')
        self.assertEqual(section.title, 'Test Section')
        self.assertTrue(section.is_active)

    def test_section_ordering(self):
        s2 = AdminGuideSection.objects.create(section_key='b', title='B', order=20)
        s1 = AdminGuideSection.objects.create(section_key='a', title='A', order=10)
        sections = list(AdminGuideSection.objects.all())
        self.assertEqual(sections[0], s1)
        self.assertEqual(sections[1], s2)

    def test_section_str(self):
        section = AdminGuideSection.objects.create(
            section_key='test', title='Test', icon='🧠'
        )
        self.assertEqual(str(section), '🧠 Test')

    def test_article_creation(self):
        section = AdminGuideSection.objects.create(
            section_key='sec', title='Section'
        )
        article = AdminGuideArticle.objects.create(
            section=section,
            title='Article Title',
            slug='article-title',
            content='## Hello\n\nWorld',
            order=10,
        )
        self.assertEqual(article.section, section)
        self.assertFalse(article.is_editable)
        self.assertTrue(article.is_active)

    def test_article_unique_together(self):
        section = AdminGuideSection.objects.create(
            section_key='sec', title='Section'
        )
        AdminGuideArticle.objects.create(
            section=section, title='Art', slug='art', content='c'
        )
        with self.assertRaises(Exception):
            AdminGuideArticle.objects.create(
                section=section, title='Art 2', slug='art', content='c2'
            )

    def test_article_str(self):
        section = AdminGuideSection.objects.create(
            section_key='sec', title='Section'
        )
        article = AdminGuideArticle.objects.create(
            section=section, title='Article', slug='article', content='c'
        )
        self.assertEqual(str(article), 'Section > Article')


class AdminGuideViewAccessTests(AdminTestMixin, TestCase):
    """Test that views enforce staff-only access."""

    def setUp(self):
        self.client = Client()
        self.admin = self.create_admin()
        self.user = self.create_user(email='regular@example.com')
        self.section = AdminGuideSection.objects.create(
            section_key='test-sec', title='Test Section', order=10
        )
        self.article = AdminGuideArticle.objects.create(
            section=self.section, title='Test Article', slug='test-article',
            content='Test content', order=10
        )

    def test_guide_home_requires_admin(self):
        self.client.login(email='regular@example.com', password='testpass123')
        response = self.client.get(reverse('admin_console:admin_guide_home'))
        self.assertNotEqual(response.status_code, 200)

    def test_guide_home_accessible_by_admin(self):
        self.client.login(email='admin@example.com', password='adminpass123')
        response = self.client.get(reverse('admin_console:admin_guide_home'))
        self.assertEqual(response.status_code, 200)

    def test_guide_section_view(self):
        self.client.login(email='admin@example.com', password='adminpass123')
        response = self.client.get(
            reverse('admin_console:admin_guide_section', args=['test-sec'])
        )
        self.assertEqual(response.status_code, 200)

    def test_guide_article_view(self):
        self.client.login(email='admin@example.com', password='adminpass123')
        response = self.client.get(
            reverse('admin_console:admin_guide_article',
                    args=['test-sec', 'test-article'])
        )
        self.assertEqual(response.status_code, 200)

    def test_guide_404_for_invalid_section(self):
        self.client.login(email='admin@example.com', password='adminpass123')
        response = self.client.get(
            reverse('admin_console:admin_guide_section', args=['nonexistent'])
        )
        self.assertEqual(response.status_code, 404)

    def test_guide_404_for_invalid_article(self):
        self.client.login(email='admin@example.com', password='adminpass123')
        response = self.client.get(
            reverse('admin_console:admin_guide_article',
                    args=['test-sec', 'nonexistent'])
        )
        self.assertEqual(response.status_code, 404)

    def test_manage_view_accessible(self):
        self.client.login(email='admin@example.com', password='adminpass123')
        response = self.client.get(reverse('admin_console:admin_guide_manage'))
        self.assertEqual(response.status_code, 200)

    def test_edit_view_only_editable_articles(self):
        """Non-editable articles should return 404 for edit view."""
        self.client.login(email='admin@example.com', password='adminpass123')
        response = self.client.get(
            reverse('admin_console:admin_guide_article_edit',
                    args=[self.article.pk])
        )
        self.assertEqual(response.status_code, 404)


class AdminGuideContentTests(AdminTestMixin, TestCase):
    """Test content rendering and sidebar behavior."""

    def setUp(self):
        self.client = Client()
        self.admin = self.create_admin()
        self.client.login(email='admin@example.com', password='adminpass123')

        self.section1 = AdminGuideSection.objects.create(
            section_key='sec-1', title='First Section', icon='📄', order=10
        )
        self.section2 = AdminGuideSection.objects.create(
            section_key='sec-2', title='Second Section', icon='🧠', order=20
        )
        self.article1 = AdminGuideArticle.objects.create(
            section=self.section1, title='Art 1', slug='art-1',
            content='**Bold text** and `code`', order=10
        )
        self.article2 = AdminGuideArticle.objects.create(
            section=self.section2, title='Art 2', slug='art-2',
            content='## Heading\n\nParagraph', order=10
        )

    def test_sidebar_shows_all_sections(self):
        response = self.client.get(reverse('admin_console:admin_guide_home'))
        self.assertContains(response, 'First Section')
        self.assertContains(response, 'Second Section')

    def test_markdown_rendered_in_content(self):
        response = self.client.get(
            reverse('admin_console:admin_guide_article',
                    args=['sec-1', 'art-1'])
        )
        self.assertContains(response, '<strong>Bold text</strong>')
        self.assertContains(response, '<code>code</code>')

    def test_article_content_displayed(self):
        response = self.client.get(
            reverse('admin_console:admin_guide_article',
                    args=['sec-2', 'art-2'])
        )
        self.assertContains(response, 'Heading')
        self.assertContains(response, 'Paragraph')

    def test_active_section_highlighted(self):
        response = self.client.get(
            reverse('admin_console:admin_guide_section', args=['sec-1'])
        )
        content = response.content.decode()
        # The active section should have the 'active' class
        self.assertIn('active', content)

    def test_inactive_sections_hidden(self):
        self.section2.is_active = False
        self.section2.save()
        response = self.client.get(reverse('admin_console:admin_guide_home'))
        self.assertNotContains(response, 'Second Section')


class AdminGuideEditTests(AdminTestMixin, TestCase):
    """Test article editing functionality."""

    def setUp(self):
        self.client = Client()
        self.admin = self.create_admin()
        self.client.login(email='admin@example.com', password='adminpass123')

        self.section = AdminGuideSection.objects.create(
            section_key='edit-sec', title='Edit Section', order=10
        )
        self.editable_article = AdminGuideArticle.objects.create(
            section=self.section, title='Editable', slug='editable',
            content='Original content', order=10, is_editable=True
        )
        self.locked_article = AdminGuideArticle.objects.create(
            section=self.section, title='Locked', slug='locked',
            content='Locked content', order=20, is_editable=False
        )

    def test_edit_editable_article(self):
        response = self.client.post(
            reverse('admin_console:admin_guide_article_edit',
                    args=[self.editable_article.pk]),
            {'title': 'Updated Title', 'content': 'Updated content'}
        )
        self.assertEqual(response.status_code, 302)
        self.editable_article.refresh_from_db()
        self.assertEqual(self.editable_article.title, 'Updated Title')
        self.assertEqual(self.editable_article.content, 'Updated content')

    def test_cannot_edit_non_editable(self):
        response = self.client.get(
            reverse('admin_console:admin_guide_article_edit',
                    args=[self.locked_article.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_edit_form_displays(self):
        response = self.client.get(
            reverse('admin_console:admin_guide_article_edit',
                    args=[self.editable_article.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Original content')

    def test_edit_redirects_to_manage(self):
        response = self.client.post(
            reverse('admin_console:admin_guide_article_edit',
                    args=[self.editable_article.pk]),
            {'title': 'Updated', 'content': 'Updated'}
        )
        self.assertRedirects(response, reverse('admin_console:admin_guide_manage'))


class AdminGuideDashboardTileTests(AdminTestMixin, TestCase):
    """Test that the Admin Guide tile appears on the dashboard."""

    def setUp(self):
        self.client = Client()
        self.admin = self.create_admin()
        self.client.login(email='admin@example.com', password='adminpass123')

    def test_dashboard_has_guide_tile(self):
        response = self.client.get(reverse('admin_console:dashboard'))
        self.assertContains(response, 'Admin Guide')
        self.assertContains(response, 'admin-guide')
