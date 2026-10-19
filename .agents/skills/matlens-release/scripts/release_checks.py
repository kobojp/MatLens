"""Read-only release checks; writes evidence only to this repository's ignored build/."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from desktop.update_core import (  # noqa: E402
    download,
    extract_package,
    verify_manifest,
    verify_package,
    version_key,
)
from desktop.updates import UpdateService  # noqa: E402
from desktop.version import VERSION  # noqa: E402

REPO = "kobojp/MatLens"
LATEST = f"https://github.com/{REPO}/releases/latest/download/"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def asset_info(path: Path) -> dict:
    return {"name": path.name, "size": path.stat().st_size, "sha256": digest(path)}


def asset_names(version: str) -> list[str]:
    version_key(version)
    require("-" not in version, "本 skill 的正式發布檢查不接受測試版。")
    names = [f"MatLens-{version}-win-x64.zip", f"MatLens-{version}-update-win-x64.zip",
             "stable.json"]
    if version_key(version) >= version_key("0.5.5"):
        names.append(f"MatLens-Setup-{version}-x64.exe")
    return names


def check_versions() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
    lock = tomllib.loads((ROOT / "uv.lock").read_text("utf-8"))
    versions = [item["version"] for item in lock["package"] if item["name"] == "matlens"]
    installer = (ROOT / "packaging/MatLens.iss").read_text("utf-8").splitlines()
    require(project["project"]["version"] == VERSION and versions == [VERSION],
            "pyproject.toml／uv.lock 與 desktop/version.py 版本不一致。")
    require(f"AppVersion={VERSION}" in installer
            and f"OutputBaseFilename=MatLens-Setup-{VERSION}-x64" in installer,
            "Inno Setup 版本或輸出檔名不一致。")


def find_key(
    explicit: str | None, public_key: str, local_appdata: Path,
    repository_roots: tuple[Path, ...] = (),
) -> Path:
    """Only inspect known signing locations; never print private bytes or create keys."""
    if explicit:
        candidates = [Path(explicit).expanduser()]
    else:
        candidates = [local_appdata / "MatLens-Signing/release.key"]
        candidates.extend(sorted((local_appdata / "Packages").glob(
            "OpenAI.Codex_*/LocalCache/Local/MatLens-Signing/release.key"
        )))
    matches = []
    for path in candidates:
        if not path.is_file():
            continue
        path = path.resolve()
        require(all(root.resolve() not in path.parents for root in (ROOT, *repository_roots)),
                "簽章私鑰必須存放在 repository 之外，包含其他 worktree。")
        try:
            key = Ed25519PrivateKey.from_private_bytes(path.read_bytes())
            actual = base64.b64encode(key.public_key().public_bytes_raw()).decode()
        except ValueError:
            actual = ""
        if actual == public_key:
            matches.append(path)
    if matches and matches[0] == candidates[0].resolve():
        return matches[0]
    require(len(matches) == 1, "找不到唯一且符合內建公鑰的私鑰，請提供既有私鑰路徑。")
    return matches[0]


def zip_contents(path: Path, version: str, update: bool) -> dict:
    """Compare shipped program bytes while excluding data, credentials and unsafe paths."""
    roots = {"MatLens"} if update else {"MatLens", "install.ps1", "Install-MatLens.cmd"}
    programs = {}
    seen = set()
    actual_roots = set()
    forbidden_suffixes = {".db", ".sqlite", ".sqlite3", ".key", ".pem", ".pfx", ".p12"}
    forbidden_parts = {"data", "photos", "node_modules", ".git", ".venv"}
    with zipfile.ZipFile(path) as archive:
        for item in archive.infolist():
            name = item.filename.replace("\\", "/").rstrip("/")
            parts = name.split("/")
            require(all(part not in {"", ".", ".."} for part in parts), f"ZIP 路徑不安全：{name}")
            require(name.casefold() not in seen, f"ZIP 有重複路徑：{name}")
            require(not stat.S_ISLNK(item.external_attr >> 16), f"ZIP 含連結：{name}")
            seen.add(name.casefold())
            actual_roots.add(parts[0])
            require(parts[0] in roots, f"ZIP 頂層檔案不符合發佈格式：{name}")
            is_directory = item.is_dir() or item.filename.endswith("\\")
            if parts[0] != "MatLens":
                require(len(parts) == 1 and not is_directory, f"安裝腳本必須是檔案：{name}")
            require(not (set(part.lower() for part in parts) & forbidden_parts)
                    and Path(name).suffix.lower() not in forbidden_suffixes
                    and not any(part.lower().startswith(".env") for part in parts),
                    f"ZIP 含資料或敏感檔案：{name}")
            if len(parts) > 1:
                require(parts[1] in {"MatLens.exe", "MatLensUpdater.exe", "_internal"},
                        f"ZIP 含非程式檔案：{name}")
            if not is_directory and parts[0] == "MatLens":
                with archive.open(item) as handle:
                    program_digest = hashlib.file_digest(handle, "sha256").hexdigest()
                    programs[name] = (item.file_size, program_digest)
    require(actual_roots == roots, "ZIP 缺少程式目錄或完整安裝腳本。")
    require({"MatLens/MatLens.exe", "MatLens/MatLensUpdater.exe"} <= programs.keys(),
            f"{version} ZIP 缺少主程式或更新器。")
    return programs


def audit_local(dist: Path, version: str, public_key: str, evidence: Path) -> dict:
    names = asset_names(version)
    manifest = verify_manifest((dist / "stable.json").read_bytes(), public_key, "stable")
    require(manifest["version"] == version, "本機 manifest 版本不一致。")
    expected_url = f"https://github.com/{REPO}/releases/download/v{version}/{names[1]}"
    require(manifest["url"] == expected_url, "本機 manifest 的更新 URL 不一致。")
    verify_package(dist / names[1], manifest)
    full = zip_contents(dist / names[0], version, update=False)
    update = zip_contents(dist / names[1], version, update=True)
    require(full == update, "完整安裝包與更新包的程式內容不同。")
    extract_package(dist / names[1], evidence / "unpacked")
    if len(names) == 4:
        require((dist / names[3]).read_bytes()[:2] == b"MZ", "安裝精靈不是 Windows EXE。")
    return {"ok": True, "version": version, "signature_verified": True,
            "assets": [asset_info(dist / name) for name in names]}


def check_draft(release: dict, assets: list[dict], version: str, commit: str) -> dict:
    require(len(commit) == 40 and all(char in "0123456789abcdef" for char in commit),
            "草稿檢查需要完整的 commit SHA。")
    require(release["isDraft"] and not release["isPrerelease"], "必須是尚未公開的正式版草稿。")
    require(release["tagName"] == f"v{version}" and release["targetCommitish"] == commit,
            "草稿 tag 或目標 commit 不一致。")
    remote = {asset["name"]: asset for asset in release["assets"]}
    require(len(remote) == len(release["assets"])
            and set(remote) == {asset["name"] for asset in assets}, "草稿附件清單不一致。")
    for local in assets:
        asset = remote[local["name"]]
        require(asset["size"] == local["size"] and asset["state"] == "uploaded"
                and asset["digest"] == f"sha256:{local['sha256']}",
                f"草稿附件大小、狀態或 SHA-256 不一致：{local['name']}")
    return {"ok": True, "version": version, "commit": commit, "draft_verified": True}


def check_public(dist: Path, version: str, public_key: str, evidence: Path) -> dict:
    names = asset_names(version)
    for attempt in range(6):
        target = evidence / f"manifest-{attempt}.json"
        download(LATEST + "stable.json", target, 100000)
        manifest = verify_manifest(target.read_bytes(), public_key, "stable")
        if manifest["version"] == version:
            break
        require(version_key(manifest["version"]) < version_key(version),
                "公開最新版高於預期版本，停止驗證以免操作錯誤版本。")
        require(attempt < 5, "latest 快取仍是舊版；保留報告，稍後再驗證，勿重新發佈。")
        print(f"latest 尚為 {manifest['version']}，10 秒後重新確認。", file=sys.stderr, flush=True)
        time.sleep(10)
    assets = []
    for name in names:
        path = evidence / name
        download(LATEST + name, path, (dist / name).stat().st_size)
        actual, expected = asset_info(path), asset_info(dist / name)
        require(actual == expected, f"公開附件與本機不同：{name}")
        assets.append(actual)
    published = verify_manifest((evidence / "stable.json").read_bytes(), public_key, "stable")
    require(published == manifest, "公開 manifest 在驗證途中改變。")
    verify_package(evidence / names[1], published)
    service = UpdateService(evidence / "service")
    service.check()
    deadline = time.monotonic() + 45
    while service.status()["phase"] == "checking" and time.monotonic() < deadline:
        time.sleep(0.2)
    state = service.status()
    require(state["phase"] == "current" and state.get("version") == version,
            "程式正常更新檢查尚未讀到目前版本。")
    return {"ok": True, "version": version, "signature_verified": True,
            "public_latest_download_verified": True, "updater_check_verified": True,
            "assets": assets}


def main() -> None:
    parser = argparse.ArgumentParser(description="MatLens 發佈檢查；不簽章、不修改 GitHub。")
    parser.add_argument("mode", choices=["key", "local", "draft", "public"])
    parser.add_argument("--key", help="既有私鑰路徑；也可用 MATLENS_SIGNING_KEY_PATH")
    parser.add_argument("--commit", help="草稿的精確目標 commit SHA")
    args = parser.parse_args()
    os.chdir(ROOT)
    source = json.loads((ROOT / "desktop/update-source.json").read_text("utf-8"))
    require(source["stable"] == LATEST + "stable.json", "正式更新來源不符專案規則。")
    if args.mode == "key":
        explicit = args.key or os.environ.get("MATLENS_SIGNING_KEY_PATH")
        worktrees = subprocess.run(["git", "worktree", "list", "--porcelain", "-z"],
                                   check=True, capture_output=True, text=True, encoding="utf-8")
        roots = tuple(Path(line.removeprefix("worktree "))
                      for line in worktrees.stdout.split("\0") if line.startswith("worktree "))
        key = find_key(explicit, source["public_key"], Path(os.environ["LOCALAPPDATA"]), roots)
        print(json.dumps({"path": str(key), "public_key_matches": True}, ensure_ascii=False))
        return
    check_versions()
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    evidence = Path(tempfile.mkdtemp(prefix=f"release-{VERSION}-{args.mode}-", dir=build))
    dist = ROOT / "dist"
    if args.mode in {"local", "draft"}:
        report = audit_local(dist, VERSION, source["public_key"], evidence)
        if args.mode == "draft":
            require(bool(args.commit), "draft 檢查必須提供 --commit 完整 SHA。")
            command = ["gh", "release", "view", f"v{VERSION}", "--repo", REPO, "--json",
                       "isDraft,isPrerelease,tagName,targetCommitish,assets"]
            release = json.loads(subprocess.run(command, check=True, capture_output=True,
                                                text=True, encoding="utf-8").stdout)
            report = check_draft(release, report["assets"], VERSION, args.commit)
    else:
        audit_local(dist, VERSION, source["public_key"], evidence)
        report = check_public(dist, VERSION, source["public_key"], evidence)
    report["evidence_dir"] = str(evidence)
    (evidence / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"發佈檢查失敗：{error}") from error
