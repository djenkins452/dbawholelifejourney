"""
Word Ladder Generator Service

Generates Word Ladder puzzles where players transform one word to another
by changing one letter at a time, with each step being a valid word.
"""

import random
from collections import deque


class WordLadderGenerator:
    """
    Generates Word Ladder puzzles using BFS to find valid paths.
    """

    # Difficulty settings: word length and path length
    DIFFICULTY_SETTINGS = {
        'easy': {'word_length': 3, 'min_path': 2, 'max_path': 4},
        'medium': {'word_length': 4, 'min_path': 4, 'max_path': 6},
        'hard': {'word_length': 5, 'min_path': 6, 'max_path': 10},
    }

    # Common words for each length (subset for fast generation)
    WORD_LISTS = {
        3: [
            'cat', 'bat', 'hat', 'rat', 'sat', 'mat', 'pat', 'fat',
            'car', 'bar', 'far', 'jar', 'tar', 'war',
            'dog', 'hog', 'log', 'fog', 'jog', 'cog',
            'hot', 'pot', 'dot', 'got', 'lot', 'not', 'rot',
            'run', 'bun', 'fun', 'gun', 'sun', 'pun',
            'pen', 'hen', 'men', 'ten', 'den',
            'bed', 'red', 'led', 'fed', 'wed',
            'big', 'dig', 'fig', 'pig', 'wig', 'rig',
            'cup', 'pup', 'sup',
            'box', 'fox', 'pox',
            'map', 'cap', 'gap', 'lap', 'nap', 'tap', 'rap', 'sap',
            'tip', 'dip', 'hip', 'lip', 'rip', 'sip', 'zip',
            'top', 'hop', 'mop', 'pop', 'cop',
            'bit', 'fit', 'hit', 'kit', 'pit', 'sit', 'wit',
            'but', 'cut', 'gut', 'hut', 'jut', 'nut', 'put', 'rut',
            'bad', 'dad', 'had', 'lad', 'mad', 'pad', 'sad',
            'bag', 'rag', 'tag', 'wag', 'lag',
            'add', 'odd',
            'age', 'ace', 'ice',
            'air', 'aim', 'aid',
            'all', 'ill',
            'and', 'end',
            'ant', 'act', 'art',
            'any', 'bay', 'day', 'gay', 'hay', 'jay', 'lay', 'may',
            'pay', 'ray', 'say', 'way',
        ],
        4: [
            'cold', 'bold', 'fold', 'gold', 'hold', 'mold', 'sold', 'told',
            'warm', 'worm', 'word', 'work', 'wore', 'woke',
            'head', 'bead', 'dead', 'lead', 'read', 'heal', 'heat', 'heap',
            'tail', 'fail', 'hail', 'jail', 'mail', 'nail', 'pail', 'rail', 'sail',
            'talk', 'walk', 'tall', 'wall', 'ball', 'call', 'fall', 'hall', 'mall',
            'back', 'hack', 'jack', 'lack', 'pack', 'rack', 'sack', 'tack',
            'bank', 'rank', 'tank', 'sank',
            'base', 'case', 'vase', 'ease',
            'bear', 'dear', 'fear', 'gear', 'hear', 'near', 'pear', 'rear', 'tear', 'wear', 'year',
            'beat', 'feat', 'heat', 'meat', 'neat', 'peat', 'seat',
            'best', 'fest', 'jest', 'nest', 'pest', 'rest', 'test', 'vest', 'west', 'zest',
            'bird', 'girl', 'firm', 'fire',
            'blue', 'blur', 'glue', 'clue',
            'boat', 'coat', 'goat', 'moat',
            'bone', 'cone', 'done', 'gone', 'lone', 'none', 'tone', 'zone',
            'book', 'cook', 'hook', 'look', 'nook', 'took',
            'born', 'corn', 'horn', 'morn', 'torn', 'worn',
            'cake', 'fake', 'lake', 'make', 'rake', 'sake', 'take', 'wake',
            'came', 'dame', 'fame', 'game', 'lame', 'name', 'same', 'tame',
            'card', 'hard', 'yard', 'ward',
            'care', 'bare', 'dare', 'fare', 'hare', 'mare', 'pare', 'rare', 'ware',
            'cart', 'dart', 'fart', 'hart', 'mart', 'part', 'tart',
            'city', 'pity',
            'clay', 'play', 'slay', 'flay',
            'code', 'mode', 'node', 'rode',
            'coin', 'join',
            'come', 'dome', 'home', 'rome', 'some', 'tome',
            'cool', 'fool', 'pool', 'tool',
            'copy', 'cozy',
            'core', 'bore', 'fore', 'gore', 'more', 'pore', 'sore', 'tore', 'wore',
            'cost', 'host', 'lost', 'most', 'post',
            'date', 'fate', 'gate', 'hate', 'late', 'mate', 'rate',
            'deal', 'heal', 'meal', 'peal', 'real', 'seal', 'teal', 'zeal',
            'deep', 'keep', 'peep', 'seep', 'weep',
            'door', 'poor', 'moor',
            'down', 'gown', 'town',
            'draw', 'flaw', 'claw',
            'dust', 'bust', 'gust', 'just', 'lust', 'must', 'rust',
            'each',
            'east', 'fast', 'last', 'mast', 'past', 'vast',
            'edge',
            'face', 'lace', 'pace', 'race',
            'fact', 'pact', 'tact',
            'fair', 'hair', 'pair', 'lair',
            'farm', 'harm', 'warm',
            'fast', 'cast', 'last', 'mast', 'past', 'vast',
            'feed', 'need', 'seed', 'weed',
            'feel', 'heel', 'peel', 'reel',
            'fill', 'bill', 'dill', 'gill', 'hill', 'kill', 'mill', 'pill', 'will',
            'find', 'bind', 'kind', 'mind', 'wind',
            'fine', 'dine', 'line', 'mine', 'nine', 'pine', 'vine', 'wine',
            'fish', 'dish', 'wish',
            'five', 'dive', 'give', 'hive', 'live',
            'flat', 'that', 'chat', 'what',
            'flow', 'blow', 'glow', 'slow', 'show', 'snow',
            'food', 'good', 'hood', 'mood', 'wood',
            'foot', 'boot', 'hoot', 'loot', 'root', 'soot',
            'form', 'norm', 'dorm',
            'four', 'hour', 'pour', 'sour', 'tour', 'your',
            'free', 'tree', 'flee',
            'from', 'frog', 'from',
            'full', 'bull', 'dull', 'gull', 'hull', 'lull', 'mull', 'pull',
        ],
        5: [
            'black', 'blank', 'clank', 'plank', 'prank', 'frank', 'crank',
            'block', 'clock', 'flock', 'shock', 'stock',
            'blood', 'flood', 'brood',
            'blown', 'brown', 'crown', 'drown', 'frown', 'grown', 'shown', 'known',
            'board', 'hoard',
            'boast', 'coast', 'roast', 'toast',
            'bound', 'found', 'ground', 'hound', 'mound', 'pound', 'round', 'sound', 'wound',
            'brake', 'break', 'creak', 'freak', 'sneak', 'speak', 'steak', 'tweak', 'wreak',
            'brand', 'grand', 'stand',
            'brave', 'crave', 'grave', 'shave', 'slave', 'stave',
            'bread', 'dread', 'spread', 'thread', 'tread',
            'break', 'bleak', 'creak', 'freak', 'sneak', 'speak', 'steak', 'tweak', 'wreak',
            'brief', 'chief', 'grief', 'thief',
            'bring', 'cling', 'fling', 'sling', 'sting', 'swing', 'thing', 'wring',
            'brisk', 'frisk', 'whisk',
            'broad', 'troad',
            'broke', 'choke', 'smoke', 'spoke', 'stoke', 'woke',
            'brook', 'crook', 'shook',
            'broom', 'bloom', 'gloom',
            'brown', 'crown', 'drown', 'frown', 'grown',
            'brush', 'blush', 'crush', 'flush', 'plush', 'slush',
            'build', 'guild',
            'burns', 'turns', 'curns',
            'burst', 'first', 'worst', 'thirst',
            'cabin', 'robin',
            'cable', 'fable', 'sable', 'table',
            'camel', 'panel',
            'canal', 'final', 'penal', 'renal', 'tonal', 'zonal',
            'candy', 'dandy', 'handy', 'sandy',
            'carry', 'marry', 'tarry', 'harry', 'parry', 'worry',
            'catch', 'batch', 'hatch', 'latch', 'match', 'patch', 'watch',
            'chain', 'brain', 'drain', 'grain', 'plain', 'slain', 'Spain', 'stain', 'strain', 'train',
            'chair', 'flair', 'stair',
            'chalk', 'stalk', 'walk',
            'champ', 'clamp', 'cramp', 'stamp', 'tramp',
            'charm', 'alarm', 'farm',
            'chase', 'erase', 'phase',
            'cheap', 'cheat',
            'check', 'cheek', 'creek', 'sleek', 'wreck',
            'cheer', 'sheer', 'steer',
            'chess', 'bless', 'dress', 'guess', 'press',
            'chest', 'crest', 'quest',
            'child', 'build', 'guild', 'mild', 'wild',
            'chill', 'drill', 'frill', 'grill', 'skill', 'spill', 'still', 'thrill', 'trill',
            'china', 'spine',
            'choke', 'broke', 'smoke', 'spoke', 'stoke', 'woke',
            'chord', 'sword', 'word',
            'chunk', 'drunk', 'flunk', 'plunk', 'skunk', 'spunk', 'stunk', 'trunk',
            'claim', 'clam',
            'clash', 'class', 'glass', 'grass',
            'clasp', 'grasp',
            'class', 'clash', 'glass', 'grass',
            'clean', 'clear', 'ocean',
            'clear', 'clean', 'shear', 'smear', 'spear', 'swear',
            'clerk', 'perk',
            'click', 'brick', 'flick', 'prick', 'quick', 'slick', 'stick', 'thick', 'trick',
            'cliff', 'skiff', 'sniff', 'stiff', 'whiff',
            'climb', 'limb',
            'cling', 'bring', 'fling', 'sling', 'sting', 'swing', 'thing', 'wring',
            'cloak', 'croak',
            'clock', 'block', 'flock', 'shock', 'stock',
            'close', 'chose',
            'cloth', 'sloth',
            'cloud', 'aloud', 'proud', 'shroud',
            'clown', 'brown', 'crown', 'drown', 'frown', 'grown',
            'coast', 'boast', 'roast', 'toast',
            'couch', 'pouch', 'touch', 'vouch',
            'count', 'fount', 'mount',
            'court', 'short', 'sport',
            'cover', 'hover', 'lover', 'rover',
            'crack', 'black', 'track', 'whack',
            'craft', 'draft', 'graft', 'shaft',
            'crane', 'frame', 'plane',
            'crash', 'brash', 'flash', 'slash', 'smash', 'stash', 'trash',
            'crawl', 'brawl', 'drawl', 'shawl', 'trawl',
            'crazy', 'hazy', 'lazy',
            'cream', 'dream', 'gleam', 'steam', 'stream', 'scream',
            'creek', 'cheek', 'sleek', 'wreck',
            'creep', 'sleep', 'steep', 'sweep',
            'crest', 'chest', 'quest',
            'crime', 'grime', 'prime', 'slime',
            'crisp', 'clasp', 'grasp',
            'cross', 'floss', 'gloss', 'gross',
            'crowd', 'cloud', 'proud',
            'crown', 'brown', 'drown', 'frown', 'grown',
            'cruel', 'gruel',
            'crush', 'brush', 'blush', 'flush', 'plush', 'slush',
            'crust', 'trust', 'thrust',
            'curve', 'nerve', 'serve',
        ],
    }

    def __init__(self):
        self.word_graph = {}
        self._build_graphs()

    def _build_graphs(self):
        """Build adjacency graphs for each word length."""
        for length, words in self.WORD_LISTS.items():
            graph = {}
            # Filter to only words of correct length (lowercase)
            valid_words = [w.lower() for w in words if len(w) == length]
            word_set = set(valid_words)

            for word in valid_words:
                neighbors = []
                for i in range(length):
                    for c in 'abcdefghijklmnopqrstuvwxyz':
                        if c != word[i]:
                            candidate = word[:i] + c + word[i+1:]
                            if candidate in word_set:
                                neighbors.append(candidate)
                graph[word] = neighbors

            self.word_graph[length] = graph

    def generate(self, difficulty='easy'):
        """
        Generate a new Word Ladder puzzle.

        Args:
            difficulty: 'easy', 'medium', or 'hard'

        Returns:
            dict with puzzle and solution data
        """
        settings = self.DIFFICULTY_SETTINGS.get(difficulty, self.DIFFICULTY_SETTINGS['easy'])
        word_length = settings['word_length']
        min_path = settings['min_path']
        max_path = settings['max_path']

        graph = self.word_graph.get(word_length, {})
        words = list(graph.keys())

        if not words:
            raise ValueError(f"No words available for length {word_length}")

        # Try to find a good puzzle
        attempts = 0
        while attempts < 100:
            attempts += 1

            start = random.choice(words)
            path = self._find_path_bfs(start, min_path, max_path, graph)

            if path and len(path) >= min_path:
                end = path[-1]
                return {
                    'puzzle_data': {
                        'start_word': start,
                        'end_word': end,
                        'word_length': word_length,
                        'expected_steps': len(path) - 1,
                    },
                    'solution_data': {
                        'path': path,
                    },
                    'difficulty': difficulty,
                }

        # Fallback: use any valid path found
        for start in words:
            path = self._find_path_bfs(start, 2, max_path, graph)
            if path:
                end = path[-1]
                return {
                    'puzzle_data': {
                        'start_word': start,
                        'end_word': end,
                        'word_length': word_length,
                        'expected_steps': len(path) - 1,
                    },
                    'solution_data': {
                        'path': path,
                    },
                    'difficulty': difficulty,
                }

        raise ValueError("Could not generate a valid word ladder")

    def _find_path_bfs(self, start, min_length, max_length, graph):
        """
        Find a path of appropriate length using BFS.
        """
        queue = deque([(start, [start])])
        visited = {start}
        valid_paths = []

        while queue:
            word, path = queue.popleft()

            if len(path) > max_length:
                continue

            if min_length <= len(path) <= max_length:
                valid_paths.append(path)
                if len(valid_paths) > 20:  # Limit paths collected
                    break

            for neighbor in graph.get(word, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))

        return random.choice(valid_paths) if valid_paths else None

    def find_shortest_path(self, start, end, word_length):
        """
        Find shortest path between two words.

        Used for verifying user solutions.
        """
        graph = self.word_graph.get(word_length, {})

        if start not in graph or end not in graph:
            return None

        queue = deque([(start, [start])])
        visited = {start}

        while queue:
            word, path = queue.popleft()

            if word == end:
                return path

            for neighbor in graph.get(word, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))

        return None

    @staticmethod
    def verify_solution(puzzle_data, submitted_solution):
        """
        Verify a submitted Word Ladder solution.

        Args:
            puzzle_data: Puzzle data with start/end words
            submitted_solution: dict with 'path' key (list of words)

        Returns:
            bool: True if valid path from start to end
        """
        start = puzzle_data.get('start_word', '')
        end = puzzle_data.get('end_word', '')
        word_length = puzzle_data.get('word_length', 4)
        path = submitted_solution.get('path', [])

        if not path:
            return False

        # Check start and end
        if path[0].lower() != start.lower():
            return False
        if path[-1].lower() != end.lower():
            return False

        # Check each step
        for i in range(len(path) - 1):
            word1 = path[i].lower()
            word2 = path[i + 1].lower()

            # Must be same length
            if len(word1) != word_length or len(word2) != word_length:
                return False

            # Must differ by exactly one letter
            diff = sum(1 for a, b in zip(word1, word2) if a != b)
            if diff != 1:
                return False

            # Word must be valid (in our dictionary)
            words = WordLadderGenerator.WORD_LISTS.get(word_length, [])
            if word2 not in words:
                return False

        return True


def generate_word_ladder(difficulty='easy'):
    """
    Convenience function to generate a Word Ladder puzzle.
    """
    generator = WordLadderGenerator()
    return generator.generate(difficulty)


def verify_word_ladder_solution(puzzle_data, submitted_solution):
    """
    Verify a submitted Word Ladder solution.
    """
    return WordLadderGenerator.verify_solution(puzzle_data, submitted_solution)
