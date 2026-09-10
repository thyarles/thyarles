#!/usr/bin/env python3
"""Render assets/stats.svg — the `btop` card on the profile README.

Language standing comes from CodersRank, which scores real contribution across
every connected repo. An earlier version derived languages from the GitHub API
instead and could not be made honest: counting repos-per-primary-language put
JavaScript on top and Shell at 8%, while raw Linguist bytes put Jupyter
Notebook at 90% (.ipynb files embed base64 image output). CodersRank already
solves that, and it is the profile Charles actually maintains.

GitHub still supplies the repo/star/commit counters.

    python3 assets/make-stats.py                # CodersRank + public GitHub
    GH_TOKEN=... python3 assets/make-stats.py   # also fills in the commit count
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date

from termsvg import CYAN, DIM, GREEN, GREY, ORANGE, PURPLE, USER, Bar, command_col, prompt, render

LOGIN = "thyarles"
CR = f"https://api.codersrank.io/v2/users/{LOGIN}"

BAR_W, CARD_COLS, TOP_N = 20, 77, 6
NAME_COL, BAR_COL, WORLD_COL, BR_COL = 2, 17, 39, 59

# names that overflow the 14-char label column
ABBREV = {"Jupyter Notebook": "Jupyter", "Robot": "Robot Fwk"}

# a few of GitHub's own language colours, so the bars read at a glance
LANG_COLOUR = {
    "Shell": "#89e051", "Python": "#3572A5", "Go": "#00ADD8", "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6", "HTML": "#e34c26", "CSS": "#563d7c", "Java": "#b07219",
    "JSON": "#a0a0a0", "Jupyter Notebook": "#DA5B0B", "Less": "#1d365d", "SCSS": "#c6538c",
    "PHP": "#4F5D95", "Robot": "#00c0b5", "Dockerfile": "#384d54", "R": "#198CE7",
    "C": "#555555", "Rust": "#dea584", "HCL": "#844FBA", "Ruby": "#701516",
}


def get(url, token=None):
    headers = {"Accept": "application/json", "User-Agent": f"{LOGIN}-profile-card"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
        return json.loads(r.read().decode())


def github(token):
    """Repo/star/commit counters. Best effort — the card still builds without them."""
    out = {}
    try:
        user = get(f"https://api.github.com/users/{LOGIN}", token)
        out["repos"] = user["public_repos"]
        stars, page = 0, 1
        while True:
            batch = get(f"https://api.github.com/users/{LOGIN}/repos"
                        f"?per_page=100&type=owner&page={page}", token)
            stars += sum(r["stargazers_count"] for r in batch)
            if len(batch) < 100:
                break
            page += 1
        out["stars"] = stars
    except (urllib.error.HTTPError, urllib.error.URLError, KeyError) as exc:
        print(f"  note: GitHub counters unavailable ({exc})", file=sys.stderr)

    if not token:
        return out
    try:                                    # commit count is GraphQL-only
        query = '{user(login:"%s"){contributionsCollection{totalCommitContributions}}}' % LOGIN
        req = urllib.request.Request(
            "https://api.github.com/graphql", data=json.dumps({"query": query}).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                     "User-Agent": f"{LOGIN}-profile-card"})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.loads(r.read().decode())
        out["commits"] = body["data"]["user"]["contributionsCollection"]["totalCommitContributions"]
    except (urllib.error.HTTPError, urllib.error.URLError, KeyError, TypeError) as exc:
        print(f"  note: commit count unavailable ({exc})", file=sys.stderr)
    return out


def streak_days(badges):
    for b in badges:
        if b.get("badgeFamily") == "Streak":
            return b.get("values", {}).get("days")
    return None


def build_rows(user, langs, badges, gh):
    rows = [prompt("btop"), []]

    rank, total = user.get("position"), user.get("total_users")
    if rank and total:
        rows.append([
            (NAME_COL, "codersrank".ljust(14), CYAN),
            (17, f"#{rank:,} of {total:,} devs worldwide", GREY),
            (52, f"top {rank / total * 100:.2f}%", GREEN),
        ])

    days = streak_days(badges)
    if days:
        rows.append([(NAME_COL, "streak".ljust(14), CYAN),
                     (17, f"{int(days):,} days committing in a row", GREY)])

    if gh:
        bits = []
        if "repos" in gh:
            bits.append(f"{gh['repos']:,} repos")
        if "stars" in gh:
            bits.append(f"{gh['stars']:,} stars")
        if "commits" in gh:
            bits.append(f"{gh['commits']:,} commits (1y)")
        if bits:
            rows.append([(NAME_COL, "github".ljust(14), CYAN),
                         (17, " · ".join(bits), GREY)])

    top = sorted(langs.items(), key=lambda kv: -kv[1]["score"])[:TOP_N]
    if top:
        best = top[0][1]["score"] or 1
        rows += [[], [
            (NAME_COL, "top languages", GREEN),
            (WORLD_COL, "world rank", DIM),
            (BR_COL, "Brazil", DIM),
        ]]
        for name, d in top:
            rows.append([
                (NAME_COL, ABBREV.get(name, name)[:14].ljust(15), GREY),
                Bar(BAR_COL, BAR_W, d["score"] / best, LANG_COLOUR.get(name, PURPLE)),
                (WORLD_COL, f"#{d['world_wide_rank']:>6,}", GREY),
                # pool size dimmed, so the eye separates rank from field size
                (WORLD_COL + 8, f"of {d['world_wide_all']:>7,}", DIM),
                (BR_COL, f"#{d['country_rank']:>5,}", GREY),
            ])

    # the standouts, with the pool size shown so the flex stays honest
    ones = sorted((d["country_all"], n, d) for n, d in langs.items() if d["country_rank"] == 1)
    if ones:
        bits = [f"{n} #1 of {d['country_all']}" for _, n, d in reversed(ones[-2:])]
        rows += [[], [(NAME_COL, "top of Brazil".ljust(14), CYAN),
                      (17, " · ".join(bits), ORANGE)]]

    rows += [[], [(NAME_COL, f"snapshot {date.today().isoformat()} · codersrank.io/@{LOGIN}", DIM)],
             prompt()]
    return rows


if __name__ == "__main__":
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    user = get(CR)                                  # essential — let it fail loudly
    langs = get(f"{CR}/languages?get_all=true")
    try:
        badges = get(f"{CR}/badges").get("badges", [])
    except (urllib.error.HTTPError, urllib.error.URLError):
        badges = []

    rows = build_rows(user, langs, badges, github(token))
    render(rows,
           path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "stats.svg"),
           title=f"{USER} — btop",
           cursor=(len(rows) - 1, command_col()),
           min_cols=CARD_COLS)
