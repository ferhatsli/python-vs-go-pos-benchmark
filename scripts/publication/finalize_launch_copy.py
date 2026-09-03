#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import urlparse

MEDIUM_TOKEN = "{{MEDIUM_URL}}"
GITHUB_TOKEN = "{{GITHUB_URL}}"


def _validate_https(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"URL must be HTTPS: {url}")


def finalize_copy(source: str, medium_url: str, github_url: str) -> str:
    _validate_https(medium_url)
    _validate_https(github_url)
    if MEDIUM_TOKEN not in source or GITHUB_TOKEN not in source:
        raise ValueError("launch copy is missing required URL tokens")
    return source.replace(MEDIUM_TOKEN, medium_url).replace(GITHUB_TOKEN, github_url)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inject verified live URLs into LinkedIn launch copy.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--medium-url", required=True)
    parser.add_argument("--github-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = args.source.read_text(encoding="utf-8")
    try:
        result = finalize_copy(source, args.medium_url, args.github_url)
    except ValueError as exc:
        parser.error(str(exc))
    args.output.write_text(result, encoding="utf-8")
    print(f"PASS: finalized launch copy -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
