#!/usr/bin/env python3
"""Build the static Vast.ai referral site into ./dist.

Stdlib only (Pillow is optional, for share images). Reads live offers from Vast.ai's public
offer search and falls back to data/pricing-fallback.json when that fails.
"""
import datetime as dt
import html
import json
import os
import re
import shutil
import sys

import chart
import vast

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist")

DOMAIN = os.environ.get("SITE_DOMAIN", "vastaicode.com")
BASE = f"https://{DOMAIN}"
REF_ID = "881041"
SIGNUP = f"https://cloud.vast.ai/?ref_id={REF_ID}"
LINK_TEXT = f"cloud.vast.ai/?ref_id={REF_ID}"
FALLBACK = os.path.join(ROOT, "data", "pricing-fallback.json")
HISTORY = os.path.join(ROOT, "data", "history.csv")
HISTORY_NAME = "vast-ai-gpu-price-history.csv"
SITE_NAME = "Vast.ai Referral Code"
INDEXNOW_KEY = "9a4d27c1e06b4f58b3c7d5e1f0a2864b"
KEEP_DAYS = 30        # keep showing a GPU model this long after its last free machine
FACTS_CHECKED = "November 2026"   # when the statements about Vast.ai's terms were last checked against its docs

e = html.escape


# ---------------------------------------------------------------- data

def load_pricing():
    prev = None
    if os.path.exists(FALLBACK):
        with open(FALLBACK) as f:
            prev = json.load(f)
    try:
        data = vast.summarize(vast.fetch_offers())
        if len(data["models"]) < 5:
            raise ValueError(f"only {len(data['models'])} models in the offer search")
        if prev:  # models with nothing free right now keep their last known prices for a while
            now = chart.parse_ts(data["generated_at"])
            have = {m["slug"] for m in data["models"]}
            for m in prev["models"]:
                if m["slug"] not in have and now - chart.parse_ts(m["last_seen"]) <= dt.timedelta(days=KEEP_DAYS):
                    data["models"].append({**m, "machines": 0, "gpus": 0, "offers": 0})
        data["models"].sort(key=lambda m: m["slug"])
        with open(FALLBACK, "w") as f:
            json.dump(data, f, indent=1, sort_keys=True)
        print(f"fetched live offers: {len(data['models'])} models", file=sys.stderr)
        return data, True
    except Exception as ex:  # network or format problem: build from the last snapshot
        print(f"offer fetch failed ({ex}); using fallback", file=sys.stderr)
        if prev is None:
            raise
        return prev, False


def usd(v):
    if v is None:
        return "–"
    s = f"{v:,.2f}"
    if v < 10 and abs(v * 100 - round(v * 100)) > 1e-9:
        s = f"{v:,.3f}"
    return f"${s}"


def art(name):
    """'an RTX 4090', 'an H100', 'a B200', 'a Tesla V100': initials are read letter by letter."""
    first = name.split()[0]
    if first.isupper() or any(c.isdigit() for c in first):
        return ("an " if first[0] in "AEFHILMNORSX" else "a ") + name
    return ("an " if first[0].lower() in "aeiou" else "a ") + name


def plural(n, word):
    return f"{n:,} {word}{'' if n == 1 else 's'}"


CLASS = {"datacenter": "Data center", "professional": "Workstation", "consumer": "Consumer"}


# ---------------------------------------------------------------- layout

