"""
Brain Training App Configuration

Premium brain training module with 5 games:
- Sudoku (logic)
- KenKen/Calcudoku (math logic)
- Nonogram/Picross (visual logic)
- Word Ladder (language)
- Memory Matrix (memory/attention)
"""

from django.apps import AppConfig


class BrainTrainingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.brain_training'
    verbose_name = 'Brain Training'
