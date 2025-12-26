/**
 * US State Timezone Lookup
 * 
 * Maps US states to their primary timezone.
 * Note: Some states span multiple timezones; this uses the most populous timezone.
 * 
 * Location: static/js/timezone-lookup.js
 */

const STATE_TIMEZONES = {
    'Alabama': 'US/Central',
    'Alaska': 'US/Alaska',
    'Arizona': 'US/Mountain',
    'Arkansas': 'US/Central',
    'California': 'US/Pacific',
    'Colorado': 'US/Mountain',
    'Connecticut': 'US/Eastern',
    'Delaware': 'US/Eastern',
    'District of Columbia': 'US/Eastern',
    'Florida': 'US/Eastern',
    'Georgia': 'US/Eastern',
    'Hawaii': 'US/Hawaii',
    'Idaho': 'US/Mountain',
    'Illinois': 'US/Central',
    'Indiana': 'US/Eastern',
    'Iowa': 'US/Central',
    'Kansas': 'US/Central',
    'Kentucky': 'US/Eastern',
    'Louisiana': 'US/Central',
    'Maine': 'US/Eastern',
    'Maryland': 'US/Eastern',
    'Massachusetts': 'US/Eastern',
    'Michigan': 'US/Eastern',
    'Minnesota': 'US/Central',
    'Mississippi': 'US/Central',
    'Missouri': 'US/Central',
    'Montana': 'US/Mountain',
    'Nebraska': 'US/Central',
    'Nevada': 'US/Pacific',
    'New Hampshire': 'US/Eastern',
    'New Jersey': 'US/Eastern',
    'New Mexico': 'US/Mountain',
    'New York': 'US/Eastern',
    'North Carolina': 'US/Eastern',
    'North Dakota': 'US/Central',
    'Ohio': 'US/Eastern',
    'Oklahoma': 'US/Central',
    'Oregon': 'US/Pacific',
    'Pennsylvania': 'US/Eastern',
    'Rhode Island': 'US/Eastern',
    'South Carolina': 'US/Eastern',
    'South Dakota': 'US/Central',
    'Tennessee': 'US/Central',
    'Texas': 'US/Central',
    'Utah': 'US/Mountain',
    'Vermont': 'US/Eastern',
    'Virginia': 'US/Eastern',
    'Washington': 'US/Pacific',
    'West Virginia': 'US/Eastern',
    'Wisconsin': 'US/Central',
    'Wyoming': 'US/Mountain'
};

/**
 * Get timezone for a US state
 * @param {string} stateName - Full state name (e.g., "California")
 * @returns {string|null} - Timezone string or null if not found
 */
function getTimezoneForState(stateName) {
    return STATE_TIMEZONES[stateName] || null;
}

/**
 * Lookup ZIP code and populate form fields
 * Requires: zipInput, cityInput, stateInput, timezoneSelect, statusEl
 */
async function lookupZip() {
    const zipInput = document.getElementById('zip_code');
    const statusEl = document.getElementById('zip_status');
    const cityInput = document.getElementById('id_location_city');
    const stateInput = document.getElementById('id_location_country');
    const timezoneSelect = document.getElementById('id_timezone');
    
    if (!zipInput || !statusEl) return;
    
    const zip = zipInput.value.trim();
    
    // Validate ZIP format
    if (!/^\d{5}$/.test(zip)) {
        statusEl.textContent = 'Please enter a valid 5-digit ZIP code';
        statusEl.style.color = 'var(--color-error)';
        return;
    }
    
    statusEl.textContent = 'Looking up...';
    statusEl.style.color = 'var(--color-text-muted)';
    
    try {
        const response = await fetch(`https://api.zippopotam.us/us/${zip}`);
        
        if (!response.ok) {
            throw new Error('ZIP code not found');
        }
        
        const data = await response.json();
        const place = data.places[0];
        
        // Fill in city and state
        if (cityInput) {
            cityInput.value = place['place name'];
        }
        if (stateInput) {
            stateInput.value = `${place['state']}, US`;
        }
        
        // Try to set timezone based on state
        const timezone = getTimezoneForState(place['state']);
        if (timezone && timezoneSelect) {
            // Find and select the matching option
            for (let option of timezoneSelect.options) {
                if (option.value === timezone) {
                    option.selected = true;
                    break;
                }
            }
        }
        
        statusEl.textContent = `Found: ${place['place name']}, ${place['state']}`;
        statusEl.style.color = 'var(--color-success, #10b981)';
        
    } catch (error) {
        statusEl.textContent = 'ZIP code not found. Please enter city manually.';
        statusEl.style.color = 'var(--color-error)';
    }
}

// Allow Enter key to trigger lookup
document.addEventListener('DOMContentLoaded', function() {
    const zipInput = document.getElementById('zip_code');
    if (zipInput) {
        zipInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                lookupZip();
            }
        });
    }
});

// Export for module use if needed
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { STATE_TIMEZONES, getTimezoneForState, lookupZip };
}