CSS = """
:root{--bg:#0a0f10;--panel:#11181a;--panel2:#172022;--line:#243033;--text:#e6ecec;--muted:#98a6a8;
--accent:#0b8573;--accent2:#3dd6c0;--ok:#3ecf8e;--warn:#f0b429;--radius:12px}
@media (prefers-color-scheme: light){:root:not([data-theme="dark"]){--bg:#f6f9f9;--panel:#fff;--panel2:#edf3f3;
--line:#d9e3e3;--text:#121a1b;--muted:#56666a;--accent:#0b7566;--accent2:#0b7566;--ok:#11875a;--warn:#a86b00}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--accent2)}
.wrap{max-width:960px;margin:0 auto;padding:0 16px}
header.top{border-bottom:1px solid var(--line)}
header.top .wrap{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:4px 12px;min-height:56px;padding-top:8px;padding-bottom:8px}
.brand{font-weight:700;color:var(--text);text-decoration:none}
.brand span{color:var(--accent2)}
nav{display:flex;gap:16px;flex-wrap:wrap}
nav a{color:var(--muted);text-decoration:none;font-size:15px}
nav a:hover{color:var(--text)}
h1{font-size:clamp(28px,5vw,42px);line-height:1.15;margin:40px 0 12px;letter-spacing:-.02em}
h2{font-size:24px;margin:48px 0 12px;letter-spacing:-.01em}
h3{font-size:18px;margin:24px 0 6px}
.lead{color:var(--muted);font-size:18px;max-width:680px}
.codebox{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:20px;margin:24px 0;
display:flex;flex-wrap:wrap;align-items:center;gap:12px}
.codebox .label{width:100%;color:var(--muted);font-size:14px}
.code{font:700 clamp(15px,4vw,22px)/1.3 ui-monospace,SFMono-Regular,Menlo,monospace;overflow-wrap:anywhere;
background:var(--panel2);border:1px dashed var(--accent2);border-radius:8px;padding:10px 14px;user-select:all}
.btn{display:inline-block;border:0;border-radius:8px;padding:12px 18px;font:600 15px system-ui,sans-serif;cursor:pointer;
text-decoration:none;background:var(--accent);color:#fff}
.btn.ghost{background:transparent;color:var(--text);border:1px solid var(--line)}
.btn:hover{filter:brightness(1.1)}
.small{font-size:13px;color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:16px 0}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:16px}
.card b{display:block;font-size:22px}
.card span{color:var(--muted);font-size:14px}
ol.steps{padding-left:20px}
ol.steps li{margin:6px 0}
.tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:var(--radius)}
table{border-collapse:collapse;width:100%;font-size:15px;background:var(--panel)}
th,td{text-align:left;padding:10px 12px;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--muted);font-weight:600;font-size:13px;background:var(--panel2)}
tr:last-child td{border-bottom:0}
table.wraps td{white-space:normal;min-width:120px}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.pill{display:inline-block;font-size:12px;padding:1px 8px;border-radius:99px;border:1px solid var(--line);color:var(--muted)}
.pill.ok{color:var(--ok);border-color:var(--ok)}
.ptable tbody tr{position:relative;transition:background .12s}
.ptable tbody tr:hover{background:var(--panel2)}
.ptable tbody tr:focus-within{outline:2px solid var(--accent2);outline-offset:-2px}
.ptable a.row{color:var(--text);font-weight:600;text-decoration:none}
.ptable a.row::after{content:"";position:absolute;inset:0}
.ptable tr:hover a.row{color:var(--accent2)}
.ptable .hi{color:var(--muted)}
.ptable .sub{display:none;font-size:13px;color:var(--muted);font-weight:400;margin-top:2px}
.ptable .ok-t{color:var(--ok)}
.ptable .go{width:1%;color:var(--muted);font-size:20px;line-height:1;padding-left:4px}
.ptable tr:hover .go{color:var(--accent2)}
.ptable th button{all:unset;cursor:pointer;color:inherit}
.ptable th button:hover{color:var(--text)}
.ptable th button:focus-visible{outline:2px solid var(--accent2);border-radius:4px}
.ptable th[aria-sort] button{color:var(--text)}
.ptable th[aria-sort=ascending] button::after{content:" ↑"}
.ptable th[aria-sort=descending] button::after{content:" ↓"}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}
.chip{border:1px solid var(--line);background:var(--panel);color:var(--muted);border-radius:99px;padding:6px 12px;
font:500 14px system-ui,sans-serif;cursor:pointer}
.chip span{opacity:.7;margin-left:2px}
.chip:hover{color:var(--text)}
.chip[aria-pressed=true]{background:var(--accent);border-color:var(--accent);color:#fff}
@media (max-width:640px){
.ptable .c-vram,.ptable .c-bid,.ptable .c-now,.ptable .c-trend{display:none}
.ptable .sub{display:block}
.ptable td.c-name{white-space:normal}
.ptable th,.ptable td{padding:10px 8px}
.ptable .c-price .hi{display:block;font-size:13px}
.ptable .dot{display:none}
.ptable .sub{white-space:nowrap}
}
details{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:12px 16px;margin:8px 0}
summary{cursor:pointer;font-weight:600}
.note{border-left:3px solid var(--warn);padding:8px 12px;background:var(--panel);border-radius:0 8px 8px 0;font-size:14px;color:var(--muted)}
footer{border-top:1px solid var(--line);margin-top:64px;padding:24px 0 40px;color:var(--muted);font-size:13px}
.crumbs{font-size:14px;color:var(--muted);margin-top:24px}
.crumbs a{color:var(--muted)}
"""

COPY_JS = """
<script>
document.querySelectorAll('[data-copy]').forEach(function(b){b.addEventListener('click',function(){
var t=b.getAttribute('data-copy');var done=function(){var o=b.textContent;b.textContent='Copied!';setTimeout(function(){b.textContent=o},1500)};
if(navigator.clipboard){navigator.clipboard.writeText(t).then(done,function(){})}else{var r=document.createRange();
var el=document.querySelector('.code');r.selectNodeContents(el);var s=getSelection();s.removeAllRanges();s.addRange(r);document.execCommand('copy');done()}
})});
</script>
"""


def canonical(path):
    return BASE + ("/" if path == "index.html" else "/" + path.replace(".html", ""))


def breadcrumbs(items):
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": u}
                                for i, (n, u) in enumerate(items)]}


# Set by main(): whether share images were generated, and when prices were fetched.
STATE = {"images": False, "modified": None, "hist": {}}


def page(path, title, desc, body, jsonld=None, og=None, og_alt=None, crumbs=None, noindex=False, charts=False):
    canon = canonical(path)
    docs = list(jsonld or [])
    if crumbs:
        docs.append(breadcrumbs(crumbs))
    if not noindex:
        docs.append({"@context": "https://schema.org", "@type": "WebPage", "url": canon, "name": title,
                     "description": desc, "inLanguage": "en", "dateModified": STATE["modified"],
                     "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": BASE + "/"}})
    ld = "".join('<script type="application/ld+json">' + json.dumps(x, ensure_ascii=False).replace("</", "<\\/")
                 + "</script>" for x in docs)
    img = ""
    if STATE["images"]:
        og = og or "/og/home.png"
        img = f"""<meta property="og:image" content="{BASE}{og}">
<meta property="og:image:type" content="image/png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{e(og_alt or title)}">
<meta name="twitter:image" content="{BASE}{og}">
<meta name="twitter:image:alt" content="{e(og_alt or title)}">"""
    robots = "noindex" if noindex else "index,follow,max-image-preview:large,max-snippet:-1"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<meta name="robots" content="{robots}">
<link rel="canonical" href="{canon}">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:locale" content="en_US">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{canon}">
<meta name="twitter:card" content="{'summary_large_image' if STATE['images'] else 'summary'}">
<meta name="twitter:title" content="{e(title)}">
<meta name="twitter:description" content="{e(desc)}">
{img}
<link rel="icon" href="/favicon.ico" sizes="48x48">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<meta name="theme-color" content="#0a0f10">
<style>{CSS}{chart.CHART_CSS}</style>
{ld}
</head>
<body>
<header class="top"><div class="wrap">
<a class="brand" href="/">Vast.ai <span>Referral Code</span></a>
<nav><a href="/#prices">GPU prices</a><a href="/pricing">How pricing works</a><a href="/#faq">FAQ</a></nav>
</div></header>
<main class="wrap">
{body}
</main>
<footer><div class="wrap">
<p>Unofficial site. Not affiliated with, endorsed by or operated by Vast.ai. “Vast.ai” is used only to describe the service.</p>
<p>Disclosure: the signup link on this site is our referral link (ID {e(REF_ID)}). If you create an account through it, Vast.ai pays us
3% of what you spend, as referral credit. It costs you nothing and gives you no discount.</p>
<p>Prices come from Vast.ai's public offer search and change constantly. Check cloud.vast.ai before you rent.</p>
</div></footer>
{COPY_JS}{chart.CHART_JS if charts else ''}
</body>
</html>
"""


def codebox(label="Vast.ai referral link"):
    return f"""<div class="codebox">
