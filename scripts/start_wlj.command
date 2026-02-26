#!/usr/bin/env bash
# ==============================================================================
# File: scripts/start_wlj.command
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Double-clickable macOS launcher for WLJ dev server + UI tests
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-26
#
# Usage: Double-click in Finder, or run from terminal: ./scripts/start_wlj.command
# ==============================================================================

# .command files open in Terminal.app when double-clicked on macOS.
# Delegate to the main script.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/start_wlj_test_env.sh"
