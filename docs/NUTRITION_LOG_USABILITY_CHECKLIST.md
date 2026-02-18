# Nutrition Log Usability Checklist

**Created:** 2026-02-18
**Last Updated:** 2026-02-18

## Daily Nutrition Log (`/health/physical/nutrition/`)

### Layout & Navigation
- [x] Date navigation arrows (prev/next day)
- [x] "Go to Today" link when viewing a past date
- [x] Current date prominently displayed (day name + full date)
- [x] Breadcrumb navigation (Health > Nutrition)
- [x] Quick action cards (History, Stats, Goals, My Foods, Templates)

### Daily Summary
- [x] Large calorie display with accent color
- [x] Progress bar showing % of daily calorie goal
- [x] Macro cards (Protein/Carbs/Fat) with color coding
- [x] Mini progress bars for each macro goal
- [x] ARIA labels on all progress bars

### Meal Sections
- [x] Four meal groups: Breakfast, Lunch, Dinner, Snacks
- [x] Meal subtotal line (calories + P/C/F)
- [x] "+ Add" button per meal section (with date param)
- [x] Scan barcode button per meal section
- [x] Copy Meal button (appears when meal has entries)
- [x] Empty state text when no entries for a meal

### Food Entry Rows
- [x] Food name as clickable link to detail page
- [x] Brand name displayed when available
- [x] Serving info (quantity x size unit)
- [x] Calorie count (accent color)
- [x] Data source badge (Saved/FatSecret/AI/Custom/Quick)
- [x] Copy button (opens copy modal)
- [x] Edit button (links to edit form)
- [x] Delete button (confirmation dialog)
- [x] All action buttons have aria-labels

### Copy Modals
- [x] Copy Entry: date picker + meal selector
- [x] Copy Meal: date picker + target meal selector
- [x] Copy Day: date picker + merge/replace option
- [x] Loading state on confirm button
- [x] Toast notification on success
- [x] Backdrop click to close
- [x] Escape key to close (native `<dialog>`)

### Mobile (< 640px)
- [x] Sticky bottom totals bar (cal/P/C/F)
- [x] Quick actions grid becomes 3-column
- [x] Touch targets minimum 36px (buttons)
- [x] Date nav buttons are 44x44px
- [x] Modal close buttons are 44px
- [x] No horizontal scrolling

---

## Add Food Form (`/health/physical/nutrition/add/`)

### Form Sections
- [x] Section 1: Food name (with autocomplete) + brand + meal/date/time
- [x] Section 2: Serving size (quantity + size + unit)
- [x] Section 3: Nutrition facts (calories + P/C/F macros + optional details)
- [x] Section 4: Context (optional, collapsible)

### Autocomplete
- [x] Debounced search (300ms)
- [x] Source badges (Saved/FatSecret/AI Estimate)
- [x] Nutrition preview in dropdown
- [x] Auto-fills all nutrition fields on selection
- [x] Quantity scaling (client-side preview)
- [x] Keyboard navigation (arrows, enter, escape)
- [x] Loading spinner during search

### Form Actions
- [x] Cancel button
- [x] Log Food (primary action)
- [x] Save & Add Another
- [x] Save & Scan (barcode)
- [x] Actions stack on mobile

### Data Source Indicator
- [x] Shows when form is pre-filled from barcode/scan
- [x] Displays source name + confidence %

### Mobile
- [x] Form sections full-width
- [x] Macros row stays 3-column even on mobile
- [x] Form card removes border on mobile (edge-to-edge)

---

## Meal Templates (`/health/physical/nutrition/templates/`)

### Template Cards
- [x] Template name with favorite star
- [x] Meta info (item count, calories, meal type, use count)
- [x] "Log" button with date picker modal
- [x] Delete button with confirmation
- [x] Items list showing food names + calories

### Apply Template Modal
- [x] Date picker defaulting to today
- [x] Loading state during apply
- [x] Redirects to nutrition home for target date on success

### Empty State
- [x] Icon + heading + description
- [x] Link to daily nutrition page

---

## Food Entry Detail (`/health/physical/nutrition/entry/<pk>/`)

- [x] Large nutrition display (calories + macros grid)
- [x] Extra nutrition (fiber, sugar, sat fat)
- [x] Serving info
- [x] Context section (location, pace, hunger, fullness)
- [x] Notes section
- [x] Meta info (entry source, data source, confidence, logged time)
- [x] Edit and Delete actions

---

## Accessibility Compliance

### ARIA
- [x] `role="progressbar"` with `aria-valuenow/min/max` and `aria-label`
- [x] `aria-label` on all icon-only buttons
- [x] `aria-label` on data source badges
- [x] `role="alert"` on form error messages
- [x] `aria-labelledby` on modals
- [x] `aria-label` on navigation landmarks

### Keyboard
- [x] All interactive elements focusable
- [x] Native `<dialog>` provides built-in Escape handling
- [x] Form navigation via Tab key
- [x] Autocomplete dropdown via arrow keys + Enter

### Touch Targets
- [x] Date nav buttons: 44x44px
- [x] Food action buttons: 36x36px (acceptable with spacing)
- [x] Modal close buttons: 44x44px
- [x] Form submit buttons: full-width on mobile
- [x] All inputs minimum 16px font (prevents iOS zoom)

### Semantic HTML
- [x] `<section>` for meal groups with `aria-label`
- [x] `<nav>` for breadcrumbs and date navigation
- [x] `<fieldset>` + `<legend>` for form sections
- [x] `<dialog>` for modals
- [x] `<details>` + `<summary>` for collapsible sections

---

## Performance

- [x] No external fonts (system font stack)
- [x] CSS in inline `<style nonce>` blocks (no FOUC)
- [x] SVG icons inline (no icon font or sprite sheet)
- [x] Debounced API calls (food search)
- [x] Minimal JS (no framework dependencies)
