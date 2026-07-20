/**
 * WLJ Attachment Framework — the canonical, DOMAIN-AGNOSTIC attachment platform.
 *
 * ONE reusable component that can be dropped into ANY WLJ page (chat, meals,
 * medical, journal, faith, relationships, finance, operations, future domains)
 * with config, not customization. The framework knows nothing about the domain
 * it serves; the consuming page declares behavior
 * (docs/WLJ_MULTIMODAL_INTAKE_ARCHITECTURE.md §10).
 *
 * TWO layers:
 *   1. Low-level helpers (stable): `prepareImage` (EXIF orientation, downscale,
 *      HEIC→JPEG, compress under cap), `fileKind`, `attachDragAndDrop`,
 *      `sniff`/`isImage`. Reusable on their own.
 *   2. The framework controller: `WLJAttachments.mount(config)` — a self-managing
 *      attachment set (select / validate / normalize / upload-with-progress /
 *      preview chips + thumbs / remove) driven entirely by config:
 *        - `classes`         which content classes are allowed
 *        - `maxItems`        max attachments
 *        - `endpoint`        upload destination
 *        - `uploadParams`    artifact association (e.g. {associate_to:'meal:12'})
 *        - `previewStyle`    'mixed' | 'chips' | 'thumbs'
 *        - `onUploaded/onChange/onProgress/onError`  post-upload behavior
 *      The controller exposes `getArtifactIds()`, `getImagesPayload()`,
 *      `clear()`, `remove()`, `hasPending()` — a generic interface every
 *      consumer uses the same way.
 *
 * Reusable UI: attachment chips/thumbs are rendered by the framework (per-type
 * icons, name, size, progress, remove) — not chat-specific markup. Styles live
 * in static/css/wlj-attachments.css.
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

    // Coarse content class — MUST match the server kind taxonomy
    // (apps/ai/upload_validation.py: image / document / audio / video). PDF and
    // Office/text all map to 'document'. Uses declared type first, extension as
    // fallback (some OS pickers report an empty type for .md/.m4a/etc.).
    function fileKind(file) {
        var t = ((file && file.type) || '').toLowerCase();
        var name = ((file && file.name) || '').toLowerCase();
        if (isImage(file)) return 'image';
        if (t.indexOf('audio/') === 0 || /\.(mp3|m4a|wav|aac|ogg|caf)$/.test(name)) return 'audio';
        if (t.indexOf('video/') === 0 || /\.(mov|mp4|m4v|hevc|avi|webm|mkv)$/.test(name)) return 'video';
        if (t === 'application/pdf' || /\.pdf$/.test(name)) return 'document';
        if (/word|excel|powerpoint|spreadsheet|presentation|officedocument|document|csv|text\//.test(t) ||
            /\.(docx|xlsx|pptx|txt|md|markdown|csv)$/.test(name)) {
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

    // ── Universal accept string (all supported classes) ──────────────────────
    var UNIVERSAL_ACCEPT = [
        IMAGE_ACCEPT, 'image/tiff', '.tif', '.tiff',
        'application/pdf', '.pdf',
        '.docx', '.xlsx', '.pptx',
        'text/plain', 'text/markdown', 'text/csv', '.txt', '.md', '.csv',
        'audio/*', '.mp3', '.m4a', '.wav', '.aac',
        'video/*', '.mov', '.mp4',
    ].join(',');

    // ── Reusable UI: per-type icons + chip/thumb renderer ────────────────────
    var _ICONS = {
        image: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>',
        document: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8M8 17h8"/></svg>',
        audio: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>',
        video: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="4" width="14" height="16" rx="2"/><path d="M22 8l-6 4 6 4V8z"/></svg>',
        other: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M13 2v7h7"/></svg>',
    };
    var _X_ICON = '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';

    function _fmtSize(bytes) {
        if (!bytes) return '';
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    function _renderPreview(container, items, opts) {
        opts = opts || {};
        var style = opts.style || 'mixed';
        container.innerHTML = '';
        container.classList.add('wlj-attach-preview');
        container.hidden = items.length === 0;
        if (!items.length) return;

        items.forEach(function (item) {
            var asThumb = (style !== 'chips') && item.kind === 'image' && item.dataUrl;
            var el = document.createElement('div');
            el.className = asThumb ? 'wlj-attach-thumb' : 'wlj-attach-chip';
            el.setAttribute('data-status', item.status);

            if (asThumb) {
                var img = document.createElement('img');
                img.src = item.dataUrl; img.alt = item.name || 'image';
                el.appendChild(img);
            } else {
                var icon = document.createElement('span');
                icon.className = 'wlj-attach-icon';
                icon.innerHTML = _ICONS[item.kind] || _ICONS.other;
                el.appendChild(icon);
                var meta = document.createElement('span');
                meta.className = 'wlj-attach-meta';
                var nm = document.createElement('span');
                nm.className = 'wlj-attach-name'; nm.textContent = item.name || item.kind;
                var sz = document.createElement('span');
                sz.className = 'wlj-attach-size'; sz.textContent = _fmtSize(item.size);
                meta.appendChild(nm); meta.appendChild(sz);
                el.appendChild(meta);
            }

            // Progress / status affordance.
            if (item.status === 'uploading') {
                var bar = document.createElement('span');
                bar.className = 'wlj-attach-progress';
                var fill = document.createElement('span');
                fill.className = 'wlj-attach-progress-fill';
                fill.style.width = Math.round((item.progress || 0) * 100) + '%';
                bar.appendChild(fill);
                el.appendChild(bar);
            } else if (item.status === 'error') {
                el.classList.add('is-error');
                el.title = item.error || 'Upload failed';
            }

            var rm = document.createElement('button');
            rm.type = 'button';
            rm.className = 'wlj-attach-remove';
            rm.setAttribute('aria-label', 'Remove ' + (item.name || 'attachment'));
            rm.innerHTML = _X_ICON;
            rm.addEventListener('click', function () {
                if (opts.onRemove) opts.onRemove(item.localId);
            });
            el.appendChild(rm);

            container.appendChild(el);
        });
    }

    // ── Helpers for the controller ───────────────────────────────────────────
    function _getCsrf() {
        var m = document.cookie.match(/csrftoken=([^;]+)/);
        return m ? m[1] : '';
    }

    function _base64ToBlob(b64, mime) {
        var chars = atob(b64);
        var bytes = new Uint8Array(chars.length);
        for (var i = 0; i < chars.length; i++) bytes[i] = chars.charCodeAt(i);
        return new Blob([bytes], { type: mime || 'application/octet-stream' });
    }

    // ── The framework controller ─────────────────────────────────────────────
    function mount(config) {
        config = config || {};
        var endpoint = config.endpoint || '/assistant/api/attachments/';
        var classes = config.classes || ['image', 'document', 'audio', 'video'];
        var maxItems = config.maxItems || 5;
        var previewStyle = config.previewStyle || 'mixed';
        var normalizeImages = config.normalizeImages !== false;
        var keepImageData = !!config.keepImageData;
        // May be a boolean OR a predicate(item)→bool — preserve it as given
        // (do NOT coerce; `fn !== false` would collapse a predicate to `true`).
        var autoUpload = (config.autoUpload === undefined) ? true : config.autoUpload;
        var previewContainer = config.previewContainer || null;
        var items = [];
        var seq = 0;

        function notifyError(msg) {
            if (config.onError) config.onError(msg);
            else if (msg) { try { alert(msg); } catch (e) {} }
        }
        function publicItems() {
            return items.map(function (it) {
                return {
                    localId: it.localId, name: it.name, size: it.size, kind: it.kind,
                    mime: it.mime, status: it.status, artifactId: it.artifactId,
                    progress: it.progress,
                };
            });
        }
        function render() {
            if (previewContainer) {
                _renderPreview(previewContainer, items, { style: previewStyle, onRemove: remove });
            }
        }
        function changed() {
            if (config.onChange) config.onChange(publicItems());
            render();
        }

        function addFiles(fileList) {
            var arr = Array.prototype.slice.call(fileList || []);
            arr.forEach(function (file) {
                if (items.length >= maxItems) {
                    notifyError('You can attach up to ' + maxItems + ' files.');
                    return;
                }
                var kind = fileKind(file);
                if (classes.indexOf(kind) === -1) {
                    notifyError('That type of file isn’t allowed here.');
                    return;
                }
                var item = {
                    localId: ++seq, file: file, name: file.name || '',
                    size: file.size || 0, kind: kind, mime: file.type || '',
                    status: 'pending', artifactId: null, dataUrl: null, data: null,
                    progress: 0, error: null,
                };
                items.push(item);
                changed();
                _process(item);
            });
        }

        // autoUpload may be a boolean OR a predicate(item)→bool, so a consumer can
        // upload some kinds and handle others itself (e.g. chat keeps images inline
        // for immediate perception) — config, never a chat-specific branch here.
        function _shouldUpload(item) {
            return (typeof autoUpload === 'function') ? !!autoUpload(item) : !!autoUpload;
        }

        function _process(item) {
            if (item.kind === 'image' && normalizeImages) {
                prepareImage(item.file).then(function (img) {
                    item.mime = img.mimeType;
                    item.dataUrl = img.dataUrl;               // for thumbnail preview
                    if (keepImageData) item.data = img.data;  // inline perception (chat)
                    if (_shouldUpload(item)) _upload(item, _base64ToBlob(img.data, img.mimeType), item.name);
                    else { item.status = 'ready'; changed(); }
                }).catch(function (err) {
                    item.status = 'error';
                    item.error = (err && err.message) || 'Could not read image';
                    notifyError(item.error);
                    changed();
                });
            } else if (_shouldUpload(item)) {
                _upload(item, item.file, item.name);
            } else {
                item.status = 'ready';
                changed();
            }
        }

        function _upload(item, blob, name) {
            item.status = 'uploading'; item.progress = 0; changed();
            var xhr = new XMLHttpRequest();
            xhr.open('POST', endpoint);
            xhr.setRequestHeader('X-CSRFToken', config.csrfToken || _getCsrf());
            if (xhr.upload) {
                xhr.upload.onprogress = function (e) {
                    if (e.lengthComputable) {
                        item.progress = e.loaded / e.total;
                        if (config.onProgress) config.onProgress(item.localId, item.progress);
                        render();
                    }
                };
            }
            xhr.onload = function () {
                var data = null;
                try { data = JSON.parse(xhr.responseText); } catch (e) {}
                var att = data && data.attachments && data.attachments[0];
                if (xhr.status === 200 && data && data.success && att) {
                    item.artifactId = att.artifact_id;
                    item.kind = att.kind || item.kind;
                    item.mime = att.content_type || item.mime;
                    item.size = att.size || item.size;
                    item.status = 'uploaded'; item.progress = 1;
                    if (config.onUploaded) config.onUploaded(publicItems().filter(function (x) {
                        return x.localId === item.localId;
                    })[0]);
                } else {
                    item.status = 'error';
                    item.error = (data && data.error) || 'Upload failed';
                    notifyError(item.error);
                }
                changed();
            };
            xhr.onerror = function () {
                item.status = 'error'; item.error = 'Upload failed';
                notifyError(item.error); changed();
            };
            var fd = new FormData();
            fd.append('file', blob, name);
            if (config.uploadParams) {
                Object.keys(config.uploadParams).forEach(function (k) {
                    fd.append(k, config.uploadParams[k]);
                });
            }
            xhr.send(fd);
        }

        function remove(localId) {
            items = items.filter(function (it) { return it.localId !== localId; });
            if (config.onRemove) config.onRemove(localId);
            changed();
        }
        function clear() { items = []; changed(); }
        function getArtifactIds() {
            return items.filter(function (it) { return it.status === 'uploaded' && it.artifactId; })
                        .map(function (it) { return it.artifactId; });
        }
        function getImagesPayload() {
            return items.filter(function (it) { return it.kind === 'image' && it.data; })
                        .map(function (it) { return { data: it.data, mime: it.mime }; });
        }
        // Sent-message receipts — a durable record the surface renders in the user's bubble.
        function getReceipts() {
            return items.map(function (it) {
                return {
                    filename: it.name || it.kind, kind: it.kind,
                    status: (it.status === 'uploaded' ? 'ready'
                             : it.status === 'error' ? 'failed' : (it.status || 'ready')),
                };
            });
        }
        function hasPending() {
            return items.some(function (it) {
                return it.status === 'uploading' || it.status === 'pending';
            });
        }
        // Resolve once every attachment has reached a TERMINAL state (uploaded / error /
        // ready) — so a caller can wait for in-flight uploads before reading getArtifactIds().
        // This closes the race where Send fires mid-upload and the artifact_id is dropped
        // (and then orphaned by clear()). Resolves immediately when nothing is pending; a
        // timeout guarantees Send is never blocked indefinitely by a stuck upload.
        function whenReady(timeoutMs) {
            return new Promise(function (resolve) {
                if (!hasPending()) return resolve();
                var start = Date.now();
                var iv = setInterval(function () {
                    if (!hasPending() || (timeoutMs && Date.now() - start > timeoutMs)) {
                        clearInterval(iv);
                        resolve();
                    }
                }, 100);
            });
        }

        // Wire the provided input / triggers / drop zone.
        if (config.input) {
            config.input.addEventListener('change', function () {
                if (config.input.files && config.input.files.length) {
                    addFiles(config.input.files);
                    config.input.value = '';
                }
            });
        }
        (config.triggers || []).forEach(function (t) {
            if (t && config.input) t.addEventListener('click', function () { config.input.click(); });
        });
        if (config.dropZone) attachDragAndDrop(config.dropZone, addFiles);

        return {
            addFiles: addFiles, remove: remove, clear: clear,
            getArtifactIds: getArtifactIds, getImagesPayload: getImagesPayload,
            getReceipts: getReceipts,
            hasPending: hasPending, whenReady: whenReady, render: render,
            count: function () { return items.length; },
            items: publicItems,
        };
    }

    // Render sent-message attachment RECEIPTS into a message bubble (both chat surfaces + on
    // history load). A durable, visible record that a file was attached — documents have no
    // inline image, so without this the transcript hides the upload.
    function renderReceipts(container, receipts) {
        if (!container || !receipts || !receipts.length) return;
        var wrap = document.createElement('div');
        wrap.className = 'wlj-attach-receipts';
        var STATE = { ready: 'Attached', processing: 'Reading…', failed: 'Upload failed',
                      unreadable: "Couldn't read" };
        receipts.forEach(function (r) {
            var chip = document.createElement('span');
            chip.className = 'wlj-attach-receipt is-' + (r.status || 'ready');
            var icon = document.createElement('span');
            icon.className = 'wlj-attach-icon';
            icon.innerHTML = _ICONS[r.kind] || _ICONS.other;
            var nm = document.createElement('span');
            nm.className = 'wlj-attach-name';
            nm.textContent = r.filename || 'attachment';
            var st = document.createElement('span');
            st.className = 'wlj-attach-receipt-state';
            st.textContent = STATE[r.status] || STATE.ready;
            chip.appendChild(icon); chip.appendChild(nm); chip.appendChild(st);
            wrap.appendChild(chip);
        });
        container.appendChild(wrap);
    }

    window.WLJAttachments = {
        IMAGE_ACCEPT: IMAGE_ACCEPT,
        UNIVERSAL_ACCEPT: UNIVERSAL_ACCEPT,
        isImage: isImage,
        isHeic: isHeic,
        fileKind: fileKind,
        prepareImage: prepareImage,
        attachDragAndDrop: attachDragAndDrop,
        renderPreview: _renderPreview,
        renderReceipts: renderReceipts,
        mount: mount,
        limits: { MAX_DIM: MAX_DIM, TARGET_MAX_BYTES: TARGET_MAX_BYTES },
    };
})();