<div class="label">{e(label)}</div>
<span class="code">{e(LINK_TEXT)}</span>
<button class="btn ghost" data-copy="{e(SIGNUP)}">Copy link</button>
<a class="btn" href="{e(SIGNUP)}" rel="nofollow sponsored">Sign up with this link →</a>
<div class="small" style="width:100%">Vast.ai has no “referral code” box to type into. The referral is carried by the link, so open it first and then create your account. The ID in it is {e(REF_ID)}.</div>
</div>"""


def avail_text(m):
    if not m["machines"]:
        return "none free right now"
    return f"{plural(m['gpus'], 'GPU')} free on {plural(m['machines'], 'machine')}"


def price_table(models, updated, controls=False):
    rows = []
    for m in models:
        n = m["machines"]
        status = (f'<span class="pill ok">{plural(n, "machine")}</span>' if n else '<span class="pill">none free</span>')
        sub_free = (f'<span class="ok-t">{plural(n, "machine")}</span>' if n else 'none free')
        pts = STATE["hist"].get(m["slug"], [])
        if pts:
            cutoff = pts[-1]["t"] - dt.timedelta(days=7)
            pts = [p for p in pts if p["t"] >= cutoff and p["available"] > 0]
        lo, med = m["min"], m["median"]
        price = f"<b>{usd(lo)}</b>" + (f'<span class="hi"><span class="dot"> · </span>median {usd(med)}</span>' if n > 1 and med != lo else "")
        rows.append(f"""<tr data-class="{e(m['gpu_class'])}" data-free="{n}" data-price="{lo}" data-bid="{m['bid'] or 0}" data-vram="{m['vram_gb']}" data-name="{e(m['name'])}">
<td class="c-name"><a class="row" href="/gpu/{e(m['slug'])}">{e(m['name'])}</a><span class="sub">{m['vram_gb']} GB · {sub_free}</span></td>
<td class="num c-vram">{m['vram_gb']} GB</td><td class="num c-price">{price}</td><td class="num c-bid">{usd(m['bid'])}</td><td class="c-now">{status}</td>
<td class="c-trend">{chart.sparkline(pts)}</td><td class="go" aria-hidden="true">›</td></tr>""")
    head = ('<th class="c-name"><button data-sort="name">GPU</button></th>'
            '<th class="num c-vram"><button data-sort="vram">VRAM</button></th>'
            '<th class="num c-price"><button data-sort="price">On-demand from</button></th>'
            '<th class="num c-bid"><button data-sort="bid">Interruptible from</button></th>'
            '<th class="c-now"><button data-sort="free">Free now</button></th><th class="c-trend">7-day low price</th><th class="go"></th>'
            if controls else
            '<th class="c-name">GPU</th><th class="num c-vram">VRAM</th><th class="num c-price">On-demand from</th>'
            '<th class="num c-bid">Interruptible from</th><th class="c-now">Free now</th><th class="c-trend">7-day low price</th><th class="go"></th>')
    chips = ""
    if controls:
        n_free = sum(m["machines"] > 0 for m in models)
        groups = [("all", "All", len(models))]
        if n_free < len(models):
            groups.append(("free", "Available now", n_free))
        for key in ("datacenter", "professional", "consumer"):
            c = sum(m["gpu_class"] == key for m in models)
            if c:
                groups.append((key, CLASS[key], c))
        chips = ('<div class="chips" role="group" aria-label="Filter GPUs">' + "".join(
            f'<button class="chip" data-filter="{k}" aria-pressed="{"true" if k == "all" else "false"}">{l} <span>{c}</span></button>'
            for k, l, c in groups) + "</div>")
    return f"""{chips}<div class="tablewrap"><table class="ptable{' sortable' if controls else ''}">
