import argparse
import fcntl
import hashlib
import json
import os
import pwd
import re
import shutil
import socket
import stat
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4
from zipfile import ZipFile


APP = Path("/opt/bus-query")
UNIT = Path("/etc/systemd/system/bus-query.service")
MARKER = "yll682/bus-query"
USER = "bus-query"
ROOT_FILES = {"bus_api_client.py", "requirements-runtime.txt", "掌上公交城市配置.json", "掌上公交公开城市列表.json"}


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def validate_paths():
    if APP.resolve() != APP or UNIT.parent.resolve() != UNIT.parent or UNIT.is_symlink():
        raise ValueError("安装目录和服务文件路径不允许使用符号链接")
    if APP.exists():
        marker = APP / "managed.json"
        if marker.is_symlink() or json.loads(marker.read_text())["application"] != MARKER:
            raise ValueError("安装目录不属于本项目，操作已终止")
    if UNIT.exists() and (not APP.exists() or not UNIT.read_text().startswith("# Managed by " + MARKER + "\n")):
        raise ValueError("服务文件不属于本项目，操作已终止")


def load_config():
    config = json.loads((APP / "config.json").read_text())
    if type(config["port"]) is not int or not 1024 <= config["port"] <= 65535:
        raise ValueError("监听端口无效")
    if re.fullmatch(r"[A-Za-z0-9_-]{1,100}", config["deviceId"]) is None:
        raise ValueError("设备标识无效")
    return config


def available_port(port):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", port))


def ensure_user():
    marker = json.loads((APP / "managed.json").read_text())
    accounts = {entry.pw_name: entry for entry in pwd.getpwall()}
    if USER in accounts:
        account = accounts[USER]
        if marker.get("userUid") != account.pw_uid or account.pw_dir != "/nonexistent" or account.pw_shell != "/usr/sbin/nologin":
            raise ValueError("系统用户不属于本项目，操作已终止")
        return
    if "userUid" in marker:
        raise ValueError("本项目系统用户缺失，请检查系统用户配置")
    run("useradd", "--system", "--user-group", "--no-create-home", "--home-dir", "/nonexistent", "--shell", "/usr/sbin/nologin", USER)
    marker["userUid"] = pwd.getpwnam(USER).pw_uid
    (APP / "managed.json").write_text(json.dumps(marker))


def wait_ready(port):
    # 服务启动需要短暂时间；仅在连接尚未建立时继续等待。
    for _ in range(30):
        if subprocess.run(["systemctl", "is-failed", "--quiet", "bus-query"]).returncode == 0:
            raise RuntimeError("服务启动失败，请查看 journalctl -u bus-query")
        try:
            with urlopen(f"http://127.0.0.1:{port}/ready", timeout=2) as response:
                if json.load(response)["status"] != "ok":
                    raise ValueError("服务健康检查失败")
                return
        except HTTPError:
            raise
        except URLError:
            time.sleep(1)
    raise TimeoutError("服务未能通过健康检查，请查看 journalctl -u bus-query")


def download_release():
    request = Request("https://api.github.com/repos/yll682/bus-query/releases/latest",
                      headers={"Accept": "application/vnd.github+json", "User-Agent": "bus-query-installer"})
    with urlopen(request, timeout=60) as response:
        release = json.load(response)
    asset = next(item for item in release["assets"] if item["name"] == "bus-query.zip")
    digest = asset["digest"]
    if re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
        raise ValueError("GitHub 发布文件未提供有效的 SHA256")
    if not asset["browser_download_url"].startswith("https://github.com/yll682/bus-query/releases/download/"):
        raise ValueError("发布文件下载地址无效")
    folder = APP / "downloads"
    folder.mkdir(exist_ok=True)
    target = folder / (uuid4().hex + ".zip")
    with urlopen(Request(asset["browser_download_url"], headers={"User-Agent": "bus-query-installer"}), timeout=120) as response:
        with target.open("xb") as output:
            shutil.copyfileobj(response, output)
    if hashlib.sha256(target.read_bytes()).hexdigest() != digest.removeprefix("sha256:"):
        raise ValueError("发布文件 SHA256 校验失败")
    return target


def unpack(archive_path):
    with ZipFile(archive_path) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if len(names) != len(set(names)) or sum(entry.file_size for entry in entries) > 64 * 1024 * 1024:
            raise ValueError("发布文件存在重复名称或超过大小限制")
        manifest = json.loads(archive.read("release.json"))
        if manifest["application"] != MARKER or re.fullmatch(r"[A-Za-z0-9._-]{1,100}", manifest["version"]) is None:
            raise ValueError("发布文件项目标识或版本无效")
        if set(names) != set(manifest["files"]) | {"release.json"}:
            raise ValueError("发布文件与清单不一致")
        required = ROOT_FILES | {"website/app.py", "website/service.py", "website/__init__.py", "web/dist/index.html"}
        if not required <= set(names):
            raise ValueError("发布文件缺少运行所需文件")
        bodies = {}
        for entry in entries:
            name = entry.filename
            path = PurePosixPath(name)
            mode = entry.external_attr >> 16
            if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name or stat.S_ISLNK(mode) or entry.is_dir():
                raise ValueError("发布文件路径或文件类型无效")
            allowed = name in ROOT_FILES or name == "release.json" or (len(path.parts) == 2 and path.parts[0] == "website" and path.suffix == ".py") or name.startswith("web/dist/")
            if not allowed:
                raise ValueError("发布文件包含未允许的文件")
            body = archive.read(entry)
            if name != "release.json" and hashlib.sha256(body).hexdigest() != manifest["files"][name]:
                raise ValueError("发布文件内容校验失败")
            bodies[name] = body
    target = APP / "releases" / (manifest["version"] + "-" + uuid4().hex)
    target.mkdir(parents=True, mode=0o755)
    for name, body in bodies.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        path.chmod(0o644)
    return target


