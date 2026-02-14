/**
 * Goal Timer Engine — Circular progress timer for DURATION goals.
 *
 * Features:
 * - Start / Pause / Resume / Stop lifecycle
 * - Circular SVG progress ring
 * - localStorage persistence across page loads
 * - Auto-submit duration on stop
 * - Session target, time completed, weekly progress
 *
 * Usage:
 *   const timer = new GoalTimer({
 *     goalPk: 123,
 *     targetMinutes: 30,
 *     csrfToken: '...',
 *     onUpdate: (state) => { ... },
 *     onSaved: (response) => { ... },
 *   });
 *
 * Location: static/js/goal-timer.js
 */

class GoalTimer {
    constructor(options) {
        this.goalPk = options.goalPk;
        this.targetMinutes = options.targetMinutes || 0;
        this.csrfToken = options.csrfToken;
        this.onUpdate = options.onUpdate || (() => {});
        this.onSaved = options.onSaved || (() => {});
        this.onError = options.onError || ((err) => console.error(err));

        this.storageKey = `wlj_timer_${this.goalPk}`;
        this.intervalId = null;
        this.state = 'idle'; // idle | running | paused
        this.startedAt = null;
        this.pausedAt = null;
        this.accumulatedMs = 0;

        this._loadState();
        if (this.state === 'running') {
            this._startInterval();
        }
    }

    // ── Public API ──

    start() {
        if (this.state === 'running') return;
        this.state = 'running';
        this.startedAt = Date.now();
        this.pausedAt = null;
        this.accumulatedMs = 0;
        this._saveState();
        this._startInterval();
    }

    pause() {
        if (this.state !== 'running') return;
        this.state = 'paused';
        this.accumulatedMs = this.getElapsedMs();
        this.pausedAt = Date.now();
        this.startedAt = null;
        this._clearInterval();
        this._saveState();
        this._emitUpdate();
    }

    resume() {
        if (this.state !== 'paused') return;
        this.state = 'running';
        this.startedAt = Date.now();
        this.pausedAt = null;
        this._saveState();
        this._startInterval();
    }

    async stop() {
        if (this.state === 'idle') return;
        const elapsed = this.getElapsedMs();
        const minutes = elapsed / 60000;

        this._reset();

        if (minutes < 0.1) {
            this.onError('Session too short to save.');
            return;
        }

        try {
            const res = await fetch(`/purpose/habits/${this.goalPk}/log-duration/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken,
                },
                body: JSON.stringify({
                    duration_minutes: Math.round(minutes * 100) / 100,
                }),
            });
            const data = await res.json();
            if (data.success) {
                this.onSaved(data);
            } else {
                this.onError(data.error || 'Failed to save session.');
            }
        } catch (err) {
            this.onError('Network error. Please try again.');
        }
    }

    getElapsedMs() {
        if (this.state === 'running' && this.startedAt) {
            return this.accumulatedMs + (Date.now() - this.startedAt);
        }
        return this.accumulatedMs;
    }

    getElapsedMinutes() {
        return this.getElapsedMs() / 60000;
    }

    getProgressPercent() {
        if (!this.targetMinutes || this.targetMinutes <= 0) return 0;
        return Math.min(100, (this.getElapsedMinutes() / this.targetMinutes) * 100);
    }

    formatTime(ms) {
        const totalSeconds = Math.floor(ms / 1000);
        const hours = Math.floor(totalSeconds / 3600);
        const mins = Math.floor((totalSeconds % 3600) / 60);
        const secs = totalSeconds % 60;
        if (hours > 0) {
            return `${hours}:${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
        }
        return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    }

    isActive() {
        return this.state !== 'idle';
    }

    // ── Internal ──

    _startInterval() {
        this._clearInterval();
        this.intervalId = setInterval(() => this._emitUpdate(), 1000);
        this._emitUpdate();
    }

    _clearInterval() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
        }
    }

    _emitUpdate() {
        this.onUpdate({
            state: this.state,
            elapsedMs: this.getElapsedMs(),
            elapsedFormatted: this.formatTime(this.getElapsedMs()),
            elapsedMinutes: this.getElapsedMinutes(),
            progressPercent: this.getProgressPercent(),
            targetMinutes: this.targetMinutes,
        });
    }

