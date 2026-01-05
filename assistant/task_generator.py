"""
Improvement Task Generator for WLJ Personal Data Query System.

Owner: admin@wholelifejourney.com

This module creates structured improvement tasks when knowledge gaps are detected.
Tasks include code templates and test requirements for implementing fixes.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from django.utils import timezone

from .gap_detector import GapSeverity, GapType, categorize_gap_severity


# Project name constant for task categorization
PROJECT_NAME = 'Personal Assistant Growth'


@dataclass
class ImprovementTask:
    """Represents a structured improvement task for the project management system."""

    title: str
    description: str
    gap_type: GapType
    severity: GapSeverity
    original_query: str
    suggested_fix: str
    code_template: str
    test_requirements: List[str]
    requires_approval: bool
    created_at: datetime = field(default_factory=timezone.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert the task to a dictionary for serialization."""
        return {
            'title': self.title,
            'description': self.description,
            'gap_type': self.gap_type.value if self.gap_type else None,
            'severity': self.severity.value if self.severity else None,
            'original_query': self.original_query,
            'suggested_fix': self.suggested_fix,
            'code_template': self.code_template,
            'test_requirements': self.test_requirements,
            'requires_approval': self.requires_approval,
            'created_at': self.created_at.isoformat(),
            'project': PROJECT_NAME,
        }


def generate_improvement_task(gap_result: Dict[str, Any]) -> Optional[ImprovementTask]:
    """
    Generate an improvement task based on gap detection results.

    This function analyzes the gap type and creates a structured task
    with appropriate code templates and test requirements.

    Args:
        gap_result: The result from detect_knowledge_gap() containing:
            - gap_detected (bool)
            - gap_type (GapType)
            - original_query (str)
            - suggested_category (str or None)
            - timestamp (datetime)

    Returns:
        ImprovementTask if a gap was detected, None otherwise.

    Example:
        >>> gap_result = {
        ...     'gap_detected': True,
        ...     'gap_type': GapType.MISSING_KEYWORDS,
        ...     'original_query': 'What was my hydration today?',
        ...     'suggested_category': 'hydration',
        ... }
        >>> task = generate_improvement_task(gap_result)
        >>> task.title
        'Add keywords for hydration data type'
    """
    if not gap_result.get('gap_detected'):
        return None

    gap_type = gap_result.get('gap_type')
    original_query = gap_result.get('original_query', '')
    suggested_category = gap_result.get('suggested_category', 'unknown')
    severity = categorize_gap_severity(gap_type)

    # Determine if approval is required based on severity
    requires_approval = severity != GapSeverity.LOW

    # Generate task based on gap type
    if gap_type == GapType.MISSING_KEYWORDS:
        return _generate_missing_keywords_task(
            original_query, suggested_category, severity, requires_approval
        )
    elif gap_type == GapType.NO_DATA_METHOD:
        return _generate_no_data_method_task(
            original_query, suggested_category, severity, requires_approval
        )
    elif gap_type == GapType.UNSUPPORTED_QUERY_PATTERN:
        return _generate_unsupported_pattern_task(
            original_query, suggested_category, severity, requires_approval
        )
    elif gap_type == GapType.UNKNOWN_DATA_TYPE:
        return _generate_unknown_data_type_task(
            original_query, suggested_category, severity, requires_approval
        )

    return None


def _generate_missing_keywords_task(
    original_query: str,
    suggested_category: str,
    severity: GapSeverity,
    requires_approval: bool,
) -> ImprovementTask:
    """Generate task to add keywords to intent_detector.py."""
    title = f"Add keywords for '{suggested_category}' data type"
    description = (
        f"User query '{original_query}' was not recognized because the keyword "
        f"'{suggested_category}' is not in the PERSONAL_DATA_KEYWORDS dictionary. "
        f"Add appropriate keywords to enable detection of this data type."
    )
    suggested_fix = (
        f"Add '{suggested_category}' and related terms to the appropriate "
        f"data type category in PERSONAL_DATA_KEYWORDS in intent_detector.py"
    )

    code_template = generate_code_template(GapType.MISSING_KEYWORDS, suggested_category)
    test_requirements = [
        f"Test that '{suggested_category}' keyword is detected",
        "Test that related terms are also detected",
        "Verify no regression in existing keyword detection",
    ]

    return ImprovementTask(
        title=title,
        description=description,
        gap_type=GapType.MISSING_KEYWORDS,
        severity=severity,
        original_query=original_query,
        suggested_fix=suggested_fix,
        code_template=code_template,
        test_requirements=test_requirements,
        requires_approval=requires_approval,
    )