def install(args):
    initial = not APP.exists()
    if initial:
        if any(entry.pw_name == USER for entry in pwd.getpwall()):
            raise ValueError("同名系统用户已存在，操作已终止")
        port = args.port or 8765
        if not 1024 <= port <= 65535:
            raise ValueError("端口范围为 1024 至 65535")
        available_port(port)
        APP.mkdir(mode=0o755)
        (APP / "managed.json").write_text(json.dumps({"application": MARKER}))
        config = {"port": port, "deviceId": "bus-web-" + uuid4().hex}
        (APP / "config.json").write_text(json.dumps(config))
        (APP / "config.json").chmod(0o600)
    else:
        config = load_config()
        if args.port is not None and args.port != config["port"]:
            raise ValueError("更新保留现有端口，请通过 config.json 修改配置")
    archive = args.archive.resolve() if args.archive else download_release()
    target = unpack(archive)
    run(sys.executable, "-m", "venv", str(target / ".venv"))
    python = str(target / ".venv/bin/python")
    run(python, "-m", "pip", "install", "--disable-pip-version-check", "-r", str(target / "requirements-runtime.txt"))
    run(python, "-c", "from website.app import app; assert app.title", cwd=target, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    ensure_user()
    unit = args.unit.read_text()
    if not unit.startswith("# Managed by " + MARKER + "\n"):
        raise ValueError("服务模板无效")
    UNIT.write_text(unit)
    (APP / ".env").write_text(f"BUS_PORT={config['port']}\nBUS_DEVICE_ID={config['deviceId']}\n")
    (APP / ".env").chmod(0o600)
    link = APP / ("current-" + uuid4().hex)
    link.symlink_to(target, target_is_directory=True)
    os.replace(link, APP / "current")
    run("systemctl", "daemon-reload")
    run("systemctl", "enable", "bus-query")
    run("systemctl", "restart", "bus-query")
    wait_ready(config["port"])
    shutil.copyfile(Path(__file__), APP / "installer.py")
    shutil.copyfile(args.unit, APP / "bus-query.service")
    if args.archive is None:
        archive.unlink()
    print(f"安装 / 更新完成：http://127.0.0.1:{config['port']}\n配置文件：{APP / 'config.json'}\n日志：journalctl -u bus-query -f")


def restart():
    config = load_config()
    run("systemctl", "restart", "bus-query")
    wait_ready(config["port"])
    print("服务已重启")


def status():
    if not APP.exists():
        print("尚未安装")
        return
    config = load_config()
    active = subprocess.run(["systemctl", "is-active", "bus-query"], capture_output=True, text=True)
    print(f"服务状态：{active.stdout.strip()}\n本机地址：http://127.0.0.1:{config['port']}")


def uninstall(confirmed):
    if not APP.exists():
        print("尚未安装")
        return
    if not confirmed and input("将删除本项目服务、安装文件和配置。输入 yes 确认卸载：") != "yes":
        print("已取消")
        return
    # 删除操作仅接受固定目录和本项目标识，并拒绝目录内部的挂载点。
    validate_paths()
    for path in APP.rglob("*"):
        if not path.is_symlink() and path.is_mount():
            raise ValueError("安装目录包含挂载点，操作已终止")
    marker = json.loads((APP / "managed.json").read_text())
    account = next((entry for entry in pwd.getpwall() if entry.pw_name == USER), None)
    if account is not None and (marker.get("userUid") != account.pw_uid or account.pw_dir != "/nonexistent" or account.pw_shell != "/usr/sbin/nologin"):
        raise ValueError("系统用户不属于本项目，操作已终止")
    if UNIT.exists():
        run("systemctl", "stop", "bus-query")
        run("systemctl", "disable", "bus-query")
        UNIT.unlink()
        run("systemctl", "daemon-reload")
    if account is not None:
        run("userdel", USER)
    shutil.rmtree(APP)
    print("卸载完成。浏览器中的收藏仍保留。")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["install", "restart", "status", "uninstall"])
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--unit", type=Path, default=Path(__file__).with_name("bus-query.service"))
    parser.add_argument("--port", type=int)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    if os.geteuid() != 0 or sys.version_info < (3, 10) or not Path("/run/systemd/system").is_dir():
        raise RuntimeError("需要 root 权限、Python 3.10 及以上版本和正在运行的 systemd")
    with Path("/run/lock/bus-query-installer.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        validate_paths()
        if args.action == "install":
            install(args)
        elif args.action == "restart":
            restart()
        elif args.action == "status":
            status()
        else:
            uninstall(args.yes)


if __name__ == "__main__":
    main()
