"""Run all llm-ledger test modules (plain asserts, no framework)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import test_build
import test_confidence
import test_match
import test_nhlocal
import test_reconcile
import test_validate

MODULES = (test_match, test_confidence, test_reconcile, test_validate, test_build,
           test_nhlocal)


def main() -> int:
    failures = 0
    for module in MODULES:
        for name in sorted(dir(module)):
            if not name.startswith("test_"):
                continue
            try:
                getattr(module, name)()
                print(f"PASS {module.__name__}.{name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {module.__name__}.{name}: {exc}")
    if failures:
        print(f"\n{failures} test(s) failed")
        return 1
    print("\nall tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
