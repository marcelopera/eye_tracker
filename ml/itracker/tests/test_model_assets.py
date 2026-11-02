from io import BytesIO
import hashlib
import sys
from urllib.error import URLError

import pytest

import model_assets


@pytest.fixture
def assets(monkeypatch):
    payloads = {name: f'synthetic model: {name}'.encode() for name in model_assets.ASSETS}
    manifest = {name: (f'https://models.invalid/{name}', hashlib.sha256(data).hexdigest())
                for name, data in payloads.items()}
    monkeypatch.setattr(model_assets, 'ASSETS', manifest)
    calls = []
    def response(url, *, timeout):
        assert timeout == 120
        name = url.rsplit('/', 1)[1]
        calls.append(name)
        return BytesIO(payloads[name])
    monkeypatch.setattr(model_assets, 'urlopen', response)
    return payloads, calls


def test_empty_directory_downloads_all_six_assets_and_cached_restart_is_offline(tmp_path, monkeypatch, assets):
    payloads, calls = assets
    directory = tmp_path / 'models'
    model_assets.download(directory, model_assets.ASSETS)
    assert set(calls) == set(payloads) and len(calls) == 6
    assert {p.name for p in directory.iterdir()} == set(payloads)
    model_assets.verify(directory, model_assets.ASSETS)
    before = {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in directory.iterdir()}
    assert all(p.stat().st_mode & 0o777 == 0o644 for p in directory.iterdir())
    def offline(*args, **kwargs):
        pytest.fail('A verified cached model must not require network access')
    monkeypatch.setattr(model_assets, 'urlopen', offline)
    model_assets.download(directory, model_assets.ASSETS)
    assert {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in directory.iterdir()} == before


def test_missing_and_corrupt_assets_are_repaired_selectively(tmp_path, assets):
    payloads, calls = assets
    for name, data in payloads.items():
        (tmp_path / name).write_bytes(data)
    (tmp_path / 'mean_left_224.mat').unlink()
    (tmp_path / 'face_landmarker.task').write_bytes(b'corrupt detector')
    model_assets.download(tmp_path, model_assets.ASSETS)
    assert set(calls) == {'mean_left_224.mat', 'face_landmarker.task'}
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == payloads


def test_wrong_download_hash_is_never_published_and_temporary_files_are_removed(tmp_path, monkeypatch, assets):
    (tmp_path / 'face_landmarker.task').write_bytes(b'previous file')
    monkeypatch.setattr(model_assets, 'urlopen', lambda *args, **kwargs: BytesIO(b'incorrect bytes'))
    with pytest.raises(ValueError, match='SHA-256'):
        model_assets.download(tmp_path, ['face_landmarker.task'])
    assert (tmp_path / 'face_landmarker.task').read_bytes() == b'previous file'
    assert not list(tmp_path.glob('.download-*'))


def test_transient_network_failure_is_retried_with_a_fresh_atomic_download(tmp_path, monkeypatch, assets):
    payloads, _ = assets
    attempts = []
    delays = []
    def response(*args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise URLError('temporary network failure')
        return BytesIO(payloads['face_landmarker.task'])
    monkeypatch.setattr(model_assets, 'urlopen', response)
    monkeypatch.setattr(model_assets.time, 'sleep', delays.append)
    model_assets.download(tmp_path, ['face_landmarker.task'])
    assert len(attempts) == 2 and delays == [1]
    model_assets.verify(tmp_path, ['face_landmarker.task'])
    assert not list(tmp_path.glob('.download-*'))


def test_failed_startup_exits_nonzero_and_does_not_leave_partial_models(tmp_path, monkeypatch, assets, capsys):
    attempts = []
    def unavailable(*args, **kwargs):
        attempts.append(1)
        raise URLError('network unavailable')
    monkeypatch.setattr(model_assets, 'urlopen', unavailable)
    monkeypatch.setattr(model_assets.time, 'sleep', lambda _: None)
    monkeypatch.setattr(sys, 'argv', ['model_assets.py', '--models', str(tmp_path)])
    with pytest.raises(SystemExit) as failure:
        model_assets.main()
    assert failure.value.code == 1 and len(attempts) == 3
    assert 'Falha ao preparar modelos' in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_bootstrap_entrypoint_checks_network_and_detector_assets(tmp_path, monkeypatch, assets, capsys):
    _, calls = assets
    monkeypatch.setattr(sys, 'argv', ['model_assets.py', '--models', str(tmp_path)])
    model_assets.main()
    assert len(calls) == 6 and 'face_landmarker.task' in calls
    assert 'Todos os modelos estão prontos' in capsys.readouterr().out


def test_incomplete_response_is_cleaned_up_after_bounded_retries(tmp_path, monkeypatch, assets):
    class BrokenResponse(BytesIO):
        def read(self, size=-1):
            if self.tell():
                raise ConnectionResetError('interrupted download')
            return super().read(size)
    monkeypatch.setattr(model_assets, 'urlopen', lambda *args, **kwargs: BrokenResponse(b'partial response'))
    monkeypatch.setattr(model_assets.time, 'sleep', lambda _: None)
    with pytest.raises(ConnectionResetError):
        model_assets.download(tmp_path, ['face_landmarker.task'])
    assert list(tmp_path.iterdir()) == []