def _generate_no_data_method_task(
    original_query: str,
    suggested_category: str,
    severity: GapSeverity,
    requires_approval: bool,
) -> ImprovementTask:
    """Generate task to add new method to data_service.py."""
    title = f"Add query method for '{suggested_category}' data"
    description = (
        f"User query '{original_query}' detected '{suggested_category}' data type, "
        f"but PersonalDataService has no method to retrieve this data. "
        f"Implement get_{suggested_category}_data() method."
    )
    suggested_fix = (
        f"Add get_{suggested_category}_data() method to PersonalDataService class "
        f"in data_service.py, following the pattern of existing methods like get_weight_data()"
    )

    code_template = generate_code_template(GapType.NO_DATA_METHOD, suggested_category)
    test_requirements = [
        f"Test get_{suggested_category}_data() returns correct data structure",
        f"Test get_{suggested_category}_data() handles no data case",
        f"Test get_{suggested_category}_data() respects since_date filter",
        f"Test query_by_intent() includes '{suggested_category}' in query_map",
    ]

    return ImprovementTask(
        title=title,
        description=description,
        gap_type=GapType.NO_DATA_METHOD,
        severity=severity,
        original_query=original_query,
        suggested_fix=suggested_fix,
        code_template=code_template,
        test_requirements=test_requirements,
        requires_approval=requires_approval,
    )


def _generate_unsupported_pattern_task(
    original_query: str,
    suggested_category: str,
    severity: GapSeverity,
    requires_approval: bool,
) -> ImprovementTask:
    """Generate task to add support for unsupported query pattern."""
    title = f"Add support for {suggested_category}"
    description = (
        f"User query '{original_query}' uses a query pattern ({suggested_category}) "
        f"that is not currently supported. Implement support for this pattern type."
    )
    suggested_fix = (
        f"Add support for {suggested_category} in the appropriate module. "
        f"This may require updates to date_parser.py, data_service.py, or "
        f"adding new analysis capabilities."
    )

    code_template = generate_code_template(
        GapType.UNSUPPORTED_QUERY_PATTERN, suggested_category
    )
    test_requirements = [
        f"Test that {suggested_category} are recognized",
        f"Test that {suggested_category} return appropriate results",
        "Verify no regression in existing query patterns",
    ]

    return ImprovementTask(
        title=title,
        description=description,
        gap_type=GapType.UNSUPPORTED_QUERY_PATTERN,
        severity=severity,
        original_query=original_query,
        suggested_fix=suggested_fix,
        code_template=code_template,
        test_requirements=test_requirements,
        requires_approval=requires_approval,
    )


def _generate_unknown_data_type_task(
    original_query: str,
    suggested_category: str,
    severity: GapSeverity,
    requires_approval: bool,
) -> ImprovementTask:
    """Generate task for unknown data type that may require model changes."""
    title = f"Evaluate new data type: '{suggested_category}'"
    description = (
        f"User query '{original_query}' suggests tracking '{suggested_category}' data, "
        f"which is not currently a recognized data type. Evaluate whether to add "
        f"this as a new tracked category, which may require model changes."
    )
    suggested_fix = (
        f"1. Evaluate if '{suggested_category}' should be a new data type\n"
        f"2. If yes, create a model in the appropriate app\n"
        f"3. Add keywords to PERSONAL_DATA_KEYWORDS\n"
        f"4. Add query method to PersonalDataService"
    )

    code_template = generate_code_template(GapType.UNKNOWN_DATA_TYPE, suggested_category)
    test_requirements = [
        f"Test model creation for {suggested_category} (if applicable)",
        f"Test keyword detection for {suggested_category}",
        f"Test data retrieval for {suggested_category}",
        "Integration test for full query flow",
    ]

    return ImprovementTask(
        title=title,
        description=description,
        gap_type=GapType.UNKNOWN_DATA_TYPE,
        severity=severity,
        original_query=original_query,
        suggested_fix=suggested_fix,
        code_template=code_template,
        test_requirements=test_requirements,
        requires_approval=requires_approval,
    )


