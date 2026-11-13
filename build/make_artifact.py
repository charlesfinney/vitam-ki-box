"""Build single-file versions of the landing page (index + Impressum + Datenschutz in one HTML file).

Outputs:
  vitam-box-landing.html   fragment for the Claude artifact (the artifact adds doctype/head/body)
  preview-standalone.html  complete document that opens on its own, e.g. by double-clicking inside the zip

CSS, Inter font files and images are inlined as data URIs, so neither file needs the assets/ folder.
Impressum, Datenschutz and the artikel-*.html pages become hash views (#impressum, #artikel-training, …).
Run after `npm run build`. Expects the site HTML in ./src (dev) or in the parent folder (project layout)."""
import re, base64, pathlib

here = pathlib.Path(__file__).parent
site = here / 'src' if (here / 'src' / 'index.html').exists() else here.parent
css_file = here / 'vitam.css' if (here / 'vitam.css').exists() else site / 'assets' / 'vitam.css'

idx = (site / 'index.html').read_text()
PAGES = ['impressum', 'datenschutz'] + sorted(f.stem for f in site.glob('artikel-*.html'))
css = css_file.read_text()

def b64(path):
    return base64.b64encode(path.read_bytes()).decode()

# Fonts referenced from vitam.css as fonts/<file>.woff2 -> data URIs
css = re.sub(r"url\((['\"]?)fonts/([^'\")]+\.woff2)\1\)",
             lambda m: f"url(data:font/woff2;base64,{b64(site / 'assets' / 'fonts' / m.group(2))})", css)

def body_inner(html):
    return re.search(r'<body[^>]*>(.*)</body>', html, re.S).group(1)

def main_parts(html):
    m = re.search(r'<main([^>]*)>(.*?)</main>', html, re.S)
    return m.group(1), m.group(2)

body = body_inner(idx)

# Legal views, built from each page's <main>
legal = ''
for vid in PAGES:
    html = (site / f'{vid}.html').read_text()
    attrs, inner = main_parts(html)
    cls = re.search(r'class="([^"]*)"', attrs).group(1)
    legal += f'\n  <div id="view-{vid}" class="view border-t border-line" hidden><main class="{cls}">{inner}</main></div>\n'

body = body.replace('<main>', '<main id="view-home" class="view">', 1)
body = body.replace('</main>', '</main>' + legal, 1)

# Internal links -> hash routes
for vid in PAGES:
    body = body.replace(f'href="{vid}.html"', f'href="#{vid}"')
body = body.replace('href="index.html#', 'href="#')
body = body.replace('href="index.html"', 'href="#"')
# The preview holds only the German pages: the EN / UA switcher opens the live site instead
for lang in ('en', 'uk'):
    body = body.replace(f'href="{lang}/index.html"', f'href="https://charlesfinney.github.io/vitam-ki-box/{lang}/" target="_blank" rel="noopener"')
# No server behind a single file: drop the form endpoint (the demo script already prevents submit)
body = body.replace(' action="/waitlist" method="post"', '')

# Images -> data URIs
body = re.sub(r'src="(assets/img/[^"]+\.jpg)"',
              lambda m: f'src="data:image/jpeg;base64,{b64(site / m.group(1))}"', body)

router = '''
  <script>
    // Hash views: #impressum and #datenschutz show the legal pages; every other hash shows the home view.
    (function () {
      var views = __VIEWS__;
      function route() {
        var h = location.hash.replace('#', '');
        var active = views[h] || 'view-home';
        document.querySelectorAll('.view').forEach(function (v) { v.hidden = v.id !== active; });
        if (!h || views[h]) { window.scrollTo(0, 0); return; }
        var t = h && document.getElementById(h);
        if (t) t.scrollIntoView();
      }
      window.addEventListener('hashchange', route);
      route();
    })();
  </script>
'''
import json
router = router.replace('__VIEWS__', json.dumps({v: f'view-{v}' for v in PAGES}))
body = body.rstrip() + '\n' + router

style = f'''<style>
/* Single light look by design (UI-design.html palette): white ground, #e6e6f0 hairlines, #74748a muted, #424257 slate, #4d65cb focus. */
:root {{ color-scheme: light; }}
{css}
body {{ margin: 0; background: #ffffff; color: #000000; font-family: Inter, system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif; font-size: 16px; font-weight: 300; line-height: 1.5; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }}
img {{ max-width: 100%; }}
.px-5 {{ padding-left: max(20px, env(safe-area-inset-left, 0px)); padding-right: max(20px, env(safe-area-inset-right, 0px)); }}
.page-top {{ padding-bottom: calc(8px + env(safe-area-inset-bottom, 0px)); right: calc(4% + env(safe-area-inset-right, 0px)); }}
@media (prefers-reduced-motion: reduce) {{ html {{ scroll-behavior: auto; }} * {{ transition: none !important; }} }}
</style>
'''

# 1) Artifact fragment
artifact = '<title>Vita AI Concierge</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n' + style + body
(here / 'vitam-box-landing.html').write_text(artifact)

# 2) Standalone document: reuse index.html's own <head> metadata, swap the stylesheet link for the inline style
head = re.search(r'<head>(.*?)</head>', idx, re.S).group(1)
head = re.sub(r'\s*<link rel="stylesheet" href="assets/vitam.css" />', '', head)
standalone = f'<!DOCTYPE html>\n<html lang="de">\n<head>{head.rstrip()}\n{style}</head>\n<body>{body}</body>\n</html>\n'
(here / 'preview-standalone.html').write_text(standalone)

for f in ('vitam-box-landing.html', 'preview-standalone.html'):
    print(f, (here / f).stat().st_size)
