"""
Memory Matrix Generator Service

Generates Memory Matrix challenges where players must remember
and recreate a pattern of highlighted cells after a brief viewing period.
"""

import random


class MemoryMatrixGenerator:
    """
    Generates Memory Matrix challenges.

    The challenge displays a grid with some cells highlighted for a few seconds,
    then clears the grid. The player must recreate the pattern from memory.
    """

    # Difficulty settings: grid size and number of highlighted cells
    DIFFICULTY_SETTINGS = {
        'easy': {
            'grid_size': 3,
            'min_cells': 3,
            'max_cells': 4,
            'view_time_ms': 3000,  # 3 seconds
        },
        'medium': {
            'grid_size': 4,
            'min_cells': 5,
            'max_cells': 7,
            'view_time_ms': 2500,  # 2.5 seconds
        },
        'hard': {
            'grid_size': 5,
            'min_cells': 8,
            'max_cells': 12,
            'view_time_ms': 2000,  # 2 seconds
        },
        'expert': {
            'grid_size': 6,
            'min_cells': 12,
            'max_cells': 18,
            'view_time_ms': 1500,  # 1.5 seconds
        },
    }

    def generate(self, difficulty='easy'):
        """
        Generate a new Memory Matrix challenge.

        Args:
            difficulty: 'easy', 'medium', 'hard', or 'expert'

        Returns:
            dict with puzzle and solution data
        """
        settings = self.DIFFICULTY_SETTINGS.get(difficulty, self.DIFFICULTY_SETTINGS['easy'])
        grid_size = settings['grid_size']
        min_cells = settings['min_cells']
        max_cells = settings['max_cells']
        view_time = settings['view_time_ms']

        # Generate random pattern
        total_cells = grid_size * grid_size
        num_highlighted = random.randint(min_cells, min(max_cells, total_cells))

        # Select random cells to highlight
        all_positions = [(r, c) for r in range(grid_size) for c in range(grid_size)]
        highlighted = random.sample(all_positions, num_highlighted)

        # Create solution grid (1 = highlighted, 0 = empty)
        solution_grid = [[0] * grid_size for _ in range(grid_size)]
        for r, c in highlighted:
            solution_grid[r][c] = 1

        return {
            'puzzle_data': {
                'grid_size': grid_size,
                'highlighted_cells': highlighted,  # List of [row, col] positions
                'cell_count': num_highlighted,
                'view_time_ms': view_time,
            },
            'solution_data': {
                'grid': solution_grid,
                'highlighted_cells': highlighted,
            },
            'difficulty': difficulty,
        }

    @staticmethod
    def verify_solution(puzzle_data, submitted_solution):
        """
        Verify a submitted Memory Matrix solution.

        Args:
            puzzle_data: Puzzle data with grid size and highlighted cells
            submitted_solution: dict with 'grid' or 'selected_cells' key

        Returns:
            dict with:
                - correct: bool (True if perfect match)
                - accuracy: float (percentage of correct cells 0-100)
                - correct_count: int (number of correctly identified cells)
                - total_highlighted: int (total cells that should be highlighted)
                - false_positives: int (cells wrongly marked)
                - false_negatives: int (cells missed)
        """
        puzzle_data.get('grid_size', 3)
        expected_cells = set(tuple(c) for c in puzzle_data.get('highlighted_cells', []))

        # Handle both grid format and cell list format
        if 'grid' in submitted_solution:
            grid = submitted_solution['grid']
            submitted_cells = set()
            for r in range(len(grid)):
                for c in range(len(grid[r])):
                    if grid[r][c] == 1:
                        submitted_cells.add((r, c))
        elif 'selected_cells' in submitted_solution:
            submitted_cells = set(tuple(c) for c in submitted_solution['selected_cells'])
        else:
            submitted_cells = set()

        # Calculate metrics
        correct_cells = expected_cells & submitted_cells
        false_positives = submitted_cells - expected_cells
        false_negatives = expected_cells - submitted_cells

        total_highlighted = len(expected_cells)
        correct_count = len(correct_cells)

        # Calculate accuracy
        if total_highlighted == 0:
            accuracy = 100.0 if len(submitted_cells) == 0 else 0.0
        else:
            # Penalize both false positives and false negatives
            errors = len(false_positives) + len(false_negatives)
            accuracy = max(0, (1 - errors / (total_highlighted + len(false_positives))) * 100)

        return {
            'correct': submitted_cells == expected_cells,
            'accuracy': round(accuracy, 1),
            'correct_count': correct_count,
            'total_highlighted': total_highlighted,
            'false_positives': len(false_positives),
            'false_negatives': len(false_negatives),
        }

    @staticmethod
    def calculate_score(accuracy, time_spent_ms, view_time_ms, difficulty):
        """
        Calculate score based on accuracy and speed.

        Args:
            accuracy: Percentage accuracy (0-100)
            time_spent_ms: Time spent on recall in milliseconds
            view_time_ms: Original viewing time
            difficulty: Difficulty level

        Returns:
            int: Score (0-200+)
        """
        # Base score from accuracy
        base_score = accuracy

        # Time bonus - faster recall = higher bonus
        # Max 50 point bonus for very fast recall
        expected_recall_time = view_time_ms * 2  # Expect recall to take ~2x viewing time
        if time_spent_ms < expected_recall_time:
            time_ratio = time_spent_ms / expected_recall_time
            time_bonus = int(50 * (1 - time_ratio))
        else:
            time_bonus = 0

        # Difficulty multiplier
        multipliers = {
            'easy': 1.0,
            'medium': 1.2,
            'hard': 1.5,
            'expert': 2.0,
        }
        multiplier = multipliers.get(difficulty, 1.0)

        total_score = int((base_score + time_bonus) * multiplier)
        return max(0, total_score)


def generate_memory_matrix(difficulty='easy'):
    """
    Convenience function to generate a Memory Matrix challenge.
    """
    generator = MemoryMatrixGenerator()
    return generator.generate(difficulty)


def verify_memory_matrix_solution(puzzle_data, submitted_solution):
    """
    Verify a submitted Memory Matrix solution.

    Returns dict with accuracy metrics.
    """
    return MemoryMatrixGenerator.verify_solution(puzzle_data, submitted_solution)
