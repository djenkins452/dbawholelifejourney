/**
 * Timer Completion Sounds — Web Audio API synthesizer.
 *
 * Generates 5 popular timer completion sounds without external audio files.
 * Sounds persist preference in localStorage.
 *
 * Usage:
 *   TimerSounds.play('chime');
 *   TimerSounds.setPreference(goalPk, 'bell');
 *   const pref = TimerSounds.getPreference(goalPk);
 *
 * Location: static/js/timer-sounds.js
 */
const TimerSounds = (function() {
    'use strict';

    let audioCtx = null;
    const STORAGE_KEY_PREFIX = 'wlj_timer_sound_';

    function getContext() {
        if (!audioCtx) {
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        }
        if (audioCtx.state === 'suspended') {
            audioCtx.resume();
        }
        return audioCtx;
    }

    // ── Sound Definitions ──

    /**
     * 1. Chime — Two-tone meditation bell (like Insight Timer / Calm)
     */
    function playChime() {
        const ctx = getContext();
        const now = ctx.currentTime;

        [523.25, 783.99].forEach(function(freq, i) {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = 'sine';
            osc.frequency.value = freq;
            gain.gain.setValueAtTime(0, now + i * 0.3);
            gain.gain.linearRampToValueAtTime(0.4, now + i * 0.3 + 0.05);
            gain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.3 + 1.8);
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start(now + i * 0.3);
            osc.stop(now + i * 0.3 + 1.8);
        });
    }

    /**
     * 2. Bell — Classic kitchen timer ring (triple ding)
     */
    function playBell() {
        const ctx = getContext();
        const now = ctx.currentTime;

        for (var i = 0; i < 3; i++) {
            var offset = i * 0.25;
            var osc = ctx.createOscillator();
            var gain = ctx.createGain();
            osc.type = 'sine';
            osc.frequency.value = 880;
            gain.gain.setValueAtTime(0, now + offset);
            gain.gain.linearRampToValueAtTime(0.5, now + offset + 0.01);
            gain.gain.exponentialRampToValueAtTime(0.001, now + offset + 0.5);
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start(now + offset);
            osc.stop(now + offset + 0.5);

            // Add harmonic overtone for metallic bell quality
            var osc2 = ctx.createOscillator();
            var gain2 = ctx.createGain();
            osc2.type = 'sine';
            osc2.frequency.value = 880 * 2.756;
            gain2.gain.setValueAtTime(0, now + offset);
            gain2.gain.linearRampToValueAtTime(0.15, now + offset + 0.01);
            gain2.gain.exponentialRampToValueAtTime(0.001, now + offset + 0.3);
            osc2.connect(gain2);
            gain2.connect(ctx.destination);
            osc2.start(now + offset);
            osc2.stop(now + offset + 0.3);
        }
    }

    /**
     * 3. Gentle — Soft ascending tone (like Headspace)
     */
    function playGentle() {
        const ctx = getContext();
        const now = ctx.currentTime;
        var notes = [392, 440, 523.25, 659.25];

        notes.forEach(function(freq, i) {
            var osc = ctx.createOscillator();
            var gain = ctx.createGain();
            osc.type = 'sine';
            osc.frequency.value = freq;
            var start = now + i * 0.35;
            gain.gain.setValueAtTime(0, start);
            gain.gain.linearRampToValueAtTime(0.3, start + 0.08);
            gain.gain.exponentialRampToValueAtTime(0.001, start + 1.0);
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start(start);
            osc.stop(start + 1.0);
        });
    }

    /**
     * 4. Celebration — Cheerful completion jingle (like Duolingo)
     */
    function playCelebration() {
        const ctx = getContext();
        const now = ctx.currentTime;
        var notes = [
            {freq: 523.25, start: 0, dur: 0.15},
            {freq: 659.25, start: 0.12, dur: 0.15},
            {freq: 783.99, start: 0.24, dur: 0.15},
            {freq: 1046.50, start: 0.36, dur: 0.6},
        ];

        notes.forEach(function(n) {
            var osc = ctx.createOscillator();
            var gain = ctx.createGain();
            osc.type = 'triangle';
            osc.frequency.value = n.freq;
            var t = now + n.start;
            gain.gain.setValueAtTime(0, t);
            gain.gain.linearRampToValueAtTime(0.4, t + 0.02);
            gain.gain.exponentialRampToValueAtTime(0.001, t + n.dur);
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start(t);
            osc.stop(t + n.dur);
        });
    }

    /**
     * 5. Harp — Gentle harp glissando (like a mindfulness app)
     */
    function playHarp() {
        const ctx = getContext();
        const now = ctx.currentTime;
        var notes = [261.63, 329.63, 392, 523.25, 659.25, 783.99];

        notes.forEach(function(freq, i) {
            var osc = ctx.createOscillator();
            var gain = ctx.createGain();
            osc.type = 'sine';
            osc.frequency.value = freq;
            var start = now + i * 0.1;
            gain.gain.setValueAtTime(0, start);
            gain.gain.linearRampToValueAtTime(0.25, start + 0.02);
            gain.gain.exponentialRampToValueAtTime(0.001, start + 1.5);
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start(start);
            osc.stop(start + 1.5);
        });
    }

    // ── Sound Registry ──

    var SOUNDS = {
        chime:       { label: 'Chime',       description: 'Meditation bell', play: playChime },
        bell:        { label: 'Bell',         description: 'Kitchen timer',   play: playBell },
        gentle:      { label: 'Gentle Rise',  description: 'Soft ascending',  play: playGentle },
        celebration: { label: 'Celebration',  description: 'Cheerful jingle', play: playCelebration },
        harp:        { label: 'Harp',         description: 'Harp glissando',  play: playHarp },
    };

    var DEFAULT_SOUND = 'chime';

    // ── Public API ──

    function play(soundId) {
        if (!soundId || soundId === 'none') return;
        var sound = SOUNDS[soundId];
        if (sound) {
            sound.play();
        }
    }

    function preview(soundId) {
        play(soundId);
    }

    function getSounds() {
        var result = [];
        Object.keys(SOUNDS).forEach(function(key) {
            result.push({ id: key, label: SOUNDS[key].label, description: SOUNDS[key].description });
        });
        result.push({ id: 'none', label: 'None', description: 'Silent' });
        return result;
    }

    function setPreference(goalPk, soundId) {
        try {
            localStorage.setItem(STORAGE_KEY_PREFIX + goalPk, soundId);
        } catch (e) { /* quota */ }
    }

    function getPreference(goalPk) {
        try {
            return localStorage.getItem(STORAGE_KEY_PREFIX + goalPk) || DEFAULT_SOUND;
        } catch (e) {
            return DEFAULT_SOUND;
        }
    }

    return {
        play: play,
        preview: preview,
        getSounds: getSounds,
        setPreference: setPreference,
        getPreference: getPreference,
        DEFAULT_SOUND: DEFAULT_SOUND,
    };
})();
