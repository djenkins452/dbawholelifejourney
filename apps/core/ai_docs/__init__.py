"""
Whole Life Journey — Auto-Synchronizing Documentation System

Project: Whole Life Journey
Path: apps/core/ai_docs/
Purpose: Generate and synchronize living documentation from actual code

Description:
    Provides a documentation pipeline that introspects CoS blueprint
    models, engines, and configuration to produce human-readable
    admin guide content. Documentation never drifts from code because
    it is generated from code.

Public API:
    - sync_cos_admin_guide() — Generate and write guide to admin console
    - validate_cos_architecture() — Check code matches registry
    - generate_cos_admin_guide() — Return markdown string

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""
