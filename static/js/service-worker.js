/**
 * Whole Life Journey - Capture Service Worker
 *
 * Project: Whole Life Journey
 * Path: static/js/service-worker.js
 * Purpose: Background sync for audio capture uploads
 *
 * Description:
 *     This Service Worker handles background uploading of audio recordings
 *     when the user navigates away from the capture page. It processes the
 *     IndexedDB queue and uploads recordings even when the tab is closed.
 *
 * Key Responsibilities:
 *     - Background sync for pending audio uploads
 *     - Push notification display when uploads complete
 *     - Notification click handling for navigation
 *
 * Copyright:
 *     (c) Whole Life Journey. All rights reserved.
 *     This code is proprietary and may not be copied, modified, or distributed
 *     without explicit permission.
 */

const SW_VERSION = '1.0.0';
const DB_NAME = 'WLJCaptureQueue';
const DB_VERSION = 1;
const RECORDINGS_STORE = 'recordings';

// Upload configuration
const MAX_UPLOAD_ATTEMPTS = 5;
const RETRY_DELAYS = [2000, 5000, 15000, 30000, 60000]; // Generous backoff for weak cellular

/**
 * Service Worker Installation
 * Skip waiting to activate immediately
 */
self.addEventListener('install', (event) => {
    console.log('[SW] Installing Service Worker v' + SW_VERSION);
    self.skipWaiting();
});

/**
 * Service Worker Activation
 * Claim all clients to start controlling pages immediately
 */
self.addEventListener('activate', (event) => {
    console.log('[SW] Activating Service Worker v' + SW_VERSION);
    event.waitUntil(self.clients.claim());
});

/**
 * Background Sync Event Handler
 * Triggered when connectivity is restored or by periodic sync
 */
self.addEventListener('sync', (event) => {
    console.log('[SW] Sync event triggered:', event.tag);

    if (event.tag === 'capture-upload') {
        event.waitUntil(processUploadQueue());
    }
});

/**
 * Periodic Background Sync (if supported)
 * For browsers that support periodic background sync
 */
self.addEventListener('periodicsync', (event) => {
    console.log('[SW] Periodic sync event:', event.tag);

    if (event.tag === 'capture-upload-periodic') {
        event.waitUntil(processUploadQueue());
    }
});

/**
 * Push Notification Handler
 * Display notification when server sends push
 */
self.addEventListener('push', (event) => {
    console.log('[SW] Push notification received');

    let data = {
        title: 'Whole Life Journey',
        body: 'Your recording has been processed.',
        icon: '/static/icons/common/logo.svg',
        badge: '/static/icons/common/badge.png',
        tag: 'capture-notification',
        data: { url: '/capture/' }
    };

    if (event.data) {
        try {
            const payload = event.data.json();
            data = { ...data, ...payload };
        } catch (e) {
            // Use text if not JSON
            data.body = event.data.text() || data.body;
        }
    }

    event.waitUntil(
        self.registration.showNotification(data.title, {
            body: data.body,
            icon: data.icon,
            badge: data.badge,
            tag: data.tag,
            data: data.data,
            requireInteraction: false,
            actions: [
                { action: 'view', title: 'View Recording' },
                { action: 'dismiss', title: 'Dismiss' }
            ]
        })
    );
});

/**
 * Notification Click Handler
 * Navigate to the appropriate page when notification is clicked
 */
self.addEventListener('notificationclick', (event) => {
    console.log('[SW] Notification clicked:', event.action);

    event.notification.close();

    if (event.action === 'dismiss') {
        return;
    }

    const urlToOpen = event.notification.data?.url || '/capture/';

    event.waitUntil(
        self.clients.matchAll({ type: 'window', includeUncontrolled: true })
            .then((clientList) => {
                // Check if there's already a window open
                for (const client of clientList) {
                    if (client.url.includes(urlToOpen) && 'focus' in client) {
                        return client.focus();
                    }
                }
                // Open new window if none found
                if (self.clients.openWindow) {
                    return self.clients.openWindow(urlToOpen);
                }
            })
    );
});

/**
 * Message Handler
 * Handle messages from the main thread
 */
self.addEventListener('message', (event) => {
    console.log('[SW] Message received:', event.data);

    if (event.data?.type === 'PROCESS_QUEUE') {
        event.waitUntil(processUploadQueue());
    }

    if (event.data?.type === 'GET_VERSION') {
        event.ports[0]?.postMessage({ version: SW_VERSION });
    }
});

