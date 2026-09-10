#!/usr/bin/env python3
"""Render assets/neofetch.svg — the identity card on the profile README.

Edit ART / INFO below and re-run:  python3 assets/make-neofetch.py
"""
import os

from termsvg import (CYAN, GREEN, GREY, ORANGE, PINK, PURPLE, DIM,
                     USER, prompt, render)

INFO_COL, KEY_W = 23, 11          # column grid, in characters

ART = [
    "        .--.",
    "       |o_o |",
    "       |:_/ |",
    "      //   \\ \\",
    "     (|     | )",
    "    /'\\_   _/`\\",
    "    \\___)=(___/",
]

# (key, [(text, colour), ...])
INFO = [
    ("OS",       [("Linux \u2014 any distro that gives me a shell", GREY)]),
    ("Host",     [("Bras\u00edlia \u00b7 DF \u00b7 Brazil", GREY)]),
    ("Uptime",   [("30+ years in tech, first login at age 11", GREY)]),
    ("Shell",    [("bash 5.2 (vim keybindings, obviously)", GREY)]),
    ("WM",       [("Kubernetes ", GREY), ("[CKS \u00b7 CKA \u00b7 CKAD]", PURPLE)]),
    ("Packages", [("5 Linux Foundation certifications", GREY)]),
    ("Kernel",   [("BSc Computer Eng \u2192 MSc Mechatronics", GREY)]),
    ("Modules",  [("Quantum Computing specialization", GREY)]),
    ("Process",  [("PhD in Informatics @ UnB  ", GREY), ("[running]", GREEN)]),
    ("Stopped",  [("BSc Statistics  ", GREY), ("[50% \u00b7 SIGSTOP]", PINK)]),
    ("Job 1",    [("Infra & DevOps Lead \u00b7 MPT", GREY)]),
    ("Job 2",    [("Innovation \u00b7 Hadoop/Cloudera + private LLMs", GREY)]),
    ("GPU",      [("clustered NVIDIA \u2192 ", GREY), ("smartlabbr.org", PURPLE)]),
    ("History",  [("VTEX (NYC HQ) 2021\u20132023 \u00b7 QE Lead", GREY)]),
    ("Locale",   [("pt_BR.UTF-8 \u00b7 en_US.UTF-8", GREY)]),
    ("Battery",  [("caffeine ", GREY), ("[charging]", GREEN)]),
]


def build_rows():
    rows = [prompt("neofetch"), []]

    # right-hand column: header, rule, then the key/value pairs
    right = [[(0, USER, GREEN)], [(0, "-" * len(USER), DIM)]]
    for key, runs in INFO:
        row, col = [(0, key.ljust(KEY_W), CYAN)], KEY_W
        for text, colour in runs:
            row.append((col, text, colour))
            col += len(text)
        right.append(row)

    for i in range(max(len(ART), len(right))):
        row = []
        if i < len(ART):                       # ascii art, left column
            stripped = ART[i].lstrip()
            row.append((len(ART[i]) - len(stripped), stripped, ORANGE))
        if i < len(right):                     # info, right column
            row += [(INFO_COL + c, t, colour) for c, t, colour in right[i]]
        rows.append(row)

    return rows + [[], prompt()]


if __name__ == "__main__":
    rows = build_rows()
    render(rows,
           path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "neofetch.svg"),
           title=f"{USER} \u2014 neofetch",
           cursor=(len(rows) - 1, len(USER) + 3))
