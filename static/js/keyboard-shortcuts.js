/**
 * Keyboard Shortcuts for Whole Life Journey
 *
 * Provides global keyboard shortcuts for navigation and common actions.
 * Supports both Mac (Cmd) and Windows/Linux (Ctrl) modifiers.
 *
 * Shortcuts:
 * - Cmd/Ctrl + N: New entry/item (context-aware)
 * - Cmd/Ctrl + S: Save (when in form)
 * - Cmd/Ctrl + /: Focus search
 * - Cmd/Ctrl + J: Go to Journal
 * - Cmd/Ctrl + H: Go to Health (uses Shift to avoid browser history)
 * - Cmd/Ctrl + Shift + H: Go to Health
 * - ?: Show keyboard shortcuts help
 */

(function() {
    'use strict';

    // Configuration for keyboard shortcuts
    const SHORTCUTS = {
        // Navigation shortcuts
        'j': {
            description: 'Go to Journal',
            action: () => navigateTo('/journal/'),
            modifiers: ['meta', 'ctrl']
        },
        'g': {
            description: 'Go to Goals',
            action: () => navigateTo('/purpose/'),
            modifiers: ['meta', 'ctrl']
        },
        'o': {
            description: 'Go to Organize',
            action: () => navigateTo('/life/'),
            modifiers: ['meta', 'ctrl']
        },
        'd': {
            description: 'Go to Dashboard',
            action: () => navigateTo('/dashboard/'),
            modifiers: ['meta', 'ctrl']
        },

        // Action shortcuts
        'n': {
            description: 'New entry/item',
            action: triggerNewAction,
            modifiers: ['meta', 'ctrl']
        },
        '/': {
            description: 'Focus search',
            action: focusSearch,
            modifiers: ['meta', 'ctrl']
        },

        // Help shortcut (no modifier)
        '?': {
            description: 'Show keyboard shortcuts',
            action: showShortcutsModal,
            modifiers: []
        }
    };

    // Track if modal is open
    let modalOpen = false;

    /**
     * Navigate to a URL
     */
    function navigateTo(url) {
        window.location.href = url;
    }

    /**
     * Trigger the "New" action for the current page context
     */
    function triggerNewAction() {
        // Look for a "New" button on the page
        const newButtons = document.querySelectorAll(
            'a[href*="create"], a[href*="new"], button[data-new-action], .btn-primary:contains("New")'
        );

        // Find button with "New" text
        const newButton = Array.from(document.querySelectorAll('a.btn-primary, button.btn-primary'))
            .find(btn => btn.textContent.toLowerCase().includes('new'));

        if (newButton) {
            newButton.click();
            return;
        }

        // Fallback: look for any create link
        const createLink = document.querySelector('a[href*="create"]');
        if (createLink) {
            createLink.click();
        }
    }

    /**
     * Focus the search input
     */
    function focusSearch() {
        // Try global search first
        const searchInput = document.querySelector(
            '#global-search, input[name="q"], input[type="search"], .search-input'
        );

        if (searchInput) {
            searchInput.focus();
            searchInput.select();
        }
    }

    /**
     * Show the keyboard shortcuts modal
     */
    function showShortcutsModal() {
        if (modalOpen) {
            hideShortcutsModal();
            return;
        }

        // Create modal if it doesn't exist
        let modal = document.getElementById('keyboard-shortcuts-modal');
        if (!modal) {
            modal = createShortcutsModal();
            document.body.appendChild(modal);
        }

        modal.hidden = false;
        modalOpen = true;

        // Close on Escape
        document.addEventListener('keydown', handleEscape);
    }

    /**
     * Hide the shortcuts modal
     */
    function hideShortcutsModal() {
        const modal = document.getElementById('keyboard-shortcuts-modal');
        if (modal) {
            modal.hidden = true;
        }
        modalOpen = false;
        document.removeEventListener('keydown', handleEscape);
    }

    /**
     * Handle Escape key to close modal
     */
    function handleEscape(e) {
        if (e.key === 'Escape') {
            hideShortcutsModal();
        }
    }

    /**
     * Create the shortcuts modal element
     */
    function createShortcutsModal() {
        const modal = document.createElement('div');
        modal.id = 'keyboard-shortcuts-modal';
        modal.className = 'shortcuts-modal';
        modal.hidden = true;

        const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
        const modKey = isMac ? '⌘' : 'Ctrl';

        modal.innerHTML = `
            <div class="shortcuts-modal-backdrop" onclick="window.hideShortcutsModal && window.hideShortcutsModal()"></div>
            <div class="shortcuts-modal-content">
                <div class="shortcuts-modal-header">
                    <h2>Keyboard Shortcuts</h2>
                    <button type="button" class="shortcuts-modal-close" onclick="window.hideShortcutsModal && window.hideShortcutsModal()" aria-label="Close">
                        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                            <line x1="18" y1="6" x2="6" y2="18"/>
                            <line x1="6" y1="6" x2="18" y2="18"/>
                        </svg>
                    </button>
                </div>
                <div class="shortcuts-modal-body">
                    <div class="shortcuts-section">
                        <h3>Navigation</h3>
                        <div class="shortcut-row">
                            <span class="shortcut-keys"><kbd>${modKey}</kbd> + <kbd>D</kbd></span>
                            <span class="shortcut-desc">Go to Dashboard</span>
                        </div>
                        <div class="shortcut-row">
                            <span class="shortcut-keys"><kbd>${modKey}</kbd> + <kbd>J</kbd></span>
                            <span class="shortcut-desc">Go to Journal</span>
                        </div>
                        <div class="shortcut-row">
                            <span class="shortcut-keys"><kbd>${modKey}</kbd> + <kbd>G</kbd></span>
                            <span class="shortcut-desc">Go to Goals</span>
                        </div>
                        <div class="shortcut-row">
                            <span class="shortcut-keys"><kbd>${modKey}</kbd> + <kbd>O</kbd></span>
                            <span class="shortcut-desc">Go to Organize</span>
                        </div>
                    </div>
                    <div class="shortcuts-section">
                        <h3>Actions</h3>
                        <div class="shortcut-row">
                            <span class="shortcut-keys"><kbd>${modKey}</kbd> + <kbd>N</kbd></span>
                            <span class="shortcut-desc">New entry/item</span>
                        </div>
                        <div class="shortcut-row">
                            <span class="shortcut-keys"><kbd>${modKey}</kbd> + <kbd>/</kbd></span>
                            <span class="shortcut-desc">Focus search</span>
                        </div>
                        <div class="shortcut-row">
                            <span class="shortcut-keys"><kbd>?</kbd></span>
                            <span class="shortcut-desc">Show this help</span>
                        </div>
                    </div>
                </div>
            </div>
        `;

        return modal;
    }

    /**
     * Main keyboard event handler
     */
    function handleKeyboard(e) {
        // Don't trigger shortcuts when typing in inputs
        const activeElement = document.activeElement;
        const isTyping = activeElement && (
            activeElement.tagName === 'INPUT' ||
            activeElement.tagName === 'TEXTAREA' ||
            activeElement.isContentEditable
        );

        // Allow ? shortcut even when not in an input (except for shift+/)
        if (isTyping && e.key !== '?') {
            return;
        }

        // Get the pressed key
        const key = e.key.toLowerCase();

        // Check for ? shortcut (shift + /)
        if (e.key === '?' && !e.metaKey && !e.ctrlKey) {
            e.preventDefault();
            showShortcutsModal();
            return;
        }

        // Check registered shortcuts
        const shortcut = SHORTCUTS[key];
        if (!shortcut) return;

        // Check if correct modifier is pressed
        const hasModifier = e.metaKey || e.ctrlKey;
        const needsModifier = shortcut.modifiers.length > 0;

        if (needsModifier && !hasModifier) return;
        if (!needsModifier && hasModifier) return;

        // Prevent default browser behavior
        e.preventDefault();

        // Execute the action
        if (typeof shortcut.action === 'function') {
            shortcut.action();
        }
    }

    /**
     * Initialize keyboard shortcuts
     */
    function init() {
        document.addEventListener('keydown', handleKeyboard);

        // Expose hide function globally for modal backdrop click
        window.hideShortcutsModal = hideShortcutsModal;
    }

    // Add styles for the modal
    const styles = document.createElement('style');
    styles.textContent = `
        .shortcuts-modal {
            position: fixed;
            inset: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 1000;
        }

        .shortcuts-modal[hidden] {
            display: none;
        }

        .shortcuts-modal-backdrop {
            position: absolute;
            inset: 0;
            background: rgba(0, 0, 0, 0.5);
        }

        .shortcuts-modal-content {
            position: relative;
            background: var(--color-background, #fff);
            border-radius: var(--radius-lg, 12px);
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
            max-width: 500px;
            width: 90%;
            max-height: 80vh;
            overflow: auto;
        }

        .shortcuts-modal-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: var(--space-4, 1rem) var(--space-5, 1.25rem);
            border-bottom: 1px solid var(--color-border, #e5e5e5);
        }

        .shortcuts-modal-header h2 {
            margin: 0;
            font-size: var(--font-size-lg, 1.125rem);
        }

        .shortcuts-modal-close {
            background: none;
            border: none;
            padding: var(--space-2, 0.5rem);
            cursor: pointer;
            color: var(--color-text-muted, #666);
            border-radius: var(--radius-md, 8px);
        }

        .shortcuts-modal-close:hover {
            background: var(--color-surface, #f5f5f5);
            color: var(--color-text, #333);
        }

        .shortcuts-modal-body {
            padding: var(--space-5, 1.25rem);
        }

        .shortcuts-section {
            margin-bottom: var(--space-6, 1.5rem);
        }

        .shortcuts-section:last-child {
            margin-bottom: 0;
        }

        .shortcuts-section h3 {
            font-size: var(--font-size-sm, 0.875rem);
            font-weight: 600;
            color: var(--color-text-muted, #666);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin: 0 0 var(--space-3, 0.75rem) 0;
        }

        .shortcut-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: var(--space-2, 0.5rem) 0;
        }

        .shortcut-keys {
            display: flex;
            align-items: center;
            gap: var(--space-1, 0.25rem);
        }

        .shortcut-keys kbd {
            display: inline-block;
            padding: var(--space-1, 0.25rem) var(--space-2, 0.5rem);
            font-family: var(--font-mono, monospace);
            font-size: var(--font-size-xs, 0.75rem);
            background: var(--color-surface, #f5f5f5);
            border: 1px solid var(--color-border, #e5e5e5);
            border-radius: var(--radius-sm, 4px);
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
        }

        .shortcut-desc {
            color: var(--color-text, #333);
            font-size: var(--font-size-sm, 0.875rem);
        }
    `;
    document.head.appendChild(styles);

    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
