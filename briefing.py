#!/usr/bin/env python3
"""
Morning Briefing – Generator (Etappe 2, öffentlicher Teil).

Baut die Seite index.html neu: Begrüßung, Wetter (Münster), Märkte (DAX/MSCI World)
und Nachrichten-Cluster mit kurzen KI-Zusammenfassungen. Schreibt index.html +
manifest.json ins Repo-Wurzelverzeichnis – GitHub Pages zeigt sie dann an.

Persönliche Blöcke (Whoop, Fotos, Agenda, Geburtstag) bleiben bewusst NICHT hier,
sondern kommen später im iPhone-Kurzbefehl (Etappe 3) – die bleiben am Gerät.

Läuft automatisch per GitHub Actions. Nichts manuell starten.
"""

import os, html, datetime as dt
import requests, feedparser

# ---------------------------------------------------------------- Konfiguration
NAME = "Daniel"
LAT, LON = 51.96, 7.63          # Münster
MAX_PER_CLUSTER = 3

# Nachrichten-Cluster in Anzeige-Reihenfolge: (Titel, [Feed-URLs], Quellenname)
CLUSTERS = [
    ("Politik & Welt", ["https://www.tagesschau.de/index~rss2.xml"], "Tagesschau"),
    ("Wirtschaft & Finanzen", ["https://www.handelsblatt.com/contentexport/feed/finanzen"], "Handelsblatt"),
    ("Künstliche Intelligenz & Tech",
     ["https://news.google.com/rss/search?q=artificial+intelligence&hl=en-US&gl=US&ceid=US:en"], "KI-News"),
    ("Mesum & Rheine",
     ["https://news.google.com/rss/search?q=%22Mesum%22+OR+%22Rheine%22+Stadt&hl=de&gl=DE&ceid=DE:de"], "MV / Lokal"),
    ("Genossenschaftsbanken & Atruvia",
     ["https://news.google.com/rss/search?q=Genossenschaftsbank+OR+Atruvia+OR+BVR&hl=de&gl=DE&ceid=DE:de"], "Geno-News"),
    ("FC Bayern", ["https://fcbinside.de/feed"], "FCBinside"),
]

QUOTES = [
    ("Es ist nicht wenig Zeit, die wir haben, sondern es ist viel Zeit, die wir nicht nutzen.", "Seneca"),
    ("Der Anfang ist die Hälfte des Ganzen.", "Aristoteles"),
    ("Wer ein Warum zum Leben hat, erträgt fast jedes Wie.", "Friedrich Nietzsche"),
    ("Qualität ist kein Zufall; sie ist immer das Ergebnis angestrengten Denkens.", "John Ruskin"),
    ("Das Geheimnis des Vorwärtskommens besteht darin, den ersten Schritt zu tun.", "Mark Twain"),
]

C = dict(paper="#FCFCFA", card="#FFFFFF", ink="#1A1B1D", ink_soft="#46484D",
         meta="#8C8B85", hair="#ECEBE6", accent="#33524F", warm="#C2613B",
         cool="#5E7E97", mild="#8FA68C")
WMO = {0:"\u2600",1:"\u2600",2:"\u26C5",3:"\u2601",45:"\u2601",48:"\u2601",
       51:"\u2602",53:"\u2602",55:"\u2602",61:"\u2602",63:"\u2602",65:"\u2602",
       71:"\u2603",73:"\u2603",75:"\u2603",80:"\u2602",81:"\u2602",82:"\u2602",
       95:"\u26C8",96:"\u26C8",99:"\u26C8"}
WD = ["Mo","Di","Mi","Do","Fr","Sa","So"]

# ---------------------------------------------------------------- Datenholen
def get_weather():
    u = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
         "&daily=weather_code,temperature_2m_max,temperature_2m_min"
         "&timezone=Europe/Berlin&forecast_days=10" % (LAT, LON))
    d = requests.get(u, timeout=20).json()["daily"]
    out = []
    for i, iso in enumerate(d["time"]):
        date = dt.date.fromisoformat(iso)
        out.append(dict(day=WD[date.weekday()], ico=WMO.get(d["weather_code"][i], "\u2601"),
                        hi=round(d["temperature_2m_max"][i]), lo=round(d["temperature_2m_min"][i]),
                        today=(i == 0)))
    return out

def _fmt(p, cur):
    if cur == "EUR" or (cur is None and p > 1000):
        return f"{p:,.0f}".replace(",", ".")
    s = {"USD": "$", "EUR": "\u20ac"}.get(cur, "")
    return f"{p:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + s

