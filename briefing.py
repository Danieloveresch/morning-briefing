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

import os, re, html, json, calendar, datetime as dt
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import requests, feedparser

# ---------------------------------------------------------------- Konfiguration
NAME = "Daniel"
LAT, LON = 51.96, 7.63          # Münster
TZ = ZoneInfo("Europe/Berlin")

MAX_PER_CLUSTER     = 3          # angezeigte Meldungen je Cluster
CANDIDATES_PER_FEED = 20         # vorher ziehen, dann filtern (Backfill-Reserve)
DEFAULT_AGE_HOURS   = 30         # bevorzugtes Frischefenster (schnelle Cluster)
HARD_MAX_DAYS       = 10         # älter als das wird nie gezeigt
DUP_THRESHOLD       = 0.5        # Titel-Ähnlichkeit fürs deterministische Netz

# Nischen-Cluster aktualisieren selten -> größeres Fenster, damit aufgefüllt wird
AGE_BY_CLUSTER = {
    "Mesum & Rheine":                  120,   # lokal -> bis 5 Tage zurück
    "Genossenschaftsbanken & Atruvia": 120,   # Fachnische -> bis 5 Tage zurück
}

# Nicht-News / Müll aussortieren (Domain-Teilstrings + Titel-Muster)
BLOCK_DOMAINS = ("wetter.com", "wetter.de")
BLOCK_TITLE   = (re.compile(r"\b\d-tage", re.I), re.compile(r"übersicht", re.I),
                 re.compile(r"livestream", re.I))

GERMAN_STOP = {
    "der","die","das","und","oder","in","im","den","dem","von","mit","für","auf",
    "zu","über","nach","bei","aus","ist","sind","wird","werden","wollen","will",
    "ein","eine","einen","am","an","als","auch","sich","dass","wir","ihre","ihr",
    "sein","seine","mehr","neue","neuer","vor","beim","zur","zum","des","um",
}

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

