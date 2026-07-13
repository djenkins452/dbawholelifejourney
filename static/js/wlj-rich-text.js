/**
 * WLJ Rich Text Editor — platform glue.
 *
 * ONE editor for all of WLJ. Finds every `<textarea data-wlj-rte>` (rendered by
 * apps/core/widgets.py :: WLJRichTextWidget), hides it, and mounts a TipTap editor
 * + toolbar around it. The editor's HTML is mirrored back into the textarea on
 * every change, so normal form submission posts sanitized-on-save HTML with no
 * per-form JavaScript. Self-hosted bundle (window.WLJTipTap) — no CDN.
 *
 * CSP-safe: external file, all listeners via addEventListener, no inline handlers.
 * Idempotent: guards against double-mount so htmx/turbo swaps are safe.
 */
(function () {
  'use strict';

  // ---- small helpers -------------------------------------------------------
  function svg(inner) {
    return (
      '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" ' +
      'stroke="currentColor" stroke-width="2" stroke-linecap="round" ' +
      'stroke-linejoin="round" aria-hidden="true">' + inner + '</svg>'
    );
  }

  function getCsrfToken() {
    var input = document.querySelector('[name=csrfmiddlewaretoken]');
    if (input && input.value) return input.value;
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : '';
  }

  // ---- toolbar definition --------------------------------------------------
  // Each control: {name, title, html, run(editor), active(editor)?}. Grouped so
  // the toolbar can wrap/collapse gracefully on narrow screens (CSS handles it).
  var ICONS = {
    bold: svg('<path d="M6 4h8a4 4 0 0 1 0 8H6z"/><path d="M6 12h9a4 4 0 0 1 0 8H6z"/>'),
    italic: svg('<line x1="19" y1="4" x2="10" y2="4"/><line x1="14" y1="20" x2="5" y2="20"/><line x1="15" y1="4" x2="9" y2="20"/>'),
    underline: svg('<path d="M6 3v7a6 6 0 0 0 12 0V3"/><line x1="4" y1="21" x2="20" y2="21"/>'),
    strike: svg('<line x1="4" y1="12" x2="20" y2="12"/><path d="M16 6c-.5-1.5-2-2.5-4-2.5C9 3.5 7.5 5 7.5 7c0 1 .5 1.8 1.5 2.5"/><path d="M8 17c.5 1.5 2 2.5 4 2.5 2.2 0 4-1.2 4-3.2"/>'),
    code: svg('<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>'),
    h1: null, h2: null, h3: null,
    bullet: svg('<line x1="9" y1="6" x2="20" y2="6"/><line x1="9" y1="12" x2="20" y2="12"/><line x1="9" y1="18" x2="20" y2="18"/><circle cx="4" cy="6" r="1.5"/><circle cx="4" cy="12" r="1.5"/><circle cx="4" cy="18" r="1.5"/>'),
    ordered: svg('<line x1="10" y1="6" x2="21" y2="6"/><line x1="10" y1="12" x2="21" y2="12"/><line x1="10" y1="18" x2="21" y2="18"/><path d="M4 6h1v4"/><path d="M4 10h2"/><path d="M6 16.5A1.5 1.5 0 1 0 4.7 18"/>'),
    task: svg('<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>'),
    quote: svg('<path d="M3 21c3 0 7-1 7-8V5a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h1"/><path d="M14 21c3 0 7-1 7-8V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h1"/>'),
    hr: svg('<line x1="3" y1="12" x2="21" y2="12"/>'),
    link: svg('<path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1"/><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"/>'),
    image: svg('<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/>'),
    table: svg('<rect x="3" y="3" width="18" height="18" rx="1"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/><line x1="9" y1="3" x2="9" y2="21"/><line x1="15" y1="3" x2="15" y2="21"/>'),
    alignLeft: svg('<line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="15" y2="12"/><line x1="3" y1="18" x2="18" y2="18"/>'),
    alignCenter: svg('<line x1="3" y1="6" x2="21" y2="6"/><line x1="7" y1="12" x2="17" y2="12"/><line x1="5" y1="18" x2="19" y2="18"/>'),
    alignRight: svg('<line x1="3" y1="6" x2="21" y2="6"/><line x1="9" y1="12" x2="21" y2="12"/><line x1="6" y1="18" x2="21" y2="18"/>'),
    undo: svg('<path d="M9 14L4 9l5-5"/><path d="M4 9h11a6 6 0 0 1 0 12h-3"/>'),
    redo: svg('<path d="M15 14l5-5-5-5"/><path d="M20 9H9a6 6 0 0 0 0 12h3"/>'),
  };

  function textButton(label) {
    return '<span class="wlj-rte-btn-text">' + label + '</span>';
  }

  function buildGroups(ctx) {
    return [
      [
        { name: 'bold', title: 'Bold (Ctrl+B)', html: ICONS.bold, run: function (e) { e.chain().focus().toggleBold().run(); }, active: function (e) { return e.isActive('bold'); } },
        { name: 'italic', title: 'Italic (Ctrl+I)', html: ICONS.italic, run: function (e) { e.chain().focus().toggleItalic().run(); }, active: function (e) { return e.isActive('italic'); } },
        { name: 'underline', title: 'Underline (Ctrl+U)', html: ICONS.underline, run: function (e) { e.chain().focus().toggleUnderline().run(); }, active: function (e) { return e.isActive('underline'); } },
        { name: 'strike', title: 'Strikethrough', html: ICONS.strike, run: function (e) { e.chain().focus().toggleStrike().run(); }, active: function (e) { return e.isActive('strike'); } },
        { name: 'code', title: 'Inline code', html: ICONS.code, run: function (e) { e.chain().focus().toggleCode().run(); }, active: function (e) { return e.isActive('code'); } },
      ],
      [
        { name: 'h1', title: 'Heading 1', html: textButton('H1'), run: function (e) { e.chain().focus().toggleHeading({ level: 1 }).run(); }, active: function (e) { return e.isActive('heading', { level: 1 }); } },
        { name: 'h2', title: 'Heading 2', html: textButton('H2'), run: function (e) { e.chain().focus().toggleHeading({ level: 2 }).run(); }, active: function (e) { return e.isActive('heading', { level: 2 }); } },
        { name: 'h3', title: 'Heading 3', html: textButton('H3'), run: function (e) { e.chain().focus().toggleHeading({ level: 3 }).run(); }, active: function (e) { return e.isActive('heading', { level: 3 }); } },
      ],
      [
        { name: 'bullet', title: 'Bullet list', html: ICONS.bullet, run: function (e) { e.chain().focus().toggleBulletList().run(); }, active: function (e) { return e.isActive('bulletList'); } },
        { name: 'ordered', title: 'Numbered list', html: ICONS.ordered, run: function (e) { e.chain().focus().toggleOrderedList().run(); }, active: function (e) { return e.isActive('orderedList'); } },
        { name: 'task', title: 'Task checklist', html: ICONS.task, run: function (e) { e.chain().focus().toggleTaskList().run(); }, active: function (e) { return e.isActive('taskList'); } },
      ],
      [
        { name: 'quote', title: 'Block quote', html: ICONS.quote, run: function (e) { e.chain().focus().toggleBlockquote().run(); }, active: function (e) { return e.isActive('blockquote'); } },
        { name: 'hr', title: 'Divider', html: ICONS.hr, run: function (e) { e.chain().focus().setHorizontalRule().run(); } },
      ],
      [
        { name: 'alignLeft', title: 'Align left', html: ICONS.alignLeft, run: function (e) { e.chain().focus().setTextAlign('left').run(); }, active: function (e) { return e.isActive({ textAlign: 'left' }); } },
        { name: 'alignCenter', title: 'Align center', html: ICONS.alignCenter, run: function (e) { e.chain().focus().setTextAlign('center').run(); }, active: function (e) { return e.isActive({ textAlign: 'center' }); } },
        { name: 'alignRight', title: 'Align right', html: ICONS.alignRight, run: function (e) { e.chain().focus().setTextAlign('right').run(); }, active: function (e) { return e.isActive({ textAlign: 'right' }); } },
      ],
      [
        { name: 'link', title: 'Insert / edit link (Ctrl+K)', html: ICONS.link, run: function (e) { ctx.openLinkPopover(); }, active: function (e) { return e.isActive('link'); } },
        ctx.uploadUrl ? { name: 'image', title: 'Insert image', html: ICONS.image, run: function (e) { ctx.pickImage(); } } : null,
        { name: 'table', title: 'Insert table', html: ICONS.table, run: function (e) { e.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run(); } },
      ].filter(Boolean),
      [
        { name: 'undo', title: 'Undo (Ctrl+Z)', html: ICONS.undo, run: function (e) { e.chain().focus().undo().run(); } },
        { name: 'redo', title: 'Redo (Ctrl+Y)', html: ICONS.redo, run: function (e) { e.chain().focus().redo().run(); } },
      ],
    ];
  }

  // ---- image upload --------------------------------------------------------
  function uploadImage(uploadUrl, file, sourceLabel) {
    var form = new FormData();
    form.append('image', file);
    if (sourceLabel) form.append('source_label', sourceLabel);
    return fetch(uploadUrl, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrfToken() },
      body: form,
      credentials: 'same-origin',
    }).then(function (r) {
      return r.json().then(function (data) {
        if (!r.ok || !data.url) throw new Error(data.error || 'Upload failed');
        return data.url;
      });
    });
  }

  // ---- mount one editor ----------------------------------------------------
  function mount(textarea) {
    var T = window.WLJTipTap;
    textarea.setAttribute('data-wlj-rte-ready', 'true');

    var placeholder = textarea.getAttribute('data-wlj-rte-placeholder') || '';
    var minHeight = parseInt(textarea.getAttribute('data-wlj-rte-min-height'), 10) || 220;
    var uploadUrl = textarea.getAttribute('data-wlj-rte-upload-url') || '';
    var sourceLabel = textarea.getAttribute('name') || '';

    var field = document.createElement('div');
    field.className = 'wlj-rte';
    var toolbar = document.createElement('div');
    toolbar.className = 'wlj-rte-toolbar';
    toolbar.setAttribute('role', 'toolbar');
    var mountEl = document.createElement('div');
    mountEl.className = 'wlj-rte-content';
    mountEl.style.minHeight = minHeight + 'px';

    textarea.parentNode.insertBefore(field, textarea);
    field.appendChild(toolbar);
    field.appendChild(mountEl);
    field.appendChild(textarea); // keep the (hidden) source textarea inside the field

    var fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.accept = 'image/*';
    fileInput.style.display = 'none';
    field.appendChild(fileInput);

    var ctx = {
      uploadUrl: uploadUrl,
      pickImage: function () { fileInput.click(); },
      openLinkPopover: function () { openLinkPopover(); },
    };

    var editor = new T.Editor({
      element: mountEl,
      extensions: [
        T.StarterKit.configure({ codeBlock: false, heading: { levels: [1, 2, 3] } }),
        T.Underline,
        T.Link.configure({
          openOnClick: false,
          autolink: true,
          linkOnPaste: true,
          HTMLAttributes: { rel: 'noopener noreferrer nofollow', target: '_blank' },
        }),
        T.ResizableImage.configure({ inline: false, allowBase64: false }),
        T.TextAlign.configure({ types: ['heading', 'paragraph'] }),
        T.TaskList,
        T.TaskItem.configure({ nested: true }),
        T.Table.configure({ resizable: false }),
        T.TableRow,
        T.TableHeader,
        T.TableCell,
        T.Placeholder.configure({ placeholder: placeholder }),
      ],
      content: textarea.value || '',
      editorProps: {
        attributes: { class: 'wlj-rte-prose', 'aria-label': placeholder || 'Rich text editor' },
        handlePaste: function (view, event) {
          return handleImageInsertFromData(event.clipboardData);
        },
        handleDrop: function (view, event) {
          return handleImageInsertFromData(event.dataTransfer, event);
        },
      },
      onUpdate: function () {
        textarea.value = editor.getHTML();
      },
    });

    function handleImageInsertFromData(dataTransfer, event) {
      if (!uploadUrl || !dataTransfer || !dataTransfer.files || !dataTransfer.files.length) {
        return false;
      }
      var images = Array.prototype.filter.call(dataTransfer.files, function (f) {
        return f.type && f.type.indexOf('image/') === 0;
      });
      if (!images.length) return false;
      if (event) event.preventDefault();
      images.forEach(function (file) {
        uploadImage(uploadUrl, file, sourceLabel)
          .then(function (url) { editor.chain().focus().setImage({ src: url }).run(); })
          .catch(function (err) { window.alert(err.message || 'Image upload failed.'); });
      });
      return true;
    }

    fileInput.addEventListener('change', function () {
      if (!fileInput.files || !fileInput.files.length) return;
      uploadImage(uploadUrl, fileInput.files[0], sourceLabel)
        .then(function (url) { editor.chain().focus().setImage({ src: url }).run(); })
        .catch(function (err) { window.alert(err.message || 'Image upload failed.'); })
        .then(function () { fileInput.value = ''; });
    });

    // ---- build toolbar DOM (CSP-safe: delegated listener) ----
    var buttonEls = [];
    buildGroups(ctx).forEach(function (group) {
      var g = document.createElement('div');
      g.className = 'wlj-rte-group';
      group.forEach(function (spec) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'wlj-rte-btn';
        b.title = spec.title;
        b.setAttribute('aria-label', spec.title);
        b.innerHTML = spec.html;
        b.addEventListener('mousedown', function (ev) { ev.preventDefault(); });
        b.addEventListener('click', function () {
          spec.run(editor);
          refreshActive();
        });
        g.appendChild(b);
        if (spec.active) buttonEls.push({ el: b, active: spec.active });
      });
      toolbar.appendChild(g);
    });

    function refreshActive() {
      buttonEls.forEach(function (item) {
        var on = false;
        try { on = !!item.active(editor); } catch (e) { on = false; }
        item.el.classList.toggle('is-active', on);
      });
    }
    editor.on('selectionUpdate', refreshActive);
    editor.on('transaction', refreshActive);
    refreshActive();

    // ---- link popover (Ctrl+K / toolbar) ----
    var popover = null;
    function openLinkPopover() {
      closeLinkPopover();
      var prev = editor.getAttributes('link').href || '';
      popover = document.createElement('div');
      popover.className = 'wlj-rte-linkpop';
      var input = document.createElement('input');
      input.type = 'url';
      input.placeholder = 'https://example.com';
      input.value = prev;
      input.className = 'wlj-rte-linkpop-input';
      var apply = document.createElement('button');
      apply.type = 'button';
      apply.className = 'wlj-rte-linkpop-apply';
      apply.textContent = 'Apply';
      var remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'wlj-rte-linkpop-remove';
      remove.textContent = 'Remove';
      popover.appendChild(input);
      popover.appendChild(apply);
      popover.appendChild(remove);
      toolbar.appendChild(popover);
      input.focus();

      function commit() {
        var url = (input.value || '').trim();
        if (!url) { editor.chain().focus().extendMarkRange('link').unsetLink().run(); }
        else { editor.chain().focus().extendMarkRange('link').setLink({ href: url }).run(); }
        closeLinkPopover();
        refreshActive();
      }
      apply.addEventListener('click', commit);
      remove.addEventListener('click', function () {
        editor.chain().focus().extendMarkRange('link').unsetLink().run();
        closeLinkPopover();
        refreshActive();
      });
      input.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter') { ev.preventDefault(); commit(); }
        else if (ev.key === 'Escape') { ev.preventDefault(); closeLinkPopover(); }
      });
    }
    function closeLinkPopover() {
      if (popover && popover.parentNode) popover.parentNode.removeChild(popover);
      popover = null;
    }
    ctx.openLinkPopover = openLinkPopover;

    mountEl.addEventListener('keydown', function (ev) {
      var mod = ev.ctrlKey || ev.metaKey;
      if (mod && (ev.key === 'k' || ev.key === 'K')) {
        ev.preventDefault();
        openLinkPopover();
      }
    });

    // Ensure the source textarea holds the initial (normalized) HTML pre-submit.
    var form = textarea.closest('form');
    if (form) {
      form.addEventListener('submit', function () { textarea.value = editor.getHTML(); });
    }
  }

  // ---- boot ---------------------------------------------------------------
  function scan() {
    if (!window.WLJTipTap || !window.WLJTipTap.Editor) return false;
    var nodes = document.querySelectorAll('textarea[data-wlj-rte]:not([data-wlj-rte-ready])');
    Array.prototype.forEach.call(nodes, mount);
    return true;
  }

  function boot() {
    if (scan()) return;
    // Bundle not ready yet (unexpected with defer ordering) — poll briefly.
    var tries = 0;
    var timer = setInterval(function () {
      tries += 1;
      if (scan() || tries > 40) clearInterval(timer);
    }, 50);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
  // Re-scan after htmx swaps (new forms may appear).
  document.addEventListener('htmx:afterSwap', scan);
  window.WLJRichText = { scan: scan };
})();
