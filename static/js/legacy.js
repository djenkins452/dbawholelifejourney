/* Legacy — minimal, CSP-safe interactions (no inline handlers). */
(function () {
    'use strict';

    function ready(fn) {
        if (document.readyState !== 'loading') { fn(); }
        else { document.addEventListener('DOMContentLoaded', fn); }
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
                    panel.hidden = true;
                    bell.setAttribute('aria-expanded', 'false');
                }
            });
        }

        // ⌘K / Ctrl+K focuses Legacy search.
        var search = document.querySelector('.legacy-search-input');
        if (search) {
            document.addEventListener('keydown', function (e) {
                if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
                    var scope = document.querySelector('.legacy-root');
                    if (scope) { e.preventDefault(); search.focus(); }
                }
            });
        }
    });
})();
