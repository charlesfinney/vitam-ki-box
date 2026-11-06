# Vita Concierge: draft website

Nov 6, 2026 · Charles Finney +1 (332) 249-3276

Draft website for Vita Concierge, your own AI in a case, to accompany the proposal. The repo keeps its old name (`vitam-ki-box`) so the shared link stays the same. For the team and early investors. Not a live shop: the order form is a demo and sends nothing.

Live: https://charlesfinney.github.io/vitam-ki-box/ (German), `/en/` (English) and `/uk/` (Ukrainian; the switcher shows "UA"). All pages carry `noindex`, so search engines leave the draft alone.

## What's here
1. Built pages, served by GitHub Pages: German at the root (`index.html`, Impressum, Datenschutz, three article stubs `artikel-*.html`), English in `en/`, Ukrainian in `uk/`. Do not edit these by hand: the next build overwrites them.
2. `assets/`: compiled CSS, self-hosted Inter font (SIL OFL), images.
3. `build/`: the sources and the build.
   - `content/<lang>/*.html`: each page's text, written natively per language, with a short header (`title`, `description`).
   - `i18n/<lang>.json`: top bar, header and footer text per language.
   - `templates/`: page shell, top bar and header, footer, flags. Written once for all languages.
   - `generate.py` builds the pages; Tailwind builds `assets/vitam.css`; `make_artifact.py` builds a single-file preview.

## Editing
1. Edit the source in `build/content/`, `build/i18n/` or `build/templates/`.
2. `cd build && npm install && npm run build` builds all pages and the CSS (needs Python 3 with Jinja2: `pip install jinja2`).
3. A new page in a language: add `build/content/<lang>/<name>.html`. If the same file name exists in another language, the pages link to each other (`hreflang` and the language switcher).
4. Commit and push (or upload) the sources and the built pages. GitHub Pages republishes within a minute or two.
