"""Build the site in three languages from one set of templates.

Sources (edit these):
  build/content/<lang>/<page>.html   front matter (title, description) + the page's <main>, written natively per language
  build/i18n/<lang>.json             top bar, header and footer text per language
  build/templates/                   page shell, top bar + header, footer, flags (written once)

Output (do not edit, it is overwritten):
  German at the site root, English in en/, Ukrainian in uk/.

Run from anywhere:  python3 build/generate.py   (needs Jinja2: pip install jinja2)
Then rebuild the CSS:  cd build && npm run build
"""
import json, pathlib, sys
from jinja2 import Environment, FileSystemLoader, StrictUndefined

BUILD = pathlib.Path(__file__).resolve().parent
SITE = BUILD.parent
BASE_URL = 'https://charlesfinney.github.io/vitam-ki-box/'

# code, output folder (relative to the site root). German is the default (x-default).
LANGS = [('de', ''), ('en', 'en/'), ('uk', 'uk/')]
DEFAULT = 'de'


def read_page(path):
    """Split '---' front matter (key: value lines) from the page body."""
    text = path.read_text()
    if not text.startswith('---\n'):
        sys.exit(f'{path}: missing front matter')
    head, body = text[4:].split('\n---\n', 1)
    meta = dict(line.split(': ', 1) for line in head.splitlines() if line.strip())
    if 'title' not in meta:
        sys.exit(f'{path}: front matter needs a title')
    return meta, body.rstrip('\n')


def main():
    env = Environment(loader=FileSystemLoader(BUILD / 'templates'), autoescape=False,
                      undefined=StrictUndefined, keep_trailing_newline=True)
    page_tpl = env.get_template('page.html')

    strings = {code: json.loads((BUILD / 'i18n' / f'{code}.json').read_text()) for code, _ in LANGS}
    pages = {code: {p.name: p for p in sorted((BUILD / 'content' / code).glob('*.html'))} for code, _ in LANGS}
    folder = dict(LANGS)

    for code, out in LANGS:
        t = strings[code]
        if len(t['nav']) not in (0, 4):
            sys.exit(f'i18n/{code}.json: the header has room for exactly 4 menu items (or none)')
        root = '../' * out.count('/')  # path from this language's folder back to the site root
        for name, src in pages[code].items():
            meta, main_html = read_page(src)
            # hreflang alternates: only for pages that exist in more than one language
            langs_with_page = [c for c, _ in LANGS if name in pages[c]]
            alternates = []
            if len(langs_with_page) > 1:
                url = lambda c: BASE_URL + folder[c] + ('' if name == 'index.html' else name)
                alternates = [{'hreflang': c, 'href': url(c)} for c in langs_with_page]
                alternates.append({'hreflang': 'x-default', 'href': url(DEFAULT)})
            # language switcher: same page in the other language if it exists, else that language's home page
            switcher = []
            for c, f in LANGS:
                target = name if name in pages[c] else 'index.html'
                switcher.append({'code': c, 'label': strings[c]['label'], 'name': strings[c]['name'],
                                 'current': c == code, 'href': root + f + target})
            html = page_tpl.render(
                lang=code, name=name, t=t, root=root, switcher=switcher, alternates=alternates,
                title=meta['title'], description=meta.get('description'),
                home='' if name == 'index.html' else 'index.html',
                divider=name != 'index.html', main=main_html)
            dest = SITE / out / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(html)
            print('built', out + name)


if __name__ == '__main__':
    main()
