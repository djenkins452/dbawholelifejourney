/* ==========================================================================
 * wlj-confirmation.js — the ONE shared Rich Confirmation renderer.
 * docs/WLJ_RICH_CONFIRMATION_ARCHITECTURE.md
 *
 * Both chat surfaces (desktop panel + mobile drawer) consume this — no surface
 * or feature builds its own confirmation UI. It renders a presentation-independent
 * confirmation card (title / summary / preview / primary + secondary actions with
 * primary|secondary|danger styles), handles expired / already-resolved / executing
 * states, and resolves a click DETERMINISTICALLY through POST /assistant/api/confirm/
 * (the SAME engine a typed "yes" uses — no model call). CSP-safe: no inline handlers.
 *
 * API:
 *   WLJConfirmation.render(container, card, { onResult })  → renders the card
 *   WLJConfirmation.applyResolved({confirmation_id, status})  → marks a prior card
 * where `card` = {confirmation_id, status, expires_in, title, summary, preview[],
 *                 actions:{primary, secondary[]}}.
 * ========================================================================== */
(function () {
  "use strict";

  var ENDPOINT = "/assistant/api/confirm/";

  function csrf() {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    if (m) return decodeURIComponent(m[1]);
    var el = document.querySelector('input[name=csrfmiddlewaretoken]');
    return el ? el.value : "";
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function styleClass(style) {
    if (style === "danger") return "wlj-confirm-btn wlj-confirm-danger";
    if (style === "secondary") return "wlj-confirm-btn wlj-confirm-secondary";
    return "wlj-confirm-btn wlj-confirm-primary";
  }

  // Build the (non-button) content shared by every state.
  function buildBody(card) {
    var frag = document.createDocumentFragment();
    if (card.title) frag.appendChild(el("div", "wlj-confirm-title", card.title));
    if (card.summary) frag.appendChild(el("div", "wlj-confirm-summary", card.summary));
    var preview = card.preview || [];
    if (preview.length) {
      var ul = el("ul", "wlj-confirm-preview");
      preview.forEach(function (line) { ul.appendChild(el("li", null, line)); });
      frag.appendChild(ul);
    }
    return frag;
  }

  function orderedActions(card) {
    var a = (card.actions || {});
    var list = [];
    if (a.primary) list.push(a.primary);
    (a.secondary || []).forEach(function (s) { list.push(s); });
    return list;
  }

  function setStatusNote(root, text) {
    var old = root.querySelector(".wlj-confirm-note");
    if (old) old.remove();
    if (text) root.appendChild(el("div", "wlj-confirm-note", text));
  }

  function disable(root, executingKey) {
    root.classList.add("wlj-confirm-executing");
    root.querySelectorAll(".wlj-confirm-btn").forEach(function (b) {
      b.disabled = true;
      b.setAttribute("aria-disabled", "true");
      if (b.getAttribute("data-key") === executingKey) b.classList.add("wlj-confirm-busy");
    });
  }

  function markResolved(root, status) {
    root.classList.remove("wlj-confirm-executing");
    root.classList.add("wlj-confirm-done");
    root.setAttribute("data-status", status || "resolved");
    var actions = root.querySelector(".wlj-confirm-actions");
    if (actions) actions.remove();
    var note = { resolved: "Done.", cancelled: "Cancelled.",
                 already_resolved: "Already handled.", expired: "This confirmation expired.",
                 error: "That couldn't be completed." }[status] || "";
    setStatusNote(root, note);
  }

  function resolve(root, card, key, opts) {
    if (root.classList.contains("wlj-confirm-executing") ||
        root.classList.contains("wlj-confirm-done")) return;
    disable(root, key);
    fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      credentials: "same-origin",
      body: JSON.stringify({ confirmation_id: card.confirmation_id, choice: key })
    }).then(function (r) { return r.json(); }).then(function (data) {
      var st = (data.confirmation_resolved && data.confirmation_resolved.status) ||
               (data.success ? "resolved" : "error");
      markResolved(root, st);
      if (data.response && opts && typeof opts.onResult === "function") {
        opts.onResult(data.response, data.confirmation_resolved || {});
      }
    }).catch(function () {
      root.classList.remove("wlj-confirm-executing");
      root.querySelectorAll(".wlj-confirm-btn").forEach(function (b) {
        b.disabled = false; b.removeAttribute("aria-disabled"); b.classList.remove("wlj-confirm-busy");
      });
      setStatusNote(root, "Network error — try again.");
    });
  }

  function render(container, card, opts) {
    if (!container || !card || !card.confirmation_id) return null;
    opts = opts || {};
    var root = el("div", "wlj-confirm");
    root.setAttribute("role", "group");
    root.setAttribute("aria-label", "Confirmation: " + (card.title || "action"));
    root.setAttribute("data-confirmation-id", card.confirmation_id);
    root.setAttribute("data-status", card.status || "pending");
    root.appendChild(buildBody(card));

    var status = card.status || "pending";
    if (status !== "pending") {
      markResolved(root, status);
      container.appendChild(root);
      return root;
    }

    var actions = el("div", "wlj-confirm-actions");
    orderedActions(card).forEach(function (a) {
      if (!a || !a.key) return;
      var btn = el("button", styleClass(a.style), a.label || a.key);
      btn.type = "button";
      btn.setAttribute("data-key", a.key);
      btn.addEventListener("click", function () { resolve(root, card, a.key, opts); });
      btn.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); resolve(root, card, a.key, opts); }
      });
      actions.appendChild(btn);
    });
    root.appendChild(actions);
    container.appendChild(root);
    return root;
  }

  // Mark a previously-rendered card (found by id) as resolved/cancelled — used when a TYPED
  // confirm/cancel resolved it (the server tells us which card via confirmation_resolved).
  function applyResolved(meta) {
    if (!meta || !meta.confirmation_id) return;
    var root = document.querySelector(
      '.wlj-confirm[data-confirmation-id="' + (meta.confirmation_id + "").replace(/"/g, "") + '"]');
    if (root && !root.classList.contains("wlj-confirm-done")) {
      markResolved(root, meta.status || "resolved");
    }
  }

  window.WLJConfirmation = { render: render, applyResolved: applyResolved };
})();