# Podcasts: (Anzeigename, Suchbegriff). Der Feed wird per Apple-Podcast-Suche
# automatisch aufgelöst -> keine fragilen Feed-URLs, die veralten.
PODCASTS = [
    ("Lanz & Precht",     "Lanz Precht"),
    ("Betreutes Fühlen",  "Betreutes Fühlen Atze Leon Windscheid"),
    ("Lage der Nation",   "Lage der Nation Banse Buermeyer"),
    ("OMR",               "OMR Podcast Westermeyer"),
    ("Finance Forward",   "Finance Forward"),
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
         "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
         "&timezone=Europe/Berlin&forecast_days=10" % (LAT, LON))
    d = requests.get(u, timeout=20).json()["daily"]
    out = []
    for i, iso in enumerate(d["time"]):
        date = dt.date.fromisoformat(iso)
        out.append(dict(day=WD[date.weekday()], ico=WMO.get(d["weather_code"][i], "\u2601"),
                        hi=round(d["temperature_2m_max"][i]), lo=round(d["temperature_2m_min"][i]),
                        rain=d["precipitation_probability_max"][i] or 0,
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

# ---------------------------------------------------------------- Dedup-Hilfen
def _toks(title):
    t = (title or "").lower().split(" - ")[0]        # Outlet-Suffix abschneiden
    t = re.sub(r"[^a-zäöüß0-9 ]", " ", t)
    return {w[:6] for w in t.split() if len(w) > 2 and w not in GERMAN_STOP}

def _dup(a, b, thr=DUP_THRESHOLD):
    ta, tb = _toks(a), _toks(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / min(len(ta), len(tb)) >= thr   # Overlap-Koeffizient

def _entry_dt(e):
    for k in ("published_parsed", "updated_parsed"):
        v = e.get(k)
        if v:
            return datetime.fromtimestamp(calendar.timegm(v), tz=timezone.utc)
    return None

def _blocked(e):
    link = (e.get("link") or "").lower()
    if any(d in link for d in BLOCK_DOMAINS):
        return True
    title = e.get("title") or ""
    return any(p.search(title) for p in BLOCK_TITLE)

def _llm_distinct(cands, n, key):
    """Haiku wählt n inhaltlich verschiedene Schlagzeilen (paraphrasensicher)."""
    import anthropic
    lines = "\n".join("%d. %s" % (i, c.get("title", "")) for i, c in enumerate(cands))
    prompt = ("Hier nummerierte Nachrichten-Schlagzeilen. Manche berichten über "
              "DASSELBE Ereignis bzw. dieselbe Meldung (nur andere Quelle oder "
              "Formulierung) – die sind Dubletten. Wähle %d Schlagzeilen, die "
              "VERSCHIEDENE Ereignisse abdecken; pro Ereignis nur die "
              "aussagekräftigste. Behandle zwei nur dann als gleich, wenn es "
              "wirklich dieselbe Nachricht ist – nicht bloß dasselbe Thema. "
              "Wenn es weniger verschiedene Ereignisse als %d gibt, gib entsprechend "
              "weniger zurück. Antworte NUR mit JSON-Array der Indizes, wichtigste "
              "zuerst, z.B. [0,3,7].\n\n%s" % (n, n, lines))
    msg = anthropic.Anthropic(api_key=key).messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=60,
        messages=[{"role": "user", "content": prompt}])
    raw = msg.content[0].text.strip().strip("`")
    if raw.lower().startswith("json"):
        raw = raw[4:]
    idx = json.loads(raw[raw.index("["):raw.rindex("]") + 1])
    seen, out = set(), []
    for i in idx:
        if isinstance(i, int) and 0 <= i < len(cands) and i not in seen:
            seen.add(i); out.append(cands[i])
    return out[:n]

def _dedupe_simple(cands, n):
    """Deterministisches Netz, falls kein API-Key / Fehler."""
    out = []
    for c in cands:
        if not any(_dup(c.get("title", ""), o.get("title", "")) for o in out):
            out.append(c)
        if len(out) >= n:
            break
    return out

def dedupe_pick(cands, n):
    if len(cands) <= 1:
        return cands[:n]
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key and len(cands) > n:
        try:
            picked = _llm_distinct(cands, n, key)
            if picked:
                return picked
        except Exception:
            pass
    return _dedupe_simple(cands, n)

def get_cluster(feeds, max_age_h):
    """Holt viele Kandidaten, filtert Müll, sortiert neu→alt.
    Bevorzugt frische Meldungen (< max_age_h), hängt aber ältere als
    Auffüll-Reserve hinten an, damit der Block auf MAX_PER_CLUSTER kommt.
    Wirklich Altes (> HARD_MAX_DAYS) fliegt ganz raus."""
    now = datetime.now(timezone.utc)
    hard = timedelta(days=HARD_MAX_DAYS)
    cand, seen_links = [], set()
    for url in feeds:
        for e in feedparser.parse(url).entries[:CANDIDATES_PER_FEED]:
            link = e.get("link", "")
            if (link and link in seen_links) or _blocked(e):
                continue
            ts = _entry_dt(e)
            if ts and (now - ts) > hard:      # uralt -> weg
                continue
            seen_links.add(link)
            cand.append((ts, e))
    cand.sort(key=lambda x: x[0] or datetime(1970, 1, 1, tzinfo=timezone.utc),
              reverse=True)                   # neueste zuerst
    win = timedelta(hours=max_age_h)
    fresh = [e for ts, e in cand if ts and (now - ts) <= win]
    older = [e for ts, e in cand if not (ts and (now - ts) <= win)]
    return fresh + older                      # frisch zuerst, Rest als Backfill

# ---------------------------------------------------------------- HTML
def esc(s): return html.escape(s or "")

def render_weather(days):
    cells = ""
    for d in days:
        cls = "today" if d["today"] else ""
        cells += ('<div class="wx"><div class="wx-day %s">%s</div><div class="wx-ico">%s\ufe0e</div>'
                  '<div class="wx-t">%d<span class="lo">/%d</span></div>'
                  '<div class="wx-r">%d%%</div></div>'
                  % (cls, d["day"], d["ico"], d["hi"], d["lo"], d["rain"]))
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
    shown = []                                  # cluster-übergreifende Titel
    out = ""
    for i, (title, feeds, src) in enumerate(CLUSTERS):
        cands = get_cluster(feeds, AGE_BY_CLUSTER.get(title, DEFAULT_AGE_HOURS))
        # schon in einem früheren Cluster gezeigte Story hier rauswerfen
        cands = [c for c in cands
                 if not any(_dup(c.get("title", ""), s) for s in shown)]
        items = dedupe_pick(cands, MAX_PER_CLUSTER)
        if not items:
            continue
        for it in items:
            shown.append(it.get("title", ""))
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

def get_podcasts():
    """Neueste Folge je Show. Feed wird via Apple-Podcast-Suche aufgeloest."""
    out = []
    for name, term in PODCASTS:
        try:
            r = requests.get("https://itunes.apple.com/search",
                             params={"media": "podcast", "limit": 1, "term": term},
                             headers={"User-Agent": "Mozilla/5.0"}, timeout=20).json()
            feed_url = r["results"][0]["feedUrl"]
            e = feedparser.parse(feed_url).entries[0]
            topic = _strip(e.get("title", ""))
            desc = _strip(e.get("summary", "") or e.get("subtitle", ""))
            if desc and len(desc) > 150:
                desc = desc[:150] + "\u2026"
            out.append(dict(name=name, link=e.get("link", feed_url),
                            topic=topic, desc=desc))
        except Exception:
            continue
    return out

def render_podcasts(pods):
    if not pods:
        return ""
    rows = ""
    for p in pods:
        desc = ('<div class="pod-desc">%s</div>' % esc(p["desc"])) if p["desc"] else ""
        rows += ('<div class="pod"><a class="pod-name" href="%s">%s</a>'
                 '<div class="pod-topic">%s</div>%s</div>'
                 % (esc(p["link"]), esc(p["name"]), esc(p["topic"]), desc))
    return ('<div class="divider"></div><div class="sec">'
            '<div class="eyebrow">Podcasts <span class="count">neueste Folgen</span></div>'
            '<div style="margin-top:8px;">%s</div></div>' % rows)

# ---------------------------------------------------------------- Rezept
# Mehrere gesunde Rezept-Feeds; pro Tag wird der beste nach Gesundheit + Dauer
# bewertet und gezeigt. Die Rezeptseiten liefern strukturierte Daten (JSON-LD).
RECIPE_FEEDS = [
    "https://www.skinnytaste.com/feed/",
    "https://www.wellplated.com/feed/",
    "https://www.loveandlemons.com/feed/",
]

_DUR = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?")

def _minutes(v):
    if not isinstance(v, str):
        return None
    m = _DUR.fullmatch(v.strip())
    if not m:
        return None
    return (int(m.group(1) or 0) * 60 + int(m.group(2) or 0)) or None

def _num(x):
    try:
        return float(re.sub(r"[^\d.]", "", str(x)) or 0) or None
    except Exception:
        return None

def _img_url(v):
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return v.get("url")
    if isinstance(v, list) and v:
        return _img_url(v[0])
    return None

def _jsonld_recipes(text):
    out = []
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', text, re.S | re.I):
        try:
            data = json.loads(m.group(1).strip())
        except Exception:
            continue
        items = data if isinstance(data, list) else \
            data.get("@graph", [data]) if isinstance(data, dict) else []
        for it in items:
            if not isinstance(it, dict):
                continue
            t = it.get("@type", "")
            if t == "Recipe" or (isinstance(t, list) and "Recipe" in t):
                out.append(it)
    return out

def _recipe_from(it, fallback_url):
    name = it.get("name")
    if not name:
        return None
    tt = _minutes(it.get("totalTime")) or \
        ((_minutes(it.get("prepTime")) or 0) + (_minutes(it.get("cookTime")) or 0)) or None
    cal = None
    if isinstance(it.get("nutrition"), dict):
        cal = _num(it["nutrition"].get("calories"))
    rating = None
    if isinstance(it.get("aggregateRating"), dict):
        rating = _num(it["aggregateRating"].get("ratingValue"))
    ings = [_strip(str(x)) for x in (it.get("recipeIngredient") or [])][:3]
    return dict(name=_strip(str(name)), url=it.get("url") or fallback_url,
                img=_img_url(it.get("image")), minutes=tt, cal=cal,
                rating=rating, ings=ings)

def _recipe_score(r):
    s = 0.0
    if r["minutes"]:
        s += max(0, 45 - r["minutes"])          # schneller = besser (bis 45 Min)
    if r["cal"]:
        s += max(0, (700 - r["cal"]) / 20)       # kalorienärmer = besser
    if r["rating"]:
        s += r["rating"] * 4                      # gute Bewertung zählt
    return s

def get_recipe():
    cands = []
    for feed in RECIPE_FEEDS:
        try:
            for e in feedparser.parse(feed).entries[:3]:
                url = e.get("link")
                if not url:
                    continue
                text = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20).text
                for it in _jsonld_recipes(text):
                    r = _recipe_from(it, url)
                    if r and r["img"] and r["minutes"]:
                        cands.append(r)
                    break
        except Exception:
            continue
    if not cands:
        return None
    cands.sort(key=_recipe_score, reverse=True)
    return cands[0]

def render_recipe(r):
    if not r:
        return ""
    meta = []
    if r["minutes"]:
        meta.append("%d Min" % r["minutes"])
    if r["rating"]:
        meta.append('<span class="star">\u2605</span> %.1f' % r["rating"])
    if r["cal"]:
        meta.append("%d kcal" % r["cal"])
    why = []
    if r["minutes"] and r["minutes"] <= 30:
        why.append("schnell")
    if r["cal"] and r["cal"] <= 500:
        why.append("kalorienarm")
    if r["rating"] and r["rating"] >= 4.5:
        why.append("top bewertet")
    why_html = ('<div class="r-why">Warum: %s</div>' % esc(" · ".join(why))) if why else ""
    ings = (' · '.join(esc(i) for i in r["ings"])) if r["ings"] else ""
    img = ('background-image:url(\'%s\')' % esc(r["img"])) if r["img"] else ""
    return ('<div class="divider"></div><div class="sec">'
            '<div class="eyebrow">Gesund &amp; schnell <span class="count">automatisch ausgewählt</span></div>'
            '<a class="recipe" href="%s"><div class="recipe-img" style="%s"></div>'
            '<div class="recipe-body"><div class="r-title">%s</div>'
            '<div class="r-meta">%s</div><div class="r-ing">%s</div>%s</div></a></div>'
            % (esc(r["url"]), img, esc(r["name"]), " · ".join(meta), ings, why_html))

# ---------------------------------------------------------------- Fußball / Sport
# Alle Spiele aus den ICS-Spielplaenen von calovo (cal.to) - ohne iPhone-Kalender.
# Je nach gewaehltem calovo-Kalender inkl. CL/Pokal/Testspiele.
# (Anzeigename, ICS-URL, OpenLigaDB-Liga fuer Tabelle | "", Tabellen-Suchbegriff | "")
SPORTS_ICS = [
    ("FC Bayern",       "https://i.cal.to/ical/2/fcbayern/bundesliga-spielplan/37736a35.76a29904-93a09808.ics", "bl1", "Bayern"),
    ("Preussen Muenster","https://i.cal.to/ical/509/scpreussen-muenster/spielplan/37736a35.76a29904-d818caed.ics", "bl2", "Preu"),
    ("Uni Baskets",     "https://i.cal.to/ical/3645/wwu-baskets/spielplan/37736a35.76a29904-dc771112.ics", "", ""),
]
SPORTS_SEASON = 2026
SPORTS_DAYS = 7

TV_LABEL = {"ard":"ARD","zdf":"ZDF","das erste":"Das Erste","sat.1":"Sat.1","sat1":"Sat.1",
            "ran":"ran","rtl":"RTL","prosieben":"ProSieben","sport1":"Sport1","nitro":"Nitro",
            "sportschau":"Sportschau","sky":"Sky","dazn":"DAZN","amazon":"Amazon Prime",
            "prime":"Amazon Prime","wow":"WOW","magentasport":"MagentaSport","magenta tv":"MagentaTV"}
TV_PAY  = ["sky","dazn","amazon","prime","wow","magentasport","magenta tv"]
TV_FREE = ["ard","zdf","das erste","sat.1","sat1","ran","rtl","prosieben","sport1","nitro","sportschau"]

_TBL = {}

def _table_pos(league, match):
    if not league or not match:
        return None
    if league not in _TBL:
        try:
            _TBL[league] = requests.get(
                "https://api.openligadb.de/getbltable/%s/%s" % (league, SPORTS_SEASON),
                timeout=20).json()
        except Exception:
            _TBL[league] = []
    for i, t in enumerate(_TBL[league], 1):
        if match.lower() in (t.get("teamName", "") or "").lower():
            return i
    return None

def _ics_field(block, name):
    for line in block.splitlines():
        if line.startswith(name + ":") or line.startswith(name + ";"):
            return line.split(":", 1)[-1].strip()
    return ""

def _ics_dt(value):
    if not value:
        return None, False
    is_utc = value.endswith("Z")
    v = value.replace("Z", "")
    try:
        if "T" in v:
            d = dt.datetime.strptime(v[:15], "%Y%m%dT%H%M%S")
            d = d.replace(tzinfo=timezone.utc).astimezone(TZ) if is_utc else d.replace(tzinfo=TZ)
            return d, True
        return dt.datetime.strptime(v[:8], "%Y%m%d").replace(tzinfo=TZ), False
    except Exception:
        return None, False

def _broadcaster(text):
    t = text.lower()
    for kw in TV_PAY:
        if re.search(r"(?<![a-z])" + re.escape(kw) + r"(?![a-z])", t):
            return TV_LABEL.get(kw, kw), "Pay"
    for kw in TV_FREE:
        if re.search(r"(?<![a-z])" + re.escape(kw) + r"(?![a-z])", t):
            return TV_LABEL.get(kw, kw), "Free"
    return "", ""

def get_sports():
    games = []
    now = dt.datetime.now(TZ)
    horizon = now + dt.timedelta(days=SPORTS_DAYS)
    for name, ics, league, match in SPORTS_ICS:
        url = ics.replace("webcal://", "https://")
        if not url.startswith("http"):
            continue
        try:
            txt = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20).text
        except Exception:
            continue
        pos = _table_pos(league, match)
        for block in txt.split("BEGIN:VEVENT")[1:]:
            block = block.split("END:VEVENT")[0]
            when, has_time = _ics_dt(_ics_field(block, "DTSTART"))
            if not when or not (now <= when <= horizon):
                continue
            summary = _ics_field(block, "SUMMARY")
            blob = summary + " " + _ics_field(block, "DESCRIPTION") + " " + _ics_field(block, "LOCATION")
            tv, kind = _broadcaster(blob)
            games.append(dict(name=name, when=when, has_time=has_time,
                              title=summary, pos=pos, tv=tv, tv_kind=kind))
    games.sort(key=lambda g: g["when"])
    return games

