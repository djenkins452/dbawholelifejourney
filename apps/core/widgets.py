"""
Reusable form widgets for the WLJ platform.

Provides mobile-friendly numeric input widgets that automatically
set the correct `inputmode` attribute for triggering the appropriate
mobile keyboard (numeric keypad for integers, decimal keypad for decimals).

Also provides `enhance_number_inputs()` which patches Django's built-in
NumberInput to auto-add `inputmode` based on the `step` attribute —
called once from CoreConfig.ready() to cover ALL existing forms globally.
"""
from django import forms


class NumericInput(forms.NumberInput):
    """
    NumberInput widget that triggers the numeric keypad on mobile devices.

    Use for integer fields (reps, steps, counts, years, etc.).
    Automatically sets inputmode="numeric" and pattern="[0-9]*".
    """

    def __init__(self, attrs=None):
        default_attrs = {
            'inputmode': 'numeric',
            'pattern': '[0-9]*',
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs)


class DecimalInput(forms.NumberInput):
    """
    NumberInput widget that triggers the decimal keypad on mobile devices.

    Use for decimal/float fields (weight, prices, glucose, distances, etc.).
    Automatically sets inputmode="decimal".
    """

    def __init__(self, attrs=None):
        default_attrs = {
            'inputmode': 'decimal',
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs)


def enhance_number_inputs():
    """
    Patch Django's NumberInput.get_context to auto-add `inputmode` to all
    NumberInput widgets that don't already specify one.

    Logic:
    - If `step` is fractional (e.g. 0.01, 0.1) or "any" → inputmode="decimal"
    - Otherwise (integers, no step) → inputmode="numeric" + pattern="[0-9]*"

    This is called once from CoreConfig.ready() and covers every
    forms.NumberInput in the entire project without modifying individual forms.
    """
    original_get_context = forms.NumberInput.get_context

    def enhanced_get_context(self, name, value, attrs):
        context = original_get_context(self, name, value, attrs)
        widget_attrs = context['widget']['attrs']

        # Skip if inputmode already explicitly set
        if 'inputmode' in widget_attrs:
            return context

        step = widget_attrs.get('step', '')
        if _is_decimal_step(step):
            widget_attrs['inputmode'] = 'decimal'
        else:
            widget_attrs['inputmode'] = 'numeric'
            if 'pattern' not in widget_attrs:
                widget_attrs['pattern'] = '[0-9]*'

        return context

    forms.NumberInput.get_context = enhanced_get_context


def _is_decimal_step(step):
    """Return True if the step value indicates a decimal field."""
    if not step:
        return False
    if str(step).lower() == 'any':
        return True
    try:
        return float(step) < 1
    except (ValueError, TypeError):
        return False


class WLJRichTextWidget(forms.Textarea):
    """The single WLJ Rich Text Editor widget — drop-in for any narrative field.

    Renders a hidden `<textarea>` that holds sanitized HTML (the canonical value
    posted with the form). `static/js/wlj-rich-text.js` finds the textarea via
    the ``data-wlj-rte`` marker, mounts a TipTap editor + toolbar around it, and
    mirrors the editor HTML back into the textarea on every change so normal form
    submission just works — no per-form JavaScript.

    Usage in a ModelForm::

        from apps.core.widgets import WLJRichTextWidget
        class Meta:
            widgets = {"body": WLJRichTextWidget(placeholder="Write freely…")}

    Every page that renders the widget must load the editor assets once via
    ``{% include "components/_rich_text_editor_assets.html" %}`` (the widget's
    ``Media`` also declares them for templates that emit ``{{ form.media }}``).
    """

    #: default endpoint name for image uploads (resolved lazily in render)
    upload_url_name = "core:rich_text_image_upload"

    def __init__(self, attrs=None, *, placeholder="", min_height=220,
                 upload_enabled=True):
        self.placeholder = placeholder
        self.min_height = min_height
        self.upload_enabled = upload_enabled
        super().__init__(attrs)

    @property
    def media(self):
        from django.forms import Media
        return Media(
            css={"all": ["css/wlj-rich-text.css"]},
            js=["vendor/tiptap/tiptap.bundle.js", "js/wlj-rich-text.js"],
        )

    def use_required_attribute(self, initial):
        # The source textarea is hidden; a hidden + `required` control triggers a
        # non-focusable browser validation error. Required is enforced server-side.
        return False

    def build_attrs(self, base_attrs, extra_attrs=None):
        attrs = super().build_attrs(base_attrs, extra_attrs)
        attrs["data-wlj-rte"] = "true"
        attrs["data-wlj-rte-placeholder"] = self.placeholder or ""
        attrs["data-wlj-rte-min-height"] = str(self.min_height)
        existing = attrs.get("class", "")
        attrs["class"] = (existing + " wlj-rte-source").strip()
        # The visible editor is contenteditable; the source textarea is hidden.
        attrs["hidden"] = "hidden"
        attrs["aria-hidden"] = "true"
        if self.upload_enabled:
            try:
                from django.urls import reverse
                attrs["data-wlj-rte-upload-url"] = reverse(self.upload_url_name)
            except Exception:
                # Endpoint not wired yet / reversal failed — degrade to no upload.
                attrs["data-wlj-rte-upload-url"] = ""
        else:
            attrs["data-wlj-rte-upload-url"] = ""
        return attrs