<thead><tr>{head}</tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
<p class="small">From Vast.ai's public offer search, {e(updated)}: verified machines that were free to rent. Prices are for the GPU only,
per GPU per hour; storage and bandwidth are charged separately. “Interruptible from” is the lowest minimum bid.
Models with nothing free show the last price we saw.</p>"""


TABLE_JS = """
<script>
(function(){var t=document.querySelector('table.sortable');if(!t)return;var tb=t.tBodies[0],rows=[].slice.call(tb.rows),orig=rows.slice();
var chips=document.querySelectorAll('.chip'),cur={k:null,dir:1};
chips.forEach(function(c){c.addEventListener('click',function(){var f=c.getAttribute('data-filter');
chips.forEach(function(x){x.setAttribute('aria-pressed',x===c?'true':'false')});
rows.forEach(function(r){r.hidden=!(f==='all'||(f==='free'?+r.dataset.free>0:r.dataset.class===f))})})});
t.querySelectorAll('th button').forEach(function(b){b.addEventListener('click',function(){var k=b.getAttribute('data-sort');
if(cur.k===k){cur.dir=-cur.dir}else{cur.k=k;cur.dir=(k==='name'||k==='price'||k==='bid')?1:-1}
t.querySelectorAll('th').forEach(function(th){th.removeAttribute('aria-sort')});
b.parentNode.setAttribute('aria-sort',cur.dir>0?'ascending':'descending');
var s=orig.slice().sort(function(a,c){var x,y,sa=+a.dataset.free>0,sc=+c.dataset.free>0;
if(k!=='free'&&sa!==sc){return sa?-1:1}if(k==='name'){return cur.dir*a.dataset.name.localeCompare(c.dataset.name)}
x=+a.dataset[k];y=+c.dataset[k];return cur.dir*(x-y)});s.forEach(function(r){tb.appendChild(r)})})});
})();
</script>
"""


def faq_html(items):
    return "".join(f"<details><summary>{e(q)}</summary><p>{a}</p></details>" for q, a in items)


def faq_ld(items):
    strip = lambda s: re.sub(r"<[^>]+>", "", s)
    return {"@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": q,
                            "acceptedAnswer": {"@type": "Answer", "text": strip(a)}} for q, a in items]}


def cheapest(models, prefix):
    hits = [m for m in models if m["machines"] and m["slug"].startswith(prefix)]
    return min(hits, key=lambda m: m["min"]) if hits else None


# ---------------------------------------------------------------- pages

def build_index(data, models, updated, year):
    avail = [m for m in models if m["machines"] > 0]
    cheap = min(avail, key=lambda m: m["min"]) if avail else None
    r4090 = cheapest(models, "rtx-4090")
    h100 = cheapest(models, "h100")
    n_machines = sum(m["machines"] for m in avail)

    faq = [
        ("What is the Vast.ai referral code?",
         f"Vast.ai doesn't use a code that you type in. The referral is carried by a link: "
         f'<a href="{e(SIGNUP)}" rel="nofollow sponsored">{e(LINK_TEXT)}</a>. The number {e(REF_ID)} is our referral ID. '
         "Open the link, then create your account in the same browser."),
        ("Does the referral link give me a discount?",
         "No. Vast.ai's referral program rewards only the referrer: Vast.ai pays us 3% of what referred accounts spend, as referral credit. "
         "Your prices are exactly the same with or without the link."),
        ("Is there a Vast.ai promo code or coupon?",
         f"Vast.ai's documentation describes no promo codes and no signup bonus (checked {FACTS_CHECKED}), and we don't know of a public code that works. "
         'The real ways to pay less are interruptible instances, reserved discounts and comparing hosts. See <a href="/pricing">how Vast.ai pricing works</a>.'),
        ("Is there free credit for new Vast.ai accounts?",
         "Vast.ai's documentation doesn't mention one. You add credit before you rent, and the minimum deposit is $5."),
        ("Does the link work if I already have a Vast.ai account?",
         "No. Vast.ai counts a referral only when a new account is created through the link."),
        ("How does Vast.ai billing work?",
         "You buy credit first and it's used up as you go. The GPU is billed per second while the instance runs. Storage is billed for as long as "
         "the instance exists, even when it's stopped. Bandwidth is billed per byte in both directions. Each host sets its own three prices."),
        ("How can I pay?",
         "By card through Stripe, or with crypto through BitPay or Crypto.com. Credit you've spent isn't refunded; unspent credit usually can be, on request."),
        ("What's the difference between on-demand and interruptible?",
         "An on-demand instance has a fixed price and keeps running until you stop it. An interruptible instance runs at a price you bid, "
         "often less than half the on-demand price, and it's paused whenever someone outbids you or rents the machine on demand."),
        ("What is Vast.ai?",
         "A GPU rental marketplace. Independent hosts, from hobbyists to data centers, list their machines and set their own prices. "
         "You pick an offer, launch a Docker template on it and connect by SSH or Jupyter. There's also a CLI, an API and a serverless product."),
        ("Where do these prices come from?",
         "From Vast.ai's public offer search, the same data its console shows. About every 3 hours we read all verified machines that are free to rent "
         "and keep the lowest and median GPU price for each model. Unverified machines and machines that are already rented aren't included."),
        ("Is this site run by Vast.ai?",
         "No. It's an independent site that shares a referral link and a copy of Vast.ai's public prices."),
    ]

    cards = []
    if cheap:
        cards.append(f"<div class='card'><b>{usd(cheap['min'])}/hr</b><span>cheapest GPU free now ({e(cheap['name'])})</span></div>")
    if r4090:
        cards.append(f"<div class='card'><b>{usd(r4090['min'])}/hr</b><span>RTX 4090 from</span></div>")
    if h100:
        cards.append(f"<div class='card'><b>{usd(h100['min'])}/hr</b><span>H100 from ({e(h100['name'])})</span></div>")
    cards.append(f"<div class='card'><b>{n_machines:,}</b><span>verified machines free now, {len(avail)} GPU models</span></div>")

    body = f"""
<h1>Vast.ai Referral Code ({year}): link ID {e(REF_ID)}</h1>
<p class="lead">Vast.ai is a GPU rental marketplace where hosts compete on price. Its referral works through a link, not a code you type in.
Sign up through the link below, then compare live prices for {len(models)} GPU models.</p>
{codebox()}
<p class="note">Honest note: the link gives you no discount and no bonus credit. Vast.ai pays us 3% of what you spend, as referral credit.
You pay the same prices either way.</p>
<div class="grid">{''.join(cards)}</div>

<h2>How to use the referral link</h2>
<ol class="steps">
<li>Open <a href="{e(SIGNUP)}" rel="nofollow sponsored">{e(LINK_TEXT)}</a>. It only counts for new accounts.</li>
<li>Create your account and confirm your e-mail address. You can't rent before the e-mail is verified.</li>
<li>Go to Billing and add credit by card or crypto. The minimum deposit is $5.</li>
<li>Pick a template (PyTorch, ComfyUI and so on), search for a GPU, and click Rent.</li>
<li>When you're done, delete the instance. A stopped instance still pays for its storage.</li>
</ol>

<h2 id="prices">Vast.ai GPU prices right now</h2>
{price_table(models, updated, controls=True)}

<h2>Ways to pay less on Vast.ai</h2>
<div class="grid">
<div class="card"><b>Interruptible</b><span>bid your own price, often less than half of on-demand; can be paused when outbid</span></div>
<div class="card"><b>Reserved</b><span>pre-pay for an instance you'll keep for weeks or months, up to 50% off</span></div>
<div class="card"><b>Compare hosts</b><span>the same GPU can cost twice as much on another machine; sort by price</span></div>
<div class="card"><b>Delete, don't stop</b><span>stopped instances keep paying for storage until you delete them</span></div>
</div>
<p><a href="/pricing">How Vast.ai pricing works →</a></p>