def render_sports(games):
    if not games:
        return ""
    rows = ""
    for g in games:
        when = ("%s %02d:%02d" % (WD[g["when"].weekday()], g["when"].hour, g["when"].minute)
                if g["has_time"] else WD[g["when"].weekday()])
        pos = (' <span class="g-pos">(Tab. %d.)</span>' % g["pos"]) if g.get("pos") else ""
        tv = ('<span class="g-tv">%s \xb7 %s</span>' % (esc(g["tv"]), esc(g["tv_kind"]))) if g["tv"] else ""
        rows += ('<div class="game"><span class="g-when">%s</span>'
                 '<span class="g-opp">%s</span>%s %s</div>'
                 % (when, esc(g["title"]), pos, tv))
    return ('<div class="divider"></div><div class="sec">'
            '<div class="eyebrow">Sport \xb7 diese Woche '
            '<span class="count">alle Wettbewerbe \xb7 Tabelle in ( )</span></div>'
            '<div style="margin-top:8px;">%s</div></div>' % rows)

# ---------------------------------------------------------------- Events Münster
# Beste-Mühe: liest die Rausgegangen-Seite und zieht strukturierte Event-Daten
# (JSON-LD). Kein offizieller Feed vorhanden -> bei Bedarf leer.
EVENTS_URL = "https://rausgegangen.de/muenster/"
EVENTS_DAYS = 7
EVENTS_MAX = 5
HANSA_KEYWORD = "hansaviertel"

