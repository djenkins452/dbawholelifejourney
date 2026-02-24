/**
 * Whole Life Journey - Main JavaScript
 *
 * Project: Whole Life Journey
 * Path: static/js/main.js
 * Purpose: Core JavaScript for navigation, UI interactions, and HTMX enhancements
 *
 * Description:
 *     Provides essential JavaScript functionality for the application including
 *     navigation menu toggles, user menu interactions, message dismissal,
 *     speech-to-text support, and HTMX response handling.
 *
 * Key Features:
 *     - Mobile navigation toggle (hamburger menu)
 *     - User dropdown menu with click-outside-to-close
 *     - Flash message auto-dismiss
 *     - Speech-to-text for journal entries
 *     - Pull-to-refresh on mobile devices
 *     - HTMX request/response handling
 *
 * Dependencies:
 *     - HTMX (optional, for dynamic content loading)
 *     - Web Speech API (optional, for speech-to-text)
 *
 * Copyright:
 *     (c) Whole Life Journey. All rights reserved.
 *     This code is proprietary and may not be copied, modified, or distributed
 *     without explicit permission.
 */

// ==========================================================================
// Navigation
// ==========================================================================

// Desktop Left Rail collapse/expand toggle
function toggleDesktopRail() {
    var rail = document.getElementById('desktop-left-rail');
    if (!rail) return;

    var isCollapsed = rail.classList.toggle('collapsed');

    // Toggle body class for main area margin adjustment
    document.body.classList.toggle('nav-collapsed', isCollapsed);

    // Update tooltip and label on ALL toggle buttons (top and bottom)
    var toggleBtns = rail.querySelectorAll('.rail-collapse-toggle');
    toggleBtns.forEach(function(toggleBtn) {
        toggleBtn.setAttribute('data-tooltip', isCollapsed ? 'Expand' : 'Collapse');
        var label = toggleBtn.querySelector('.rail-label');
        if (label) {
            label.textContent = isCollapsed ? 'Expand' : 'Collapse';
        }
    });

    // Persist preference via AJAX
    fetch('/users/preferences/toggle/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-CSRFToken': getCSRFToken()
        },
        body: 'field=desktop_nav_collapsed&value=' + (isCollapsed ? 'true' : 'false')
    }).catch(function(err) {
        console.warn('Failed to save rail preference:', err);
    });
}

// Get CSRF token from cookie
function getCSRFToken() {
    var name = 'csrftoken';
    var cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

function toggleMobileMenu() {
    const menu = document.getElementById('nav-menu');
    const button = document.querySelector('.nav-mobile-toggle');

    if (menu && button) {
        const isOpen = menu.classList.toggle('open');
        button.setAttribute('aria-expanded', isOpen);

        // Close all dropdowns when closing mobile menu
        if (!isOpen) {
            closeAllNavDropdowns();
        }
    }
}

function toggleUserMenu() {
    const menu = document.getElementById('user-menu');
    const button = document.querySelector('.nav-user-button');

    if (menu && button) {
        const isHidden = menu.hidden;
        menu.hidden = !isHidden;
        button.setAttribute('aria-expanded', !isHidden);
    }
}

// Toggle navigation dropdown (for mobile and click-based interaction)
function toggleNavDropdown(dropdown) {
    if (!dropdown) return;

    const button = dropdown.querySelector('.nav-dropdown-toggle');
    const menu = dropdown.querySelector('.nav-dropdown-menu');

    if (!button || !menu) return;

    const isOpen = dropdown.classList.contains('open');

    // Close all other dropdowns first
    closeAllNavDropdowns();

    if (!isOpen) {
        dropdown.classList.add('open');
        menu.hidden = false;
        button.setAttribute('aria-expanded', 'true');
    }
}

// Close all navigation dropdowns
function closeAllNavDropdowns() {
    document.querySelectorAll('.nav-dropdown').forEach(function(dropdown) {
        dropdown.classList.remove('open');
        const button = dropdown.querySelector('.nav-dropdown-toggle');
        const menu = dropdown.querySelector('.nav-dropdown-menu');
        if (button) button.setAttribute('aria-expanded', 'false');
        if (menu) menu.hidden = true;
    });
}

// Initialize nav dropdown click handlers
document.addEventListener('DOMContentLoaded', function() {
    // Add click handlers to all dropdown toggles
    document.querySelectorAll('.nav-dropdown-toggle').forEach(function(toggle) {
        toggle.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            const dropdown = toggle.closest('.nav-dropdown');
            toggleNavDropdown(dropdown);
        });
    });
});

