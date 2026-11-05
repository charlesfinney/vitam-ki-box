# Vitam KI Box: draft website

Nov 5, 2026 · Charles Finney +1 (332) 249-3276

Draft website for the Vitam KI Box, to accompany the proposal. For the team and early investors. Not a live shop: the order form is a demo and sends nothing.

Live: https://charlesfinney.github.io/vitam-ki-box/

## What's here
1. `index.html` with Impressum, Datenschutz and three article stubs (`artikel-*.html`).
2. `assets/`: compiled CSS, self-hosted Inter font (SIL OFL), images.
3. `build/`: Tailwind source and the scripts that keep the pages in sync.

All pages carry `noindex`, so search engines leave the draft alone.

## Editing
1. Edit `index.html`.
2. `python3 build/sync_chrome.py` copies the top bar, header and footer into the other pages.
3. `cd build && npm install && npm run build` regenerates `assets/vitam.css`.
4. Commit and push. GitHub Pages republishes within a minute or two.
