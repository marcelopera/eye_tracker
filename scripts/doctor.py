#!/usr/bin/env python3
"""Diagnóstico local sem modificar configurações ou regras de rede."""
import platform
import shutil
import socket
import subprocess
import sys


def run(*args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"  Indisponível: {exc}")
        return None


def main():
    print('Docker:')
    docker = run('docker', 'info', '--format', '{{.ServerVersion}}') if shutil.which('docker') else None
    docker_ok = docker is not None and docker.returncode == 0
    print('  Em execução: ' + docker.stdout.strip() if docker_ok else '  Não disponível ou daemon parado.')
    print('IP local:')
    try:
        addresses = sorted({item[4][0] for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
                            if not item[4][0].startswith('127.')})
    except OSError:
        addresses = []
    print('  ' + (', '.join(addresses) if addresses else 'Não identificado; confira ipconfig/ip addr.'))
    print('Portas: nenhuma configurada; verifique disponibilidade quando os serviços forem definidos.')
    print('Firewall: verificação manual necessária para as portas e perfil de rede escolhidos.')
    print('ADB:')
    adb = run('adb', 'devices', '-l') if shutil.which('adb') else None
    print('  ' + adb.stdout.strip().replace('\n', '\n  ') if adb and adb.returncode == 0 else '  Indisponível ou erro ao consultar dispositivos.')
    print(f'Sistema: {platform.system()} {platform.release()}')
    return 0 if docker_ok else 1


if __name__ == '__main__':
    sys.exit(main())
