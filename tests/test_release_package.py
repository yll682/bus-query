import hashlib
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parent.parent


def test_real_release_package():
    output = ROOT / "work/release-tests" / (uuid4().hex + ".zip")
    subprocess.run([sys.executable, str(ROOT / "deploy/build_release.py"), "--output", str(output), "--version", "test-build"], check=True)
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        manifest = json.loads(archive.read("release.json"))
        assert manifest["application"] == "yll682/bus-query"
        assert set(archive.namelist()) == set(manifest["files"]) | {"release.json"}
        for name, digest in manifest["files"].items():
            body = archive.read(name)
            assert hashlib.sha256(body).hexdigest() == digest
            assert body == (ROOT / name).read_bytes()
        assert 'id="app"' in archive.read("web/dist/index.html").decode()
        assert "requests==2.31.0" in archive.read("requirements-runtime.txt").decode()
        assert any(name.startswith("web/dist/assets/") and name.endswith(".js") for name in archive.namelist())
        assert len(json.loads(archive.read("掌上公交城市配置.json"))) == 500
        assert all(not name.endswith((".apk", ".db", ".log")) for name in archive.namelist())
        assert all(not name.startswith(("work/", "tools/", "另一个AI/", "web/node_modules/", "tests/")) for name in archive.namelist())
