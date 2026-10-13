#!/usr/bin/env python3
"""Track a process's position in the TRF1 chronological judgment queue.

    python3 queue/track.py            fetch today's positions, then rebuild the report
    python3 queue/track.py report     rebuild queue/README.md from the CSVs only
    python3 queue/track.py backfill   seed the CSVs from the old json/<label>/ snapshots

The court's API sits behind a Cloudflare challenge for datacenter IPs, so the
fetch runs from a residential connection; a challenge page fails the run
instead of being recorded.
"""

from __future__ import annotations

import csv
import datetime as dt
import glob
import json
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
API = "https://sistemas.trf1.jus.br/pgp-api/api/local/{local}/processo/{number}?ordem=1&max=10&offset=0"
# The court answers per "local"; a case moves from JFDF to TRF1 on appeal.
LOCAIS = ("TRF1", "JFDF")
BRT = dt.timezone(dt.timedelta(hours=-3))
FIELDS = ("date", "position", "grau", "court", "local")
RATE_WINDOW_DAYS = 30


def processes() -> dict[str, str]:
    return json.loads((HERE / "processes.json").read_text())


def get_json(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://sistemas.trf1.jus.br/ordemcronologica/",
            "User-Agent": "queue-tracker (+https://github.com/thyarles/thyarles)",
        },
    )
    last: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
                if "json" not in resp.headers.get("Content-Type", ""):
                    raise ValueError(f"not JSON ({resp.headers.get('Content-Type')}): {body[:80]!r}")
                return json.loads(body)
        except Exception as exc:  # network, HTTP or challenge page: retry, then give up
            last = exc
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"{url}: {last}")


def to_row(entry: dict, local: str) -> dict[str, str]:
    orgao = entry["orgao"]
    day = dt.datetime.fromtimestamp(entry["dataInformacao"] / 1000, BRT).date()
    return {
        "date": day.isoformat(),
        "position": str(entry["ordem"]),
        "grau": orgao["grau"],
        "court": orgao["descricaoOrgaoJulgador"],
        "local": local,
    }


def load(label: str) -> dict[str, dict[str, str]]:
    path = DATA / f"{label}.csv"
    if not path.exists():
        return {}
    with path.open(newline="") as fh:
        return {r["date"]: r for r in csv.DictReader(fh)}


