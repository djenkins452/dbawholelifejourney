/**
 * What's New Feature - JavaScript
 *
 * Handles checking for unseen release notes and displaying the modal.
 * Runs on page load for authenticated users.
 */

(function() {
    'use strict';

    // Configuration
    const CHECK_ENDPOINT = '/api/whats-new/check/';
    const DISMISS_ENDPOINT = '/api/whats-new/dismiss/';

    // DOM elements
    let modal = null;
    let modalBody = null;

    /**
     * Initialize the What's New feature on page load.
     */
    function init() {
        modal = document.getElementById('whats-new-modal');
        modalBody = document.getElementById('whats-new-modal-body');

        if (!modal) {
            // Modal not present, likely unauthenticated user
            return;
        }

        // Check for unseen notes on page load (with small delay to not block rendering)
        setTimeout(checkForUpdates, 500);

        // Close modal when clicking outside
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                dismissWhatsNew();
            }
        });

        // Close on Escape key
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && modal.open) {
                dismissWhatsNew();
            }
        });
    }

    /**
     * Check the API for unseen release notes.
     */
    async function checkForUpdates() {
        try {
            const response = await fetch(CHECK_ENDPOINT, {
                method: 'GET',
                headers: {
                    'Accept': 'application/json',
                },
                credentials: 'same-origin',
            });

            if (!response.ok) {
                console.error('What\'s New: Failed to check for updates');
                return;
            }

            const data = await response.json();

            if (data.has_unseen && data.notes && data.notes.length > 0) {
                showModal(data.notes);
            }
        } catch (error) {
            console.error('What\'s New: Error checking for updates', error);
        }
    }

    /**
     * Display the modal with the given release notes.
     */
    function showModal(notes) {
        if (!modalBody) return;

        // Build the content HTML
        let html = '';

        notes.forEach(function(note) {
            html += buildNoteHTML(note);
        });

        modalBody.innerHTML = html;

        // Show the modal
        modal.showModal();

        // Animate in
        modal.classList.add('whats-new-modal-open');
    }

    /**
     * Build HTML for a single release note item.
     */
    function buildNoteHTML(note) {
        const badgeClass = 'badge-' + note.entry_type;
        const dateFormatted = formatDate(note.release_date);

        let html = `
            <div class="whats-new-item">
                <div class="whats-new-item-icon">${note.icon}</div>
                <div class="whats-new-item-content">
                    <div class="whats-new-item-header">
                        <h3 class="whats-new-item-title">${escapeHtml(note.title)}</h3>
                        <span class="whats-new-item-badge ${badgeClass}">${escapeHtml(note.type_display)}</span>
                        ${note.is_major ? '<span class="whats-new-item-badge badge-major">Major</span>' : ''}
                    </div>
                    <p class="whats-new-item-description">${escapeHtml(note.description)}</p>
                    <div class="whats-new-item-date">${dateFormatted}</div>
                    ${note.learn_more_url ? `<a href="${escapeHtml(note.learn_more_url)}" class="whats-new-item-link" target="_blank" rel="noopener">Learn more</a>` : ''}
                </div>
            </div>
        `;

        return html;
    }

    /**
     * Dismiss the modal and mark notes as seen.
     */
    window.dismissWhatsNew = async function() {
        if (!modal) return;

        // Close the modal
        modal.close();
        modal.classList.remove('whats-new-modal-open');

        // Mark as seen on the server
        try {
            const csrfToken = getCsrfToken();

            await fetch(DISMISS_ENDPOINT, {
                method: 'POST',
                headers: {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken,
                },
                credentials: 'same-origin',
            });
        } catch (error) {
            console.error('What\'s New: Error marking as seen', error);
        }
    };

    /**
     * Get the CSRF token from the cookie.
     */
    function getCsrfToken() {
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
     * Format an ISO date string to a human-readable format.
     */
    function formatDate(isoDate) {
        const date = new Date(isoDate);
        const options = { year: 'numeric', month: 'long', day: 'numeric' };
        return date.toLocaleDateString('en-US', options);
    }

    /**
     * Escape HTML to prevent XSS.
     */
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
