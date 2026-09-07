"""Maintainer-only signing command; private key must live outside the repository."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from desktop.update_core import https_url, verify_manifest
from desktop.version import DATA_COMPATIBILITY, VERSION


def main():
    parser = argparse.ArgumentParser(description="建立 MatLens 已簽章更新資訊")
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--init-key", action="store_true")
    parser.add_argument("--package", type=Path)
    parser.add_argument("--url")
    parser.add_argument("--notes", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--version", default=VERSION)
    parser.add_argument("--channel", choices=["stable", "preview"], default="stable")
    args = parser.parse_args()
    if args.init_key:
        key = Ed25519PrivateKey.generate()
        with args.key.open("xb") as target:
            target.write(key.private_bytes_raw())
        print(base64.b64encode(key.public_key().public_bytes_raw()).decode())
        return
    if not all([args.package, args.url, args.notes, args.output]):
        parser.error("簽章需要 --package、--url、--notes、--output")
    key = Ed25519PrivateKey.from_private_bytes(args.key.read_bytes())
    with args.package.open("rb") as package:
        digest = hashlib.file_digest(package, "sha256").hexdigest()
    payload = json.dumps({
        "version": args.version, "channel": args.channel, "platform": "win-x64",
        "data_compatibility": DATA_COMPATIBILITY, "url": https_url(args.url),
        "size": args.package.stat().st_size, "sha256": digest,
        "notes": args.notes.read_text(encoding="utf-8"),
    }, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    envelope = json.dumps({"payload": base64.b64encode(payload).decode(),
                           "signature": base64.b64encode(key.sign(payload)).decode()})
    verify_manifest(envelope.encode(),
                    base64.b64encode(key.public_key().public_bytes_raw()).decode(), args.channel)
    with args.output.open("x", encoding="utf-8") as output:
        output.write(envelope)
    print(f"Signed {args.output.name}; private key not included.")


if __name__ == "__main__":
    main()
