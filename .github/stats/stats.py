#!/usr/bin/env python3
"""Draws the HIGH SCORES panel (assets/stats.svg and assets/stats-m.svg) from
public GitHub activity. Standard library only, so the workflow needs no installs.

Usage:
  GITHUB_TOKEN=... python3 .github/stats/stats.py            # fetch + draw
  python3 .github/stats/stats.py --data sample.json          # draw from saved data

Pixel lettering comes from glyphs.json, rasterised from Jersey 10 and Tiny5
(both SIL Open Font License 1.1).
"""
import base64
import datetime as dt
import json
import os
import struct
import sys
import urllib.request
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
LOGIN = os.environ.get("STATS_LOGIN", "Oliverr100")
K = 4

INK = "#22091F"
CREAM = "#F6EEE3"
LILAC = "#A99CC8"
LILAC_L = "#D9D0EE"
DIM = "#6F5FA6"
GOLD_BANDS = [(0, "#FFF1B8"), (3, "#FFE08A"), (6, "#FFC94D"), (9, "#FF9A3D")]
LEVELS = ["#1E1447", "#7A4A1E", "#B8742A", "#F0A63A", "#FFE08A"]
LEVEL_NAMES = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}
BAYER4 = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

GLYPHS = json.load(open(os.path.join(HERE, "glyphs.json")))


