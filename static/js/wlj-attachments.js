/**
 * WLJ Universal Attachments — shared client-side intake helpers.
 *
 * ONE implementation consumed by BOTH chat surfaces (assistant_panel.html desktop
 * dock + chat_widget.html mobile drawer) — the "build once, reuse everywhere"
 * platform surface (docs/WLJ_MULTIMODAL_INTAKE_ARCHITECTURE.md).
 *
 * Milestone 1 scope — IMAGES end-to-end:
 *   - Intelligent client-side normalization: EXIF-correct orientation, downscale
 *     large photos, and compress under the server size cap so the user almost
 *     never sees "file too large" and photos are never sideways.
 *   - HEIC/HEIF → JPEG conversion where the engine can decode it (WebKit / the
 *     iOS WKWebView app and Safari) — the primary iPhone path.
 *   - Drag-and-drop onto the chat input.
 *   - (Photos / Take-a-photo / Browse come from the OS sheet once the file
 *     input `accept` is widened — no extra JS needed.)
 *
 * Non-image types (PDF/audio/video/docs) are a later milestone (server ingestion
 * + perception); this module exposes hooks (`fileKind`) for that expansion.
 *
 * CSP: loaded via <script src> (same-origin, 'self'); no inline handlers.
 */
(function () {
    'use strict';

    var MAX_DIM = 2048;                       // longest edge after downscale
    var TARGET_MAX_BYTES = 4.5 * 1024 * 1024; // stay under the 5 MB server cap
    var INPUT_MAX_BYTES = 40 * 1024 * 1024;   // refuse to decode absurd inputs
    var JPEG_QUALITY = 0.85;

    // Image types we accept for selection. HEIC/HEIF included — converted to JPEG
    // client-side on WebKit (iPhone). GIF kept as-is to preserve animation.
    var IMAGE_ACCEPT = [
        'image/jpeg', 'image/png', 'image/gif', 'image/webp',
        'image/heic', 'image/heif', '.heic', '.heif',
    ].join(',');

    function isImage(file) {
        if (!file) return false;
        if (file.type && file.type.indexOf('image/') === 0) return true;
        // Some browsers report an empty type for HEIC — fall back to extension.
        return /\.(heic|heif)$/i.test(file.name || '');
    }

    function isHeic(file) {
        return /image\/hei[cf]/i.test(file.type || '') ||
               /\.(heic|heif)$/i.test(file.name || '');
    }

    // Coarse content class for the (future) universal preview + routing.
    function fileKind(file) {
        var t = (file && file.type) || '';
        if (isImage(file)) return 'image';
        if (t.indexOf('audio/') === 0) return 'audio';
        if (t.indexOf('video/') === 0) return 'video';
        if (t === 'application/pdf' || /\.pdf$/i.test(file.name || '')) return 'pdf';
        if (/word|excel|powerpoint|spreadsheet|presentation|document|csv|text\//.test(t)) {
            return 'document';
        }
        return 'other';
    }

    function _blobToDataURL(blob) {
        return new Promise(function (resolve, reject) {
            var r = new FileReader();
            r.onload = function () { resolve(r.result); };
            r.onerror = function () { reject(new Error('read failed')); };
            r.readAsDataURL(blob);
        });
    }

    function _fileToStored(file) {
        // Pass-through: return the {data, mimeType, dataUrl} shape both chat
        // surfaces store, WITHOUT re-encoding (preserves GIF animation, and
        // already-small images that need no work).
        return _blobToDataURL(file).then(function (dataUrl) {
            return {
                data: (dataUrl.split(',')[1] || ''),
                mimeType: file.type || 'application/octet-stream',
                dataUrl: dataUrl,
                name: file.name || '',
            };
        });
    }

    function _canvasToStored(canvas, mime) {
        return new Promise(function (resolve, reject) {
            canvas.toBlob(function (blob) {
                if (!blob) { reject(new Error('encode failed')); return; }
                _blobToDataURL(blob).then(function (dataUrl) {
                    resolve({
                        data: (dataUrl.split(',')[1] || ''),
                        mimeType: mime,
                        dataUrl: dataUrl,
                        name: '',
                    });
                }).catch(reject);
            }, mime, JPEG_QUALITY);
        });
    }

    /**
     * Normalize an image File into the stored {data, mimeType, dataUrl} shape.
     * Returns a Promise. Rejects with {message} for user-facing failures.
     */
    function prepareImage(file) {
        if (!isImage(file)) {
            return Promise.reject({ message: 'That file is not an image.' });
        }
        if (file.size > INPUT_MAX_BYTES) {
            return Promise.reject({
                message: 'That image is extremely large (over 40 MB) and can’t be processed.',
            });
        }

        // GIF: keep as-is (canvas would flatten animation) if already small enough.
        if ((file.type === 'image/gif') && file.size <= TARGET_MAX_BYTES) {
            return _fileToStored(file);
        }

        // Decode with EXIF orientation applied. Decoding lets us catch large
        // DIMENSIONS (e.g. a 4000px screenshot that is small in bytes), not just
        // large byte size. Old engines that lack createImageBitmap fall back.
        if (typeof createImageBitmap !== 'function') {
            if (isHeic(file)) {
                return Promise.reject({
                    message: 'HEIC images aren’t supported in this browser. They work from your iPhone, or convert to JPEG first.',
                });
            }
            return _fileToStored(file);
        }

        return createImageBitmap(file, { imageOrientation: 'from-image' })
            .then(function (bitmap) {
                var w = bitmap.width, h = bitmap.height;
                var maxSide = Math.max(w, h);
                var needsResize = maxSide > MAX_DIM;
                // Re-encode when: too many pixels, too many bytes, a JPEG (bake
                // EXIF orientation), or HEIC (convert). Otherwise keep the
                // original bytes to avoid needless quality loss.
                var needsWork = needsResize ||
                                file.size > TARGET_MAX_BYTES ||
                                file.type === 'image/jpeg' ||
                                isHeic(file);
                if (!needsWork) {
                    if (bitmap.close) { try { bitmap.close(); } catch (e) {} }
                    return _fileToStored(file);
                }

                var scale = Math.min(1, MAX_DIM / maxSide);
                var cw = Math.max(1, Math.round(w * scale));
                var ch = Math.max(1, Math.round(h * scale));
                var canvas = document.createElement('canvas');
                canvas.width = cw;
                canvas.height = ch;
                var ctx = canvas.getContext('2d');
                ctx.drawImage(bitmap, 0, 0, cw, ch);
                if (bitmap.close) { try { bitmap.close(); } catch (e) {} }

                // Preserve PNG for screenshots/alpha; everything else → JPEG.
                var outMime = (file.type === 'image/png') ? 'image/png' : 'image/jpeg';
                return _canvasToStored(canvas, outMime).then(function (stored) {
                    // If a PNG result is still over the cap, fall back to JPEG.
                    if (stored.data.length * 0.75 > TARGET_MAX_BYTES &&
                        outMime !== 'image/jpeg') {
                        return _canvasToStored(canvas, 'image/jpeg');
                    }
                    return stored;
                });
            })
            .catch(function () {
                // Decode failed (e.g. HEIC on a non-WebKit engine).
                if (isHeic(file)) {
                    return Promise.reject({
                        message: 'HEIC images aren’t supported in this browser. They work from your iPhone, or convert to JPEG first.',
                    });
                }
                // Non-HEIC decode failure → try to send the original.
                return _fileToStored(file);
            });
    }

    /**
     * Wire drag-and-drop on a drop zone. onFiles receives a FileList/array.
     * Adds/removes a CSS class so the surface can show a drop affordance.
     */
    function attachDragAndDrop(dropZone, onFiles, opts) {
        if (!dropZone || typeof onFiles !== 'function') return;
        opts = opts || {};
        var overClass = opts.overClass || 'wlj-drag-over';
        var depth = 0;

        function stop(e) { e.preventDefault(); e.stopPropagation(); }

        dropZone.addEventListener('dragenter', function (e) {
            stop(e); depth++; dropZone.classList.add(overClass);
        });
        dropZone.addEventListener('dragover', function (e) {
            stop(e);
            if (e.dataTransfer) { try { e.dataTransfer.dropEffect = 'copy'; } catch (x) {} }
        });
        dropZone.addEventListener('dragleave', function (e) {
            stop(e); depth = Math.max(0, depth - 1);
            if (depth === 0) dropZone.classList.remove(overClass);
        });
        dropZone.addEventListener('drop', function (e) {
            stop(e); depth = 0; dropZone.classList.remove(overClass);
            var files = e.dataTransfer && e.dataTransfer.files;
            if (files && files.length) onFiles(files);
        });
    }

    window.WLJAttachments = {
        IMAGE_ACCEPT: IMAGE_ACCEPT,
        isImage: isImage,
        isHeic: isHeic,
        fileKind: fileKind,
        prepareImage: prepareImage,
        attachDragAndDrop: attachDragAndDrop,
        limits: { MAX_DIM: MAX_DIM, TARGET_MAX_BYTES: TARGET_MAX_BYTES },
    };
})();
