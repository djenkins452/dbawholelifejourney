/*
 * WLJ shared Person component — hover card + click-to-open for ANY recognized person
 * reference (`<span data-mention data-person-id="N">…</span>`), anywhere in WLJ.
 *
 * ONE implementation, many consumers: Journal, Tasks, Prayer, Documents, Notes and every
 * future surface get identity-confirmation-on-hover and navigation-on-click for free —
 * there is no per-module hover logic. Loaded globally from base.html and fully
 * event-delegated, so it costs nothing until a chip is actually hovered or clicked.
 *
 *   Hover = confirm WLJ recognized the right person (lightweight card).
 *   Click = open that person's full page.
 *
 * Performance: card data is fetched once per person and cached; hover is debounced so we
 * never fetch on raw mouse movement. Recognition chips inside the editor (.ProseMirror /
 * contenteditable) are ignored — that is an editing context, not a reading one.
 */
(function () {
  "use strict";

  var cache = {};                 // pk -> Promise<data|null>
  var card = null, showTimer = null, hideTimer = null, currentPk = null;

  function inEditor(el) {
    return !!(el.closest && el.closest('.ProseMirror, [contenteditable="true"]'));
  }
  function chipFrom(el) {
    return (el && el.closest) ? el.closest('[data-mention][data-person-id]') : null;
  }
  function esc(s) {
    var d = document.createElement("div");
    d.textContent = (s == null) ? "" : String(s);
    return d.innerHTML;
  }

  function fetchCard(pk) {
    if (!cache[pk]) {
      cache[pk] = fetch("/people/api/" + pk + "/card/", {
        headers: { "X-Requested-With": "XMLHttpRequest" }, credentials: "same-origin"
      }).then(function (r) { return r.ok ? r.json() : null; })
        .catch(function () { return null; });
    }
    return cache[pk];
  }

  function ensureCard() {
    if (card) return card;
    card = document.createElement("div");
    card.className = "wlj-person-card";
    card.setAttribute("role", "dialog");
    card.style.display = "none";
    card.addEventListener("mouseenter", function () { clearTimeout(hideTimer); });
    card.addEventListener("mouseleave", scheduleHide);
    document.body.appendChild(card);
    return card;
  }

  function render(data) {
    var chips = (data.recognition || []).map(function (n) {
      return '<span class="wlj-pc-chip">' + esc(n) + "</span>";
    }).join("");
    return '<div class="wlj-pc-name">' + esc(data.name) + "</div>"
      + (data.relationship ? '<div class="wlj-pc-rel">' + esc(data.relationship) + "</div>" : "")
      + (chips
          ? '<div class="wlj-pc-section-label">Recognized as</div>'
            + '<div class="wlj-pc-chips">' + chips + "</div>"
          : "")
      + '<a class="wlj-pc-open" href="' + esc(data.url) + '">Open Person →</a>';
  }

  function position(chip) {
    var r = chip.getBoundingClientRect();
    var c = card.getBoundingClientRect();
    var docW = document.documentElement.clientWidth;
    var docH = document.documentElement.clientHeight;
    var left = Math.min(r.left + window.scrollX, window.scrollX + docW - c.width - 8);
    left = Math.max(window.scrollX + 8, left);
    var top = r.bottom + window.scrollY + 6;
    if (r.bottom + c.height + 12 > docH) top = r.top + window.scrollY - c.height - 6;
    card.style.left = left + "px";
    card.style.top = top + "px";
  }

  function show(chip) {
    var pk = chip.getAttribute("data-person-id");
    currentPk = pk;
    ensureCard();
    fetchCard(pk).then(function (data) {
      if (currentPk !== pk || !data) return;   // hover moved on, or no data
      card.innerHTML = render(data);
      card.style.display = "block";
      position(chip);
    });
  }

  function scheduleHide() {
    clearTimeout(hideTimer);
    hideTimer = setTimeout(function () {
      if (card) card.style.display = "none";
      currentPk = null;
    }, 180);
  }

  document.addEventListener("mouseover", function (e) {
    var chip = chipFrom(e.target);
    if (!chip || inEditor(chip)) return;
    clearTimeout(hideTimer);
    clearTimeout(showTimer);
    showTimer = setTimeout(function () { show(chip); }, 220);   // hover intent
  });
  document.addEventListener("mouseout", function (e) {
    var chip = chipFrom(e.target);
    if (!chip || inEditor(chip)) return;
    clearTimeout(showTimer);
    scheduleHide();
  });
  document.addEventListener("click", function (e) {
    var chip = chipFrom(e.target);
    if (!chip || inEditor(chip)) return;      // editing context navigates nowhere
    e.preventDefault();
    var pk = chip.getAttribute("data-person-id");
    fetchCard(pk).then(function (data) {
      window.location.href = (data && data.url) ? data.url : ("/people/" + pk + "/");
    });
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") scheduleHide();
  });
})();
