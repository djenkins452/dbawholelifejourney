/* Legacy — minimal, CSP-safe interactions (no inline handlers). */
(function () {
    'use strict';

    function ready(fn) {
        if (document.readyState !== 'loading') { fn(); }
        else { document.addEventListener('DOMContentLoaded', fn); }
    }

    function csrfFrom(form) {
        var el = form && form.querySelector('[name=csrfmiddlewaretoken]');
        if (el) return el.value;
        var m = document.cookie.match(/csrftoken=([^;]+)/);
        return m ? m[1] : '';
    }

    function toast(msg) {
        var t = document.getElementById('legacyToast');
        if (!t) { return; }
        t.textContent = msg;
        t.hidden = false;
        t.classList.add('show');
        clearTimeout(t._timer);
        t._timer = setTimeout(function () { t.classList.remove('show'); t.hidden = true; }, 2600);
    }

    ready(function () {
        // Progress bars: width set via JS (CSP blocks inline style attributes).
        document.querySelectorAll('.lg-progress-fill[data-progress]').forEach(function (el) {
            var pct = parseInt(el.getAttribute('data-progress'), 10) || 0;
            requestAnimationFrame(function () { el.style.width = Math.max(0, Math.min(100, pct)) + '%'; });
        });

        // Notifications panel toggle.
        var bell = document.getElementById('legacyBell');
        var panel = document.getElementById('legacyNotifPanel');
        if (bell && panel) {
            bell.addEventListener('click', function (e) {
                e.stopPropagation();
                var open = !panel.hidden;
                panel.hidden = open;
                bell.setAttribute('aria-expanded', String(!open));
            });
            document.addEventListener('click', function (e) {
                if (!panel.hidden && !panel.contains(e.target) && e.target !== bell) {
                    panel.hidden = true; bell.setAttribute('aria-expanded', 'false');
                }
            });
        }

        // ⌘K / Ctrl+K focuses Legacy search.
        var search = document.querySelector('.legacy-search-input');
        if (search) {
            document.addEventListener('keydown', function (e) {
                if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
                    if (document.querySelector('.legacy-root')) { e.preventDefault(); search.focus(); }
                }
            });
        }

        // Confirmation modal (two-stage permanent delete, etc.).
        var confirmModal = document.getElementById('confirmModal');
        if (confirmModal) {
            var pendingForm = null;
            var okBtn = document.getElementById('confirmOk');
            var titleEl = document.getElementById('confirmTitle');
            var msgEl = document.getElementById('confirmMsg');
            function closeConfirm() { confirmModal.hidden = true; pendingForm = null; }
            document.addEventListener('click', function (e) {
                var trig = e.target.closest && e.target.closest('.js-confirm-delete');
                if (trig) {
                    e.preventDefault();
                    pendingForm = trig.closest('form');
                    if (titleEl) { titleEl.textContent = trig.getAttribute('data-confirm-title') || 'Permanently delete this?'; }
                    if (msgEl) { msgEl.textContent = trig.getAttribute('data-confirm-msg') || 'This action cannot be undone.'; }
                    confirmModal.hidden = false;
                    return;
                }
                if (e.target.closest && e.target.closest('.js-confirm-cancel')) { closeConfirm(); return; }
                if (e.target === confirmModal) { closeConfirm(); }
            });
            if (okBtn) { okBtn.addEventListener('click', function () { if (pendingForm) { pendingForm.submit(); } }); }
            document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !confirmModal.hidden) { closeConfirm(); } });
        }

        // Library: auto-submit on select / file change.
        document.querySelectorAll('.lg-autosubmit').forEach(function (sel) {
            sel.addEventListener('change', function () { if (sel.form) sel.form.submit(); });
        });
        // Media library / any file input that should submit its form on selection.
        document.querySelectorAll('.js-autoupload').forEach(function (inp) {
            inp.addEventListener('change', function () { if (inp.files.length && inp.form) inp.form.submit(); });
        });

        // Placeholder buttons — anything genuinely not built yet.
        document.querySelectorAll('.js-legacy-soon').forEach(function (btn) {
            btn.addEventListener('click', function () { toast(btn.getAttribute('data-note') || 'Coming soon.'); });
        });

        // Cleanup undo + place "Search again" (delegated — panel is injected).
        document.addEventListener('click', function (e) {
            if (!e.target.closest) { return; }
            var undo = e.target.closest('.js-cleanup-undo');
            if (undo) {
                e.preventDefault();
                var wrap = undo.closest('[data-cleanup]');
                var mForm = document.getElementById('memoryForm');
                undo.disabled = true;
                fetch(undo.getAttribute('data-url'), {
                    method: 'POST',
                    headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrfFrom(mForm) },
                    credentials: 'same-origin'
                }).then(function (r) { return r.json(); }).then(function (d) {
                    if (d && d.ok) {
                        var b = document.getElementById('memoryBody');
                        if (b) { b.value = d.body; b.dispatchEvent(new Event('input', { bubbles: true })); }
                        if (wrap) { wrap.parentNode.removeChild(wrap); }
                        toast('Restored your original wording.');
                    } else { undo.disabled = false; }
                }).catch(function () { undo.disabled = false; });
                return;
            }
        });

        // Media Detail: filter the "add to more stories" picker as you type.
        var mdSearch = document.querySelector('.md-search-in');
        if (mdSearch) {
            var mdPicks = Array.prototype.slice.call(document.querySelectorAll('.md-pick'));
            var mdEmpty = document.querySelector('.md-picker-empty');
            mdSearch.addEventListener('input', function () {
                var q = mdSearch.value.trim().toLowerCase();
                var shown = 0;
                mdPicks.forEach(function (p) {
                    var match = !q || (p.getAttribute('data-title') || '').indexOf(q) > -1;
                    p.hidden = !match;
                    if (match) { shown++; }
                });
                if (mdEmpty) { mdEmpty.hidden = shown > 0; }
            });
        }

        // Voice capture — browser speech-to-text, transcribed live into the story.
        var talkBtn = document.getElementById('talkBtn');
        var voiceBody = document.getElementById('memoryBody');
        var talkLabel = document.getElementById('talkBtnLabel');
        if (talkBtn && voiceBody) {
            var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
            if (!SR) {
                talkBtn.addEventListener('click', function () {
                    toast('Voice needs a browser like Chrome or Safari — you can keep typing here.');
                });
            } else {
                var rec = new SR();
                rec.continuous = true; rec.interimResults = true; rec.lang = 'en-US';
                var listening = false, baseText = '';
                function setListening(on) {
                    listening = on;
                    talkBtn.classList.toggle('is-recording', on);
                    talkBtn.setAttribute('aria-pressed', String(on));
                    if (talkLabel) { talkLabel.textContent = on ? 'Listening…' : 'Talk'; }
                }
                talkBtn.addEventListener('click', function () {
                    if (listening) { rec.stop(); return; }
                    baseText = voiceBody.value ? voiceBody.value.replace(/\s+$/, '') + ' ' : '';
                    try { rec.start(); } catch (e) { /* already starting */ }
                });
                rec.onstart = function () { setListening(true); };
                rec.onend = function () { setListening(false); };
                rec.onerror = function (e) {
                    setListening(false);
                    if (e && (e.error === 'not-allowed' || e.error === 'service-not-allowed')) {
                        toast('Microphone access is blocked — allow it in your browser to talk.');
                    }
                };
                rec.onresult = function (e) {
                    var interim = '', finalTxt = '';
                    for (var i = e.resultIndex; i < e.results.length; i++) {
                        var t = e.results[i][0].transcript;
                        if (e.results[i].isFinal) { finalTxt += t; } else { interim += t; }
                    }
                    if (finalTxt) { baseText += finalTxt; }
                    voiceBody.value = baseText + interim;
                    // Feed autosave + Discover exactly as if typed.
                    voiceBody.dispatchEvent(new Event('input', { bubbles: true }));
                };
            }
        }

        // Story Discovery Engine — Discover button.
        var discoverBtn = document.getElementById('discoverBtn');
        var discoveryPanel = document.getElementById('discoveryPanel');
        if (discoverBtn && discoveryPanel) {
            var mForm = document.getElementById('memoryForm');
            var lbl = document.getElementById('discoverBtnLabel');
            discoverBtn.addEventListener('click', function () {
                if (discoverBtn.disabled || !mForm) { return; }
                discoverBtn.disabled = true;
                discoverBtn.classList.add('is-loading');
                if (lbl) { lbl.textContent = 'Reading your story…'; }
                var fd = new FormData(mForm);
                fetch(discoverBtn.getAttribute('data-url'), {
                    method: 'POST',
                    headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrfFrom(mForm) },
                    body: fd, credentials: 'same-origin'
                }).then(function (r) { return r.json(); }).then(function (d) {
                    if (d && d.ok) {
                        var pkInput = document.getElementById('memoryPk');
                        if (pkInput && !pkInput.value && d.pk) {
                            pkInput.value = d.pk;
                            if (window.history.replaceState) {
                                window.history.replaceState({}, '', '/legacy/memories/' + d.pk + '/edit/');
                            }
                        }
                        // Auto-title: fill an empty title with the suggestion (editable).
                        if (d.suggested_title) {
                            var titleEl = document.getElementById('memoryTitle');
                            if (titleEl && !titleEl.value.trim()) {
                                titleEl.value = d.suggested_title;
                                titleEl.dispatchEvent(new Event('input', { bubbles: true }));
                            }
                        }
                        // Cleanup phase: reflect the gently tidied text in the editor.
                        if (d.cleaned_body) {
                            var bodyEl = document.getElementById('memoryBody');
                            if (bodyEl && bodyEl.value !== d.cleaned_body) {
                                bodyEl.value = d.cleaned_body;
                                bodyEl.dispatchEvent(new Event('input', { bubbles: true }));
                            }
                        }
                        discoveryPanel.innerHTML = d.html || '';
                        // While reviewing findings, hide the persistent connections.
                        var sc = document.getElementById('storyConnections');
                        if (sc) { sc.hidden = true; }
                        discoveryPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                    }
                }).catch(function () {
                    discoveryPanel.innerHTML = '<p class="discovery-msg">Something interrupted discovery. Your memory is saved — try again in a moment.</p>';
                }).then(function () {
                    discoverBtn.disabled = false;
                    discoverBtn.classList.remove('is-loading');
                    if (lbl) { lbl.textContent = 'Discover'; }
                });
            });
            // Delegated handlers for the (dynamically injected) review panel.
            function syncDisc(wrap) {
                var lab = wrap.querySelector('[name^="edit_label_"]');
                var nameEl = wrap.querySelector('.disc-person-name') || wrap.querySelector('.disc-chip-text');
                if (lab && nameEl && lab.value.trim()) { nameEl.textContent = lab.value.trim(); }
                var rel = wrap.querySelector('[name^="edit_rel_"]');
                var relEl = wrap.querySelector('.disc-person-rel');
                if (rel && relEl) { relEl.textContent = rel.value ? (rel.value.charAt(0).toUpperCase() + rel.value.slice(1)) : ''; }
            }
            document.addEventListener('click', function (e) {
                if (!e.target.closest) { return; }
                if (e.target.closest('.js-discovery-cancel')) {
                    discoveryPanel.innerHTML = '';
                    var scx = document.getElementById('storyConnections');
                    if (scx) { scx.hidden = false; }
                    return;
                }
                var editBtn = e.target.closest('.js-disc-edit');
                if (editBtn) {
                    e.preventDefault(); e.stopPropagation();
                    var w = editBtn.closest('[data-disc]');
                    if (w) {
                        w.classList.toggle('is-editing');
                        if (w.classList.contains('is-editing')) {
                            var inp = w.querySelector('.disc-edit-in, .disc-chip-edit');
                            if (inp) { inp.focus(); }
                        } else { syncDisc(w); }
                    }
                    return;
                }
                var doneBtn = e.target.closest('.disc-edit-done');
                if (doneBtn) {
                    e.preventDefault();
                    var wd = doneBtn.closest('[data-disc]');
                    if (wd) { wd.classList.remove('is-editing'); syncDisc(wd); }
                    return;
                }
                var mp = e.target.closest('.js-mp-focus');
                if (mp) {
                    var b = document.getElementById('memoryBody');
                    if (b) { b.focus(); b.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
                    return;
                }
            });
        }

        // Editor autosave (debounced).
        var form = document.getElementById('memoryForm');
        if (form) {
            var title = document.getElementById('memoryTitle');
            var body = document.getElementById('memoryBody');
            var pkInput = document.getElementById('memoryPk');
            var indicator = document.getElementById('editorAutosave');
            var timer = null;
            var lastSaved = '';
            // NB: a field named "action" shadows form.action (returns a RadioNodeList),
            // so always read the URL from the attribute.
            var actionUrl = form.getAttribute('action');

            function snapshot() { return (title ? title.value : '') + ' ' + (body ? body.value : ''); }
            lastSaved = snapshot();
            var pkPromise = null;   // in-flight "create this memory" request, if any

            // Create the memory EXACTLY ONCE, even when several triggers fire at
            // once (a photo drop racing the debounced autosave). Without this, two
            // pk-less saves each create a separate memory and the just-uploaded
            // photo attaches to the wrong one — the "media not staying attached" bug.
            function ensurePk() {
                if (pkInput && pkInput.value) { return Promise.resolve(pkInput.value); }
                if (pkPromise) { return pkPromise; }
                var fd = new FormData(form); fd.set('action', 'autosave');
                pkPromise = fetch(actionUrl, {
                    method: 'POST',
                    headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrfFrom(form) },
                    body: fd, credentials: 'same-origin'
                }).then(function (r) { return r.json(); }).then(function (d) {
                    pkPromise = null;
                    if (d && d.ok && d.pk) {
                        if (pkInput && !pkInput.value) {
                            pkInput.value = d.pk;
                            if (d.edit_url && window.history.replaceState) { window.history.replaceState({}, '', d.edit_url); }
                        }
                        lastSaved = snapshot();
                        return d.pk;
                    }
                    throw new Error('save failed');
                }).catch(function (e) { pkPromise = null; throw e; });
                return pkPromise;
            }

            function autosave() {
                if (snapshot() === lastSaved) { return; }
                if (pkInput && !pkInput.value) { ensurePk().catch(function () { if (indicator) { indicator.textContent = 'Not saved'; } }); return; }
                if (indicator) { indicator.textContent = 'Saving…'; }
                var fd = new FormData(form);
                fd.set('action', 'autosave');
                fetch(actionUrl, {
                    method: 'POST',
                    headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrfFrom(form) },
                    body: fd,
                    credentials: 'same-origin'
                }).then(function (r) { return r.json(); }).then(function (d) {
                    if (d && d.ok) {
                        lastSaved = snapshot();
                        if (pkInput && !pkInput.value && d.pk) {
                            pkInput.value = d.pk;
                            if (d.edit_url && window.history.replaceState) {
                                window.history.replaceState({}, '', d.edit_url);
                            }
                        }
                        if (indicator) { indicator.textContent = 'Saved ' + (d.saved_at || ''); }
                    } else if (indicator) { indicator.textContent = 'Not saved'; }
                }).catch(function () { if (indicator) { indicator.textContent = 'Not saved'; } });
            }

            function schedule() {
                if (indicator) { indicator.textContent = 'Editing…'; }
                clearTimeout(timer);
                timer = setTimeout(autosave, 1500);
            }
            if (title) { title.addEventListener('input', schedule); }
            if (body) { body.addEventListener('input', schedule); }

            var mediaPanel = document.getElementById('editorMedia');
            if (mediaPanel) {
                var grid = document.getElementById('editorMediaGrid');
                var fileInput = document.getElementById('mediaFileInput');
                var drop = document.getElementById('mediaDrop');

                function appendThumb(it) {
                    if (!grid) { return; }
                    var d = document.createElement('div');
                    d.className = 'editor-media-thumb type-' + it.type;
                    d.setAttribute('data-media-id', it.id);
                    if (it.is_photo && it.thumb_url) {
                        var img = document.createElement('img'); img.src = it.thumb_url; img.alt = ''; d.appendChild(img);
                    } else {
                        var s = document.createElement('span'); s.className = 'editor-media-kind'; s.textContent = it.kind_display; d.appendChild(s);
                    }
                    var rm = document.createElement('button');
                    rm.type = 'button'; rm.className = 'editor-media-rm js-media-remove';
                    rm.setAttribute('data-media-id', it.id); rm.setAttribute('aria-label', 'Remove from this story');
                    rm.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/></svg>';
                    d.appendChild(rm);
                    grid.appendChild(d);
                    grid.hidden = false;
                }

                function uploadFiles(files) {
                    if (!files || !files.length) { return; }
                    mediaPanel.classList.add('is-uploading');
                    ensurePk().then(function (pk) {
                        var fd = new FormData();
                        for (var i = 0; i < files.length; i++) { fd.append('file', files[i]); }
                        return fetch('/legacy/memories/' + pk + '/media/add/', {
                            method: 'POST',
                            headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrfFrom(form) },
                            body: fd, credentials: 'same-origin'
                        });
                    }).then(function (r) { return r.json(); }).then(function (d) {
                        mediaPanel.classList.remove('is-uploading');
                        if (d && d.ok) {
                            (d.items || []).forEach(appendThumb);
                            if (d.skipped) { toast(d.skipped); }
                        } else { toast('That didn\'t upload — try again in a moment.'); }
                    }).catch(function () {
                        mediaPanel.classList.remove('is-uploading');
                        toast('That didn\'t upload — try again in a moment.');
                    });
                }

                if (fileInput) {
                    fileInput.addEventListener('change', function () { uploadFiles(fileInput.files); fileInput.value = ''; });
                }
                if (drop) {
                    ['dragenter', 'dragover'].forEach(function (ev) {
                        drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add('is-drag'); });
                    });
                    drop.addEventListener('dragleave', function (e) {
                        if (!drop.contains(e.relatedTarget)) { drop.classList.remove('is-drag'); }
                    });
                    drop.addEventListener('drop', function (e) {
                        e.preventDefault(); drop.classList.remove('is-drag');
                        if (e.dataTransfer && e.dataTransfer.files) { uploadFiles(e.dataTransfer.files); }
                    });
                }

                document.addEventListener('click', function (e) {
                    var rm = e.target.closest && e.target.closest('.js-media-remove');
                    if (!rm) { return; }
                    e.preventDefault();
                    var id = rm.getAttribute('data-media-id');
                    var pk = pkInput ? pkInput.value : '';
                    var thumb = rm.closest('.editor-media-thumb');
                    if (!pk || !id) { if (thumb) { thumb.parentNode.removeChild(thumb); } return; }
                    fetch('/legacy/memories/' + pk + '/media/' + id + '/remove/', {
                        method: 'POST',
                        headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrfFrom(form) },
                        credentials: 'same-origin'
                    }).then(function (r) { return r.json(); }).then(function (d) {
                        if (d && d.ok && thumb) { thumb.parentNode.removeChild(thumb); }
                    }).catch(function () {});
                });
            }

            // Save any pending edits when leaving.
            window.addEventListener('beforeunload', function () { if (snapshot() !== lastSaved) { navigator.sendBeacon && (function () {
                var fd = new FormData(form); fd.set('action', 'autosave');
                try { navigator.sendBeacon(actionUrl, fd); } catch (e) {}
            })(); } });
        }
    });
})();