<h2 id="faq">FAQ</h2>
{faq_html(faq)}
"""
    title = f"Vast.ai Referral Code {year}: Link ID {REF_ID} + Live GPU Prices"
    desc = (f"Vast.ai referral link: {LINK_TEXT}. Vast.ai has no code to type in; the link carries the referral. "
            f"Plus live RTX 4090, RTX 5090, H100 and H200 rental prices, updated every 3 hours.")
    site_ld = {"@context": "https://schema.org", "@type": "WebSite", "name": SITE_NAME, "alternateName": DOMAIN,
               "url": BASE + "/", "inLanguage": "en"}
    return page("index.html", title, desc, body + TABLE_JS, [site_ld, faq_ld(faq)],
                og="/og/home.png", og_alt=f"Vast.ai referral link {LINK_TEXT}")


def pct(a, b):
    return (a - b) / b * 100 if b else 0


def price_stats(m, pts):
    """Summary of the lowest asking price over the last 30 days (or since tracking began).
    Only snapshots with machines actually free count: otherwise the price is a leftover, not an ask."""
    if not pts:
        return None
    end = pts[-1]["t"]
    win = [p for p in pts if p["t"] >= end - dt.timedelta(days=30)]
    real = [p for p in win if p["available"] > 0]
    if len(real) < 4 or (real[-1]["t"] - real[0]["t"]) < dt.timedelta(days=2):
        return None
    lows = sorted(p["min"] for p in real)
    week = [p for p in real if p["t"] >= end - dt.timedelta(days=7)]
    return {
        "full30": (end - pts[0]["t"]) >= dt.timedelta(days=29),
        "start": win[0]["t"],
        "low": min(real, key=lambda p: (p["min"], p["t"])),
        "high": max(real, key=lambda p: (p["min"], p["t"])),
        "avg": round(sum(lows) / len(lows), 3),
        "avail_avg": sum(p["available"] for p in win) / len(win),
        "soldout_share": sum(p["available"] == 0 for p in win) / len(win),
        "cur": m["min"] if m["machines"] > 0 else None,
        "last_real": real[-1],
        "week_from": week[0] if len(week) >= 2 else None,
    }


def price_context(name, st):
    """Returns (paragraph html, cards html, extra faq items)."""
    when = "over the past 30 days" if st["full30"] else f"since we started tracking on {st['start'].strftime('%-d %b %Y')}"
    low, high, avg = st["low"], st["high"], st["avg"]
    parts = [f"{when[0].upper() + when[1:]}, the cheapest {e(name)} on Vast.ai has cost between <b>{usd(low['min'])}</b> and "
             f"<b>{usd(high['min'])}</b> per GPU-hour, with an average of <b>{usd(avg)}</b>."]
    cur = st["cur"]
    if cur is not None:
        d = pct(cur, avg)
        rel = ("about the same as" if abs(d) < 3 else f"{abs(d):.0f}% {'below' if d < 0 else 'above'}")
        parts.append(f"Today's lowest price, {usd(cur)}, is {rel} that average.")
    else:
        parts.append(f"None are free right now. The last available price was {usd(st['last_real']['min'])} "
                     f"on {st['last_real']['t'].strftime('%-d %b')}.")
    so = st["soldout_share"]
    avail_txt = f"On average {st['avail_avg']:.0f} verified machines with it were free to rent at any time"
    avail_txt += (f", and none were free in {so * 100:.0f}% of our snapshots." if so >= 0.05 else
                  ", and it was rarely unavailable.")
    parts.append(avail_txt)
    para = f"<p>{' '.join(parts)}</p>"

    since = "" if st["full30"] else f" since {st['start'].strftime('%-d %b')}"
    label = (lambda a: f"30-day {a}") if st["full30"] else (lambda a: f"{a[0].upper() + a[1:]}{since}")
    cards = [f"<div class='card'><b>{usd(low['min'])}</b><span>{label('low')} (on {low['t'].strftime('%-d %b')})</span></div>",
             f"<div class='card'><b>{usd(avg)}</b><span>{label('average')}</span></div>",
             f"<div class='card'><b>{usd(high['min'])}</b><span>{label('high')}</span></div>"]
    wf = st["week_from"]
    week_txt = None
    if wf and cur is not None:
        d = pct(cur, wf["min"])
        arrow = "flat" if abs(d) < 0.5 else (f"+{d:.0f}%" if d > 0 else f"−{-d:.0f}%")
        cards.append(f"<div class='card'><b>{arrow}</b><span>7-day change ({usd(wf['min'])} → {usd(cur)})</span></div>")
        week_txt = (f"In the last 7 days the lowest price went from {usd(wf['min'])} to {usd(cur)}"
                    + (" (no real change)." if abs(d) < 0.5 else f" ({'up' if d > 0 else 'down'} {abs(d):.0f}%)."))
    faq = [(f"What's the cheapest {name} price on Vast.ai recently?",
            f"{usd(low['min'])} per GPU-hour on {low['t'].strftime('%-d %b %Y')}, the lowest on-demand asking price {when}. "
            f"The average lowest price over that time was {usd(avg)}.")]
    if week_txt:
        faq.append((f"Are {name} rental prices going up or down?",
                    week_txt + " Prices are set by individual hosts and move as machines get rented and freed, "
                    "so check the chart above before you rent."))
    return para, f"<div class='grid'>{''.join(cards)}</div>", faq


def build_gpu(m, models, updated):
    name = m["name"]
    lo, med, bid = m["min"], m["median"], m["bid"]
    n = m["machines"]
    cls = CLASS[m["gpu_class"]]
    peers = [p for p in models if p["gpu_class"] == m["gpu_class"] and p["slug"] != m["slug"]][:8]
    status = avail_text(m)
    day, month = lo * 24, lo * 24 * 30
    from_word = "from" if n else "last seen at"

    if n:
        a_price = (f"From {usd(lo)} per GPU-hour on demand" + (f" (median {usd(med)} across {plural(n, 'machine')})" if n > 1 else "")
                   + f", billed per second. That's about {usd(day)} a day or {usd(month)} for 30 days at the lowest price. "
                   "Storage and bandwidth are charged on top, at rates each host sets.")
        a_avail = (f"At the last update: {status}, in {plural(m['countries'], 'country').replace('countrys', 'countries')}. "
                   f"The largest single machine offered {plural(m['max_gpus'], 'GPU')}. Only verified machines that aren't rented are counted.")
    else:
        seen = chart.parse_ts(m["last_seen"]).strftime("%-d %b %Y")
        a_price = (f"No verified machine with it is free right now. The last on-demand price we saw was {usd(lo)} per GPU-hour, on {seen}. "
                   "Storage and bandwidth are charged on top, at rates each host sets.")
        a_avail = f"Not at the last update. We last saw one free on {seen}. Machines come back as rentals end, so check again later."
    faq = [(f"How much does {art(name)} cost on Vast.ai?", a_price),
           (f"Is the {name} available on Vast.ai now?", a_avail)]
    if bid is not None:
        save = pct(bid, lo)
        faq.append((f"How cheap is an interruptible {name}?",
                    f"The lowest minimum bid {'is' if n else 'was'} {usd(bid)} per GPU-hour"
                    + (f", {abs(save):.0f}% below the cheapest on-demand price" if save <= -3 else "")
                    + ". An interruptible instance is paused when someone outbids you or rents the machine on demand, so save your work often."))
    faq.append(("Is there a discount code?",
                f"Vast.ai's documentation describes no promo codes (checked {FACTS_CHECKED}). Our referral link gives no discount either; it only tells Vast.ai we sent you. "
                "To pay less, use an interruptible instance or a reserved discount."))

    peer_rows = price_table(peers, updated) if peers else ""
    pts = STATE["hist"].get(m["slug"], [])
    st = price_stats(m, pts)
    ctx_html = ""
    if st:
        para, cards, more_faq = price_context(name, st)
        faq = faq[:1] + more_faq + faq[1:]
        ctx_html = f"<h2>{e(name)} price trend</h2>\n{para}\n{cards}"
    hist_html = ""
    if pts:
        since = pts[0]["t"].strftime("%-d %b %Y")
        price_chart = chart.line_chart(f"p-{m['slug']}", pts, "min", f"{name} lowest price per GPU-hour over time",
                                       usd, band_key="med")
        avail_chart = chart.line_chart(f"a-{m['slug']}", pts, "available", f"{name} machines free to rent over time",
                                       lambda v: f"{v:,.0f}", zero=True, unit=" free")
        rows = "".join(f"<tr><td>{p['t'].strftime('%-d %b %Y, %H:%M')}</td><td class='num'>{usd(p['min'])}</td>"
                       f"<td class='num'>{usd(p['med'])}</td><td class='num'>{usd(p['bid'])}</td><td class='num'>{p['available']}</td>"
                       f"<td class='num'>{p['gpus']}</td></tr>" for p in reversed(pts[-40:]))
        note = ("" if len(pts) > 1 else
                "<p class='small'>Tracking just started. A new snapshot is added every 3 hours, so the chart fills in over the coming days.</p>")
        hist_html = f"""<h2>{e(name)} price history</h2>
