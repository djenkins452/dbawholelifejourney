/**
 * Speech-to-Text and Spell Check Enhancement
 * Whole Life Journey
 * 
 * Adds voice input and spell check to all free-form text fields.
 * Include this script in base.html to enable across the application.
 */

(function() {
    'use strict';

    // Check for browser support
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const hasSpeechSupport = !!SpeechRecognition;

    // Configuration
    const CONFIG = {
        // Selectors for text fields that should get speech-to-text
        textFieldSelectors: [
            'textarea',
            'input[type="text"]',
            'input:not([type])'  // inputs without type default to text
        ],
        // Exclude these fields from speech-to-text
        excludeSelectors: [
            'input[type="email"]',
            'input[type="password"]',
            'input[type="number"]',
            'input[type="date"]',
            'input[type="time"]',
            'input[type="url"]',
            'input[type="tel"]',
            'input[type="search"]',
            'input[name="username"]',
            'input[name="csrfmiddlewaretoken"]',
            '[data-no-speech]'
        ],
        // Language for speech recognition
        language: 'en-US',
        // Continuous mode (keep listening until stopped)
        continuous: true,
        // Interim results (show results as user speaks)
        interimResults: true
    };

    /**
     * Initialize speech-to-text for a text field
     */
    function initSpeechToText(field) {
        if (!hasSpeechSupport) return;
        if (field.dataset.speechInitialized) return;
        
        // Check if field should be excluded
        for (const selector of CONFIG.excludeSelectors) {
            if (field.matches(selector)) return;
        }

        field.dataset.speechInitialized = 'true';

        // Create the microphone button
        const micButton = document.createElement('button');
        micButton.type = 'button';
        micButton.className = 'speech-btn';
        micButton.title = 'Click to speak';
        micButton.setAttribute('aria-label', 'Voice input');
        micButton.innerHTML = `
            <svg class="mic-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
                <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
                <line x1="12" y1="19" x2="12" y2="23"/>
                <line x1="8" y1="23" x2="16" y2="23"/>
            </svg>
            <svg class="mic-icon-active" viewBox="0 0 24 24" fill="currentColor" stroke="none">
                <rect x="9" y="2" width="6" height="12" rx="3"/>
                <path d="M19 10v2a7 7 0 0 1-14 0v-2" fill="none" stroke="currentColor" stroke-width="2"/>
                <line x1="12" y1="19" x2="12" y2="23" stroke="currentColor" stroke-width="2"/>
                <line x1="8" y1="23" x2="16" y2="23" stroke="currentColor" stroke-width="2"/>
            </svg>
        `;

        // Wrap the field if needed for positioning
        let wrapper = field.parentElement;
        if (!wrapper.classList.contains('speech-field-wrapper')) {
            wrapper = document.createElement('div');
            wrapper.className = 'speech-field-wrapper';
            field.parentNode.insertBefore(wrapper, field);
            wrapper.appendChild(field);
        }
        wrapper.appendChild(micButton);

        // Speech recognition instance
        let recognition = null;
        let isListening = false;
        let finalTranscript = '';

        micButton.addEventListener('click', function(e) {
            e.preventDefault();
            
            if (isListening) {
                stopListening();
            } else {
                startListening();
            }
        });

        function startListening() {
            recognition = new SpeechRecognition();
            recognition.lang = CONFIG.language;
            recognition.continuous = CONFIG.continuous;
            recognition.interimResults = CONFIG.interimResults;

            finalTranscript = '';

            recognition.onstart = function() {
                isListening = true;
                micButton.classList.add('listening');
                field.classList.add('speech-active');
                field.placeholder = field.dataset.originalPlaceholder || field.placeholder;
                field.dataset.originalPlaceholder = field.placeholder;
            };

            recognition.onresult = function(event) {
                let interimTranscript = '';
                
                for (let i = event.resultIndex; i < event.results.length; i++) {
                    const transcript = event.results[i][0].transcript;
                    if (event.results[i].isFinal) {
                        finalTranscript += transcript + ' ';
                    } else {
                        interimTranscript += transcript;
                    }
                }

                // Get current cursor position or end of text
                const cursorPos = field.selectionStart || field.value.length;
                const textBefore = field.value.substring(0, cursorPos);
                const textAfter = field.value.substring(cursorPos);
                
                // For textarea, append; for input, replace or append based on content
                if (field.tagName === 'TEXTAREA') {
                    // Add space if needed
                    const needsSpace = textBefore.length > 0 && !textBefore.endsWith(' ') && !textBefore.endsWith('\n');
                    const spacer = needsSpace ? ' ' : '';
                    field.value = textBefore + spacer + finalTranscript + interimTranscript + textAfter;
                } else {
                    // For input fields, append to existing
                    const needsSpace = textBefore.length > 0 && !textBefore.endsWith(' ');
                    const spacer = needsSpace ? ' ' : '';
                    field.value = textBefore + spacer + finalTranscript + interimTranscript;
                }

                // Trigger input event for any listeners
                field.dispatchEvent(new Event('input', { bubbles: true }));
            };

            recognition.onerror = function(event) {
                console.warn('Speech recognition error:', event.error);
                if (event.error === 'not-allowed') {
                    alert('Microphone access denied. Please allow microphone access in your browser settings.');
                }
                stopListening();
            };

            recognition.onend = function() {
                if (isListening) {
                    // Restart if user hasn't stopped manually
                    try {
                        recognition.start();
                    } catch (e) {
                        stopListening();
                    }
                }
            };

            try {
                recognition.start();
            } catch (e) {
                console.error('Failed to start speech recognition:', e);
            }
        }

        function stopListening() {
            isListening = false;
            micButton.classList.remove('listening');
            field.classList.remove('speech-active');
            
            if (recognition) {
                recognition.stop();
                recognition = null;
            }

            // Clean up any trailing spaces
            field.value = field.value.trim();
            field.dispatchEvent(new Event('input', { bubbles: true }));
            field.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }

    /**
     * Enable spell check on a text field
     */
    function enableSpellCheck(field) {
        if (field.dataset.spellcheckInitialized) return;
        
        // Check if field should be excluded
        for (const selector of CONFIG.excludeSelectors) {
            if (field.matches(selector)) return;
        }

        field.dataset.spellcheckInitialized = 'true';
        
        // Enable browser spell check
        field.setAttribute('spellcheck', 'true');
        
        // For better spell check support
        field.setAttribute('autocomplete', 'on');
        field.setAttribute('autocorrect', 'on');
        field.setAttribute('autocapitalize', 'sentences');
    }

    /**
     * Initialize all text fields on the page
     */
    function initAllFields() {
        const selector = CONFIG.textFieldSelectors.join(', ');
        const fields = document.querySelectorAll(selector);
        
        fields.forEach(field => {
            // Skip hidden fields
            if (field.type === 'hidden') return;
            
            // Skip fields in certain containers
            if (field.closest('[data-no-enhancements]')) return;
            
            enableSpellCheck(field);
            initSpeechToText(field);
        });
    }

    /**
     * Observe DOM for dynamically added fields
     */
    function observeDOM() {
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                mutation.addedNodes.forEach(function(node) {
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        // Check if the added node is a text field
                        if (node.matches && CONFIG.textFieldSelectors.some(sel => node.matches(sel))) {
                            enableSpellCheck(node);
                            initSpeechToText(node);
                        }
                        // Check children
                        const selector = CONFIG.textFieldSelectors.join(', ');
                        const fields = node.querySelectorAll ? node.querySelectorAll(selector) : [];
                        fields.forEach(field => {
                            enableSpellCheck(field);
                            initSpeechToText(field);
                        });
                    }
                });
            });
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    }

    /**
     * Add CSS styles
     */
    function addStyles() {
        const styles = document.createElement('style');
        styles.textContent = `
            /* Speech-to-text wrapper */
            .speech-field-wrapper {
                position: relative;
                display: inline-block;
                width: 100%;
            }
            
            .speech-field-wrapper textarea,
            .speech-field-wrapper input[type="text"],
            .speech-field-wrapper input:not([type]) {
                padding-right: 40px;
                width: 100%;
                box-sizing: border-box;
            }
            
            /* Microphone button */
            .speech-btn {
                position: absolute;
                right: 8px;
                top: 50%;
                transform: translateY(-50%);
                width: 28px;
                height: 28px;
                padding: 4px;
                border: none;
                background: transparent;
                cursor: pointer;
                border-radius: var(--radius-sm, 4px);
                color: var(--color-text-muted, #6b7280);
                transition: all 0.2s ease;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            
            /* Position adjustment for textareas */
            .speech-field-wrapper:has(textarea) .speech-btn {
                top: 12px;
                transform: none;
            }
            
            .speech-btn:hover {
                background: var(--color-surface, #f3f4f6);
                color: var(--color-accent, #6366f1);
            }
            
            .speech-btn:focus {
                outline: 2px solid var(--color-accent, #6366f1);
                outline-offset: 2px;
            }
            
            .speech-btn .mic-icon {
                width: 18px;
                height: 18px;
                display: block;
            }
            
            .speech-btn .mic-icon-active {
                width: 18px;
                height: 18px;
                display: none;
                color: var(--color-error, #ef4444);
            }
            
            /* Listening state */
            .speech-btn.listening {
                background: var(--color-error, #ef4444);
                color: white;
                animation: pulse 1.5s infinite;
            }
            
            .speech-btn.listening .mic-icon {
                display: none;
            }
            
            .speech-btn.listening .mic-icon-active {
                display: block;
                color: white;
            }
            
            .speech-active {
                border-color: var(--color-error, #ef4444) !important;
                box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.1) !important;
            }
            
            @keyframes pulse {
                0%, 100% {
                    opacity: 1;
                }
                50% {
                    opacity: 0.7;
                }
            }
            
            /* Spell check visual feedback */
            textarea[spellcheck="true"]:focus,
            input[type="text"][spellcheck="true"]:focus {
                /* Browser will show red underlines for misspelled words */
            }
            
            /* No speech support message */
            .no-speech-support .speech-btn {
                display: none;
            }
            
            /* Mobile adjustments */
            @media (max-width: 640px) {
                .speech-btn {
                    width: 32px;
                    height: 32px;
                }
                
                .speech-field-wrapper textarea,
                .speech-field-wrapper input[type="text"] {
                    padding-right: 44px;
                }
            }
        `;
        document.head.appendChild(styles);
    }

    /**
     * Show speech support notice
     */
    function checkSpeechSupport() {
        if (!hasSpeechSupport) {
            document.body.classList.add('no-speech-support');
            console.info('Speech recognition not supported in this browser. Voice input will be disabled.');
        }
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    function init() {
        addStyles();
        checkSpeechSupport();
        initAllFields();
        observeDOM();
    }

    // Expose API for manual initialization if needed
    window.SpeechEnhancement = {
        init: initAllFields,
        initField: function(field) {
            enableSpellCheck(field);
            initSpeechToText(field);
        },
        isSupported: hasSpeechSupport
    };

})();
