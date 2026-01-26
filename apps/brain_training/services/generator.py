"""
Challenge Generator Factory

Central factory for generating and verifying challenges across all game types.
"""

from ..models import Challenge, Game
from .sudoku import generate_sudoku, verify_sudoku_solution
from .kenken import generate_kenken, verify_kenken_solution
from .nonogram import generate_nonogram, verify_nonogram_solution
from .word_ladder import generate_word_ladder, verify_word_ladder_solution
from .memory_matrix import generate_memory_matrix, verify_memory_matrix_solution


# Game slug to generator function mapping
GENERATORS = {
    'sudoku': generate_sudoku,
    'kenken': generate_kenken,
    'nonogram': generate_nonogram,
    'word_ladder': generate_word_ladder,
    'memory_matrix': generate_memory_matrix,
}

# Game slug to verifier function mapping
VERIFIERS = {
    'sudoku': verify_sudoku_solution,
    'kenken': verify_kenken_solution,
    'nonogram': verify_nonogram_solution,
    'word_ladder': verify_word_ladder_solution,
    'memory_matrix': verify_memory_matrix_solution,
}


def generate_challenge(game_slug: str, difficulty: str = 'medium') -> dict:
    """
    Generate a new challenge for the specified game type.

    Args:
        game_slug: Game identifier ('sudoku', 'kenken', etc.)
        difficulty: Difficulty level

    Returns:
        dict with puzzle_data and solution_data

    Raises:
        ValueError: If game type is not supported
    """
    generator = GENERATORS.get(game_slug)
    if not generator:
        raise ValueError(f"Unknown game type: {game_slug}")

    return generator(difficulty)


def verify_solution(game_slug: str, puzzle_data: dict, submitted_solution: dict) -> bool:
    """
    Verify a submitted solution for the specified game type.

    Args:
        game_slug: Game identifier
        puzzle_data: The original puzzle data
        submitted_solution: The user's submitted solution

    Returns:
        bool: True if solution is correct

    Raises:
        ValueError: If game type is not supported
    """
    verifier = VERIFIERS.get(game_slug)
    if not verifier:
        raise ValueError(f"Unknown game type: {game_slug}")

    result = verifier(puzzle_data, submitted_solution)

    # Handle both bool returns and dict returns (memory matrix)
    if isinstance(result, dict):
        return result.get('correct', False)
    return result


def create_challenge_record(game: Game, difficulty: str = 'medium') -> Challenge:
    """
    Generate and persist a new challenge to the database.

    Args:
        game: Game model instance
        difficulty: Difficulty level

    Returns:
        Challenge model instance
    """
    # Generate the challenge
    data = generate_challenge(game.slug, difficulty)

    puzzle_data = data['puzzle_data']
    solution_data = data['solution_data']

    # Generate unique ID and hash solution
    challenge_id = Challenge.generate_challenge_id(game.slug, puzzle_data)
    solution_hash = Challenge.hash_solution(solution_data)

    # Check if this challenge already exists
    existing = Challenge.objects.filter(challenge_id=challenge_id).first()
    if existing:
        return existing

    # Create new challenge
    challenge = Challenge.objects.create(
        game=game,
        challenge_id=challenge_id,
        difficulty=difficulty,
        puzzle_data=puzzle_data,
        solution_data=solution_data,
        solution_hash=solution_hash,
        is_pregenerated=True,
    )

    return challenge


def get_or_create_challenges(game: Game, difficulty: str, count: int = 10) -> list:
    """
    Get existing challenges or create new ones if needed.

    Args:
        game: Game model instance
        difficulty: Difficulty level
        count: Number of challenges needed

    Returns:
        List of Challenge instances
    """
    # First, try to get existing challenges
    existing = list(Challenge.objects.filter(
        game=game,
        difficulty=difficulty,
    ).order_by('?')[:count])

    needed = count - len(existing)

    # Generate more if needed
    for _ in range(needed):
        try:
            challenge = create_challenge_record(game, difficulty)
            existing.append(challenge)
        except Exception:
            # If generation fails, continue with what we have
            pass

    return existing[:count]


def prefill_queue(user, game: Game, difficulty: str = 'medium', min_size: int = 5):
    """
    Ensure user has at least min_size challenges in their queue.

    Args:
        user: User model instance
        game: Game model instance
        difficulty: Difficulty level
        min_size: Minimum queue size to maintain
    """
    from ..models import ChallengeQueue

    current_size = ChallengeQueue.queue_size(user, game)

    if current_size >= min_size:
        return

    needed = min_size - current_size
    challenges = get_or_create_challenges(game, difficulty, needed)

    # Filter out challenges already in queue
    existing_ids = set(
        ChallengeQueue.objects.filter(
            user=user, game=game
        ).values_list('challenge_id', flat=True)
    )

    new_challenges = [c for c in challenges if c.id not in existing_ids]

    if new_challenges:
        ChallengeQueue.add_to_queue(user, game, new_challenges)