# ------------------------------------------------------------------ data
QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount contributionLevel } }
      }
    }
    repositories(ownerAffiliations: OWNER, privacy: PUBLIC) { totalCount }
  }
}
"""


def fetch():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is not set")
    body = json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode()
    req = urllib.request.Request("https://api.github.com/graphql", data=body, headers={
        "Authorization": "bearer " + token, "Content-Type": "application/json", "User-Agent": "profile-stats"})
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.load(r)
    if "errors" in res:
        sys.exit("GraphQL error: " + json.dumps(res["errors"]))
    u = res["data"]["user"]
    cal = u["contributionsCollection"]["contributionCalendar"]
    days = []
    for w in cal["weeks"]:
        for d in w["contributionDays"]:
            days.append({"date": d["date"], "count": d["contributionCount"],
                         "level": LEVEL_NAMES.get(d["contributionLevel"], 0)})
    return {"total": cal["totalContributions"], "days": days, "repos": u["repositories"]["totalCount"]}


def summarise(data):
    days = sorted(data["days"], key=lambda d: d["date"])
    counts = [d["count"] for d in days]
    longest = run = 0
    for c in counts:
        run = run + 1 if c > 0 else 0
        longest = max(longest, run)
    cur = 0
    i = len(counts) - 1
    if i >= 0 and counts[i] == 0:  # today may not have activity yet
        i -= 1
    while i >= 0 and counts[i] > 0:
        cur += 1
        i -= 1
    return {
        "total": data["total"],
        "current": cur,
        "longest": longest,
        "best": max(counts) if counts else 0,
        "active": sum(1 for c in counts if c > 0),
        "repos": data["repos"],
        "days": days,
    }


# ---------------------------------------------------------------- canvas
def rgb(c):
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


class Canvas:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.buf = bytearray(w * h * 4)

    def px(self, x, y, c, a=255):
        if not (0 <= x < self.w and 0 <= y < self.h):
            return
        r, g, b = rgb(c) if isinstance(c, str) else c
        i = (y * self.w + x) * 4
        if a >= 255:
            self.buf[i:i + 4] = bytes((r, g, b, 255))
            return
        sa = a / 255
        da = self.buf[i + 3] / 255
        oa = sa + da * (1 - sa)
        if oa <= 0:
            return
        for k, v in enumerate((r, g, b)):
            self.buf[i + k] = int(round((v * sa + self.buf[i + k] * da * (1 - sa)) / oa))
        self.buf[i + 3] = int(round(oa * 255))

    def rect(self, x, y, w, h, c, a=255):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.px(xx, yy, c, a)

    def rrect(self, x, y, w, h, c, corner):
        for yy in range(h):
            inset = 0
            if yy < len(corner):
                inset = corner[yy]
            elif yy >= h - len(corner):
                inset = corner[h - 1 - yy]
            for xx in range(x + inset, x + w - inset):
                self.px(xx, y + yy, c)

    def png(self, k):
        rows = []
        for y in range(self.h):
            row = self.buf[y * self.w * 4:(y + 1) * self.w * 4]
            wide = bytearray()
            for x in range(self.w):
                wide += bytes(row[x * 4:x * 4 + 4]) * k
            line = b"\x00" + bytes(wide)
            rows.append(line * k)
        raw = b"".join(rows)

        def chunk(t, d):
            return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
        ihdr = struct.pack(">IIBBBBB", self.w * k, self.h * k, 8, 6, 0, 0, 0)
        return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def window(cv):
    w, h = cv.w, cv.h
    cv.rrect(0, 0, w, h, INK, [3, 1, 1])
    cv.rrect(1, 1, w - 2, h - 2, "#CFC4EA", [2, 1])
    for yy in range(2, h - 2):
        cv.px(w - 2, yy, "#4A3C7A")
    for xx in range(2, w - 2):
        cv.px(xx, h - 2, "#4A3C7A")
    cv.rrect(2, 2, w - 4, h - 4, "#6F5FA6", [1])
    cv.rrect(3, 3, w - 6, h - 6, INK, [1])
    top, bot = rgb("#1A0F3D"), rgb("#0E0826")
    steps = 6
    cols = [tuple(int(round(top[i] + (bot[i] - top[i]) * s / (steps - 1))) for i in range(3)) for s in range(steps)]
    ih = h - 8
    for yy in range(ih):
        t = yy / max(1, ih - 1) * (steps - 1)
        lo = int(t)
        fr = t - lo
        for xx in range(w - 8):
            thr = (BAYER4[(4 + yy) % 4][(4 + xx) % 4] + 0.5) / 16
            cv.px(4 + xx, 4 + yy, cols[min(steps - 1, lo + (1 if fr > thr else 0))])


def text_width(font, s, scale=1, tracking=0):
    g = GLYPHS[font]["glyphs"]
    return sum((g.get(ch, g["?"])["a"] + tracking) * scale for ch in s) - tracking * scale


def text(cv, font, s, x, y, col=CREAM, scale=1, bands=None, shadow=None, tracking=0):
    """Draw text with its cap top at y. Optional 1px ink outline+shadow via shadow=(dx, dy)."""
    f = GLYPHS[font]
    cap = f["cap"]
    base = y + cap * scale
    cells = []
    pen = x
    for ch in s:
        gl = f["glyphs"].get(ch, f["glyphs"]["?"])
        for j, row in enumerate(gl["r"]):
            for i, bit in enumerate(row):
                if bit == "1":
                    for sy in range(scale):
                        for sx in range(scale):
                            cells.append((pen + (gl["x"] + i) * scale + sx, base + (gl["y"] + j) * scale + sy,
                                          (gl["y"] + j + cap) * scale + sy))
        pen += (gl["a"] + tracking) * scale
    if shadow:
        on = {(cx, cy) for cx, cy, _ in cells}
        ring = set()
        for (cx, cy) in on:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    ring.add((cx + dx, cy + dy))
        ring -= on
        for (cx, cy) in on | ring:
            cv.px(cx + shadow[0], cy + shadow[1], "#5A1F4F")
        for (cx, cy) in ring:
            cv.px(cx, cy, INK)
    for (cx, cy, ry) in cells:
        c = col
        if bands:
            for r0, bc in bands:
                if ry >= r0 * scale:
                    c = bc
        cv.px(cx, cy, c)
    return pen - x


def fmt(n):
    return f"{n:,}"


# ------------------------------------------------------------------- draw
def draw(st, phone, today):
    W = 180 if phone else 320
    weeks_shown = 30 if phone else 53
    days = st["days"]
    # group into weeks (Sunday-start, as GitHub does)
    weeks = []
    for d in days:
        date = dt.date.fromisoformat(d["date"])
        dow = (date.weekday() + 1) % 7
        if not weeks or dow == 0:
            weeks.append([None] * 7)
        weeks[-1][dow] = (date, d["count"], d["level"])
    weeks = weeks[-weeks_shown:]
    pitch, cell = 5, 4
    gw = len(weeks) * pitch - 1
    if phone:
        stat_y = 47
        grid_y = 106
    else:
        stat_y = 10
        grid_y = 62
    H = grid_y + 7 * pitch + 30
    cv = Canvas(W, H)
    window(cv)
    # headline number
    text(cv, "tiny", "CONTRIBUTIONS IN THE LAST YEAR", 14, 11, LILAC)
    text(cv, "jersey", fmt(st["total"]), 14, 20, scale=2, bands=GOLD_BANDS, shadow=(1, 1))
    # stat cells
    cells = [("CURRENT STREAK", f"{st['current']} day" + ("" if st["current"] == 1 else "s")),
             ("LONGEST STREAK", f"{st['longest']} day" + ("" if st["longest"] == 1 else "s")),
             ("BEST DAY", fmt(st["best"])),
             ("PUBLIC REPOS", fmt(st["repos"]))]
    if phone:
        x0, colw = 14, 80
    else:
        x0, colw = 150, 82
    for i, (lab, val) in enumerate(cells):
        cx = x0 + (i % 2) * colw
        cy = stat_y + (i // 2) * 22
        cv.rect(cx - 4, cy - 2, 2, 18, "#3A2C66")
        text(cv, "tiny", lab, cx, cy + 1, LILAC)
        text(cv, "jersey", val, cx, cy + 8, CREAM)
    # contribution grid: each day is a block, brighter = more contributions
    gx = (W - gw) // 2
    for wi, wk in enumerate(weeks):
        for di, d in enumerate(wk):
            if d is None:
                continue
            lvl = d[2]
            x, y = gx + wi * pitch, grid_y + di * pitch
            cv.rect(x, y, cell, cell, LEVELS[lvl])
            if lvl >= 2:
                cv.px(x, y, "#FFF6D6")
            if lvl == 0:
                cv.px(x + cell - 1, y + cell - 1, "#170F38")
    # month labels at the first full week of each month
    last_x = -99
    for wi, wk in enumerate(weeks):
        first = next((d for d in wk if d), None)
        if first and first[0].day <= 7:
            x = gx + wi * pitch
            if x - last_x >= 18 and x + 12 < W - 6:
                text(cv, "tiny", MONTHS[first[0].month - 1], x, grid_y + 7 * pitch + 2, DIM)
                last_x = x
    # footer
    fy = grid_y + 7 * pitch + 12
    stamp = f"UPDATED {today.day} {MONTHS[today.month - 1]} {today.year}"
    text(cv, "tiny", stamp, 14, fy, DIM)
    if phone:
        return finish(cv, st, W, H, gx, gw, grid_y, pitch, weeks)
    lx = W - 14 - (5 * pitch - 1) - text_width("tiny", "MORE") - text_width("tiny", "LESS") - 8
    text(cv, "tiny", "LESS", lx, fy, DIM)
    lx += text_width("tiny", "LESS") + 4
    for i, c in enumerate(LEVELS):
        cv.rect(lx + i * pitch, fy, cell, cell, c)
    text(cv, "tiny", "MORE", lx + 5 * pitch + 3, fy, DIM)
    return finish(cv, st, W, H, gx, gw, grid_y, pitch, weeks)


def finish(cv, st, W, H, gx, gw, grid_y, pitch, weeks):

    # ---------------------------------------------------------------- svg
    WW, HH = W * K, H * K
    base = base64.b64encode(cv.png(K)).decode()
    cat = base64.b64encode(open(os.path.join(HERE, "cat-run.png"), "rb").read()).decode()
    T = 14.0
    run_w = gw * K
    cat_y = grid_y * K - 46 + 2
    css = (
        "image{image-rendering:pixelated}"
        f".scan{{animation:scan {T}s steps({len(weeks)},end) infinite}}"
        f".walk{{animation:walk {T}s linear infinite}}"
        ".run{animation:run .44s steps(4,end) infinite}"
        f"@keyframes scan{{from{{transform:translateX(0px)}}to{{transform:translateX({run_w + 4}px)}}}}"
        f"@keyframes walk{{from{{transform:translateX({-30}px)}}to{{transform:translateX({run_w - 20}px)}}}}"
        "@keyframes run{from{transform:translateX(0px)}to{transform:translateX(-232px)}}"
        "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WW} {HH}" width="{WW}" height="{HH}">'
        f"<title>High scores: {fmt(st['total'])} contributions in the last year</title>"
        f"<style>{css}</style>"
        f'<defs><clipPath id="cc"><rect width="58" height="46"/></clipPath>'
        f'<clipPath id="gc"><rect x="{gx*K}" y="{grid_y*K - 60}" width="{run_w}" height="{7*pitch*K + 60}"/></clipPath></defs>'
        f'<image width="{WW}" height="{HH}" href="data:image/png;base64,{base}"/>'
        f'<g clip-path="url(#gc)">'
        f'<rect class="scan" x="{gx*K - 2}" y="{grid_y*K - 2}" width="{pitch*K}" height="{7*pitch*K}" fill="#FFFFFF" opacity=".16"/>'
        f'<g transform="translate({gx*K} {cat_y})"><g class="walk"><g clip-path="url(#cc)"><g class="run">'
        f'<image width="232" height="46" href="data:image/png;base64,{cat}"/></g></g></g></g>'
        f"</g></svg>"
    )
    return svg


def main():
    args = sys.argv[1:]
    if "--data" in args:
        data = json.load(open(args[args.index("--data") + 1]))
    else:
        data = fetch()
    st = summarise(data)
    today = dt.date.fromisoformat(st["days"][-1]["date"]) if st["days"] else dt.date.today()
    out_dir = os.path.join(ROOT, "assets")
    os.makedirs(out_dir, exist_ok=True)
    for phone, name in ((False, "stats.svg"), (True, "stats-m.svg")):
        open(os.path.join(out_dir, name), "w").write(draw(st, phone, today))
    print(json.dumps({k: v for k, v in st.items() if k != "days"}))


if __name__ == "__main__":
    main()
