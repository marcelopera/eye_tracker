"""Camera video to auditable gaze estimates; absent measurements stay absent."""
from collections import Counter
from fractions import Fraction
import csv
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
from uuid import uuid4

import cv2
import numpy as np

from analysis import Timeline, calibrate, evaluate, screen_point, stimulus_point, smooth_demonstration
from config import ProcessingConfig
from itracker import FILES, REVISION, Model, digest
from preprocess import DetectionFailure, LANDMARKER_SHA256, Preprocessor
from video import camera_frames

PIPELINE_VERSION = "1.2.0"


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")


def process_session(video: Path, events: Path, models: Path, config_path: Path, output: Path,
                    *, run_id=None, session_id=None, progress_path=None, preprocessor_factory=Preprocessor, model_factory=Model):
    started = time.monotonic()
    run_id = run_id or str(uuid4())
    if progress_path and progress_path.resolve() in {p.resolve() for p in (video, events, config_path)}:
        raise ValueError("Progresso não pode substituir arquivos de entrada")
    def progress(count, stage):
        if progress_path is None:
            return
        fd, temporary = tempfile.mkstemp(dir=progress_path.parent, prefix=".progress-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump({"frames_processed": count, "stage": stage}, stream)
            os.replace(temporary, progress_path)
        finally:
            Path(temporary).unlink(missing_ok=True)
    config = ProcessingConfig.model_validate_json(config_path.read_text(encoding="utf-8"))
    metadata = json.loads(events.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict) or metadata.get("estado") not in ("concluida", "interrompida") or not isinstance(metadata.get("eventos"), list):
        raise ValueError("Metadados da coleta incompatíveis")
    if output.exists():
        raise ValueError("Diretório de saída já existe; use uma nova execução")
    output.parent.mkdir(parents=True, exist_ok=True)
    timeline = Timeline(config.synchronization)
    model = model_factory(models)
    detector = preprocessor_factory(models)
    rows = []
    try:
        with tempfile.TemporaryDirectory(dir=output.parent, prefix=".processing-") as temporary:
            directory = Path(temporary)
            previews = []
            for image, timing in camera_frames(video, config.capture.rotation_degrees, config.capture.mirrored):
                if len(rows) >= 100000:
                    raise ValueError("Limite de 100000 quadros por execução excedido")
                camera_ns = (int(Fraction(timing["camera_pts"]) * Fraction(*timing["camera_time_base"]) * 10**9)
                             if timing["camera_pts"] is not None and timing["camera_time_base"] else None)
                event_ns = timeline.event_time(camera_ns)
                stimulus_ms, temporal_reason = timeline.stimulus_time(event_ns)
                if event_ns is None:
                    temporal_reason = ("missing_camera_timestamp" if camera_ns is None else
                                       "outside_anchor_range" if timeline.report["status"] == "available" else
                                       "synchronization_" + timeline.report["status"])
                target = next((t for t in config.targets if event_ns is not None and t.start_ns <= event_ns < t.end_ns), None)
                row = {**timing, "run_id": run_id, "session_id": session_id or metadata.get("coleta_local"), "camera_time_ns": camera_ns, "event_time_ns": event_ns,
                       "phase": target.phase if target else ("stimulus" if stimulus_ms is not None else "unknown"),
                       "stimulus_time_ms": stimulus_ms, "temporal_reason": temporal_reason,
                       "prediction_cm": None, "features": None, "screen_px": None, "stimulus_px": None,
                       "calibrated_screen_px": None, "calibrated_stimulus_px": None,
                       "target_px": [target.x_px, target.y_px] if target else None,
                       "valid": False, "reason": None, "boxes": None,
                       "spatial_reason": "missing_geometry" if config.geometry is None else None,
                       "outside_screen": None, "outside_stimulus": None,
                       "calibrated_outside_screen": None, "calibrated_outside_stimulus": None}
                try:
                    inputs, boxes, crops = detector.prepare(image)
                    prediction, features = model.predict(inputs)
                    row.update(valid=True, prediction_cm=prediction[0].tolist(), features=features[0].tolist(), boxes=boxes)
                    row["screen_px"] = screen_point(row["prediction_cm"], config.geometry)
                    replace = None
                    if len(previews) >= config.preview_frames and row['phase'] in ('calibration', 'stimulus', 'validation') and not any(p.get('phase') == row['phase'] for p in previews):
                        counts = Counter(p.get('phase') for p in previews)
                        replace = next((p for p in previews if p.get('phase') == 'unknown' or counts[p.get('phase')] > 1), None)
                    if len(previews) < config.preview_frames or replace is not None:
                        filename = f"crops-{timing['frame_index']}.jpg"
                        if not cv2.imwrite(str(directory / filename), np.concatenate([crops[n] for n in ("face", "left", "right")], axis=1)):
                            raise OSError("Não foi possível salvar inspeção dos recortes")
                        if replace is not None:
                            (directory / replace['file']).unlink()
                            previews.remove(replace)
                        previews.append({"frame_index": timing["frame_index"], "file": filename, "phase": row['phase'], "order": ["face", "left", "right"]})
                except DetectionFailure as error:
                    row["reason"] = str(error)
                rows.append(row)
                if len(rows) % 30 == 0:
                    progress(len(rows), "inference")
            progress(len(rows), "evaluation")
            calibration = calibrate(rows, config)
            for row in rows:
                for prefix in ("", "calibrated_"):
                    point = row[prefix + "screen_px"]
                    row[prefix + "stimulus_px"] = stimulus_point(point, config.geometry) if row["stimulus_time_ms"] is not None else None
                    if point is not None and config.geometry:
                        g = config.geometry
                        row[prefix + "outside_screen"] = not (0 <= point[0] < g.screen_width_px and 0 <= point[1] < g.screen_height_px)
                        mapped = row[prefix + "stimulus_px"]
                        if mapped is not None:
                            row[prefix + "outside_stimulus"] = not (0 <= mapped[0] < g.stimulus_width_px and 0 <= mapped[1] < g.stimulus_height_px)
            if config.demonstration:
                smooth_demonstration(rows)
            metrics = evaluate(rows, config.geometry, config.criteria)
            count = len(rows)
            valid = sum(r["valid"] for r in rows)
            elapsed = time.monotonic() - started
            summary = {"pipeline_version": PIPELINE_VERSION, "run_id": run_id, "model_revision": REVISION,
                       "model_sha256": {name: value[1] for name, value in FILES.items()},
                       "source_sha256": {p.name: digest(p) for p in sorted(Path(__file__).parent.glob("*.py"))},
                       "dependencies_sha256": digest(Path(__file__).parent / "uv.lock"),
                       "detector_sha256": LANDMARKER_SHA256, "config": config.model_dump(),
                       "input_sha256": {"video": digest(video), "events": digest(events)},
                       "session_id": session_id or metadata.get("coleta_local"), "local_session_id": metadata.get("coleta_local"), "experiment_id": metadata.get("experimento"),
                       "collection_status": metadata["estado"], "frames": count, "valid_frames": valid,
                       "invalid_fraction": (count - valid) / count,
                       "frames_with_event_time": sum(r["event_time_ns"] is not None for r in rows),
                       "frames_with_stimulus_time": sum(r["stimulus_time_ms"] is not None for r in rows), "failure_counts": dict(Counter(r["reason"] for r in rows if not r["valid"])),
                       "processing_seconds": elapsed, "frames_per_second": count / elapsed,
                       "synchronization": timeline.report, "calibration": calibration,
                       "geometry_status": "provided" if config.geometry else "unavailable",
                       "validation": metrics, "previews": previews,
                       "scientific_validation": "classroom_demonstration" if config.demonstration else "requires_device_pilot",
                       "config_mode": "demonstration" if config.demonstration else "measured",
                       "preprocessing": {"channels": "BGR", "scale": "0..255 minus official mean", "resize": "bilinear",
                                         "face_square_margin": 1.1, "eye_square_margin": 1.8,
                                         "padding": "replicate", "grid": "25x25 row-major, MATLAB rounding",
                                         "detector_equivalence": "not_equivalent_to_Apple"}}
            with (directory / "samples.jsonl").open("w", encoding="utf-8") as stream:
                for row in rows:
                    if not config.export_features:
                        row.pop("features")
                    stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            fields = ["run_id", "session_id", "frame_index", "camera_pts", "time_base_num", "time_base_den", "camera_time_ns", "event_time_ns",
                      "phase", "stimulus_time_ms", "valid", "reason", "temporal_reason", "spatial_reason", "raw_x_cm", "raw_y_cm",
                      "screen_x_px", "screen_y_px", "x_px", "y_px", "calibrated_screen_x_px", "calibrated_screen_y_px",
                      "calibrated_x_px", "calibrated_y_px", "outside_screen", "outside_stimulus",
                      "calibrated_outside_screen", "calibrated_outside_stimulus", "demo_x_px", "demo_y_px"]
            with (directory / "samples.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                for row in rows:
                    flat = {key: row.get(key) for key in fields}
                    base = row["camera_time_base"] or [None, None]
                    flat.update(time_base_num=base[0], time_base_den=base[1])
                    for key, names in (("prediction_cm", ("raw_x_cm", "raw_y_cm")), ("screen_px", ("screen_x_px", "screen_y_px")),
                                       ("stimulus_px", ("x_px", "y_px")), ("calibrated_screen_px", ("calibrated_screen_x_px", "calibrated_screen_y_px")),
                                       ("calibrated_stimulus_px", ("calibrated_x_px", "calibrated_y_px")),
                                       ("demo_stimulus_px", ("demo_x_px", "demo_y_px"))):
                        point = row.get(key) or [None, None]
                        flat.update(zip(names, point))
                    writer.writerow(flat)
            write_json(directory / "summary.json", summary)
            shutil.move(str(directory), output)
    finally:
        detector.close()
    return summary
