"""Fetch a snapshot of Vast.ai's public marketplace offers and summarize it per GPU model.

Uses Vast.ai's offer search. With an API key (VAST_API_KEY) one request returns everything.
Without a key the search returns at most 64 offers per request, and a different part of the market
each time, so the snapshot is merged from many requests and is close to complete, not exact.
"""
import collections
import datetime as dt
import json
import re
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SEARCH_URL = "https://console.vast.ai/api/v0/bundles/"
UA = "gpu-price-site-builder/1.0"
CAP = 64            # most offers one request returns without an API key
ROUNDS = 2          # without a key every request returns a different part of the market, so ask more than once
MAX_REQUESTS = 450
PAUSE = 1.3         # seconds between requests (faster gets HTTP 429)
BASE_QUERY = {"verified": {"eq": True}, "rentable": {"eq": True}, "rented": {"eq": False}, "type": "on-demand"}

_count = 0


def _get(query, api_key=None):
    global _count
    url = SEARCH_URL + "?q=" + urllib.parse.quote(json.dumps(query))
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    for attempt in range(6):
        _count += 1
        if _count > MAX_REQUESTS:
            raise RuntimeError("too many requests to the offer search")
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=90) as r:
                return json.load(r)["offers"]
        except urllib.error.HTTPError as ex:
            if ex.code not in (429, 500, 502, 503, 504) or attempt == 5:
                raise RuntimeError(f"offer search answered HTTP {ex.code}") from None  # never echo the request
            time.sleep(8 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError) as ex:
            if attempt == 5:
                raise RuntimeError(f"offer search unreachable: {getattr(ex, 'reason', ex)}") from None
            time.sleep(8 * (attempt + 1))


def _walk(extra, out):
    """Collect offers matching `extra`, splitting the price range wherever a request comes back full."""
    def rec(lo, hi):
        page = _get({**BASE_QUERY, **extra, "dph_total": {"gte": lo, "lt": hi}, "limit": CAP})
        time.sleep(PAUSE)
        out.extend(page)
        if len(page) >= CAP and hi - lo > 1e-3:
            mid = (lo + hi) / 2 if lo > 0 else hi / 8
            rec(lo, mid)
            rec(mid, hi)
    rec(0, 4000)


def fetch_offers(api_key=None, known_names=()):
    """Verified, currently rentable on-demand offers. Returns (offers, complete).

    With an API key one request returns the whole market (complete=True).
    Without one, Vast.ai returns at most 64 offers per request and a different subset every time, so we
    ask per GPU model, several times, and merge. That finds most machines but not provably all of them.
    """
    global _count
    _count = 0
    if api_key:
        offers = _get({**BASE_QUERY, "limit": 20000}, api_key)
        if len(offers) > CAP:
            print(f"vast: {len(offers)} offers with API key", file=sys.stderr)
            return offers, True
        print("vast: API key request returned a capped result; using the keyless method", file=sys.stderr)
    found = []
    _walk({}, found)
    names = sorted({o["gpu_name"] for o in found if o.get("gpu_name")} | set(known_names))
    for _ in range(ROUNDS):
        for name in names:
            _walk({"gpu_name": {"eq": name}}, found)
    print(f"vast: {len(found)} offer rows, {len({o['machine_id'] for o in found})} machines, "
          f"{len(names)} models in {_count} requests (no API key)", file=sys.stderr)
    return found, False


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def gpu_class(name):
    n = name.upper()
    if n.startswith(("TITAN", "GTX", "RX ", "ARC")) or re.match(r"RTX \d0[5-9]0", n):
        return "consumer"       # RTX 3090, RTX 4070S Ti, RTX 5060 Ti, RTX 3060 laptop ...
    if n.startswith(("RTX", "QUADRO", "Q RTX")):
        return "professional"   # RTX A6000, RTX 6000Ada, RTX PRO 6000, Quadro P4000 ...
    return "datacenter"         # H100, A100, L40S, B200, Tesla ...


def summarize(offers, complete=False, now=None):
    """-> {"generated_at", "complete", "market": {...}, "models": [...]} with prices in USD per GPU-hour.

    A machine can show up as several offers (different slices of its GPUs, or the same one fetched twice):
    each machine counts once, at its lowest price per GPU."""
    now = now or dt.datetime.now(dt.timezone.utc)
    by = collections.defaultdict(dict)
    for o in offers:
        if not (o.get("gpu_name") and o.get("num_gpus") and o.get("dph_base")):
            continue
        m = by[o["gpu_name"]].setdefault(o["machine_id"], {"price": None, "bid": None, "gpus": 0, "o": o})
        price = o["dph_base"] / o["num_gpus"]
        if m["price"] is None or price < m["price"]:
            m["price"], m["o"] = price, o
        if o.get("min_bid"):
            bid = o["min_bid"] / o["num_gpus"]
            m["bid"] = bid if m["bid"] is None else min(m["bid"], bid)
        m["gpus"] = max(m["gpus"], o["num_gpus"])
    models = []
    for name, machines in by.items():
        lst = sorted(machines.values(), key=lambda m: m["price"])
        price = [m["price"] for m in lst]
        bids = [m["bid"] for m in lst if m["bid"] is not None]
        vram = collections.Counter(round(m["o"]["gpu_ram"] / 1024) for m in lst).most_common(1)[0][0]
        dc = [m["price"] for m in lst if m["o"].get("hosting_type") == 1]
        models.append({
            "name": name, "slug": slugify(name), "gpu_class": gpu_class(name), "vram_gb": vram,
            "min": round(price[0], 4), "median": round(statistics.median(price), 4), "max": round(price[-1], 4),
            "bid": round(min(bids), 4) if bids else None,
            "dc_min": round(min(dc), 4) if dc else None,
            "machines": len(lst), "gpus": sum(m["gpus"] for m in lst),
            "max_gpus": max(m["gpus"] for m in lst),
            "countries": len({(m["o"].get("geolocation") or "").split(",")[-1].strip() for m in lst} - {""}),
            "best_location": lst[0]["o"].get("geolocation") or None,
            "last_seen": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
    market = {"machines": sum(m["machines"] for m in models), "gpus": sum(m["gpus"] for m in models), "models": len(models)}
    return {"generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "unit": "USD per GPU-hour", "complete": complete,
            "market": market, "models": models}


if __name__ == "__main__":
    import os
    data = summarize(*fetch_offers(os.environ.get("VAST_API_KEY")))
    print(json.dumps(data["market"]), "complete" if data["complete"] else "sampled")
    for m in sorted(data["models"], key=lambda m: -m["machines"])[:40]:
        print(f"{m['name']:22} {m['vram_gb']:4}GB min={m['min']:<7} med={m['median']:<7} bid={m['bid']} machines={m['machines']} gpus={m['gpus']}")
