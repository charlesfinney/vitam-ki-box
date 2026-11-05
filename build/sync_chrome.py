"""Copy the top bar, header and footer from index.html into the sub-pages (Impressum, Datenschutz, artikel-*.html).

index.html marks its chrome with <!-- chrome:top --> … <!-- /chrome:top --> and <!-- chrome:footer --> … <!-- /chrome:footer -->.
In the sub-pages, in-page links (#box) become links back to the home page (index.html#box).
Run from the build folder (dev: ./src) or the project's build folder (site files one level up)."""
import re, pathlib

here = pathlib.Path(__file__).parent
site = here / 'src' if (here / 'src' / 'index.html').exists() else here.parent
index = (site / 'index.html').read_text()

def block(name):
    m = re.search(rf'<!-- chrome:{name} -->.*?<!-- /chrome:{name} -->', index, re.S)
    return m.group(0)

def for_subpage(html):
    return re.sub(r'href="#([a-z0-9-]+)"', r'href="index.html#\1"', html)

top = for_subpage(block('top'))
footer = for_subpage(block('footer'))
script = re.search(r'<a href="#" class="page-top".*?</script>', index, re.S).group(0)

pages = ['impressum.html', 'datenschutz.html'] + sorted(p.name for p in site.glob('artikel-*.html'))
for name in pages:
    f = site / name
    s = f.read_text()
    head, rest = s.split('<body class="font-sans antialiased">', 1)
    main = re.search(r'<main.*?</main>', rest, re.S).group(0)
    # product name: Vitam KI Box everywhere, except the company name
    head = re.sub(r'Vitam Box(?! GbR)', 'Vitam KI Box', head)
    main = re.sub(r'Vitam Box(?! GbR)', 'Vitam KI Box', main)
    body = ('<body class="font-sans antialiased">\n\n  ' + top + '\n  <div class="border-t border-line"></div>\n\n  '
            + main + '\n\n  ' + footer + '\n\n  ' + script + '\n</body>\n</html>\n')
    f.write_text(head + body)
    print('synced', name)
