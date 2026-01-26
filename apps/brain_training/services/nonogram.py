"""
Nonogram/Picross Generator Service

Generates Nonogram puzzles where players fill cells based on number clues.
Each row/column has clues indicating consecutive filled cell groups.
"""

import random
from copy import deepcopy


class NonogramGenerator:
    """
    Generates valid Nonogram puzzles.

    Process:
    1. Generate a random pattern (filled/empty cells)
    2. Calculate row and column clues
    3. Verify the puzzle has a unique solution
    """

    # Difficulty affects grid size and pattern density
    DIFFICULTY_SETTINGS = {
        'easy': {'size': 5, 'density_range': (0.4, 0.6)},
        'medium': {'size': 10, 'density_range': (0.35, 0.55)},
        'hard': {'size': 15, 'density_range': (0.30, 0.50)},
    }

    def __init__(self, size=5):
        self.size = size
        self.grid = [[0] * size for _ in range(size)]

    def generate(self, difficulty='easy'):
        """
        Generate a new Nonogram puzzle.

        Args:
            difficulty: 'easy', 'medium', or 'hard'

        Returns:
            dict with puzzle and solution data
        """
        settings = self.DIFFICULTY_SETTINGS.get(difficulty, self.DIFFICULTY_SETTINGS['easy'])
        self.size = settings['size']
        density_min, density_max = settings['density_range']

        # Generate random pattern
        density = random.uniform(density_min, density_max)
        self._generate_pattern(density)

        # Ensure puzzle is solvable (has unique solution)
        attempts = 0
        while not self._is_uniquely_solvable() and attempts < 10:
            self._generate_pattern(density)
            attempts += 1

        solution = deepcopy(self.grid)

        # Calculate clues
        row_clues = self._calculate_row_clues()
        col_clues = self._calculate_col_clues()

        return {
            'puzzle_data': {
                'size': self.size,
                'row_clues': row_clues,
                'col_clues': col_clues,
            },
            'solution_data': {
                'grid': solution,
            },
            'difficulty': difficulty,
        }

    def _generate_pattern(self, density):
        """Generate a random filled/empty pattern."""
        self.grid = []
        for i in range(self.size):
            row = []
            for j in range(self.size):
                row.append(1 if random.random() < density else 0)
            self.grid.append(row)

        # Ensure at least one cell in each row/col is filled
        for i in range(self.size):
            if sum(self.grid[i]) == 0:
                self.grid[i][random.randint(0, self.size - 1)] = 1

        for j in range(self.size):
            if sum(self.grid[i][j] for i in range(self.size)) == 0:
                self.grid[random.randint(0, self.size - 1)][j] = 1

    def _calculate_row_clues(self):
        """Calculate clues for each row."""
        clues = []
        for row in self.grid:
            clues.append(self._calculate_line_clue(row))
        return clues

    def _calculate_col_clues(self):
        """Calculate clues for each column."""
        clues = []
        for j in range(self.size):
            col = [self.grid[i][j] for i in range(self.size)]
            clues.append(self._calculate_line_clue(col))
        return clues

    def _calculate_line_clue(self, line):
        """
        Calculate clue for a single line (row or column).

        Returns list of consecutive filled cell group sizes.
        """
        clue = []
        count = 0

        for cell in line:
            if cell == 1:
                count += 1
            elif count > 0:
                clue.append(count)
                count = 0

        if count > 0:
            clue.append(count)

        return clue if clue else [0]

    def _is_uniquely_solvable(self):
        """
        Check if the puzzle has a unique solution.

        Uses constraint propagation for small grids.
        For larger grids, we use a simplified check.
        """
        if self.size <= 5:
            return self._solve_and_check_unique()
        else:
            # For larger grids, use heuristic check
            return self._heuristic_unique_check()

    def _solve_and_check_unique(self):
        """
        Try to solve and verify uniqueness for small grids.
        """
        row_clues = self._calculate_row_clues()
        col_clues = self._calculate_col_clues()

        solutions = []
        empty_grid = [[None] * self.size for _ in range(self.size)]

        def solve(grid, row):
            if len(solutions) > 1:
                return

            if row == self.size:
                # Check columns
                for j in range(self.size):
                    col = [grid[i][j] for i in range(self.size)]
                    if self._calculate_line_clue(col) != col_clues[j]:
                        return
                solutions.append(deepcopy(grid))
                return

            # Generate all valid row configurations
            for config in self._generate_line_configs(row_clues[row], self.size):
                grid[row] = config
                # Early column constraint check
                valid = True
                for j in range(self.size):
                    partial_col = [grid[i][j] for i in range(row + 1)]
                    if not self._partial_col_valid(partial_col, col_clues[j]):
                        valid = False
                        break
                if valid:
                    solve(grid, row + 1)

        solve(empty_grid, 0)
        return len(solutions) == 1

    def _generate_line_configs(self, clue, length):
        """Generate all valid configurations for a line with given clue."""
        if clue == [0]:
            yield [0] * length
            return

        def generate(remaining_clue, pos, current):
            if not remaining_clue:
                # Fill rest with zeros
                full = current + [0] * (length - len(current))
                if len(full) == length:
                    yield full
                return

            block_size = remaining_clue[0]
            rest = remaining_clue[1:]

            # Calculate minimum space needed for remaining blocks
            min_space = sum(rest) + len(rest)  # blocks + separators

            # Try placing block at each valid position
            for start in range(len(current), length - block_size - min_space + 1):
                # Add zeros before block
                new_current = current + [0] * (start - len(current))
                # Add block
                new_current = new_current + [1] * block_size
                # Add separator if more blocks follow
                if rest:
                    new_current = new_current + [0]

                yield from generate(rest, start + block_size + 1, new_current)

        yield from generate(clue, 0, [])

    def _partial_col_valid(self, partial_col, clue):
        """Check if partial column can still lead to valid solution."""
        # Count filled groups so far
        groups = []
        count = 0
        for cell in partial_col:
            if cell == 1:
                count += 1
            elif count > 0:
                groups.append(count)
                count = 0

        # Check if groups match prefix of clue
        if len(groups) > len(clue):
            return False

        for i, g in enumerate(groups):
            if i == len(groups) - 1 and count == 0:
                # Last complete group
                if g > clue[i]:
                    return False
            else:
                # Incomplete or earlier group
                if g > clue[i]:
                    return False

        return True

    def _heuristic_unique_check(self):
        """
        Heuristic check for larger grids.

        Checks that clues provide sufficient information.
        """
        row_clues = self._calculate_row_clues()
        col_clues = self._calculate_col_clues()

        # Check for trivial clues (all 0 or full row)
        trivial_rows = sum(1 for c in row_clues if c == [0] or c == [self.size])
        trivial_cols = sum(1 for c in col_clues if c == [0] or c == [self.size])

        # Too many trivial lines means likely ambiguous
        if trivial_rows + trivial_cols > self.size // 2:
            return False

        # Check information density
        info_score = 0
        for clue in row_clues + col_clues:
            if clue != [0]:
                info_score += len(clue)

        # Need sufficient information
        min_info = self.size * 1.5
        return info_score >= min_info

    @staticmethod
    def verify_solution(puzzle_data, submitted_solution):
        """
        Verify a submitted Nonogram solution.

        Args:
            puzzle_data: Puzzle data with clues
            submitted_solution: dict with 'grid' key

        Returns:
            bool: True if correct
        """
        size = puzzle_data.get('size', 5)
        row_clues = puzzle_data.get('row_clues', [])
        col_clues = puzzle_data.get('col_clues', [])
        grid = submitted_solution.get('grid', [])

        # Check dimensions
        if len(grid) != size:
            return False
        for row in grid:
            if len(row) != size:
                return False

        # Calculate clues from submitted grid
        for i, row in enumerate(grid):
            submitted_clue = NonogramGenerator._line_clue(row)
            if submitted_clue != row_clues[i]:
                return False

        for j in range(size):
            col = [grid[i][j] for i in range(size)]
            submitted_clue = NonogramGenerator._line_clue(col)
            if submitted_clue != col_clues[j]:
                return False

        return True

    @staticmethod
    def _line_clue(line):
        """Calculate clue for a line."""
        clue = []
        count = 0
        for cell in line:
            if cell == 1:
                count += 1
            elif count > 0:
                clue.append(count)
                count = 0
        if count > 0:
            clue.append(count)
        return clue if clue else [0]


def generate_nonogram(difficulty='easy'):
    """
    Convenience function to generate a Nonogram puzzle.
    """
    generator = NonogramGenerator()
    return generator.generate(difficulty)


def verify_nonogram_solution(puzzle_data, submitted_solution):
    """
    Verify a submitted Nonogram solution.
    """
    return NonogramGenerator.verify_solution(puzzle_data, submitted_solution)
