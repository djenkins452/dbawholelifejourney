"""
Tests for Brain Training puzzle generators.

Tests that each generator produces valid, solvable puzzles
with correct difficulty scaling.
"""

from django.test import TestCase

from apps.brain_training.services.sudoku import SudokuGenerator, generate_sudoku, verify_sudoku_solution
from apps.brain_training.services.kenken import KenKenGenerator, generate_kenken, verify_kenken_solution
from apps.brain_training.services.nonogram import NonogramGenerator, generate_nonogram
from apps.brain_training.services.word_ladder import WordLadderGenerator, generate_word_ladder, verify_word_ladder_solution
from apps.brain_training.services.memory_matrix import MemoryMatrixGenerator, generate_memory_matrix, verify_memory_matrix_solution


class SudokuGeneratorTests(TestCase):
    """Tests for Sudoku puzzle generation and verification."""

    def test_generate_easy_puzzle(self):
        """Easy puzzles should have ~40 revealed cells."""
        result = generate_sudoku('easy')
        self.assertIn('puzzle_data', result)
        self.assertIn('solution_data', result)

        puzzle = result['puzzle_data']['grid']
        revealed = sum(1 for row in puzzle for cell in row if cell != 0)
        # Easy should have ~40 revealed cells
        self.assertGreaterEqual(revealed, 35)
        self.assertLessEqual(revealed, 45)

    def test_generate_hard_puzzle(self):
        """Hard puzzles should have ~25 revealed cells."""
        result = generate_sudoku('hard')
        puzzle = result['puzzle_data']['grid']
        revealed = sum(1 for row in puzzle for cell in row if cell != 0)
        # Hard should have ~25 revealed cells
        self.assertGreaterEqual(revealed, 20)
        self.assertLessEqual(revealed, 30)

    def test_solution_is_valid(self):
        """Generated solution should be a valid Sudoku."""
        result = generate_sudoku('medium')
        solution = result['solution_data']['grid']

        # Check all rows have 1-9
        for row in solution:
            self.assertEqual(set(row), set(range(1, 10)))

        # Check all columns have 1-9
        for col in range(9):
            col_values = [solution[row][col] for row in range(9)]
            self.assertEqual(set(col_values), set(range(1, 10)))

        # Check all 3x3 boxes have 1-9
        for box_r in range(3):
            for box_c in range(3):
                box_values = []
                for r in range(3):
                    for c in range(3):
                        box_values.append(solution[box_r * 3 + r][box_c * 3 + c])
                self.assertEqual(set(box_values), set(range(1, 10)))

    def test_verify_correct_solution(self):
        """Verify solution should return True for correct answers."""
        result = generate_sudoku('easy')
        puzzle_data = result['puzzle_data']
        solution_data = result['solution_data']

        is_valid = verify_sudoku_solution(puzzle_data, solution_data)
        self.assertTrue(is_valid)

    def test_verify_incorrect_solution(self):
        """Verify solution should return False for wrong answers."""
        result = generate_sudoku('easy')
        puzzle_data = result['puzzle_data']

        # Create a wrong solution
        wrong_solution = {'grid': [[1] * 9 for _ in range(9)]}

        is_valid = verify_sudoku_solution(puzzle_data, wrong_solution)
        self.assertFalse(is_valid)


class KenKenGeneratorTests(TestCase):
    """Tests for KenKen puzzle generation and verification."""

    def test_generate_easy_puzzle(self):
        """Easy KenKen should be 4x4 with simple operations."""
        result = generate_kenken('easy')
        self.assertEqual(result['puzzle_data']['size'], 4)
        self.assertIn('cages', result['puzzle_data'])

    def test_generate_hard_puzzle(self):
        """Hard KenKen should be 6x6."""
        result = generate_kenken('hard')
        self.assertEqual(result['puzzle_data']['size'], 6)

    def test_solution_is_valid_latin_square(self):
        """Generated solution should be a valid Latin square."""
        result = generate_kenken('medium')
        solution = result['solution_data']['grid']
        size = result['puzzle_data']['size']

        # Check rows
        for row in solution:
            self.assertEqual(set(row), set(range(1, size + 1)))

        # Check columns
        for col in range(size):
            col_values = [solution[row][col] for row in range(size)]
            self.assertEqual(set(col_values), set(range(1, size + 1)))

    def test_verify_correct_solution(self):
        """Verify solution should return True for correct answers."""
        result = generate_kenken('easy')
        is_valid = verify_kenken_solution(result['puzzle_data'], result['solution_data'])
        self.assertTrue(is_valid)


