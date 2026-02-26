"""WLJ UI Test Framework — Artifact Capture Engine.

Captures screenshots (PNG) and HTML dumps on test failure
per Sections 9.1–9.3 of the master requirements.
"""

from datetime import datetime, timezone
from pathlib import Path


class ArtifactCapture:
    """Captures failure artifacts: screenshots and HTML page dumps.

    Artifacts are saved to module-scoped directories with the naming
    convention: {module}_{case_id}_{timestamp}.{ext}

    Artifacts are ephemeral (not committed to git) and exist for
    debugging/analysis purposes only.
    """

    def __init__(self, module, artifacts_dir=None):
        """Initialize with module name and optional artifacts directory.

        Args:
            module: Module name (e.g., 'journal', 'health').
            artifacts_dir: Override path for artifacts output.
                Defaults to ``modules/<module>/artifacts/``.
        """
        self.module = module
        base = Path(__file__).parent.parent
        self.artifacts_dir = Path(artifacts_dir) if artifacts_dir else (
            base / "modules" / module / "artifacts"
        )

    def capture_on_failure(self, page, case_id):
        """Capture both screenshot and HTML dump for a failed case.

        Args:
            page: Playwright Page object.
            case_id: The failing test case identifier.

        Returns:
            dict with keys ``screenshot`` and ``html_dump``, each
            containing the relative path string to the saved artifact,
            or ``None`` if capture failed.
        """
        self._ensure_dir()
        timestamp = _artifact_timestamp()

        screenshot_path = self._capture_screenshot(page, case_id, timestamp)
        html_path = self._capture_html(page, case_id, timestamp)

        return {
            "screenshot": str(screenshot_path) if screenshot_path else None,
            "html_dump": str(html_path) if html_path else None,
        }

    def capture_screenshot(self, page, case_id):
        """Capture only a screenshot for a failed case.

        Args:
            page: Playwright Page object.
            case_id: The failing test case identifier.

        Returns:
            Path to the saved screenshot, or ``None`` on error.
        """
        self._ensure_dir()
        return self._capture_screenshot(page, case_id, _artifact_timestamp())

    def capture_html(self, page, case_id):
        """Capture only an HTML dump for a failed case.

        Args:
            page: Playwright Page object.
            case_id: The failing test case identifier.

        Returns:
            Path to the saved HTML file, or ``None`` on error.
        """
        self._ensure_dir()
        return self._capture_html(page, case_id, _artifact_timestamp())

    # --- Internal helpers ---

    def _capture_screenshot(self, page, case_id, timestamp):
        """Take a full-page PNG screenshot.

        Per Section 9.1: full page screenshot, not viewport only.
        """
        filename = _artifact_filename(self.module, case_id, timestamp, "png")
        path = self.artifacts_dir / filename
        try:
            page.screenshot(path=str(path), full_page=True)
            return path
        except Exception:
            return None

    def _capture_html(self, page, case_id, timestamp):
        """Dump full page HTML content.

        Per Section 9.2: full ``page.content()`` at time of failure.
        """
        filename = _artifact_filename(self.module, case_id, timestamp, "html")
        path = self.artifacts_dir / filename
        try:
            content = page.content()
            path.write_text(content, encoding="utf-8")
            return path
        except Exception:
            return None

    def _ensure_dir(self):
        """Create artifact directory if it doesn't exist."""
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)


# --- Helpers ---

def _artifact_timestamp():
    """Return compact UTC timestamp for artifact filenames."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


def _artifact_filename(module, case_id, timestamp, ext):
    """Build artifact filename per Section 9 naming convention.

    Format: {module}_{case_id}_{timestamp}.{ext}
    """
    return f"{module}_{case_id}_{timestamp}.{ext}"
