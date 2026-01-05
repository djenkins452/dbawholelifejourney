/**
 * Favorites Toggle Functionality
 *
 * Handles the star toggle button for adding/removing pages from favorites.
 * Also provides menu refresh functionality.
 */

(function() {
    'use strict';

    // Get CSRF token from cookie
    function getCsrfToken() {
        const name = 'csrftoken';
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const [key, value] = cookie.trim().split('=');
            if (key === name) {
                return value;
            }
        }
        return '';
    }

    // Toggle favorite status
    async function toggleFavorite(button) {
        const url = button.dataset.url;
        // Use data-title if provided, otherwise extract from page title
        let title = button.dataset.title;
        if (!title || title === 'Page') {
            // Extract title from <title> tag, removing site suffix
            const pageTitle = document.title || '';
            title = pageTitle.split(' - ')[0].split(' | ')[0].trim() || 'This Page';
        }

        if (!url) {
            console.error('Favorite toggle missing url data attribute');
            return;
        }

        // Disable button during request
        button.disabled = true;

        try {
            const response = await fetch('/api/favorites/toggle/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
                body: JSON.stringify({ url, title }),
            });

            if (!response.ok) {
                throw new Error('Failed to toggle favorite');
            }

            const data = await response.json();

            // Handle max favorites error
            if (data.error) {
                showToast(data.error, 'warning');
                return;
            }

            // Update button state
            const isFavorite = data.is_favorite;
            button.classList.toggle('is-favorite', isFavorite);
            button.setAttribute('aria-label', isFavorite ? 'Remove from favorites' : 'Add to favorites');
            button.setAttribute('title', isFavorite ? 'Remove from favorites' : 'Add to favorites');

            // Update star fill and stroke colors
            const polygon = button.querySelector('polygon');
            if (polygon) {
                polygon.setAttribute('fill', isFavorite ? '#f59e0b' : 'none');
                polygon.setAttribute('stroke', isFavorite ? '#f59e0b' : '#9ca3af');
            }

            // Add animation class
            button.classList.add('animating');
            setTimeout(() => button.classList.remove('animating'), 300);

            // Show feedback
            showToast(isFavorite ? 'Added to favorites' : 'Removed from favorites', 'success');

        } catch (error) {
            console.error('Error toggling favorite:', error);
            showToast('Failed to update favorite', 'error');
        } finally {
            button.disabled = false;
        }
    }

    // Simple toast notification
    function showToast(message, type = 'info') {
        // Check if there's an existing toast system
        const existingToast = document.querySelector('.toast-container');
        if (existingToast && window.showToast) {
            window.showToast(message, type);
            return;
        }

        // Create simple toast
        const toast = document.createElement('div');
        toast.className = `favorite-toast favorite-toast-${type}`;
        toast.textContent = message;
        toast.style.cssText = `
            position: fixed;
            bottom: 1rem;
            right: 1rem;
            padding: 0.75rem 1.5rem;
            background: ${type === 'success' ? 'var(--color-success, #10b981)' :
                         type === 'warning' ? 'var(--color-warning, #f59e0b)' :
                         type === 'error' ? 'var(--color-danger, #ef4444)' :
                         'var(--color-surface)'};
            color: white;
            border-radius: var(--radius-md, 0.5rem);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            z-index: 10000;
            animation: fadeInUp 0.3s ease;
        `;

        document.body.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'fadeOutDown 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    // Add CSS animations if not present
    function addAnimationStyles() {
        if (document.getElementById('favorite-animations')) return;

        const style = document.createElement('style');
        style.id = 'favorite-animations';
        style.textContent = `
            @keyframes fadeInUp {
                from { opacity: 0; transform: translateY(1rem); }
                to { opacity: 1; transform: translateY(0); }
            }
            @keyframes fadeOutDown {
                from { opacity: 1; transform: translateY(0); }
                to { opacity: 0; transform: translateY(1rem); }
            }
        `;
        document.head.appendChild(style);
    }

    // Initialize on DOM ready
    function init() {
        addAnimationStyles();

        // Find and bind inline favorite toggle button (in page header)
        const inlineBtn = document.getElementById('favorite-toggle');
        if (inlineBtn) {
            inlineBtn.addEventListener('click', () => toggleFavorite(inlineBtn));
        }

        // Find and bind floating favorite toggle button
        const floatingBtn = document.getElementById('favorite-floating-toggle');
        if (floatingBtn) {
            floatingBtn.addEventListener('click', () => toggleFavorite(floatingBtn));

            // Hide floating button if inline button exists
            if (inlineBtn) {
                floatingBtn.style.display = 'none';
            }
        }
    }

    // Run when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Expose for external use
    window.WLJFavorites = {
        toggleFavorite,
        showToast,
    };

})();
