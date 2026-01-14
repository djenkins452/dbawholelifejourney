/**
 * Audio Recorder Module
 *
 * Handles browser audio recording using the MediaRecorder API.
 * Records in webm format for best browser compatibility.
 */

class AudioRecorder {
    constructor(options = {}) {
        this.maxDurationMs = options.maxDuration || 60 * 60 * 1000; // 60 minutes default
        this.onStateChange = options.onStateChange || (() => {});
        this.onTimeUpdate = options.onTimeUpdate || (() => {});
        this.onError = options.onError || console.error;

        this.mediaRecorder = null;
        this.audioChunks = [];
        this.recordingStartTime = null;
        this.timerInterval = null;
        this.audioBlob = null;
        this.stream = null;
    }

    /**
     * Check if browser supports audio recording
     */
    static isSupported() {
        return !!(
            navigator.mediaDevices &&
            navigator.mediaDevices.getUserMedia &&
            window.MediaRecorder
        );
    }

    /**
     * Get preferred MIME type for recording
     */
    static getPreferredMimeType() {
        if (MediaRecorder.isTypeSupported('audio/webm')) {
            return 'audio/webm';
        }
        if (MediaRecorder.isTypeSupported('audio/mp4')) {
            return 'audio/mp4';
        }
        if (MediaRecorder.isTypeSupported('audio/ogg')) {
            return 'audio/ogg';
        }
        return '';
    }

    /**
     * Request microphone access
     */
    async requestPermission() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            // Stop immediately - just checking permission
            stream.getTracks().forEach(track => track.stop());
            return true;
        } catch (err) {
            this.onError('Microphone access denied', err);
            return false;
        }
    }

    /**
     * Start recording
     */
    async start() {
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });

            const mimeType = AudioRecorder.getPreferredMimeType();
            const options = mimeType ? { mimeType } : {};

            this.mediaRecorder = new MediaRecorder(this.stream, options);
            this.audioChunks = [];

            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.audioChunks.push(event.data);
                }
            };

            this.mediaRecorder.onstop = () => {
                this._handleRecordingStop();
            };

            // Start recording with data collection every second
            this.mediaRecorder.start(1000);
            this.recordingStartTime = Date.now();
            this.onStateChange('recording');

            // Start timer
            this.timerInterval = setInterval(() => {
                const elapsed = Date.now() - this.recordingStartTime;
                this.onTimeUpdate(elapsed);

                // Auto-stop at max duration
                if (elapsed >= this.maxDurationMs) {
                    this.stop();
                }
            }, 100);

            return true;
        } catch (err) {
            this.onError('Failed to start recording', err);
            return false;
        }
    }

    /**
     * Stop recording
     */
    stop() {
        if (this.timerInterval) {
            clearInterval(this.timerInterval);
            this.timerInterval = null;
        }

        if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
            this.mediaRecorder.stop();
        }
    }

    /**
     * Handle recording stop internally
     */
    _handleRecordingStop() {
        // Stop all tracks
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
        }

        // Create blob
        const mimeType = this.mediaRecorder?.mimeType || 'audio/webm';
        this.audioBlob = new Blob(this.audioChunks, { type: mimeType });

        const duration = Date.now() - this.recordingStartTime;
        this.onStateChange('preview', {
            blob: this.audioBlob,
            duration: duration,
            mimeType: mimeType
        });
    }

    /**
     * Get the recorded audio blob
     */
    getBlob() {
        return this.audioBlob;
    }

    /**
     * Get duration of recording in milliseconds
     */
    getDuration() {
        if (!this.recordingStartTime) return 0;
        return Date.now() - this.recordingStartTime;
    }

    /**
     * Discard the current recording
     */
    discard() {
        this.audioBlob = null;
        this.audioChunks = [];
        this.recordingStartTime = null;
        this.onStateChange('idle');
    }

    /**
     * Format milliseconds as MM:SS
     */
    static formatTime(ms) {
        const totalSeconds = Math.floor(ms / 1000);
        const minutes = Math.floor(totalSeconds / 60);
        const seconds = totalSeconds % 60;
        return String(minutes).padStart(2, '0') + ':' + String(seconds).padStart(2, '0');
    }

    /**
     * Format milliseconds as HH:MM:SS for longer recordings
     */
    static formatTimeLong(ms) {
        const totalSeconds = Math.floor(ms / 1000);
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;

        if (hours > 0) {
            return String(hours).padStart(2, '0') + ':' +
                   String(minutes).padStart(2, '0') + ':' +
                   String(seconds).padStart(2, '0');
        }
        return String(minutes).padStart(2, '0') + ':' + String(seconds).padStart(2, '0');
    }
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = AudioRecorder;
}
