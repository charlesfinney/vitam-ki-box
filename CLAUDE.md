# Vita AI Concierge website: instructions for Claude

Nov 6, 2026 · Charles Finney +1 (332) 249-3276

Draft website for Vita AI Concierge, a private, air-gapped AI in a rugged case sold with full concierge service. Readers are non-technical; the site is shared with the team and early investors. It stays a draft: every page `noindex`, demo order form that sends nothing.

## Rules
1. Never edit the built pages (`index.html`, `impressum.html`, `datenschutz.html`, `artikel-*.html`, `en/`, `uk/`). Edit the sources in `build/content/<lang>/`, `build/i18n/<lang>.json`, `build/templates/`, then rebuild.
2. Build: `cd build && npm install && npm run build` (Python 3 with Jinja2, Tailwind 3.4.17). Commit the built pages too: GitHub Pages deploys from `main`, root folder.
3. Check every change with Playwright at 1280 and 390 px: `document.documentElement.scrollWidth` must equal the viewport width; no request may leave the site.
4. German is written natively for German readers; English and Ukrainian are written natively too, never translated literally. Ukrainian copy needs a native speaker's review.
5. Don't invent facts, figures, quotes or social proof. Cite sources.
6. Keep the look: black top bar, white header, white and lavender (#e6e6f0) sections, slate (#424257) bands, colourful line icons (#d4800f, #5aa31c, #2b9bd9, #4a69c9, #c9425a). Type: Unbounded (light) for headings, big numbers and the wordmark, Inter for all other text, both self-hosted with Cyrillic (decided by Charles, Nov 8, 2026). Unbounded is wide: check long German and Ukrainian words in headings at 390 px. No third-party requests.
7. Product name "Vita AI Concierge" (renamed from "Vita Concierge" by Charles, Nov 9, 2026; wordmark "VITA AI Concierge"); company stays "Vitam Box GbR"; e-mail stays hello@vitambox.de. Don't name the prototype case maker.
8. Share cards: `python3 build/make_og.py` renders `assets/img/og-<lang>.png` from `build/og/card.html` and the `og` text in `build/i18n/<lang>.json`.
9. Working style with Charles: most important first, short paragraphs, numbered steps, no compliments. Documents carry the byline "date · Charles Finney +1 (332) 249-3276".
10. Decisions, business model and handoff live in the claude.ai Project "Vita Concierge" (`landing-page/HANDOFF.md`, `landing-page/decisions-and-prelaunch.md`, `business/business-model.md`). If Charles pastes from them, they win over this file.
11. Judge every visual change against `DESIGN.md` (what premium means for our buyers, what is not us, and the checks before anything ships).
12. Measurement (`pruefstand/`, page `messen.html`): we promise that an update is installed only if it does no worse on the client's own tasks, with the result signed in the service book. Never publish a measured figure that the Prüfstand did not produce on Vita's hardware; until then, say target values. Run `python3 pruefstand/pruefstand.py selftest` after changing anything in `pruefstand/`.
