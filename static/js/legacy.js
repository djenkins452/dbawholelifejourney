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
        var mediaInput = document.getElementById('mediaFileInput');
        if (mediaInput) {
            mediaInput.addEventListener('change', function () { if (mediaInput.files.length && mediaInput.form) mediaInput.form.submit(); });
        }
        // Media library / any file input that should submit its form on selection.
        document.querySelectorAll('.js-autoupload').forEach(function (inp) {
            inp.addEventListener('change', function () { if (inp.files.length && inp.form) inp.form.submit(); });
        });

        // Placeholder buttons (voice-to-text, analyze) — no AI in Phase 1.
        document.querySelectorAll('.js-legacy-soon').forEach(function (btn) {
            btn.addEventListener('click', function () { toast(btn.getAttribute('data-note') || 'Coming soon.'); });
        });

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
                        discoveryPanel.innerHTML = d.html || '';
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
                if (e.target.closest('.js-discovery-cancel')) { discoveryPanel.innerHTML = ''; return; }
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

            function autosave() {
                if (snapshot() === lastSaved) { return; }
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
            // Save any pending edits when leaving.
            window.addEventListener('beforeunload', function () { if (snapshot() !== lastSaved) { navigator.sendBeacon && (function () {
                var fd = new FormData(form); fd.set('action', 'autosave');
                try { navigator.sendBeacon(actionUrl, fd); } catch (e) {}
            })(); } });
        }
    });
})();
