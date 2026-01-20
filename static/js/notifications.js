/**
 * Notification Bell - In-App Notification System
 *
 * Handles:
 * - Notification bell dropdown toggle
 * - Fetching and displaying notifications
 * - Marking notifications as read
 * - Updating the unread badge count
 *
 * File: static/js/notifications.js
 * Project: Whole Life Journey
 */

(function() {
    'use strict';

    // State
    let isDropdownOpen = false;
    let notificationsLoaded = false;
    let refreshInterval = null;

    // DOM Elements (lazy loaded)
    function getBellTrigger() {
        return document.getElementById('notification-bell-trigger');
    }

    function getDropdown() {
        return document.getElementById('notification-dropdown');
    }

    function getBadge() {
        return document.getElementById('notification-badge');
    }

    function getNotificationList() {
        return document.getElementById('notification-list');
    }

    /**
     * Toggle the notification dropdown
     */
    window.toggleNotificationDropdown = function() {
        const dropdown = getDropdown();
        const trigger = getBellTrigger();

        if (!dropdown || !trigger) return;

        isDropdownOpen = !isDropdownOpen;

        if (isDropdownOpen) {
            dropdown.hidden = false;
            trigger.setAttribute('aria-expanded', 'true');
            loadNotifications();

            // Close when clicking outside
            setTimeout(() => {
                document.addEventListener('click', closeOnOutsideClick);
            }, 10);
        } else {
            closeDropdown();
        }
    };

    /**
     * Close the dropdown
     */
    function closeDropdown() {
        const dropdown = getDropdown();
        const trigger = getBellTrigger();

        if (dropdown) dropdown.hidden = true;
        if (trigger) trigger.setAttribute('aria-expanded', 'false');

        isDropdownOpen = false;
        document.removeEventListener('click', closeOnOutsideClick);
    }

    /**
     * Close dropdown when clicking outside
     */
    function closeOnOutsideClick(event) {
        const container = document.getElementById('notification-bell-container');
        if (container && !container.contains(event.target)) {
            closeDropdown();
        }
    }

    /**
     * Load notifications from API
     */
    function loadNotifications() {
        const listEl = getNotificationList();
        if (!listEl) return;

        // Show loading state only on first load
        if (!notificationsLoaded) {
            listEl.innerHTML = '<div class="notification-loading">Loading...</div>';
        }

        fetch('/api/notifications/unread/')
            .then(response => response.json())
            .then(data => {
                notificationsLoaded = true;
                renderNotifications(data.notifications);
                updateBadge(data.unread_count);
            })
            .catch(error => {
                console.error('Failed to load notifications:', error);
                listEl.innerHTML = '<div class="notification-empty">Failed to load notifications</div>';
            });
    }

    /**
     * Render notifications in the dropdown
     */
    function renderNotifications(notifications) {
        const listEl = getNotificationList();
        if (!listEl) return;

        if (!notifications || notifications.length === 0) {
            listEl.innerHTML = `
                <div class="notification-empty">
                    <div class="notification-empty-icon">🔔</div>
                    <p>No new notifications</p>
                </div>
            `;
            return;
        }

        listEl.innerHTML = notifications.map(notification => `
            <a href="${notification.action_url || '#'}"
               class="notification-item ${notification.is_read ? '' : 'unread'}"
               data-notification-id="${notification.id}"
               onclick="handleNotificationItemClick(event, ${notification.id}, '${notification.action_url || ''}')">
                <div class="notification-item-icon">${notification.icon}</div>
                <div class="notification-item-content">
                    <h4 class="notification-item-title">${escapeHtml(notification.title)}</h4>
                    <p class="notification-item-message">${escapeHtml(notification.message)}</p>
                    <span class="notification-item-time">${formatTimeAgo(notification.created_at)}</span>
                </div>
            </a>
        `).join('');
    }

    /**
     * Handle notification item click
     */
    window.handleNotificationItemClick = function(event, notificationId, actionUrl) {
        event.preventDefault();

        // Mark as read
        fetch(`/api/notifications/${notificationId}/read/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCsrfToken(),
                'Content-Type': 'application/json',
            },
        }).then(() => {
            // Update UI
            const item = document.querySelector(`[data-notification-id="${notificationId}"]`);
            if (item) {
                item.classList.remove('unread');
            }

            // Update badge
            updateNotificationBadge();

            // Navigate
            if (actionUrl && actionUrl !== '#') {
                window.location.href = actionUrl;
            } else {
                closeDropdown();
            }
        });
    };

    /**
     * Mark all notifications as read
     */
    window.markAllNotificationsRead = function() {
        fetch('/api/notifications/mark-all-read/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCsrfToken(),
                'Content-Type': 'application/json',
            },
        })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Update all items in dropdown
                    document.querySelectorAll('.notification-item.unread').forEach(item => {
                        item.classList.remove('unread');
                    });

                    // Update items on notification page
                    document.querySelectorAll('.notification-list-item.unread').forEach(item => {
                        item.classList.remove('unread');
                        const dot = item.querySelector('.notification-list-unread-dot');
                        if (dot) dot.remove();
                    });

                    // Clear badge
                    updateBadge(0);
                }
            });
    };

    /**
     * Update the notification badge
     */
    function updateBadge(count) {
        const badge = getBadge();
        if (!badge) return;

        if (count > 0) {
            badge.textContent = count > 99 ? '99+' : count;
            badge.hidden = false;
        } else {
            badge.hidden = true;
        }
    }

    /**
     * Fetch and update badge count (called periodically)
     */
    window.updateNotificationBadge = function() {
        fetch('/api/notifications/count/')
            .then(response => response.json())
            .then(data => {
                updateBadge(data.unread_count);
            })
            .catch(error => {
                console.error('Failed to update notification count:', error);
            });
    };

    /**
     * Format time ago string
     */
    function formatTimeAgo(isoString) {
        const date = new Date(isoString);
        const now = new Date();
        const seconds = Math.floor((now - date) / 1000);

        if (seconds < 60) return 'Just now';
        if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
        if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
        if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;

        return date.toLocaleDateString();
    }

    /**
     * Escape HTML to prevent XSS
     */
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Get CSRF token
     */
    function getCsrfToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
               document.cookie.split('; ').find(row => row.startsWith('csrftoken='))?.split('=')[1] ||
               '';
    }

    /**
     * Initialize notification system
     */
    function init() {
        // Initial badge update
        updateNotificationBadge();

        // Refresh badge every 60 seconds
        refreshInterval = setInterval(updateNotificationBadge, 60000);

        // Close dropdown on Escape key
        document.addEventListener('keydown', function(event) {
            if (event.key === 'Escape' && isDropdownOpen) {
                closeDropdown();
            }
        });
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
