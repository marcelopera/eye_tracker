"""Controlled-input inference with the published frozen iTracker Caffe model."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import urllib.request

import av
import cv2
import numpy as np

from video import camera_frames

REVISION = "e4af90da3c4c9068fbce433fa648d1f9bc7a394b"
BASE = f"https://raw.githubusercontent.com/CSAILVision/GazeCapture/{REVISION}/models"
FILES = {
    "itracker_deploy.prototxt": ("itracker_deploy.prototxt", "93a984a55829f07813859a068d9bf30ec8b3161d7121f715a9a9124b34cfdb76"),
    "itracker25x_iter_92000.caffemodel": ("snapshots/itracker25x_iter_92000.caffemodel", "d748042ebd402a4b6418cdff44a6e64f9bca1256fd3761f7ddc68fd5519ef98a"),
    "mean_face_224.mat": ("mean_images/mean_face_224.mat", "43dccf2f655259b23d3b2cd20907f5d7479e175215caba6bb310d3a4c3fc4756"),
    "mean_left_224.mat": ("mean_images/mean_left_224.mat", "b502c0c7392cea761688625f2be8b0359fc9df74599ef744ce37b7dc68dcb470"),
    "mean_right_224.mat": ("mean_images/mean_right_224.mat", "15167a33bc553cf624869be2717129362ea2a3445ba26676927a6f63205e2ef0"),
}
INPUTS = {"face": (1, 3, 224, 224), "left": (1, 3, 224, 224), "right": (1, 3, 224, 224), "grid": (1, 625)}
BLOBS = {"face": "image_face", "left": "image_left", "right": "image_right", "grid": "facegrid"}


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(directory, names=FILES):
    for name in names:
        path = directory / name
        if not path.is_file() or digest(path) != FILES[name][1]:
            raise ValueError(f"Arquivo ausente ou SHA-256 incompatível: {path}; execute download")


def download(directory):
    directory.mkdir(parents=True, exist_ok=True)
    for name, (remote, expected) in FILES.items():
        destination = directory / name
        if destination.is_file() and digest(destination) == expected:
            destination.chmod(0o644)
            continue
        fd, temporary = tempfile.mkstemp(dir=directory, prefix=".download-")
        try:
            with os.fdopen(fd, "wb") as output, urllib.request.urlopen(f"{BASE}/{remote}", timeout=120) as response:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            if digest(Path(temporary)) != expected:
                raise ValueError(f"SHA-256 incompatível para {name}")
            os.chmod(temporary, 0o644)
            os.replace(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)


class Model:
    """Load and verify the frozen network once per run."""
    def __init__(self, directory):
        verify(directory, ("itracker_deploy.prototxt", "itracker25x_iter_92000.caffemodel"))
        cv2.setNumThreads(1)
        self.net = cv2.dnn.readNetFromCaffe(str(directory / "itracker_deploy.prototxt"), str(directory / "itracker25x_iter_92000.caffemodel"))
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

    def predict(self, inputs):
        if set(inputs) != set(INPUTS):
            raise ValueError(f"Entradas esperadas: {', '.join(INPUTS)}")
        for name, shape in INPUTS.items():
            value = inputs[name]
            if value.shape != shape or value.dtype != np.float32 or not np.isfinite(value).all():
                raise ValueError(f"{name} deve ser float32 finito com forma {shape}")
            self.net.setInput(value, BLOBS[name])
        prediction, features = self.net.forward(["fc3", "relufc2"])
        if prediction.shape != (1, 2) or features.shape != (1, 128) or not np.isfinite(prediction).all() or not np.isfinite(features).all():
            raise ValueError("Saídas incompatíveis ou não finitas do modelo")
        return prediction, features


def infer(directory, inputs):
    return Model(directory).predict(inputs)


def inspect_video(source, destination, rotation, mirrored):
    """Write an atomic diagnostic record for each decoded frame."""
    if source.resolve() == destination.resolve():
        raise ValueError("A saída não pode substituir o vídeo de entrada")
    fd, temporary = tempfile.mkstemp(dir=destination.parent, prefix=".video-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            for image, timing in camera_frames(source, rotation, mirrored):
                record = {**timing, "width": image.shape[1], "height": image.shape[0],
                          "stimulus_time_ms": None, "prediction_cm": None,
                          "valid": False, "reason": "inferência não implementada",
                          "stimulus_time_reason": "sincronização não comprovada"}
                output.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("download", "smoke", "infer"):
        command = sub.add_parser(name)
        command.add_argument("--models", type=Path, required=True)
        if name == "infer":
            command.add_argument("--input", type=Path, required=True, help="NPZ com face, left, right e grid já pré-processados")
    video = sub.add_parser("inspect-video", help="Decodifica quadros e registra PTS, sem inferência")
    video.add_argument("--video", type=Path, required=True)
    video.add_argument("--output", type=Path, required=True)
    video.add_argument("--rotation", type=int, choices=(0, 90, 180, 270), required=True)
    video.add_argument("--mirrored", action="store_true")
    sub.add_parser("config-schema", help="JSON Schema da configuração v1")
    prepare = sub.add_parser("prepare", help="Gera configuração a partir da coleta instrumentada")
    prepare.add_argument("--events", type=Path, required=True)
    prepare.add_argument("--settings", type=Path, required=True)
    prepare.add_argument("--demo", action="store_true", help="Parâmetros aproximados para demonstração")
    detector = sub.add_parser("download-detector")
    detector.add_argument("--models", type=Path, required=True)
    process = sub.add_parser("process")
    process.add_argument("--models", type=Path, required=True)
    process.add_argument("--video", type=Path, required=True)
    process.add_argument("--events", type=Path, required=True)
    process.add_argument("--config", type=Path, required=True)
    process.add_argument("--output", type=Path, required=True)
    process.add_argument("--run-id")
    process.add_argument("--session-id")
    process.add_argument("--progress", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            from collection import prepare_collection
            print(json.dumps(prepare_collection(json.loads(args.events.read_text(encoding="utf-8")),
                json.loads(args.settings.read_text(encoding="utf-8")), demonstration=args.demo), ensure_ascii=False, allow_nan=False))
            return
        if args.command == "config-schema":
            from config import ProcessingConfig
            print(json.dumps(ProcessingConfig.model_json_schema(), ensure_ascii=False, indent=2))
            return
        if args.command == "download-detector":
            from preprocess import LANDMARKER_URL, LANDMARKER_SHA256
            args.models.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(dir=args.models)
            try:
                with os.fdopen(fd, "wb") as output, urllib.request.urlopen(LANDMARKER_URL, timeout=120) as response:
                    output.write(response.read())
                if digest(Path(temporary)) != LANDMARKER_SHA256:
                    raise ValueError("SHA-256 do detector incompatível")
                os.chmod(temporary, 0o644)
                os.replace(temporary, args.models / "face_landmarker.task")
            finally:
                Path(temporary).unlink(missing_ok=True)
            return
        if args.command == "process":
            from pipeline import process_session
            process_session(args.video, args.events, args.models, args.config, args.output, run_id=args.run_id, session_id=args.session_id, progress_path=args.progress)
            return
        if args.command == "inspect-video":
            inspect_video(args.video, args.output, args.rotation, args.mirrored)
            return
        if args.command == "download":
            download(args.models)
            print(f"Arquivos verificados: {args.models}")
            return
        if args.command == "smoke":
            inputs = {name: np.zeros(shape, dtype=np.float32) for name, shape in INPUTS.items()}
        else:
            with np.load(args.input, allow_pickle=False) as data:
                inputs = {name: data[name] for name in data.files}
        prediction, features = infer(args.models, inputs)
        print(json.dumps({"prediction_cm": prediction[0].tolist(), "features": features[0].tolist(), "model_revision": REVISION, "weights_sha256": FILES["itracker25x_iter_92000.caffemodel"][1]}, allow_nan=False))
    except (ValueError, TypeError, OSError, cv2.error, av.FFmpegError, KeyError) as error:
        parser.exit(1, f"Erro: {error}\n")


if __name__ == "__main__":
    main()