<p>Lowest and median on-demand asking price per GPU-hour on Vast.ai, recorded about every 3 hours since {since}.</p>
<div class="key"><span><i class="k-ln"></i>Lowest price</span><span><i class="k-band"></i>Range up to the median price</span></div>
{price_chart}
{note}
<h3>{e(name)} machines free to rent</h3>
{avail_chart}
<details><summary>Show data table</summary><div class="tablewrap"><table>
<thead><tr><th>Time (UTC)</th><th class="num">Lowest</th><th class="num">Median</th><th class="num">Min bid</th><th class="num">Machines</th><th class="num">GPUs</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<p class="small">Full history for every GPU: <a href="/data/{HISTORY_NAME}">{HISTORY_NAME}</a> (CC BY 4.0, please link back).</p></details>"""
    cards = [f"<div class='card'><b>{usd(lo)}</b><span>{'lowest on-demand price' if n else 'last on-demand price seen'}, per GPU-hour</span></div>"]
    if n > 1:
        cards.append(f"<div class='card'><b>{usd(med)}</b><span>median across {plural(n, 'machine')}</span></div>")
    if bid is not None:
        cards.append(f"<div class='card'><b>{usd(bid)}</b><span>interruptible, lowest minimum bid</span></div>")
    cards.append(f"<div class='card'><b>{m['vram_gb']} GB</b><span>VRAM · {e(cls)} GPU</span></div>")
    cards.append(f"<div class='card'><b>{n}</b><span>{'machine' if n == 1 else 'machines'} free now"
                 + (f", {plural(m['gpus'], 'GPU')}" if n else "") + "</span></div>")
    if n:
        cards.append(f"<div class='card'><b>{usd(month)}</b><span>30 days at the lowest price, GPU only</span></div>")
    body = f"""
