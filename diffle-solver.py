"""
# Game Instructions

- Given a list of all valid words and a hidden randomly selected word
- Guess the hidden word using as few letters as possible
- Each guess must be a valid word
- After each guess, you will be given information about each letter of the guess. A letter can be one or more of the following:
  - The letter is absent from the hidden word. For example, if a letter occurs twice in the hidden word, if the guess has 3 occurrences of the letter, the third occurrence will be marked as absent.
  - The letter is present in the hidden word and is the start of a sequence in the hidden word. If two sequential letters are both start of sequences in hidden word, it means the ordering is correct but the two letters are not connected to each other.
  - The letter is present and is a continuation of the previous letter
  - The letter is beginning of the hidden word.
  - The letter is the end of the word.

# Algorithm

The algorithm works by simulating what feedback each potential guess would produce and measuring how much that guess would narrow down the candidate pool.
1. Evaluate every possible valid guess by predicting how the feedback would partition the remaining candidate words.
2. The guess that, in the worst-case scenario, leaves the fewest candidates is selected as the next guess.
3. Given the feedback from the game of the guess, remove invalid candidate words.
"""

#!/usr/bin/env python3
import csv
import collections
import re
from abc import ABC, abstractmethod
from concurrent.futures import ProcessPoolExecutor
from bs4 import BeautifulSoup

# -------------------------
# Data Model and Rule Classes
# -------------------------
class Word:
    def __init__(self, word: str):
        self.word = word
        # Use collections.Counter for efficient letter counting
        self.letter_count = collections.Counter(word)
        self.guess_rules = []
        # Create rules based on letter occurrences, tracking the count as we progress in the word
        occurrences = {}
        for letter in word:
            occurrences[letter] = occurrences.get(letter, 0) + 1
            self.guess_rules.append(LetterOccurrenceRule(letter, occurrences[letter], exact=False))
        self.guess_rules.append(LetterStartRule(word[0]))
        self.guess_rules.append(LetterEndRule(word[-1]))

    def __repr__(self):
        return self.word

class Rule(ABC):
    @abstractmethod
    def matches(self, word: Word) -> bool:
        pass

class LetterOccurrenceRule(Rule):
    def __init__(self, letter: str, num_occurrences: int, exact: bool):
        self.letter = letter
        self.num_occurrences = num_occurrences
        self.exact = exact

    def matches(self, word: Word) -> bool:
        actual_occurrences = word.letter_count.get(self.letter, 0)
        return (actual_occurrences == self.num_occurrences) if self.exact else (actual_occurrences >= self.num_occurrences)

    def __repr__(self):
        return f"LetterOccurrenceRule({self.letter}, {self.num_occurrences}, exact={self.exact})"

class LetterStartRule(Rule):
    def __init__(self, letter: str):
        self.letter = letter

    def matches(self, word: Word) -> bool:
        return word.word.startswith(self.letter)

    def __repr__(self):
        return f"LetterStartRule({self.letter})"

class LetterEndRule(Rule):
    def __init__(self, letter: str):
        self.letter = letter

    def matches(self, word: Word) -> bool:
        return word.word.endswith(self.letter)

    def __repr__(self):
        return f"LetterEndRule({self.letter})"

class RegexRule(Rule):
    def __init__(self, regex: re.Pattern):
        self.regex = regex

    def matches(self, word: Word) -> bool:
        return bool(self.regex.fullmatch(word.word))

    def __repr__(self):
        return f"RegexRule({self.regex})"

# -------------------------
# File and Word List Processing
# -------------------------
def load_words(filename: str) -> list:
    """Read a CSV file and return the first row as a list of strings."""
    with open(filename, mode='r') as file:
        csv_reader = csv.reader(file)
        data_array = list(csv_reader)
    return data_array[0]

def clean_words(words: list) -> list:
    """Filter the provided list of words to only valid Diffle input words."""
    # Diffle only allows words of up to 10 letters.
    return [word for word in words if len(word) <= 10]

def init_words(words: list) -> list:
    """Convert a list of strings into a list of Word objects."""
    return [Word(word) for word in words]

# -------------------------
# Game Scoring and Rule Application
# -------------------------
def split_by_rule(word_lists: list, rule: Rule) -> list:
    """
    Split each word list into two lists, one where all words matches the given
    rule, and one where they don't.

    Return an updated list of word lists with empty word lists removed.
    """
    result = []
    for word_list in word_lists:
        true_group = []
        false_group = []
        for word in word_list:
            match = rule.matches(word)
            if match:
                true_group.append(word)
            else:
                false_group.append(word)
        if false_group:
            result.append(false_group)
        if true_group:
            result.append(true_group)
    return result

def get_max_remaining_after_guessing(guess_word: Word, remaining_words: list) -> int:
    """
    For a given guess word, return the maximum number of possible remaining
    words after making the guess.
    """
    word_lists = [remaining_words]
    for rule in guess_word.guess_rules:
        word_lists = split_by_rule(word_lists, rule)
    return max(len(group) for group in word_lists)

def compute_score(guess_word: Word, remaining_words: list) -> tuple:
    """
    Return the score of the guess word, where lower lexicographical scores are
    better.

    The score prioritizes words that reduce the max possible remaining words
    after making the guess, and then by the guess word length.
    """
    return (get_max_remaining_after_guessing(guess_word, remaining_words), len(guess_word.word))

