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
MINT, MINT_D, FIELD = "#6EE6CE", "#3FC2A7", "#0F1014"
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
    days = sorted(data["days"], key=lambda d: d["date"])
    counts = [d["count"] for d in days]
    longest = run = 0
    for c in counts:
        run = run + 1 if c > 0 else 0
        longest = max(longest, run)
    weeks = []  # (first date, total), Sunday-start like the GitHub calendar
    for d in days:
        date = dt.date.fromisoformat(d["date"])
        if not weeks or (date.weekday() + 1) % 7 == 0:
            weeks.append([date, 0])
        weeks[-1][1] += d["count"]
    return {"total": data["total"], "longest": longest, "best": max(counts) if counts else 0,
            "active": sum(1 for c in counts if c > 0), "repos": data["repos"], "weeks": weeks,
            "today": dt.date.fromisoformat(days[-1]["date"]) if days else dt.date.today()}


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


def draw(st, phone):
    doc = Doc()
    W = 720 if phone else 1200
    weeks = st["weeks"][-26:] if phone else st["weeks"][-53:]
    vals = [w[1] for w in weeks]
    vmax = max(vals) if vals and max(vals) > 0 else 1
    best_i = vals.index(max(vals)) if vals else 0
    el = []
    # headline
    if phone:
        big, _ = doc.text("display", fmt(st["total"]), 64, 36, 104, fill=MINT, tracking=-0.01)
        lab, _ = doc.text("ui", "contributions in the last year", 22, 36, 142, fill=SUB, tracking=-0.01)
        el += [big, lab]
        stats_y, cell_w, x0 = 196, 216, 36
        chart = (30, 270, W - 60, 220)
    else:
        big, bw = doc.text("display", fmt(st["total"]), 76, 46, 120, fill=MINT, tracking=-0.01)
        lab, _ = doc.text("ui", "contributions in the last year", 24, 48, 158, fill=SUB, tracking=-0.01)
        el += [big, lab]
        stats_y, cell_w, x0 = 100, 190, W - 48 - 3 * 190
        chart = (40, 196, W - 80, 200)
    stats = [(plural(st["longest"], "day"), "Longest streak"),
             (fmt(st["best"]), "Best day"),
             (fmt(st["repos"]), "Public repos")]
    vs = 34 if phone else 40
    ls = 18 if phone else 20
    widths = [max(doc.text("display", v, vs, 0, 0, tracking=-0.01)[1], doc.text("ui", l, ls, 0, 0, tracking=-0.01)[1])
              for v, l in stats]
    if phone:
        xs = [x0 + i * cell_w for i in range(3)]
    else:
        gap = 64
        xs = []
        x = W - 48
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
    # chart frame
    cx0, cy0, cw, ch = chart
    el.append(f'<rect x="{cx0}" y="{cy0}" width="{cw}" height="{ch}" rx="18" fill="{FIELD}" '
              f'stroke="#fff" stroke-width="1.5" stroke-opacity=".1"/>')
    padx, top, bottom = 24, 44, 46
    base = cy0 + ch - bottom
    hmax = ch - top - bottom
    for k in (1, 2, 3):
        gy = base - hmax * k / 3
        el.append(f'<path d="M{cx0 + padx} {gy:.1f} H{cx0 + cw - padx}" stroke="#fff" stroke-opacity=".06" '
                  f'stroke-width="1.5" stroke-dasharray="4 6"/>')
    el.append(f'<path d="M{cx0 + padx} {base} H{cx0 + cw - padx}" stroke="#fff" stroke-opacity=".12" stroke-width="1.5"/>')
    n = len(weeks)
    pitch = (cw - 2 * padx) / max(1, n)
    bwid = pitch * 0.62
    bars = []
    for i, (d, v) in enumerate(weeks):
        x = cx0 + padx + i * pitch + (pitch - bwid) / 2
        if v == 0:
            bars.append(f'<rect x="{x:.1f}" y="{base - 3:.1f}" width="{bwid:.1f}" height="3" rx="1.5" fill="#fff" fill-opacity=".1"/>')
            continue
        h = max(6, hmax * v / vmax)
        op = 0.55 + 0.45 * (v / vmax)
        fill = MINT if i == best_i else MINT_D
        bars.append(f'<rect x="{x:.1f}" y="{base - h:.1f}" width="{bwid:.1f}" height="{h:.1f}" rx="{min(5, bwid/2):.1f}" '
                    f'fill="{fill}" fill-opacity="{op:.2f}"/>')
    el += bars
    # best week label
    if vals and max(vals) > 0:
        bx = cx0 + padx + best_i * pitch + pitch / 2
        by = base - hmax - 12
        label = f"Best week {fmt(max(vals))}"
        lw = doc.text("ui_b", label, 17, 0, 0)[1]
        lx = min(max(bx - lw / 2, cx0 + padx), cx0 + cw - padx - lw)
        t, _ = doc.text("ui_b", label, 17, lx, by, fill=MINT)
        el.append(t)
    # month labels at the first week of each month
    last = -99
    for i, (d, v) in enumerate(weeks):
        first_day = d
        if i == 0 or first_day.day <= 7:
            x = cx0 + padx + i * pitch + pitch / 2
            if x - last < (52 if phone else 60) or x > cx0 + cw - padx - 20:
                continue
            m = (first_day + dt.timedelta(days=6)).month if i == 0 and first_day.day > 7 else first_day.month
            t, _ = doc.text("ui", MONTHS[m - 1], 16, x, base + 28, fill=MUTED, anchor="middle")
            el.append(t)
            last = x
    # playhead sweeping across the weeks
    T = 14
    span = cw - 2 * padx
    el.append(f'<g class="ph"><rect x="{cx0 + padx - 1}" y="{cy0 + 18}" width="2" height="{base - cy0 - 18}" fill="{MINT}" '
              f'fill-opacity=".85"/><rect x="{cx0 + padx - 9}" y="{cy0 + 18}" width="18" height="{base - cy0 - 18}" '
              f'fill="url(#phg)"/><circle cx="{cx0 + padx}" cy="{cy0 + 18}" r="4.5" fill="{MINT}"/></g>')
    css = (f".ph{{animation:ph {T}s linear infinite}}"
           f"@keyframes ph{{0%{{transform:translateX(0px);opacity:0}}4%{{opacity:1}}92%{{opacity:1}}"
           f"100%{{transform:translateX({span:.1f}px);opacity:0}}}}"
           "@media (prefers-reduced-motion:reduce){.ph{animation:none;opacity:0}}")
    # footer
    fy = cy0 + ch + 34
    up = f"Updated {st['today'].day} {MONTHS[st['today'].month - 1]} {st['today'].year}"
    t, _ = doc.text("ui", up, 17, 46 if not phone else 36, fy, fill=MUTED, tracking=-0.01)
    el.append(t)
    if not phone:
        t, _ = doc.text("ui", "Weekly contributions, last 12 months", 17, W - 48, fy, fill=MUTED, anchor="end", tracking=-0.01)
        el.append(t)
    else:
        t, _ = doc.text("ui", "Weekly, last 6 months", 17, W - 36, fy, fill=MUTED, anchor="end", tracking=-0.01)
        el.append(t)
    H = int(fy + 30)
    title = f"Activity: {fmt(st['total'])} contributions in the last year"
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img">'
           f"<title>{title}</title><style>{css}</style><defs>"
           f'<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1A1B21"/>'
           f'<stop offset="1" stop-color="#141418"/></linearGradient>'
           f'<linearGradient id="edge" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".16"/>'
           f'<stop offset=".5" stop-color="#fff" stop-opacity=".07"/><stop offset="1" stop-color="#fff" stop-opacity=".05"/></linearGradient>'
           f'<linearGradient id="phg" x1="0" x2="1"><stop offset="0" stop-color="{MINT}" stop-opacity="0"/>'
           f'<stop offset=".5" stop-color="{MINT}" stop-opacity=".18"/><stop offset="1" stop-color="{MINT}" stop-opacity="0"/></linearGradient>'
           f"{doc.defs()}</defs>"
           f'<rect width="{W}" height="{H}" rx="30" fill="url(#bg)"/>'
           f'{"".join(el)}'
           f'<rect x=".75" y=".75" width="{W - 1.5}" height="{H - 1.5}" rx="29.25" fill="none" stroke="url(#edge)" stroke-width="1.5"/>'
           f"</svg>")
    return svg


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
    print(json.dumps({k: v for k, v in st.items() if k not in ("weeks", "today")}))


if __name__ == "__main__":
    main()
