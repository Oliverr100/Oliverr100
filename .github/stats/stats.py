#!/usr/bin/env python3
"""Draws the Activity panel (assets/stats.svg and assets/stats-m.svg) from public
GitHub activity. Standard library only, so the workflow needs no installs.

Usage:
  GITHUB_TOKEN=... python3 .github/stats/stats.py            # fetch + draw
  python3 .github/stats/stats.py --data sample.json          # draw from saved data

Lettering comes from glyphs.json: outlines of Unbounded and Familjen Grotesk
(both SIL Open Font License 1.1), so the SVG needs no web fonts.
"""
import datetime as dt
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
LOGIN = os.environ.get("STATS_LOGIN", "Oliverr100")

TXT, WHITE, SUB, MUTED = "#EEF1F6", "#FFFFFF", "#9AA3B2", "#6B7384"
MINT, FIELD = "#6EE6CE", "#0F1014"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

GL = json.load(open(os.path.join(HERE, "glyphs.json"), encoding="utf-8"))

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
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
    days = [{"date": d["date"], "count": d["contributionCount"]}
            for w in cal["weeks"] for d in w["contributionDays"]]
    return {"total": cal["totalContributions"], "days": days, "repos": u["repositories"]["totalCount"]}


def summarise(data):
    days = sorted(({"date": dt.date.fromisoformat(d["date"]), "count": d["count"]} for d in data["days"]),
                  key=lambda d: d["date"])
    counts = [d["count"] for d in days]
    longest = run = 0
    for c in counts:
        run = run + 1 if c > 0 else 0
        longest = max(longest, run)
    best = max(days, key=lambda d: (d["count"], d["date"])) if days else None
    # columns of 7 days, Sunday first, like the GitHub calendar
    weeks = []
    for d in days:
        if not weeks or (d["date"].weekday() + 1) % 7 == 0:
            weeks.append([])
        weeks[-1].append(d)
    return {"total": data["total"], "longest": longest, "best": best["count"] if best else 0,
            "best_date": best["date"] if best and best["count"] else None,
            "active": sum(1 for c in counts if c > 0), "repos": data["repos"], "weeks": weeks,
            "today": days[-1]["date"] if days else dt.date.today()}


# ------------------------------------------------------------------ svg
class Doc:
    def __init__(self):
        self.used = {}

    def text(self, font, s, size, x, y, fill=TXT, anchor="start", tracking=0.0):
        F = GL[font]
        upem = F["upem"]
        sc = size / upem
        pen = 0
        xs = []
        for i, ch in enumerate(s):
            g = F["glyphs"].get(ch) or F["glyphs"]["?"]
            xs.append(pen)
            pen += g[0] + tracking * upem
            if i + 1 < len(s):
                pen += F["kern"].get(ch + s[i + 1], 0)
        w = (pen - tracking * upem) * sc
        if anchor == "end":
            x -= w
        elif anchor == "middle":
            x -= w / 2
        uses = []
        for ch, px in zip(s, xs):
            if ch == " " or ch not in F["glyphs"]:
                continue
            gid = f"{font[0]}{'b' if font == 'ui_b' else ''}{ord(ch)}"
            self.used[gid] = F["glyphs"][ch][1]
            uses.append(f'<use href="#{gid}" x="{round(px)}"/>')
        return (f'<g transform="translate({x:.1f} {y:.1f}) scale({sc:.5f} {-sc:.5f})" fill="{fill}">'
                f'{"".join(uses)}</g>'), w

    def defs(self):
        return "".join(f'<path id="{k}" d="{v}"/>' for k, v in self.used.items())


def fmt(n):
    return f"{n:,}"


def plural(n, word):
    return f"{fmt(n)} {word}" + ("" if n == 1 else "s")


def mix(a, b, t):
    """Blend hex colour a towards b by t (0..1)."""
    pa = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    pb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(pa, pb))


LEVELS = [None, mix(FIELD, MINT, .28), mix(FIELD, MINT, .48), mix(FIELD, MINT, .72), MINT]


def levels(weeks):
    """Map counts to 0..4 using quartiles of the non-zero days (as GitHub does)."""
    nz = sorted(d["count"] for w in weeks for d in w if d["count"] > 0)
    if not nz:
        return lambda c: 0
    q = [nz[min(len(nz) - 1, int(len(nz) * k))] for k in (0.25, 0.5, 0.75)]

    def lv(c):
        if c <= 0:
            return 0
        if c <= q[0]:
            return 1
        if c <= q[1]:
            return 2
        if c <= q[2]:
            return 3
        return 4
    return lv


