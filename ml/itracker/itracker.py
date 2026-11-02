"""Controlled-input inference with the published frozen iTracker Caffe model."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import urllib.request

import cv2
import numpy as np

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
            continue
        fd, temporary = tempfile.mkstemp(dir=directory, prefix=".download-")
        try:
            with os.fdopen(fd, "wb") as output, urllib.request.urlopen(f"{BASE}/{remote}", timeout=120) as response:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            if digest(Path(temporary)) != expected:
                raise ValueError(f"SHA-256 incompatível para {name}")
            os.replace(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)


def infer(directory, inputs):
    verify(directory, ("itracker_deploy.prototxt", "itracker25x_iter_92000.caffemodel"))
    if set(inputs) != set(INPUTS):
        raise ValueError(f"Entradas esperadas: {', '.join(INPUTS)}")
    for name, shape in INPUTS.items():
        value = inputs[name]
        if value.shape != shape or value.dtype != np.float32 or not np.isfinite(value).all():
            raise ValueError(f"{name} deve ser float32 finito com forma {shape}")
    net = cv2.dnn.readNetFromCaffe(str(directory / "itracker_deploy.prototxt"), str(directory / "itracker25x_iter_92000.caffemodel"))
    for name, blob in BLOBS.items():
        net.setInput(inputs[name], blob)
    prediction, features = net.forward(["fc3", "relufc2"])
    if prediction.shape != (1, 2) or features.shape != (1, 128) or not np.isfinite(prediction).all() or not np.isfinite(features).all():
        raise ValueError("Saídas incompatíveis ou não finitas do modelo")
    return prediction, features


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("download", "smoke", "infer"):
        command = sub.add_parser(name)
        command.add_argument("--models", type=Path, required=True)
        if name == "infer":
            command.add_argument("--input", type=Path, required=True, help="NPZ com face, left, right e grid já pré-processados")
    args = parser.parse_args()
    try:
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
    except (ValueError, OSError, cv2.error, KeyError) as error:
        parser.exit(1, f"Erro: {error}\n")


if __name__ == "__main__":
    main()
