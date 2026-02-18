# Nutrition Log UI Redesign — Phase 6

**Created:** 2026-02-18
**Status:** In Progress

## Current State

### Pages & Templates
| Page | Template | Purpose | Issues |
|------|----------|---------|--------|
| Daily Nutrition Log | `nutrition/home.html` | Today's food tracker dashboard | No date nav, no copy actions, no source badges, no data_source_used display |
| Log Food | `nutrition/food_entry_form.html` | Full food entry form | Single page (not 2-step), no search/scan/photo tabs |
| Quick Add | `nutrition/quick_add.html` | Calories-only form | OK but isolated — no link back to it from daily log prominently |
| Food Detail | `nutrition/food_entry_detail.html` | View single entry | No copy action, no source badge |
| History | `nutrition/history.html` | Historical log | Functional, could use copy actions |
| Stats | `nutrition/stats.html` | Trends/averages | Functional, no changes needed |
| Goals | `nutrition/goals.html` | Set nutrition targets | Functional |
| Custom Foods | `nutrition/custom_food_list.html` | Saved foods | Functional |
| Custom Food Form | `nutrition/custom_food_form.html` | Create/edit custom food | Functional |
| Templates List | `nutrition/templates_list.html` | Meal templates | New, needs polish |

### JavaScript
| File | Purpose |
|------|---------|
| `static/js/food-autocomplete.js` | Food search autocomplete with quantity scaling |

### Design System
- CSS variables for colors, spacing, typography
- Cards, buttons, forms, modals (native `<dialog>`)
- Toast notifications via `window.showToast()` / `window.undoToast`
- 10 user-selectable themes
- Mobile breakpoint: 640px

## UI Changes Plan

### 1. Daily Nutrition Log (home.html)
- [x] Add date navigation (prev/today/next arrows)
- [x] Add source badges on food items (FatSecret, Local, AI, etc.)
- [x] Add copy button per food item (copy to another date/meal)
- [x] Add "Copy Meal" action per meal section header
- [x] Add "Copy Day" action in page header
- [x] Add "Templates" link in quick actions
- [x] Sticky daily totals bar at bottom on mobile
- [x] Show data_source_used badge per entry

### 2. Add Food Flow
- [x] Keep as single page (not 2-step — simpler for this app)
- [x] Add data source indicator when form is pre-filled
- [x] Improve mobile form layout

### 3. Copy Modals
- [x] Copy Entry modal: pick target date + meal type
- [x] Copy Meal modal: pick target date + meal type
- [x] Copy Day modal: pick target date + merge/replace option

### 4. Templates Screen
- [x] Polish card layout
- [x] Add "Apply to Date" with date picker
- [x] Better empty state

### 5. Performance & Accessibility
- [x] Semantic HTML (sections, headings hierarchy)
- [x] ARIA labels on interactive elements
- [x] Keyboard-accessible copy/delete actions
- [x] Touch targets 44px minimum

## Implementation Order
1. Daily Nutrition Log rebuild (biggest impact)
2. Copy modals (enables the copy feature from daily log)
3. Templates screen polish
4. Add Food form improvements
5. Performance & accessibility pass
