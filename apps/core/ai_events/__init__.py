# ==============================================================================
# File: apps/core/ai_events/__init__.py
# Project: Whole Life Journey — Django 5.x Personal Wellness/Journaling App
# Description: Event Access Layer — deterministic event-level truth for CoS
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-28
# ==============================================================================
"""
Event Access Layer — Cross-domain deterministic event access.

This package provides a standardized interface for querying event-level
execution truth from canonical domain models. It is read-only, creates
no new tables, and reads directly from source-of-truth models.

Architecture:
    Raw Data (MedicineLog, RoutineLog, etc.)
        → Domain Adapters (query + normalize)
        → EventResolver (orchestrate cross-domain)
        → Router handlers (format deterministic response)
        → User gets factual answer

Principles:
    - NO new models — reads existing tables only
    - NO data duplication — adapters are read-only projections
    - NO LLM inference — all answers are deterministic
    - NO ComplianceEvent dependency — reads raw domain models
    - Bounded queries — always date-ranged, never unbounded
"""