def get_markets():
    out = []
    for name, sym in [("DAX", "^GDAXI"), ("MSCI World", "URTH")]:
        try:
            r = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/" + sym,
                             params={"range": "5d", "interval": "1d"},
                             headers={"User-Agent": "Mozilla/5.0"}, timeout=20).json()
            m = r["chart"]["result"][0]["meta"]
            price, prev = m["regularMarketPrice"], m.get("chartPreviousClose")
            chg = (price - prev) / prev * 100 if prev else 0
            out.append(dict(name=name, val=_fmt(price, m.get("currency")), chg=chg, up=chg >= 0))
        except Exception:
            out.append(dict(name=name, val="\u2013", chg=0, up=True))
    return out

def _strip(t):
    t = html.unescape(t or "")
    while "<" in t and ">" in t:
        t = t[:t.index("<")] + t[t.index(">")+1:]
    return " ".join(t.split())

def summarize(title, raw):
    clean = _strip(raw)
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        s = clean.split(". ")[0]
        return (s[:150] + "\u2026") if len(s) > 150 else s
    try:
        import anthropic
        msg = anthropic.Anthropic(api_key=key).messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=90,
            messages=[{"role": "user", "content":
                "Fasse in EINEM sachlichen deutschen Satz (max. 22 Woerter, kein Vorspann) zusammen:\n"
                "Titel: %s\nText: %s" % (title, clean[:600])}])
        return msg.content[0].text.strip()
    except Exception:
        s = clean.split(". ")[0]
        return (s[:150] + "\u2026") if len(s) > 150 else s

def get_cluster(feeds):
    items = []
    for url in feeds:
        for e in feedparser.parse(url).entries[:MAX_PER_CLUSTER]:
            items.append(e)
        if items:
            break
    return items[:MAX_PER_CLUSTER]

# ---------------------------------------------------------------- HTML
def esc(s): return html.escape(s or "")

def render_weather(days):
    cells = ""
    for d in days:
        cls = "today" if d["today"] else ""
        cells += ('<div class="wx"><div class="wx-day %s">%s</div><div class="wx-ico">%s\ufe0e</div>'
                  '<div class="wx-t">%d<span class="lo">/%d</span></div></div>'
                  % (cls, d["day"], d["ico"], d["hi"], d["lo"]))
    return cells

def render_markets(mk):
    links = {"DAX": "https://www.boerse-frankfurt.de/index/dax",
             "MSCI World": "https://www.ishares.com/us/products/239696/"}
    parts = []
    for i, m in enumerate(mk):
        if i: parts.append('<div class="mkt-sep"></div>')
        cls = "up" if m["up"] else "down"
        arr = "\u25b2" if m["up"] else "\u25bc"
        sign = "+" if m["up"] else ""
        chg = ("%s%.2f" % (sign, m["chg"])).replace(".", ",")
        parts.append('<a class="mkt" href="%s"><span class="nm">%s</span>'
                     '<span class="vl">%s</span><span class="ch %s">%s%s%%</span></a>'
                     % (links.get(m["name"], "#"), esc(m["name"]), m["val"], cls, arr, chg))
    return "".join(parts)

def render_clusters():
    out = ""
    for i, (title, feeds, src) in enumerate(CLUSTERS):
        items = get_cluster(feeds)
        if not items: continue
        rows = ""
        for e in items:
            rows += ('<div class="item"><a class="title" href="%s">%s</a>'
                     '<div class="summary">%s</div>'
                     '<div class="meta"><span class="src">%s</span></div></div>'
                     % (esc(e.get("link", "#")), esc(e.get("title", "")),
                        esc(summarize(e.get("title", ""), e.get("summary", ""))), esc(src)))
        div = '<div class="divider"></div>' if i else ''
        out += ('%s<div class="sec"><div class="eyebrow">%s <span class="count">%d</span></div>'
                '<div style="margin-top:8px;">%s</div></div>' % (div, esc(title), len(items), rows))
    return out

