/**
 * Whole Life Journey - Context-Aware Help System
 *
 * Project: Whole Life Journey
 * Path: static/js/help.js
 * Purpose: Client-side JavaScript for the context-aware help modal
 *
 * Description:
 *     Handles the help modal functionality including opening/closing,
 *     fetching context-specific help content via API, and displaying
 *     formatted Markdown documentation.
 *
 * Key Features:
 *     - Open/close help modal with keyboard shortcuts
 *     - Fetch help content based on current HELP_CONTEXT_ID
 *     - Render Markdown content in modal
 *     - Related topics navigation
 *     - Loading states and error handling
 *
 * Dependencies:
 *     - Help modal element with id="help-modal"
 *     - Help trigger button with id="help-trigger"
 *     - Server API endpoint for help content
 *
 * Copyright:
 *     (c) Whole Life Journey. All rights reserved.
 *     This code is proprietary and may not be copied, modified, or distributed
 *     without explicit permission.
 */

// =============================================================================
// MODAL FUNCTIONS
// =============================================================================

/**
 * Opens the help modal and fetches content for the current context.
 */
function openHelpModal() {
    const modal = document.getElementById('help-modal');
    const trigger = document.getElementById('help-trigger');

    if (!modal || !trigger) {
        console.error('Help modal or trigger not found');
        return;
    }

    // Get context from the trigger button
    const contextId = trigger.dataset.helpContext || 'GENERAL';
    const helpType = trigger.dataset.helpType || 'user';

    // Show modal
    modal.showModal();

    // Fetch help content
    fetchHelpContent(contextId, helpType);
}

/**
 * Closes the help modal.
 */
function closeHelpModal() {
    const modal = document.getElementById('help-modal');
    if (modal) {
        modal.close();
    }
}

/**
 * Handle clicking outside the modal to close it.
 */
function initHelpModalClickOutside() {
    const modal = document.getElementById('help-modal');
    if (!modal) return;

    modal.addEventListener('click', (e) => {
        // If clicking on the dialog backdrop (outside content)
        if (e.target === modal) {
            closeHelpModal();
        }
    });

    // Close on Escape key
    modal.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeHelpModal();
        }
    });
}

// =============================================================================
// API FUNCTIONS
// =============================================================================

/**
 * Fetches help content from the API.
 *
 * @param {string} contextId - The HELP_CONTEXT_ID for the current page
 * @param {string} helpType - 'user' for regular help, 'admin' for admin help
 */
async function fetchHelpContent(contextId, helpType) {
    const body = document.getElementById('help-modal-body');
    const title = document.getElementById('help-modal-title');
    const footer = document.getElementById('help-modal-footer');
    const relatedList = document.getElementById('help-related-topics');

    // Show loading state
    body.innerHTML = `
        <div class="help-loading">
            <div class="help-loading-spinner"></div>
            <p>Loading help...</p>
        </div>
    `;
    footer.hidden = true;

    // Determine API endpoint
    const endpoint = helpType === 'admin'
        ? `/help/api/admin/${contextId}/`
        : `/help/api/topic/${contextId}/`;

    try {
        const response = await fetch(endpoint, {
            headers: {
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        // Update title
        title.textContent = data.title || 'Help';

        if (data.found) {
            // Show content
            let contentHtml = '';

            if (data.description) {
                contentHtml += `<p class="help-description">${escapeHtml(data.description)}</p>`;
            }

            contentHtml += `<div class="help-content">${data.content}</div>`;

            body.innerHTML = contentHtml;

            // Show related topics if any
            if (data.related && data.related.length > 0) {
                relatedList.innerHTML = data.related.map(topic => `
                    <li>
                        <button
                            type="button"
                            class="help-related-link"
                            onclick="loadRelatedTopic('${escapeHtml(topic.context_id)}', '${helpType}')"
                        >
                            ${escapeHtml(topic.title)}
                        </button>
                    </li>
                `).join('');
                footer.hidden = false;
            }
        } else {
            // Show not found state
            body.innerHTML = `
                <div class="help-not-found">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"/>
                        <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>
                        <line x1="12" y1="17" x2="12.01" y2="17"/>
                    </svg>
                    <h3>${data.title}</h3>
                    <p>${escapeHtml(data.content)}</p>
                </div>
            `;
        }
    } catch (error) {
        console.error('Error fetching help:', error);
        body.innerHTML = `
            <div class="help-not-found">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"/>
                    <line x1="12" y1="8" x2="12" y2="12"/>
                    <line x1="12" y1="16" x2="12.01" y2="16"/>
                </svg>
                <h3>Unable to Load Help</h3>
                <p>There was a problem loading help content. Please try again.</p>
            </div>
        `;
    }
}

/**
 * Loads a related topic's content.
 *
 * @param {string} contextId - The context ID of the related topic
 * @param {string} helpType - 'user' or 'admin'
 */
function loadRelatedTopic(contextId, helpType) {
    fetchHelpContent(contextId, helpType);
}

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================

/**
 * Escapes HTML entities to prevent XSS.
 *
 * @param {string} text - The text to escape
 * @returns {string} - Escaped text
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Updates the help context ID dynamically.
 * Call this when navigating within a single-page app section.
 *
 * @param {string} contextId - The new HELP_CONTEXT_ID
 * @param {string} helpType - 'user' or 'admin' (optional)
 */
function setHelpContext(contextId, helpType = null) {
    const trigger = document.getElementById('help-trigger');
    if (trigger) {
        trigger.dataset.helpContext = contextId;
        if (helpType) {
            trigger.dataset.helpType = helpType;
        }
    }
}

// =============================================================================
// INITIALIZATION
// =============================================================================

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    initHelpModalClickOutside();
});

// Also support HTMX page loads
document.body.addEventListener('htmx:afterSwap', function() {
    initHelpModalClickOutside();
});
