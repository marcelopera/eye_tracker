"""Pinned model assets and first-start preparation, using only the standard library."""
import argparse
import hashlib
import os
from pathlib import Path
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen

REVISION = "e4af90da3c4c9068fbce433fa648d1f9bc7a394b"
BASE = f"https://raw.githubusercontent.com/CSAILVision/GazeCapture/{REVISION}/models"
FILES = {
    "itracker_deploy.prototxt": ("itracker_deploy.prototxt", "93a984a55829f07813859a068d9bf30ec8b3161d7121f715a9a9124b34cfdb76"),
    "itracker25x_iter_92000.caffemodel": ("snapshots/itracker25x_iter_92000.caffemodel", "d748042ebd402a4b6418cdff44a6e64f9bca1256fd3761f7ddc68fd5519ef98a"),
    "mean_face_224.mat": ("mean_images/mean_face_224.mat", "43dccf2f655259b23d3b2cd20907f5d7479e175215caba6bb310d3a4c3fc4756"),
    "mean_left_224.mat": ("mean_images/mean_left_224.mat", "b502c0c7392cea761688625f2be8b0359fc9df74599ef744ce37b7dc68dcb470"),
    "mean_right_224.mat": ("mean_images/mean_right_224.mat", "15167a33bc553cf624869be2717129362ea2a3445ba26676927a6f63205e2ef0"),
}
LANDMARKER_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"
LANDMARKER_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
ASSETS = {name: (f"{BASE}/{remote}", sha256) for name, (remote, sha256) in FILES.items()}
ASSETS["face_landmarker.task"] = (LANDMARKER_URL, LANDMARKER_SHA256)


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def verify(directory, names=FILES):
    for name in names:
        path = directory / name
        if not path.is_file() or digest(path) != ASSETS[name][1]:
            raise ValueError(f"Arquivo ausente ou SHA-256 incompatível: {path}; execute download")


def fetch(directory, name):
    url, expected = ASSETS[name]
    fd, temporary = tempfile.mkstemp(dir=directory, prefix=".download-")
    try:
        with os.fdopen(fd, "wb") as output, urlopen(url, timeout=120) as response:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        if digest(Path(temporary)) != expected:
            raise ValueError(f"SHA-256 incompatível para {name}; arquivo não publicado")
        os.chmod(temporary, 0o644)
        os.replace(temporary, directory / name)
    finally:
        Path(temporary).unlink(missing_ok=True)


def download(directory, names=FILES):
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        destination = directory / name
        if destination.is_file() and digest(destination) == ASSETS[name][1]:
            print(f"Modelo verificado no cache: {name}", flush=True)
            continue
        print(f"Baixando modelo: {name}", flush=True)
        for attempt in range(3):
            try:
                fetch(directory, name)
                break
            except (URLError, TimeoutError, ConnectionError):
                if attempt == 2:
                    raise
                print(f"Falha de conexão; nova tentativa para {name}", flush=True)
                time.sleep(2 ** attempt)
        print(f"Modelo baixado e verificado: {name}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", type=Path, required=True)
    args = parser.parse_args()
    try:
        download(args.models, ASSETS)
        verify(args.models, ASSETS)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Falha ao preparar modelos: {error}. Confira a conexão e execute docker compose up novamente.\n")
    print("Todos os modelos estão prontos para processamento.", flush=True)


if __name__ == "__main__":
    main()
