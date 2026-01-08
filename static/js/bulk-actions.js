/**
 * Bulk Actions for List Views
 *
 * Provides functionality for selecting multiple items in list views
 * and performing bulk actions (delete, archive, etc.)
 *
 * Usage:
 * 1. Add data-bulk-container around your list
 * 2. Add checkbox inputs with data-item-checkbox and value="<id>"
 * 3. Add a "select all" checkbox with data-select-all
 * 4. Configure actions via data-bulk-delete-url and data-bulk-archive-url
 * 5. Add data-bulk-item and data-item-id="<id>" on rows for visual feedback
 */

(function() {
    'use strict';

    // State
    const selectedItems = new Set();
    let container = null;
    let toolbar = null;

    /**
     * Initialize bulk actions for a container
     */
    function initBulkActions() {
        container = document.querySelector('[data-bulk-container]');
        if (!container) return;

        // Create and inject toolbar
        createToolbar();

        // Set up event listeners
        setupCheckboxListeners();
        setupSelectAllListener();
        setupActionListeners();
    }

    /**
     * Create the bulk actions toolbar
     */
    function createToolbar() {
        toolbar = document.createElement('div');
        toolbar.className = 'bulk-actions-toolbar';
        toolbar.hidden = true;
        toolbar.innerHTML = `
            <div class="bulk-actions-info">
                <span class="bulk-count">0</span> selected
            </div>
            <div class="bulk-actions-buttons">
                ${container.dataset.bulkArchiveUrl ? `
                <button type="button" class="btn btn-secondary btn-sm" data-bulk-action="archive">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 8v13H3V8M1 3h22v5H1zM10 12h4"/>
                    </svg>
                    Archive
                </button>
                ` : ''}
                <button type="button" class="btn btn-danger btn-sm" data-bulk-action="delete">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                    </svg>
                    Delete
                </button>
                <button type="button" class="btn btn-ghost btn-sm" data-bulk-action="clear">
                    Clear Selection
                </button>
            </div>
        `;

        // Insert toolbar after the page header
        const header = container.querySelector('.page-header');
        if (header) {
            header.after(toolbar);
        } else {
            container.prepend(toolbar);
        }
    }

    /**
     * Set up listeners for individual item checkboxes
     */
    function setupCheckboxListeners() {
        container.addEventListener('change', (e) => {
            if (e.target.matches('[data-item-checkbox]')) {
                const itemId = e.target.value;
                if (e.target.checked) {
                    selectedItems.add(itemId);
                    // Add visual selection to parent row
                    const row = e.target.closest('[data-bulk-item]');
                    if (row) row.classList.add('selected');
                } else {
                    selectedItems.delete(itemId);
                    const row = e.target.closest('[data-bulk-item]');
                    if (row) row.classList.remove('selected');
                }
                updateUI();
            }
        });
    }

    /**
     * Set up listener for "select all" checkbox
     */
    function setupSelectAllListener() {
        const selectAll = container.querySelector('[data-select-all]');
        if (!selectAll) return;

        selectAll.addEventListener('change', (e) => {
            const checkboxes = container.querySelectorAll('[data-item-checkbox]');
            checkboxes.forEach(checkbox => {
                checkbox.checked = e.target.checked;
                const itemId = checkbox.value;
                const row = checkbox.closest('[data-bulk-item]');
                if (e.target.checked) {
                    selectedItems.add(itemId);
                    if (row) row.classList.add('selected');
                } else {
                    selectedItems.delete(itemId);
                    if (row) row.classList.remove('selected');
                }
            });
            updateUI();
        });
    }

    /**
     * Set up listeners for action buttons
     */
    function setupActionListeners() {
        toolbar.addEventListener('click', (e) => {
            const button = e.target.closest('[data-bulk-action]');
            if (!button) return;

            const action = button.dataset.bulkAction;
            switch (action) {
                case 'delete':
                    confirmAndExecute('delete');
                    break;
                case 'archive':
                    confirmAndExecute('archive');
                    break;
                case 'clear':
                    clearSelection();
                    break;
            }
        });
    }

    /**
     * Update the UI based on selection state
     */
    function updateUI() {
        const count = selectedItems.size;

        // Update toolbar visibility
        toolbar.hidden = count === 0;

        // Update count display
        const countEl = toolbar.querySelector('.bulk-count');
        if (countEl) {
            countEl.textContent = count;
        }

        // Update select all checkbox
        const selectAll = container.querySelector('[data-select-all]');
        const allCheckboxes = container.querySelectorAll('[data-item-checkbox]');
        if (selectAll && allCheckboxes.length > 0) {
            const allChecked = Array.from(allCheckboxes).every(cb => cb.checked);
            const someChecked = Array.from(allCheckboxes).some(cb => cb.checked);
            selectAll.checked = allChecked;
            selectAll.indeterminate = someChecked && !allChecked;
        }
    }

    /**
     * Clear all selections
     */
    function clearSelection() {
        selectedItems.clear();
        container.querySelectorAll('[data-item-checkbox]').forEach(cb => {
            cb.checked = false;
            const row = cb.closest('[data-bulk-item]');
            if (row) row.classList.remove('selected');
        });
        const selectAll = container.querySelector('[data-select-all]');
        if (selectAll) {
            selectAll.checked = false;
            selectAll.indeterminate = false;
        }
        updateUI();
    }

    /**
     * Show confirmation modal and execute action
     */
    function confirmAndExecute(action) {
        const count = selectedItems.size;
        if (count === 0) return;

        const actionLabel = action === 'delete' ? 'delete' : 'archive';
        const message = `Are you sure you want to ${actionLabel} ${count} item${count > 1 ? 's' : ''}?`;

        // Create confirmation modal
        showConfirmModal(message, action, () => {
            executeAction(action);
        });
    }

    /**
     * Show confirmation modal
     */
    function showConfirmModal(message, action, onConfirm) {
        // Remove any existing modal
        const existing = document.getElementById('bulk-confirm-modal');
        if (existing) existing.remove();

        const isDelete = action === 'delete';
        const buttonClass = isDelete ? 'btn-danger' : 'btn-primary';
        const buttonText = isDelete ? 'Delete' : 'Archive';

        const modal = document.createElement('div');
        modal.id = 'bulk-confirm-modal';
        modal.className = 'bulk-modal';
        modal.innerHTML = `
            <div class="bulk-modal-backdrop"></div>
            <div class="bulk-modal-content">
                <div class="bulk-modal-header">
                    <h3>Confirm ${buttonText}</h3>
                </div>
                <div class="bulk-modal-body">
                    <p>${message}</p>
                    ${isDelete ? '<p class="text-error text-sm">This action cannot be undone.</p>' : ''}
                </div>
                <div class="bulk-modal-footer">
                    <button type="button" class="btn btn-ghost" data-modal-cancel>Cancel</button>
                    <button type="button" class="btn ${buttonClass}" data-modal-confirm>${buttonText}</button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        // Event listeners
        modal.querySelector('[data-modal-cancel]').addEventListener('click', () => modal.remove());
        modal.querySelector('.bulk-modal-backdrop').addEventListener('click', () => modal.remove());
        modal.querySelector('[data-modal-confirm]').addEventListener('click', () => {
            modal.remove();
            onConfirm();
        });

        // Escape to close
        const escHandler = (e) => {
            if (e.key === 'Escape') {
                modal.remove();
                document.removeEventListener('keydown', escHandler);
            }
        };
        document.addEventListener('keydown', escHandler);
    }

    /**
     * Execute the bulk action via API
     */
    async function executeAction(action) {
        const ids = Array.from(selectedItems);
        const url = action === 'delete'
            ? container.dataset.bulkDeleteUrl
            : container.dataset.bulkArchiveUrl;

        if (!url) {
            console.error('No URL configured for action:', action);
            return;
        }

        // Show loading state
        const buttons = toolbar.querySelectorAll('.bulk-actions-buttons button');
        buttons.forEach(btn => btn.disabled = true);

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken(),
                },
                body: JSON.stringify({ ids: ids })
            });

            const data = await response.json();

            if (data.success) {
                // Show success message
                showToast(data.message || `${data.count || ids.length} item${ids.length > 1 ? 's' : ''} ${action}d successfully`);

                // Remove deleted/archived items from DOM
                ids.forEach(id => {
                    const row = container.querySelector(`[data-item-id="${id}"]`);
                    if (row) {
                        row.style.transition = 'opacity 0.3s, transform 0.3s';
                        row.style.opacity = '0';
                        row.style.transform = 'translateX(-20px)';
                        setTimeout(() => row.remove(), 300);
                    }
                });

                // Clear selection
                clearSelection();

                // Update page counts if displayed
                updatePageCounts(ids.length, action);
            } else {
                showToast(data.error || 'An error occurred', 'error');
            }
        } catch (error) {
            console.error('Bulk action failed:', error);
            showToast('An error occurred. Please try again.', 'error');
        } finally {
            buttons.forEach(btn => btn.disabled = false);
        }
    }

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
     * Show a toast notification
     */
    function showToast(message, type = 'success') {
        // Use existing Django messages framework if available
        const messagesContainer = document.querySelector('.messages');
        if (messagesContainer) {
            const alert = document.createElement('div');
            alert.className = `alert alert-${type}`;
            alert.textContent = message;
            messagesContainer.appendChild(alert);
            setTimeout(() => alert.remove(), 5000);
            return;
        }

        // Fallback: create simple toast
        const toast = document.createElement('div');
        toast.className = `bulk-toast bulk-toast-${type}`;
        toast.textContent = message;
        document.body.appendChild(toast);

        setTimeout(() => {
            toast.classList.add('bulk-toast-hide');
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    /**
     * Update page counts after bulk action
     */
    function updatePageCounts(count, action) {
        // Try to update common count displays
        const subtitle = container.querySelector('.page-subtitle');
        if (subtitle) {
            const match = subtitle.textContent.match(/(\d+)/);
            if (match) {
                const oldCount = parseInt(match[1], 10);
                const newCount = Math.max(0, oldCount - count);
                subtitle.textContent = subtitle.textContent.replace(/\d+/, newCount);
            }
        }
    }

    // Add styles
    const styles = document.createElement('style');
    styles.textContent = `
        .bulk-actions-toolbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: var(--space-3, 0.75rem) var(--space-4, 1rem);
            background: var(--color-accent, #4f46e5);
            color: white;
            border-radius: var(--radius-lg, 12px);
            margin-bottom: var(--space-4, 1rem);
            animation: slideDown 0.2s ease-out;
        }

        .bulk-actions-toolbar[hidden] {
            display: none;
        }

        @keyframes slideDown {
            from {
                opacity: 0;
                transform: translateY(-10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .bulk-actions-info {
            font-size: var(--font-size-sm, 0.875rem);
            font-weight: 500;
        }

        .bulk-count {
            font-weight: 700;
        }

        .bulk-actions-buttons {
            display: flex;
            gap: var(--space-2, 0.5rem);
        }

        .bulk-actions-toolbar .btn {
            color: white;
            border-color: rgba(255, 255, 255, 0.3);
        }

        .bulk-actions-toolbar .btn:hover {
            background: rgba(255, 255, 255, 0.1);
        }

        .bulk-actions-toolbar .btn-danger {
            background: var(--color-error, #ef4444);
            border-color: var(--color-error, #ef4444);
        }

        .bulk-actions-toolbar .btn-danger:hover {
            background: #dc2626;
        }

        /* Checkbox styling */
        .bulk-checkbox {
            width: 18px;
            height: 18px;
            cursor: pointer;
            accent-color: var(--color-accent, #4f46e5);
        }

        .bulk-checkbox-cell {
            width: 40px;
            text-align: center;
        }

        /* Selected row highlight */
        .bulk-selected {
            background: rgba(79, 70, 229, 0.05) !important;
        }

        /* Modal styles */
        .bulk-modal {
            position: fixed;
            inset: 0;
            z-index: 9999;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .bulk-modal-backdrop {
            position: absolute;
            inset: 0;
            background: rgba(0, 0, 0, 0.5);
        }

        .bulk-modal-content {
            position: relative;
            background: var(--color-background, #fff);
            border-radius: var(--radius-lg, 12px);
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
            max-width: 400px;
            width: 90%;
        }

        .bulk-modal-header {
            padding: var(--space-4, 1rem) var(--space-5, 1.25rem);
            border-bottom: 1px solid var(--color-border, #e5e5e5);
        }

        .bulk-modal-header h3 {
            margin: 0;
            font-size: var(--font-size-lg, 1.125rem);
        }

        .bulk-modal-body {
            padding: var(--space-5, 1.25rem);
        }

        .bulk-modal-body p {
            margin: 0;
        }

        .bulk-modal-body p + p {
            margin-top: var(--space-2, 0.5rem);
        }

        .bulk-modal-footer {
            display: flex;
            justify-content: flex-end;
            gap: var(--space-3, 0.75rem);
            padding: var(--space-4, 1rem) var(--space-5, 1.25rem);
            border-top: 1px solid var(--color-border, #e5e5e5);
        }

        /* Toast notification */
        .bulk-toast {
            position: fixed;
            bottom: var(--space-6, 1.5rem);
            right: var(--space-6, 1.5rem);
            padding: var(--space-3, 0.75rem) var(--space-5, 1.25rem);
            background: var(--color-background, #fff);
            border-radius: var(--radius-lg, 12px);
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.15);
            z-index: 9999;
            animation: slideUp 0.3s ease-out;
        }

        .bulk-toast-success {
            border-left: 4px solid var(--color-success, #10b981);
        }

        .bulk-toast-error {
            border-left: 4px solid var(--color-error, #ef4444);
        }

        .bulk-toast-hide {
            opacity: 0;
            transform: translateY(10px);
            transition: all 0.3s;
        }

        @keyframes slideUp {
            from {
                opacity: 0;
                transform: translateY(10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        /* Card-based list checkbox positioning */
        .entry-card-checkbox {
            position: absolute;
            top: var(--space-3, 0.75rem);
            left: var(--space-3, 0.75rem);
        }

        .entry-card {
            position: relative;
        }

        .entry-card.has-checkbox .entry-link {
            padding-left: calc(var(--space-5, 1.25rem) + 28px);
        }
    `;
    document.head.appendChild(styles);

    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initBulkActions);
    } else {
        initBulkActions();
    }

    // Expose for external use
    window.bulkActions = {
        clearSelection,
        getSelected: () => Array.from(selectedItems)
    };
})();
