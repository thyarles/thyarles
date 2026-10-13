#!/usr/bin/env python3
"""Track a process's position in the TRF1 chronological judgment queue.

    python3 queue/track.py            fetch today's positions, then rebuild the report
    python3 queue/track.py report     rebuild queue/README.md from the CSVs only
    python3 queue/track.py backfill   seed the CSVs from the old json/<label>/ snapshots

Once a week it also counts the whole queue by the month each case was
concluded to the judge, which shows how fast each month's cases are judged.
Only those counts are stored, never other cases' numbers.

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
from collections import Counter
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
API = "https://sistemas.trf1.jus.br/pgp-api/api/local/{local}/processo/{number}?ordem=1&max=10&offset=0"
# The court answers per "local"; a case moves from JFDF to TRF1 on appeal.
LOCAIS = ("TRF1", "JFDF")
BRT = dt.timezone(dt.timedelta(hours=-3))
QUEUE_API = (
    "https://sistemas.trf1.jus.br/pgp-api/api/orgao/{orgao}/processo"
    "?local={local}&ordem=1&max=100&offset={offset}"  # the server caps pages at 100
)
FIELDS = ("date", "position", "grau", "court", "local", "orgao_id", "concluded")
COHORT_FIELDS = ("snapshot", "concluded", "waiting")
COHORT_EVERY_DAYS = 7
COHORT_MONTHS_SHOWN = 24
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


def brt_date(ms: int) -> dt.date:
    return dt.datetime.fromtimestamp(ms / 1000, BRT).date()


def to_row(entry: dict, local: str) -> dict[str, str]:
    orgao = entry["orgao"]
    return {
        "date": brt_date(entry["dataInformacao"]).isoformat(),
        "position": str(entry["ordem"]),
        "grau": orgao["grau"],
        "court": orgao["descricaoOrgaoJulgador"],
        "local": local,
        "orgao_id": str(orgao["id"]),
        "concluded": brt_date(entry["primeiraConclusao"]).isoformat(),
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


def load_cohorts(label: str) -> dict[str, dict[str, int]]:
    """snapshot date -> {conclusion month: cases still waiting}."""
    path = DATA / f"{label}-cohorts.csv"
    snapshots: dict[str, dict[str, int]] = {}
    if path.exists():
        with path.open(newline="") as fh:
            for r in csv.DictReader(fh):
                snapshots.setdefault(r["snapshot"], {})[r["concluded"]] = int(r["waiting"])
    return snapshots


def snapshot_queue(label: str, row: dict[str, str]) -> None:
    """Count the case's whole queue by conclusion month, at most once a week."""
    seen = load_cohorts(label)
    today = dt.date.fromisoformat(row["date"])
    if seen and (today - dt.date.fromisoformat(max(seen))).days < COHORT_EVERY_DAYS:
        return
    counts: Counter[str] = Counter()
    offset = 0
    while True:
        page = get_json(QUEUE_API.format(orgao=row["orgao_id"], local=row["local"], offset=offset))
        counts.update(brt_date(p["primeiraConclusao"]).strftime("%Y-%m") for p in page["processos"])
        offset += 100
        if not page["processos"] or offset >= page["totalLista"]:
            break
        time.sleep(1)  # about 90 pages for a 9000-case queue; no need to rush
    path = DATA / f"{label}-cohorts.csv"
    new = not path.exists()
    with path.open("a", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        if new:
            writer.writerow(COHORT_FIELDS)
        writer.writerows((row["date"], month, counts[month]) for month in sorted(counts))
    print(f"{label}: weekly snapshot, {sum(counts.values())} cases in queue")


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
        try:
            snapshot_queue(label, row)
        except RuntimeError as exc:  # the daily reading stands; the snapshot retries tomorrow
            print(f"{label}: weekly snapshot FAILED {exc}", file=sys.stderr)
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


def add_months(month: str, n: int) -> str:
    y, m = divmod(int(month[:4]) * 12 + int(month[5:7]) - 1 + n, 12)
    return f"{y:04d}-{m + 1:02d}"


def describe_cohorts(last: dict[str, str], snapshots: dict[str, dict[str, int]]) -> list[str]:
    if not snapshots:
        return []
    dates = sorted(snapshots)
    now = dates[-1]
    month_ago = [d for d in dates if (dt.date.fromisoformat(now) - dt.date.fromisoformat(d)).days >= 28]
    cols = [now] + ([month_ago[-1]] if month_ago else []) + ([dates[0]] if dates[0] not in (now, *month_ago[-1:]) else [])
    yours = (last.get("concluded") or "")[:7] or max(snapshots[now])
    shown = [add_months(yours, -k) for k in range(COHORT_MONTHS_SHOWN - 1, -1, -1)]

    def total(snap: str, keep) -> int:  # noqa: ANN001
        return sum(n for m, n in snapshots[snap].items() if keep(m))

    out = [
        "### Who is waiting, by month concluded (weekly)",
        "",
        "Cases still in this queue, grouped by the month they were concluded to the judge.",
        "A month's count dropping means its cases are being judged; the oldest months that",
        "drop fast are the ones the judge is working on now.",
        "",
        "| Concluded | " + " | ".join(cols) + " |",
        "|---|" + "---:|" * len(cols),
        f"| before {shown[0]} | " + " | ".join(str(total(c, lambda m: m < shown[0])) for c in cols) + " |",
    ]
    for month in shown:
        mark = " ← yours" if month == yours else ""
        out.append(f"| {month}{mark} | " + " | ".join(str(snapshots[c].get(month, 0)) for c in cols) + " |")
    out += [
        f"| after {yours} | " + " | ".join(str(total(c, lambda m: m > yours)) for c in cols) + " |",
        "| **total** | " + " | ".join(f"**{total(c, lambda m: True)}**" for c in cols) + " |",
        "",
    ]
    return out


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
    out += describe_cohorts(last, load_cohorts(label))
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
