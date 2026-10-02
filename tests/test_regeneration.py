import json
import sys
from types import SimpleNamespace

import pandas as pd

from regenerate_emotions import regenerate


def test_generated_csv_and_metadata_identify_the_selected_model(tmp_path, monkeypatch):
    def classify(texts, **kwargs):
        return [[{'label': label, 'score': score} for label, score in [
            ('neutral', 0.2), ('sadness', 0.3), ('surprise', 0.1),
            ('anger', 0.1), ('disgust', 0.1), ('fear', 0.1), ('joy', 0.1),
        ]] for text in texts]
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(
        __version__='test', set_num_threads=lambda value: None))
    monkeypatch.setitem(sys.modules, 'transformers', SimpleNamespace(pipeline=lambda *args, **kwargs: classify))
    source = tmp_path / 'input.csv'
    output = tmp_path / 'output.csv'
    pd.DataFrame({'isbn13': [100], 'description': ['One sentence. Another sentence.']}).to_csv(source, index=False)
    regenerate(source, output, model_path='another/emotion-model', revision='test-revision')
    result = pd.read_csv(output)
    assert result.sadness.tolist() == [0.3]
    assert result.surprise.tolist() == [0.1]
    assert result.isbn13.tolist() == [100]
    metadata = json.loads(output.with_suffix('.metadata.json').read_text())
    assert metadata['model'] == 'another/emotion-model'
    assert metadata['revision'] == 'test-revision'
    assert metadata['books'] == 1