def generate_code_template(gap_type: GapType, category: str) -> str:
    """
    Generate code template for fixing the identified gap.

    Args:
        gap_type: The type of gap that needs to be fixed.
        category: The suggested category/keyword for the fix.

    Returns:
        A string containing the code template to implement the fix.

    Example:
        >>> template = generate_code_template(GapType.MISSING_KEYWORDS, 'hydration')
        >>> 'hydration' in template
        True
    """
    if gap_type == GapType.MISSING_KEYWORDS:
        return _keyword_code_template(category)
    elif gap_type == GapType.NO_DATA_METHOD:
        return _data_method_code_template(category)
    elif gap_type == GapType.UNSUPPORTED_QUERY_PATTERN:
        return _query_pattern_code_template(category)
    elif gap_type == GapType.UNKNOWN_DATA_TYPE:
        return _new_data_type_code_template(category)

    return f"# TODO: Implement fix for {category}"


def _keyword_code_template(category: str) -> str:
    """Generate code template for adding keywords."""
    return f'''# Add to PERSONAL_DATA_KEYWORDS in intent_detector.py

# Option 1: Add to existing category if related
'existing_category': [
    # ... existing keywords ...
    '{category}',  # New keyword
],

# Option 2: Create new category if distinct
'{category}': [
    '{category}',
    # Add related terms here
],
'''


def _data_method_code_template(category: str) -> str:
    """Generate code template for adding a data query method."""
    method_name = f"get_{category}_data"
    return f'''# Add to PersonalDataService in data_service.py

def {method_name}(
    self,
    since_date: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    """
    Retrieve and summarize the user's {category} data.

    Args:
        since_date: Optional datetime to filter entries from this date.

    Returns:
        None if no {category} entries exist for the user.
        Otherwise, a dictionary containing the data summary.
    """
    # Check cache first
    cache_key = _generate_cache_key(self.user.id, '{category}', since_date)
    cached_data = cache.get(cache_key)
    if cached_data is not None:
        return cached_data

    # Import the model (adjust import path as needed)
    # from apps.<app_name>.models import <ModelName>

    # Build base queryset
    # queryset = <ModelName>.objects.filter(user=self.user)

    # Apply date filter if provided
    # if since_date:
    #     queryset = queryset.filter(created_at__gte=since_date)

    # Check if any entries exist
    # if not queryset.exists():
    #     return None

    # Build and return result
    result = {{
        'type': '{category}',
        # Add relevant data fields
    }}

    # Cache the result
    cache.set(cache_key, result, PERSONAL_DATA_CACHE_TTL)

    return result


# Also add to query_map in query_by_intent():
query_map: Dict[str, callable] = {{
    # ... existing mappings ...
    '{category}': self.{method_name},
}}
'''


def _query_pattern_code_template(category: str) -> str:
    """Generate code template for adding query pattern support."""
    return f'''# Supporting {category} requires analysis infrastructure

# For comparison queries:
# Add to data_service.py or create new analysis module

def compare_data(
    self,
    data_type: str,
    period1_start: datetime,
    period1_end: datetime,
    period2_start: datetime,
    period2_end: datetime,
) -> Dict[str, Any]:
    """Compare data between two time periods."""
    # Fetch data for both periods
    # Calculate differences and percentages
    # Return comparison results
    pass


# For correlation analysis:
def analyze_correlation(
    self,
    data_type1: str,
    data_type2: str,
    since_date: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Analyze correlation between two data types."""
    # Fetch data for both types
    # Calculate correlation coefficient
    # Return analysis results
    pass


# For predictive queries:
def predict_trend(
    self,
    data_type: str,
    days_ahead: int = 7,
) -> Dict[str, Any]:
    """Predict future values based on historical trends."""
    # Fetch historical data
    # Apply trend analysis
    # Return predictions
    pass
'''


def _new_data_type_code_template(category: str) -> str:
    """Generate code template for adding a new data type."""
    model_name = category.title().replace('_', '')
    return f'''# Step 1: Create model in appropriate app (e.g., apps/health/models.py)

class {model_name}Entry(models.Model):
    """Model for tracking {category} data."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='{category}_entries',
    )
    value = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=20, default='')
    recorded_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-recorded_at']
        verbose_name = '{category} entry'
        verbose_name_plural = '{category} entries'

    def __str__(self):
        return f"{{self.user.email}}: {{self.value}} ({{self.recorded_at}})"


# Step 2: Add keywords to PERSONAL_DATA_KEYWORDS in intent_detector.py
'{category}': [
    '{category}',
    # Add related terms
],


# Step 3: Add to SUPPORTED_DATA_TYPES in gap_detector.py
SUPPORTED_DATA_TYPES = [
    # ... existing types ...
    '{category}',
]


# Step 4: Add to DATA_TYPES_WITH_METHODS after implementing the query method
DATA_TYPES_WITH_METHODS = [
    # ... existing types ...
    '{category}',
]


# Step 5: Implement get_{category}_data() in PersonalDataService
# (See NO_DATA_METHOD template)
'''


