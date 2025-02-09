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

# Available information
- allWords
- remainingWords
- remainingLetters (letters not attempted)
- for each attempted letter
  - exactly N occurrences (including 0)
  - possibly N or more occurrences
  - invalid ordering
- connected letters
- starting letter / sequence
- ending letter / sequence

# Constraints
1. Letters not in the word
2. Letters in the word
3. Letter in the wrong order
3. Ordering, connected words, beginning and end

# Algorithm

If there is only 1 remainingWords, pick that one
If there is only 2 remainingWords, pick one at random
Otherwise pick a guess from allWords that has highest score (i.e. highest chance of removing the most words in remainingWords)

To score a guess:
- For each unique letter in the guess
  - Add to the score the number of words in remainingWords the letter shows up in (will be 0 for invalid absent letters)
    - Reasoning: if we try a letter and find it is invalid, it removes the most remainingWords
- See how many constraints this word can update
  - Add to the score the number of invalid ordered letter that are moved to a different ordering
    - Can also try scoring by number of remainingWords that will be removed if the new ordering is correct
  - Add 1 to the score if the start of the word has not been found yet and the guess has the first valid letter as the first letter
    - Can also try scoring by number of remainingWords that will be removed if the starting sequence was valid
  - Add 1 to the score if the end of the word has not been found yet and the guess has the last valid letter as the last letter
    - Can also try scoring by number of remainingWords that will be removed
  - Add to the score the number of new groupings of valid ordering (e.g. if we know A*G*L, and the word has "AGL", that is two new groupings)
- Subtract the score by number of invalid letters used (letters used beyond the number of occurrences allowed)

# Modeling

allWords: [string]
remainingWords: [string]
remainingLetters: {char: integer}
  - Maps a letter to number of words in remainingWords that has the letter
letterOccurrences: {char: [int, bool]}
  - Maps a letter to [number of occurrences, finalized]. If finalized is false, there is a chance there could be more occurrences
ordering: [string]
  - Each element in the array is a string that starts with a letter:
    - Lower case letter: valid letter and in correct ordering, but could have more occurrences in the word that haven't been found yet
    - Upper case letter: valid letter and all occurrences of the letter have been found
  - The string is then followed by one or more special characters:
    - "^" -- start of the word
    - "$" -- end of the word
    - "~" -- a continuation
    - "?" -- position is incorrect
    - "!" -- tombstone for incorrect position, but the correct positions for all occurrences of the letter has been found and are presents in other parts of the `ordering` array
