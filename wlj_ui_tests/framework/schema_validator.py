"""WLJ UI Test Framework — YAML Schema Loader and Validator.

Validates YAML suite files against the required schema
per Sections 7.1–7.2 of the master requirements.
"""

import yaml
from pathlib import Path

from .version import MIN_SCHEMA_VERSION, MAX_SCHEMA_VERSION


class ValidationError(Exception):
    """Raised when a YAML suite file fails schema validation."""

    def __init__(self, errors):
        self.errors = errors if isinstance(errors, list) else [errors]
        super().__init__(f"Validation failed with {len(self.errors)} error(s): "
                         + "; ".join(self.errors))


# --- Valid enum values per Section 7.2 ---

VALID_AUTH_STRATEGIES = {"session", "token", "none"}
VALID_ACTIONS = {"NAVIGATE", "CLICK", "TYPE", "SELECT", "WAIT", "ASSERT"}
VALID_SELECTOR_STRATEGIES = {"data-testid", "name", "id", "text_contains", "role"}
VALID_PRIORITIES = {"high", "medium", "low"}
VALID_ASSERT_TYPES = {
    "text_contains", "text_equals",
    "url_contains", "url_equals",
    "element_visible", "element_not_visible",
    "element_count", "attribute_equals",
}

# Actions that require a selector
SELECTOR_REQUIRED_ACTIONS = {"CLICK", "TYPE", "SELECT", "ASSERT"}
# Actions that require specific fields
ACTION_REQUIRED_FIELDS = {
    "NAVIGATE": ["url"],
    "TYPE": ["input"],
    "SELECT": ["value"],
}
# Assert types that require a selector
SELECTOR_REQUIRED_ASSERTS = {
    "text_contains", "text_equals",
    "element_visible", "element_not_visible",
    "element_count", "attribute_equals",
}