// ============================================================================
// IndexedDB Operations
// ============================================================================

/**
 * Open the capture queue database
 */
function openDatabase() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, DB_VERSION);

        request.onerror = () => {
            console.error('[SW] IndexedDB open error:', request.error);
            reject(request.error);
        };

        request.onsuccess = () => {
            resolve(request.result);
        };

        request.onupgradeneeded = (event) => {
            const db = event.target.result;
            if (!db.objectStoreNames.contains(RECORDINGS_STORE)) {
                const store = db.createObjectStore(RECORDINGS_STORE, { keyPath: 'clientId' });
                store.createIndex('status', 'uploadStatus', { unique: false });
                store.createIndex('createdAt', 'createdAt', { unique: false });
            }
        };
    });
}

/**
 * Get all pending recordings from IndexedDB
 */
async function getPendingRecordings() {
    try {
        const db = await openDatabase();
        const tx = db.transaction(RECORDINGS_STORE, 'readonly');
        const store = tx.objectStore(RECORDINGS_STORE);

        return new Promise((resolve) => {
            const recordings = [];
            const request = store.openCursor();

            request.onsuccess = (event) => {
                const cursor = event.target.result;
                if (cursor) {
                    const record = cursor.value;
                    // Only process pending or failed uploads
                    if (record.uploadStatus === 'pending' || record.uploadStatus === 'failed') {
                        recordings.push(record);
                    }
                    cursor.continue();
                } else {
                    db.close();
                    resolve(recordings);
                }
            };

            request.onerror = () => {
                db.close();
                resolve([]);
            };
        });
    } catch (error) {
        console.error('[SW] Error getting pending recordings:', error);
        return [];
    }
}

/**
 * Update a recording's status in IndexedDB
 */
async function updateRecordingStatus(clientId, updates) {
    try {
        const db = await openDatabase();
        const tx = db.transaction(RECORDINGS_STORE, 'readwrite');
        const store = tx.objectStore(RECORDINGS_STORE);

        return new Promise((resolve, reject) => {
            const getRequest = store.get(clientId);

            getRequest.onsuccess = () => {
                const record = getRequest.result;
                if (record) {
                    const updated = { ...record, ...updates };
                    const putRequest = store.put(updated);

                    putRequest.onsuccess = () => {
                        db.close();
                        resolve(updated);
                    };

                    putRequest.onerror = () => {
                        db.close();
                        reject(putRequest.error);
                    };
                } else {
                    db.close();
                    resolve(null);
                }
            };

            getRequest.onerror = () => {
                db.close();
                reject(getRequest.error);
            };
        });
    } catch (error) {
        console.error('[SW] Error updating recording:', error);
        throw error;
    }
}

/**
 * Delete a recording from IndexedDB
 */
async function deleteRecording(clientId) {
    try {
        const db = await openDatabase();
        const tx = db.transaction(RECORDINGS_STORE, 'readwrite');
        const store = tx.objectStore(RECORDINGS_STORE);

        return new Promise((resolve, reject) => {
            const request = store.delete(clientId);

            request.onsuccess = () => {
                db.close();
                resolve(true);
            };

            request.onerror = () => {
                db.close();
                reject(request.error);
            };
        });
    } catch (error) {
        console.error('[SW] Error deleting recording:', error);
        throw error;
    }
}

// ============================================================================
// Upload Processing
// ============================================================================

/**
 * Process the upload queue
 * Main function that handles background sync
 */
async function processUploadQueue() {
    console.log('[SW] Processing upload queue...');

    const recordings = await getPendingRecordings();

    if (recordings.length === 0) {
        console.log('[SW] No pending recordings to upload');
        return;
    }

    console.log(`[SW] Found ${recordings.length} pending recording(s)`);

    // Process recordings one at a time to avoid overwhelming the server
    for (const recording of recordings) {
        try {
            await processRecording(recording);
        } catch (error) {
            console.error(`[SW] Failed to process recording ${recording.clientId}:`, error);
        }
    }

    // Notify clients that processing is complete
    await notifyClients({ type: 'QUEUE_PROCESSED' });
}

/**
 * Process a single recording
 */
