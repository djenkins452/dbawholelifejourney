# ==============================================================================
# File: docs/wlj_project_blueprint_loading.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Instructions for Claude to load project blueprint JSON files
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-02
# Last Updated: 2026-01-02
# ==============================================================================

# Project Blueprint Loading Instructions

## For the User

When you have a new project blueprint JSON file to load, simply say:

```
Load <filename>.json
```

Example: `Load WLJ_New_Feature_Project.json`

Claude will handle everything else automatically.

---

## For Claude (Execution Instructions)

When the user says **"Load <filename>.json"**, follow these steps exactly:

### Step 1: Verify the File Exists

Check if the file exists in the main repository's `project_blueprints/` directory:

```bash
ls -la C:\dbawholelifejourney\project_blueprints/<filename>.json
```

If the file doesn't exist, inform the user and stop.

### Step 2: Validate JSON Structure

Read and validate the file has the required structure:

```json
{
  "project": {
    "name": "Project Name (required)",
    "description": "Project description (required)"
  },
  "tasks": [
    {
      "phase": "Phase N",
      "name": "Task title",
      "description": {
        "objective": "What the task accomplishes (required)",
        "inputs": ["Context needed (can be empty array)"],
        "actions": ["Step 1", "Step 2 (at least one required)"],
        "output": "Expected deliverable (required)"
      },
      "priority": "High|Medium|Low",
      "status": "New",
      "effort": "Small|Medium|Large|High",
      "allow_out_of_phase": false
    }
  ]
}
```

If validation fails, report the specific error to the user.

### Step 3: Add File to Git

```bash
cd C:\dbawholelifejourney && git add project_blueprints/<filename>.json
```

### Step 4: Update load_initial_data.py

Read the file:
```
C:\dbawholelifejourney\apps\core\management\commands\load_initial_data.py
```

Find the `project_blueprints` list and add the new file path:

```python
project_blueprints = [
    'project_blueprints/wlj_executable_work_orchestration.json',
    'project_blueprints/Goals_Habit_Matrix_Upgrade.json',
    'project_blueprints/WLJ_Secure_Signup_Anti_Fraud_System.json',
    'project_blueprints/<filename>.json',  # <-- Add this line
]
```

### Step 5: Commit and Push

```bash
cd C:\dbawholelifejourney && git add apps/core/management/commands/load_initial_data.py && git commit -m "$(cat <<'EOF'
Add <Project Name> project blueprint

- Add <filename>.json to project_blueprints/
- Update load_initial_data.py to load the new blueprint on deploy
- Project has N tasks across M phases

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)" && git push origin main
```

### Step 6: Report Success

Tell the user:
- File is now tracked in git
- Added to load_initial_data.py
- Will load on next Railway deploy
- List the tasks that will be created

---

## Blueprint JSON Template

For reference, here's a template for creating new blueprints:

```json
{
  "project": {
    "name": "Project Name Here",
    "description": "Brief description of what this project accomplishes."
  },
  "tasks": [
    {
      "phase": "Phase 1",
      "name": "First Task Title",
      "description": {
        "objective": "Clear statement of what this task accomplishes.",
        "inputs": [
          "Any files or context needed",
          "Can be empty array [] if none"
        ],
        "actions": [
          "Step 1: Do this specific thing.",
          "Step 2: Then do this.",
          "Step 3: Finally, do this."
        ],
        "output": "What the completed task produces or achieves."
      },
      "priority": "High",
      "status": "New",
      "effort": "Medium",
      "allow_out_of_phase": false
    }
  ]
}
```

## File Location

All blueprint JSON files go in:
```
C:\dbawholelifejourney\project_blueprints\
```

## Naming Convention

Use descriptive names with underscores:
- `WLJ_Feature_Name.json`
- `Goals_Habit_Matrix_Upgrade.json`
- `WLJ_Secure_Signup_Anti_Fraud_System.json`
