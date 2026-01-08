/**
 * Command Palette for Whole Life Journey
 *
 * A VS Code / Slack-style command palette that provides quick access to
 * navigation and common actions via Cmd/Ctrl+K.
 *
 * Features:
 * - Fuzzy search filtering
 * - Keyboard navigation (arrow keys, Enter)
 * - Mouse support
 * - Organized by categories
 */

(function() {
    'use strict';

    // Command palette state
    let isOpen = false;
    let selectedIndex = 0;
    let filteredCommands = [];

    // All available commands
    const COMMANDS = [
        // Navigation - Dashboard
        { id: 'nav-dashboard', title: 'Dashboard', category: 'Navigation', url: '/dashboard/', keywords: ['home', 'main', 'overview'] },

        // Navigation - Journal
        { id: 'nav-journal', title: 'Journal Home', category: 'Journal', url: '/journal/', keywords: ['entries', 'diary'] },
        { id: 'nav-journal-new', title: 'New Journal Entry', category: 'Journal', url: '/journal/entries/create/', keywords: ['create', 'write', 'add'] },
        { id: 'nav-journal-list', title: 'All Journal Entries', category: 'Journal', url: '/journal/entries/', keywords: ['list', 'browse'] },
        { id: 'nav-journal-book', title: 'Journal Book View', category: 'Journal', url: '/journal/book/', keywords: ['read', 'flip'] },
        { id: 'nav-journal-prompts', title: 'Journal Prompts', category: 'Journal', url: '/journal/prompts/', keywords: ['inspiration', 'ideas'] },
        { id: 'nav-journal-tags', title: 'Journal Tags', category: 'Journal', url: '/journal/tags/', keywords: ['labels', 'organize'] },

        // Navigation - Faith
        { id: 'nav-faith', title: 'Faith Home', category: 'Faith', url: '/faith/', keywords: ['spiritual', 'bible'] },
        { id: 'nav-faith-verse', title: "Today's Verse", category: 'Faith', url: '/faith/todays-verse/', keywords: ['scripture', 'daily'] },
        { id: 'nav-faith-plans', title: 'Reading Plans', category: 'Faith', url: '/faith/plans/', keywords: ['bible', 'study'] },
        { id: 'nav-faith-prayers', title: 'Prayers', category: 'Faith', url: '/faith/prayers/', keywords: ['pray', 'request'] },
        { id: 'nav-faith-milestones', title: 'Faith Milestones', category: 'Faith', url: '/faith/milestones/', keywords: ['achievements', 'growth'] },
        { id: 'nav-faith-reflections', title: 'Faith Reflections', category: 'Faith', url: '/faith/reflections/', keywords: ['thoughts', 'insights'] },

        // Navigation - Health
        { id: 'nav-health', title: 'Health Home', category: 'Health', url: '/health/', keywords: ['vitals', 'wellness'] },
        { id: 'nav-health-weight', title: 'Weight Tracking', category: 'Health', url: '/health/weight/', keywords: ['scale', 'pounds', 'kg'] },
        { id: 'nav-health-weight-new', title: 'Log Weight', category: 'Health', url: '/health/weight/create/', keywords: ['add', 'record'] },
        { id: 'nav-health-heartrate', title: 'Heart Rate', category: 'Health', url: '/health/heart-rate/', keywords: ['pulse', 'bpm'] },
        { id: 'nav-health-bp', title: 'Blood Pressure', category: 'Health', url: '/health/blood-pressure/', keywords: ['systolic', 'diastolic'] },
        { id: 'nav-health-glucose', title: 'Glucose', category: 'Health', url: '/health/glucose/', keywords: ['blood sugar', 'diabetes'] },
        { id: 'nav-health-medicine', title: "Today's Medicines", category: 'Health', url: '/health/medicine/', keywords: ['pills', 'medication', 'drugs'] },
        { id: 'nav-health-medicine-list', title: 'All Medicines', category: 'Health', url: '/health/medicine/list/', keywords: ['medications'] },
        { id: 'nav-health-fitness', title: 'Fitness Home', category: 'Health', url: '/health/fitness/', keywords: ['exercise', 'workout'] },
        { id: 'nav-health-workouts', title: 'Workouts', category: 'Health', url: '/health/fitness/workouts/', keywords: ['exercise', 'gym'] },
        { id: 'nav-health-nutrition', title: 'Nutrition Home', category: 'Health', url: '/health/nutrition/', keywords: ['food', 'diet', 'calories'] },
        { id: 'nav-health-food-log', title: 'Log Food', category: 'Health', url: '/health/nutrition/log/', keywords: ['meal', 'eat', 'add'] },

        // Navigation - Goals (Purpose)
        { id: 'nav-goals', title: 'Goals Home', category: 'Goals', url: '/purpose/', keywords: ['purpose', 'objectives'] },
        { id: 'nav-goals-yearly', title: 'Yearly Focus', category: 'Goals', url: '/purpose/directions/', keywords: ['annual', 'direction'] },
        { id: 'nav-goals-life', title: 'Life Goals', category: 'Goals', url: '/purpose/goals/', keywords: ['objectives', 'targets'] },
        { id: 'nav-goals-new', title: 'New Goal', category: 'Goals', url: '/purpose/goals/create/', keywords: ['add', 'create'] },
        { id: 'nav-goals-habits', title: 'Habit Goals', category: 'Goals', url: '/purpose/habits/', keywords: ['routines', 'daily'] },
        { id: 'nav-goals-intentions', title: 'Intentions', category: 'Goals', url: '/purpose/intentions/', keywords: ['plans', 'changes'] },
        { id: 'nav-goals-reflections', title: 'Goal Reflections', category: 'Goals', url: '/purpose/reflections/', keywords: ['review', 'progress'] },

        // Navigation - Organize (Life)
        { id: 'nav-life', title: 'Organize Home', category: 'Organize', url: '/life/', keywords: ['life', 'manage'] },
        { id: 'nav-life-calendar', title: 'Calendar', category: 'Organize', url: '/life/calendar/', keywords: ['schedule', 'events', 'dates'] },
        { id: 'nav-life-projects', title: 'Projects', category: 'Organize', url: '/life/projects/', keywords: ['work', 'tasks'] },
        { id: 'nav-life-tasks', title: 'Tasks', category: 'Organize', url: '/life/tasks/', keywords: ['todo', 'checklist'] },
        { id: 'nav-life-inventory', title: 'Inventory', category: 'Organize', url: '/life/inventory/', keywords: ['items', 'belongings'] },
        { id: 'nav-life-pets', title: 'Pets', category: 'Organize', url: '/life/pets/', keywords: ['animals', 'dogs', 'cats'] },
        { id: 'nav-life-recipes', title: 'Recipes', category: 'Organize', url: '/life/recipes/', keywords: ['cooking', 'food'] },
        { id: 'nav-life-maintenance', title: 'Maintenance', category: 'Organize', url: '/life/maintenance/', keywords: ['home', 'repairs'] },
        { id: 'nav-life-documents', title: 'Documents', category: 'Organize', url: '/life/documents/', keywords: ['files', 'papers'] },

        // Navigation - Finance
        { id: 'nav-finance', title: 'Finance Home', category: 'Finance', url: '/finance/', keywords: ['money', 'budget'] },
        { id: 'nav-finance-accounts', title: 'Accounts', category: 'Finance', url: '/finance/accounts/', keywords: ['bank', 'cards'] },
        { id: 'nav-finance-transactions', title: 'Transactions', category: 'Finance', url: '/finance/transactions/', keywords: ['spending', 'purchases'] },
        { id: 'nav-finance-budgets', title: 'Budgets', category: 'Finance', url: '/finance/budgets/', keywords: ['spending', 'limits'] },
        { id: 'nav-finance-goals', title: 'Financial Goals', category: 'Finance', url: '/finance/goals/', keywords: ['savings', 'targets'] },
        { id: 'nav-finance-metrics', title: 'Finance Metrics', category: 'Finance', url: '/finance/metrics/', keywords: ['stats', 'analytics'] },

        // Navigation - User
        { id: 'nav-profile', title: 'Profile', category: 'Account', url: '/users/profile/', keywords: ['settings', 'account'] },
        { id: 'nav-preferences', title: 'Preferences', category: 'Account', url: '/users/preferences/', keywords: ['settings', 'options'] },

        // Quick Actions
        { id: 'action-search', title: 'Search', category: 'Quick Actions', action: focusGlobalSearch, keywords: ['find', 'lookup'] },
        { id: 'action-help', title: 'Help', category: 'Quick Actions', action: openHelp, keywords: ['support', 'guide', 'how'] },
        { id: 'action-shortcuts', title: 'Keyboard Shortcuts', category: 'Quick Actions', action: showKeyboardShortcuts, keywords: ['keys', 'hotkeys'] },
    ];

    /**
     * Simple fuzzy match scoring
     */
    function fuzzyScore(query, text) {
        query = query.toLowerCase();
        text = text.toLowerCase();

        // Exact match gets highest score
        if (text === query) return 1000;

        // Starts with query gets high score
        if (text.startsWith(query)) return 100 + (query.length / text.length) * 50;

        // Contains query as substring
        if (text.includes(query)) return 50 + (query.length / text.length) * 25;

        // Fuzzy character matching
        let score = 0;
        let queryIndex = 0;
        let consecutiveBonus = 0;

        for (let i = 0; i < text.length && queryIndex < query.length; i++) {
            if (text[i] === query[queryIndex]) {
                score += 10 + consecutiveBonus;
                consecutiveBonus += 5;
                queryIndex++;
            } else {
                consecutiveBonus = 0;
            }
        }

        // Only count as match if all query characters were found
        if (queryIndex === query.length) {
            return score;
        }

        return 0;
    }

    /**
     * Filter and sort commands based on search query
     */
    function filterCommands(query) {
        if (!query || query.trim() === '') {
            // Show all commands grouped by category
            return COMMANDS.slice();
        }

        query = query.trim();

        // Score each command
        const scored = COMMANDS.map(cmd => {
            let maxScore = 0;

            // Score title
            maxScore = Math.max(maxScore, fuzzyScore(query, cmd.title));

            // Score category
            maxScore = Math.max(maxScore, fuzzyScore(query, cmd.category) * 0.5);

            // Score keywords
            if (cmd.keywords) {
                for (const keyword of cmd.keywords) {
                    maxScore = Math.max(maxScore, fuzzyScore(query, keyword) * 0.8);
                }
            }

            return { ...cmd, score: maxScore };
        });

        // Filter out zero scores and sort by score descending
        return scored
            .filter(cmd => cmd.score > 0)
            .sort((a, b) => b.score - a.score);
    }

    /**
     * Create the command palette DOM element
     */
    function createPaletteElement() {
        const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
        const modKey = isMac ? '⌘' : 'Ctrl';

        const palette = document.createElement('div');
        palette.id = 'command-palette';
        palette.className = 'command-palette';
        palette.hidden = true;

        palette.innerHTML = `
            <div class="command-palette-backdrop"></div>
            <div class="command-palette-container">
                <div class="command-palette-header">
                    <div class="command-palette-search-wrapper">
                        <svg class="command-palette-search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="11" cy="11" r="8"/>
                            <path d="M21 21l-4.35-4.35"/>
                        </svg>
                        <input
                            type="text"
                            class="command-palette-input"
                            placeholder="Type a command or search..."
                            autocomplete="off"
                            spellcheck="false"
                        >
                        <kbd class="command-palette-hint">${modKey}+K</kbd>
                    </div>
                </div>
                <div class="command-palette-results">
                    <div class="command-palette-list"></div>
                    <div class="command-palette-empty" hidden>
                        <p>No results found</p>
                    </div>
                </div>
                <div class="command-palette-footer">
                    <span><kbd>↑↓</kbd> Navigate</span>
                    <span><kbd>↵</kbd> Select</span>
                    <span><kbd>Esc</kbd> Close</span>
                </div>
            </div>
        `;

        return palette;
    }

    /**
     * Render the command list
     */
    function renderCommands(commands) {
        const list = document.querySelector('.command-palette-list');
        const empty = document.querySelector('.command-palette-empty');

        if (!list) return;

        if (commands.length === 0) {
            list.innerHTML = '';
            if (empty) empty.hidden = false;
            return;
        }

        if (empty) empty.hidden = true;

        // Group by category
        const grouped = {};
        for (const cmd of commands) {
            if (!grouped[cmd.category]) {
                grouped[cmd.category] = [];
            }
            grouped[cmd.category].push(cmd);
        }

        let html = '';
        let index = 0;

        for (const category of Object.keys(grouped)) {
            html += `<div class="command-palette-category">${category}</div>`;

            for (const cmd of grouped[category]) {
                const isSelected = index === selectedIndex ? 'selected' : '';
                html += `
                    <div class="command-palette-item ${isSelected}" data-index="${index}" data-id="${cmd.id}">
                        <span class="command-palette-item-title">${cmd.title}</span>
                    </div>
                `;
                index++;
            }
        }

        list.innerHTML = html;
        filteredCommands = commands;

        // Add click handlers
        list.querySelectorAll('.command-palette-item').forEach(item => {
            item.addEventListener('click', () => {
                const idx = parseInt(item.dataset.index, 10);
                executeCommand(filteredCommands[idx]);
            });
            item.addEventListener('mouseenter', () => {
                selectedIndex = parseInt(item.dataset.index, 10);
                updateSelection();
            });
        });
    }

    /**
     * Update the visual selection
     */
    function updateSelection() {
        const items = document.querySelectorAll('.command-palette-item');
        items.forEach((item, idx) => {
            item.classList.toggle('selected', idx === selectedIndex);
        });

        // Scroll selected item into view
        const selected = document.querySelector('.command-palette-item.selected');
        if (selected) {
            selected.scrollIntoView({ block: 'nearest' });
        }
    }

    /**
     * Execute a command
     */
    function executeCommand(cmd) {
        if (!cmd) return;

        closePalette();

        if (cmd.action && typeof cmd.action === 'function') {
            cmd.action();
        } else if (cmd.url) {
            window.location.href = cmd.url;
        }
    }

    /**
     * Open the command palette
     */
    function openPalette() {
        let palette = document.getElementById('command-palette');
        if (!palette) {
            palette = createPaletteElement();
            document.body.appendChild(palette);

            // Set up event listeners
            const backdrop = palette.querySelector('.command-palette-backdrop');
            backdrop.addEventListener('click', closePalette);

            const input = palette.querySelector('.command-palette-input');
            input.addEventListener('input', handleInput);
            input.addEventListener('keydown', handleKeydown);
        }

        palette.hidden = false;
        isOpen = true;
        selectedIndex = 0;

        // Reset and focus input
        const input = palette.querySelector('.command-palette-input');
        input.value = '';
        input.focus();

        // Show all commands initially
        renderCommands(filterCommands(''));

        // Prevent body scroll
        document.body.style.overflow = 'hidden';
    }

    /**
     * Close the command palette
     */
    function closePalette() {
        const palette = document.getElementById('command-palette');
        if (palette) {
            palette.hidden = true;
        }
        isOpen = false;

        // Restore body scroll
        document.body.style.overflow = '';
    }

    /**
     * Handle input changes
     */
    function handleInput(e) {
        const query = e.target.value;
        selectedIndex = 0;
        renderCommands(filterCommands(query));
    }

    /**
     * Handle keyboard navigation within the palette
     */
    function handleKeydown(e) {
        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                if (selectedIndex < filteredCommands.length - 1) {
                    selectedIndex++;
                    updateSelection();
                }
                break;

            case 'ArrowUp':
                e.preventDefault();
                if (selectedIndex > 0) {
                    selectedIndex--;
                    updateSelection();
                }
                break;

            case 'Enter':
                e.preventDefault();
                if (filteredCommands[selectedIndex]) {
                    executeCommand(filteredCommands[selectedIndex]);
                }
                break;

            case 'Escape':
                e.preventDefault();
                closePalette();
                break;
        }
    }

    /**
     * Global keyboard handler for Cmd/Ctrl+K
     */
    function handleGlobalKeydown(e) {
        // Cmd/Ctrl + K
        if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
            e.preventDefault();
            if (isOpen) {
                closePalette();
            } else {
                openPalette();
            }
        }

        // Escape when open
        if (e.key === 'Escape' && isOpen) {
            e.preventDefault();
            closePalette();
        }
    }

    // Quick action functions
    function focusGlobalSearch() {
        const searchInput = document.querySelector('#global-search, input[name="q"], input[type="search"], .search-input');
        if (searchInput) {
            searchInput.focus();
            searchInput.select();
        }
    }

    function openHelp() {
        if (typeof window.openHelpModal === 'function') {
            window.openHelpModal();
        }
    }

    function showKeyboardShortcuts() {
        if (typeof window.hideShortcutsModal === 'function') {
            // Toggle the shortcuts modal
            const modal = document.getElementById('keyboard-shortcuts-modal');
            if (modal && !modal.hidden) {
                window.hideShortcutsModal();
            } else {
                // Trigger the ? shortcut handler
                document.dispatchEvent(new KeyboardEvent('keydown', { key: '?' }));
            }
        }
    }

    // Add styles
    const styles = document.createElement('style');
    styles.textContent = `
        .command-palette {
            position: fixed;
            inset: 0;
            z-index: 9999;
            display: flex;
            align-items: flex-start;
            justify-content: center;
            padding-top: 15vh;
        }

        .command-palette[hidden] {
            display: none;
        }

        .command-palette-backdrop {
            position: absolute;
            inset: 0;
            background: rgba(0, 0, 0, 0.5);
            backdrop-filter: blur(2px);
        }

        .command-palette-container {
            position: relative;
            width: 100%;
            max-width: 580px;
            margin: 0 var(--space-4, 1rem);
            background: var(--color-background, #fff);
            border-radius: var(--radius-xl, 16px);
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25),
                        0 0 0 1px rgba(0, 0, 0, 0.05);
            overflow: hidden;
        }

        .command-palette-header {
            padding: var(--space-3, 0.75rem);
            border-bottom: 1px solid var(--color-border, #e5e5e5);
        }

        .command-palette-search-wrapper {
            display: flex;
            align-items: center;
            gap: var(--space-3, 0.75rem);
            padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem);
            background: var(--color-surface, #f5f5f5);
            border-radius: var(--radius-lg, 12px);
        }

        .command-palette-search-icon {
            width: 20px;
            height: 20px;
            color: var(--color-text-muted, #666);
            flex-shrink: 0;
        }

        .command-palette-input {
            flex: 1;
            border: none;
            background: transparent;
            font-size: var(--font-size-base, 1rem);
            color: var(--color-text, #333);
            outline: none;
        }

        .command-palette-input::placeholder {
            color: var(--color-text-muted, #999);
        }

        .command-palette-hint {
            font-size: var(--font-size-xs, 0.75rem);
            padding: var(--space-1, 0.25rem) var(--space-2, 0.5rem);
            background: var(--color-background, #fff);
            border: 1px solid var(--color-border, #e5e5e5);
            border-radius: var(--radius-sm, 4px);
            color: var(--color-text-muted, #666);
            flex-shrink: 0;
        }

        .command-palette-results {
            max-height: 400px;
            overflow-y: auto;
        }

        .command-palette-list {
            padding: var(--space-2, 0.5rem);
        }

        .command-palette-category {
            padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem);
            font-size: var(--font-size-xs, 0.75rem);
            font-weight: 600;
            color: var(--color-text-muted, #666);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .command-palette-item {
            display: flex;
            align-items: center;
            gap: var(--space-3, 0.75rem);
            padding: var(--space-3, 0.75rem);
            border-radius: var(--radius-md, 8px);
            cursor: pointer;
            transition: background-color 0.1s;
        }

        .command-palette-item:hover,
        .command-palette-item.selected {
            background: var(--color-surface, #f5f5f5);
        }

        .command-palette-item.selected {
            background: var(--color-accent, #4f46e5);
            color: white;
        }

        .command-palette-item-title {
            font-size: var(--font-size-sm, 0.875rem);
        }

        .command-palette-empty {
            padding: var(--space-8, 2rem);
            text-align: center;
            color: var(--color-text-muted, #666);
        }

        .command-palette-footer {
            display: flex;
            gap: var(--space-4, 1rem);
            padding: var(--space-3, 0.75rem) var(--space-4, 1rem);
            border-top: 1px solid var(--color-border, #e5e5e5);
            font-size: var(--font-size-xs, 0.75rem);
            color: var(--color-text-muted, #666);
        }

        .command-palette-footer kbd {
            display: inline-block;
            padding: 2px 6px;
            background: var(--color-surface, #f5f5f5);
            border: 1px solid var(--color-border, #e5e5e5);
            border-radius: var(--radius-sm, 4px);
            font-family: var(--font-mono, monospace);
            font-size: 0.65rem;
        }

        /* Dark mode support */
        @media (prefers-color-scheme: dark) {
            .command-palette-container {
                background: var(--color-background, #1a1a1a);
            }

            .command-palette-search-wrapper {
                background: var(--color-surface, #2a2a2a);
            }

            .command-palette-hint {
                background: var(--color-surface, #2a2a2a);
            }

            .command-palette-item:hover,
            .command-palette-item.selected {
                background: var(--color-surface, #2a2a2a);
            }

            .command-palette-item.selected {
                background: var(--color-accent, #4f46e5);
            }
        }
    `;
    document.head.appendChild(styles);

    // Initialize
    function init() {
        document.addEventListener('keydown', handleGlobalKeydown);

        // Expose functions globally for external use
        window.openCommandPalette = openPalette;
        window.closeCommandPalette = closePalette;
    }

    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
