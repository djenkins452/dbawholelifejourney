"""
KenKen/Calcudoku Generator Service

Generates KenKen puzzles with mathematical cages.
Each cage has an operation (+, -, *, /) and target value.
"""

import random
from copy import deepcopy
from itertools import permutations


class KenKenGenerator:
    """
    Generates valid KenKen puzzles.

    Process:
    1. Generate a Latin square (valid grid)
    2. Divide into cages
    3. Assign operations and calculate targets
    """

    # Difficulty affects grid size and cage complexity
    DIFFICULTY_SETTINGS = {
        'easy': {'size': 4, 'max_cage_size': 2, 'operations': ['+']},
        'medium': {'size': 5, 'max_cage_size': 3, 'operations': ['+', '-', '*']},
        'hard': {'size': 6, 'max_cage_size': 4, 'operations': ['+', '-', '*', '/']},
    }

    def __init__(self, size=4):
        self.size = size
        self.grid = [[0] * size for _ in range(size)]
        self.cages = []

    def generate(self, difficulty='easy'):
        """
        Generate a new KenKen puzzle.

        Args:
            difficulty: 'easy', 'medium', or 'hard'

        Returns:
            dict with puzzle and solution data
        """
        settings = self.DIFFICULTY_SETTINGS.get(difficulty, self.DIFFICULTY_SETTINGS['easy'])
        self.size = settings['size']
        self.grid = [[0] * self.size for _ in range(self.size)]

        # Generate valid Latin square
        self._generate_latin_square()
        solution = deepcopy(self.grid)

        # Generate cages
        self.cages = self._generate_cages(settings['max_cage_size'], settings['operations'])

        # Format puzzle data
        puzzle_cages = []
        for cells, operation, target in self.cages:
            puzzle_cages.append({
                'cells': cells,  # List of [row, col] positions
                'operation': operation,
                'target': target,
            })

        return {
            'puzzle_data': {
                'size': self.size,
                'cages': puzzle_cages,
            },
            'solution_data': {
                'grid': solution,
            },
            'difficulty': difficulty,
        }

    def _generate_latin_square(self):
        """Generate a valid Latin square (each number 1-n appears once per row/col)."""
        n = self.size

        # Start with first row shuffled
        first_row = list(range(1, n + 1))
        random.shuffle(first_row)
        self.grid[0] = first_row

        # Fill remaining rows
        for row in range(1, n):
            if not self._fill_row(row):
                # Restart if stuck
                return self._generate_latin_square()

    def _fill_row(self, row):
        """Fill a row maintaining Latin square property."""
        n = self.size
        available = [set(range(1, n + 1)) for _ in range(n)]

        # Remove values already in each column
        for col in range(n):
            for prev_row in range(row):
                available[col].discard(self.grid[prev_row][col])

        # Try to fill using backtracking
        return self._fill_row_backtrack(row, 0, available, set())

    def _fill_row_backtrack(self, row, col, available, used):
        """Backtracking helper for filling rows."""
        if col == self.size:
            return True

        candidates = list(available[col] - used)
        random.shuffle(candidates)

        for num in candidates:
            self.grid[row][col] = num
            used.add(num)
            if self._fill_row_backtrack(row, col + 1, available, used):
                return True
            used.remove(num)

        self.grid[row][col] = 0
        return False

    def _generate_cages(self, max_cage_size, operations):
        """
        Generate random cages covering all cells.

        Returns list of (cells, operation, target) tuples.
        """
        n = self.size
        used = [[False] * n for _ in range(n)]
        cages = []

        while True:
            # Find first unused cell
            start = None
            for i in range(n):
                for j in range(n):
                    if not used[i][j]:
                        start = (i, j)
                        break
                if start:
                    break

            if not start:
                break

            # Grow a cage from this cell
            cage_size = random.randint(1, min(max_cage_size, 4))
            cells = self._grow_cage(start, cage_size, used)

            # Mark cells as used
            for r, c in cells:
                used[r][c] = True

            # Determine operation and target
            values = [self.grid[r][c] for r, c in cells]
            operation, target = self._assign_operation(values, operations)

            cages.append((cells, operation, target))

        return cages

    def _grow_cage(self, start, target_size, used):
        """Grow a cage from a starting cell."""
        cells = [list(start)]
        candidates = set()

        def add_neighbors(r, c):
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = r + dr, c + dc
                if 0 <= nr < self.size and 0 <= nc < self.size:
                    if not used[nr][nc] and [nr, nc] not in cells:
                        candidates.add((nr, nc))

        add_neighbors(start[0], start[1])

        while len(cells) < target_size and candidates:
            # Pick a random candidate
            next_cell = random.choice(list(candidates))
            candidates.remove(next_cell)
            cells.append(list(next_cell))
            add_neighbors(next_cell[0], next_cell[1])

        return cells

    def _assign_operation(self, values, allowed_ops):
        """
        Assign an operation and calculate target for cage values.
        """
        if len(values) == 1:
            # Single cell - no operation needed
            return '', values[0]

        # Try different operations
        possible = []

        if '+' in allowed_ops:
            possible.append(('+', sum(values)))

        if '*' in allowed_ops:
            product = 1
            for v in values:
                product *= v
            possible.append(('*', product))

        if len(values) == 2:
            if '-' in allowed_ops:
                diff = abs(values[0] - values[1])
                possible.append(('-', diff))

            if '/' in allowed_ops:
                a, b = max(values), min(values)
                if b != 0 and a % b == 0:
                    possible.append(('/', a // b))

        if not possible:
            possible = [('+', sum(values))]

        return random.choice(possible)

    @staticmethod
    def verify_solution(puzzle_data, submitted_solution):
        """
        Verify a submitted KenKen solution.

        Args:
            puzzle_data: Puzzle data with size and cages
            submitted_solution: dict with 'grid' key

        Returns:
            bool: True if correct
        """
        size = puzzle_data.get('size', 4)
        cages = puzzle_data.get('cages', [])
        grid = submitted_solution.get('grid', [])

        # Check dimensions
        if len(grid) != size:
            return False
        for row in grid:
            if len(row) != size:
                return False

        # Check Latin square property
        for row in grid:
            if set(row) != set(range(1, size + 1)):
                return False

        for col in range(size):
            if set(grid[row][col] for row in range(size)) != set(range(1, size + 1)):
                return False

        # Check all cages
        for cage in cages:
            cells = cage['cells']
            operation = cage['operation']
            target = cage['target']

            values = [grid[r][c] for r, c in cells]

            if not KenKenGenerator._check_cage(values, operation, target):
                return False

        return True

    @staticmethod
    def _check_cage(values, operation, target):
        """Check if cage values satisfy the operation/target."""
        if not operation or operation == '':
            # Single cell
            return len(values) == 1 and values[0] == target

        if operation == '+':
            return sum(values) == target

        if operation == '*':
            product = 1
            for v in values:
                product *= v
            return product == target

        if operation == '-':
            if len(values) != 2:
                return False
            return abs(values[0] - values[1]) == target

        if operation == '/':
            if len(values) != 2:
                return False
            a, b = max(values), min(values)
            return b != 0 and a / b == target

        return False


def generate_kenken(difficulty='easy'):
    """
    Convenience function to generate a KenKen puzzle.
    """
    generator = KenKenGenerator()
    return generator.generate(difficulty)


def verify_kenken_solution(puzzle_data, submitted_solution):
    """
    Verify a submitted KenKen solution.
    """
    return KenKenGenerator.verify_solution(puzzle_data, submitted_solution)
