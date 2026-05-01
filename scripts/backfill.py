"""
Backfill historical OpenAQ and prescribing data into GCS.

Uploads data for each month in the given range. After backfill, trigger
the transform_dag via Airflow UI or CLI to load data into BigQuery.

Prerequisites:
    - Airflow stack running (cd orchestration && docker compose up -d)
    - UK stations already refreshed (via refresh_uk_stations task)

Usage:
    python scripts/backfill.py --start 2025-06 --end 2026-02
    python scripts/backfill.py --start 2025-04 --end 2025-10 --openaq-only
    python scripts/backfill.py --start 2025-04 --end 2025-10 --prescribing-only
"""

import argparse
import subprocess
import sys
from datetime import date

COMPOSE_DIR = "orchestration"
EXEC_CMD = ["docker", "compose", "-f", f"{COMPOSE_DIR}/docker-compose.yml", "exec", "-T", "airflow-scheduler"]


def run_airflow(args: list[str], description: str) -> bool:
    """Run an airflow command inside the scheduler container."""
    cmd = EXEC_CMD + args
    print(f"\n{'='*60}")
    print(f"  {description}")
    print(f"  Command: {' '.join(args)}")
    print(f"{'='*60}")

    result = subprocess.run(cmd, text=True)

    if result.returncode != 0:
        print(f"  FAILED (exit code {result.returncode})")
        return False

    print(f"  OK")
    return True


def generate_months(start: date, end: date) -> list[date]:
    """Generate a list of first-of-month dates from start to end (inclusive)."""
    months = []
    current = start.replace(day=1)
    end_month = end.replace(day=1)
    while current <= end_month:
        months.append(current)
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    return months


def parse_month(value: str) -> date:
    """Parse YYYY-MM into a date."""
    try:
        parts = value.split("-")
        return date(int(parts[0]), int(parts[1]), 1)
    except (ValueError, IndexError):
        raise argparse.ArgumentTypeError(f"Invalid month format: '{value}'. Use YYYY-MM (e.g. 2025-04)")


def main():
    parser = argparse.ArgumentParser(description="Backfill historical data into GCS.")
    parser.add_argument("--start", type=parse_month, required=True, help="Start month (YYYY-MM)")
    parser.add_argument("--end", type=parse_month, required=True, help="End month inclusive (YYYY-MM)")
    parser.add_argument("--openaq-only", action="store_true", help="Only backfill OpenAQ data")
    parser.add_argument("--prescribing-only", action="store_true", help="Only backfill prescribing data")
    args = parser.parse_args()

    if args.openaq_only and args.prescribing_only:
        parser.error("Cannot use both --openaq-only and --prescribing-only")

    months = generate_months(args.start, args.end)
    run_openaq = not args.prescribing_only
    run_prescribing = not args.openaq_only

    print(f"Backfill plan: {len(months)} months from {args.start:%Y-%m} to {args.end:%Y-%m}")
    print(f"  OpenAQ:      {'yes' if run_openaq else 'skip'}")
    print(f"  Prescribing: {'yes' if run_prescribing else 'skip'}")

    failed = []

    # Refresh UK stations once before ingesting OpenAQ
    if run_openaq:
        ok = run_airflow(
            ["airflow", "tasks", "test", "ingest_dag", "refresh_uk_stations", str(args.start)],
            "Refreshing UK station list",
        )
        if not ok:
            print("\nStation refresh failed — cannot proceed with OpenAQ ingest.")
            sys.exit(1)

    # Loop through each month
    for i, month in enumerate(months, 1):
        date_str = str(month)
        label = f"[{i}/{len(months)}] {month:%Y-%m}"

        if run_openaq:
            ok = run_airflow(
                ["airflow", "tasks", "test", "ingest_dag", "ingest_openaq_to_gcs", date_str],
                f"{label} — OpenAQ to GCS",
            )
            if not ok:
                failed.append(f"openaq {month:%Y-%m}")

        if run_prescribing:
            ok = run_airflow(
                ["airflow", "tasks", "test", "ingest_dag", "ingest_prescribing_to_gcs", date_str],
                f"{label} — Prescribing to GCS",
            )
            if not ok:
                failed.append(f"prescribing {month:%Y-%m}")

    # Summary
    print(f"\n{'='*60}")
    print(f"  Backfill complete: {len(months)} months")
    if failed:
        print(f"  {len(failed)} failures:")
        for f in failed:
            print(f"    - {f}")
        sys.exit(1)
    else:
        print(f"  All tasks succeeded")
    print(f"{'='*60}")
    print(f"\n  Next: trigger transform_dag to load data into BigQuery")
    print(f"  docker compose exec airflow-scheduler airflow dags trigger transform_dag")


if __name__ == "__main__":
    main()
