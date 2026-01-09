/**
 * Undo Toast Notification System
 *
 * Project: Whole Life Journey
 * Path: static/js/undo-toast.js
 * Purpose: Show toast notifications with undo capability after delete actions
 *
 * Description:
 *     Provides a reusable toast notification system that appears after soft-delete
 *     operations. Users have 5 seconds to click Undo to restore the deleted item.
 *     If the timer expires, the item remains soft-deleted (no permanent deletion).
 *
 * Usage:
 *     // Show an undo toast after deleting an item
 *     window.undoToast.show({
 *         message: 'Weight entry deleted',
 *         itemType: 'health.weightentry',
 *         itemId: 123,
 *         onUndo: () => { /* optional callback after restore * / }
 *     });
 *
 *     // For delete forms, add data attributes:
 *     <form data-undo-delete
 *           data-item-type="health.weightentry"
 *           data-item-name="Weight entry">
 *
 * Copyright:
 *     (c) Whole Life Journey. All rights reserved.
 */

(function() {
    'use strict';

    // Configuration
    const TOAST_DURATION = 5000; // 5 seconds
    const RESTORE_URL = '/api/restore/';

    // State
    let currentToast = null;
    let countdownInterval = null;

    /**
     * Get CSRF token from cookie
     */
    function getCSRFToken() {
        const name = 'csrftoken';
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    /**
     * Create the toast element
     */
    function createToastElement() {
        const toast = document.createElement('div');
        toast.className = 'undo-toast';
        toast.setAttribute('role', 'alert');
        toast.setAttribute('aria-live', 'polite');
        toast.innerHTML = `
            <div class="undo-toast-content">
                <span class="undo-toast-message"></span>
                <button type="button" class="undo-toast-btn" aria-label="Undo delete">
                    Undo <span class="undo-toast-countdown"></span>
                </button>
            </div>
            <div class="undo-toast-progress">
                <div class="undo-toast-progress-bar"></div>
            </div>
        `;
        return toast;
    }

    /**
     * Show the undo toast
     * @param {Object} options - Configuration options
     * @param {string} options.message - Message to display
     * @param {string} options.itemType - Model type (e.g., 'health.weightentry')
     * @param {number|string} options.itemId - ID of the deleted item
     * @param {Function} options.onUndo - Callback after successful restore
     * @param {Function} options.onExpire - Callback when timer expires without undo
     */
    function showToast(options) {
        // Remove any existing toast
        hideToast();

        const { message, itemType, itemId, onUndo, onExpire } = options;

        // Create toast
        currentToast = createToastElement();
        currentToast.querySelector('.undo-toast-message').textContent = message;

        const countdownEl = currentToast.querySelector('.undo-toast-countdown');
        const progressBar = currentToast.querySelector('.undo-toast-progress-bar');
        const undoBtn = currentToast.querySelector('.undo-toast-btn');

        // Set up countdown
        let secondsRemaining = Math.ceil(TOAST_DURATION / 1000);
        countdownEl.textContent = `(${secondsRemaining}s)`;

        // Animate progress bar
        progressBar.style.transition = `width ${TOAST_DURATION}ms linear`;

        // Add to DOM
        document.body.appendChild(currentToast);

        // Force reflow to enable animation
        currentToast.offsetHeight;

        // Show toast with animation
        currentToast.classList.add('undo-toast-visible');

        // Start progress bar animation
        requestAnimationFrame(() => {
            progressBar.style.width = '0%';
        });

        // Update countdown every second
        countdownInterval = setInterval(() => {
            secondsRemaining--;
            if (secondsRemaining > 0) {
                countdownEl.textContent = `(${secondsRemaining}s)`;
            } else {
                countdownEl.textContent = '';
            }
        }, 1000);

        // Handle undo click
        undoBtn.addEventListener('click', async () => {
            undoBtn.disabled = true;
            undoBtn.innerHTML = '<span class="undo-toast-spinner"></span> Restoring...';

            try {
                const success = await restoreItem(itemType, itemId);
                if (success) {
                    hideToast();
                    showSuccessMessage('Item restored');
                    if (onUndo) onUndo();
                } else {
                    undoBtn.innerHTML = 'Undo <span class="undo-toast-countdown"></span>';
                    undoBtn.disabled = false;
                    showErrorMessage('Failed to restore item');
                }
            } catch (error) {
                console.error('Restore failed:', error);
                undoBtn.innerHTML = 'Undo <span class="undo-toast-countdown"></span>';
                undoBtn.disabled = false;
                showErrorMessage('Failed to restore item');
            }
        });

        // Auto-hide after duration
        setTimeout(() => {
            if (currentToast) {
                hideToast();
                if (onExpire) onExpire();
            }
        }, TOAST_DURATION);
    }

    /**
     * Hide the current toast
     */
    function hideToast() {
        if (countdownInterval) {
            clearInterval(countdownInterval);
            countdownInterval = null;
        }

        if (currentToast) {
            currentToast.classList.remove('undo-toast-visible');
            currentToast.classList.add('undo-toast-hiding');

            setTimeout(() => {
                if (currentToast && currentToast.parentNode) {
                    currentToast.parentNode.removeChild(currentToast);
                }
                currentToast = null;
            }, 300);
        }
    }

    /**
     * Restore a soft-deleted item via API
     */
    async function restoreItem(itemType, itemId) {
        const response = await fetch(RESTORE_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken(),
            },
            body: JSON.stringify({
                item_type: itemType,
                item_id: itemId,
            }),
        });

        const data = await response.json();
        return data.success;
    }

    /**
     * Show a brief success message
     */
    function showSuccessMessage(message) {
        const msg = document.createElement('div');
        msg.className = 'undo-toast-feedback undo-toast-feedback-success';
        msg.textContent = message;
        document.body.appendChild(msg);

        requestAnimationFrame(() => {
            msg.classList.add('undo-toast-feedback-visible');
        });

        setTimeout(() => {
            msg.classList.remove('undo-toast-feedback-visible');
            setTimeout(() => msg.remove(), 300);
        }, 2000);
    }

    /**
     * Show a brief error message
     */
    function showErrorMessage(message) {
        const msg = document.createElement('div');
        msg.className = 'undo-toast-feedback undo-toast-feedback-error';
        msg.textContent = message;
        document.body.appendChild(msg);

        requestAnimationFrame(() => {
            msg.classList.add('undo-toast-feedback-visible');
        });

        setTimeout(() => {
            msg.classList.remove('undo-toast-feedback-visible');
            setTimeout(() => msg.remove(), 300);
        }, 3000);
    }

    /**
     * Initialize delete form handlers
     * Forms with data-undo-delete will show undo toast instead of redirecting
     */
    function initDeleteForms() {
        document.addEventListener('submit', async (e) => {
            const form = e.target;
            if (!form.hasAttribute('data-undo-delete')) return;

            e.preventDefault();

            const itemType = form.dataset.itemType;
            const itemName = form.dataset.itemName || 'Item';
            const itemId = form.dataset.itemId;
            const redirectUrl = form.dataset.redirectUrl || form.action.replace('/delete/', '/');
            const rowSelector = form.dataset.rowSelector;

            // Disable form to prevent double-submit
            const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
            if (submitBtn) submitBtn.disabled = true;

            try {
                // Submit delete request
                const response = await fetch(form.action, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCSRFToken(),
                        'X-Requested-With': 'XMLHttpRequest',
                    },
                    body: new FormData(form),
                });

                const data = await response.json();

                if (data.success) {
                    // Hide the deleted item from UI
                    if (rowSelector) {
                        const row = document.querySelector(rowSelector);
                        if (row) {
                            row.style.transition = 'opacity 0.3s, transform 0.3s';
                            row.style.opacity = '0';
                            row.style.transform = 'translateX(-20px)';
                            setTimeout(() => {
                                row.style.display = 'none';
                            }, 300);
                        }
                    }

                    // Show undo toast
                    showToast({
                        message: `${itemName} deleted`,
                        itemType: data.item_type || itemType,
                        itemId: data.item_id || itemId,
                        onUndo: () => {
                            // Restore the row visibility
                            if (rowSelector) {
                                const row = document.querySelector(rowSelector);
                                if (row) {
                                    row.style.display = '';
                                    row.style.opacity = '1';
                                    row.style.transform = '';
                                }
                            }
                        },
                        onExpire: () => {
                            // Optionally redirect after expiration
                            if (data.redirect_url) {
                                window.location.href = data.redirect_url;
                            }
                        }
                    });
                } else {
                    showErrorMessage(data.error || 'Delete failed');
                    if (submitBtn) submitBtn.disabled = false;
                }
            } catch (error) {
                console.error('Delete request failed:', error);
                showErrorMessage('Delete failed. Please try again.');
                if (submitBtn) submitBtn.disabled = false;
            }
        });
    }

    // Inject styles
    const styles = document.createElement('style');
    styles.textContent = `
        /* Undo Toast Container */
        .undo-toast {
            position: fixed;
            bottom: var(--space-6, 1.5rem);
            left: 50%;
            transform: translateX(-50%) translateY(100px);
            background: var(--color-surface, #1f2937);
            color: var(--color-text-inverse, #fff);
            border-radius: var(--radius-lg, 12px);
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
            z-index: 10000;
            opacity: 0;
            transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1),
                        opacity 0.3s ease;
            min-width: 280px;
            max-width: 400px;
            overflow: hidden;
        }

        .undo-toast-visible {
            transform: translateX(-50%) translateY(0);
            opacity: 1;
        }

        .undo-toast-hiding {
            transform: translateX(-50%) translateY(20px);
            opacity: 0;
        }

        .undo-toast-content {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: var(--space-4, 1rem);
            padding: var(--space-4, 1rem) var(--space-5, 1.25rem);
        }

        .undo-toast-message {
            font-size: var(--font-size-sm, 0.875rem);
            font-weight: 500;
        }

        .undo-toast-btn {
            background: rgba(255, 255, 255, 0.15);
            border: none;
            color: inherit;
            padding: var(--space-2, 0.5rem) var(--space-4, 1rem);
            border-radius: var(--radius-md, 8px);
            font-size: var(--font-size-sm, 0.875rem);
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
            white-space: nowrap;
            display: flex;
            align-items: center;
            gap: var(--space-1, 0.25rem);
        }

        .undo-toast-btn:hover:not(:disabled) {
            background: rgba(255, 255, 255, 0.25);
        }

        .undo-toast-btn:disabled {
            cursor: not-allowed;
            opacity: 0.7;
        }

        .undo-toast-countdown {
            font-weight: normal;
            opacity: 0.8;
        }

        /* Progress bar */
        .undo-toast-progress {
            height: 3px;
            background: rgba(255, 255, 255, 0.1);
        }

        .undo-toast-progress-bar {
            height: 100%;
            width: 100%;
            background: var(--color-accent, #4f46e5);
        }

        /* Loading spinner */
        .undo-toast-spinner {
            width: 14px;
            height: 14px;
            border: 2px solid rgba(255, 255, 255, 0.3);
            border-top-color: #fff;
            border-radius: 50%;
            animation: undo-toast-spin 0.6s linear infinite;
        }

        @keyframes undo-toast-spin {
            to { transform: rotate(360deg); }
        }

        /* Feedback messages */
        .undo-toast-feedback {
            position: fixed;
            bottom: var(--space-6, 1.5rem);
            left: 50%;
            transform: translateX(-50%) translateY(20px);
            padding: var(--space-3, 0.75rem) var(--space-5, 1.25rem);
            border-radius: var(--radius-lg, 12px);
            font-size: var(--font-size-sm, 0.875rem);
            font-weight: 500;
            z-index: 10001;
            opacity: 0;
            transition: transform 0.3s ease, opacity 0.3s ease;
        }

        .undo-toast-feedback-visible {
            transform: translateX(-50%) translateY(0);
            opacity: 1;
        }

        .undo-toast-feedback-success {
            background: var(--color-success, #10b981);
            color: white;
        }

        .undo-toast-feedback-error {
            background: var(--color-error, #ef4444);
            color: white;
        }

        /* Dark theme adjustments */
        [data-theme="dark"] .undo-toast,
        .theme-dark .undo-toast {
            background: var(--color-surface, #374151);
        }

        /* Mobile responsiveness */
        @media (max-width: 480px) {
            .undo-toast {
                left: var(--space-4, 1rem);
                right: var(--space-4, 1rem);
                transform: translateX(0) translateY(100px);
                min-width: auto;
                max-width: none;
            }

            .undo-toast-visible {
                transform: translateX(0) translateY(0);
            }

            .undo-toast-hiding {
                transform: translateX(0) translateY(20px);
            }

            .undo-toast-feedback {
                left: var(--space-4, 1rem);
                right: var(--space-4, 1rem);
                transform: translateX(0) translateY(20px);
            }

            .undo-toast-feedback-visible {
                transform: translateX(0) translateY(0);
            }
        }
    `;
    document.head.appendChild(styles);

    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initDeleteForms);
    } else {
        initDeleteForms();
    }

    // Expose API
    window.undoToast = {
        show: showToast,
        hide: hideToast,
    };
})();
