/**
 * WLJ Rich Text Editor — TipTap bundle entry.
 *
 * Bundled (esbuild, IIFE) into `static/vendor/tiptap/tiptap.bundle.js` and
 * exposed on `window.WLJTipTap`. This file decides exactly which TipTap
 * building blocks ship with WLJ — keep it minimal; only add an extension here
 * when a toolbar control in `static/js/wlj-rich-text.js` actually uses it.
 *
 * Rebuild after any change: see frontend/tiptap/README.md
 */
import { Editor, mergeAttributes } from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import MentionBase from '@tiptap/extension-mention';
import Underline from '@tiptap/extension-underline';
import Link from '@tiptap/extension-link';
import Image from '@tiptap/extension-image';
import TextAlignBase from '@tiptap/extension-text-align';
import TaskList from '@tiptap/extension-task-list';
import TaskItem from '@tiptap/extension-task-item';
import Table from '@tiptap/extension-table';
import TableRow from '@tiptap/extension-table-row';
import TableHeader from '@tiptap/extension-table-header';
import TableCell from '@tiptap/extension-table-cell';
import Placeholder from '@tiptap/extension-placeholder';

/**
 * ResizableImage — the official Image node plus a persisted integer `width`
 * attribute and a drag-handle NodeView. Width is stored as the plain HTML
 * `width` attribute (not inline CSS) so the server-side sanitizer can
 * allow-list it trivially and rendering stays safe.
 */
/**
 * TextAlign that persists alignment as a `data-text-align` attribute instead of
 * inline `style="text-align:…"`. The server-side sanitizer (nh3) cannot filter
 * CSS *inside* a style attribute, so we never allow `style`; a data attribute is
 * trivially allow-listed and safe. CSS in wlj-rich-text.css maps
 * [data-text-align="center"] -> text-align:center for both editor and render.
 */
const TextAlign = TextAlignBase.extend({
  addGlobalAttributes() {
    return [
      {
        types: this.options.types,
        attributes: {
          textAlign: {
            default: this.options.defaultAlignment,
            parseHTML: (element) =>
              element.getAttribute('data-text-align') ||
              element.style.textAlign ||
              this.options.defaultAlignment,
            renderHTML: (attributes) => {
              if (
                !attributes.textAlign ||
                attributes.textAlign === this.options.defaultAlignment
              ) {
                return {};
              }
              return { 'data-text-align': attributes.textAlign };
            },
          },
        },
      },
    ];
  },
});

const ResizableImage = Image.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      width: {
        default: null,
        parseHTML: (element) => {
          const w = element.getAttribute('width');
          return w ? parseInt(w, 10) || null : null;
        },
        renderHTML: (attributes) => {
          if (!attributes.width) return {};
          return { width: attributes.width };
        },
      },
    };
  },
  addNodeView() {
    return ({ node, editor, getPos }) => {
      const wrapper = document.createElement('span');
      wrapper.className = 'wlj-rte-image';
      const img = document.createElement('img');
      img.src = node.attrs.src;
      if (node.attrs.alt) img.alt = node.attrs.alt;
      if (node.attrs.title) img.title = node.attrs.title;
      if (node.attrs.width) img.setAttribute('width', node.attrs.width);
      wrapper.appendChild(img);

      // Only editable instances get a resize handle.
      if (editor.isEditable) {
        const handle = document.createElement('span');
        handle.className = 'wlj-rte-image-handle';
        handle.setAttribute('contenteditable', 'false');
        wrapper.appendChild(handle);

        let startX = 0;
        let startWidth = 0;
        const onMove = (e) => {
          const dx = e.clientX - startX;
          const next = Math.max(48, Math.round(startWidth + dx));
          img.setAttribute('width', next);
        };
        const onUp = () => {
          document.removeEventListener('mousemove', onMove);
          document.removeEventListener('mouseup', onUp);
          const w = parseInt(img.getAttribute('width'), 10) || null;
          if (typeof getPos === 'function') {
            editor
              .chain()
              .focus()
              .updateAttributes('image', { width: w })
              .run();
          }
        };
        handle.addEventListener('mousedown', (e) => {
          e.preventDefault();
          startX = e.clientX;
          startWidth = img.getBoundingClientRect().width;
          document.addEventListener('mousemove', onMove);
          document.addEventListener('mouseup', onUp);
        });
      }

      return {
        dom: wrapper,
        update: (updatedNode) => {
          if (updatedNode.type.name !== 'image') return false;
          img.src = updatedNode.attrs.src;
          if (updatedNode.attrs.width) {
            img.setAttribute('width', updatedNode.attrs.width);
          } else {
            img.removeAttribute('width');
          }
          return true;
        },
      };
    };
  },
});

/**
 * WLJMention — a canonical person mention node. Stores the canonical people.Person id
 * (attr `id`) + the visible `label`, and renders the WLJ markup contract:
 *   <span data-mention data-person-id="123" class="wlj-mention">@Heather</span>
 * matched exactly by the server-side sanitizer allow-list (rich_text.py). The plain-text
 * shadow is "@Heather" (no id) — `renderText` + the span's text content both agree.
 * The suggestion behaviour (@ trigger, canonical lookup, dropdown) is configured by the
 * shared editor glue (static/js/wlj-rich-text.js), not here.
 */
const Mention = MentionBase.extend({
  renderHTML({ node, HTMLAttributes }) {
    const label = node.attrs.label ?? node.attrs.id;
    return ['span', mergeAttributes(
      { 'data-mention': '', 'data-person-id': node.attrs.id, class: 'wlj-mention' },
      HTMLAttributes,
    ), `@${label}`];
  },
  renderText({ node }) {
    return `@${node.attrs.label ?? node.attrs.id}`;
  },
  parseHTML() {
    return [{
      tag: 'span[data-mention]',
      getAttrs: (el) => ({
        id: el.getAttribute('data-person-id'),
        label: (el.textContent || '').replace(/^@/, ''),
      }),
    }];
  },
});

export {
  Editor,
  StarterKit,
  Mention,
  Underline,
  Link,
  Image,
  ResizableImage,
  TextAlign,
  TaskList,
  TaskItem,
  Table,
  TableRow,
  TableHeader,
  TableCell,
  Placeholder,
};