<div class="crumbs"><a href="/">Vast.ai referral code</a> › <a href="/#prices">GPU prices</a> › {e(name)}</div>
<h1>{e(name)} rental price: {from_word} {usd(lo)}/hour on Vast.ai</h1>
<p class="lead">Rent {e(art(name))} ({m['vram_gb']} GB) on Vast.ai, billed per second. Right now: {e(status)}.</p>
<div class="grid">{''.join(cards)}</div>
{ctx_html}
{codebox("Sign up through our referral link to rent it")}
{hist_html}
<p><a href="{e(SIGNUP)}" rel="nofollow sponsored">Search live {e(name)} offers on Vast.ai</a> · <a href="/pricing">How Vast.ai pricing works</a></p>
<h2>{e(name)} on Vast.ai: FAQ</h2>
{faq_html(faq)}
{f'<h2>Other {e(cls.lower())} GPUs</h2>' + peer_rows if peers else ''}
<p class="small">Prices updated {e(updated)}.</p>
"""
    title = f"{name} Rental Price: {from_word} {usd(lo)}/hr on Vast.ai"
    if st and n:
        desc = (f"{name} rental price on Vast.ai: from {usd(lo)}/hr today, "
                f"{'30-day' if st['full30'] else 'recent'} low {usd(st['low']['min'])}, average {usd(st['avg'])}. "
                f"Price history and live availability.")
    elif n:
        desc = (f"Rent {art(name)} on Vast.ai from {usd(lo)}/hr on demand"
                + (f" or from {usd(bid)}/hr interruptible" if bid is not None else "")
                + f". {m['vram_gb']} GB VRAM, {status}. Price history and live availability.")
    else:
        desc = (f"{name} rental on Vast.ai: none free right now, last seen at {usd(lo)}/hr. "
                f"{m['vram_gb']} GB VRAM. Price history and live availability.")
    og_alt = f"{name} on Vast.ai: {from_word} {usd(lo)} per GPU-hour"
    return page(f"gpu/{m['slug']}.html", title, desc, body, [faq_ld(faq)],
                og=f"/og/gpu/{m['slug']}.png", og_alt=og_alt,
                crumbs=[(SITE_NAME, BASE + "/"), ("GPU prices", BASE + "/#prices"), (name, canonical(f"gpu/{m['slug']}.html"))],
                charts=bool(pts))


FAVICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#0f9d8a"/>
<path d="M17 18l15 29 15-29" fill="none" stroke="#fff" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/></svg>"""


def build_pricing(models, updated, year):
    both = [m for m in models if m["machines"] >= 2 and m["bid"] is not None]
    both.sort(key=lambda m: -m["machines"])
    rows = "".join(
        f"<tr><td><a href='/gpu/{e(m['slug'])}'>{e(m['name'])}</a></td><td class='num'>{usd(m['min'])}</td>"
        f"<td class='num'>{usd(m['bid'])}</td><td class='num'>{'−%.0f%%' % -pct(m['bid'], m['min']) if m['bid'] < m['min'] else '–'}</td>"
        f"<td class='num'>{usd(m['min'] * 24 * 30)}</td></tr>" for m in both[:12])
    faq = [
        ("Does Vast.ai bill per hour or per second?",
         "Prices are quoted per hour, but the GPU is billed per second while the instance is running. Your balance updates every few seconds."),
        ("Why am I charged when my instance is stopped?",
         "Stopping releases the GPU, but your disk stays on the host's machine, so storage keeps billing. Delete the instance to stop all charges."),
        ("What happens when my balance reaches zero?",
         "Your instances are stopped automatically. With a card on file, Vast.ai charges it to cover the negative balance and your data stays. "
         "Without one, the instances and their data are eventually deleted."),
        ("What is the minimum deposit on Vast.ai?",
         "$5. You can add credit by card (Stripe) or crypto (BitPay, Crypto.com), and set up automatic top-ups with a saved card."),
        ("Can I get a refund?",
         "Not for credit you've already spent. For unspent credit, ask Vast.ai through the website chat; its docs say that's refundable in most cases."),
        ("Does the referral link change any of these prices?",
         "No. Prices are the same with or without it. Signing up through it only tells Vast.ai that this site sent you."),
    ]
    body = f"""
<div class="crumbs"><a href="/">Vast.ai referral code</a> › How pricing works</div>
<h1>Vast.ai pricing explained ({year}): on-demand, interruptible and reserved</h1>
<p class="lead">Vast.ai has no price list. Every host sets its own rates, so the same GPU can cost very different amounts.
Here's what you're charged for and how to pay less.</p>

<h2>The three things you pay for</h2>
<div class="grid">
<div class="card"><b>GPU</b><span>per second, only while the instance is running</span></div>
<div class="card"><b>Storage</b><span>per GB, for as long as the instance exists, even when stopped</span></div>
<div class="card"><b>Bandwidth</b><span>per byte, for uploads and downloads</span></div>
</div>
<p>All three rates are set by the host and shown before you rent: hover over the price of an offer to see the breakdown.
The prices on this site are the GPU part only.</p>

<h2>On-demand, interruptible or reserved</h2>
<div class="tablewrap"><table class="wraps">
<thead><tr><th>Type</th><th>Price</th><th>Can it be interrupted?</th><th>Good for</th></tr></thead>
<tbody>
<tr><td><b>On-demand</b></td><td>Fixed, set by the host</td><td>No</td><td>Work that has to keep running</td></tr>
<tr><td><b>Interruptible</b></td><td>You bid; often 50% or more below on-demand</td><td>Yes, when outbid or rented on demand</td><td>Jobs that save checkpoints</td></tr>
<tr><td><b>Reserved</b></td><td>Up to 50% off for pre-paying</td><td>No</td><td>The same instance for weeks or months</td></tr>
</tbody></table></div>

<h2>On-demand vs interruptible prices right now</h2>
<p>Lowest prices per GPU-hour among verified machines free at the last update ({e(updated)}).</p>
<div class="tablewrap"><table>
<thead><tr><th>GPU</th><th class="num">On-demand from</th><th class="num">Interruptible from</th><th class="num">Difference</th><th class="num">30 days on demand</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<p class="small">“Interruptible from” is the lowest minimum bid. A minimum bid gets you the machine only while nobody bids more.
<a href="/#prices">See all {len(models)} GPU models →</a></p>

<h2>How reserved discounts work</h2>
<p>You don't rent a reserved instance directly. You rent on demand, then pre-pay for that instance from its card on the Instances page.
The longer the period you pre-pay, the bigger the discount, up to 50%.</p>
<ul>
<li>The pre-paid credit is locked to that one instance and can't move to another host.</li>
<li>If you cancel early, Vast.ai takes back the discount you've used so far plus a 5% fee, and refunds the rest.</li>
<li>Adding small amounts mid-term recalculates the discount and can make it worse.</li>
</ul>

<h2>Costs that catch people out</h2>
<ul>
<li><b>Stopped instances still cost money.</b> Storage is billed until you delete the instance.</li>
<li><b>Bandwidth varies a lot.</b> Check the per-TB rate before you download large models or datasets.</li>
<li><b>Disk size is fixed at creation.</b> You can't grow it later, so pick enough the first time.</li>
<li><b>An empty balance stops everything.</b> Set up auto top-up, or a low-balance e-mail alert, for long jobs.</li>
</ul>

{codebox("New to Vast.ai? Sign up through our referral link")}

<h2>FAQ</h2>
{faq_html(faq)}
<p class="small">Source: Vast.ai's documentation (docs.vast.ai), checked {FACTS_CHECKED}. Terms can change; check Vast.ai's site before relying on them.</p>
"""
    return page("pricing.html", f"Vast.ai Pricing Explained {year}: On-Demand, Interruptible, Reserved",
                "How Vast.ai pricing works: per-second GPU billing, storage and bandwidth charges, interruptible bids, "
                "reserved discounts up to 50%, and live price examples.",
                body, [faq_ld(faq)], og="/og/pricing.png", og_alt="Vast.ai pricing explained",
                crumbs=[(SITE_NAME, BASE + "/"), ("How pricing works", canonical("pricing.html"))])