def compute_scores_batch(args: tuple[list, list]) -> list:
    """
    Worker function for scoring a batch of guess words.

    Parameters:
    args -- a tuple with a list of guess words and list of remaining words.

    Return a list of tuples (Word, compute_score(Word)).
    """
    words_batch, remaining_words = args
    results = []
    for word in words_batch:
        score = compute_score(word, remaining_words)
        # print(f"[debug] finished compute_score: {word}, {score}")
        results.append((word, score))
    return results

def get_next_guess(all_words: list, remaining_words: list) -> tuple[Word, tuple[int, int]]:
    """
    Select the next guess word from either all_words or remaining_words.

    Parameters:
    all_words -- list of all allowed Word objects.
    remaining_words -- list of remaining candidate Word objects.

    Return the next guess as a tuple of (Word, compute_score(Word)).

    Raise ValueError if there are no remaining words.
    """
    # Base cases when there is <= 2 remaining words
    if len(remaining_words) == 0:
        raise ValueError("No more remaining words!")
    if len(remaining_words) == 1:
        return (remaining_words[0], (0, len(remaining_words[0].word)))
    if len(remaining_words) == 2:
        if len(remaining_words[0].word) < len(remaining_words[1].word):
            return (remaining_words[0], (1, len(remaining_words[0].word)))
        else:
            return (remaining_words[1], (1, len(remaining_words[1].word)))

    # Batch words into a single task to minimize overhead of creating too many executor tasks.
    BATCH_SIZE = 1000
    batches = [all_words[i:i+BATCH_SIZE] for i in range(0, len(all_words), BATCH_SIZE)]
    results = []
    with ProcessPoolExecutor() as executor:
        for batch_result in executor.map(compute_scores_batch, ((batch, remaining_words) for batch in batches)):
            results.extend(batch_result)
    return min(results, key=lambda x: x[1])

def parse_guess_results(html: str) -> list:
    """
    Parse the HTML of the guess result (div with "guess" class) from the
    Diffle UI.

    Return a list of Rules to filter the remaining words by.
    """
    soup = BeautifulSoup(html, 'html.parser')
    rules = []
    occurrence_count = collections.Counter()
    regex_parts = []
    found_end = False

    for letter_div in soup.find_all(class_="letter"):
        letter = letter_div.get_text()
        classes = set(letter_div.get("class", []))

        if "absent" in classes:
            # Check equal to 0 as well so we explicitly set a 0 count for the letter, which will allow us to create a
            # rule for it later.
            if occurrence_count[letter] >= 0:
              # Use negative occurrence to mark that the occurrence count is an exact count (cannot be more).
              occurrence_count[letter] = -occurrence_count[letter]
        else:
            occurrence_count[letter] += 1

        if "start" in classes:
            rules.append(LetterStartRule(letter))
        if "end" in classes:
            rules.append(LetterEndRule(letter))
            found_end = True

        if "head" in classes:
            # TODO: handle case where the "head" immediately follows a "head" or "tail", in which case we know that
            # there is some other letter that comes in between, so can use '.+' instead of '.*'
            regex_parts.append(f'.*{letter}')
        if "tail" in classes:
            regex_parts.append(letter)
        if "present" in classes:
            # TODO: handle "present" case where the letter exists but is in the wrong order
            # TODO: handle case where "present" is next to "head" or "tail" since you know this letter cannot be next to those letters in the final answer
            pass

    for letter, count in occurrence_count.items():
        rules.append(LetterOccurrenceRule(letter, abs(count), exact=(count <= 0)))

    if not found_end:
        regex_parts.append(r'.+')
    if len(regex_parts) > 0:
        regex_pattern = ''.join(regex_parts)
        print(f'[debug] RegexRule regex: {regex_pattern}')
        rules.append(RegexRule(re.compile(regex_pattern)))

    return rules


def filter_words(words: list, rules: list) -> list:
    """Return a list of words that satisfy all the given rules."""
    return [word for word in words if all(rule.matches(word) for rule in rules)]

# -------------------------
# Main Interactive Loop
# -------------------------
if __name__ == "__main__":
    allowed_words = clean_words(load_words('allowed.csv'))
    answer_words = load_words('answers.csv')  # Answers are guaranteed valid so no cleaning needed

    all_words = init_words(allowed_words)
    remaining_words = init_words(answer_words)

    # The first guess word is always the same, and is precomputed by calling
    # `get_next_guess` with the full set of `all_words` and `remaining_words`.
    guess_word = Word("centralise")

    while True:
        print(f"Recommended guess: {guess_word}")
        try:
          remaining_words.remove(guess_word)
        except:
            pass
        try:
          all_words.remove(guess_word)
        except:
            pass

        guess_html = input("What was the result? Enter the HTML of the div with class 'guess': ")
        rules = parse_guess_results(guess_html)

        remaining_words_before_count = len(remaining_words)
        remaining_words = filter_words(remaining_words, rules)
        print(f"Remaining words filtered from {remaining_words_before_count} to {len(remaining_words)}")
        if len(remaining_words) < 20:
            print(remaining_words)

        # Prioritize picking a word from `remaining_words`` if it can achieve
        # the same or better results than a word from `all_words` since it
        # gives us a better chance of guessing the exact word.
        remaining_word_guess, remaining_word_score = get_next_guess(remaining_words, remaining_words)
        all_words_guess, all_words_score = get_next_guess(all_words, remaining_words)
        guess_word = all_words_guess if all_words_score < remaining_word_score else remaining_word_guess

        print(f"[debug] remaining_word_guess: {remaining_word_guess}, score: {remaining_word_score}")
        print(f"[debug] all_words_guess: {all_words_guess}, score: {all_words_score}")
        print(f"[debug] guess_word: {guess_word}")
