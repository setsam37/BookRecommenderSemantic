"""Regression tests run without an API key or a vector database."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def app():
    spec = importlib.util.spec_from_file_location('dashboard', ROOT / 'gradio-dashboard.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.__dict__


def catalog(size=20):
    return pd.DataFrame({
        'isbn13': range(100, 100 + size), 'title': ['Book'] * size,
        'authors': ['Author'] * size, 'description': ['A book description.'] * size,
        'simple_categories': ['Fiction'] * size,
        'large_thumbnail': ['cover-not-found.jpg'] * size,
        'joy': [i / size for i in range(size)],
        'surprise': [i / size for i in range(size)],
        'anger': [i / size for i in range(size)],
        'fear': [i / size for i in range(size)],
        'sadness': [i / size for i in range(size)],
    })


class SearchResults:
    """An external search boundary with a fixed semantic order."""
    def __init__(self, ids, categories):
        self.ids = ids
        self.categories = categories

    def similarity_search(self, query, k, filter=None):
        ids = self.ids
        if filter:
            ids = [isbn for isbn in ids if self.categories[isbn] == filter['simple_categories']]
        return [SimpleNamespace(metadata={'isbn13': isbn}) for isbn in ids[:k]]


def configure(app, books, ids=None):
    app['books'] = books
    app['db_books'] = SearchResults(ids if ids is not None else books.isbn13.tolist(),
                                  dict(zip(books.isbn13, books.simple_categories)))


def test_happy_tone_changes_order(app):
    configure(app, catalog(3))
    result = app['retrieve_semantic_recommendations']('story', 'ALL', 'Happy')
    assert result.isbn13.tolist() == [102, 101, 100]


@pytest.mark.parametrize('tone', ['Happy', 'Surprising', 'Angry', 'Suspenseful', 'Sad'])
def test_tone_ranks_full_candidate_pool_before_limit(app, tone):
    configure(app, catalog(20))
    result = app['retrieve_semantic_recommendations']('story', 'ALL', tone)
    assert result.isbn13.tolist() == list(range(119, 103, -1))


def test_no_tone_preserves_semantic_order(app):
    configure(app, catalog(3), [102, 100, 101])
    assert app['retrieve_semantic_recommendations']('story', 'ALL', 'ALL').isbn13.tolist() == [102, 100, 101]


def test_category_can_retrieve_books_beyond_first_fifty(app):
    books = catalog(70)
    books.loc[:54, 'simple_categories'] = 'Nonfiction'
    configure(app, books)
    result = app['retrieve_semantic_recommendations']('story', 'Fiction', 'ALL')
    assert result.isbn13.tolist() == list(range(155, 170))


def test_omitted_category_means_all(app):
    configure(app, catalog(3))
    assert len(app['retrieve_semantic_recommendations']('story')) == 3


def test_missing_author_has_readable_fallback(app):
    books = catalog(1)
    books.loc[0, 'authors'] = float('nan')
    configure(app, books)
    result = app['recommend_books']('story', 'ALL', 'ALL')
    assert 'Unknown author' in result[0][1]


def test_blank_query_does_not_call_search(app):
    class NoSearch:
        def similarity_search(self, *args, **kwargs):
            pytest.fail('Blank input must not incur an embedding request')
    app['books'] = catalog(1)
    app['db_books'] = NoSearch()
    assert app['recommend_books']('   ', 'ALL', 'ALL') == []


def test_duplicate_search_ids_keep_first_semantic_rank(app):
    configure(app, catalog(4), [100, 101, 100, 102])
    assert app['retrieve_semantic_recommendations']('story', 'ALL', 'ALL').isbn13.tolist() == [100, 101, 102]


def test_equal_tone_scores_preserve_semantic_order(app):
    books = catalog(3)
    books['joy'] = 0.5
    configure(app, books, [102, 100, 101])
    assert app['retrieve_semantic_recommendations']('story', 'ALL', 'Happy').isbn13.tolist() == [102, 100, 101]


def test_unknown_category_returns_empty_without_search(app):
    configure(app, catalog(3))
    class NoSearch:
        def similarity_search(self, *args, **kwargs):
            pytest.fail('No books in this category; search is unnecessary')
    app['db_books'] = NoSearch()
    assert app['recommend_books']('story', 'Unknown category', 'ALL') == []