def main():
    data, live = load_pricing()
    if live and chart.append(HISTORY, data):
        print("recorded price snapshot", file=sys.stderr)
    STATE["hist"] = chart.load(HISTORY)
    t = chart.parse_ts(data["generated_at"])
    updated = t.strftime("%-d %b %Y, %H:%M UTC")
    year = t.year

    # Free machines first, most expensive GPUs on top; then models with nothing free.
    models = sorted(data["models"], key=lambda m: (m["machines"] == 0, -m["min"]))

    if os.path.exists(DIST):
        shutil.rmtree(DIST)
    os.makedirs(os.path.join(DIST, "gpu"))
    STATE["modified"] = t.isoformat()

    try:
        import og
        os.makedirs(os.path.join(DIST, "og", "gpu"))
        avail = [m for m in models if m["machines"] > 0]
        stats = None
        if avail:
            c = min(avail, key=lambda m: m["min"])
            stats = (f"GPUs from {usd(c['min'])}/hr", f"{len(avail)} GPU models free now")
        og.home(os.path.join(DIST, "og", "home.png"), LINK_TEXT, stats)
        og.pricing(os.path.join(DIST, "og", "pricing.png"), LINK_TEXT)
        for m in models:
            sub = (f"{plural(m['machines'], 'machine')} free now" if m["machines"] else "none free right now")
            og.gpu(os.path.join(DIST, "og", "gpu", m["slug"] + ".png"), LINK_TEXT, m["name"], usd(m["min"]), sub, m["vram_gb"])
        og.icons(DIST)
        STATE["images"] = True
    except ImportError as ex:
        print(f"Pillow not available ({ex}); building without share images", file=sys.stderr)

    def write(rel, text):
        with open(os.path.join(DIST, rel), "w") as f:
            f.write(text)

    write("index.html", build_index(data, models, updated, year))
    for m in models:
        write(f"gpu/{m['slug']}.html", build_gpu(m, models, updated))
    write("pricing.html", build_pricing(models, updated, year))
    os.makedirs(os.path.join(DIST, "data"))
    if os.path.exists(HISTORY):
        shutil.copy(HISTORY, os.path.join(DIST, "data", HISTORY_NAME))

    write("404.html", page("404.html", "Page not found | Vast.ai Referral Code", "Page not found.",
                           f"<h1>Page not found</h1><p>Looking for the Vast.ai referral link? Here it is.</p>{codebox()}",
                           noindex=True))
    write("site.webmanifest", json.dumps({"name": SITE_NAME, "short_name": "vastaicode", "start_url": "/", "display": "browser",
                                          "background_color": "#0a0f10", "theme_color": "#0a0f10",
                                          "icons": [{"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
                                                    {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"}]}))
    write(f"{INDEXNOW_KEY}.txt", INDEXNOW_KEY)
    write("favicon.svg", FAVICON)
    write("CNAME", DOMAIN + "\n")
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n")

    lastmod = t.strftime("%Y-%m-%d")
    urls = [BASE + "/", BASE + "/pricing"] + [f"{BASE}/gpu/{m['slug']}" for m in models]
    write("urls.txt", "\n".join(urls) + "\n")  # for the IndexNow ping in CI
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
          + "".join(f"<url><loc>{u}</loc><lastmod>{lastmod}</lastmod></url>\n" for u in urls) + "</urlset>\n")

    lines = [f"# Vast.ai referral link: {SIGNUP}", "",
             f"> Unofficial site. Vast.ai is a GPU rental marketplace where hosts set their own prices. Its referral works through a link, "
             f"not a typed code: {SIGNUP} (referral ID {REF_ID}). The link gives the new user no discount; Vast.ai pays the referrer 3% of spend.", "",
             f"## GPU prices (USD per GPU-hour, GPU only, verified machines free to rent, {updated})", ""]
    lines += [f"- [{m['name']}]({BASE}/gpu/{m['slug']}): on-demand from {usd(m['min'])}"
              + (f", interruptible from {usd(m['bid'])}" if m["bid"] is not None else "")
              + f", {m['vram_gb']} GB, {plural(m['machines'], 'machine')} free" for m in models]
    lines += ["", "## Guides", "",
              f"- [How Vast.ai pricing works]({BASE}/pricing): on-demand, interruptible, reserved, storage and bandwidth"]
    write("llms.txt", "\n".join(lines) + "\n")

    print(f"built {len(models) + 2} pages into dist/ ({'live' if live else 'fallback'} prices, {updated})", file=sys.stderr)


if __name__ == "__main__":
    main()
