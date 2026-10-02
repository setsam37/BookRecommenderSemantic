"""Aggregate classifier scores by label, never by their position."""
EMOTION_LABELS = ('anger', 'disgust', 'fear', 'joy', 'sadness', 'surprise')


def calculate_max_emotion_scores(predictions):
    scores = {label: 0.0 for label in EMOTION_LABELS}
    for prediction in predictions:
        by_label = {item['label']: float(item['score']) for item in prediction}
        missing = set(EMOTION_LABELS) - by_label.keys()
        if missing:
            raise ValueError(f'Classifier is missing emotion labels: {sorted(missing)}')
        for label in EMOTION_LABELS:
            scores[label] = max(scores[label], by_label[label])
    return scores
