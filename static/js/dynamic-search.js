/**
 * dynamic-search.js — Reusable debounced search for list pages.
 *
 * Usage: Add  data-dynamic-search  to any <form> that contains a search input.
 *
 * The script will:
 *   1. Find the text input (input[name="q"] or input[name="search"])
 *   2. Debounce keystroke input — auto-submit the form after 600 ms of
 *      inactivity when the query is ≥ 2 characters (or empty, to reset).
 *   3. On page load, restore focus + cursor position in the search field
 *      so the user can keep refining without re-clicking.
 *   4. Auto-submit the form when any element with  data-auto-submit  changes
 *      (dropdowns, checkboxes, etc.).
 *
 * CSP-safe: loaded as an external script with nonce.
 */
(function () {
    'use strict';

    var DEBOUNCE_MS = 600;
    var MIN_QUERY_LENGTH = 2;

    function initDynamicSearch(form) {
        // Find the search input — support name="q" or name="search"
        var searchInput = form.querySelector('input[name="q"], input[name="search"]');
        if (!searchInput) return;

        // --- Focus retention ---
        // If returning from a search, keep focus in the search box so the
        // user can keep typing (e.g. "ho" → "horse" without re-clicking).
        if (searchInput.value.length > 0) {
            searchInput.focus();
            var len = searchInput.value.length;
            searchInput.setSelectionRange(len, len);
        }

        // --- Debounced search ---
        var debounceTimer;
        searchInput.addEventListener('input', function () {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(function () {
                var val = searchInput.value.trim();
                if (val.length >= MIN_QUERY_LENGTH || val.length === 0) {
                    form.submit();
                }
            }, DEBOUNCE_MS);
        });

        // --- Filter auto-submit ---
        // Any element inside the form with data-auto-submit will trigger
        // an immediate form submit on change (dropdowns, checkboxes).
        form.querySelectorAll('[data-auto-submit]').forEach(function (el) {
            el.addEventListener('change', function () {
                form.submit();
            });
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('[data-dynamic-search]').forEach(initDynamicSearch);
    });
})();
