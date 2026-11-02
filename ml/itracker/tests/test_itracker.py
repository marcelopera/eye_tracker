import numpy as np
import pytest

import itracker


def test_missing_or_changed_models_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="ausente ou SHA-256"):
        itracker.verify(tmp_path)
    (tmp_path / "itracker_deploy.prototxt").write_text("corrompido")
    with pytest.raises(ValueError, match="SHA-256"):
        itracker.verify(tmp_path)


def test_input_validation_and_named_blobs(tmp_path, monkeypatch):
    monkeypatch.setattr(itracker, "verify", lambda *args: None)
    class Net:
        def __init__(self):
            self.blobs = {}
        def setInput(self, data, name):
            self.blobs[name] = data
        def forward(self, outputs):
            assert outputs == ["fc3", "relufc2"]
            assert set(self.blobs) == set(itracker.BLOBS.values())
            return np.zeros((1, 2)), np.zeros((1, 128))
    monkeypatch.setattr(itracker.cv2.dnn, "readNetFromCaffe", lambda *args: Net())
    inputs = {k: np.zeros(shape, np.float32) for k, shape in itracker.INPUTS.items()}
    assert itracker.infer(tmp_path, inputs)[1].shape == (1, 128)
    inputs["face"][0, 0, 0, 0] = np.nan
    with pytest.raises(ValueError, match="face"):
        itracker.infer(tmp_path, inputs)
