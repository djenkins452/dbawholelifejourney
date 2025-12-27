"""
Tests for Help System Mixins
"""
from django.test import TestCase, RequestFactory
from django.views.generic import TemplateView
from django.contrib.auth import get_user_model

from apps.help.mixins import HelpContextMixin

User = get_user_model()


class HelpContextMixinTests(TestCase):
    """Tests for HelpContextMixin."""

    def setUp(self):
        """Set up test data."""
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )

    def test_static_help_context_id(self):
        """Test that static help_context_id is added to context."""

        class TestView(HelpContextMixin, TemplateView):
            template_name = "base.html"
            help_context_id = "TEST_CONTEXT"

        request = self.factory.get('/')
        request.user = self.user

        view = TestView()
        view.request = request
        context = view.get_context_data()

        self.assertEqual(context['help_context_id'], 'TEST_CONTEXT')

    def test_default_help_context_id(self):
        """Test that default help_context_id is GENERAL."""

        class TestView(HelpContextMixin, TemplateView):
            template_name = "base.html"

        request = self.factory.get('/')
        request.user = self.user

        view = TestView()
        view.request = request
        context = view.get_context_data()

        self.assertEqual(context['help_context_id'], 'GENERAL')

    def test_dynamic_help_context_id(self):
        """Test that get_help_context_id can be overridden."""

        class TestView(HelpContextMixin, TemplateView):
            template_name = "base.html"

            def get_help_context_id(self):
                if self.request.GET.get('mode') == 'create':
                    return "CREATE_MODE"
                return "LIST_MODE"

        # Test list mode
        request = self.factory.get('/')
        request.user = self.user

        view = TestView()
        view.request = request
        context = view.get_context_data()

        self.assertEqual(context['help_context_id'], 'LIST_MODE')

        # Test create mode
        request = self.factory.get('/?mode=create')
        request.user = self.user

        view = TestView()
        view.request = request
        context = view.get_context_data()

        self.assertEqual(context['help_context_id'], 'CREATE_MODE')
