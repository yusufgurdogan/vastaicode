"""Fetch a snapshot of Vast.ai's public marketplace offers and summarize it per GPU model.

Uses the same unauthenticated offer search the Vast console uses. It returns at most 64 offers
per request, so we walk the whole market in price order.
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
PAGE = 64          # server-side cap for requests without an API key
MAX_REQUESTS = 400
PAUSE = 0.6        # seconds between requests


def _get(query):
    url = SEARCH_URL + "?q=" + urllib.parse.quote(json.dumps(query))
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)["offers"]
        except urllib.error.HTTPError as ex:
            if ex.code not in (429, 500, 502, 503, 504) or attempt == 4:
                raise
            time.sleep(3 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError):
            if attempt == 4:
                raise
            time.sleep(3 * (attempt + 1))


def fetch_offers():
    """All verified, currently rentable on-demand offers. Pages by price because there is no offset."""
    base = {"verified": {"eq": True}, "rentable": {"eq": True}, "rented": {"eq": False}, "type": "on-demand",
            "order": [["dph_total", "asc"]], "limit": PAGE}
    seen, floor, n = {}, None, 0
    while n < MAX_REQUESTS:
        query = dict(base)
        if floor is not None:
            query["dph_total"] = {"gte": floor}
        page = _get(query)
        n += 1
        new = [o for o in page if o["id"] not in seen]
        for o in new:
            seen[o["id"]] = o
        if len(page) < PAGE:
            break
        top = max(o["dph_total"] for o in page)
        if not new or top == floor:
            # A whole page at one price: step just past it (we may miss a few identical offers).
            top = (floor if floor is not None else top) + 1e-6
        floor = top
        time.sleep(PAUSE)
    else:
        raise RuntimeError("offer search did not finish")
    print(f"vast: {len(seen)} offers in {n} requests", file=sys.stderr)
    return list(seen.values())


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def gpu_class(name):
    n = name.upper()
    if n.startswith(("TITAN", "GTX", "RX ", "ARC")) or re.match(r"RTX \d0[5-9]0", n):
        return "consumer"       # RTX 3090, RTX 4070S Ti, RTX 5060 Ti, RTX 3060 laptop ...
    if n.startswith(("RTX", "QUADRO", "Q RTX")):
        return "professional"   # RTX A6000, RTX 6000Ada, RTX PRO 6000, Quadro P4000 ...
    return "datacenter"         # H100, A100, L40S, B200, Tesla ...


def summarize(offers, now=None):
    """-> {"generated_at", "market": {...}, "models": [...]} with prices in USD per GPU-hour."""
    now = now or dt.datetime.now(dt.timezone.utc)
    by = collections.defaultdict(list)
    for o in offers:
        if o.get("gpu_name") and o.get("num_gpus") and o.get("dph_base"):
            by[o["gpu_name"]].append(o)
    models = []
    for name, lst in by.items():
        price = sorted(o["dph_base"] / o["num_gpus"] for o in lst)
        bids = [o["min_bid"] / o["num_gpus"] for o in lst if o.get("min_bid")]
        machines = {}
        for o in lst:  # one machine can appear as several offers (slices of its GPUs)
            machines[o["machine_id"]] = max(machines.get(o["machine_id"], 0), o["num_gpus"])
        vram = collections.Counter(round(o["gpu_ram"] / 1024) for o in lst).most_common(1)[0][0]
        dc = [o["dph_base"] / o["num_gpus"] for o in lst if o.get("hosting_type") == 1]
        best = min(lst, key=lambda o: o["dph_base"] / o["num_gpus"])
        models.append({
            "name": name, "slug": slugify(name), "gpu_class": gpu_class(name), "vram_gb": vram,
            "min": round(price[0], 4), "median": round(statistics.median(price), 4), "max": round(price[-1], 4),
            "bid": round(min(bids), 4) if bids else None,
            "dc_min": round(min(dc), 4) if dc else None,
            "machines": len(machines), "gpus": sum(machines.values()), "offers": len(lst),
            "max_gpus": max(o["num_gpus"] for o in lst),
            "countries": len({(o.get("geolocation") or "").split(",")[-1].strip() for o in lst} - {""}),
            "best_location": best.get("geolocation") or None,
            "last_seen": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
    market = {"offers": len(offers), "machines": len({o["machine_id"] for o in offers}),
              "gpus": sum(m["gpus"] for m in models), "models": len(models)}
    return {"generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "unit": "USD per GPU-hour", "market": market,
            "models": models}


if __name__ == "__main__":
    data = summarize(fetch_offers())
    print(json.dumps(data["market"]))
    for m in sorted(data["models"], key=lambda m: -m["machines"]):
        print(f"{m['name']:22} {m['gpu_class']:12} {m['vram_gb']:4}GB min={m['min']:<7} med={m['median']:<7} bid={m['bid']} dc={m['dc_min']} machines={m['machines']} gpus={m['gpus']} countries={m['countries']}")
