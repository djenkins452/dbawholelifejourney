"""
Dashboard Configuration Service

Manages dashboard tile configuration including:
- Tile visibility (show/hide)
- Tile ordering (drag-and-drop)
- Tile sizing (small/medium/large)
- Default configurations based on enabled modules

Location: apps/dashboard/services/config_service.py
"""

from typing import Optional
from copy import deepcopy


# =============================================================================
# TILE DEFINITIONS
# =============================================================================

# Size options for tiles
TILE_SIZES = ['small', 'medium', 'large']

# All available dashboard tiles with metadata
TILE_DEFINITIONS = {
    'quick_stats': {
        'id': 'quick_stats',
        'name': 'Quick Stats',
        'description': 'At-a-glance metrics including journal streak, tasks completed, active prayers, and medicine status.',
        'icon': 'chart-bar',
        'module_dependency': None,  # Always available
        'default_visible': True,
        'default_size': 'medium',
        'mandatory': False,
        'default_order': 1,
    },
    'weather': {
        'id': 'weather',
        'name': 'Weather',
        'description': 'Current weather conditions and forecast for your location.',
        'icon': 'cloud-sun',
        'module_dependency': None,  # Requires location_city set
        'requires_location': True,
        'default_visible': True,
        'default_size': 'medium',
        'mandatory': False,
        'default_order': 2,
    },
    'memory_verse': {
        'id': 'memory_verse',
        'name': 'Memory Verse',
        'description': 'Your current memory verse for daily reflection and meditation.',
        'icon': 'book-open',
        'module_dependency': 'faith_enabled',
        'default_visible': True,
        'default_size': 'medium',
        'mandatory': False,
        'default_order': 3,
    },
    'ai_insights': {
        'id': 'ai_insights',
        'name': 'AI Insights',
        'description': 'Personalized daily insights powered by AI, analyzing patterns across your journal, health, and goals.',
        'icon': 'sparkles',
        'module_dependency': 'ai_enabled',
        'default_visible': True,
        'default_size': 'large',
        'mandatory': True,  # Cannot be hidden
        'pinned_position': 1,  # Always first, cannot be reordered
        'default_order': 1,
    },
    'celebrations': {
        'id': 'celebrations',
        'name': 'Celebrations',
        'description': 'Recognition of your achievements, streaks, and milestones across all areas of life.',
        'icon': 'trophy',
        'module_dependency': 'ai_enabled',
        'default_visible': True,
        'default_size': 'medium',
        'mandatory': False,
        'default_order': 5,
    },
    'nudges': {
        'id': 'nudges',
        'name': 'Accountability Nudges',
        'description': 'Gentle reminders about overdue tasks, journal gaps, and areas needing attention.',
        'icon': 'bell',
        'module_dependency': 'ai_enabled',
        'default_visible': True,
        'default_size': 'medium',
        'mandatory': False,
        'default_order': 6,
    },
    'weekly_summary': {
        'id': 'weekly_summary',
        'name': 'Weekly Summary',
        'description': 'AI-generated overview of your week including accomplishments and patterns.',
        'icon': 'calendar-week',
        'module_dependency': 'ai_enabled',
        'default_visible': True,
        'default_size': 'medium',
        'mandatory': False,
        'default_order': 7,
    },
    'daily_encouragement': {
        'id': 'daily_encouragement',
        'name': 'Daily Encouragement',
        'description': 'Uplifting messages and optional scripture to start your day.',
        'icon': 'sun',
        'module_dependency': None,
        'default_visible': True,
        'default_size': 'medium',
        'mandatory': False,
        'default_order': 8,
    },
    'current_fast': {
        'id': 'current_fast',
        'name': 'Current Fast',
        'description': 'Live countdown timer for your active fasting session with progress bar.',
        'icon': 'clock',
        'module_dependency': 'health_enabled',
        'default_visible': True,
        'default_size': 'medium',
        'mandatory': False,
        'default_order': 9,
    },
    'cycle_tracking': {
        'id': 'cycle_tracking',
        'name': 'Cycle Tracking',
        'description': 'Current menstrual cycle phase, cycle day, and quick logging buttons.',
        'icon': 'heart',
        'module_dependency': 'health_enabled',
        'requires_gender': 'female',
        'default_visible': True,
        'default_size': 'medium',
        'mandatory': False,
        'default_order': 10,
    },
    'quick_actions': {
        'id': 'quick_actions',
        'name': 'Quick Actions',
        'description': 'Fast links to common actions like new journal entry, log weight, add task, and more.',
        'icon': 'bolt',
        'module_dependency': None,
        'default_visible': True,
        'default_size': 'large',
        'mandatory': False,
        'default_order': 11,
    },
    'module_cards': {
        'id': 'module_cards',
        'name': 'Module Cards',
        'description': 'Navigation cards with summary stats for each of your enabled modules.',
        'icon': 'squares-2x2',
        'module_dependency': None,
        'default_visible': True,
        'default_size': 'large',
        'mandatory': False,
        'default_order': 12,
    },
    'medicine_schedule': {
        'id': 'medicine_schedule',
        'name': "Today's Medicine",
        'description': 'Your medication schedule for today with status tracking.',
        'icon': 'pill',
        'module_dependency': 'health_enabled',
        'default_visible': True,
        'default_size': 'medium',
        'mandatory': False,
        'default_order': 13,
    },
    'nutrition_progress': {
        'id': 'nutrition_progress',
        'name': 'Nutrition Progress',
        'description': 'Daily calorie and macro tracking with progress toward your goals.',
        'icon': 'utensils',
        'module_dependency': 'health_enabled',
        'default_visible': True,
        'default_size': 'medium',
        'mandatory': False,
        'default_order': 14,
    },
    'recent_workouts': {
        'id': 'recent_workouts',
        'name': 'Recent Workouts',
        'description': 'Your latest workout sessions and any new personal records.',
        'icon': 'dumbbell',
        'module_dependency': 'health_enabled',
        'default_visible': True,
        'default_size': 'medium',
        'mandatory': False,
        'default_order': 15,
    },
    'goal_progress': {
        'id': 'goal_progress',
        'name': 'Goal Progress',
        'description': 'Active goals with milestone progress bars and upcoming deadlines.',
        'icon': 'target',
        'module_dependency': 'purpose_enabled',
        'default_visible': True,
        'default_size': 'medium',
        'mandatory': False,
        'default_order': 16,
    },
    'upcoming_events': {
        'id': 'upcoming_events',
        'name': 'Upcoming Events',
        'description': 'Calendar events for the next 7 days.',
        'icon': 'calendar',
        'module_dependency': 'life_enabled',
        'default_visible': True,
        'default_size': 'medium',
        'mandatory': False,
        'default_order': 17,
    },
    'upcoming_celebrations': {
        'id': 'upcoming_celebrations',
        'name': 'Upcoming Celebrations',
        'description': 'Birthdays, anniversaries, and other significant events in the next 30 days.',
        'icon': 'cake',
        'module_dependency': 'life_enabled',
        'default_visible': True,
        'default_size': 'medium',
        'mandatory': False,
        'default_order': 18,
    },
    'recurring_transactions': {
        'id': 'recurring_transactions',
        'name': 'Upcoming Bills',
        'description': 'Recurring transactions due in the next 7 days.',
        'icon': 'credit-card',
        'module_dependency': 'finances_enabled',
        'default_visible': True,
        'default_size': 'medium',
        'mandatory': False,
        'default_order': 19,
    },
}