// Close user menu when clicking outside
document.addEventListener('click', function(event) {
    const userMenu = document.getElementById('user-menu');
    const userButton = document.querySelector('.nav-user-button');

    if (userMenu && userButton) {
        if (!userButton.contains(event.target) && !userMenu.contains(event.target)) {
            userMenu.hidden = true;
            userButton.setAttribute('aria-expanded', 'false');
        }
    }

    // Close nav dropdowns when clicking outside (for mobile)
    const clickedDropdown = event.target.closest('.nav-dropdown');
    document.querySelectorAll('.nav-dropdown').forEach(function(dropdown) {
        if (dropdown !== clickedDropdown) {
            dropdown.classList.remove('open');
            const button = dropdown.querySelector('.nav-dropdown-toggle');
            const menu = dropdown.querySelector('.nav-dropdown-menu');
            if (button) button.setAttribute('aria-expanded', 'false');
            if (menu) menu.hidden = true;
        }
    });
});

// Close mobile menu when clicking outside
document.addEventListener('click', function(event) {
    const navMenu = document.getElementById('nav-menu');
    const mobileToggle = document.querySelector('.nav-mobile-toggle');

    if (navMenu && mobileToggle) {
        if (!mobileToggle.contains(event.target) && !navMenu.contains(event.target)) {
            navMenu.classList.remove('open');
            mobileToggle.setAttribute('aria-expanded', 'false');
            closeAllNavDropdowns();
        }
    }
});

// ==========================================================================
// Messages
// ==========================================================================

// Auto-dismiss messages after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    const messages = document.querySelectorAll('.message');
    
    messages.forEach(function(message) {
        setTimeout(function() {
            message.style.transition = 'opacity 0.3s ease';
            message.style.opacity = '0';
            setTimeout(function() {
                message.remove();
            }, 300);
        }, 5000);
    });
});

// ==========================================================================
// Form Enhancements
// ==========================================================================

// Auto-resize textareas
document.addEventListener('DOMContentLoaded', function() {
    const textareas = document.querySelectorAll('textarea.auto-resize');
    
    textareas.forEach(function(textarea) {
        function resize() {
            textarea.style.height = 'auto';
            textarea.style.height = textarea.scrollHeight + 'px';
        }
        
        textarea.addEventListener('input', resize);
        resize(); // Initial resize
    });
});

// Character counter for textareas
document.addEventListener('DOMContentLoaded', function() {
    const textareas = document.querySelectorAll('textarea[data-max-length]');
    
    textareas.forEach(function(textarea) {
        const maxLength = parseInt(textarea.dataset.maxLength, 10);
        const counter = document.createElement('div');
        counter.className = 'text-xs text-muted mt-1';
        textarea.parentNode.appendChild(counter);
        
        function updateCounter() {
            const remaining = maxLength - textarea.value.length;
            counter.textContent = remaining + ' characters remaining';
            counter.style.color = remaining < 50 ? 'var(--color-warning)' : '';
        }
        
        textarea.addEventListener('input', updateCounter);
        updateCounter();
    });
});

// ==========================================================================
// Page Load Progress Bar
// ==========================================================================