    _reset() {
        this._clearInterval();
        this.state = 'idle';
        this.startedAt = null;
        this.pausedAt = null;
        this.accumulatedMs = 0;
        this._clearStorage();
        this._emitUpdate();
    }

    _saveState() {
        try {
            localStorage.setItem(this.storageKey, JSON.stringify({
                goalPk: this.goalPk,
                state: this.state,
                startedAt: this.startedAt,
                pausedAt: this.pausedAt,
                accumulatedMs: this.accumulatedMs,
            }));
        } catch (e) { /* quota exceeded etc. */ }
    }

    _loadState() {
        try {
            const raw = localStorage.getItem(this.storageKey);
            if (!raw) return;
            const saved = JSON.parse(raw);
            if (saved.goalPk !== this.goalPk) return;

            this.state = saved.state || 'idle';
            this.startedAt = saved.startedAt || null;
            this.pausedAt = saved.pausedAt || null;
            this.accumulatedMs = saved.accumulatedMs || 0;
        } catch (e) {
            this._clearStorage();
        }
    }

    _clearStorage() {
        try {
            localStorage.removeItem(this.storageKey);
        } catch (e) { /* ok */ }
    }

    destroy() {
        this._clearInterval();
    }
}


/**
 * Initialize the timer UI on a goal detail page.
 * Expects DOM elements with specific IDs.
 */
function initGoalTimerUI(goalPk, targetMinutes, csrfToken) {
    const container = document.getElementById('timer-container');
    if (!container) return null;

    const circle = document.getElementById('timer-progress-ring');
    const timeDisplay = document.getElementById('timer-time');
    const percentDisplay = document.getElementById('timer-percent');
    const startBtn = document.getElementById('timer-start');
    const pauseBtn = document.getElementById('timer-pause');
    const resumeBtn = document.getElementById('timer-resume');
    const stopBtn = document.getElementById('timer-stop');
    const statusLabel = document.getElementById('timer-status');

    // SVG ring setup
    const radius = circle ? parseFloat(circle.getAttribute('r')) : 0;
    const circumference = 2 * Math.PI * radius;
    if (circle) {
        circle.style.strokeDasharray = circumference;
        circle.style.strokeDashoffset = circumference;
    }

    function setProgress(percent) {
        if (!circle) return;
        const offset = circumference - (percent / 100) * circumference;
        circle.style.strokeDashoffset = offset;

        // Color transition: accent → success at 100%
        if (percent >= 100) {
            circle.style.stroke = 'var(--color-success, #22c55e)';
        } else {
            circle.style.stroke = 'var(--color-accent, #6366f1)';
        }
    }

    function updateButtons(state) {
        if (!startBtn) return;
        startBtn.style.display = state === 'idle' ? 'inline-flex' : 'none';
        pauseBtn.style.display = state === 'running' ? 'inline-flex' : 'none';
        resumeBtn.style.display = state === 'paused' ? 'inline-flex' : 'none';
        stopBtn.style.display = (state === 'running' || state === 'paused') ? 'inline-flex' : 'none';

        if (statusLabel) {
            const labels = { idle: 'Ready', running: 'Running', paused: 'Paused' };
            statusLabel.textContent = labels[state] || '';
            statusLabel.className = 'timer-status timer-status-' + state;
        }
    }

    const timer = new GoalTimer({
        goalPk,
        targetMinutes,
        csrfToken,
        onUpdate(data) {
            if (timeDisplay) timeDisplay.textContent = data.elapsedFormatted;
            if (percentDisplay) percentDisplay.textContent = Math.round(data.progressPercent) + '%';
            setProgress(data.progressPercent);
            updateButtons(data.state);
        },
        onSaved(data) {
            // Refresh page to show updated stats
            window.location.reload();
        },
        onError(msg) {
            const fb = document.getElementById('feedback-message');
            if (fb) {
                fb.textContent = msg;
                fb.className = 'feedback-message error';
                fb.style.display = 'block';
                setTimeout(() => { fb.style.display = 'none'; }, 4000);
            }
        },
    });

    if (startBtn) startBtn.addEventListener('click', () => timer.start());
    if (pauseBtn) pauseBtn.addEventListener('click', () => timer.pause());
    if (resumeBtn) resumeBtn.addEventListener('click', () => timer.resume());
    if (stopBtn) stopBtn.addEventListener('click', () => timer.stop());

    return timer;
}
