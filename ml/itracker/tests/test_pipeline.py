import json

import cv2
import numpy as np

from pipeline import process_session
from preprocess import DetectionFailure
from test_video import make_video


class Detector:
    def __init__(self, directory):
        self.count = 0
    def close(self):
        pass
    def prepare(self, image):
        self.count += 1
        if self.count == 2:
            raise DetectionFailure("no_face")
        return {}, {"face": [0, 0, 32, 24]}, {name: np.zeros((224, 224, 3), np.uint8) for name in ("face", "left", "right")}


class Model:
    def __init__(self, directory):
        pass
    def predict(self, inputs):
        return np.array([[1., -2.]], np.float32), np.zeros((1, 128), np.float32)


def test_video_to_export_preserves_failed_frames_and_missing_measurements(tmp_path):
    video, events, config = [tmp_path / name for name in ("video.mkv", "sessao.json", "config.json")]
    make_video(video)
    events.write_text(json.dumps({"estado": "interrompida", "eventos": []}))
    config.write_text(json.dumps({"schema_version": 1, "capture": {"rotation_degrees": 0, "mirrored": False}}))
    output = tmp_path / "results"
    report = process_session(video, events, tmp_path, config, output, preprocessor_factory=Detector, model_factory=Model)
    assert report["frames"] == 3 and report["valid_frames"] == 2
    assert report["collection_status"] == "interrompida"
    assert report["synchronization"]["status"] == "unavailable"
    assert report["failure_counts"] == {"no_face": 1}
    rows = [json.loads(line) for line in (output / "samples.jsonl").read_text().splitlines()]
    assert [r["frame_index"] for r in rows] == [0, 1, 2]
    assert all(r["stimulus_time_ms"] is None and r["stimulus_px"] is None for r in rows)
    assert rows[1]["prediction_cm"] is None and "features" not in rows[0]
    assert rows[0]["prediction_cm"] == [1., -2.]
    assert len((output / "samples.csv").read_text().splitlines()) == 4
    assert cv2.imread(str(output / report["previews"][0]["file"])).shape == (224, 672, 3)


def test_complete_controlled_pipeline_with_calibration_validation_and_stimulus(tmp_path):
    from fractions import Fraction
    import av
    video = tmp_path / 'complete.mkv'
    with av.open(str(video), 'w') as output:
        stream = output.add_stream('ffv1', rate=10)
        stream.width, stream.height, stream.pix_fmt = 32, 24, 'bgr0'
        for index in range(8):
            frame = av.VideoFrame.from_ndarray(np.zeros((24,32,3), np.uint8), format='bgr24')
            frame.pts, frame.time_base = index, Fraction(1,10)
            for packet in stream.encode(frame): output.mux(packet)
        for packet in stream.encode(): output.mux(packet)
    class AllFaces(Detector):
        def prepare(self, image):
            return {}, {}, {n: np.zeros((224,224,3), np.uint8) for n in ('face','left','right')}
    origin = 10**12
    geometry = {"screen_width_px": 1000, "screen_height_px": 2000, "screen_width_mm": 100,
                "screen_height_mm": 200, "camera_x_mm": 50, "camera_y_mm": 0,
                "model_axes": [[1,0],[0,-1]], "measurement_evidence": "synthetic only", "axes_evidence": "synthetic only",
                "stimulus_rect": [0,500,1000,1000], "stimulus_width_px": 100, "stimulus_height_px": 100}
    settings = {"schema_version": 1, "capture": {"rotation_degrees": 0, "mirrored": False}, "geometry": geometry,
                "synchronization": {"method": "synthetic test clock", "evidence": "synthetic only", "event_clock": "test",
                    "anchors": [{"camera_ns": t, "event_ns": origin+t} for t in (0,400000000,800000000)],
                    "measurement_error_ms": 0, "max_error_ms": 1,
                    "presented_frames": [{"event_ns": origin+t, "media_time_ms": ms, "duration_ms": 100} for t,ms in ((500000000,0),(600000000,100))]},
                "targets": [{"phase": "calibration" if i<3 else "validation", "start_ns": origin+i*100000000,
                             "end_ns": origin+(i+1)*100000000, "x_px": i*100, "y_px": i*100} for i in range(5)],
                "calibration": {"kernel":"linear","C":1,"epsilon":.1,"gamma":1,"min_samples":3,"min_targets":3}}
    config = tmp_path / 'config.json';config.write_text(json.dumps(settings))
    events = tmp_path / 'events.json';events.write_text(json.dumps({"estado":"concluida","eventos":[]}))
    report = process_session(video, events, tmp_path, config, tmp_path/'results', preprocessor_factory=AllFaces, model_factory=Model)
    assert report['calibration']['status'] == 'available'
    assert {p['phase'] for p in report['previews']} == {'calibration', 'validation', 'stimulus'}
    assert len(list((tmp_path/'results').glob('crops-*.jpg'))) == 3
    assert report['validation']['baseline']['evaluated_frames'] == 2
    assert report['validation']['calibrated']['evaluated_frames'] == 2
    rows = [json.loads(line) for line in (tmp_path/'results/samples.jsonl').read_text().splitlines()]
    assert rows[5]['stimulus_time_ms'] == 0 and rows[6]['stimulus_time_ms'] == 100
    assert rows[4]['stimulus_time_ms'] is None and rows[7]['stimulus_time_ms'] is None
    assert rows[5]['stimulus_px'] == [60., -30.] and rows[5]['outside_stimulus']
    assert rows[5]['calibrated_stimulus_px'] is not None