class DashboardConfigService:
    """
    Service for managing dashboard tile configuration.

    Usage:
        service = DashboardConfigService(user)
        config = service.get_config()
        tiles = service.get_visible_tiles()
        service.update_config(new_config)
    """

    def __init__(self, user):
        self.user = user
        self.prefs = user.preferences

    def get_available_tiles(self) -> list:
        """
        Get list of tiles available to this user based on their enabled modules.

        Returns:
            List of tile definitions the user can see/configure.
        """
        available = []

        for tile_id, tile_def in TILE_DEFINITIONS.items():
            # Check module dependency
            module_dep = tile_def.get('module_dependency')
            if module_dep and not getattr(self.prefs, module_dep, False):
                continue

            # Check location requirement
            if tile_def.get('requires_location') and not self.prefs.location_city:
                continue

            # Check gender requirement (for cycle tracking)
            required_gender = tile_def.get('requires_gender')
            if required_gender:
                user_gender = getattr(self.prefs, 'gender', None)
                if user_gender != required_gender:
                    continue

            available.append(deepcopy(tile_def))

        return available

    def get_default_config(self) -> dict:
        """
        Generate default configuration based on user's enabled modules.

        Returns:
            Dict with 'tiles' key containing list of tile configs.
        """
        available_tiles = self.get_available_tiles()

        tiles = []
        for tile_def in sorted(available_tiles, key=lambda t: t['default_order']):
            tiles.append({
                'id': tile_def['id'],
                'visible': tile_def['default_visible'],
                'size': tile_def['default_size'],
                'order': tile_def['default_order'],
            })

        return {'tiles': tiles, 'version': 1}

    def get_config(self) -> dict:
        """
        Get user's dashboard configuration, or defaults if not set.

        Returns full tile definitions merged with user config for display.

        Returns:
            Dashboard configuration dict with full tile metadata.
        """
        stored_config = self.prefs.dashboard_config

        if not stored_config or 'tiles' not in stored_config:
            base_config = self.get_default_config()
        else:
            # Merge stored config with available tiles (in case new tiles were added)
            base_config = self._merge_config_with_available(stored_config)

        # Merge in full tile definitions for display
        available_tiles = {t['id']: t for t in self.get_available_tiles()}
        enriched_tiles = []

        for tile_config in base_config.get('tiles', []):
            tile_id = tile_config['id']
            tile_def = available_tiles.get(tile_id)

            if tile_def:
                # Merge definition with config (config takes precedence)
                merged = {**tile_def, **tile_config}
                enriched_tiles.append(merged)

        return {'tiles': enriched_tiles, 'version': base_config.get('version', 1)}

    def _merge_config_with_available(self, stored_config: dict) -> dict:
        """
        Merge stored config with currently available tiles.

        Adds any new tiles that weren't in the stored config,
        removes any tiles that are no longer available.
        """
        available_tiles = {t['id']: t for t in self.get_available_tiles()}
        stored_tiles = {t['id']: t for t in stored_config.get('tiles', [])}

        merged_tiles = []
        max_order = max((t.get('order', 0) for t in stored_config.get('tiles', [])), default=0)

        # First, add all stored tiles that are still available
        for tile_config in stored_config.get('tiles', []):
            tile_id = tile_config['id']
            if tile_id in available_tiles:
                merged_tiles.append(tile_config)

        # Then, add any new tiles that weren't in stored config
        for tile_id, tile_def in available_tiles.items():
            if tile_id not in stored_tiles:
                max_order += 1
                merged_tiles.append({
                    'id': tile_id,
                    'visible': tile_def['default_visible'],
                    'size': tile_def['default_size'],
                    'order': max_order,
                })

        # Sort by order
        merged_tiles.sort(key=lambda t: t.get('order', 999))

        return {'tiles': merged_tiles, 'version': stored_config.get('version', 1)}

    def get_visible_tiles(self) -> list:
        """
        Get ordered list of visible tiles with their full definitions.

        Returns:
            List of tile configs merged with definitions, ordered by user preference.
            Pinned tiles (like AI Insights) are always at their designated position.
        """
        config = self.get_config()
        available_tiles = {t['id']: t for t in self.get_available_tiles()}

        pinned = []
        visible = []
        for tile_config in config.get('tiles', []):
            tile_id = tile_config['id']
            tile_def = available_tiles.get(tile_id)

            if not tile_def:
                continue

            # Mandatory tiles are always visible
            is_visible = tile_config.get('visible', True) or tile_def.get('mandatory', False)

            if is_visible:
                merged = {**tile_def, **tile_config}
                # Pinned tiles go in a separate list to be inserted at their position
                if tile_def.get('pinned_position') is not None:
                    pinned.append((tile_def['pinned_position'], merged))
                else:
                    visible.append(merged)

        # Sort pinned tiles by their position and insert at the front
        pinned.sort(key=lambda x: x[0])
        result = [tile for _, tile in pinned] + visible

        return result

    def update_config(self, new_config: dict) -> bool:
        """
        Update user's dashboard configuration.

        Args:
            new_config: New configuration dict with 'tiles' key.

        Returns:
            True if successful, False if validation failed.
        """
        if not self._validate_config(new_config):
            return False

        # Strip down to only config fields (not full definitions)
        # This is important because get_config() returns enriched tiles
        config_fields = {'id', 'visible', 'size', 'order'}
        cleaned_tiles = []

        available_tiles = {t['id']: t for t in self.get_available_tiles()}

        for tile_config in new_config.get('tiles', []):
            tile_id = tile_config['id']

            # Only keep config fields
            cleaned_tile = {k: v for k, v in tile_config.items() if k in config_fields}

            # Ensure mandatory tiles remain visible
            tile_def = available_tiles.get(tile_id)
            if tile_def and tile_def.get('mandatory'):
                cleaned_tile['visible'] = True

            # Ensure pinned tiles keep their pinned position
            if tile_def and tile_def.get('pinned_position') is not None:
                cleaned_tile['order'] = tile_def['pinned_position']

            cleaned_tiles.append(cleaned_tile)

        storage_config = {'tiles': cleaned_tiles, 'version': new_config.get('version', 1)}
        self.prefs.dashboard_config = storage_config
        self.prefs.save(update_fields=['dashboard_config', 'updated_at'])
        return True

    def _validate_config(self, config: dict) -> bool:
        """
        Validate configuration structure.
        """
        if not isinstance(config, dict):
            return False

        if 'tiles' not in config:
            return False

        tiles = config['tiles']
        if not isinstance(tiles, list):
            return False

        for tile in tiles:
            if not isinstance(tile, dict):
                return False
            if 'id' not in tile:
                return False
            if tile.get('size') and tile['size'] not in TILE_SIZES:
                return False

        return True

    def reset_to_defaults(self) -> None:
        """
        Reset user's dashboard to default configuration.
        """
        self.prefs.dashboard_config = self.get_default_config()
        self.prefs.save(update_fields=['dashboard_config', 'updated_at'])

    def update_tile(self, tile_id: str, visible: Optional[bool] = None,
                    size: Optional[str] = None, order: Optional[int] = None) -> bool:
        """
        Update a single tile's configuration.

        Args:
            tile_id: ID of the tile to update.
            visible: New visibility state (optional).
            size: New size ('small', 'medium', 'large') (optional).
            order: New order position (optional).

        Returns:
            True if successful.
        """
        config = self.get_config()

        for tile_config in config.get('tiles', []):
            if tile_config['id'] == tile_id:
                if visible is not None:
                    # Check if tile is mandatory
                    tile_def = TILE_DEFINITIONS.get(tile_id, {})
                    if not tile_def.get('mandatory'):
                        tile_config['visible'] = visible
                if size is not None and size in TILE_SIZES:
                    tile_config['size'] = size
                if order is not None:
                    tile_config['order'] = order
                break

        return self.update_config(config)

    def reorder_tiles(self, tile_ids: list) -> bool:
        """
        Reorder tiles based on provided list of tile IDs.

        Args:
            tile_ids: List of tile IDs in desired order.

        Returns:
            True if successful.
        """
        config = self.get_config()
        tiles_by_id = {t['id']: t for t in config.get('tiles', [])}

        # Update order based on position in tile_ids
        for idx, tile_id in enumerate(tile_ids):
            if tile_id in tiles_by_id:
                tiles_by_id[tile_id]['order'] = idx + 1

        # Re-sort tiles
        config['tiles'] = sorted(tiles_by_id.values(), key=lambda t: t.get('order', 999))

        return self.update_config(config)

    @staticmethod
    def get_tile_definition(tile_id: str) -> Optional[dict]:
        """
        Get the definition for a specific tile.
        """
        return TILE_DEFINITIONS.get(tile_id)

    @staticmethod
    def get_all_tile_definitions() -> dict:
        """
        Get all tile definitions.
        """
        return deepcopy(TILE_DEFINITIONS)
