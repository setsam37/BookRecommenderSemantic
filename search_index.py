"""A persistent Chroma index, partitioned by catalog content and embedding model."""
import hashlib
import json
import os
from pathlib import Path


def load_or_create_index(books, index_root, model='text-embedding-3-small', *, embeddings=None):
    from langchain_chroma import Chroma
    from langchain_core.documents import Document

    if embeddings is None:
        if not os.getenv('OPENAI_API_KEY', '').strip():
            raise RuntimeError('Set a new OPENAI_API_KEY in .env or your environment before searching.')
        from langchain_openai import OpenAIEmbeddings
        embeddings = OpenAIEmbeddings(model=model, max_retries=2)

    records = [{'isbn13': str(int(row.isbn13)), 'description': row.description,
                'simple_categories': str(row.simple_categories)} for row in books.itertuples()]
    fingerprint = hashlib.sha256(json.dumps(
        {'schema': 1, 'model': model, 'books': records}, sort_keys=True, ensure_ascii=False,
    ).encode('utf-8')).hexdigest()
    directory = Path(index_root) / fingerprint
    directory.mkdir(parents=True, exist_ok=True)
    store = Chroma(collection_name='books', persist_directory=str(directory),
                   embedding_function=embeddings)
    existing = set(store.get(include=[])['ids'])
    pending = [record for record in records if record['isbn13'] not in existing]
    # Stable IDs let an interrupted build resume without embedding completed books.
    for start in range(0, len(pending), 128):
        batch = pending[start:start + 128]
        store.add_documents(
            [Document(page_content=record['description'], metadata={
                'isbn13': int(record['isbn13']), 'simple_categories': record['simple_categories'],
            }) for record in batch],
            ids=[record['isbn13'] for record in batch],
        )
    return store