def draw(st, phone):
    doc = Doc()
    W = 720 if phone else 1200
    weeks = st["weeks"][-26:] if phone else st["weeks"][-53:]
    lv = levels(weeks)
    el = []
    # ---------------------------------------------------------- headline + stats
    if phone:
        big, _ = doc.text("display", fmt(st["total"]), 64, 36, 104, fill=MINT, tracking=-0.01)
        lab, _ = doc.text("ui", "contributions in the last year", 22, 36, 142, fill=SUB, tracking=-0.01)
        el += [big, lab]
        stats_y = 206
        frame = (30, 254, W - 60)
    else:
        big, _ = doc.text("display", fmt(st["total"]), 76, 46, 120, fill=MINT, tracking=-0.01)
        lab, _ = doc.text("ui", "contributions in the last year", 24, 48, 158, fill=SUB, tracking=-0.01)
        el += [big, lab]
        stats_y = 100
        frame = (40, 196, W - 80)
    stats = [(plural(st["longest"], "day"), "Longest streak"),
             (fmt(st["best"]), "Best day"),
             (fmt(st["repos"]), "Public repos")]
    vs = 34 if phone else 40
    ls = 18 if phone else 20
    widths = [max(doc.text("display", v, vs, 0, 0, tracking=-0.01)[1], doc.text("ui", l, ls, 0, 0, tracking=-0.01)[1])
              for v, l in stats]
    if phone:
        xs = [36 + i * 216 for i in range(3)]
    else:
        gap, xs, x = 64, [], W - 48
        for w_ in reversed(widths):
            x -= w_
            xs.insert(0, x)
            x -= gap
    for i, (v, l) in enumerate(stats):
        cx = xs[i]
        if not phone or i:
            el.append(f'<rect x="{cx - (30 if not phone else 14):.1f}" y="{stats_y - (40 if not phone else 34)}" width="1.5" '
                      f'height="{70 if not phone else 60}" fill="#fff" fill-opacity=".1"/>')
        vt, _ = doc.text("display", v, vs, cx, stats_y, fill=WHITE, tracking=-0.01)
        lt, _ = doc.text("ui", l, ls, cx, stats_y + (28 if phone else 32), fill=MUTED, tracking=-0.01)
        el += [vt, lt]

    # ---------------------------------------------------------- calendar heatmap
    fx, fy, fw = frame
    pad = 18 if phone else 24
    lab_w = 42 if phone else 48
    month_h = 30
    gx0 = fx + pad + lab_w
    gx1 = fx + fw - pad
    n = len(weeks)
    pitch = (gx1 - gx0) / max(1, n)
    cell = pitch * 0.8
    gy0 = fy + 20 + month_h
    fh = 20 + month_h + 7 * pitch + 22
    el.append(f'<rect x="{fx}" y="{fy}" width="{fw}" height="{fh:.1f}" rx="18" fill="{FIELD}" '
              f'stroke="#fff" stroke-width="1.5" stroke-opacity=".1"/>')
    for row, name in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        t, _ = doc.text("ui", name, 15 if phone else 16, fx + pad, gy0 + row * pitch + cell * 0.5 + 5.5, fill=MUTED)
        el.append(t)
    # month labels where a month begins; a partial first month gives way to the next label
    marks = []
    for i, w in enumerate(weeks):
        first = w[0]["date"]
        m = next((d["date"].month for d in w if d["date"].day == 1), None)
        if i == 0 and m is None:
            m = first.month
        if m is not None and i <= n - 2:
            marks.append((i, m))
    keep = [mk for j, mk in enumerate(marks) if j + 1 >= len(marks) or marks[j + 1][0] - mk[0] >= 3]
    for i, m in keep:
        t, _ = doc.text("ui", MONTHS[m - 1], 15 if phone else 16, gx0 + i * pitch, fy + 20 + 16, fill=MUTED)
        el.append(t)
    cells = []
    today = st["today"]
    for i, w in enumerate(weeks):
        for d in w:
            row = (d["date"].weekday() + 1) % 7
            x = gx0 + i * pitch
            y = gy0 + row * pitch
            k = lv(d["count"])
            if k == 0:
                cells.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell:.1f}" height="{cell:.1f}" rx="3.5" '
                             f'fill="#fff" fill-opacity=".055"/>')
            else:
                cells.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell:.1f}" height="{cell:.1f}" rx="3.5" fill="{LEVELS[k]}"/>')
            if d["date"] == st["best_date"]:
                cells.append(f'<rect x="{x - 3:.1f}" y="{y - 3:.1f}" width="{cell + 6:.1f}" height="{cell + 6:.1f}" rx="5.5" '
                             f'fill="none" stroke="{MINT}" stroke-opacity=".55" stroke-width="1.5"/>')
            if d["date"] == today:
                cells.append(f'<rect class="td" x="{x - 3:.1f}" y="{y - 3:.1f}" width="{cell + 6:.1f}" height="{cell + 6:.1f}" '
                             f'rx="5.5" fill="none" stroke="#fff" stroke-width="1.5"/>')
    el += cells
    # scanner sweeping across the weeks
    T = 14
    span = n * pitch
    top, bot = gy0 - 8, gy0 + 7 * pitch - (pitch - cell) + 8
    el.append(f'<g class="ph"><rect x="{gx0 - 11:.1f}" y="{top:.1f}" width="22" height="{bot - top:.1f}" fill="url(#phg)"/>'
              f'<rect x="{gx0 - 1:.1f}" y="{top:.1f}" width="2" height="{bot - top:.1f}" rx="1" fill="{MINT}" fill-opacity=".9"/></g>')
    css = (f".ph{{animation:ph {T}s linear infinite}}"
           f"@keyframes ph{{0%{{transform:translateX(0px);opacity:0}}4%{{opacity:1}}92%{{opacity:1}}"
           f"100%{{transform:translateX({span:.1f}px);opacity:0}}}}"
           ".td{animation:td 2.4s ease-in-out infinite}@keyframes td{50%{stroke-opacity:.15}}"
           "@media (prefers-reduced-motion:reduce){.ph{animation:none;opacity:0}.td{animation:none}}")
    # ---------------------------------------------------------- footer + legend
    foot = fy + fh + 34
    up = f"Updated {today.day} {MONTHS[today.month - 1]} {today.year}"
    t, _ = doc.text("ui", up, 17, 36 if phone else 46, foot, fill=MUTED, tracking=-0.01)
    el.append(t)
    sw, gap = (15, 5) if phone else (16, 5)
    xr = W - (36 if phone else 48)
    more, mw = doc.text("ui", "More", 17, xr, foot, fill=MUTED, anchor="end", tracking=-0.01)
    x = xr - mw - 10 - 5 * sw - 4 * gap
    sy = foot - 13
    for k in range(5):
        fill = 'fill="#fff" fill-opacity=".055"' if k == 0 else f'fill="{LEVELS[k]}"'
        el.append(f'<rect x="{x + k * (sw + gap):.1f}" y="{sy}" width="{sw}" height="{sw}" rx="3.5" {fill}/>')
    less, _ = doc.text("ui", "Less", 17, x - 10, foot, fill=MUTED, anchor="end", tracking=-0.01)
    el += [less, more]
    H = int(foot + 30)
    title = f"Activity: {fmt(st['total'])} contributions in the last year"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img">'
            f"<title>{title}</title><style>{css}</style><defs>"
            f'<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1A1B21"/>'
            f'<stop offset="1" stop-color="#141418"/></linearGradient>'
            f'<linearGradient id="edge" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".16"/>'
            f'<stop offset=".5" stop-color="#fff" stop-opacity=".07"/><stop offset="1" stop-color="#fff" stop-opacity=".05"/></linearGradient>'
            f'<linearGradient id="phg" x1="0" x2="1"><stop offset="0" stop-color="{MINT}" stop-opacity="0"/>'
            f'<stop offset=".5" stop-color="{MINT}" stop-opacity=".22"/><stop offset="1" stop-color="{MINT}" stop-opacity="0"/></linearGradient>'
            f"{doc.defs()}</defs>"
            f'<rect width="{W}" height="{H}" rx="30" fill="url(#bg)"/>'
            f'{"".join(el)}'
            f'<rect x=".75" y=".75" width="{W - 1.5}" height="{H - 1.5}" rx="29.25" fill="none" stroke="url(#edge)" stroke-width="1.5"/>'
            f"</svg>")


def main():
    args = sys.argv[1:]
    if "--data" in args:
        data = json.load(open(args[args.index("--data") + 1]))
    else:
        data = fetch()
    st = summarise(data)
    out_dir = os.path.join(ROOT, "assets")
    os.makedirs(out_dir, exist_ok=True)
    for phone, name in ((False, "stats.svg"), (True, "stats-m.svg")):
        open(os.path.join(out_dir, name), "w", encoding="utf-8").write(draw(st, phone))
    print(json.dumps({k: (v.isoformat() if isinstance(v, dt.date) else v)
                      for k, v in st.items() if k not in ("weeks", "today")}))


if __name__ == "__main__":
    main()