"""

from abc import ABC, abstractmethod
from bs4 import BeautifulSoup
import csv
import re
import string

class Word:
    def __init__(self, word: str):
        self.word = word
        self.letter_count = {}
        self.guess_rules = []

        for letter in word:
            new_count = self.letter_count.get(letter, 0) + 1
            self.letter_count[letter] = new_count
            self.guess_rules.append(LetterOccurrenceRule(letter, new_count, exact=False))

        self.guess_rules.append(LetterStartRule(word[0]))
        self.guess_rules.append(LetterEndRule(word[-1]))

    def __repr__(self):
        return self.word

class Rule(ABC):
    @abstractmethod
    def matches(self, word: Word) -> bool:
        pass

class LetterOccurrenceRule(Rule):
    letter: string
    num_occurrences: int
    exact: bool # false if word can have more occurrences of the letter

    def __init__(self, letter: str, num_occurrences: int, exact: bool):
        self.letter = letter
        self.num_occurrences = num_occurrences
        self.exact = exact

    def matches(self, word: Word) -> bool:
        actual_occurrences = word.letter_count.get(self.letter, 0)
        return self.num_occurrences == actual_occurrences if self.exact else self.num_occurrences <= actual_occurrences

class LetterStartRule(Rule):
    letter: string

    def __init__(self, letter: str):
        self.letter = letter

    def matches(self, word: Word) -> bool:
        return word.word.startswith(self.letter)

class LetterEndRule(Rule):
    letter: string

    def __init__(self, letter: str):
        self.letter = letter

    def matches(self, word: Word) -> bool:
        return word.word.endswith(self.letter)

def load_words(filename):
    with open(filename, mode='r') as file:
        csv_reader = csv.reader(file)
        data_array = []
        for row in csv_reader:
            data_array.append(row)
    return data_array[0]

def clean_words(words: list) -> list:
    # Diffle only allows 10 letter words
    return [word for word in words if len(word) <= 10]

def init_words(words: list) -> list:
    return [Word(word) for word in words]

# Splits every list of words inside word_lists into two lists, one with words where Rule is true and one where it is false.
def split_by_rule(word_lists: list, rule: Rule) -> list:
    result = []
    for word_list in word_lists:
        false_group = [word for word in word_list if not rule.matches(word)]
        true_group = [word for word in word_list if rule.matches(word)]
        if len(false_group) > 0:
            result.append(false_group)
        if len(true_group) > 0:
            result.append(true_group)
    return result

# Computes the maximum possible remaining_words after guessing the word
def get_max_remaining_after_guessing(guess_word: Word, remaining_words: list):
    word_lists = [remaining_words]
    for rule in guess_word.guess_rules:
        word_lists = split_by_rule(word_lists, rule)
    return max(len(group) for group in word_lists)

def score_guess(guess_word: Word, remaining_words: list) -> tuple[int, int]:
    return (get_max_remaining_after_guessing(guess_word, remaining_words), len(guess_word.word))

def get_next_guess(all_words: list, remaining_words: list) -> Word:
    scored_words = [(word, score_guess(word, remaining_words)) for word in all_words]
    min_score_word = min(scored_words, key=lambda x: x[1])
    print(f"[debug] get_next_guess: {min_score_word}")
    return min_score_word[0]

if __name__ == "__main__":
    all_words = init_words(clean_words(load_words('allowed.csv')))
    # No need to clean answers since they are guaranteed to be valid
    remaining_words = init_words(load_words('answers.csv'))
    while True:
      guess_word = get_next_guess(all_words, remaining_words)
      print(f"Recommended guess: {guess_word}")
      guess_html = input("Enter guess result html: ")
      # guess_results = parse_guess_results(guess_html)
      # unattempted_letters = update_unattempted_letters(unattempted_letters, guess[0])
      # regex_filters = build_regex_filters(guess_results)
      # TODO: filter remaining_words by regex_filters. each word has to satisfy all regexes










# def get_letter_scores(letters: set, words: list) -> dict:
#     letter_counts = {letter: 0 for letter in letters}
#     for word in words:
#         unique_letters_in_word = set(word)
#         for letter in letters:
#             if letter in unique_letters_in_word:
#                 letter_counts[letter] += 1
#     return letter_counts

# def score_word(word: str, letter_scores: dict) -> int:
#     return sum(letter_scores.get(letter, 0) for letter in set(word))

# def rank_words(words: list, letter_scores: dict) -> list:
#     return sorted(((word, score_word(word, letter_scores)) for word in words), key=lambda x: x[1], reverse=True)

# def get_next_guess(all_words: list, remaining_words: list, unattempted_letters: set) -> str:
#     unattempted_letters_scores = get_letter_scores(unattempted_letters, remaining_words)
#     scored_words = rank_words(all_words, unattempted_letters_scores)
#     return scored_words[0]

# # Returns a list of Rules
# def parse_guess_results(html: str) -> list:
#     soup = BeautifulSoup(html, 'html.parser')
#     parsed_letters = []
#     for letter_div in soup.find_all(class_="letter"):
#         letter = letter_div.get_text()
#         classes = [cls for cls in letter_div.get("class", []) if cls != "letter"]
#         parsed_letters.append((letter, set(classes)))
#     return parsed_letters

# def build_regex_filters(guess_results: list) -> list:
#   regex_filters = []
#   possible_sequence = ""
#   for i, (letter, classes) in enumerate(guess_results):
#     if "absent" in classes:
#         if len(possible_sequence > 0):
#             regex_filters.append(f"{re.escape(possible_sequence)}")
#         regex_filters.append(re.compile(f"^[^{re.escape(letter)}]*$"))
#         possible_sequence = ""
#     elif "start" in classes:
#         regex_filters.append(re.compile(f"^{re.escape(letter)}"))
#     elif "end" in classes:
#         regex_filters.append(re.compile(f"{re.escape(letter)}$"))
#     elif "head" in classes:
#         if len(possible_sequence > 0):
#             regex_filters.append(f"{re.escape(possible_sequence)}")
#         possible_sequence = letter
#     elif "tail" in classes:
#         possible_sequence = f"{possible_sequence}{letter}"

# def update_unattempted_letters(letters: set, guess: str) -> set:
#     guess_letters = set(guess)
#     return {letter for letter in letters if letter not in guess_letters}