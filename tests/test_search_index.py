import pandas as pd
import pytest
from langchain_core.embeddings import Embeddings

from search_index import load_or_create_index


class LocalEmbeddings(Embeddings):
    """Deterministic vectors; replacing only the paid embedding boundary."""
    def embed_documents(self, texts):
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text):
        return [float('nature' in text.lower()), float('history' in text.lower()), 1.0]


class QueryOnlyEmbeddings(LocalEmbeddings):
    def embed_documents(self, texts):
        pytest.fail('A completed index must not embed the catalog again')


def catalog():
    return pd.DataFrame({'isbn13': [100, 101], 'description': ['nature guide', 'history book'],
                         'simple_categories': ["Children's Nonfiction", 'Nonfiction']})


def test_persisted_index_reopens_without_embedding_books(tmp_path):
    store = load_or_create_index(catalog(), tmp_path, 'local-test', embeddings=LocalEmbeddings())
    assert store.similarity_search('nature', k=1)[0].metadata['isbn13'] == 100
    reopened = load_or_create_index(catalog(), tmp_path, 'local-test', embeddings=QueryOnlyEmbeddings())
    assert reopened.get(include=[])['ids'] == ['100', '101']
    assert reopened.similarity_search('history', k=1)[0].metadata['isbn13'] == 101


def test_category_filter_searches_only_eligible_books(tmp_path):
    store = load_or_create_index(catalog(), tmp_path, 'local-test', embeddings=LocalEmbeddings())
    matches = store.similarity_search('history', k=1, filter={'simple_categories': "Children's Nonfiction"})
    assert [match.metadata['isbn13'] for match in matches] == [100]


def test_catalog_changes_do_not_reuse_stale_vectors(tmp_path):
    store = load_or_create_index(catalog(), tmp_path, 'local-test', embeddings=LocalEmbeddings())
    changed = catalog()
    changed.loc[0, 'description'] = 'history guide'
    updated = load_or_create_index(changed, tmp_path, 'local-test', embeddings=LocalEmbeddings())
    assert store.get(ids=['100'])['documents'] == ['nature guide']
    assert updated.get(ids=['100'])['documents'] == ['history guide']


def test_embedding_model_change_builds_a_separate_index(tmp_path):
    load_or_create_index(catalog(), tmp_path, 'model-a', embeddings=LocalEmbeddings())
    load_or_create_index(catalog(), tmp_path, 'model-b', embeddings=LocalEmbeddings())
    assert len(list(tmp_path.iterdir())) == 2


def test_interrupted_index_build_resumes_missing_books(tmp_path):
    store = load_or_create_index(catalog(), tmp_path, 'local-test', embeddings=LocalEmbeddings())
    store.delete(ids=['101'])
    class ResumeEmbeddings(LocalEmbeddings):
        def embed_documents(self, texts):
            if 'nature guide' in texts:
                pytest.fail('Completed books must not be embedded again')
            return super().embed_documents(texts)
    resumed = load_or_create_index(catalog(), tmp_path, 'local-test', embeddings=ResumeEmbeddings())
    assert set(resumed.get(include=[])['ids']) == {'100', '101'}