def _jsonld_all(text):
    out = []
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', text, re.S | re.I):
        try:
            data = json.loads(m.group(1).strip())
        except Exception:
            continue
        items = data if isinstance(data, list) else \
            (data.get("@graph", [data]) if isinstance(data, dict) else [])
        for it in items:
            if isinstance(it, dict):
                out.append(it)
    return out

def _loc_name(loc):
    if isinstance(loc, dict):
        return loc.get("name") or ""
    if isinstance(loc, list) and loc:
        return _loc_name(loc[0])
    if isinstance(loc, str):
        return loc
    return ""

def get_events():
    try:
        text = requests.get(EVENTS_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=20).text
    except Exception:
        return []
    now = dt.datetime.now(TZ)
    horizon = now + dt.timedelta(days=EVENTS_DAYS)
    evs, seen = [], set()
    for it in _jsonld_all(text):
        t = it.get("@type", "")
        if not (t == "Event" or (isinstance(t, list) and "Event" in t)):
            continue
        sd = it.get("startDate")
        if not sd:
            continue
        try:
            when = dt.datetime.fromisoformat(sd.replace("Z", "+00:00"))
            when = when.astimezone(TZ) if when.tzinfo else when.replace(tzinfo=TZ)
        except Exception:
            continue
        if not (now <= when <= horizon):
            continue
        name = _strip(str(it.get("name", "")))
        if not name or name in seen:
            continue
        seen.add(name)
        venue = _strip(_loc_name(it.get("location")))
        has_time = "T" in sd
        hansa = HANSA_KEYWORD in (name + " " + venue).lower()
        evs.append(dict(when=when, has_time=has_time, title=name, venue=venue,
                        url=it.get("url") or EVENTS_URL, hansa=hansa))
    evs.sort(key=lambda e: e["when"])
    # Hansaviertel-Treffer nach oben
    evs.sort(key=lambda e: not e["hansa"])
    return evs[:EVENTS_MAX]

