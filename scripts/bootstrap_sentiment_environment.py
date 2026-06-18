#!/usr/bin/env python3
"""
Install the pinned JP-EN sentiment runtime.

This exists because oseti 0.4.3.1 declares the legacy `mecab` package, which
builds from source and requires system `mecab-config` on macOS. The analysis
runtime works with `mecab-python3` plus `ipadic`, so this bootstrap installs the
pinned transitive stack first and then installs oseti with `--no-deps`.
"""

from __future__ import annotations

import importlib.metadata as metadata
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK_PATH = ROOT / "requirements-sentiment.lock.txt"
OSETI_PIN = "oseti==0.4.3.1"


def _read_lock(path: Path) -> list[str]:
    requirements = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        requirements.append(line)
    return requirements


def _run(args: list[str]) -> None:
    subprocess.run(args, check=True)


def _installed_versions(packages: list[str]) -> dict[str, str]:
    versions = {}
    for requirement in packages:
        package = requirement.split("==", 1)[0]
        distribution = "mecab-python3" if package == "mecab-python3" else package
        versions[package] = metadata.version(distribution)
    return versions


def _smoke_test_oseti() -> None:
    import ipadic
    import oseti

    analyzer = oseti.Analyzer(mecab_args=f"-r /dev/null -d {ipadic.DICDIR}")
    scores = analyzer.analyze("良いです。悪いです。")
    if scores != [1.0, -1.0]:
        raise RuntimeError(f"Unexpected oseti smoke-test scores: {scores!r}")


def main() -> int:
    requirements = _read_lock(LOCK_PATH)
    if OSETI_PIN not in requirements:
        raise RuntimeError(f"{LOCK_PATH} must include {OSETI_PIN}")

    dependency_requirements = [req for req in requirements if req != OSETI_PIN]
    _run([sys.executable, "-m", "pip", "install", *dependency_requirements])
    _run([sys.executable, "-m", "pip", "install", "--no-deps", OSETI_PIN])
    _smoke_test_oseti()

    versions = _installed_versions(requirements)
    print("Sentiment runtime ready:")
    for package in sorted(versions):
        print(f"{package}=={versions[package]}")
    print("Note: `pip check` may report `oseti requires mecab`; runtime uses mecab-python3 + ipadic.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
