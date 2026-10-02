from emotion_scores import calculate_max_emotion_scores
import pytest


def test_scores_are_assigned_by_label_including_neutral():
    predictions = [[{'label': label, 'score': score} for label, score in [
        ('surprise', 0.1), ('neutral', 0.2), ('sadness', 0.3),
        ('joy', 0.4), ('fear', 0.5), ('disgust', 0.6), ('anger', 0.7),
    ]]]
    assert calculate_max_emotion_scores(predictions) == {
        'anger': 0.7, 'disgust': 0.6, 'fear': 0.5, 'joy': 0.4,
        'sadness': 0.3, 'surprise': 0.1,
    }


def test_missing_labels_are_rejected_instead_of_silently_shifting_scores():
    with pytest.raises(ValueError, match='missing emotion labels'):
        calculate_max_emotion_scores([[{'label': 'joy', 'score': 0.8}]])


def test_each_emotion_uses_its_maximum_across_sentences():
    labels = ['anger', 'disgust', 'fear', 'joy', 'sadness', 'surprise']
    predictions = [
        [{'label': label, 'score': 0.1} for label in labels],
        [{'label': label, 'score': 0.9 if label == 'surprise' else 0.05} for label in labels],
    ]
    assert calculate_max_emotion_scores(predictions) == {
        'anger': 0.1, 'disgust': 0.1, 'fear': 0.1, 'joy': 0.1, 'sadness': 0.1, 'surprise': 0.9,
    }
