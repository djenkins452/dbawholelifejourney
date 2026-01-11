/**
 * Accordion Component
 *
 * Provides collapsible accordion functionality with localStorage persistence
 * for the preferences page and other accordion-based interfaces.
 *
 * Usage:
 *   <div class="accordion" data-accordion-id="preferences">
 *       <div class="accordion-group" data-accordion-key="appearance">
 *           <button class="accordion-header">...</button>
 *           <div class="accordion-body">...</div>
 *       </div>
 *   </div>
 */

(function() {
    'use strict';

    const STORAGE_PREFIX = 'wlj_accordion_';

    /**
     * Get the storage key for an accordion
     */
    function getStorageKey(accordionId) {
        return STORAGE_PREFIX + accordionId;
    }

    /**
     * Load saved accordion state from localStorage
     */
    function loadAccordionState(accordionId) {
        try {
            const stored = localStorage.getItem(getStorageKey(accordionId));
            return stored ? JSON.parse(stored) : {};
        } catch (e) {
            console.warn('Failed to load accordion state:', e);
            return {};
        }
    }

    /**
     * Save accordion state to localStorage
     */
    function saveAccordionState(accordionId, state) {
        try {
            localStorage.setItem(getStorageKey(accordionId), JSON.stringify(state));
        } catch (e) {
            console.warn('Failed to save accordion state:', e);
        }
    }

    /**
     * Toggle an accordion group open/closed
     */
    function toggleAccordionGroup(group, accordionId) {
        const isOpen = group.classList.contains('is-open');
        const key = group.dataset.accordionKey;

        if (isOpen) {
            group.classList.remove('is-open');
        } else {
            group.classList.add('is-open');
        }

        // Save state if we have a key
        if (key && accordionId) {
            const state = loadAccordionState(accordionId);
            state[key] = !isOpen;
            saveAccordionState(accordionId, state);
        }
    }

    /**
     * Initialize a single accordion container
     */
    function initAccordion(accordion) {
        const accordionId = accordion.dataset.accordionId || 'default';
        const savedState = loadAccordionState(accordionId);
        const groups = accordion.querySelectorAll(':scope > .accordion-group');

        groups.forEach(function(group) {
            const header = group.querySelector(':scope > .accordion-header');
            const key = group.dataset.accordionKey;

            if (!header) return;

            // Restore saved state or use default
            if (key && savedState.hasOwnProperty(key)) {
                if (savedState[key]) {
                    group.classList.add('is-open');
                } else {
                    group.classList.remove('is-open');
                }
            }

            // Add click handler
            header.addEventListener('click', function(e) {
                // Don't toggle if clicking a link or button inside the header
                if (e.target.closest('a, button:not(.accordion-header)')) {
                    return;
                }
                e.preventDefault();
                toggleAccordionGroup(group, accordionId);
            });

            // Add keyboard support
            header.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    toggleAccordionGroup(group, accordionId);
                }
            });

            // Ensure header is focusable
            if (!header.hasAttribute('tabindex')) {
                header.setAttribute('tabindex', '0');
            }

            // Set ARIA attributes
            const bodyId = 'accordion-body-' + (key || Math.random().toString(36).substr(2, 9));
            const body = group.querySelector(':scope > .accordion-body');
            if (body) {
                body.id = bodyId;
                header.setAttribute('aria-controls', bodyId);
                header.setAttribute('aria-expanded', group.classList.contains('is-open'));
            }
        });

        // Update ARIA on state changes
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.attributeName === 'class') {
                    const group = mutation.target;
                    const header = group.querySelector(':scope > .accordion-header');
                    if (header) {
                        header.setAttribute('aria-expanded', group.classList.contains('is-open'));
                    }
                }
            });
        });

        groups.forEach(function(group) {
            observer.observe(group, { attributes: true, attributeFilter: ['class'] });
        });

        // Initialize nested accordions
        const nestedAccordions = accordion.querySelectorAll('.accordion-body .accordion');
        nestedAccordions.forEach(function(nested) {
            initAccordion(nested);
        });
    }

    /**
     * Initialize all accordions on the page
     */
    function initAllAccordions() {
        // Only init top-level accordions (nested ones are initialized by parent)
        const accordions = document.querySelectorAll('.accordion:not(.accordion-body .accordion)');
        accordions.forEach(initAccordion);
    }

    /**
     * Public API for programmatic control
     */
    window.WLJAccordion = {
        /**
         * Open a specific accordion group by key
         */
        open: function(accordionId, key) {
            const accordion = document.querySelector('[data-accordion-id="' + accordionId + '"]');
            if (!accordion) return;

            const group = accordion.querySelector('[data-accordion-key="' + key + '"]');
            if (group && !group.classList.contains('is-open')) {
                toggleAccordionGroup(group, accordionId);
            }
        },

        /**
         * Close a specific accordion group by key
         */
        close: function(accordionId, key) {
            const accordion = document.querySelector('[data-accordion-id="' + accordionId + '"]');
            if (!accordion) return;

            const group = accordion.querySelector('[data-accordion-key="' + key + '"]');
            if (group && group.classList.contains('is-open')) {
                toggleAccordionGroup(group, accordionId);
            }
        },

        /**
         * Toggle a specific accordion group by key
         */
        toggle: function(accordionId, key) {
            const accordion = document.querySelector('[data-accordion-id="' + accordionId + '"]');
            if (!accordion) return;

            const group = accordion.querySelector('[data-accordion-key="' + key + '"]');
            if (group) {
                toggleAccordionGroup(group, accordionId);
            }
        },

        /**
         * Expand all groups in an accordion
         */
        expandAll: function(accordionId) {
            const accordion = document.querySelector('[data-accordion-id="' + accordionId + '"]');
            if (!accordion) return;

            const groups = accordion.querySelectorAll('.accordion-group:not(.is-open)');
            const state = {};
            groups.forEach(function(group) {
                group.classList.add('is-open');
                const key = group.dataset.accordionKey;
                if (key) state[key] = true;
            });
            saveAccordionState(accordionId, state);
        },

        /**
         * Collapse all groups in an accordion
         */
        collapseAll: function(accordionId) {
            const accordion = document.querySelector('[data-accordion-id="' + accordionId + '"]');
            if (!accordion) return;

            const groups = accordion.querySelectorAll('.accordion-group.is-open');
            const state = {};
            groups.forEach(function(group) {
                group.classList.remove('is-open');
                const key = group.dataset.accordionKey;
                if (key) state[key] = false;
            });
            saveAccordionState(accordionId, state);
        },

        /**
         * Re-initialize accordions (useful after dynamic content updates)
         */
        refresh: function() {
            initAllAccordions();
        }
    };

    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAllAccordions);
    } else {
        initAllAccordions();
    }
})();
