/**
 * Whole Life Journey - Biometric Login (WebAuthn)
 *
 * Project: Whole Life Journey
 * Path: static/js/biometric.js
 * Purpose: WebAuthn-based biometric authentication (Face ID, Touch ID, Windows Hello)
 *
 * Description:
 *     Enables passwordless login using device biometrics through the Web Authentication
 *     API (WebAuthn). Supports Face ID on iOS, Touch ID on Mac, Windows Hello, and
 *     other platform authenticators.
 *
 * Key Features:
 *     - Device capability detection
 *     - Credential registration flow (linking device to account)
 *     - Authentication flow (passwordless login)
 *     - Base64URL encoding/decoding for WebAuthn data
 *
 * Security Notes:
 *     - Biometric data NEVER leaves the device
 *     - Only cryptographic signatures are sent to server
 *     - Uses public key cryptography for verification
 *     - Credential IDs are device-specific
 *
 * Browser Support:
 *     - Chrome 67+, Firefox 60+, Safari 13+, Edge 79+
 *     - Requires HTTPS (except localhost)
 *
 * Dependencies:
 *     - Web Authentication API (navigator.credentials)
 *     - Server endpoints at /user/biometric/*
 *
 * Copyright:
 *     (c) Whole Life Journey. All rights reserved.
 *     This code is proprietary and may not be copied, modified, or distributed
 *     without explicit permission.
 */

