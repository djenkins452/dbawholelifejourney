# ==============================================================================
# File: docs/wlj_goals_habit_rules.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Goal Structure and Habit Rules specification for the Goals & Habit Matrix System
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-02
# Last Updated: 2026-01-02
# ==============================================================================

# WLJ Goal Structure and Habit Rules

This document defines the data model and rules for goals that support start/end dates, habits, and daily completion tracking. This is part of the **WLJ Goals & Habit Matrix System Upgrade** project.

---

## 1. Goal Model Structure

### Required Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | CharField(200) | Yes | The goal title/name |
| `purpose` | TextField | Yes | Why this goal matters - the deeper meaning |
| `start_date` | DateField | Yes | When the goal period begins |
| `end_date` | DateField | Yes | When the goal period ends |
| `habit_required` | BooleanField | Yes | Whether this goal requires daily habit tracking |

### Optional Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `description` | TextField | No | Additional details about the goal |
| `success_criteria` | TextField | No | What success looks like |
| `domain` | ForeignKey(LifeDomain) | No | Life area this goal belongs to |
| `status` | CharField | No | Goal status (active, paused, completed, abandoned) |

### Validation Rules

1. **Date Validation**
   - `end_date` must be greater than or equal to `start_date`
   - `start_date` can be in the past (for retroactive goal creation)
   - `end_date` can be in the past (for completed goals)

2. **Name Validation**
   - Cannot be empty or whitespace-only
   - Maximum 200 characters

3. **Purpose Validation**
   - Cannot be empty if `habit_required` is True
   - Helps users understand why they're committing to daily tracking

---

## 2. Habit Rules

### Core Principles

1. **One Entry Per Calendar Day**
   - Each goal with `habit_required=True` allows exactly ONE habit entry per calendar day
   - The valid date range is from `start_date` to `end_date` (inclusive)
   - Users cannot create entries for dates outside this range

2. **Missed Days Are Valid Data States**
   - A day without an entry is NOT an error - it's valid data
   - The system does NOT auto-create "missed" entries
   - Absence of data = day was not completed (or not tracked)
   - This allows users to be honest without being punished by the system

3. **No Future Entries**
   - Users cannot mark future days as complete
   - Entries can only be created for today or past dates within the goal range

### Habit Entry Model

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `goal` | ForeignKey(Goal) | Yes | The parent goal |
| `date` | DateField | Yes | The calendar date for this entry |
| `completed` | BooleanField | Yes | Whether the habit was completed |
| `notes` | TextField | No | Optional notes about this day |
| `created_at` | DateTimeField | Auto | When the entry was created |

### Unique Constraint

```python
class Meta:
    unique_together = ['goal', 'date']
```

This ensures one entry per goal per day.

---

## 3. Habit Matrix Generation

### Automatic Generation Rules

When a goal has `habit_required=True`, the system must:

1. **Calculate Total Days**
   ```python
   total_days = (end_date - start_date).days + 1  # Inclusive
   ```

2. **Generate Matrix Grid**
   - The habit matrix is a visual grid representation
   - Grid is generated on-demand, NOT stored in the database
   - Empty boxes represent days not yet completed
   - Filled boxes represent completed days

3. **Matrix Layout Algorithm**
   ```python
   # Optimized rectangular layout
   rows = floor(sqrt(total_days))
   columns = ceil(total_days / rows)

   # Total boxes = rows × columns
   # Disabled boxes = (rows × columns) - total_days
   ```

4. **Box States**
   - **Completed**: Habit entry exists with `completed=True`
   - **Incomplete**: Date is in the past, no entry or `completed=False`
   - **Today**: Current date, can be marked complete
   - **Future**: Cannot be interacted with yet
   - **Disabled**: Box exists for grid alignment but represents no date

### Example

A 30-day goal (January 1 - January 30):
- `total_days = 30`
- `rows = floor(sqrt(30)) = 5`
- `columns = ceil(30/5) = 6`
- Grid: 5×6 = 30 boxes (no disabled boxes)

A 100-day goal:
- `total_days = 100`
- `rows = floor(sqrt(100)) = 10`
- `columns = ceil(100/10) = 10`
- Grid: 10×10 = 100 boxes (no disabled boxes)

A 45-day goal:
- `total_days = 45`
- `rows = floor(sqrt(45)) = 6`
- `columns = ceil(45/6) = 8`
- Grid: 6×8 = 48 boxes (3 disabled boxes)

---

## 4. Backend Validation Requirements

### Goal Creation/Update

```python
def clean(self):
    # Validate date range
    if self.end_date < self.start_date:
        raise ValidationError("End date must be on or after start date.")

    # Validate purpose for habit goals
    if self.habit_required and not self.purpose.strip():
        raise ValidationError("Purpose is required for habit-tracking goals.")
```

### Habit Entry Creation

```python
def clean(self):
    # Validate date is within goal range
    if self.date < self.goal.start_date:
        raise ValidationError("Date cannot be before goal start date.")
    if self.date > self.goal.end_date:
        raise ValidationError("Date cannot be after goal end date.")

    # Validate not future date
    if self.date > timezone.now().date():
        raise ValidationError("Cannot create habit entries for future dates.")

    # Validate goal has habit tracking enabled
    if not self.goal.habit_required:
        raise ValidationError("This goal does not have habit tracking enabled.")
```

---

## 5. AI Execution Rules

When Claude is executing tasks related to goals and habits:

### MUST DO
- Validate all required fields before saving
- Respect the date range constraints
- Allow gaps in habit tracking (missed days are valid)
- Generate habit matrix using the sizing algorithm

### MUST NOT
- Auto-fill missed days with incomplete entries
- Allow entries outside the goal date range
- Allow future date entries
- Create duplicate entries for the same goal+date

### Error Handling
- Return clear validation errors explaining what failed
- Do not save partial data
- Log validation failures for debugging

---

## 6. Relationship to Existing Models

### Current LifeGoal Model (apps/purpose/models.py)

The existing `LifeGoal` model is designed for 12-36 month goals without daily tracking. This new goal structure is **separate** and designed for shorter-term, habit-focused goals.

**Option A: Extend LifeGoal**
- Add `start_date`, `end_date`, `habit_required` fields
- Add HabitEntry model with ForeignKey to LifeGoal
- Pros: Single goal model, less complexity
- Cons: Mixes two different goal philosophies

**Option B: New HabitGoal Model**
- Create separate `HabitGoal` model in purpose app
- Keep `LifeGoal` for long-term direction setting
- Pros: Clean separation of concerns
- Cons: Two goal types to manage

**Recommendation:** Option B - Create a new `HabitGoal` model to keep the two concepts separate. Life Goals are about direction, Habit Goals are about daily execution.

---

## 7. Summary

This document establishes:

1. **Goal Fields**: name, purpose, start_date, end_date, habit_required (all required)
2. **Habit Rules**: One entry per day, missed days are valid, no future entries
3. **Matrix Generation**: Auto-calculate optimal grid size based on date range
4. **Validation**: Enforce rules at both model and AI execution level

This rule set can be enforced by both backend Django validation and AI task execution.
