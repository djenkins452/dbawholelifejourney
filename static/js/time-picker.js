/**
 * WLJ Quarter-Hour Time Picker
 *
 * Replaces native <input type="time"> with hour + minute <select> dropdowns
 * showing only 15-minute increments (00, 15, 30, 45).
 *
 * Targets: any input[type="time"][step="900"] OR input[type="time"].wlj-quarter-time
 *
 * The original <input type="time"> is kept hidden so form submission
 * still sends the standard HH:MM format. The selects sync to it.
 *
 * Usage: automatic on DOMContentLoaded. For dynamically added inputs,
 * call window.wljInitTimePickers(container) on the parent element.
 */
(function () {
  'use strict';

  var MINUTES = ['00', '15', '30', '45'];
  var SELECTOR = 'input[type="time"][step="900"], input[type="time"].wlj-quarter-time';

  /**
   * Build the hour options (12-hour with AM/PM display, 24h value).
   */
  function buildHourOptions() {
    var opts = [];
    for (var h = 0; h < 24; h++) {
      var display12 = h === 0 ? '12 AM' :
                      h < 12 ? h + ' AM' :
                      h === 12 ? '12 PM' :
                      (h - 12) + ' PM';
      opts.push({ value: String(h).padStart(2, '0'), label: display12 });
    }
    return opts;
  }

  var HOUR_OPTIONS = buildHourOptions();

  /**
   * Create a styled <select> element.
   */
  function createSelect(options, selectedValue, ariaLabel, className) {
    var sel = document.createElement('select');
    sel.className = 'form-input wlj-time-select ' + (className || '');
    sel.setAttribute('aria-label', ariaLabel);

    // Blank option
    var blank = document.createElement('option');
    blank.value = '';
    blank.textContent = '--';
    sel.appendChild(blank);

    options.forEach(function (opt) {
      var o = document.createElement('option');
      o.value = opt.value;
      o.textContent = opt.label;
      if (opt.value === selectedValue) o.selected = true;
      sel.appendChild(o);
    });

    return sel;
  }

  /**
   * Parse HH:MM string into { hour: '08', minute: '15' }.
   * Snaps minute to nearest quarter.
   */
  function parseTime(val) {
    if (!val) return { hour: '', minute: '' };
    var parts = val.split(':');
    var h = parts[0] || '';
    var m = parseInt(parts[1] || '0', 10);
    // Snap to nearest quarter
    var snapped = Math.round(m / 15) * 15;
    if (snapped === 60) { snapped = 0; h = String((parseInt(h, 10) + 1) % 24).padStart(2, '0'); }
    return { hour: h, minute: String(snapped).padStart(2, '0') };
  }

  /**
   * Sync select values back to the hidden input.
   */
  function syncToInput(input, hourSel, minSel) {
    var h = hourSel.value;
    var m = minSel.value;
    if (h && m) {
      input.value = h + ':' + m;
    } else {
      input.value = '';
    }
    // Fire change event so any listeners (e.g., form validation) pick it up
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }

  /**
   * Replace a single time input with hour/minute selects.
   */
  function replaceInput(input) {
    // Don't double-init
    if (input.dataset.wljTimePicker === 'init') return;
    input.dataset.wljTimePicker = 'init';

    var parsed = parseTime(input.value);

    // Minute options with labels
    var minuteOpts = MINUTES.map(function (m) {
      return { value: m, label: ':' + m };
    });

    var hourSel = createSelect(HOUR_OPTIONS, parsed.hour, 'Hour', 'wlj-time-hour');
    var minSel = createSelect(minuteOpts, parsed.minute, 'Minute', 'wlj-time-minute');

    // Copy required attribute
    if (input.required) {
      hourSel.required = true;
      minSel.required = true;
    }

    // Copy disabled/readonly
    if (input.disabled) {
      hourSel.disabled = true;
      minSel.disabled = true;
    }

    // Wrapper
    var wrapper = document.createElement('div');
    wrapper.className = 'wlj-time-picker-wrapper';
    wrapper.appendChild(hourSel);
    wrapper.appendChild(minSel);

    // Hide original input (keep in DOM for form submission)
    input.style.display = 'none';
    input.parentNode.insertBefore(wrapper, input.nextSibling);

    // Sync on change
    hourSel.addEventListener('change', function () { syncToInput(input, hourSel, minSel); });
    minSel.addEventListener('change', function () { syncToInput(input, hourSel, minSel); });

    // If original input changes externally, update selects
    var observer = new MutationObserver(function () {
      var p = parseTime(input.value);
      if (hourSel.value !== p.hour) hourSel.value = p.hour;
      if (minSel.value !== p.minute) minSel.value = p.minute;
    });
    observer.observe(input, { attributes: true, attributeFilter: ['value'] });
  }

  /**
   * Initialize all time pickers within a container.
   */
  function initTimePickers(container) {
    var root = container || document;
    var inputs = root.querySelectorAll(SELECTOR);
    inputs.forEach(replaceInput);
  }

  // Auto-init on page load
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { initTimePickers(); });
  } else {
    initTimePickers();
  }

  // Expose for dynamic content (formsets, modals, HTMX swaps)
  window.wljInitTimePickers = initTimePickers;

  // Auto-init on HTMX content swaps
  document.addEventListener('htmx:afterSwap', function (e) {
    initTimePickers(e.detail.target);
  });
})();
