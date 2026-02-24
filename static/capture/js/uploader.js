/**
 * Audio File Uploader Module
 *
 * Handles client-side file validation and chunked uploads for audio files.
 */

class AudioUploader {
    constructor(options = {}) {
        this.maxFileSize = options.maxFileSize || 60 * 1024 * 1024; // 60MB default
        this.chunkSize = options.chunkSize || 5 * 1024 * 1024; // 5MB chunks
        this.acceptedTypes = options.acceptedTypes || [
            'audio/mpeg',
            'audio/mp4',
            'audio/wav',
            'audio/webm',
            'audio/x-m4a',
            'audio/ogg',
            'audio/aac',
            'audio/x-caf',
            'video/mp4',
        ];
        this.acceptedExtensions = options.acceptedExtensions || [
            '.mp3', '.m4a', '.mp4', '.wav', '.webm', '.ogg', '.caf'
        ];
        this.uploadUrl = options.uploadUrl || '/capture/upload/';
        this.csrfToken = options.csrfToken || '';

        this.onProgress = options.onProgress || (() => {});
        this.onSuccess = options.onSuccess || (() => {});
        this.onError = options.onError || console.error;
    }

    /**
     * Validate a file before upload
     * @param {File} file - The file to validate
     * @returns {Object} - { valid: boolean, error?: string }
     */
    validateFile(file) {
        // Check file type
        const ext = '.' + file.name.split('.').pop().toLowerCase();
        const isValidType = this.acceptedTypes.includes(file.type) ||
                           this.acceptedExtensions.includes(ext);

        if (!isValidType) {
            return {
                valid: false,
                error: 'Invalid file type. Please upload MP3, M4A, MP4, WAV, WebM, OGG, or CAF files.'
            };
        }

        // Check file size
        if (file.size > this.maxFileSize) {
            const maxSizeMB = Math.round(this.maxFileSize / (1024 * 1024));
            return {
                valid: false,
                error: `File too large. Maximum size is ${maxSizeMB}MB.`
            };
        }

        // Check if file is empty
        if (file.size === 0) {
            return {
                valid: false,
                error: 'File is empty. Please select a valid audio file.'
            };
        }

        return { valid: true };
    }

    /**
     * Format file size for display
     * @param {number} bytes - File size in bytes
     * @returns {string} - Formatted file size
     */
    static formatFileSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    /**
     * Upload a file (automatically chooses direct or chunked upload)
     * @param {File} file - The file to upload
     */
    async upload(file) {
        const validation = this.validateFile(file);
        if (!validation.valid) {
            this.onError(validation.error);
            return;
        }

        try {
            if (file.size <= this.chunkSize) {
                await this.uploadDirect(file);
            } else {
                await this.uploadChunked(file);
            }
        } catch (error) {
            this.onError(error.message || 'Upload failed. Please try again.');
        }
    }

    /**
     * Direct upload for small files
     * @param {File} file - The file to upload
     */
    async uploadDirect(file) {
        return new Promise((resolve, reject) => {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('csrfmiddlewaretoken', this.csrfToken);

            const xhr = new XMLHttpRequest();
            xhr.open('POST', this.uploadUrl);

            xhr.upload.onprogress = (e) => {
                if (e.lengthComputable) {
                    const percent = Math.round((e.loaded / e.total) * 100);
                    this.onProgress(percent, e.loaded, e.total);
                }
            };

            xhr.onload = () => {
                if (xhr.status === 200) {
                    try {
                        const response = JSON.parse(xhr.responseText);
                        if (response.success) {
                            this.onSuccess(response);
                            resolve(response);
                        } else {
                            const error = response.error || 'Upload failed.';
                            this.onError(error);
                            reject(new Error(error));
                        }
                    } catch (e) {
                        this.onError('Invalid server response');
                        reject(new Error('Invalid server response'));
                    }
                } else {
                    const error = 'Upload failed. Server returned status ' + xhr.status;
                    this.onError(error);
                    reject(new Error(error));
                }
            };

            xhr.onerror = () => {
                const error = 'Network error. Please check your connection.';
                this.onError(error);
                reject(new Error(error));
            };

            xhr.send(formData);
        });
    }

    /**
     * Chunked upload for large files
     * @param {File} file - The file to upload
     */
    async uploadChunked(file) {
        const totalChunks = Math.ceil(file.size / this.chunkSize);

        // Initialize upload session
        const initResponse = await fetch(this.uploadUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.csrfToken
            },
            body: JSON.stringify({
                action: 'init_chunked',
                filename: file.name,
                filesize: file.size,
                total_chunks: totalChunks
            })
        });

        if (!initResponse.ok) {
            throw new Error('Failed to initialize upload');
        }

        const initData = await initResponse.json();
        const sessionId = initData.session_id;

        // Upload chunks
        for (let i = 0; i < totalChunks; i++) {
            const start = i * this.chunkSize;
            const end = Math.min(start + this.chunkSize, file.size);
            const chunk = file.slice(start, end);

            const formData = new FormData();
            formData.append('chunk', chunk);
            formData.append('chunk_index', i);
            formData.append('session_id', sessionId);
            formData.append('csrfmiddlewaretoken', this.csrfToken);

            const chunkResponse = await fetch(this.uploadUrl, {
                method: 'POST',
                body: formData
            });

            if (!chunkResponse.ok) {
                throw new Error('Failed to upload chunk ' + (i + 1));
            }

            const percent = Math.round(((i + 1) / totalChunks) * 100);
            const loaded = Math.min((i + 1) * this.chunkSize, file.size);
            this.onProgress(percent, loaded, file.size);
        }

        // Complete upload
        const completeResponse = await fetch(this.uploadUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.csrfToken
            },
            body: JSON.stringify({
                action: 'complete_chunked',
                session_id: sessionId
            })
        });

        if (!completeResponse.ok) {
            throw new Error('Failed to complete upload');
        }

        const completeData = await completeResponse.json();
        if (completeData.success) {
            this.onSuccess(completeData);
        } else {
            throw new Error(completeData.error || 'Upload failed');
        }
    }

    /**
     * Get accepted file extensions as a string for file input accept attribute
     * @returns {string}
     */
    getAcceptString() {
        return this.acceptedExtensions.join(',') + ',' + this.acceptedTypes.join(',');
    }
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = AudioUploader;
}
