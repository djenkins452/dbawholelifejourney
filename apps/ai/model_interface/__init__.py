# ==============================================================================
# File: apps/ai/model_interface/__init__.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The model-interface runtime (WLJ ↔ conversational-model interface)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-09
# ==============================================================================
"""
The model-interface runtime — Phase II of docs/WLJ_MODEL_INTERFACE_DESIGN.md.

WLJ exposes four pillars (Truth, Actions, AI Relationship, Current Context) to a
provider-agnostic conversational model, which owns all reasoning. This package is the
third, separate conversational runtime (behind `use_model_interface`); it does not
touch the legacy or ChatGPT-CoS paths.
"""
