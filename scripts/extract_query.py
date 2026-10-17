"""Run with python -m scripts.extract_query; input on stdin, JSON on stdout."""

import sys

from src.engine.extraction import extract
from src.errors import AFSError


def main() -> int:
    try:
        result = extract(sys.stdin.read())
    except (AFSError, ValueError):
        print(
            "Extraction failed. Check input, local configuration and provider availability. "
            "No result generated.",
            file=sys.stderr,
        )
        return 1
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