(function() {
    var progressBar = null;

    function showProgress() {
        if (!progressBar) progressBar = document.getElementById('page-progress');
        if (progressBar) {
            progressBar.classList.remove('finishing');
            progressBar.classList.add('active');
        }
    }

    function hideProgress() {
        if (!progressBar) progressBar = document.getElementById('page-progress');
        if (progressBar) {
            progressBar.classList.add('finishing');
            setTimeout(function() {
                progressBar.classList.remove('active', 'finishing');
            }, 200);
        }
    }

    // Show progress on link clicks (navigation)
    document.addEventListener('click', function(e) {
        var link = e.target.closest('a[href]');
        if (!link) return;

        var href = link.getAttribute('href');
        // Skip if: external link, anchor, javascript, new tab, or HTMX-handled
        if (!href ||
            href.startsWith('#') ||
            href.startsWith('javascript:') ||
            href.startsWith('mailto:') ||
            href.startsWith('tel:') ||
            link.getAttribute('target') === '_blank' ||
            link.hasAttribute('hx-get') ||
            link.hasAttribute('hx-post') ||
            link.hasAttribute('data-no-progress')) {
            return;
        }

        showProgress();
    });

    // Show progress on form submissions (skip JS-handled forms like CoS chat)
    document.addEventListener('submit', function(e) {
        if (e.defaultPrevented) return;
        var form = e.target;
        if (form.hasAttribute('hx-post') || form.hasAttribute('hx-get')) return;
        showProgress();
    });

    // Hide on page load complete
    window.addEventListener('load', function() {
        hideProgress();
    });

    // Handle browser back/forward
    window.addEventListener('pageshow', function(e) {
        if (e.persisted) {
            hideProgress();
        }
    });

    // HTMX integration
    document.body.addEventListener('htmx:beforeRequest', function() {
        showProgress();
    });

    document.body.addEventListener('htmx:afterRequest', function() {
        hideProgress();
    });
})();

// ==========================================================================
// HTMX Enhancements
// ==========================================================================

// Add loading indicator during HTMX requests
document.body.addEventListener('htmx:beforeRequest', function(event) {
    const trigger = event.detail.elt;
    if (trigger) {
        trigger.classList.add('htmx-loading');
    }
});

document.body.addEventListener('htmx:afterRequest', function(event) {
    const trigger = event.detail.elt;
    if (trigger) {
        trigger.classList.remove('htmx-loading');
    }
});

// ==========================================================================
// Accessibility
// ==========================================================================

// Handle keyboard navigation for custom dropdowns
document.addEventListener('keydown', function(event) {
    // Close menus on Escape
    if (event.key === 'Escape') {
        const userMenu = document.getElementById('user-menu');
        const navMenu = document.getElementById('nav-menu');
        const mobileToggle = document.querySelector('.nav-mobile-toggle');

        if (userMenu) userMenu.hidden = true;
        if (navMenu) {
            navMenu.classList.remove('open');
            if (mobileToggle) mobileToggle.setAttribute('aria-expanded', 'false');
        }

        // Close all navigation dropdowns
        closeAllNavDropdowns();
    }
});

// ==========================================================================
// Date Formatting Helper
// ==========================================================================

function formatDate(dateString) {
    const date = new Date(dateString);
    const options = { 
        weekday: 'long', 
        year: 'numeric', 
        month: 'long', 
        day: 'numeric' 
    };
    return date.toLocaleDateString('en-US', options);
}

// ==========================================================================
// Confirmation Dialogs
// ==========================================================================

function confirmDelete(message) {
    return confirm(message || 'Are you sure you want to delete this? This action cannot be undone.');
}

function confirmArchive(message) {
    return confirm(message || 'Are you sure you want to archive this? You can restore it later from the Archives.');
}

// Attach confirmation to delete/archive forms
document.addEventListener('DOMContentLoaded', function() {
    // Delete confirmations
    document.querySelectorAll('form[data-confirm-delete]').forEach(function(form) {
        form.addEventListener('submit', function(event) {
            if (!confirmDelete(form.dataset.confirmDelete)) {
                event.preventDefault();
            }
        });
    });
    
    // Archive confirmations
    document.querySelectorAll('form[data-confirm-archive]').forEach(function(form) {
        form.addEventListener('submit', function(event) {
            if (!confirmArchive(form.dataset.confirmArchive)) {
                event.preventDefault();
            }
        });
    });
});

