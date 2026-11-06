"""Render the share cards (Open Graph images) that messaging apps show for a shared link.

Source:  build/og/card.html (layout) + the "og" block in build/i18n/<lang>.json (text)
Output:  assets/img/og-<lang>.png, 1200 x 630 px, referenced by every page via <meta property="og:image">

Run only when the card's text or look changes:  python3 build/make_og.py
Needs Python Playwright with Chromium (pip install playwright && playwright install chromium).
Inter with Cyrillic should be installed on the machine for the Ukrainian card; the repo's own font files are Latin only.
"""
import json, pathlib
from jinja2 import Template
from playwright.sync_api import sync_playwright

BUILD = pathlib.Path(__file__).resolve().parent
SITE = BUILD.parent
LANGS = ['de', 'en', 'uk']

card = Template((BUILD / 'og' / 'card.html').read_text())
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1200, 'height': 630}, device_scale_factor=1)
    for code in LANGS:
        og = json.loads((BUILD / 'i18n' / f'{code}.json').read_text())['og']
        tmp = BUILD / 'og' / f'_render-{code}.html'  # next to card.html, so relative font paths resolve
        tmp.write_text(card.render(lang=code, **og))
        page.goto(tmp.as_uri())
        page.evaluate('document.fonts.ready')
        out = SITE / 'assets' / 'img' / f'og-{code}.png'
        page.screenshot(path=str(out))
        tmp.unlink()
        print('rendered', out.relative_to(SITE), out.stat().st_size // 1024, 'KB')
    browser.close()
