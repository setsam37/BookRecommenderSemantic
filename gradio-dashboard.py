"""Gradio interface and recommendation ranking. Importing makes no API calls."""
from pathlib import Path
from threading import Lock

import pandas as pd


ROOT = Path(__file__).resolve().parent
TONES = {'Happy': 'joy', 'Surprising': 'surprise', 'Angry': 'anger',
         'Suspenseful': 'fear', 'Sad': 'sadness'}
books = None
db_books = None
index_lock = Lock()


def load_books(path=None):
    """Read the bundled catalog independently of the working directory."""
    frame = pd.read_csv(path or ROOT / 'books_with_emotions.csv')
    required = {'isbn13', 'title', 'authors', 'description', 'thumbnail',
                'simple_categories', *TONES.values()}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f'Catalog is missing columns: {", ".join(sorted(missing))}')
    if frame.isbn13.isna().any() or frame.isbn13.duplicated().any():
        raise ValueError('Catalog ISBNs must be nonempty and unique.')
    frame['authors'] = frame['authors'].fillna('Unknown author')
    frame['description'] = frame['description'].fillna('')
    if not frame.description.str.strip().ne('').all():
        raise ValueError('Every book must have a description before indexing.')
    frame['large_thumbnail'] = frame['thumbnail'].fillna('').map(
        lambda url: url + ('&' if '?' in url else '?') + 'fife=w800'
        if isinstance(url, str) and url.strip()
        else str(ROOT / 'cover-not-found.jpg')
    )
    return frame


def get_books():
    global books
    if books is None:
        books = load_books()
    return books


def get_vector_store():
    global db_books
    if db_books is None:
        with index_lock:
            if db_books is None:
                import os
                from dotenv import load_dotenv
                from search_index import load_or_create_index

                load_dotenv(ROOT / '.env')
                model = os.getenv('OPENAI_EMBEDDING_MODEL', 'text-embedding-3-small')
                db_books = load_or_create_index(get_books(), ROOT / '.cache' / 'chroma', model)
    return db_books


def retrieve_semantic_recommendations(query: str, category: str = None,
                                      tone: str = None, initial_top_k: int = 50,
                                      final_top_k: int = 16) -> pd.DataFrame:
    catalog = get_books()
    if not isinstance(query, str) or not query.strip() or final_top_k <= 0:
        return catalog.iloc[:0].copy()
    if initial_top_k <= 0:
        raise ValueError('initial_top_k must be positive.')
    if tone not in (None, 'ALL', *TONES):
        raise ValueError('Unknown emotional tone.')
    candidates = catalog
    search_options = {}
    if category not in (None, 'ALL'):
        candidates = catalog[catalog['simple_categories'] == category]
        search_options['filter'] = {'simple_categories': category}
    if candidates.empty:
        return candidates.copy()

    # Chroma applies category filtering before finding the nearest neighbors.
    recs = get_vector_store().similarity_search(
        query.strip(), k=min(max(initial_top_k, final_top_k), len(candidates)),
        **search_options,
    )
    isbn_to_rank = {}
    for rec in recs:
        isbn_to_rank.setdefault(int(rec.metadata['isbn13']), len(isbn_to_rank))
    result = candidates[candidates['isbn13'].isin(isbn_to_rank)].copy()
    result['rank'] = result['isbn13'].map(isbn_to_rank)
    result = result.sort_values('rank', kind='stable')
    if tone in TONES:
        result = result.sort_values(TONES[tone], ascending=False, kind='stable')
    return result.head(final_top_k).drop(columns='rank')


def recommend_books(query: str, category: str = 'ALL', tone: str = 'ALL'):
    recommendations = retrieve_semantic_recommendations(query, category, tone)
    results = []
    for _, row in recommendations.iterrows():
        words = str(row['description']).split()
        description = ' '.join(words[:30]) + ('...' if len(words) > 30 else '')
        value = row['authors']
        authors = [part.strip() for part in value.split(';') if part.strip()] if isinstance(value, str) else []
        if not authors:
            author_text = 'Unknown author'
        elif len(authors) == 1:
            author_text = authors[0]
        elif len(authors) == 2:
            author_text = ' and '.join(authors)
        else:
            author_text = ', '.join(authors[:-1]) + ', and ' + authors[-1]
        results.append((row['large_thumbnail'], f"{row['title']} by {author_text}: {description}"))
    return results


def build_dashboard():
    import gradio as gr

    catalog = get_books()
    categories = ['ALL'] + sorted(catalog['simple_categories'].dropna().unique())
    with gr.Blocks() as dashboard:
        gr.Markdown('# Semantic book recommender')
        with gr.Row():
            query = gr.Textbox(label='Please enter a description of a book:',
                               placeholder='e.g. A story about forgiveness')
            category = gr.Dropdown(choices=categories, label='Select a category:', value='ALL')
            tone = gr.Dropdown(choices=['ALL', *TONES], label='Select an emotional tone:', value='ALL')
            submit = gr.Button('Find recommendations')
        gr.Markdown('## Recommendations')
        gallery = gr.Gallery(label='Recommended books', columns=8, rows=2)

        def submit_query(query, category, tone):
            if not query or not query.strip():
                gr.Info('Enter a book description to find recommendations.')
                return []
            try:
                result = recommend_books(query, category, tone)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).exception('Recommendation search failed')
                raise gr.Error('Search is unavailable. Check your API key, connection, and terminal output.') from exc
            if not result:
                gr.Info('No matching books found. Try another category or description.')
            return result

        submit.click(submit_query, inputs=[query, category, tone], outputs=gallery)
        query.submit(submit_query, inputs=[query, category, tone], outputs=gallery)
    return dashboard


if __name__ == '__main__':
    import gradio as gr
    build_dashboard().queue().launch(
        theme=gr.themes.Glass(), allowed_paths=[str(ROOT / 'cover-not-found.jpg')],
    )
