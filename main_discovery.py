"""Idea Discovery orchestrator (Workflow A, docs/01-architecture.md).

Pipeline:
    HN + Reddit + Product Hunt ingest -> dedupe (vs Sheet) -> LLM scoring
    -> Sheet write -> Telegram digest

Thin orchestrator only. Run locally with --dry-run to exercise the full pipeline
while skipping the Sheet write and Telegram send (prints results to stdout).

    python main_discovery.py --dry-run
    python main_discovery.py            # writes to Sheet + sends Telegram
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

import config
import dedupe
import scoring
from delivery import telegram
from sources import hackernews, producthunt, reddit
from storage import sheets

log = logging.getLogger("discovery")

# Human-readable labels for source-failure notes in the digest (doc 06).
_SOURCE_LABELS = {"hn": "Hacker News", "reddit": "Reddit", "ph": "Product Hunt"}
_SOURCES = (("hn", hackernews.fetch), ("reddit", reddit.fetch), ("ph", producthunt.fetch))


def _fetch_sources() -> tuple[list[dict], list[str]]:
    """Fetch every source independently. A failing source is recorded as a note
    and does not abort the run (doc 01 error handling)."""
    candidates: list[dict] = []
    errors: list[str] = []

    for name, fetch in _SOURCES:
        try:
            got = fetch()
            candidates.extend(got)
            log.info("Source %s: %d candidates", name, len(got))
        except Exception as exc:  # noqa: BLE001 - isolate per-source failures
            label = _SOURCE_LABELS.get(name, name)
            log.error("Source %s failed: %s", name, exc)
            errors.append(f"{label} fetch failed this run.")

    return candidates, errors


def _print_dry_run(scored: list[dict], message: str, to_sheet: list[dict]) -> None:
    print("\n" + "=" * 70)
    print("DRY RUN — no Sheet write, no Telegram send")
    print("=" * 70)

    print(f"\nScored {len(scored)} candidate(s). "
          f"{len(to_sheet)} would be written to the Sheet (score >= {config.SHEET_THRESHOLD}):\n")
    for s in sorted(scored, key=lambda x: x.get("score", 0), reverse=True):
        flag = "" if s.get("grounded", True) else "  [!] rationale not grounded in source"
        print(f"  [{s.get('score'):>3}] {s.get('verdict'):<6} {s.get('title', '')[:70]}{flag}")
        print(f"        {s.get('rationale', '')}")
        print(f"        mvp: {s.get('mvp_scope', '')}")
        print(f"        est {s.get('est_build_days', '?')}d · {s.get('source')} · "
              f"{s.get('model_used', '')}")
        print(f"        {s.get('url', '')}\n")

    print("-" * 70)
    print("TELEGRAM DIGEST PREVIEW (would be sent):")
    print("-" * 70)
    print(message)
    print("=" * 70 + "\n")


def run(dry_run: bool) -> int:
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    candidates, source_errors = _fetch_sources()
    log.info("Total raw candidates: %d", len(candidates))

    candidates = dedupe.filter_new(candidates)
    log.info("After dedupe: %d candidates to score", len(candidates))

    scored = scoring.score_candidates(candidates)

    to_sheet = [s for s in scored if s.get("score", 0) >= config.SHEET_THRESHOLD]
    message = telegram.build_message(scored, date_str, source_errors)

    if dry_run:
        _print_dry_run(scored, message, to_sheet)
        return 0

    # Live run: write to Sheet, then send digest.
    if to_sheet:
        written = sheets.append_candidates(to_sheet)
        log.info("Wrote %d rows to the Sheet", written)
    else:
        log.info("No candidates >= %d; nothing written to the Sheet", config.SHEET_THRESHOLD)

    telegram.send(message)
    log.info("Discovery run complete.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Idea Scout — discovery pipeline (HN + Reddit + Product Hunt).")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the full pipeline but skip the Sheet write and Telegram send; print to stdout.",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Debug logging.")
    args = parser.parse_args()

    # The digest preview prints emoji/en-dashes; Windows' default cp1252 console
    # would raise UnicodeEncodeError. Force UTF-8 output where supported.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        return run(dry_run=args.dry_run)
    except Exception as exc:  # noqa: BLE001 - fail loudly with non-zero exit (doc 08)
        log.exception("Discovery run failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