class NonogramGeneratorTests(TestCase):
    """Tests for Nonogram puzzle generation."""

    def test_generate_easy_puzzle(self):
        """Easy Nonogram should be 5x5."""
        result = generate_nonogram('easy')
        self.assertEqual(result['puzzle_data']['size'], 5)
        self.assertEqual(len(result['puzzle_data']['row_clues']), 5)
        self.assertEqual(len(result['puzzle_data']['col_clues']), 5)

    def test_generate_medium_puzzle(self):
        """Medium Nonogram should be 10x10."""
        result = generate_nonogram('medium')
        self.assertEqual(result['puzzle_data']['size'], 10)

    def test_clues_match_solution(self):
        """Row and column clues should match the solution."""
        result = generate_nonogram('easy')
        solution = result['solution_data']['grid']
        row_clues = result['puzzle_data']['row_clues']
        col_clues = result['puzzle_data']['col_clues']
        size = result['puzzle_data']['size']

        # Verify row clues
        for i, row in enumerate(solution):
            expected_clue = self._calculate_clue(row)
            self.assertEqual(expected_clue, row_clues[i])

        # Verify column clues
        for j in range(size):
            col = [solution[i][j] for i in range(size)]
            expected_clue = self._calculate_clue(col)
            self.assertEqual(expected_clue, col_clues[j])

    def _calculate_clue(self, line):
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


class WordLadderGeneratorTests(TestCase):
    """Tests for Word Ladder puzzle generation."""

    def test_generate_easy_puzzle(self):
        """Easy Word Ladder should use 3-letter words."""
        result = generate_word_ladder('easy')
        self.assertEqual(result['puzzle_data']['word_length'], 3)
        self.assertEqual(len(result['puzzle_data']['start_word']), 3)
        self.assertEqual(len(result['puzzle_data']['end_word']), 3)

    def test_generate_hard_puzzle(self):
        """Hard Word Ladder should use 5-letter words."""
        result = generate_word_ladder('hard')
        self.assertEqual(result['puzzle_data']['word_length'], 5)

    def test_solution_path_is_valid(self):
        """Solution path should have valid single-letter changes."""
        result = generate_word_ladder('easy')
        path = result['solution_data']['path']

        for i in range(len(path) - 1):
            word1 = path[i]
            word2 = path[i + 1]
            # Count differences
            diff = sum(1 for a, b in zip(word1, word2) if a != b)
            self.assertEqual(diff, 1, f"More than one letter changed: {word1} -> {word2}")

    def test_verify_correct_solution(self):
        """Verify solution should return True for valid paths."""
        result = generate_word_ladder('easy')
        is_valid = verify_word_ladder_solution(result['puzzle_data'], result['solution_data'])
        self.assertTrue(is_valid)


class MemoryMatrixGeneratorTests(TestCase):
    """Tests for Memory Matrix challenge generation."""

    def test_generate_easy_challenge(self):
        """Easy Memory Matrix should be 3x3 with 3-4 cells."""
        result = generate_memory_matrix('easy')
        self.assertEqual(result['puzzle_data']['grid_size'], 3)
        cell_count = result['puzzle_data']['cell_count']
        self.assertGreaterEqual(cell_count, 3)
        self.assertLessEqual(cell_count, 4)

    def test_generate_hard_challenge(self):
        """Hard Memory Matrix should be 5x5 with 8-12 cells."""
        result = generate_memory_matrix('hard')
        self.assertEqual(result['puzzle_data']['grid_size'], 5)
        cell_count = result['puzzle_data']['cell_count']
        self.assertGreaterEqual(cell_count, 8)
        self.assertLessEqual(cell_count, 12)

    def test_verify_perfect_solution(self):
        """Perfect solution should have 100% accuracy."""
        result = generate_memory_matrix('easy')

        # Submit the exact solution
        submitted = {'selected_cells': result['puzzle_data']['highlighted_cells']}
        verification = verify_memory_matrix_solution(result['puzzle_data'], submitted)

        self.assertTrue(verification['correct'])
        self.assertEqual(verification['accuracy'], 100.0)
        self.assertEqual(verification['false_positives'], 0)
        self.assertEqual(verification['false_negatives'], 0)

    def test_verify_partial_solution(self):
        """Partial solution should have <100% accuracy."""
        result = generate_memory_matrix('medium')
        highlighted = result['puzzle_data']['highlighted_cells']

        # Submit only half the cells
        submitted = {'selected_cells': highlighted[:len(highlighted) // 2]}
        verification = verify_memory_matrix_solution(result['puzzle_data'], submitted)

        self.assertFalse(verification['correct'])
        self.assertLess(verification['accuracy'], 100.0)
        self.assertGreater(verification['false_negatives'], 0)
