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
ZHCONV_PIN = "zhconv==1.4.3"

# This script handles a package dependency conflict: oseti depends on an old
# mecab package that fails to build, but the sentiment analyzer works fine with
# mecab-python3 + ipadic (which are listed separately in the lock file). We install
# all transitive dependencies first, then install oseti without its declared
# dependencies, and finally verify with a smoke test.


def _read_lock(path: Path) -> list[str]:
    # Parse the locked requirements file (a pip-compatible format), keeping only
    # non-empty, non-comment lines.
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
    # Query the installed version of each package. Some packages have different
    # import names and distribution names, so we handle those cases explicitly.
    versions = {}
    for requirement in packages:
        package = requirement.split("==", 1)[0]
        distribution = "mecab-python3" if package == "mecab-python3" else package
        versions[package] = metadata.version(distribution)
    return versions


def _smoke_test_oseti() -> None:
    # Verify that the sentiment analyzer is properly wired by running a simple
    # test: analyze two contrasting sentences (positive and negative) to ensure
    # the tokenizer and Japanese dictionary are working correctly.
    import ipadic
    import oseti

    analyzer = oseti.Analyzer(mecab_args=f"-r /dev/null -d {ipadic.DICDIR}")
    scores = analyzer.analyze("良いです。悪いです。")
    if scores != [1.0, -1.0]:
        raise RuntimeError(f"Unexpected oseti smoke-test scores: {scores!r}")


def main() -> int:
    # Orchestrate the three-step install: load locked requirements, install all
    # dependencies first (excluding oseti), then install oseti without its declared
    # dependencies, and finally verify everything works with a smoke test.
    requirements = _read_lock(LOCK_PATH)
    if OSETI_PIN not in requirements:
        raise RuntimeError(f"{LOCK_PATH} must include {OSETI_PIN}")
    if ZHCONV_PIN not in requirements:
        raise RuntimeError(f"{LOCK_PATH} must include {ZHCONV_PIN}")

    # Install all transitive dependencies (mecab-python3, ipadic, etc.) first.
    dependency_requirements = [req for req in requirements if req != OSETI_PIN]
    _run([sys.executable, "-m", "pip", "install", *dependency_requirements])
    # Now install oseti itself, but skip its declared (broken) dependencies.
    _run([sys.executable, "-m", "pip", "install", "--no-deps", OSETI_PIN])
    # Verify that the sentiment analyzer can actually run.
    _smoke_test_oseti()

    # Report the installed stack to the user.
    versions = _installed_versions(requirements)
    print("Sentiment runtime ready:")
    for package in sorted(versions):
        print(f"{package}=={versions[package]}")
    print("Note: `pip check` may report `oseti requires mecab`; runtime uses mecab-python3 + ipadic.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
