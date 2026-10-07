import argparse
import json
import os
import pwd
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent.parent
APP = Path("/opt/bus-query")
UNIT = Path("/etc/systemd/system/bus-query.service")
PORT = 18765


def command(*args):
    return subprocess.run(["sudo", sys.executable, str(ROOT / "deploy/installer.py"), *args], check=True)


def get(path):
    with urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=20) as response:
        return response.read(), response.headers


def lifecycle(archive):
    if APP.exists() or UNIT.exists() or any(entry.pw_name == "bus-query" for entry in pwd.getpwall()):
        raise ValueError("生命周期测试要求本机尚未安装 bus-query")
    sentinel = Path("/opt/bus-query-test-neighbor")
    subprocess.run(["sudo", "mkdir", str(sentinel)], check=True)
    try:
        command("status")
        if archive is None:
            subprocess.run(["sudo", "bash", str(ROOT / "deploy.sh")], input=f"1\n{PORT}\n", text=True, check=True)
        else:
            command("install", "--archive", str(archive), "--port", str(PORT))
        config = subprocess.check_output(["sudo", "cat", str(APP / "config.json")])
        current = (APP / "current").resolve()
        assert json.loads(config)["port"] == PORT
        assert json.loads(get("/ready")[0])["status"] == "ok"
        body, headers = get("/")
        assert 'id="app"' in body.decode()
        assert headers["Permissions-Policy"] == "geolocation=(self)"
        manifest, headers = get("/manifest.webmanifest")
        pwa = json.loads(manifest)
        assert pwa["display"] == "standalone" and headers["Cache-Control"] == "no-cache"
        for icon in pwa["icons"]:
            assert get(icon["src"])[0]
        worker, headers = get("/sw.js")
        assert worker and headers["Cache-Control"] == "no-cache"
        assert "javascript" in headers["Content-Type"]
        assert len(json.loads(get("/api/cities")[0])) == 575
        if archive is None:
            subprocess.run(["sudo", "bash", str(ROOT / "deploy.sh")], input="1\n", text=True, check=True)
        else:
            command("install", "--archive", str(archive))
        assert subprocess.check_output(["sudo", "cat", str(APP / "config.json")]) == config
        assert (APP / "current").resolve() != current
        subprocess.run(["sudo", "bash", str(ROOT / "deploy.sh")], input="2\n", text=True, check=True)
        assert json.loads(get("/health")[0])["status"] == "ok"
        subprocess.run(["systemctl", "is-enabled", "--quiet", "bus-query"], check=True)
        assert subprocess.check_output(["systemctl", "show", "bus-query", "--property", "User", "--value"], text=True).strip() == "bus-query"
        assert "--no-access-log" in UNIT.read_text()
        subprocess.run(["sudo", "bash", str(ROOT / "deploy.sh")], input="3\n", text=True, check=True)
        canceled = subprocess.run(["sudo", "bash", str(ROOT / "deploy.sh")], input="4\nno\n", text=True, check=True)
        assert canceled.returncode == 0 and APP.exists()
        subprocess.run(["sudo", "bash", str(ROOT / "deploy.sh")], input="4\nyes\n", text=True, check=True)
        assert not APP.exists() and not UNIT.exists() and sentinel.is_dir()
        assert not any(entry.pw_name == "bus-query" for entry in pwd.getpwall())
        command("uninstall", "--yes")
        print("安装、更新、配置保留、重启、状态、取消卸载、完整卸载、重复卸载及相邻目录保护全部通过")
    finally:
        if APP.exists():
            command("uninstall", "--yes")
        subprocess.run(["sudo", "rmdir", str(sentinel)], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--archive", type=Path)
    source.add_argument("--public", action="store_true")
    args = parser.parse_args()
    if os.name != "posix":
        raise RuntimeError("生命周期测试需要 Linux 与 systemd")
    lifecycle(args.archive.resolve() if args.archive else None)
