/**
 * Whole Life Journey - Main JavaScript
 * 
 * Minimal, purposeful JavaScript for:
 * - Navigation interactions
 * - User menu toggle
 * - Message dismissal
 * - HTMX enhancements
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
