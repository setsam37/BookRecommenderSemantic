# Semantic Book Recommender

Find books from a natural-language description, with an optional category and emotional tone. The Gradio app searches 5,197 book descriptions using OpenAI embeddings and a persistent Chroma index. Category filtering happens inside vector search; tone ranking sorts up to 50 semantic matches before returning 16 books.

## Before using this repository

An earlier version committed an OpenAI key and a Hugging Face token. **Revoke both exposed credentials before using the app.** Removing a file or rewriting Git history does not revoke a credential. Use a newly created OpenAI key. Public Hugging Face models used here do not require a token.

The working tree no longer tracks `.env` or `.idea`. A cleaned-history bundle is supplied separately; applying this code patch or merging its PR does not rewrite old commits. Copies, forks, and GitHub cached commit views may still contain the old secrets. The owner must separately update the remote history and, where necessary, request removal of cached sensitive data from GitHub Support. See [GitHub's sensitive-data removal instructions](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).

## Quick start

Use Python 3.10–3.13; Python 3.13 is the locally tested version. The application dependencies are pinned in `requirements.txt`.

```sh
git clone https://github.com/setsam37/BookRecommenderSemantic.git
cd BookRecommenderSemantic
python -m venv .venv
```

Activate the environment on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Or on macOS/Linux:

```sh
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` locally and set `OPENAI_API_KEY` to your **new** key. Keep that file out of Git. Then run:

```sh
python gradio-dashboard.py
```

Open the local URL printed in the terminal, usually `http://127.0.0.1:7860`. The supplied CSV files are enough to run the app; preprocessing notebooks do not need to run first.

The first search embeds the catalog through the paid OpenAI API. Later searches reuse the stored book embeddings and embed only the query. Importing the Python file or starting the UI makes no embedding request. A missing key or failed request produces a readable UI error; details appear in the local terminal.

## Index storage and ranking

- The index lives in `.cache/chroma/`, which Git ignores.
- Each index is keyed by descriptions, ISBNs, categories, and `OPENAI_EMBEDDING_MODEL` (default: `text-embedding-3-small`). Editing these inputs creates a separate index so stale vectors are not reused. Changing only emotion scores does not trigger re-embedding.
- Stable ISBN document IDs let an interrupted build resume by embedding only missing books.
- A category is applied before nearest-neighbor retrieval, so rare categories are not restricted to the first 50 overall matches.
- With no tone, semantic order is preserved. With a tone, the candidate pool is sorted by its emotion score; ties preserve semantic order. Scores describe emotions in the book description, not a guaranteed emotional experience of reading the book.
- Blank queries return no results without making an API request. Missing authors use `Unknown author`, and missing covers use the bundled fallback image.

Stop the app before deleting `.cache/chroma/` if you deliberately want to rebuild every index. That incurs new embedding charges on the next search.

## Regenerate emotion scores

The original emotion notebook incorrectly assigned `neutral` scores to `sadness` and `sadness` scores to `surprise`. The shared aggregator now matches labels by name. Regenerate the entire dataset rather than renaming the old columns: the original CSV did not retain true surprise scores.

```sh
python -m pip install -r requirements-data.txt
python regenerate_emotions.py --revision 0e1cd914e3d46199ed785853e12b57304e04178b
```

The script downloads the public `j-hartmann/emotion-english-distilroberta-base` model, splits descriptions on periods, and records the maximum score for each named emotion. Inputs are truncated to the model's 512-token limit. CPU processing can take several minutes; `--device cuda` uses a compatible GPU. `--batch-size` controls inference memory use. The CSV is replaced only after all rows have been scored; `books_with_emotions.metadata.json` records provenance.

For experimentation, install `requirements-data.txt`, start Jupyter from the repository directory, and run notebooks in this order:

1. `data-exploration.ipynb`: download the Kaggle 7K Books dataset and write `books_cleaned.csv`.
2. `text-classification.ipynb`: map/classify categories and write `books_with_categories.csv`.
3. `sentiment-analysis.ipynb`: regenerate the emotion catalog using the shared script.
4. `vector-search.ipynb`: explore semantic retrieval with the same persistent index as the app.

Public models may need large downloads on first use. The category notebook can take substantially longer than the emotion script.

## Tests

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests do not require credentials or paid API calls. They check tone ranking, semantic order, category retrieval, missing metadata, emotion-label aggregation, and real Chroma index persistence with deterministic local embeddings. GitHub Actions runs the suite on Python 3.10 and 3.13 after these changes are published.

## Files

- `gradio-dashboard.py`: UI, catalog loading, result ranking, and captions.
- `search_index.py`: persistent indexing and interrupted-build recovery.
- `emotion_scores.py`: label-based emotion aggregation.
- `regenerate_emotions.py`: batched reproducible data generation.
- `books_with_emotions.csv`: application catalog.
- `books_with_emotions.metadata.json`: generated data provenance.
- `.env.example`: safe configuration template, containing no credentials.

The dataset originates from [7K Books with Metadata on Kaggle](https://www.kaggle.com/datasets/dylanjcastillo/7k-books-with-metadata). Consult its terms before redistributing the data or covers.
