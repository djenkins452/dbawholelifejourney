"""
Whole Life Journey - Scan Application Package

Project: Whole Life Journey
Path: apps/scan/__init__.py
Purpose: AI Camera scanning using OpenAI Vision for item recognition

Description:
    The Scan module provides AI-powered camera capture that uses OpenAI's
    Vision API to identify items (food, medicine, documents, etc.) and
    suggest contextual actions within other WLJ modules.

Key Responsibilities:
    - Browser camera capture (getUserMedia API)
    - File upload fallback for camera capture
    - OpenAI Vision API integration for image analysis
    - Contextual action suggestions based on identified items
    - Image storage in session for attaching to created records
    - Rate limiting to prevent API abuse

Package Contents:
    - views.py: Scan capture and results views
    - services/vision.py: OpenAI Vision API integration
    - urls.py: URL routing (mounted at /scan/)
    - templates/: Scan UI templates

Supported Categories:
    - food: General food items for nutrition logging
    - medicine: Medicine bottles for medicine tracking
    - supplement: Vitamins/supplements
    - receipt: Receipts for expense tracking
    - document: Documents for storage
    - workout_equipment: Fitness equipment
    - inventory_item: General belongings
    - barcode: Barcodes for lookup

Security Notes:
    - Privacy-first design (no permanent image storage by default)
    - Rate limiting via django-axes
    - Magic bytes validation for file uploads
    - User consent required for AI processing

Dependencies:
    - openai: OpenAI Python SDK for Vision API
    - apps.ai for AI configuration
    - getUserMedia: Browser API for camera access

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

default_app_config = 'apps.scan.apps.ScanConfig'
