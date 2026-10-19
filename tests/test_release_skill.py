from __future__ import annotations

import base64
import copy
import importlib.util
import json
import shutil
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

SKILL = Path(__file__).resolve().parents[1] / ".agents/skills/matlens-release"
SPEC = importlib.util.spec_from_file_location("release_checks", SKILL / "scripts/release_checks.py")
checks = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checks)


def test_wizard_is_required_starting_with_055():
    assert len(checks.asset_names("0.5.4")) == 3
    assert checks.asset_names("0.5.5")[-1] == "MatLens-Setup-0.5.5-x64.exe"


@pytest.fixture
def bundle(tmp_path):
    private = Ed25519PrivateKey.generate()
    public = base64.b64encode(private.public_key().public_bytes_raw()).decode()
    version = "0.1.0"
    dist = tmp_path / "dist"
    dist.mkdir()
    program = {"MatLens/MatLens.exe": b"main", "MatLens/MatLensUpdater.exe": b"updater",
               "MatLens/_internal/runtime.dll": b"runtime"}
    for filename, extra in [(checks.asset_names(version)[0], {"install.ps1": b"install",
                                                            "Install-MatLens.cmd": b"install"}),
                            (checks.asset_names(version)[1], {})]:
        with zipfile.ZipFile(dist / filename, "w") as archive:
            for name, content in (program | extra).items():
                archive.writestr(name, content)

    def signed(version=version, key=private):
        package = dist / checks.asset_names("0.1.0")[1]
        payload = json.dumps({"version": version, "channel": "stable", "platform": "win-x64",
                              "data_compatibility": 1, "size": package.stat().st_size,
                              "sha256": checks.digest(package), "notes": "測試發布",
                              "url": f"https://github.com/kobojp/MatLens/releases/download/v{version}/"
                                     f"MatLens-{version}-update-win-x64.zip"}).encode()
        return json.dumps({"payload": base64.b64encode(payload).decode(),
                           "signature": base64.b64encode(key.sign(payload)).decode()}).encode()

    (dist / "stable.json").write_bytes(signed())
    return dist, version, private, public, signed


def test_local_audit_accepts_matching_programs_and_signed_manifest(bundle, tmp_path):
    dist, version, _, public, _ = bundle
    report = checks.audit_local(dist, version, public, tmp_path / "evidence")
    assert report["ok"] and report["signature_verified"]
    assert {asset["name"] for asset in report["assets"]} == set(checks.asset_names(version))
    assert (tmp_path / "evidence/unpacked/MatLens/MatLens.exe").read_bytes() == b"main"


@pytest.mark.parametrize("extra", ["MatLens/data/matlens.db", "MatLens/../outside.txt",
                                   "MatLens/_internal/release.key"])
def test_local_audit_rejects_private_data_and_unsafe_paths(bundle, tmp_path, extra):
    dist, version, _, public, _ = bundle
    with zipfile.ZipFile(dist / checks.asset_names(version)[0], "a") as archive:
        archive.writestr(extra, b"must-not-ship")
    with pytest.raises(ValueError):
        checks.audit_local(dist, version, public, tmp_path / "evidence")
    assert not (tmp_path / "evidence/unpacked").exists()


def test_local_audit_rejects_wrong_signing_key(bundle, tmp_path):
    dist, version, _, _, _ = bundle
    wrong = base64.b64encode(Ed25519PrivateKey.generate().public_key().public_bytes_raw()).decode()
    with pytest.raises(ValueError, match="簽章"):
        checks.audit_local(dist, version, wrong, tmp_path / "evidence")


def test_key_discovery_handles_codex_redirect_and_explicit_mismatch(bundle, tmp_path):
    _, _, private, public, _ = bundle
    standard = tmp_path / "MatLens-Signing/release.key"
    redirected = (tmp_path / "Packages/OpenAI.Codex_test/LocalCache/Local"
                  / "MatLens-Signing/release.key")
    for path, key in [(standard, Ed25519PrivateKey.generate()), (redirected, private)]:
        path.parent.mkdir(parents=True)
        path.write_bytes(key.private_bytes_raw())
    assert checks.find_key(None, public, tmp_path) == redirected.resolve()
    assert redirected.read_bytes() == private.private_bytes_raw()
    with pytest.raises(ValueError, match="私鑰"):
        checks.find_key(str(standard), public, tmp_path)
    with pytest.raises(ValueError, match="worktree"):
        checks.find_key(str(redirected), public, tmp_path, (tmp_path,))


@pytest.mark.parametrize("change", ["commit", "digest", "asset", "published"])
def test_draft_gate_rejects_mismatched_remote_metadata(bundle, tmp_path, change):
    dist, version, _, public, _ = bundle
    assets = checks.audit_local(dist, version, public, tmp_path / "evidence")["assets"]
    commit = "a" * 40
    release = {"isDraft": True, "isPrerelease": False, "tagName": f"v{version}",
               "targetCommitish": commit, "assets": [
                   {"name": asset["name"], "size": asset["size"], "state": "uploaded",
                    "digest": f"sha256:{asset['sha256']}"} for asset in assets]}
    assert checks.check_draft(release, assets, version, commit)["ok"]
    invalid = copy.deepcopy(release)
    if change == "commit":
        invalid["targetCommitish"] = "b" * 40
    elif change == "digest":
        invalid["assets"][0]["digest"] = "sha256:" + "0" * 64
    elif change == "asset":
        invalid["assets"].pop()
    else:
        invalid["isDraft"] = False
    with pytest.raises(ValueError):
        checks.check_draft(invalid, assets, version, commit)


def test_public_verification_retries_only_valid_old_manifests(bundle, tmp_path, monkeypatch):
    dist, version, _, public, signed = bundle
    evidence = tmp_path / "public"
    evidence.mkdir()
    requests, pauses = [], []

    def download(url, target, limit):
        requests.append(url)
        if target.name.startswith("manifest-"):
            target.write_bytes(signed("0.0.9") if len(pauses) < 2 else signed())
        else:
            shutil.copyfile(dist / target.name, target)

    class Service:
        def __init__(self, path):
            pass

        def check(self):
            pass

        def status(self):
            return {"phase": "current", "version": version}

    monkeypatch.setattr(checks, "download", download)
    monkeypatch.setattr(checks.time, "sleep", pauses.append)
    monkeypatch.setattr(checks, "UpdateService", Service)
    report = checks.check_public(dist, version, public, evidence)
    assert report["ok"] and report["updater_check_verified"]
    assert pauses == [10, 10]
    assert all(url.startswith(checks.LATEST) and "?" not in url for url in requests)


def test_public_verification_does_not_retry_bad_signatures(bundle, tmp_path, monkeypatch):
    dist, version, _, public, signed = bundle
    evidence = tmp_path / "public"
    evidence.mkdir()
    calls = []

    def bad_signature(url, target, limit):
        calls.append(url)
        target.write_bytes(signed("0.0.9", Ed25519PrivateKey.generate()))

    monkeypatch.setattr(checks, "download", bad_signature)
    monkeypatch.setattr(checks.time, "sleep", lambda delay: pytest.fail("不應重試錯誤簽章"))
    with pytest.raises(ValueError, match="簽章"):
        checks.check_public(dist, version, public, evidence)
    assert len(calls) == 1
