"""WLJ UI Test Framework — Claude Fix Prompt Generator.

Generates actionable Claude Code fix prompts from test failures
per Sections 10.1–10.2 of the master requirements.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from .selectors import SelectorResolver


class PromptBuilder:
    """Generates ``claude_fix_prompt.md`` from failure data.

    The generated prompt is designed to be copy-pasted directly into a
    Claude Code session. One prompt file is generated per module,
    containing all failures from a single test run.
    """

    def __init__(self, run_id, module, base_url, timestamp=None):
        """Initialize with run context.

        Args:
            run_id: The unique run identifier (8-char hex).
            module: Module name (e.g., 'journal').
            base_url: The base URL tested against.
            timestamp: ISO timestamp of the run start.
                Defaults to current UTC time.
        """
        self.run_id = run_id
        self.module = module
        self.base_url = base_url
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat(
            timespec="milliseconds"
        )

    def generate(self, failures, output_path=None):
        """Generate the fix prompt markdown from a list of failures.

        Args:
            failures: List of failure dicts (from ``fail.ndjson`` or
                ``ReportWriter._fail_entries``). Each must have:
                ``case_id``, ``failed_step``, ``action``, ``selector``,
                ``error``. Optional: ``screenshot``, ``html_dump``,
                ``case_name``.
            output_path: Where to write the prompt file. Defaults to
                ``modules/<module>/reports/claude_fix_prompt.md``.

        Returns:
            str: The generated markdown content.
        """
        if not failures:
            return ""

        sections = [self._header(len(failures))]

        for i, failure in enumerate(failures, 1):
            sections.append(self._failure_section(failure, i, len(failures)))

        content = "\n".join(sections)

        if output_path is None:
            base = Path(__file__).parent.parent
            output_path = base / "modules" / self.module / "reports" / "claude_fix_prompt.md"

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

        return content

    def generate_from_ndjson(self, fail_ndjson_path, output_path=None):
        """Generate fix prompt by reading a ``fail.ndjson`` file.

        Args:
            fail_ndjson_path: Path to the ``fail.ndjson`` file.
            output_path: Where to write the prompt. Defaults to
                module reports directory.

        Returns:
            str: The generated markdown content.
        """
        failures = []
        path = Path(fail_ndjson_path)
        if path.exists():
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        failures.append(json.loads(line))
        return self.generate(failures, output_path)

    # --- Internal builders ---

    def _header(self, total_failures):
        """Build the prompt header with environment info."""
        return (
            "# WLJ UI Test Failure — Fix Required\n"
            "\n"
            "## Environment\n"
            f"- **Module:** {self.module}\n"
            f"- **Run ID:** {self.run_id}\n"
            f"- **Base URL:** {self.base_url}\n"
            f"- **Timestamp:** {self.timestamp}\n"
            f"- **Total failures:** {total_failures}\n"
        )

    def _failure_section(self, failure, index, total):
        """Build a single failure section."""
        case_id = failure.get("case_id", "unknown")
        case_name = failure.get("case_name", case_id)
        failed_step = failure.get("failed_step", "?")
        action = failure.get("action", "UNKNOWN")
        selector = failure.get("selector", "")
        error = failure.get("error", "No error message")
        screenshot = failure.get("screenshot")
        html_dump = failure.get("html_dump")

        # Resolve selector details for the prompt
        selector_details = self._selector_details(selector)

        lines = [
            f"## Failure {index} of {total}\n",
            f"### Case: {case_id}",
            f"**Name:** {case_name}\n",
            "### What Failed",
            f"- **Step:** {failed_step} ({action})",
            f"- **Action:** {action} on {selector_details['resolved']}",
            f"- **Error:** {error}\n",
            "### Selector Details",
            f"- **Strategy:** {selector_details['strategy']}",
            f"- **Value:** {selector_details['value']}",
            f"- **Resolved to:** {selector_details['resolved']}\n",
            "### Artifacts",
        ]

        if screenshot:
            lines.append(f"- **Screenshot:** {screenshot}")
        else:
            lines.append("- **Screenshot:** not captured")

        if html_dump:
            lines.append(f"- **HTML Dump:** {html_dump}")
        else:
            lines.append("- **HTML Dump:** not captured")

        lines.extend([
            "",
            "### Reproduction",
            "```bash",
            f"python wlj_ui_tests/run_suite.py --module {self.module} --headed",
            "```\n",
            "### Required Fix",
            *self._fix_instructions(selector_details, action),
            "\n---\n",
        ])

        return "\n".join(lines)

    def _selector_details(self, selector):
        """Extract strategy, value, and resolved string from selector."""
        if isinstance(selector, dict):
            info = SelectorResolver().get_strategy_info(selector)
            return {
                "strategy": info.get("strategy", "unknown"),
                "value": info.get("value", str(selector)),
                "resolved": info.get("resolved", str(selector)),
            }
        if isinstance(selector, str) and selector:
            return {
                "strategy": "css/xpath",
                "value": selector,
                "resolved": selector,
            }
        return {"strategy": "none", "value": "N/A", "resolved": "N/A"}

    def _fix_instructions(self, selector_details, action):
        """Generate actionable fix steps based on failure context."""
        strategy = selector_details["strategy"]
        value = selector_details["value"]
        resolved = selector_details["resolved"]

        instructions = []
        step = 1

        if strategy == "data-testid":
            instructions.append(
                f"{step}. Check if the element with `data-testid=\"{value}\"` "
                f"exists in the {self.module} templates"
            )
            step += 1
            instructions.append(
                f"{step}. If missing, add `data-testid=\"{value}\"` to the "
                f"target element"
            )
            step += 1
        elif resolved != "N/A":
            instructions.append(
                f"{step}. Check if the element matching `{resolved}` exists "
                f"in the {self.module} templates"
            )
            step += 1

        instructions.append(
            f"{step}. If present, check if the element is conditionally "
            f"rendered or hidden"
        )
        step += 1
        instructions.append(
            f"{step}. Verify the page has fully loaded before the "
            f"{action} action"
        )
        step += 1
        instructions.append(
            f"{step}. Run the test again to confirm the fix"
        )

        return instructions