// ==========================================================================
// Theme Preview (for theme selection page)
// ==========================================================================

function previewTheme(themeName) {
    document.documentElement.setAttribute('data-theme', themeName);
    document.body.className = 'theme-' + themeName;
}

// ==========================================================================
// Word Count (for journal entries)
// ==========================================================================

document.addEventListener('DOMContentLoaded', function() {
    const bodyTextarea = document.querySelector('textarea[name="body"]');
    const wordCountDisplay = document.getElementById('word-count');

    if (bodyTextarea && wordCountDisplay) {
        function updateWordCount() {
            const text = bodyTextarea.value.trim();
            const words = text ? text.split(/\s+/).length : 0;
            wordCountDisplay.textContent = words + ' word' + (words !== 1 ? 's' : '');
        }

        bodyTextarea.addEventListener('input', updateWordCount);
        updateWordCount();
    }
});

// ==========================================================================
// Pull-to-Refresh (Mobile)
// ==========================================================================

(function() {
    // Only enable on touch devices
    if (!('ontouchstart' in window)) return;

    let startY = 0;
    let currentY = 0;
    let isPulling = false;
    let refreshIndicator = null;
    const THRESHOLD = 80; // Pixels to pull before triggering refresh

    // Create the refresh indicator element
    function createRefreshIndicator() {
        const indicator = document.createElement('div');
        indicator.id = 'pull-to-refresh-indicator';
        indicator.innerHTML = `
            <div class="ptr-content">
                <svg class="ptr-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M23 4v6h-6M1 20v-6h6"/>
                    <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
                </svg>
                <span class="ptr-text">Pull to refresh</span>
            </div>
        `;
        document.body.insertBefore(indicator, document.body.firstChild);
        return indicator;
    }

    // Initialize
    document.addEventListener('DOMContentLoaded', function() {
        refreshIndicator = createRefreshIndicator();
    });

    // Touch start - record starting position
    document.addEventListener('touchstart', function(e) {
        // Only trigger if at top of page and not in a scrollable element
        if (window.scrollY === 0) {
            const target = e.target;
            // Don't trigger on inputs, textareas, or scrollable containers
            if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' ||
                target.closest('.nav-menu.open') || target.closest('[data-no-ptr]')) {
                return;
            }
            startY = e.touches[0].pageY;
            isPulling = true;
        }
    }, { passive: true });

    // Touch move - track pull distance
    document.addEventListener('touchmove', function(e) {
        if (!isPulling || !refreshIndicator) return;

        currentY = e.touches[0].pageY;
        const pullDistance = currentY - startY;

        // Only show indicator when pulling down
        if (pullDistance > 0 && window.scrollY === 0) {
            const progress = Math.min(pullDistance / THRESHOLD, 1);
            const translateY = Math.min(pullDistance * 0.5, THRESHOLD);

            refreshIndicator.style.transform = `translateY(${translateY}px)`;
            refreshIndicator.style.opacity = progress;

            // Update text based on threshold
            const textEl = refreshIndicator.querySelector('.ptr-text');
            const iconEl = refreshIndicator.querySelector('.ptr-icon');

            if (pullDistance >= THRESHOLD) {
                textEl.textContent = 'Release to refresh';
                iconEl.style.transform = 'rotate(180deg)';
                refreshIndicator.classList.add('ptr-ready');
            } else {
                textEl.textContent = 'Pull to refresh';
                iconEl.style.transform = `rotate(${progress * 180}deg)`;
                refreshIndicator.classList.remove('ptr-ready');
            }
        }
    }, { passive: true });

    // Touch end - trigger refresh if threshold met
    document.addEventListener('touchend', function() {
        if (!isPulling || !refreshIndicator) return;

        const pullDistance = currentY - startY;

        if (pullDistance >= THRESHOLD && window.scrollY === 0) {
            // Show refreshing state
            refreshIndicator.classList.add('ptr-refreshing');
            refreshIndicator.querySelector('.ptr-text').textContent = 'Refreshing...';

            // Reload the page with cache bust
            setTimeout(function() {
                // Force hard reload by adding timestamp to URL
                var url = window.location.href;
                // Remove any existing cache bust parameter
                url = url.replace(/[?&]_reload=\d+/, '');
                // Add new cache bust parameter
                var separator = url.indexOf('?') === -1 ? '?' : '&';
                window.location.href = url + separator + '_reload=' + Date.now();
            }, 300);
        } else {
            // Reset indicator
            refreshIndicator.style.transform = 'translateY(0)';
            refreshIndicator.style.opacity = '0';
            refreshIndicator.classList.remove('ptr-ready');
        }

        isPulling = false;
        startY = 0;
        currentY = 0;
    }, { passive: true });
})();

