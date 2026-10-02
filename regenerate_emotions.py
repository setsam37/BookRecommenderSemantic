"""Regenerate the catalog's emotion columns using the public classifier."""
import argparse
import json
from pathlib import Path

import pandas as pd

from emotion_scores import EMOTION_LABELS, calculate_max_emotion_scores


ROOT = Path(__file__).resolve().parent
MODEL_ID = 'j-hartmann/emotion-english-distilroberta-base'


def regenerate(input_path, output_path, batch_size=32, device='cpu', model_path=MODEL_ID,
               revision=None, threads=4, model_id=None):
    import torch
    from tqdm import tqdm
    from transformers import pipeline

    if batch_size <= 0:
        raise ValueError('batch_size must be positive.')
    torch.set_num_threads(threads)
    books = pd.read_csv(input_path)
    if books['description'].isna().any():
        raise ValueError('All books need descriptions before scoring.')
    classifier = pipeline('text-classification', model=model_path, revision=revision,
                          top_k=None, device=device)
    # Length grouping reduces padding while preserving each sentence's book ID.
    sentences = [(i, sentence) for i, text in enumerate(books['description'])
                 for sentence in text.split('.')]
    sentences.sort(key=lambda item: len(item[1]))
    scores = [{label: 0.0 for label in EMOTION_LABELS} for _ in range(len(books))]
    for start in tqdm(range(0, len(sentences), batch_size), desc='Emotion batches'):
        batch = sentences[start:start + batch_size]
        predictions = classifier([text for _, text in batch], batch_size=batch_size,
                                 truncation=True, max_length=512)
        for (book_index, _), prediction in zip(batch, predictions, strict=True):
            maxima = calculate_max_emotion_scores([prediction])
            for label in EMOTION_LABELS:
                scores[book_index][label] = max(scores[book_index][label], maxima[label])
    for label in EMOTION_LABELS:
        books[label] = [row[label] for row in scores]
    output_path = Path(output_path)
    temporary = output_path.with_suffix('.csv.tmp')
    books.to_csv(temporary, index=False)
    temporary.replace(output_path)
    metadata = {'model': model_id or str(model_path), 'revision': revision, 'books': len(books),
                'sentences': len(sentences), 'aggregation': 'per-label maximum over period-separated sentences',
                'truncation': 512, 'torch': torch.__version__}
    output_path.with_suffix('.metadata.json').write_text(
        json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    return books


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'books_with_categories.csv')
    parser.add_argument('--output', type=Path, default=ROOT / 'books_with_emotions.csv')
    parser.add_argument('--batch-size', type=int, default=32)
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--model', default=MODEL_ID, help='Public model ID or a local model directory.')
    parser.add_argument('--model-id', default=None, help='Canonical model ID when loading a local model directory.')
    parser.add_argument('--revision', default=None, help='Pin the Hugging Face model commit.')
    parser.add_argument('--threads', type=int, default=4)
    args = parser.parse_args()
    regenerate(args.input, args.output, args.batch_size, args.device, args.model,
               args.revision, args.threads, args.model_id)