def render_events(evs):
    if not evs:
        return ""
    rows = ""
    for e in evs:
        when = ("%s %02d:%02d" % (WD[e["when"].weekday()], e["when"].hour, e["when"].minute)
                if e["has_time"] else WD[e["when"].weekday()])
        hansa = ' <span class="ev-hansa">Hansaviertel</span>' if e["hansa"] else ""
        venue = ('<span class="ev-venue">%s</span>' % esc(e["venue"])) if e["venue"] else ""
        rows += ('<div class="ev"><span class="ev-when">%s</span>'
                 '<a class="ev-title" href="%s">%s</a>%s %s</div>'
                 % (when, esc(e["url"]), esc(e["title"]), hansa, venue))
    return ('<div class="divider"></div><div class="sec">'
            '<div class="eyebrow">Münster · diese Woche '
            '<span class="count">Events · Hansaviertel markiert</span></div>'
            '<div style="margin-top:8px;">%s</div></div>' % rows)

def build():
    days, mk = get_weather(), get_markets()
    pods = get_podcasts()
    recipe = get_recipe()
    sports = get_sports()
    events = get_events()
    now_local = dt.datetime.now(TZ)
    today = now_local.date()
    stand = now_local.strftime("%H:%M")
    built = now_local.strftime("%d.%m. %H:%M")
    quote = QUOTES[today.weekday() % len(QUOTES)]
    _wt = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    _mo = ["Januar", "Februar", "M\xe4rz", "April", "Mai", "Juni", "Juli", "August",
           "September", "Oktober", "November", "Dezember"]
    datum = "%s, %d. %s %d" % (_wt[today.weekday()], today.day, _mo[today.month - 1], today.year)
    page = """<!DOCTYPE html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
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
.mast-right{display:flex;flex-direction:column;align-items:flex-end;gap:7px}
.refresh{border:1px solid %(hair)s;background:transparent;color:%(accent)s;width:30px;height:30px;border-radius:50%%;font-size:15px;line-height:1;padding:0;cursor:pointer;-webkit-appearance:none}
.refresh:active{background:%(hair)s}
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
.wx-r{font-size:8.5px;color:%(cool)s;margin-top:1px}
.mkt-row{display:flex;align-items:center;gap:16px;margin-top:9px}
.mkt{display:flex;align-items:baseline;gap:6px;text-decoration:none}
.mkt .nm{font-size:9px;text-transform:uppercase;color:%(meta)s;font-weight:600}
.mkt .vl{font-size:13.5px;font-weight:600;color:%(ink)s}.mkt .ch{font-size:11px;font-weight:600}
.mkt-sep{width:1px;height:18px;background:%(hair)s}.up{color:#2F7D5B}.down{color:#A8453A}
.item{padding:9px 0;border-top:1px solid %(hair)s}.item:first-of-type{border-top:none;padding-top:8px}
.item a.title{font-size:13.5px;font-weight:600;color:%(ink)s;text-decoration:none;line-height:1.28}
.summary{margin:3px 0 4px;font-size:12px;color:%(ink_soft)s;line-height:1.4}
.meta{font-size:10px;color:%(meta)s}.meta .src{color:%(accent)s;font-weight:600}
.pod{padding:8px 0;border-top:1px solid %(hair)s;font-size:12px}.pod:first-of-type{border-top:none}
.pod-name{font-weight:600;color:%(accent)s;text-decoration:none;display:block}
.pod-topic{color:%(ink)s;margin-top:2px;line-height:1.35}
.pod-desc{color:%(ink_soft)s;margin-top:2px;line-height:1.35;font-size:11.5px}
.recipe{display:flex;gap:12px;margin-top:9px;text-decoration:none;align-items:center}
.recipe-img{width:84px;height:84px;border-radius:4px;flex-shrink:0;background-size:cover;background-position:center;background-color:#E7E4DC}
.r-title{font-size:13.5px;font-weight:600;color:%(ink)s}
.r-meta{font-size:10.5px;color:%(meta)s;margin-top:3px}.r-meta .star{color:%(warm)s}
.r-ing{font-size:11.5px;color:%(ink_soft)s;margin-top:5px}
.r-why{font-size:9px;color:%(accent)s;margin-top:4px;letter-spacing:.04em;text-transform:uppercase;font-weight:600}
.game{display:flex;align-items:baseline;gap:7px;padding:7px 0;border-top:1px solid %(hair)s;font-size:12.5px;flex-wrap:wrap}
.game:first-of-type{border-top:none;padding-top:8px}
.g-when{color:%(accent)s;font-weight:700;font-size:10px;letter-spacing:.03em;min-width:60px}
.g-team{font-weight:600;color:%(ink)s;text-decoration:none}
.g-pos{color:%(meta)s;font-size:10.5px}.g-opp{color:%(ink_soft)s}
.g-comp{color:%(meta)s;font-size:9px;letter-spacing:.03em;margin-left:auto;text-transform:uppercase}
.g-tv{color:%(accent)s;font-size:9px;letter-spacing:.03em;margin-left:auto;text-transform:uppercase;font-weight:600}
.ev{display:flex;align-items:baseline;gap:7px;padding:7px 0;border-top:1px solid %(hair)s;font-size:12.5px;flex-wrap:wrap}
.ev:first-of-type{border-top:none;padding-top:8px}
.ev-when{color:%(accent)s;font-weight:700;font-size:10px;letter-spacing:.03em;min-width:54px}
.ev-title{font-weight:600;color:%(ink)s;text-decoration:none}
.ev-venue{color:%(meta)s;font-size:10px;margin-left:auto}
.ev-hansa{font-size:8.5px;color:#fff;background:%(warm)s;padding:1px 6px;border-radius:3px;text-transform:uppercase;letter-spacing:.05em;font-weight:700}
.foot{padding:15px 26px 20px;border-top:1px solid %(hair)s;font-size:10px;color:%(meta)s;line-height:1.5}
</style></head><body><div class="wrap"><div class="card">
<div class="mast"><div><div class="wordmark">Morning Briefing</div><div class="submark">f\xfcr Daniel Overesch</div></div>
<div class="mast-right"><button class="refresh" onclick="location.reload()" aria-label="Aktualisieren" title="Aktualisieren">\u21bb</button><div class="date">%(datum)s</div></div></div>
<div class="greet"><div class="hi">Guten Morgen, %(name)s</div>
<div class="quote">%(qt)s <span class="by">\u2014 %(qa)s</span></div></div>
<div class="sec"><div class="eyebrow">Wetter <span class="count">10 Tage \xb7 M\xfcnster</span></div>
<div class="wx-grid">%(wx)s</div></div>
<div class="divider"></div>
<div class="sec"><div class="eyebrow">M\xe4rkte <span class="count">Stand %(stand)s</span></div>
<div class="mkt-row">%(mk)s</div></div>
<div class="divider"></div>
%(clusters)s
%(podcasts)s
%(events)s
%(recipe)s
%(sports)s
<div class="foot">Automatisch erzeugt %(built)s \xb7 \xdcberschriften verlinken auf die Originalquelle.
Pers\xf6nliche Bl\xf6cke (Whoop, Fotos, Agenda) folgen im iPhone-Kurzbefehl.</div>
</div></div></body></html>""" % dict(
        C, datum=datum, name=NAME, qt=esc(quote[0]), qa=esc(quote[1]),
        stand=stand, built=built,
        wx=render_weather(days), mk=render_markets(mk), clusters=render_clusters(),
        podcasts=render_podcasts(pods), recipe=render_recipe(recipe),
        sports=render_sports(sports), events=render_events(events))

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(page)
    with open("manifest.json", "w", encoding="utf-8") as f:
        f.write('{"name":"Morning Briefing f\\u00fcr Daniel Overesch","short_name":"Briefing",'
                '"start_url":"./index.html","scope":"./","display":"standalone",'
                '"background_color":"#FCFCFA","theme_color":"#FCFCFA","lang":"de"}')
    print("index.html + manifest.json geschrieben.")

if __name__ == "__main__":
    build()