def build():
    days, mk = get_weather(), get_markets()
    quote = QUOTES[dt.date.today().weekday() % len(QUOTES)]
    datum = dt.date.today().strftime("%A, %d. %B %Y")
    page = """<!DOCTYPE html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="manifest" href="manifest.json">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Morning Briefing">
<meta name="theme-color" content="#FCFCFA"><title>Morning Briefing</title><style>
*{box-sizing:border-box}body{margin:0;background:%(paper)s;color:%(ink)s;line-height:1.45;
font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:600px;margin:0 auto;padding:24px 18px 44px}
.card{background:%(card)s;border:1px solid %(hair)s;border-radius:4px;overflow:hidden}
a{color:inherit}
.mast{padding:18px 26px 14px;border-bottom:1px solid %(hair)s;display:flex;justify-content:space-between;align-items:baseline}
.wordmark{font-size:12px;letter-spacing:.3em;text-transform:uppercase;font-weight:600}
.submark{font-size:10.5px;color:%(meta)s;margin-top:3px}
.date{font-size:12px;color:%(meta)s;font-style:italic;text-align:right}
.greet{padding:13px 26px;border-bottom:1px solid %(hair)s}
.hi{font-size:14.5px;font-weight:600}
.quote{margin-top:8px;font-size:12px;font-style:italic;color:%(ink_soft)s}
.quote .by{color:%(meta)s}
.sec{padding:13px 26px}.divider{height:1px;background:%(hair)s;margin:0 26px}
.eyebrow{font-size:9.5px;letter-spacing:.2em;text-transform:uppercase;color:%(accent)s;font-weight:600}
.eyebrow .count{color:%(meta)s;font-weight:500}
.wx-grid{display:flex;margin-top:9px}
.wx{flex:1;text-align:center;border-left:1px solid %(hair)s;padding:0 1px}
.wx:first-child{border-left:none}
.wx-day{font-size:9px;color:%(meta)s;text-transform:uppercase}.wx-day.today{color:%(ink)s;font-weight:700}
.wx-ico{font-size:13px;margin:2px 0;color:%(ink_soft)s}
.wx-t{font-size:11px;font-weight:600}.wx-t .lo{color:%(meta)s;font-weight:400}
.mkt-row{display:flex;align-items:center;gap:16px;margin-top:9px}
.mkt{display:flex;align-items:baseline;gap:6px;text-decoration:none}
.mkt .nm{font-size:9px;text-transform:uppercase;color:%(meta)s;font-weight:600}
.mkt .vl{font-size:13.5px;font-weight:600;color:%(ink)s}.mkt .ch{font-size:11px;font-weight:600}
.mkt-sep{width:1px;height:18px;background:%(hair)s}.up{color:#2F7D5B}.down{color:#A8453A}
.item{padding:9px 0;border-top:1px solid %(hair)s}.item:first-of-type{border-top:none;padding-top:8px}
.item a.title{font-size:13.5px;font-weight:600;color:%(ink)s;text-decoration:none;line-height:1.28}
.summary{margin:3px 0 4px;font-size:12px;color:%(ink_soft)s;line-height:1.4}
.meta{font-size:10px;color:%(meta)s}.meta .src{color:%(accent)s;font-weight:600}
.foot{padding:15px 26px 20px;border-top:1px solid %(hair)s;font-size:10px;color:%(meta)s;line-height:1.5}
</style></head><body><div class="wrap"><div class="card">
<div class="mast"><div><div class="wordmark">Morning Briefing</div><div class="submark">f\xfcr Daniel Overesch</div></div>
<div class="date">%(datum)s</div></div>
<div class="greet"><div class="hi">Guten Morgen, %(name)s</div>
<div class="quote">%(qt)s <span class="by">\u2014 %(qa)s</span></div></div>
<div class="sec"><div class="eyebrow">Wetter <span class="count">10 Tage \xb7 M\xfcnster</span></div>
<div class="wx-grid">%(wx)s</div></div>
<div class="divider"></div>
<div class="sec"><div class="eyebrow">M\xe4rkte <span class="count">Stand 6:30</span></div>
<div class="mkt-row">%(mk)s</div></div>
<div class="divider"></div>
%(clusters)s
<div class="foot">Automatisch erzeugt um 06:30 \xb7 \xdcberschriften verlinken auf die Originalquelle.
Pers\xf6nliche Bl\xf6cke (Whoop, Fotos, Agenda) folgen im iPhone-Kurzbefehl.</div>
</div></div></body></html>""" % dict(
        C, datum=datum, name=NAME, qt=esc(quote[0]), qa=esc(quote[1]),
        wx=render_weather(days), mk=render_markets(mk), clusters=render_clusters())

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(page)
    with open("manifest.json", "w", encoding="utf-8") as f:
        f.write('{"name":"Morning Briefing f\\u00fcr Daniel Overesch","short_name":"Briefing",'
                '"start_url":"./index.html","scope":"./","display":"standalone",'
                '"background_color":"#FCFCFA","theme_color":"#FCFCFA","lang":"de"}')
    print("index.html + manifest.json geschrieben.")

if __name__ == "__main__":
    build()