class SchemaValidator:
    """Validates YAML suite files against the WLJ test schema.

    Performs structural validation of suite metadata, auth config,
    defaults, cases, steps, assertions, and cleanup blocks.
    Returns descriptive error messages for all validation failures.
    """

    def validate_file(self, path):
        """Load and validate a YAML suite file.

        Args:
            path: Path to the YAML file.

        Returns:
            dict: The parsed and validated suite data.

        Raises:
            ValidationError: If the file is invalid.
            FileNotFoundError: If the file doesn't exist.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Suite file not found: {path}")

        with open(path) as f:
            try:
                data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                raise ValidationError(f"YAML parse error: {e}") from e

        return self.validate(data)

    def validate(self, data):
        """Validate a parsed suite dict against the schema.

        Args:
            data: Parsed YAML suite dictionary.

        Returns:
            dict: The validated suite data (same object).

        Raises:
            ValidationError: With list of all errors found.
        """
        errors = []

        if not isinstance(data, dict):
            raise ValidationError("Suite must be a YAML mapping (dict)")

        self._validate_metadata(data, errors)
        self._validate_auth(data.get("auth"), errors)
        self._validate_defaults(data.get("defaults"), errors)
        self._validate_cases(data.get("cases"), errors)

        if errors:
            raise ValidationError(errors)

        return data

    # --- Section validators ---

    def _validate_metadata(self, data, errors):
        """Validate top-level required fields: version, suite, module."""
        # version
        version = data.get("version")
        if not version:
            errors.append("Missing required field: 'version'")
        elif not isinstance(version, str):
            errors.append("Field 'version' must be a string")
        elif not _version_in_range(version):
            errors.append(
                f"Unsupported schema version '{version}'. "
                f"Supported: {MIN_SCHEMA_VERSION}–{MAX_SCHEMA_VERSION}"
            )

        # suite
        if not data.get("suite"):
            errors.append("Missing required field: 'suite'")
        elif not isinstance(data["suite"], str):
            errors.append("Field 'suite' must be a string")

        # module
        if not data.get("module"):
            errors.append("Missing required field: 'module'")
        elif not isinstance(data["module"], str):
            errors.append("Field 'module' must be a string")

    def _validate_auth(self, auth, errors):
        """Validate auth configuration per Section 7.2."""
        if auth is None:
            errors.append("Missing required section: 'auth'")
            return

        if not isinstance(auth, dict):
            errors.append("Section 'auth' must be a mapping")
            return

        strategy = auth.get("strategy")
        if not strategy:
            errors.append("Missing required field: 'auth.strategy'")
        elif strategy not in VALID_AUTH_STRATEGIES:
            errors.append(
                f"Invalid auth.strategy '{strategy}'. "
                f"Must be one of: {', '.join(sorted(VALID_AUTH_STRATEGIES))}"
            )
        else:
            # Conditional requirements
            if strategy in ("session", "token"):
                if not auth.get("username"):
                    errors.append(
                        f"'auth.username' is required for strategy '{strategy}'"
                    )
                if not auth.get("password"):
                    errors.append(
                        f"'auth.password' is required for strategy '{strategy}'"
                    )
            if strategy == "session" and not auth.get("login_url"):
                errors.append(
                    "'auth.login_url' is required for strategy 'session'"
                )

    def _validate_defaults(self, defaults, errors):
        """Validate suite-wide defaults (all optional)."""
        if defaults is None:
            return  # Entire section is optional

        if not isinstance(defaults, dict):
            errors.append("Section 'defaults' must be a mapping")
            return

        timeout = defaults.get("timeout_ms")
        if timeout is not None and not isinstance(timeout, (int, float)):
            errors.append("'defaults.timeout_ms' must be a number")

        for bool_field in ("screenshot_on_failure", "html_dump_on_failure"):
            val = defaults.get(bool_field)
            if val is not None and not isinstance(val, bool):
                errors.append(f"'defaults.{bool_field}' must be a boolean")

    def _validate_cases(self, cases, errors):
        """Validate the cases array."""
        if cases is None:
            errors.append("Missing required section: 'cases'")
            return

        if not isinstance(cases, list):
            errors.append("Section 'cases' must be a list")
            return

        seen_ids = set()
        for i, case in enumerate(cases):
            prefix = f"cases[{i}]"
            if not isinstance(case, dict):
                errors.append(f"{prefix}: must be a mapping")
                continue
            self._validate_case(case, i, seen_ids, errors)

    def _validate_case(self, case, index, seen_ids, errors):
        """Validate a single test case."""
        prefix = f"cases[{index}]"

        # Required: id
        case_id = case.get("id")
        if not case_id:
            errors.append(f"{prefix}: missing required field 'id'")
        elif not isinstance(case_id, str):
            errors.append(f"{prefix}: 'id' must be a string")
        elif case_id in seen_ids:
            errors.append(f"{prefix}: duplicate case id '{case_id}'")
        else:
            seen_ids.add(case_id)

        # Required: name
        if not case.get("name"):
            errors.append(f"{prefix}: missing required field 'name'")

        # Optional: priority
        priority = case.get("priority")
        if priority and priority not in VALID_PRIORITIES:
            errors.append(
                f"{prefix}: invalid priority '{priority}'. "
                f"Must be one of: {', '.join(sorted(VALID_PRIORITIES))}"
            )

        # Optional: tags
        tags = case.get("tags")
        if tags is not None and not isinstance(tags, list):
            errors.append(f"{prefix}: 'tags' must be a list")

        # Steps
        steps = case.get("steps")
        if steps is not None:
            if not isinstance(steps, list):
                errors.append(f"{prefix}.steps: must be a list")
            else:
                for j, step in enumerate(steps):
                    self._validate_step(step, f"{prefix}.steps[{j}]", errors)

        # Asserts
        asserts = case.get("asserts")
        if asserts is not None:
            if not isinstance(asserts, list):
                errors.append(f"{prefix}.asserts: must be a list")
            else:
                for j, assertion in enumerate(asserts):
                    self._validate_assert(
                        assertion, f"{prefix}.asserts[{j}]", errors
                    )

        # Cleanup
        cleanup = case.get("cleanup")
        if cleanup is not None:
            if not isinstance(cleanup, list):
                errors.append(f"{prefix}.cleanup: must be a list")
            else:
                for j, step in enumerate(cleanup):
                    self._validate_step(
                        step, f"{prefix}.cleanup[{j}]", errors
                    )

    def _validate_step(self, step, prefix, errors):
        """Validate a single step definition."""
        if not isinstance(step, dict):
            errors.append(f"{prefix}: must be a mapping")
            return

        action = step.get("action", "")
        if not action:
            errors.append(f"{prefix}: missing required field 'action'")
            return

        action_upper = action.upper()
        if action_upper not in VALID_ACTIONS:
            errors.append(
                f"{prefix}: invalid action '{action}'. "
                f"Must be one of: {', '.join(sorted(VALID_ACTIONS))}"
            )
            return

        # Selector required for certain actions
        if action_upper in SELECTOR_REQUIRED_ACTIONS and not step.get("selector"):
            errors.append(
                f"{prefix}: action '{action_upper}' requires a 'selector'"
            )

        # Validate selector if present
        if step.get("selector"):
            self._validate_selector(step["selector"], prefix, errors)

        # Action-specific required fields
        for field in ACTION_REQUIRED_FIELDS.get(action_upper, []):
            if not step.get(field) and field not in step:
                errors.append(
                    f"{prefix}: action '{action_upper}' requires field '{field}'"
                )

    def _validate_assert(self, assertion, prefix, errors):
        """Validate a single assertion definition."""
        if not isinstance(assertion, dict):
            errors.append(f"{prefix}: must be a mapping")
            return

        assert_type = assertion.get("type", "")
        if not assert_type:
            errors.append(f"{prefix}: missing required field 'type'")
            return

        if assert_type not in VALID_ASSERT_TYPES:
            errors.append(
                f"{prefix}: invalid assertion type '{assert_type}'. "
                f"Must be one of: {', '.join(sorted(VALID_ASSERT_TYPES))}"
            )
            return

        # Selector required for element-based assertions
        if assert_type in SELECTOR_REQUIRED_ASSERTS and not assertion.get("selector"):
            errors.append(
                f"{prefix}: assertion '{assert_type}' requires a 'selector'"
            )

        # Validate selector if present
        if assertion.get("selector"):
            self._validate_selector(assertion["selector"], prefix, errors)

        # Expected value required for all assertions
        if "expected" not in assertion and assert_type not in (
            "element_visible", "element_not_visible"
        ):
            errors.append(
                f"{prefix}: assertion '{assert_type}' requires field 'expected'"
            )

        # attribute_equals needs 'attribute' field
        if assert_type == "attribute_equals" and not assertion.get("attribute"):
            errors.append(
                f"{prefix}: assertion 'attribute_equals' requires field 'attribute'"
            )

    def _validate_selector(self, selector, prefix, errors):
        """Validate a selector object."""
        if isinstance(selector, str):
            return  # Raw CSS/XPath passthrough is valid

        if not isinstance(selector, dict):
            errors.append(f"{prefix}.selector: must be a mapping or string")
            return

        strategy = selector.get("strategy")
        if not strategy:
            errors.append(f"{prefix}.selector: missing required field 'strategy'")
        elif strategy not in VALID_SELECTOR_STRATEGIES:
            errors.append(
                f"{prefix}.selector: invalid strategy '{strategy}'. "
                f"Must be one of: {', '.join(sorted(VALID_SELECTOR_STRATEGIES))}"
            )

        if not selector.get("value"):
            errors.append(f"{prefix}.selector: missing required field 'value'")


# --- Helpers ---

def _version_in_range(version):
    """Check if a schema version string is within supported range."""
    try:
        parts = [int(x) for x in version.split(".")]
        min_parts = [int(x) for x in MIN_SCHEMA_VERSION.split(".")]
        max_parts = [int(x) for x in MAX_SCHEMA_VERSION.split(".")]
        return min_parts <= parts <= max_parts
    except (ValueError, AttributeError):
        return False
