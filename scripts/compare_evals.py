"""Compara dos corridas de evals caso por caso, con el ruido de tokens por tipo de caso (ver evals/compare.py).

    python scripts/compare_evals.py evals/resultados/A.json evals/resultados/B.json

Sale con código 1 si hay regresiones."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.compare import compare, render  # noqa: E402


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print(__doc__)
        return 2
    base, new = (json.loads(Path(p).read_text(encoding="utf-8")) for p in argv)
    report = compare(base, new)
    print(render(report))
    return 1 if report["regressions"] else 0


if __name__ == "__main__":
    sys.exit(main())