async function processRecording(recording) {
    const { clientId, audioData, mimeType, durationMs, uploadAttempts = 0 } = recording;

    console.log(`[SW] Processing recording ${clientId}, attempt ${uploadAttempts + 1}`);

    // Defer upload if offline — background sync will re-trigger when online
    if (!isOnline()) {
        console.log(`[SW] Offline, deferring upload for ${clientId}`);
        return;
    }

    // Check if max attempts reached
    if (uploadAttempts >= MAX_UPLOAD_ATTEMPTS) {
        console.log(`[SW] Max attempts reached for ${clientId}, marking as failed`);
        await updateRecordingStatus(clientId, {
            uploadStatus: 'failed',
            lastError: 'Max upload attempts reached'
        });
        return;
    }

    // Mark as uploading
    await updateRecordingStatus(clientId, {
        uploadStatus: 'uploading',
        uploadAttempts: uploadAttempts + 1
    });

    try {
        // Create blob from array buffer
        const blob = new Blob([audioData], { type: mimeType || 'audio/webm' });

        // Create form data
        const formData = new FormData();
        formData.append('audio', blob, `capture_${clientId}.webm`);
        formData.append('client_id', clientId);
        formData.append('duration_seconds', Math.round((durationMs || 0) / 1000));
        formData.append('is_partial', recording.isPartial ? 'true' : 'false');

        // Upload to CSRF-exempt Service Worker endpoint (session-authed)
        const response = await fetch('/capture/sw-upload/', {
            method: 'POST',
            body: formData,
            credentials: 'same-origin'
        });

        if (response.ok) {
            const data = await response.json();
            console.log(`[SW] Upload successful for ${clientId}:`, data);

            // Delete from IndexedDB
            await deleteRecording(clientId);

            // Show notification
            await showUploadSuccessNotification(data);

            // Update server-side PendingCapture status
            if (recording.serverId) {
                await updateServerStatus(recording.serverId, 'completed');
            }
        } else if (response.status === 401 || response.status === 403) {
            // Authentication error - don't retry, user needs to log in
            console.log(`[SW] Authentication error for ${clientId}, marking as failed`);
            await updateRecordingStatus(clientId, {
                uploadStatus: 'failed',
                lastError: 'Authentication required - please log in'
            });
        } else {
            throw new Error(`Upload failed with status ${response.status}`);
        }
    } catch (error) {
        console.error(`[SW] Upload error for ${clientId}:`, error);

        // Calculate retry delay
        const retryDelay = RETRY_DELAYS[uploadAttempts] || RETRY_DELAYS[RETRY_DELAYS.length - 1];

        await updateRecordingStatus(clientId, {
            uploadStatus: 'failed',
            lastError: error.message
        });

        // If not at max attempts, schedule retry
        if (uploadAttempts + 1 < MAX_UPLOAD_ATTEMPTS) {
            console.log(`[SW] Scheduling retry for ${clientId} in ${retryDelay}ms`);
            setTimeout(() => {
                processRecording({ ...recording, uploadAttempts: uploadAttempts + 1 });
            }, retryDelay);
        }
    }
}

/**
 * Update server-side PendingCapture status
 */
async function updateServerStatus(serverId, status) {
    try {
        await fetch(`/capture/pending/${serverId}/status/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ status }),
            credentials: 'same-origin'
        });
    } catch (error) {
        console.error('[SW] Failed to update server status:', error);
    }
}

/**
 * Show notification when upload succeeds
 */
async function showUploadSuccessNotification(data) {
    try {
        // Check if notifications are permitted
        if (self.registration.showNotification) {
            await self.registration.showNotification('Recording Ready', {
                body: 'Your recording has been processed and is ready to view.',
                icon: '/static/icons/common/logo.svg',
                badge: '/static/icons/common/badge.png',
                tag: 'capture-success-' + (data.id || Date.now()),
                data: {
                    url: data.redirect_url || '/capture/'
                },
                requireInteraction: false,
                actions: [
                    { action: 'view', title: 'View' },
                    { action: 'dismiss', title: 'Dismiss' }
                ]
            });
        }
    } catch (error) {
        console.error('[SW] Failed to show notification:', error);
    }
}

/**
 * Notify all connected clients
 */
async function notifyClients(message) {
    const clients = await self.clients.matchAll({ type: 'window' });
    for (const client of clients) {
        client.postMessage(message);
    }
}

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Check if we're online
 */
function isOnline() {
    return self.navigator?.onLine !== false;
}

console.log('[SW] Service Worker loaded v' + SW_VERSION);
