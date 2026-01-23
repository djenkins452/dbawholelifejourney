# ==============================================================================
# File: apps/security/__init__.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Security Assessment System - CISO-grade security scoring and reporting
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-22
# ==============================================================================
"""
Security Assessment System

Provides comprehensive security assessment capabilities:
- Automated security testing with 40+ checks
- CVSS v3.1 scoring for findings
- SecurityScorecard-style grading (A-F)
- BitSight-style numeric scoring (250-900)
- Risk scoring (0-100)
- AppSec maturity assessment (0-3)
- Trend tracking over time
- Interactive dashboard with drill-down

SECURITY NOTE (Tier-0):
This module contains sensitive security assessment data.
All data is encrypted at rest using field-level encryption.
Access requires SecurityAdmin or SecurityViewer role.
"""

default_app_config = 'apps.security.apps.SecurityConfig'
