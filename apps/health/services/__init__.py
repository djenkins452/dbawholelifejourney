# ==============================================================================
# File: apps/health/services/__init__.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Health services package initialization
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2025-12-31
# Last Updated: 2025-12-31
# ==============================================================================

from .dexcom import DexcomService, DexcomSyncService
from .fatsecret import FatSecretService, fatsecret_service
from .ai_nutrition import AINutritionService, ai_nutrition_service
from .food_search import FoodSearchService, food_search_service
from .cycle_detection import CycleDetectionService, process_daily_log_signal
from .cycle_export import CycleDataExportService
from .cycle_phase import get_current_phase, get_phase_by_day, get_all_phases
from .cycle_prediction import CyclePredictionService
from .cycle_statistics import CycleStatisticsService
from .health_data import HealthDataService
from .insight_engine import InsightEngine

# Health Intelligence Engine (v2)
from .daily_summary_builder import DailyHealthSummaryBuilder
from .baseline_policy import BaselinePolicy
from .recovery_score import RecoveryScoreService
from .health_score import HealthScoreService
from .trend_analyzer import HealthTrendAnalyzer
from .correlation_service import CorrelationService
from .score_pipeline import ScorePipeline
from .cos_health_context import build_cos_health_intelligence, build_cos_health_summary_text
from .command_center_api import HealthCommandCenterService
from .protein_service import ProteinService

__all__ = [
    'DexcomService',
    'DexcomSyncService',
    'FatSecretService',
    'fatsecret_service',
    'AINutritionService',
    'ai_nutrition_service',
    'FoodSearchService',
    'food_search_service',
    'CycleDetectionService',
    'process_daily_log_signal',
    'CycleDataExportService',
    'get_current_phase',
    'get_phase_by_day',
    'get_all_phases',
    'CyclePredictionService',
    'CycleStatisticsService',
    'HealthDataService',
    'InsightEngine',
    # Health Intelligence Engine
    'DailyHealthSummaryBuilder',
    'BaselinePolicy',
    'RecoveryScoreService',
    'HealthScoreService',
    'HealthTrendAnalyzer',
    'CorrelationService',
    'ScorePipeline',
    'build_cos_health_intelligence',
    'build_cos_health_summary_text',
    'HealthCommandCenterService',
    'ProteinService',
]
