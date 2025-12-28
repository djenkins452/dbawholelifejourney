/**
 * Whole Life Journey - Main JavaScript
 *
 * Minimal, purposeful JavaScript for:
 * - Navigation interactions
 * - User menu toggle
 * - Message dismissal
 * - HTMX enhancements
 * - Pull-to-refresh on mobile
 */

// ==========================================================================
// Navigation
// ==========================================================================

function toggleMobileMenu() {
    const menu = document.getElementById('nav-menu');
    const button = document.querySelector('.nav-mobile-toggle');
    
    if (menu && button) {
        const isOpen = menu.classList.toggle('open');
        button.setAttribute('aria-expanded', isOpen);
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
});

// Close mobile menu when clicking outside
document.addEventListener('click', function(event) {
    const navMenu = document.getElementById('nav-menu');
    const mobileToggle = document.querySelector('.nav-mobile-toggle');
    
    if (navMenu && mobileToggle) {
        if (!mobileToggle.contains(event.target) && !navMenu.contains(event.target)) {
            navMenu.classList.remove('open');
            mobileToggle.setAttribute('aria-expanded', 'false');
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
        
        if (userMenu) userMenu.hidden = true;
        if (navMenu) navMenu.classList.remove('open');
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

            // Reload the page
            setTimeout(function() {
                window.location.reload();
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
