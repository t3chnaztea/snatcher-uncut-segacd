#!/usr/bin/env python3
"""Assemble an offline browser installer from a pinned, read-only engine checkout."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from patch_profiles import load_registry, DEFAULT_PROFILE_ID

ENGINE_COMMIT = "4f17297cd1dc0835a0b0747497fa15f5f63f1623"
PATCH_SHA256 = "1485cc915dc0d2629049f7abcb8f724f608a8205c89456ad534acf2d26ac09a4"


def assemble(engine: Path, patch: Path | None, output: Path, registry: Path | None = None) -> dict:
    commit = subprocess.check_output(["git", "-C", str(engine), "rev-parse", "HEAD"], text=True).strip()
    if commit != ENGINE_COMMIT:
        raise ValueError("Patch engine checkout does not match the pinned commit")
    if subprocess.check_output(["git", "-C", str(engine), "status", "--porcelain"], text=True).strip():
        raise ValueError("Patch engine checkout has local changes")
    if registry is None:
        raise ValueError("The full Snatcher Patcher requires a verified profile registry")
    registry = Path(registry)
    profiles = load_registry(registry)
    payloads = {}
    patch_hashes = {}
    for row in profiles['profiles']:
        if row['no_patch']:
            continue
        relative = Path(row['patch']['file'])
        candidate = registry.parent / relative
        if candidate.is_symlink() or not candidate.is_file() or candidate.resolve().parent != (registry.parent / 'patches/profiles').resolve():
            raise ValueError("Profile patch path is missing or unsafe")
        data = candidate.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if actual != row['patch']['sha256']:
            raise ValueError("Profile patch checksum mismatch: " + row['id'])
        payloads[row['id']] = base64.b64encode(data).decode('ascii')
        patch_hashes[row['id']] = actual
    if patch is not None and hashlib.sha256(Path(patch).read_bytes()).hexdigest() != patch_hashes[DEFAULT_PROFILE_ID]:
        raise ValueError("Default release patch checksum mismatch")
    if output.exists():
        raise ValueError("Output path already exists; choose a new candidate folder")
    root = Path(__file__).resolve().parent.parent
    source = root / "release" / "installer"
    if not source.is_dir():
        source = root / "browser"
    templates = ('index.html', 'style.css', 'app.js')
    if any((source / name).is_symlink() or not (source / name).is_file() for name in templates):
        raise ValueError("Installer templates are missing or unsafe")
    output.mkdir(parents=True)
    for name in templates:
        shutil.copyfile(source / name, output / name)
    vendor = output / "vendor"
    (vendor / "modules").mkdir(parents=True)
    shutil.copy2(engine / "LICENSE", vendor / "LICENSE")
    shutil.copy2(engine / "rom-patcher-js" / "RomPatcher.js", vendor / "RomPatcher.js")
    for module in (engine / "rom-patcher-js" / "modules").glob("*.js"):
        if module.is_file():
            shutil.copy2(module, vendor / "modules" / module.name)
    (output / "patch-data.js").write_text(
        "const SNATCHER_PROFILE_REGISTRY = " + json.dumps(profiles, separators=(',', ':')) + ";\n" +
        "const SNATCHER_PATCHES_BASE64 = " + json.dumps(payloads, separators=(',', ':')) + ";\n")
    receipt = {
        "engine_repository": "https://github.com/marcrobledo/RomPatcher.js",
        "engine_commit": commit,
        "patch_sha256": patch_hashes[DEFAULT_PROFILE_ID],
        "profile_registry_sha256": hashlib.sha256(registry.read_bytes()).hexdigest(),
        "profiles": profiles,
        "profile_patch_sha256": patch_hashes,
        "files": {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted(output.rglob("*")) if p.is_file()},
    }
    (output / "browser-build.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--patch", type=Path, help="Optional immutable default patch cross-check")
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = assemble(args.engine, args.patch, args.output, registry=args.registry)
    print(json.dumps({"engine_commit": receipt["engine_commit"], "files": len(receipt["files"])}))


if __name__ == "__main__":
    main()
