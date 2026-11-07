"""Server für die Desktop-App: freier Port, Startmeldung, Ende mit dem Standardeingang."""

import json
import os
import subprocess
import sys
import urllib.request

from procurator import desktop


def start(tmp_path):
    env = {**os.environ, "PC_CONFIG": str(tmp_path / "c.toml"), "PC_JOURNAL": str(tmp_path / "j.db"),
           "PC_INDEX": str(tmp_path / "i.db")}
    proc = subprocess.Popen([sys.executable, "-m", "procurator.desktop"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, text=True)
    line = proc.stdout.readline().strip()
    return proc, line


def test_prints_ready_line_serves_the_api_and_stops_when_stdin_closes(tmp_path):
    proc, line = start(tmp_path)
    try:
        assert line.startswith(f"{desktop.READY} http://127.0.0.1:")
        url = line.split()[1]
        with urllib.request.urlopen(f"{url}/api/operations", timeout=10) as r:
            assert r.status == 200 and json.load(r)
        proc.stdin.close()  # die Hülle ist weg
        assert proc.wait(timeout=15) == 0
    finally:
        if proc.poll() is None:
            proc.kill()


def test_two_servers_get_different_ports(tmp_path):
    a, line_a = start(tmp_path)
    b, line_b = start(tmp_path)
    try:
        assert line_a != line_b
    finally:
        for p in (a, b):
            p.stdin.close()
            p.wait(timeout=15)


def test_server_listens_only_on_the_local_interface():
    sock = desktop.bind()
    try:
        assert sock.getsockname()[0] == "127.0.0.1" and sock.getsockname()[1] > 0
    finally:
        sock.close()


def test_static_dir_is_the_built_ui_when_not_frozen():
    assert desktop.frozen_root() is None
    assert desktop.static_dir().parts[-2:] == ("web", "dist")
