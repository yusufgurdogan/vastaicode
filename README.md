# vastaicode.com

Unofficial Vast.ai referral link site (`https://cloud.vast.ai/?ref_id=881041`) with live GPU prices.

- `vast.py` reads every verified, unrented on-demand offer from Vast.ai's public offer search
  (no API key; 64 offers per request, paged by price) and summarizes it per GPU model.
- `build.py` (Python stdlib only; Pillow optional for share images) writes the site to `dist/`.
  If the fetch fails it uses `data/pricing-fallback.json`. Each live build appends a snapshot to `data/history.csv`.
- GitHub Actions builds and deploys to GitHub Pages on push, every 3 hours, and on manual dispatch.

Local build: `python3 build.py`, then open `dist/index.html`.

Statements about Vast.ai's terms (3% referral, $5 minimum deposit, billing rules) come from docs.vast.ai.
When you re-check them, update `FACTS_CHECKED` in `build.py`.
