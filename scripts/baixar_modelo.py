#!/usr/bin/env python3
"""Baixa um modelo escolhido pelo pesquisador e verifica o SHA-256 conhecido."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlparse
from urllib.request import urlopen


def download(url, expected, destination):
    if urlparse(url).scheme != 'https':
        raise ValueError('A URL deve usar HTTPS.')
    if not re.fullmatch(r'[a-fA-F0-9]{64}', expected):
        raise ValueError('Informe um SHA-256 com 64 caracteres hexadecimais.')
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(f'O destino já existe: {destination}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with urlopen(url, timeout=60) as response:
            if urlparse(response.geturl()).scheme != 'https':
                raise ValueError('O redirecionamento deve permanecer em HTTPS.')
            with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as output:
                temp = Path(output.name)
                digest = hashlib.sha256()
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
        if digest.hexdigest() != expected.lower():
            raise ValueError('SHA-256 não confere; download descartado.')
        # Link atômico não sobrescreve um arquivo existente.
        os.link(temp, destination)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url', help='URL HTTPS oficial do modelo selecionado')
    parser.add_argument('sha256', help='SHA-256 obtido independentemente de fonte confiável')
    parser.add_argument('destino', help='arquivo local; por exemplo modelos/modelo.task')
    args = parser.parse_args()
    try:
        download(args.url, args.sha256, args.destino)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'Erro: {exc}\n')
    print(f'Modelo verificado: {args.destino}')


if __name__ == '__main__':
    main()