def generate_test_template(gap_type: GapType, category: str) -> str:
    """
    Generate test code template for the improvement task.

    Args:
        gap_type: The type of gap that needs to be fixed.
        category: The suggested category/keyword for the fix.

    Returns:
        A string containing the test code template.

    Example:
        >>> template = generate_test_template(GapType.MISSING_KEYWORDS, 'hydration')
        >>> 'hydration' in template
        True
    """
    if gap_type == GapType.MISSING_KEYWORDS:
        return _keyword_test_template(category)
    elif gap_type == GapType.NO_DATA_METHOD:
        return _data_method_test_template(category)
    elif gap_type == GapType.UNSUPPORTED_QUERY_PATTERN:
        return _query_pattern_test_template(category)
    elif gap_type == GapType.UNKNOWN_DATA_TYPE:
        return _new_data_type_test_template(category)

    return f"# TODO: Add tests for {category}"


def _keyword_test_template(category: str) -> str:
    """Generate test template for keyword addition."""
    return f'''# Add to test_intent_detector.py

class Test{category.title()}Keywords(unittest.TestCase):
    """Tests for {category} keyword detection."""

    def test_{category}_keyword_detected(self):
        """Ensure '{category}' keyword is detected."""
        result = detect_personal_data_intent("What was my {category} today?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('{category}', result['data_types'])

    def test_{category}_related_terms(self):
        """Ensure related terms are also detected."""
        # Add tests for related terms
        pass
'''


def _data_method_test_template(category: str) -> str:
    """Generate test template for data query method."""
    return f'''# Add to test_data_service.py

class TestGet{category.title()}Data(TestCase):
    """Tests for get_{category}_data() method."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self.service = PersonalDataService(self.user)

    def test_{category}_data_returns_none_when_empty(self):
        """Should return None when user has no {category} data."""
        result = self.service.get_{category}_data()
        self.assertIsNone(result)

    def test_{category}_data_returns_correct_structure(self):
        """Should return correctly structured data."""
        # Create test data
        # result = self.service.get_{category}_data()
        # self.assertEqual(result['type'], '{category}')
        pass

    def test_{category}_data_respects_since_date(self):
        """Should filter by since_date when provided."""
        # Create test data with various dates
        # Test filtering
        pass
'''


def _query_pattern_test_template(category: str) -> str:
    """Generate test template for query pattern support."""
    return f'''# Add to appropriate test file

class Test{category.title().replace(" ", "")}Support(TestCase):
    """Tests for {category} support."""

    def test_{category.lower().replace(" ", "_")}_recognized(self):
        """Ensure {category} are recognized."""
        # Test pattern recognition
        pass

    def test_{category.lower().replace(" ", "_")}_returns_results(self):
        """Ensure {category} return appropriate results."""
        # Test result generation
        pass

    def test_no_regression_in_existing_patterns(self):
        """Verify existing query patterns still work."""
        # Test existing functionality
        pass
'''


def _new_data_type_test_template(category: str) -> str:
    """Generate test template for new data type."""
    model_name = category.title().replace('_', '')
    return f'''# Tests for new {category} data type

class Test{model_name}Model(TestCase):
    """Tests for {model_name}Entry model."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='test@example.com',
            password='testpass123'
        )

    def test_create_{category}_entry(self):
        """Can create a {category} entry."""
        # entry = {model_name}Entry.objects.create(
        #     user=self.user,
        #     value=Decimal('100.0'),
        # )
        # self.assertIsNotNone(entry.id)
        pass

    def test_{category}_ordering(self):
        """Entries are ordered by recorded_at descending."""
        pass


class Test{category.title()}KeywordDetection(unittest.TestCase):
    """Tests for {category} keyword detection."""

    def test_{category}_keyword_detected(self):
        """Ensure '{category}' keyword is detected."""
        result = detect_personal_data_intent("What was my {category} today?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('{category}', result['data_types'])


class Test{category.title()}DataRetrieval(TestCase):
    """Tests for {category} data retrieval."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self.service = PersonalDataService(self.user)

    def test_get_{category}_data(self):
        """Test retrieving {category} data."""
        # Create test data
        # result = self.service.get_{category}_data()
        # Assert expected results
        pass
'''
