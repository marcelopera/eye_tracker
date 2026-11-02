from fractions import Fraction
import json

import av
import numpy as np
import pytest

import itracker
from video import camera_frames


def make_video(path):
    with av.open(str(path), "w") as output:
        stream = output.add_stream("ffv1", rate=10)
        stream.width, stream.height = 32, 24
        stream.pix_fmt = "bgr0"
        for pts in (0, 2, 5):
            image = np.zeros((24, 32, 3), dtype=np.uint8)
            image[:, :16, 0] = 255
            frame = av.VideoFrame.from_ndarray(image, format="bgr24")
            frame.pts, frame.time_base = pts, Fraction(1, 10)
            for packet in stream.encode(frame):
                output.mux(packet)
        for packet in stream.encode():
            output.mux(packet)


def test_pts_and_orientation_are_preserved(tmp_path):
    path = tmp_path / "camera.mkv"
    make_video(path)
    frames = list(camera_frames(path, rotation=90, mirrored=True))
    assert len(frames) == 3
    assert [Fraction(meta["camera_pts"]) * Fraction(*meta["camera_time_base"]) for _, meta in frames] == [Fraction(0), Fraction(2, 10), Fraction(5, 10)]
    image = frames[0][0]
    assert image.shape == (32, 24, 3)
    assert image[0, 0, 0] == 0 and image[-1, 0, 0] == 255


def test_diagnostic_records_and_failed_decode_are_atomic(tmp_path):
    source, output = tmp_path / "camera.mkv", tmp_path / "frames.jsonl"
    make_video(source)
    itracker.inspect_video(source, output, 0, False)
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert len(rows) == 3
    assert all(row["prediction_cm"] is None and row["stimulus_time_ms"] is None and not row["valid"] for row in rows)
    previous = output.read_bytes()
    source.write_bytes(b"invalid video")
    with pytest.raises(av.FFmpegError):
        itracker.inspect_video(source, output, 0, False)
    assert output.read_bytes() == previous
    assert not list(tmp_path.glob(".video-*"))
    with pytest.raises(ValueError, match="substituir"):
        itracker.inspect_video(source, source, 0, False)
