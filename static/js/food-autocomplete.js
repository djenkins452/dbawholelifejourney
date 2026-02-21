/**
 * Food Autocomplete with Auto-Fill
 *
 * Provides autocomplete suggestions for food entries with automatic
 * nutrition field population when a food is selected.
 *
 * Features:
 * - Debounced search (300ms delay)
 * - 3-tier data sources: Local DB, FatSecret API, AI estimation
 * - Keyboard navigation (arrows, enter, escape)
 * - Auto-fills all nutrition fields on selection
 * - Visual feedback for auto-filled fields
 * - Source badge display (Local/FatSecret/AI)
 */

(function() {
    'use strict';

    // Configuration
    const DEBOUNCE_MS = 300;
    const MIN_QUERY_LENGTH = 2;
    const API_URL = '/health/physical/nutrition/api/search/';

    // State
    let debounceTimer = null;
    let selectedIndex = -1;
    let currentResults = [];
    let isLoading = false;

    // Per-serving snapshot (stored when food is selected, used for quantity scaling)
    let perServingSnapshot = null;

    /**
     * Initialize autocomplete on a food name input
     */
    function initFoodAutocomplete(inputElement) {
        if (!inputElement) return;

        // Don't initialize twice
        if (inputElement.dataset.autocompleteInit === 'true') return;
        inputElement.dataset.autocompleteInit = 'true';

        // Create dropdown container
        const dropdown = createDropdown(inputElement);

        // Input event handlers
        inputElement.addEventListener('input', (e) => handleInput(e, dropdown, inputElement));
        inputElement.addEventListener('keydown', (e) => handleKeydown(e, dropdown, inputElement));
        inputElement.addEventListener('focus', (e) => handleFocus(e, dropdown));

        // Click outside to close
        document.addEventListener('click', (e) => {
            if (!inputElement.contains(e.target) && !dropdown.contains(e.target)) {
                hideDropdown(dropdown);
            }
        });

        // Quantity change → recalculate totals preview
        const form = inputElement.closest('form');
        if (form) {
            const qtyField = form.querySelector('[name="quantity"]');
            if (qtyField) {
                qtyField.addEventListener('input', () => recalculateTotals(form));
                qtyField.addEventListener('change', () => recalculateTotals(form));
            }
        }
    }

    /**
     * Create the autocomplete dropdown element
     */
    function createDropdown(inputElement) {
        const dropdown = document.createElement('div');
        dropdown.className = 'food-autocomplete-dropdown';
        dropdown.hidden = true;

        // Position relative to input
        const wrapper = document.createElement('div');
        wrapper.className = 'food-autocomplete-wrapper';
        wrapper.style.position = 'relative';

        inputElement.parentNode.insertBefore(wrapper, inputElement);
        wrapper.appendChild(inputElement);
        wrapper.appendChild(dropdown);

        return dropdown;
    }

    /**
     * Handle input changes with debouncing
     */
    function handleInput(event, dropdown, inputElement) {
        clearTimeout(debounceTimer);
        const query = event.target.value.trim();

        if (query.length < MIN_QUERY_LENGTH) {
            hideDropdown(dropdown);
            return;
        }

        // Show loading state
        showLoading(dropdown);

        debounceTimer = setTimeout(() => searchFoods(query, dropdown, inputElement), DEBOUNCE_MS);
    }

    /**
     * Show loading indicator
     */
    function showLoading(dropdown) {
        isLoading = true;
        dropdown.innerHTML = `
            <div class="food-autocomplete-loading">
                <span class="spinner"></span> Searching...
            </div>
        `;
        dropdown.hidden = false;
    }

    /**
     * Search for foods via API
     */
    async function searchFoods(query, dropdown, inputElement) {
        try {
            const response = await fetch(`${API_URL}?q=${encodeURIComponent(query)}`);
            const data = await response.json();

            isLoading = false;
            currentResults = data.results || [];
            selectedIndex = -1;

            renderResults(dropdown, currentResults, query, inputElement);
        } catch (error) {
            console.error('Food search error:', error);
            isLoading = false;
            hideDropdown(dropdown);
        }
    }

    /**
     * Render search results in dropdown
     */
    function renderResults(dropdown, results, query, inputElement) {
        if (results.length === 0) {
            dropdown.innerHTML = `
                <div class="food-autocomplete-empty">
                    No matches found for "${escapeHtml(query)}"
                </div>
            `;
            dropdown.hidden = false;
            return;
        }

        let html = results.map((food, index) => `
            <div class="food-autocomplete-item ${index === selectedIndex ? 'selected' : ''}"
                 data-index="${index}">
                <div class="food-autocomplete-header">
                    <span class="food-autocomplete-name">
                        ${escapeHtml(food.name)}
                        ${food.brand ? `<span class="food-autocomplete-brand">(${escapeHtml(food.brand)})</span>` : ''}
                    </span>
                    <span class="food-autocomplete-source food-autocomplete-source-${food.source}">
                        ${getSourceLabel(food.source)}
                    </span>
                </div>
                <div class="food-autocomplete-nutrition">
                    ${formatNutrition(food)}
                </div>
            </div>
        `).join('');

        dropdown.innerHTML = html;
        dropdown.hidden = false;

        // Add click handlers
        dropdown.querySelectorAll('.food-autocomplete-item').forEach(item => {
            item.addEventListener('click', () => {
                const index = parseInt(item.dataset.index, 10);
                selectFood(currentResults[index], dropdown, inputElement);
            });
            item.addEventListener('mouseenter', () => {
                selectedIndex = parseInt(item.dataset.index, 10);
                updateSelection(dropdown);
            });
        });
    }

    /**
     * Get human-readable source label
     */
    function getSourceLabel(source) {
        const labels = {
            'local': 'Saved',
            'custom': 'My Food',
            'fatsecret': 'FatSecret',
            'ai': 'AI Estimate'
        };
        return labels[source] || source;
    }

    /**
     * Format nutrition summary for display
     */
    function formatNutrition(food) {
        const parts = [];

        if (food.calories != null) {
            parts.push(`${Math.round(food.calories)} cal`);
        }
        if (food.protein_g != null) {
            parts.push(`P: ${food.protein_g}g`);
        }
        if (food.carbohydrates_g != null) {
            parts.push(`C: ${food.carbohydrates_g}g`);
        }
        if (food.fat_g != null) {
            parts.push(`F: ${food.fat_g}g`);
        }

        return parts.join(' | ') || 'No nutrition data';
    }

    /**
     * Handle keyboard navigation
     */
    function handleKeydown(event, dropdown, inputElement) {
        if (dropdown.hidden) return;

        switch (event.key) {
            case 'ArrowDown':
                event.preventDefault();
                if (selectedIndex < currentResults.length - 1) {
                    selectedIndex++;
                    updateSelection(dropdown);
                }
                break;

            case 'ArrowUp':
                event.preventDefault();
                if (selectedIndex > 0) {
                    selectedIndex--;
                    updateSelection(dropdown);
                }
                break;

            case 'Enter':
                event.preventDefault();
                if (selectedIndex >= 0 && currentResults[selectedIndex]) {
                    selectFood(currentResults[selectedIndex], dropdown, inputElement);
                }
                break;

            case 'Escape':
                hideDropdown(dropdown);
                break;
        }
    }

    /**
     * Update visual selection
     */
    function updateSelection(dropdown) {
        dropdown.querySelectorAll('.food-autocomplete-item').forEach((item, index) => {
            item.classList.toggle('selected', index === selectedIndex);
        });

        // Scroll into view
        const selected = dropdown.querySelector('.food-autocomplete-item.selected');
        if (selected) {
            selected.scrollIntoView({ block: 'nearest' });
        }
    }

    /**
     * Select a food and auto-fill form fields
     */
    function selectFood(food, dropdown, inputElement) {
        // Find the form
        const form = inputElement.closest('form');
        if (!form) return;

        // Store per-serving snapshot for quantity scaling
        perServingSnapshot = {
            calories: food.calories || 0,
            protein_g: food.protein_g || 0,
            carbohydrates_g: food.carbohydrates_g || 0,
            fat_g: food.fat_g || 0,
            fiber_g: food.fiber_g || 0,
            sugar_g: food.sugar_g || 0,
            saturated_fat_g: food.saturated_fat_g || 0,
        };

        // Build display name
        const displayName = food.brand
            ? `${food.name} (${food.brand})`
            : food.name;

        // Auto-fill all fields (per-serving values)
        setFieldValue(form, 'food_name', displayName);
        setFieldValue(form, 'food_brand', food.brand || '');
        setFieldValue(form, 'total_calories', food.calories);
        setFieldValue(form, 'total_protein_g', food.protein_g);
        setFieldValue(form, 'total_carbohydrates_g', food.carbohydrates_g);
        setFieldValue(form, 'total_fat_g', food.fat_g);
        setFieldValue(form, 'total_fiber_g', food.fiber_g);
        setFieldValue(form, 'total_sugar_g', food.sugar_g);
        setFieldValue(form, 'total_saturated_fat_g', food.saturated_fat_g);
        setFieldValue(form, 'serving_size', food.serving_size);
        setFieldValue(form, 'serving_unit', food.serving_unit);

        // Reset quantity to 1 when selecting a new food
        setFieldValue(form, 'quantity', 1);

        hideDropdown(dropdown);

        // Visual feedback
        highlightFilledFields(form);

        // Show success message
        showFillNotification(food.source);
    }

    /**
     * Recalculate nutrition totals when quantity changes.
     * Uses the per-serving snapshot stored when food was selected.
     * This is a PREVIEW only — server recalculates on save.
     */
    function recalculateTotals(form) {
        if (!perServingSnapshot) return;

        const qtyField = form.querySelector('[name="quantity"]');
        if (!qtyField) return;

        const qty = parseFloat(qtyField.value) || 1;

        const fieldMap = {
            'total_calories': 'calories',
            'total_protein_g': 'protein_g',
            'total_carbohydrates_g': 'carbohydrates_g',
            'total_fat_g': 'fat_g',
            'total_fiber_g': 'fiber_g',
            'total_sugar_g': 'sugar_g',
            'total_saturated_fat_g': 'saturated_fat_g',
        };

        for (const [formField, snapshotKey] of Object.entries(fieldMap)) {
            const field = form.querySelector(`[name="${formField}"]`);
            const perServing = perServingSnapshot[snapshotKey] || 0;
            if (field) {
                const total = Math.round(perServing * qty * 100) / 100;
                field.value = total;
                field.classList.add('field-auto-filled');
                setTimeout(() => field.classList.remove('field-auto-filled'), 1000);
            }
        }
    }

    /**
     * Set form field value by name
     */
    function setFieldValue(form, name, value) {
        const field = form.querySelector(`[name="${name}"]`);
        if (field && value !== undefined && value !== null && value !== '') {
            field.value = value;
            // Trigger change event for any listeners
            field.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }

    /**
     * Add visual highlight to auto-filled fields
     */
    function highlightFilledFields(form) {
        const nutritionFields = [
            'total_calories', 'total_protein_g', 'total_carbohydrates_g',
            'total_fat_g', 'total_fiber_g', 'total_sugar_g', 'total_saturated_fat_g',
            'serving_size', 'serving_unit'
        ];

        nutritionFields.forEach(name => {
            const field = form.querySelector(`[name="${name}"]`);
            if (field && field.value) {
                field.classList.add('field-auto-filled');
                setTimeout(() => field.classList.remove('field-auto-filled'), 2000);
            }
        });
    }

    /**
     * Show notification about auto-fill
     */
    function showFillNotification(source) {
        // Use existing toast system if available
        if (typeof window.showToast === 'function') {
            const message = source === 'ai'
                ? 'Nutrition auto-filled (AI estimate)'
                : 'Nutrition auto-filled';
            window.showToast(message, 'success');
        }
    }

    /**
     * Handle input focus
     */
    function handleFocus(event, dropdown) {
        const query = event.target.value.trim();
        if (query.length >= MIN_QUERY_LENGTH && currentResults.length > 0 && !isLoading) {
            dropdown.hidden = false;
        }
    }

    /**
     * Hide the dropdown
     */
    function hideDropdown(dropdown) {
        dropdown.hidden = true;
        selectedIndex = -1;
    }

    /**
     * Escape HTML to prevent XSS
     */
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Initialize on DOM ready
    document.addEventListener('DOMContentLoaded', function() {
        // Find food name input on food entry form
        const foodNameInput = document.getElementById('id_food_name');
        if (foodNameInput) {
            initFoodAutocomplete(foodNameInput);
        }
    });

    // Export for external use
    window.initFoodAutocomplete = initFoodAutocomplete;
})();
