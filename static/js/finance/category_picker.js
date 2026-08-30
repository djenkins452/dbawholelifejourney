/* ==========================================================================
 * File: static/js/finance/category_picker.js
 * Project: Whole Life Journey
 * Description: In-place transaction category selection and creation.
 * Owner: Danny Jenkins (admin@wholelifejourney.com)
 * ==========================================================================
 *
 * ONE behaviour shared by the transaction list, transaction detail and attribution
 * review surfaces. Event delegation on `document`, so rows added later (pagination,
 * a re-rendered review queue) work without re-binding.
 *
 * CSP: no inline handlers anywhere — every listener is attached here, and every piece
 * of context comes from a data-* attribute rather than a function argument.
 */
(function () {
    "use strict";

    function csrfToken() {
        var match = document.cookie.match(/csrftoken=([^;]+)/);
        return match ? match[1] : "";
    }

    function pickerOf(el) {
        return el ? el.closest("[data-cat-picker]") : null;
    }

    function endpointFor(picker) {
        /* The real reversed URL, rendered per row by Django — never assembled here,
         * so a route change cannot silently strand the client. */
        return picker.getAttribute("data-cat-url");
    }

    function say(picker, message, isError) {
        var status = picker.querySelector("[data-cat-status]");
        if (!status) { return; }
        status.textContent = message || "";
        status.classList.toggle("cat-status-error", Boolean(isError));
    }

    function setBusy(picker, busy) {
        picker.classList.toggle("cat-busy", busy);
        var select = picker.querySelector("[data-cat-select]");
        if (select) { select.disabled = busy; }
    }

    function showNewField(picker, show) {
        var wrap = picker.querySelector("[data-cat-new]");
        if (!wrap) { return; }
        wrap.hidden = !show;
        if (show) {
            var input = wrap.querySelector("[data-cat-new-input]");
            if (input) { input.value = ""; input.focus(); }
        }
    }

    /* Put a newly created category into every picker on the page, so the next row
     * can choose it without a reload. */
    function addOptionEverywhere(category) {
        document.querySelectorAll("[data-cat-select]").forEach(function (select) {
            if (select.querySelector('option[value="' + category.id + '"]')) { return; }
            var option = document.createElement("option");
            option.value = String(category.id);
            option.textContent = category.name;
            var createOption = select.querySelector('option[value="__new__"]');
            select.insertBefore(option, createOption);
        });
    }

    function send(picker, body, previousValue) {
        setBusy(picker, true);
        say(picker, "Saving…");

        fetch(endpointFor(picker), {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
            body: JSON.stringify(body)
        }).then(function (response) {
            return response.json().then(function (data) {
                return { ok: response.ok, data: data };
            });
        }).then(function (result) {
            setBusy(picker, false);
            var select = picker.querySelector("[data-cat-select]");

            if (!result.ok || !result.data.success) {
                say(picker, result.data.error || "Could not save that.", true);
                if (select && previousValue !== undefined) { select.value = previousValue; }
                return;
            }

            var category = result.data.category;
            if (category) {
                if (result.data.created) { addOptionEverywhere(category); }
                if (select) { select.value = String(category.id); }
                say(picker, result.data.created ? "Created and applied."
                          : result.data.reused ? "Used your existing category."
                          : "Saved.");
            } else {
                if (select) { select.value = ""; }
                say(picker, "Cleared.");
            }
            showNewField(picker, false);

            picker.dispatchEvent(new CustomEvent("wlj:category-changed", {
                bubbles: true,
                detail: { transactionId: picker.getAttribute("data-transaction-id"),
                          category: category }
            }));
        }).catch(function () {
            setBusy(picker, false);
            say(picker, "Could not reach the server.", true);
            var select = picker.querySelector("[data-cat-select]");
            if (select && previousValue !== undefined) { select.value = previousValue; }
        });
    }

    /* Remember what was selected BEFORE the change, so a failure can put it back
     * rather than leaving the control showing something that was never saved. */
    document.addEventListener("focusin", function (event) {
        var select = event.target.closest("[data-cat-select]");
        if (select) { select.setAttribute("data-previous", select.value); }
    });

    document.addEventListener("change", function (event) {
        var select = event.target.closest("[data-cat-select]");
        if (!select) { return; }
        var picker = pickerOf(select);
        if (!picker) { return; }

        if (select.value === "__new__") {
            select.value = select.getAttribute("data-previous") || "";
            showNewField(picker, true);
            say(picker, "");
            return;
        }
        send(picker, { category_id: select.value ? Number(select.value) : null },
             select.getAttribute("data-previous") || "");
    });

    document.addEventListener("click", function (event) {
        var save = event.target.closest("[data-cat-new-save]");
        if (save) {
            var picker = pickerOf(save);
            var input = picker.querySelector("[data-cat-new-input]");
            var name = (input && input.value || "").trim();
            if (!name) { say(picker, "Give the category a name.", true);
                         if (input) { input.focus(); } return; }
            send(picker, { new_name: name });
            return;
        }

        var cancel = event.target.closest("[data-cat-new-cancel]");
        if (cancel) {
            var cancelPicker = pickerOf(cancel);
            showNewField(cancelPicker, false);
            say(cancelPicker, "");
            var sel = cancelPicker.querySelector("[data-cat-select]");
            if (sel) { sel.focus(); }
        }
    });

    /* Enter submits the new name; Escape abandons it. Both without a mouse. */
    document.addEventListener("keydown", function (event) {
        var input = event.target.closest("[data-cat-new-input]");
        if (!input) { return; }
        if (event.key === "Enter") {
            event.preventDefault();
            var save = pickerOf(input).querySelector("[data-cat-new-save]");
            if (save) { save.click(); }
        } else if (event.key === "Escape") {
            event.preventDefault();
            var cancel = pickerOf(input).querySelector("[data-cat-new-cancel]");
            if (cancel) { cancel.click(); }
        }
    });
})();
