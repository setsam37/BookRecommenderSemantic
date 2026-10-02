import importlib.util
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def app():
    spec = importlib.util.spec_from_file_location('dashboard', ROOT / 'gradio-dashboard.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bundled_catalog_handles_missing_authors_and_covers(app):
    books = app.load_books()
    assert len(books) == 5197
    assert not books.authors.isna().any()
    assert books.loc[books.isbn13 == 9780141026282, 'authors'].item() == 'Unknown author'
    fallback = str(ROOT / 'cover-not-found.jpg')
    assert (books.loc[books.thumbnail.isna(), 'large_thumbnail'] == fallback).all()
    assert Path(fallback).is_file()


def test_catalog_paths_do_not_depend_on_working_directory(app, monkeypatch):
    monkeypatch.chdir(ROOT.parent)
    assert len(app.load_books()) == 5197


def test_rejects_catalog_without_required_fields(app, tmp_path):
    path = tmp_path / 'bad.csv'
    pd.DataFrame({'title': ['Book']}).to_csv(path, index=False)
    with pytest.raises(ValueError, match='missing columns'):
        app.load_books(path)
