# ==============================================================================
# File: apps/ai/tests/test_personal_context.py
# Project: Whole Life Journey
# Description: Tests for AI Personal Context extraction and management
# ==============================================================================
"""
Tests for the Personal Context feature.

This tests:
1. Opt-out phrase detection
2. Context merging
3. Context removal
4. Prompt building
"""

from django.test import TestCase
from apps.ai.personal_context import (
    contains_opt_out_phrase,
    merge_personal_context,
    remove_fact_from_context,
    build_personal_context_prompt,
)


class OptOutPhraseDetectionTests(TestCase):
    """Test detection of opt-out phrases."""

    def test_detects_dont_save_that(self):
        """Detects 'don't save that' phrase."""
        self.assertTrue(contains_opt_out_phrase("Actually, don't save that"))
        self.assertTrue(contains_opt_out_phrase("please dont save that"))

    def test_detects_forget_what_i_said(self):
        """Detects 'forget what I said' phrase."""
        self.assertTrue(contains_opt_out_phrase("forget what I said about that"))

    def test_detects_keep_this_private(self):
        """Detects 'keep this private' phrase."""
        self.assertTrue(contains_opt_out_phrase("keep this private please"))

    def test_detects_off_the_record(self):
        """Detects 'off the record' phrase."""
        self.assertTrue(contains_opt_out_phrase("This is off the record"))

    def test_no_false_positives(self):
        """Normal text doesn't trigger opt-out."""
        self.assertFalse(contains_opt_out_phrase("I want to save money"))
        self.assertFalse(contains_opt_out_phrase("Remember to call mom"))
        self.assertFalse(contains_opt_out_phrase("Let's keep going"))


class ContextMergingTests(TestCase):
    """Test merging new context with existing context."""

    def test_merges_new_facts(self):
        """New facts are added to existing context."""
        existing = "You work as a teacher"
        new = "You have two children"
        result = merge_personal_context(existing, new)
        self.assertIn("teacher", result)
        self.assertIn("two children", result)

    def test_avoids_duplicates(self):
        """Duplicate facts are not added twice."""
        existing = "You work as a teacher"
        new = "You work as a teacher"
        result = merge_personal_context(existing, new)
        self.assertEqual(result.lower().count("teacher"), 1)

    def test_handles_empty_existing(self):
        """New context works with empty existing."""
        result = merge_personal_context("", "You have a dog")
        self.assertEqual(result, "You have a dog")

    def test_handles_empty_new(self):
        """Empty new context returns existing."""
        result = merge_personal_context("You have a dog", "")
        self.assertEqual(result, "You have a dog")


class ContextRemovalTests(TestCase):
    """Test removing facts from context."""

    def test_removes_exact_match(self):
        """Exact match is removed."""
        context = "You work as a teacher\nYou have two children"
        result = remove_fact_from_context(context, "You work as a teacher")
        self.assertNotIn("teacher", result)
        self.assertIn("two children", result)

    def test_case_insensitive_removal(self):
        """Removal is case-insensitive."""
        context = "You work as a teacher"
        result = remove_fact_from_context(context, "YOU WORK AS A TEACHER")
        self.assertEqual(result, "")

    def test_handles_not_found(self):
        """Non-existent fact doesn't break anything."""
        context = "You have a dog"
        result = remove_fact_from_context(context, "You have a cat")
        self.assertIn("dog", result)


class PromptBuildingTests(TestCase):
    """Test building the context prompt for AI."""

    def test_builds_prompt_with_context(self):
        """Prompt includes context and instructions."""
        context = "Your parents divorced when you were young"
        result = build_personal_context_prompt(context)
        self.assertIn("WHAT YOU KNOW ABOUT THIS USER", result)
        self.assertIn("parents divorced", result)
        self.assertIn("background knowledge", result)

    def test_empty_context_returns_empty(self):
        """Empty context returns empty string."""
        result = build_personal_context_prompt("")
        self.assertEqual(result, "")

    def test_none_context_returns_empty(self):
        """None context returns empty string."""
        result = build_personal_context_prompt(None)
        self.assertEqual(result, "")
