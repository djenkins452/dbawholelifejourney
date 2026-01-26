"""
Sudoku Generator Service

Generates valid 9x9 Sudoku puzzles with unique solutions.
Difficulty is controlled by the number of revealed cells.
"""

import random
from copy import deepcopy


class SudokuGenerator:
    """
    Generates and validates Sudoku puzzles.

    Puzzle generation process:
    1. Generate a complete valid solution
    2. Remove cells while ensuring unique solution
    3. Return puzzle and solution
    """

    # Difficulty settings: number of revealed cells
    DIFFICULTY_SETTINGS = {
        'easy': 40,       # 40 revealed, 41 blanks
        'medium': 32,     # 32 revealed, 49 blanks
        'hard': 25,       # 25 revealed, 56 blanks
        'expert': 20,     # 20 revealed, 61 blanks
    }

    def __init__(self):
        self.grid = [[0] * 9 for _ in range(9)]

    def generate(self, difficulty='medium'):
        """
        Generate a new Sudoku puzzle.

        Args:
            difficulty: 'easy', 'medium', 'hard', or 'expert'

        Returns:
            dict with 'puzzle' (list of lists) and 'solution' (list of lists)
        """
        # Generate complete solution
        self._fill_grid()
        solution = deepcopy(self.grid)

        # Get target revealed cells for difficulty
        target_revealed = self.DIFFICULTY_SETTINGS.get(difficulty, 32)

        # Remove cells while maintaining unique solution
        puzzle = self._create_puzzle(solution, target_revealed)

        return {
            'puzzle': puzzle,
            'solution': solution,
            'difficulty': difficulty,
            'revealed_count': sum(1 for row in puzzle for cell in row if cell != 0),
        }

    def _fill_grid(self):
        """Fill the grid with a valid complete Sudoku solution."""
        self.grid = [[0] * 9 for _ in range(9)]
        self._solve()

    def _solve(self):
        """Solve the Sudoku using backtracking with randomization."""
        empty = self._find_empty()
        if not empty:
            return True

        row, col = empty
        numbers = list(range(1, 10))
        random.shuffle(numbers)

        for num in numbers:
            if self._is_valid(row, col, num):
                self.grid[row][col] = num
                if self._solve():
                    return True
                self.grid[row][col] = 0

        return False

    def _find_empty(self):
        """Find an empty cell (value 0)."""
        for i in range(9):
            for j in range(9):
                if self.grid[i][j] == 0:
                    return (i, j)
        return None

    def _is_valid(self, row, col, num):
        """Check if placing num at (row, col) is valid."""
        # Check row
        if num in self.grid[row]:
            return False

        # Check column
        if num in [self.grid[i][col] for i in range(9)]:
            return False

        # Check 3x3 box
        box_row, box_col = 3 * (row // 3), 3 * (col // 3)
        for i in range(box_row, box_row + 3):
            for j in range(box_col, box_col + 3):
                if self.grid[i][j] == num:
                    return False

        return True

    def _create_puzzle(self, solution, target_revealed):
        """
        Create puzzle by removing cells from solution.

        Ensures the puzzle has a unique solution.
        """
        puzzle = deepcopy(solution)
        cells = [(i, j) for i in range(9) for j in range(9)]
        random.shuffle(cells)

        # Count of cells to remove
        cells_to_remove = 81 - target_revealed
        removed = 0

        for row, col in cells:
            if removed >= cells_to_remove:
                break

            # Try removing this cell
            backup = puzzle[row][col]
            puzzle[row][col] = 0

            # Check if still has unique solution
            if self._count_solutions(deepcopy(puzzle)) != 1:
                # Put it back - removing this cell creates ambiguity
                puzzle[row][col] = backup
            else:
                removed += 1

        return puzzle

    def _count_solutions(self, grid, limit=2):
        """
        Count solutions up to a limit.

        Args:
            grid: Puzzle grid
            limit: Stop counting after this many solutions

        Returns:
            Number of solutions found (capped at limit)
        """
        solutions = [0]

        def solve_count(g):
            if solutions[0] >= limit:
                return

            empty = None
            for i in range(9):
                for j in range(9):
                    if g[i][j] == 0:
                        empty = (i, j)
                        break
                if empty:
                    break

            if not empty:
                solutions[0] += 1
                return

            row, col = empty
            for num in range(1, 10):
                if self._is_valid_grid(g, row, col, num):
                    g[row][col] = num
                    solve_count(g)
                    g[row][col] = 0

        solve_count(grid)
        return solutions[0]

    def _is_valid_grid(self, grid, row, col, num):
        """Check validity for a given grid (not self.grid)."""
        if num in grid[row]:
            return False

        if num in [grid[i][col] for i in range(9)]:
            return False

        box_row, box_col = 3 * (row // 3), 3 * (col // 3)
        for i in range(box_row, box_row + 3):
            for j in range(box_col, box_col + 3):
                if grid[i][j] == num:
                    return False

        return True

    @staticmethod
    def verify_solution(puzzle, submitted):
        """
        Verify that a submitted solution is correct.

        Args:
            puzzle: Original puzzle (list of lists)
            submitted: User's submitted solution (list of lists)

        Returns:
            bool: True if solution is valid and correct
        """
        # Check dimensions
        if len(submitted) != 9:
            return False
        for row in submitted:
            if len(row) != 9:
                return False

        # Check that puzzle cells weren't changed
        for i in range(9):
            for j in range(9):
                if puzzle[i][j] != 0 and puzzle[i][j] != submitted[i][j]:
                    return False

        # Check all rows
        for row in submitted:
            if set(row) != set(range(1, 10)):
                return False

        # Check all columns
        for col in range(9):
            if set(submitted[row][col] for row in range(9)) != set(range(1, 10)):
                return False

        # Check all 3x3 boxes
        for box_row in range(3):
            for box_col in range(3):
                box = []
                for i in range(3):
                    for j in range(3):
                        box.append(submitted[box_row * 3 + i][box_col * 3 + j])
                if set(box) != set(range(1, 10)):
                    return False

        return True


def generate_sudoku(difficulty='medium'):
    """
    Convenience function to generate a Sudoku puzzle.

    Returns:
        dict with puzzle_data and solution_data formatted for the Challenge model
    """
    generator = SudokuGenerator()
    result = generator.generate(difficulty)

    return {
        'puzzle_data': {
            'grid': result['puzzle'],
            'revealed_count': result['revealed_count'],
        },
        'solution_data': {
            'grid': result['solution'],
        },
    }


def verify_sudoku_solution(puzzle_data, submitted_solution):
    """
    Verify a submitted Sudoku solution.

    Args:
        puzzle_data: The puzzle_data from Challenge model
        submitted_solution: User's submitted solution dict with 'grid' key

    Returns:
        bool: True if correct
    """
    puzzle_grid = puzzle_data.get('grid', [])
    submitted_grid = submitted_solution.get('grid', [])

    return SudokuGenerator.verify_solution(puzzle_grid, submitted_grid)