// ==========================================================================
// CSP-Compliant Global Event Delegation
// ==========================================================================
// Nonce-based CSP blocks inline event handlers (onclick, onchange, etc.).
// This section provides delegated handlers for common patterns used across
// the app, so templates don't need inline handlers.

(function() {
    'use strict';

    // --- CLICK delegation ---
    document.addEventListener('click', function(e) {
        var target = e.target;

        // Message close button (base.html)
        var msgClose = target.closest('.message-close');
        if (msgClose) {
            msgClose.parentElement.remove();
            return;
        }

        // Mobile menu toggle (navigation.html)
        if (target.closest('.nav-mobile-toggle')) {
            toggleMobileMenu();
            return;
        }

        // User menu toggle (navigation.html)
        if (target.closest('.nav-user-button')) {
            toggleUserMenu();
            return;
        }

        // Desktop left rail toggle
        if (target.closest('.rail-collapse-toggle')) {
            toggleDesktopRail();
            return;
        }

        // --- data-action delegation (CSP-compliant replacement for onclick) ---
        var actionEl = target.closest('[data-action]');
        if (actionEl) {
            var action = actionEl.dataset.action;

            switch (action) {
                // Help modal
                case 'open-help':
                    if (typeof openHelpModal === 'function') openHelpModal(e);
                    e.preventDefault();
                    break;
                case 'close-help':
                    if (typeof closeHelpModal === 'function') closeHelpModal();
                    break;

                // What's New modal
                case 'dismiss-whats-new':
                    if (typeof dismissWhatsNew === 'function') dismissWhatsNew();
                    break;

                // Intro banner
                case 'dismiss-intro':
                    if (typeof dismissIntroBanner === 'function') dismissIntroBanner(actionEl.dataset.module);
                    break;

                // System announcement
                case 'dismiss-announcement':
                    if (typeof dismissAnnouncement === 'function') dismissAnnouncement(actionEl.dataset.announcementId);
                    break;

                // Development notice
                case 'dismiss-dev-notice':
                    if (typeof dismissDevNotice === 'function') dismissDevNotice();
                    break;

                // Pending capture banner
                case 'dismiss-capture-banner':
                    if (typeof dismissPendingCaptureBanner === 'function') dismissPendingCaptureBanner();
                    break;

                // Faith upgrade
                case 'dismiss-faith-upgrade':
                    if (typeof dismissFaithUpgrade === 'function') dismissFaithUpgrade();
                    break;

                // CoS arrival briefing
                case 'dismiss-arrival-briefing':
                    if (typeof dismissArrivalBriefing === 'function') dismissArrivalBriefing();
                    break;

                // Assistant panel
                case 'toggle-assistant-panel':
                    if (typeof toggleAssistantPanel === 'function') toggleAssistantPanel();
                    break;
                case 'toggle-section':
                    if (typeof toggleSection === 'function') toggleSection(actionEl.dataset.section);
                    break;
                case 'open-assistant-chat':
                    if (typeof openAssistantChat === 'function') openAssistantChat();
                    break;
                case 'open-assistant':
                    var assistantBtn = document.getElementById('assistant-toggle-btn');
                    if (assistantBtn) assistantBtn.click();
                    break;
                case 'trigger-curveball':
                    if (typeof triggerCurveball === 'function') triggerCurveball();
                    break;
                case 'view-blueprint':
                    if (typeof viewBlueprint === 'function') viewBlueprint();
                    break;
                case 'toggle-mobile-assistant':
                    if (typeof toggleMobileAssistant === 'function') toggleMobileAssistant();
                    break;
                case 'respond-friction-gate':
                    if (typeof respondFrictionGate === 'function') {
                        respondFrictionGate(actionEl.dataset.interventionId, actionEl.dataset.response);
                    }
                    break;

                // CoS command mode
                case 'skip-reflection':
                    if (typeof skipReflection === 'function') skipReflection(actionEl.dataset.reflectionId);
                    break;
                case 'enter-data-mode':
                    if (typeof enterDataMode === 'function') enterDataMode(e);
                    e.preventDefault();
                    break;

                // Notifications
                case 'mark-all-read':
                    if (typeof markAllNotificationsRead === 'function') markAllNotificationsRead();
                    break;
                case 'notification-click':
                    if (typeof handleNotificationClick === 'function') {
                        var notifItem = actionEl.closest('[data-notification-id]');
                        var notifId = notifItem ? notifItem.dataset.notificationId : null;
                        handleNotificationClick(notifId, actionEl.dataset.notificationUrl);
                    }
                    break;

                // Generic dismiss (removes own closest container)
                case 'dismiss':
                    var dismissTarget = actionEl.dataset.dismissTarget;
                    if (dismissTarget) {
                        var el = document.getElementById(dismissTarget);
                        if (el) el.remove();
                    } else {
                        actionEl.parentElement.remove();
                    }
                    break;

                // Generic self-remove
                case 'self-remove':
                    actionEl.remove();
                    break;
            }
            return;
        }

        // Notification bell toggle (class-based, for notification_bell.html)
        if (target.closest('.notification-bell-button')) {
            if (typeof toggleNotificationDropdown === 'function') {
                toggleNotificationDropdown();
            }
            return;
        }
    });

    // --- SUBMIT delegation for confirm dialogs and form handlers ---
    document.addEventListener('submit', function(e) {
        var form = e.target;

        // Confirm dialog: <form data-confirm="Are you sure?">
        var confirmMsg = form.dataset.confirm;
        if (confirmMsg) {
            if (!confirm(confirmMsg)) {
                e.preventDefault();
            }
        }

        // CoS command mode form
        if (form.id === 'cos-cm-form') {
            if (typeof handleCommandModeInput === 'function') {
                handleCommandModeInput(e);
            } else {
                e.preventDefault();
            }
        }
    });

    // --- CHANGE delegation for auto-submit selects ---
    document.addEventListener('change', function(e) {
        var target = e.target;

        // Auto-submit select: <select data-auto-submit>
        if (target.dataset.autoSubmit !== undefined) {
            var form = target.closest('form');
            if (form) {
                form.submit();
            }
            return;
        }

        // Navigation change: <select data-navigate-param="type">
        var navParam = target.dataset.navigateParam;
        if (navParam) {
            location.href = '?' + navParam + '=' + target.value;
            return;
        }
    });

    // --- CLICK delegation for stop-propagation (.click-stop) ---
    // Elements with class "click-stop" prevent click from bubbling to parent
    // Used for checkboxes/buttons inside clickable rows/cards
    document.addEventListener('click', function(e) {
        if (e.target.closest('.click-stop')) {
            e.stopPropagation();
        }
    }, true); // Use capture phase so it runs before other click handlers

    // --- CLICK delegation for closing modals (data-close-modal) ---
    // Buttons with data-close-modal close the nearest parent <dialog>
    document.addEventListener('click', function(e) {
        var btn = e.target.closest('[data-close-modal]');
        if (btn) {
            var dialog = btn.closest('dialog');
            if (dialog) dialog.close();
        }
    });
})();
