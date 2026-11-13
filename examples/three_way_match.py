"""Small local example for checking one invoice PDF or one PO number."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.record_loader import SourceRecordLoader  # noqa: E402
from src.three_way_match import run_three_way_check  # noqa: E402


# Parse mutually exclusive input choices so each run starts from one identifier.
def main() -> int:
    parser = argparse.ArgumentParser(description="Run one local invoice/PO/GR evidence check.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--invoice", help="Allow-listed invoice path, relative to raw data or project root")
    group.add_argument("--po", help="Exact PO number, for example PO-2026-0101")
    args = parser.parse_args()

    loader = SourceRecordLoader(
        raw_data_dir=PROJECT_ROOT / "data/raw/invoice-agent",
        working_set_csv=PROJECT_ROOT / "eval/working_set.csv",
        review_queue_csv=PROJECT_ROOT / "eval/review_queue.csv",
    )
    try:
        if args.invoice:
            supplied = Path(args.invoice)
            if not supplied.is_absolute() and not (loader.raw_root / supplied).exists():
                supplied = PROJECT_ROOT / supplied
            result = run_three_way_check(invoice_path=supplied, loader=loader)
        else:
            result = run_three_way_check(po_number=args.po, loader=loader)
    except (ValueError, FileNotFoundError) as exc:
        parser.error(str(exc))
    print(json.dumps(result.as_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
