"""WLJ UI Test Framework — Browser Lifecycle Manager.

Manages the Playwright sync API lifecycle:
    sync_playwright() → chromium.launch() → new_context() → new_page()

Provides a context manager for clean startup and teardown, ensuring
the browser process is always terminated even on crashes.

Usage:
    with BrowserManager(headed=True) as bm:
        page = bm.page
        page.goto("http://localhost:8000")
        # ... run tests ...
    # Browser is closed automatically

Or manual lifecycle:
    bm = BrowserManager()
    bm.start()
    page = bm.page
    # ... run tests ...
    bm.stop()  # Always call this, even on error
"""

from playwright.sync_api import sync_playwright


class BrowserManager:
    """Manages Playwright browser lifecycle with clean teardown.

    Encapsulates sync_playwright → chromium.launch → new_context → new_page
    and guarantees cleanup via context manager or explicit stop().
    """

    # Default viewport matching common desktop resolution
    DEFAULT_VIEWPORT = {"width": 1280, "height": 800}

    # Default timeouts (milliseconds)
    DEFAULT_NAVIGATION_TIMEOUT = 30000
    DEFAULT_TIMEOUT = 10000

    def __init__(self, headed=False, slow_mo=0, viewport=None,
                 navigation_timeout=None, timeout=None):
        """Initialize browser manager.

        Args:
            headed: If True, launch browser with visible UI.
                Useful for debugging.
            slow_mo: Slow down operations by this many ms.
                Useful for debugging (e.g., slow_mo=500).
            viewport: Dict with 'width' and 'height' keys.
                Defaults to 1280x800.
            navigation_timeout: Navigation timeout in ms.
                Defaults to 30000.
            timeout: Default action timeout in ms.
                Defaults to 10000.
        """
        self.headed = headed
        self.slow_mo = slow_mo
        self.viewport = viewport or self.DEFAULT_VIEWPORT
        self.navigation_timeout = (
            navigation_timeout or self.DEFAULT_NAVIGATION_TIMEOUT
        )
        self.timeout = timeout or self.DEFAULT_TIMEOUT

        # Playwright objects — set during start()
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._started = False

    @property
    def page(self):
        """The Playwright Page object. Available after start()."""
        if not self._page:
            raise RuntimeError(
                "Browser not started. Call start() or use as context manager."
            )
        return self._page

    @property
    def context(self):
        """The Playwright BrowserContext. Available after start()."""
        if not self._context:
            raise RuntimeError("Browser not started.")
        return self._context

    @property
    def browser(self):
        """The Playwright Browser instance. Available after start()."""
        if not self._browser:
            raise RuntimeError("Browser not started.")
        return self._browser

    def start(self):
        """Launch Playwright, browser, context, and page.

        Call stop() when done, or use the context manager instead.

        Returns:
            The Playwright Page object.
        """
        if self._started:
            return self._page

        self._playwright = sync_playwright().start()

        launch_args = {
            "headless": not self.headed,
        }
        if self.slow_mo:
            launch_args["slow_mo"] = self.slow_mo

        self._browser = self._playwright.chromium.launch(**launch_args)

        self._context = self._browser.new_context(
            viewport=self.viewport,
        )

        # Set default timeouts on the context
        self._context.set_default_navigation_timeout(self.navigation_timeout)
        self._context.set_default_timeout(self.timeout)

        self._page = self._context.new_page()

        # Auto-accept browser dialogs (confirm, alert, prompt) so that
        # tests can interact with forms that use native confirm() guards
        # (e.g., data-confirm-delete).  Without this, Playwright
        # auto-*dismisses* dialogs, causing confirm() to return False
        # and blocking form submissions.
        self._page.on("dialog", lambda dialog: dialog.accept())

        self._started = True

        return self._page

    def stop(self):
        """Close page, context, browser, and Playwright — in order.

        Safe to call multiple times. Swallows individual close errors
        to ensure all resources are released.
        """
        if not self._started:
            return

        for resource, name in [
            (self._page, "page"),
            (self._context, "context"),
            (self._browser, "browser"),
        ]:
            if resource:
                try:
                    resource.close()
                except Exception:
                    pass

        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass

        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        self._started = False

    # --- Context manager ---

    def __enter__(self):
        """Start browser on context entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop browser on context exit (always, even on error)."""
        self.stop()
        return False  # Don't suppress exceptions