(function() {
    'use strict';

    // Base64URL encoding/decoding utilities
    function base64UrlEncode(buffer) {
        const bytes = new Uint8Array(buffer);
        let str = '';
        for (const byte of bytes) {
            str += String.fromCharCode(byte);
        }
        return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    }

    function base64UrlDecode(str) {
        str = str.replace(/-/g, '+').replace(/_/g, '/');
        while (str.length % 4) {
            str += '=';
        }
        const binary = atob(str);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
            bytes[i] = binary.charCodeAt(i);
        }
        return bytes.buffer;
    }

    // Check if WebAuthn is available
    function isWebAuthnAvailable() {
        return window.PublicKeyCredential !== undefined &&
               typeof window.PublicKeyCredential === 'function';
    }

    // Check if platform authenticator (Face ID, Touch ID, etc.) is available
    async function isPlatformAuthenticatorAvailable() {
        if (!isWebAuthnAvailable()) return false;
        try {
            return await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
        } catch (e) {
            console.error('Error checking platform authenticator:', e);
            return false;
        }
    }

    // Get CSRF token from cookie
    function getCsrfToken() {
        const name = 'csrftoken';
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            cookie = cookie.trim();
            if (cookie.startsWith(name + '=')) {
                return cookie.substring(name.length + 1);
            }
        }
        // Fallback: get from form input
        const csrfInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
        return csrfInput ? csrfInput.value : '';
    }

    // Register a new biometric credential
    async function registerCredential() {
        const statusEl = document.getElementById('biometric-status-message');
        const registerBtn = document.getElementById('register-biometric-btn');

        try {
            statusEl.style.display = 'block';
            statusEl.className = 'text-sm mt-2 text-muted';
            statusEl.textContent = 'Requesting registration options...';
            registerBtn.disabled = true;

            // Get registration options from server
            const optionsResponse = await fetch('/user/biometric/register/begin/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
            });

            if (!optionsResponse.ok) {
                throw new Error('Failed to get registration options');
            }

            const options = await optionsResponse.json();

            // Convert base64url fields to ArrayBuffer
            options.challenge = base64UrlDecode(options.challenge);
            options.user.id = base64UrlDecode(options.user.id);
            if (options.excludeCredentials) {
                options.excludeCredentials = options.excludeCredentials.map(cred => ({
                    ...cred,
                    id: base64UrlDecode(cred.id),
                }));
            }

            statusEl.textContent = 'Please authenticate with your device...';

            // Create credential using platform authenticator
            const credential = await navigator.credentials.create({
                publicKey: options,
            });

            statusEl.textContent = 'Verifying registration...';

            // Prepare credential for server
            const credentialData = {
                id: credential.id,
                rawId: base64UrlEncode(credential.rawId),
                type: credential.type,
                response: {
                    attestationObject: base64UrlEncode(credential.response.attestationObject),
                    clientDataJSON: base64UrlEncode(credential.response.clientDataJSON),
                },
            };

            // Get device name for identification
            const deviceName = getDeviceName();
            credentialData.deviceName = deviceName;

            // Send credential to server for verification and storage
            const verifyResponse = await fetch('/user/biometric/register/complete/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
                body: JSON.stringify(credentialData),
            });

            if (!verifyResponse.ok) {
                const error = await verifyResponse.json();
                throw new Error(error.error || 'Registration failed');
            }

            const result = await verifyResponse.json();

            statusEl.className = 'text-sm mt-2 text-success';
            statusEl.style.color = 'var(--color-success, #10b981)';
            statusEl.textContent = 'Biometric login enabled! You can now use Face ID or Touch ID to sign in.';

            // Update UI
            document.getElementById('biometric-setup-section').style.display = 'none';
            document.getElementById('biometric_toggle').checked = true;

            // Reload to show updated status
            setTimeout(() => {
                window.location.reload();
            }, 1500);

        } catch (error) {
            console.error('Registration error:', error);
            statusEl.className = 'text-sm mt-2';
            statusEl.style.color = 'var(--color-error, #ef4444)';

            if (error.name === 'NotAllowedError') {
                statusEl.textContent = 'Registration cancelled. Please try again when ready.';
            } else if (error.name === 'InvalidStateError') {
                statusEl.textContent = 'This device is already registered. Please remove it first.';
            } else {
                statusEl.textContent = `Registration failed: ${error.message}`;
            }
        } finally {
            registerBtn.disabled = false;
        }
    }

    // Authenticate using biometric credential
    async function authenticateWithBiometric() {
        const statusEl = document.getElementById('biometric-login-status');
        const loginBtn = document.getElementById('biometric-login-btn');

        try {
            if (statusEl) {
                statusEl.style.display = 'block';
                statusEl.className = 'text-sm mt-2 text-muted';
                statusEl.textContent = 'Preparing authentication...';
            }
            if (loginBtn) loginBtn.disabled = true;

            // Get authentication options from server
            const optionsResponse = await fetch('/user/biometric/login/begin/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
            });

            if (!optionsResponse.ok) {
                const error = await optionsResponse.json();
                throw new Error(error.error || 'Failed to get authentication options');
            }

            const options = await optionsResponse.json();

            // Convert base64url fields to ArrayBuffer
            options.challenge = base64UrlDecode(options.challenge);
            if (options.allowCredentials) {
                options.allowCredentials = options.allowCredentials.map(cred => ({
                    ...cred,
                    id: base64UrlDecode(cred.id),
                }));
            }

            if (statusEl) {
                statusEl.textContent = 'Please authenticate with your device...';
            }

            // Get credential
            const credential = await navigator.credentials.get({
                publicKey: options,
            });

            if (statusEl) {
                statusEl.textContent = 'Verifying...';
            }

            // Prepare assertion for server
            const assertionData = {
                id: credential.id,
                rawId: base64UrlEncode(credential.rawId),
                type: credential.type,
                response: {
                    authenticatorData: base64UrlEncode(credential.response.authenticatorData),
                    clientDataJSON: base64UrlEncode(credential.response.clientDataJSON),
                    signature: base64UrlEncode(credential.response.signature),
                },
            };

            if (credential.response.userHandle) {
                assertionData.response.userHandle = base64UrlEncode(credential.response.userHandle);
            }

            // Send assertion to server for verification
            const verifyResponse = await fetch('/user/biometric/login/complete/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
                body: JSON.stringify(assertionData),
            });

            if (!verifyResponse.ok) {
                const error = await verifyResponse.json();
                throw new Error(error.error || 'Authentication failed');
            }

            const result = await verifyResponse.json();

            if (statusEl) {
                statusEl.className = 'text-sm mt-2 text-success';
                statusEl.style.color = 'var(--color-success, #10b981)';
                statusEl.textContent = 'Authentication successful! Redirecting...';
            }

            // Redirect to dashboard or specified URL
            window.location.href = result.redirect || '/dashboard/';

        } catch (error) {
            console.error('Authentication error:', error);

            if (statusEl) {
                statusEl.className = 'text-sm mt-2';
                statusEl.style.color = 'var(--color-error, #ef4444)';

                if (error.name === 'NotAllowedError') {
                    statusEl.textContent = 'Authentication cancelled. Please try again.';
                } else {
                    statusEl.textContent = `Authentication failed: ${error.message}`;
                }
            }
        } finally {
            if (loginBtn) loginBtn.disabled = false;
        }
    }

    // Get friendly device name
    function getDeviceName() {
        const ua = navigator.userAgent;

        // iOS devices
        if (/iPhone/.test(ua)) {
            return 'iPhone';
        } else if (/iPad/.test(ua)) {
            return 'iPad';
        }
        // Android
        else if (/Android/.test(ua)) {
            const match = ua.match(/Android[^;]+;\s*([^)]+)/);
            if (match) {
                return match[1].split(' Build')[0].trim();
            }
            return 'Android Device';
        }
        // Desktop
        else if (/Macintosh/.test(ua)) {
            return 'Mac';
        } else if (/Windows/.test(ua)) {
            return 'Windows PC';
        } else if (/Linux/.test(ua)) {
            return 'Linux PC';
        }

        return 'Unknown Device';
    }

    // Initialize biometric UI on preferences page
    async function initPreferencesPage() {
        const biometricOption = document.getElementById('biometric-option');
        const biometricToggle = document.getElementById('biometric_toggle');
        const setupSection = document.getElementById('biometric-setup-section');
        const supportStatus = document.getElementById('biometric-support-status');
        const registerBtn = document.getElementById('register-biometric-btn');

        if (!biometricOption) return; // Not on preferences page

        // Check browser support
        if (!isWebAuthnAvailable()) {
            biometricOption.classList.add('disabled');
            supportStatus.textContent = '(Not supported in this browser)';
            biometricToggle.disabled = true;
            return;
        }

        // Check platform authenticator availability
        const platformAvailable = await isPlatformAuthenticatorAvailable();

        if (!platformAvailable) {
            supportStatus.textContent = '(Biometric not available on this device)';
            biometricToggle.disabled = true;
            return;
        }

        supportStatus.textContent = ''; // Clear status if supported

        // Handle toggle changes
        biometricToggle.addEventListener('change', function() {
            if (this.checked) {
                // Show setup section when enabling
                setupSection.style.display = 'block';
            } else {
                // Hide setup section when disabling
                setupSection.style.display = 'none';
            }
        });

        // Handle registration button
        if (registerBtn) {
            registerBtn.addEventListener('click', function(e) {
                e.preventDefault();
                registerCredential();
            });
        }

        // Show setup if toggle is on but no credentials
        if (biometricToggle.checked) {
            // Check if user has any credentials
            try {
                const response = await fetch('/user/biometric/credentials/', {
                    headers: {
                        'X-CSRFToken': getCsrfToken(),
                    },
                });
                const data = await response.json();

                if (!data.credentials || data.credentials.length === 0) {
                    setupSection.style.display = 'block';
                } else {
                    // Show list of registered devices
                    showRegisteredDevices(data.credentials);
                }
            } catch (e) {
                console.error('Error checking credentials:', e);
            }
        }
    }

    // Show list of registered devices
    function showRegisteredDevices(credentials) {
        const listEl = document.getElementById('biometric-credentials-list');
        if (!listEl || !credentials.length) return;

        listEl.style.display = 'block';
        listEl.innerHTML = '<h5 class="text-sm font-semibold mb-2">Registered Devices:</h5>';

        const list = document.createElement('ul');
        list.className = 'list-disc list-inside text-sm text-muted';

        credentials.forEach(cred => {
            const li = document.createElement('li');
            li.textContent = `${cred.device_name || 'Unknown Device'} (added ${new Date(cred.created_at).toLocaleDateString()})`;
            list.appendChild(li);
        });

        listEl.appendChild(list);
    }

    // Initialize biometric login button on login page
    async function initLoginPage() {
        const loginForm = document.querySelector('form[action*="login"]');
        if (!loginForm) return; // Not on login page

        // Check if biometric is supported and any credentials exist
        if (!isWebAuthnAvailable()) return;

        const platformAvailable = await isPlatformAuthenticatorAvailable();
        if (!platformAvailable) return;

        // Check if there are any biometric credentials for login
        try {
            const response = await fetch('/user/biometric/check/');
            const data = await response.json();

            if (!data.available) return;

            // Add biometric login button
            const biometricSection = document.createElement('div');
            biometricSection.className = 'biometric-login-section mt-4 pt-4 border-t';
            biometricSection.innerHTML = `
                <div class="text-center">
                    <p class="text-muted text-sm mb-3">Or sign in with biometrics</p>
                    <button type="button" id="biometric-login-btn" class="btn btn-secondary">
                        <span class="biometric-icon">🔐</span>
                        Use Face ID / Touch ID
                    </button>
                    <p id="biometric-login-status" class="text-sm mt-2" style="display: none;"></p>
                </div>
            `;

            // Insert after the form
            loginForm.parentNode.insertBefore(biometricSection, loginForm.nextSibling);

            // Add click handler
            document.getElementById('biometric-login-btn').addEventListener('click', function(e) {
                e.preventDefault();
                authenticateWithBiometric();
            });

        } catch (e) {
            console.error('Error checking biometric availability:', e);
        }
    }

    // Initialize on page load
    document.addEventListener('DOMContentLoaded', function() {
        // Check which page we're on and initialize appropriately
        if (document.getElementById('biometric-option')) {
            initPreferencesPage();
        } else if (document.querySelector('form[action*="login"]') ||
                   window.location.pathname.includes('/login')) {
            initLoginPage();
        }
    });

    // Export for external use
    window.BiometricAuth = {
        isAvailable: isWebAuthnAvailable,
        isPlatformAvailable: isPlatformAuthenticatorAvailable,
        register: registerCredential,
        authenticate: authenticateWithBiometric,
    };

})();
