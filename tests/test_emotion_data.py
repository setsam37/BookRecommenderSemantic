from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_saved_scores_match_known_classifier_output():
    # Independently recorded classifier output from the original notebook.
    books = pd.read_csv(ROOT / 'books_with_emotions.csv')
    book = books.loc[books.isbn13 == 9780002005883].iloc[0]
    assert book.sadness == pytest.approx(0.9671575427055359, abs=2e-5)
    assert book.surprise == pytest.approx(0.7296020984649658, abs=2e-5)


def test_every_book_has_complete_bounded_emotion_scores():
    books = pd.read_csv(ROOT / 'books_with_emotions.csv')
    scores = books[['anger', 'disgust', 'fear', 'joy', 'sadness', 'surprise']]
    assert len(scores) == 5197
    assert scores.notna().all().all()
    assert (scores.ge(0) & scores.le(1)).all().all()
