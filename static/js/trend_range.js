/* ==========================================================================
 * trend_range.js — reusable client for the shared TREND-RANGE interaction.
 *
 * Domain-agnostic. It knows how to: switch the active range button, fetch the
 * server's authoritative JSON payload for that range, and present it — animating
 * stat values (count-up) and fading the subtitle. It does NOT compute anything;
 * every number comes from the server. Chart updates are delegated: the controller
 * dispatches a `trendrange:updated` event carrying the payload, and each page's
 * tiny chart script listens and animates its own chart instance.
 *
 * DOM contract (a page opts in with these data-attributes):
 *   [data-trend-range][data-trend-endpoint="/path/"]   the selector container
 *     a[data-trend-option="6m"]                         one anchor per range
 *   [data-trend-stat="low"]                             a stat tile, containing…
 *     [data-trend-stat-label] / [data-trend-stat-value]
 *   [data-trend-subtitle]                               subtitle wrapper (tone class)
 *     [data-trend-subtitle-range] / [data-trend-subtitle-change]
 *   [data-trend-empty]                                  "no data in range" note
 *
 * Payload shape (from the server, identical to the initial HTML render):
 *   { range:{key,suffix,label}, options:[{key,label,active}],
 *     has_range_data, stats:[{key,label,value,display,tone}],
 *     subtitle:{range_line,change_line,tone}, chart:{labels,data}, empty_note }
 * ========================================================================== */
(function () {
    "use strict";

    var ANIM_MS = 550;

    function ease(t) { return 1 - Math.pow(1 - t, 3); }   // easeOutCubic

    // Split "−9.2 lb" / "282.9 lb" / "—" into prefix, number, suffix so we can
    // animate the number while preserving units/sign and decimal precision.
    function parseDisplay(text) {
        var m = /^(\D*)(-?\d+(?:\.\d+)?)(.*)$/.exec(text || "");
        if (!m) return null;
        var decimals = m[2].indexOf(".") >= 0 ? m[2].split(".")[1].length : 0;
        return { prefix: m[1], value: parseFloat(m[2]), suffix: m[3], decimals: decimals };
    }

    function countUp(el, toDisplay) {
        var target = parseDisplay(toDisplay);
        if (!target) { el.textContent = toDisplay; return; }     // e.g. "—"
        var from = parseDisplay(el.textContent);
        var start = from ? from.value : target.value;
        var t0 = null;
        function frame(ts) {
            if (t0 === null) t0 = ts;
            var p = Math.min(1, (ts - t0) / ANIM_MS);
            var cur = start + (target.value - start) * ease(p);
            el.textContent = target.prefix + cur.toFixed(target.decimals) + target.suffix;
            if (p < 1) { requestAnimationFrame(frame); }
            else { el.textContent = toDisplay; }                 // exact final string
        }
        requestAnimationFrame(frame);
    }

    var TONES = ["tone-success", "tone-warning"];
    function applyTone(el, tone) {
        if (!el) return;
        TONES.forEach(function (c) { el.classList.remove(c); });
        if (tone) el.classList.add("tone-" + tone);
    }

    function render(root, payload) {
        // Active button state (server is authoritative via payload.options).
        var active = payload.range && payload.range.key;
        root.querySelectorAll("[data-trend-option]").forEach(function (btn) {
            var on = btn.getAttribute("data-trend-option") === active;
            btn.classList.toggle("is-active", on);
            if (on) { btn.setAttribute("aria-current", "true"); }
            else { btn.removeAttribute("aria-current"); }
        });

        var scope = root.closest("[data-trend-scope]") || document;

        // Stats — label swaps instantly, value counts up.
        (payload.stats || []).forEach(function (s) {
            var tile = scope.querySelector('[data-trend-stat="' + s.key + '"]');
            if (!tile) return;
            var labelEl = tile.querySelector("[data-trend-stat-label]");
            var valueEl = tile.querySelector("[data-trend-stat-value]");
            if (labelEl) labelEl.textContent = s.label;
            if (valueEl) { applyTone(valueEl, s.tone); countUp(valueEl, s.display); }
        });

        // Subtitle — gentle fade swap.
        var sub = scope.querySelector("[data-trend-subtitle]");
        if (sub) {
            var rangeEl = sub.querySelector("[data-trend-subtitle-range]");
            var changeEl = sub.querySelector("[data-trend-subtitle-change]");
            sub.classList.add("is-swapping");
            window.setTimeout(function () {
                if (rangeEl) rangeEl.textContent = payload.subtitle.range_line || "";
                if (changeEl) changeEl.textContent = payload.subtitle.change_line || "";
                applyTone(changeEl, payload.subtitle.tone);
                sub.classList.remove("is-swapping");
            }, 160);
        }

        // Empty-in-range note.
        var emptyEl = scope.querySelector("[data-trend-empty]");
        if (emptyEl) {
            var showEmpty = payload.has_range_data === false;
            emptyEl.textContent = showEmpty ? (payload.empty_note || "") : "";
            emptyEl.hidden = !showEmpty;
        }

        // Chart is page-specific — hand the payload to whoever owns the chart.
        root.dispatchEvent(new CustomEvent("trendrange:updated", {
            bubbles: true, detail: payload,
        }));
    }

    function select(root, key) {
        var endpoint = root.getAttribute("data-trend-endpoint") || window.location.pathname;
        var url = endpoint + (endpoint.indexOf("?") >= 0 ? "&" : "?") +
            "range=" + encodeURIComponent(key) + "&fmt=json";
        root.classList.add("is-loading");
        fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" }, credentials: "same-origin" })
            .then(function (r) {
                if (!r.ok) throw new Error("HTTP " + r.status);
                return r.json();
            })
            .then(function (payload) {
                render(root, payload);
                // Keep the URL shareable/refresh-safe (server also persists the choice).
                try {
                    var u = new URL(window.location.href);
                    u.searchParams.set("range", key);
                    window.history.replaceState({}, "", u);
                } catch (e) { /* history unavailable — non-fatal */ }
            })
            .catch(function () {
                // Network/parse failure → fall back to a full navigation (still correct).
                window.location.href = endpoint +
                    (endpoint.indexOf("?") >= 0 ? "&" : "?") + "range=" + encodeURIComponent(key);
            })
            .finally(function () { root.classList.remove("is-loading"); });
    }

    function bind(root) {
        root.addEventListener("click", function (ev) {
            var btn = ev.target.closest("[data-trend-option]");
            if (!btn || !root.contains(btn)) return;
            ev.preventDefault();
            var key = btn.getAttribute("data-trend-option");
            if (btn.classList.contains("is-active")) return;   // no-op re-select
            select(root, key);
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("[data-trend-range]").forEach(bind);
    });
})();
