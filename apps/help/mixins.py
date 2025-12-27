"""
Help System Mixins

Provides mixins for views to easily add HELP_CONTEXT_ID to their templates.
"""


class HelpContextMixin:
    """
    Mixin that adds help_context_id to template context.

    Usage:
        class MyView(HelpContextMixin, TemplateView):
            help_context_id = "DASHBOARD_HOME"

    The help_context_id will be available in the template for the help button.
    """

    help_context_id = "GENERAL"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["help_context_id"] = self.get_help_context_id()
        return context

    def get_help_context_id(self):
        """
        Override this method for dynamic help context based on request.

        Example:
            def get_help_context_id(self):
                if self.request.GET.get('mode') == 'create':
                    return "HEALTH_WORKOUT_CREATE"
                return "HEALTH_WORKOUT_LIST"
        """
        return self.help_context_id