def save(label: str, rows: dict[str, dict[str, str]]) -> None:
    DATA.mkdir(exist_ok=True)
    with (DATA / f"{label}.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows[d] for d in sorted(rows))


def fetch() -> int:
    failed = 0
    for label, number in processes().items():
        try:
            for local in LOCAIS:
                found = get_json(API.format(local=local, number=number)).get("processos", [])
                if found:
                    row = to_row(found[0], local)
                    break
            else:
                print(f"{label}: not in any queue (judged, or out of the list)")
                continue
        except RuntimeError as exc:
            print(f"{label}: FAILED {exc}", file=sys.stderr)
            failed += 1
            continue
        rows = load(label)
        rows[row["date"]] = row  # the court's data date, so reruns on one day collapse
        save(label, rows)
        print(f"{label}: position {row['position']} at {row['court']} ({row['date']})")
    return failed


def backfill() -> None:
    for label in processes():
        rows = load(label)
        for path in glob.glob(str(HERE.parent / "json" / label / "*.json")):
            try:
                found = json.loads(Path(path).read_text()).get("processos", [])
            except ValueError:
                continue  # an old run that saved a challenge page instead of JSON
            for entry in found:
                row = to_row(entry, entry["orgao"]["siglaSecao"])
                rows.setdefault(row["date"], row)
        save(label, rows)
        print(f"{label}: {len(rows)} days")


def slope(points: list[tuple[float, float]]) -> float | None:
    """Least-squares positions per day; None until there are two distinct days."""
    if len(points) < 2:
        return None
    n = len(points)
    mx = sum(x for x, _ in points) / n
    my = sum(y for _, y in points) / n
    den = sum((x - mx) ** 2 for x, _ in points)
    return sum((x - mx) * (y - my) for x, y in points) / den if den else None


def describe(label: str, number: str, rows: list[dict[str, str]]) -> list[str]:
    if not rows:
        return [f"## {label}", "", f"`{number}` has no data yet.", ""]
    last = rows[-1]
    stage = [r for r in rows if r["court"] == last["court"]]  # current queue only
    today = dt.date.fromisoformat(last["date"])
    day = lambda r: (dt.date.fromisoformat(r["date"]) - today).days  # noqa: E731
    pos = int(last["position"])

    def moved(days: int) -> str:
        past = [r for r in stage if day(r) <= -days]
        return f"{int(past[-1]['position']) - pos:+d} positions" if past else "—"

    window = [(day(r), int(r["position"])) for r in stage if day(r) > -RATE_WINDOW_DAYS]
    whole = [(day(r), int(r["position"])) for r in stage]
    recent, overall = slope(window), slope(whole)

    def eta(rate: float | None) -> str:
        if rate is None:
            return "needs a few more days of data"
        if rate >= 0:
            return "not moving forward"
        days = pos / -rate
        return f"{-rate:.1f} positions/day → ~{today + dt.timedelta(days=days):%Y-%m-%d} ({days / 30.4:.0f} months)"

    out = [
        f"## {label}",
        "",
        f"`{number}` · {last['grau']} · **{last['court']}** ({last['local']})",
        "",
        "| | |",
        "|---|---|",
        f"| Position | **{pos}** (court data of {last['date']}) |",
        f"| In this queue since | {stage[0]['date']} (first seen at {stage[0]['position']}) |",
        f"| Advanced, last 7 days | {moved(7)} |",
        f"| Advanced, last 30 days | {moved(30)} |",
        f"| Pace, last {RATE_WINDOW_DAYS} days | {eta(recent)} |",
        f"| Pace, whole queue | {eta(overall)} |",
        "",
    ]
    if len(stage) >= 2:
        step = max(1, len(stage) // 40)
        sample = stage[::step] if stage[::step][-1] is last else stage[::step] + [last]
        out += [
            "```mermaid",
            "xychart-beta",
            f'  title "{label} — position in queue"',
            "  x-axis [" + ", ".join(f'"{r["date"][5:]}"' for r in sample) + "]",
            '  y-axis "position"',
            "  line [" + ", ".join(r["position"] for r in sample) + "]",
            "```",
            "",
        ]
    earlier = [r for r in rows if r["court"] != last["court"]]
    if earlier:
        first, final = earlier[0], earlier[-1]
        span = (dt.date.fromisoformat(final["date"]) - dt.date.fromisoformat(first["date"])).days
        out += [
            f"Earlier queue: **{final['court']}** ({final['grau']}), {first['position']} → {final['position']} "
            f"between {first['date']} and {final['date']} ({span} days); it left that queue at position "
            f"{final['position']}, not 0, so treat any ETA as a rough upper bound.",
            "",
        ]
    out += ["<details><summary>Last 15 readings</summary>", "", "| Date | Position | Court |", "|---|---:|---|"]
    out += [f"| {r['date']} | {r['position']} | {r['court']} |" for r in reversed(rows[-15:])]
    out += ["", "</details>", ""]
    return out


def report() -> None:
    lines = [
        "# Judgment queue tracker",
        "",
        "Daily position of each process in the TRF1 chronological judgment queue",
        "([ordem cronológica](https://sistemas.trf1.jus.br/ordemcronologica/)). Lower is closer to judgment.",
        f"Generated by `queue/track.py`; full history in `queue/data/`. Last update: {dt.datetime.now(BRT):%Y-%m-%d %H:%M} BRT.",
        "",
    ]
    for label, number in processes().items():
        by_date = load(label)
        rows = [by_date[d] for d in sorted(by_date)]
        lines += describe(label, number, rows)
    (HERE / "README.md").write_text("\n".join(lines))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "fetch"
    status = 0
    if mode == "backfill":
        backfill()
    elif mode == "fetch":
        status = 1 if fetch() else 0
    report()
    sys.exit(status)
