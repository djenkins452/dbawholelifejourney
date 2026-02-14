/**
 * Goal Counter Widget — +/- counter for COUNT goals.
 *
 * Features:
 * - Increment/decrement with configurable step
 * - Direct numeric input
 * - Submit on button press
 * - Animated count display
 *
 * Usage:
 *   initGoalCounterUI(goalPk, targetValue, csrfToken);
 *
 * Location: static/js/goal-counter.js
 */

function initGoalCounterUI(goalPk, targetValue, currentValue, csrfToken) {
    const container = document.getElementById('counter-container');
    if (!container) return;

    const display = document.getElementById('counter-value');
    const input = document.getElementById('counter-input');
    const minusBtn = document.getElementById('counter-minus');
    const plusBtn = document.getElementById('counter-plus');
    const saveBtn = document.getElementById('counter-save');
    const progressBar = document.getElementById('counter-progress-fill');
    const progressLabel = document.getElementById('counter-progress-label');

    let value = currentValue || 0;
    const step = 1;

    function updateDisplay() {
        if (display) display.textContent = value;
        if (input) input.value = value;

        // Update progress bar
        if (progressBar && targetValue > 0) {
            const pct = Math.min(100, (value / targetValue) * 100);
            progressBar.style.width = pct + '%';
            if (pct >= 100) {
                progressBar.classList.add('complete');
            } else {
                progressBar.classList.remove('complete');
            }
        }
        if (progressLabel && targetValue > 0) {
            progressLabel.textContent = `${value} / ${targetValue}`;
        }

        // Enable/disable minus button
        if (minusBtn) minusBtn.disabled = value <= 0;
    }

    async function saveCount() {
        if (saveBtn) {
            saveBtn.disabled = true;
            saveBtn.textContent = 'Saving...';
        }

        try {
            const res = await fetch(`/purpose/habits/${goalPk}/log-count/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken,
                },
                body: JSON.stringify({ count_value: value }),
            });
            const data = await res.json();
            if (data.success) {
                window.location.reload();
            } else {
                showError(data.error || 'Failed to save.');
                if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'Save'; }
            }
        } catch (err) {
            showError('Network error. Please try again.');
            if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'Save'; }
        }
    }

    function showError(msg) {
        const fb = document.getElementById('feedback-message');
        if (fb) {
            fb.textContent = msg;
            fb.className = 'feedback-message error';
            fb.style.display = 'block';
            setTimeout(() => { fb.style.display = 'none'; }, 4000);
        }
    }

    if (minusBtn) minusBtn.addEventListener('click', () => {
        value = Math.max(0, value - step);
        updateDisplay();
    });

    if (plusBtn) plusBtn.addEventListener('click', () => {
        value += step;
        updateDisplay();
    });

    if (input) input.addEventListener('change', () => {
        const v = parseFloat(input.value);
        if (!isNaN(v) && v >= 0) {
            value = v;
            updateDisplay();
        }
    });

    if (saveBtn) saveBtn.addEventListener('click', saveCount);

    updateDisplay();
}
