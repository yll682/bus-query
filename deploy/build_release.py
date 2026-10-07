import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parent.parent
RUNTIME_FILES = (
    "bus_api_client.py", "requirements-runtime.txt",
    "掌上公交城市配置.json", "掌上公交公开城市列表.json",
)


def build(output, version):
    if not (ROOT / "web/dist/index.html").is_file():
        raise FileNotFoundError("请执行 npm ci 和 npm run build 构建网页")
    files = [ROOT / name for name in RUNTIME_FILES]
    files += sorted((ROOT / "website").glob("*.py"))
    files += sorted(path for path in (ROOT / "web/dist").rglob("*") if path.is_file())
    payload = {path.relative_to(ROOT).as_posix(): path.read_bytes() for path in files}
    manifest = {"application": "yll682/bus-query", "version": version,
                "files": {name: hashlib.sha256(body).hexdigest() for name, body in payload.items()}}
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "x", compression=ZIP_DEFLATED) as archive:
        for name, body in payload.items():
            archive.writestr(name, body)
        archive.writestr("release.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    with ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError("发布文件 ZIP 校验失败")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(json.dumps({"archive": str(output), "files": len(payload), "sha256": digest}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    build(args.output, args.version)
