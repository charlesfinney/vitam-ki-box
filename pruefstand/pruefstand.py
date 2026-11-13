#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Vitam Box GbR
"""Vita Prüfstand: measure a local language model on professional tasks, decide whether an
update may be installed, and write the service-book entry that the concierge and the client sign.

Stdlib only (Python 3.11+). Talks to any OpenAI-compatible endpoint (llama.cpp server, Ollama,
vLLM, LM Studio), normally on the same machine: inside the case, nothing leaves.

    python3 pruefstand.py run --endpoint http://127.0.0.1:8080/v1 --model current --tasks tasks --out results/current.json
    python3 pruefstand.py compare results/current.json results/candidate.json --out results/decision.json
    python3 pruefstand.py modes results/*.json
    python3 pruefstand.py serviceheft results/decision.json --client "Kanzlei Muster" --device VC-0001 --out eintrag.html
    python3 pruefstand.py validate tasks
    python3 pruefstand.py selftest

Method (see README.md): every task is answered runs x samples times (default 5 x 5), because answers
vary. Each answer is scored by checks written into the task (facts, numbers, dates, things that must
not be invented, length). Speed is measured from the stream: time to first word, words and tokens per
second while writing, and how fast the prompt is read.
"""
import argparse, glob, html, json, os, random, re, statistics, sys, time, tomllib, urllib.parse, urllib.request
from datetime import date, datetime

VERSION = '0.1.0'
SYSTEM_PROMPT = ('Du bist ein sorgfältiger Assistent für Kanzleien, Arztpraxen und Steuerberatungen. '
                 'Antworte auf Deutsch, knapp und genau. Nenne nur, was im Dokument steht. '
                 'Wenn etwas im Dokument fehlt, sag das, statt es zu raten.')

# ----------------------------------------------------------------------------------------------
# Tasks and checks
# ----------------------------------------------------------------------------------------------

PROFESSIONS = {'kanzlei': 'Kanzlei', 'praxis': 'Arztpraxis', 'steuer': 'Steuerberatung'}
KINDS = {'extraktion', 'zusammenfassung', 'frist', 'einordnung', 'schreiben', 'rechnen'}
CHECK_TYPES = {'contains', 'absent', 'number', 'date', 'max_words', 'order'}


def load_tasks(path):
    """Load every *.toml task in a folder (or one file), sorted by id."""
    files = sorted(glob.glob(os.path.join(path, '*.toml'))) if os.path.isdir(path) else [path]
    tasks = []
    for f in files:
        with open(f, 'rb') as fh:
            t = tomllib.load(fh)
        t['_file'] = os.path.basename(f)
        tasks.append(t)
    return sorted(tasks, key=lambda t: t['id'])


def norm(text):
    return re.sub(r'\s+', ' ', text.replace(' ', ' ').replace(' ', ' ')).strip()


def parse_numbers(text):
    """All numbers in a text, read the German way: 1.234,56 and 1 234,56 and 3.299 are 1234.56, 1234.56, 3299."""
    out = []
    for m in re.finditer(r'(?<![\d.,])\d{1,3}(?:[.\s  ]\d{3})+(?:,\d+)?(?![\d])|(?<![\d.,])\d+(?:[.,]\d+)?(?![\d])', text):
        s = m.group(0)
        s = re.sub(r'[\s  ]', '', s)
        if ',' in s:                                   # German decimal comma
            s = s.replace('.', '').replace(',', '.')
        elif re.fullmatch(r'\d{1,3}(\.\d{3})+', s):     # thousands dots
            s = s.replace('.', '')
        try:
            out.append(float(s))
        except ValueError:
            pass
    return out


MONTHS = ['januar', 'februar', 'märz', 'april', 'mai', 'juni', 'juli', 'august', 'september', 'oktober', 'november', 'dezember']


def date_patterns(iso):
    d = date.fromisoformat(iso)
    dd, mm, yyyy = d.day, d.month, d.year
    return [rf'\b0?{dd}\.\s?0?{mm}\.\s?(?:{yyyy}|{str(yyyy)[2:]})\b',
            rf'\b0?{dd}\.\s?{MONTHS[mm - 1]}\s+{yyyy}\b',
            rf'\b{yyyy}-{mm:02d}-{dd:02d}\b']


def run_check(check, answer):
    """True if the answer passes this check."""
    a = norm(answer)
    t = check['type']
    if t == 'contains':
        return any(re.search(p, a, re.I) for p in check['any'])
    if t == 'absent':
        return not any(re.search(p, a, re.I) for p in check['any'])
    if t == 'number':
        tol = check.get('tolerance', 0.005)
        return any(abs(n - check['value']) <= tol for n in parse_numbers(a))
    if t == 'date':
        return any(re.search(p, a, re.I) for p in date_patterns(check['value']))
    if t == 'max_words':
        return len(a.split()) <= check['value']
    if t == 'order':                                  # items appear in this order
        pos = []
        for group in check['items']:
            hits = [m.start() for p in group for m in [re.search(p, a, re.I)] if m]
            if not hits:
                return False
            pos.append(min(hits))
        return pos == sorted(pos)
    raise ValueError(f'unknown check type {t}')


def score_answer(task, answer):
    results = [{'name': c['name'], 'passed': run_check(c, answer), 'critical': bool(c.get('critical'))} for c in task['checks']]
    return sum(r['passed'] for r in results) / len(results), results


def validate_tasks(tasks):
    """Schema and regexes; each task's reference answer must pass every check, and its counterexample must fail a critical one."""
    problems, ids = [], set()
    for t in tasks:
        where, mine = t.get('_file', t.get('id', '?')), []
        missing = [k for k in ('id', 'profession', 'kind', 'title', 'instruction', 'document', 'checks', 'reference', 'counterexample') if k not in t]
        if missing:
            problems += [f'{where}: missing "{k}"' for k in missing]
            continue
        if t['id'] in ids:
            mine.append(f'duplicate id {t["id"]}')
        ids.add(t['id'])
        if t['profession'] not in PROFESSIONS:
            mine.append(f'profession must be one of {sorted(PROFESSIONS)}')
        if t['kind'] not in KINDS:
            mine.append(f'kind must be one of {sorted(KINDS)}')
        if not any(c.get('critical') for c in t['checks']):
            mine.append('needs at least one critical check')
        for c in t['checks']:
            if c.get('type') not in CHECK_TYPES:
                mine.append(f'check "{c.get("name")}" has unknown type {c.get("type")}')
                continue
            for pat in c.get('any', []) + [x for g in c.get('items', []) for x in g]:
                try:
                    re.compile(pat)
                except re.error as e:
                    mine.append(f'check "{c["name"]}" bad regex {pat!r}: {e}')
        if not mine:
            _, res = score_answer(t, t['reference'])
            mine += [f'reference answer fails check "{r["name"]}"' for r in res if not r['passed']]
            _, res = score_answer(t, t['counterexample'])
            if all(r['passed'] for r in res if r['critical']):
                mine.append('counterexample passes every critical check (checks are not sharp enough)')
        problems += [f'{where}: {m}' for m in mine]
    return problems


# ----------------------------------------------------------------------------------------------
# Talking to the model (OpenAI-compatible, streaming)
# ----------------------------------------------------------------------------------------------

def is_local(endpoint):
    host = urllib.parse.urlparse(endpoint).hostname or ''
    return host in ('localhost', '127.0.0.1', '::1') or host.endswith('.local')


def chat_stream(endpoint, model, messages, temperature, max_tokens, timeout=600, api_key=None, seed=None):
    url = endpoint.rstrip('/') + '/chat/completions'
    body = {'model': model, 'messages': messages, 'temperature': temperature, 'max_tokens': max_tokens,
            'stream': True, 'stream_options': {'include_usage': True}}
    if seed is not None:
        body['seed'] = seed
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method='POST')
    t0 = time.perf_counter()
    first, pieces, usage = None, [], None
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            line = raw.decode('utf-8', 'replace').strip()
            if not line.startswith('data:'):
                continue
            data = line[5:].strip()
            if data == '[DONE]':
                break
            obj = json.loads(data)
            if obj.get('usage'):
                usage = obj['usage']
            for ch in obj.get('choices') or []:
                piece = (ch.get('delta') or {}).get('content') or ''
                if piece:
                    if first is None:
                        first = time.perf_counter()
                    pieces.append(piece)
    t1 = time.perf_counter()
    return ''.join(pieces), t0, first or t1, t1, usage


def measure(answer, t0, first, t1, usage, prompt_chars):
    est = usage is None or 'completion_tokens' not in usage
    completion = (usage or {}).get('completion_tokens') or max(1, round(len(answer) / 4))
    prompt = (usage or {}).get('prompt_tokens') or max(1, round(prompt_chars / 4))
    ttft, writing = first - t0, max(t1 - first, 1e-9)
    return {'ttft_s': round(ttft, 4), 'total_s': round(t1 - t0, 4),
            'prompt_tokens': prompt, 'completion_tokens': completion, 'tokens_estimated': est,
            'prefill_tok_s': round(prompt / ttft, 2) if ttft > 0 else None,
            'decode_tok_s': round(max(completion - 1, 1) / writing, 2),
            'words': len(answer.split()), 'words_s': round(len(answer.split()) / writing, 2)}


def run_tasks(endpoint, model, tasks, runs=5, samples=5, temperature=0.7, max_tokens=700, api_key=None, label=None, log=print):
    started = datetime.now().isoformat(timespec='seconds')
    out = {'pruefstand': VERSION, 'label': label or model, 'model': model, 'endpoint_local': is_local(endpoint),
           'runs': runs, 'samples': samples, 'temperature': temperature, 'started': started, 'tasks': []}
    for t in tasks:
        user = f"{t['instruction'].strip()}\n\n---\n{t['document'].strip()}"
        messages = [{'role': 'system', 'content': SYSTEM_PROMPT}, {'role': 'user', 'content': user}]
        answers = []
        for run in range(runs):
            for s in range(samples):
                answer, t0, first, t1, usage = chat_stream(endpoint, model, messages, temperature, max_tokens,
                                                           api_key=api_key, seed=run * 1000 + s)
                score, checks = score_answer(t, answer)
                answers.append({'run': run, 'sample': s, 'score': round(score, 4), 'checks': checks,
                                'speed': measure(answer, t0, first, t1, usage, len(SYSTEM_PROMPT) + len(user)),
                                'answer': answer})
        mean = statistics.fmean(a['score'] for a in answers)
        out['tasks'].append({'id': t['id'], 'profession': t['profession'], 'kind': t['kind'], 'title': t['title'],
                             'critical': bool(t.get('critical')), 'mean_score': round(mean, 4), 'answers': answers})
        log(f"  {t['id']:<38} {mean:6.1%}  ({len(answers)} answers)")
    out['finished'] = datetime.now().isoformat(timespec='seconds')
    out['summary'] = summarize(out)
    return out


# ----------------------------------------------------------------------------------------------
# Statistics and decisions
# ----------------------------------------------------------------------------------------------

def bootstrap_ci(values, iterations=2000, level=0.95, seed=7):
    """Mean and a bootstrap confidence interval over the given values (tasks), reproducible."""
    if not values:
        return 0.0, 0.0, 0.0
    rng = random.Random(seed)
    n, means = len(values), []
    for _ in range(iterations):
        means.append(statistics.fmean(values[rng.randrange(n)] for _ in range(n)))
    means.sort()
    lo, hi = means[int((1 - level) / 2 * iterations)], means[int((1 + level) / 2 * iterations) - 1]
    return statistics.fmean(values), lo, hi


def summarize(result):
    speeds = [a['speed'] for t in result['tasks'] for a in t['answers']]
    mean, lo, hi = bootstrap_ci([t['mean_score'] for t in result['tasks']])
    by_prof = {}
    for t in result['tasks']:
        by_prof.setdefault(t['profession'], []).append(t['mean_score'])
    med = lambda k: round(statistics.median(s[k] for s in speeds if s[k] is not None), 2) if speeds else None
    return {'score': round(mean, 4), 'score_ci': [round(lo, 4), round(hi, 4)],
            'by_profession': {p: round(statistics.fmean(v), 4) for p, v in sorted(by_prof.items())},
            'ttft_s_median': med('ttft_s'), 'decode_tok_s_median': med('decode_tok_s'),
            'prefill_tok_s_median': med('prefill_tok_s'), 'words_s_median': med('words_s'),
            'tokens_estimated': any(s['tokens_estimated'] for s in speeds), 'answers': len(speeds)}


def check_pass_rates(task):
    rates = {}
    for a in task['answers']:
        for c in a['checks']:
            r = rates.setdefault(c['name'], {'critical': c['critical'], 'passed': 0, 'n': 0})
            r['passed'] += c['passed']
            r['n'] += 1
    return {k: {'critical': v['critical'], 'rate': v['passed'] / v['n']} for k, v in rates.items()}


def compare(current, candidate, tolerance=0.02, max_critical_drop=0.10, max_speed_drop=None):
    """Release rule: the update goes in only if, on these tasks, it is not worse beyond noise, not worse on
    average, and no critical check (a deadline, an amount, a safety advice) gets rarer by more than max_critical_drop."""
    cur = {t['id']: t for t in current['tasks']}
    cand = {t['id']: t for t in candidate['tasks']}
    common = sorted(set(cur) & set(cand))
    diffs = [cand[i]['mean_score'] - cur[i]['mean_score'] for i in common]
    mean, lo, hi = bootstrap_ci(diffs)
    reasons, critical_drops = [], []
    for i in common:
        a, b = check_pass_rates(cur[i]), check_pass_rates(cand[i])
        for name, r in a.items():
            if r['critical'] and name in b and r['rate'] - b[name]['rate'] > max_critical_drop:
                critical_drops.append({'task': i, 'check': name, 'before': round(r['rate'], 3), 'after': round(b[name]['rate'], 3)})
    if mean < 0:
        reasons.append(f'im Mittel schlechter ({mean:+.1%})')
    if lo < -tolerance:
        reasons.append(f'kann schlechter sein (untere Grenze {lo:+.1%}, erlaubt {-tolerance:+.1%})')
    for d in critical_drops:
        reasons.append(f'kritische Prüfung seltener bestanden: {d["task"]} · {d["check"]} ({d["before"]:.0%} → {d["after"]:.0%})')
    cs, ns = current['summary'], candidate['summary']
    speed_change = None
    if cs.get('decode_tok_s_median') and ns.get('decode_tok_s_median'):
        speed_change = ns['decode_tok_s_median'] / cs['decode_tok_s_median'] - 1
        if max_speed_drop is not None and speed_change < -max_speed_drop:
            reasons.append(f'langsamer ({speed_change:+.0%})')
    missing = sorted(set(cur) ^ set(cand))
    if missing:
        reasons.append(f'nicht dieselben Aufgaben: {", ".join(missing)}')
    by_task = [{'id': i, 'title': cur[i]['title'], 'profession': cur[i]['profession'],
                'before': cur[i]['mean_score'], 'after': cand[i]['mean_score'],
                'diff': round(cand[i]['mean_score'] - cur[i]['mean_score'], 4)} for i in common]
    return {'pruefstand': VERSION, 'decided': datetime.now().isoformat(timespec='seconds'),
            'release': not reasons, 'reasons': reasons,
            'rule': {'tolerance': tolerance, 'max_critical_drop': max_critical_drop, 'max_speed_drop': max_speed_drop},
            'current': {k: current[k] for k in ('label', 'model', 'runs', 'samples', 'endpoint_local')} | {'summary': cs},
            'candidate': {k: candidate[k] for k in ('label', 'model', 'runs', 'samples', 'endpoint_local')} | {'summary': ns},
            'diff': {'mean': round(mean, 4), 'ci': [round(lo, 4), round(hi, 4)]},
            'speed_change': None if speed_change is None else round(speed_change, 4),
            'critical_drops': critical_drops, 'tasks': by_task}


def pareto_modes(results, floor=0.10):
    """From several models measured on the same tasks: Gründlich = best score; Schnell = fastest whose score is
    within `floor` of the best; Ausgewogen = among those within `floor`, the best of score² × speed (normalised).
    Quality counts twice: for a law firm or a practice, a much faster model that gets more wrong is not balanced."""
    pts = [{'label': r['label'], 'score': r['summary']['score'], 'speed': r['summary']['decode_tok_s_median'] or 0.0,
            'ttft': r['summary']['ttft_s_median']} for r in results]
    frontier = [p for p in pts if not any(q['score'] >= p['score'] and q['speed'] >= p['speed'] and q != p and
                                          (q['score'] > p['score'] or q['speed'] > p['speed']) for q in pts)]
    best = max(pts, key=lambda p: p['score'])
    fast = max((p for p in pts if p['score'] >= best['score'] - floor), key=lambda p: p['speed'])
    smax, vmax = max(p['score'] for p in pts) or 1, max(p['speed'] for p in pts) or 1
    good_enough = [p for p in frontier if p['score'] >= best['score'] - floor] or [best]
    balanced = max(good_enough, key=lambda p: (p['score'] / smax) ** 2 * (p['speed'] / vmax))
    return {'gruendlich': best, 'schnell': fast, 'ausgewogen': balanced, 'frontier': frontier, 'all': pts}


# ----------------------------------------------------------------------------------------------
# Service-book entry (printable HTML, A5)
# ----------------------------------------------------------------------------------------------

def serviceheft_html(decision, client='', device='', entry_no='', concierge='', when=None, muster=False, fonts_dir=None):
    e = html.escape
    when = when or date.today()
    dec = lambda x, n=1: f'{x:.{n}f}'.replace('.', ',')          # German decimal comma
    pct = lambda x: f'{x * 100:.0f} %'
    sign = lambda x: f'{x * 100:+.0f} Punkte' if abs(x) >= 0.005 else '±0'
    cs, ns = decision['current']['summary'], decision['candidate']['summary']
    rows = ''.join(
        f'<tr><td>{e(PROFESSIONS.get(p, p))}</td><td>{pct(cs["by_profession"].get(p, 0))}</td>'
        f'<td>{pct(ns["by_profession"].get(p, 0))}</td><td>{sign(ns["by_profession"].get(p, 0) - cs["by_profession"].get(p, 0))}</td></tr>'
        for p in sorted(set(cs['by_profession']) | set(ns['by_profession'])))
    n_tasks = len(decision['tasks'])
    runs, samples = decision['candidate']['runs'], decision['candidate']['samples']
    verdict = ('<p class="ok">Freigegeben und eingespielt.</p>' if decision['release'] else
               '<p class="no">Nicht eingespielt. Ihre bisherige KI bleibt.</p><ul>' +
               ''.join(f'<li>{e(r)}</li>' for r in decision['reasons']) + '</ul>')
    local = decision['current'].get('endpoint_local') and decision['candidate'].get('endpoint_local')
    fonts = ''
    if fonts_dir:
        fonts = ''.join(f"@font-face{{font-family:'{f}';font-weight:{w};src:url('{fonts_dir}/{file}') format('woff2');}}"
                        for f, w, file in [('Inter', 400, 'inter-latin-400-normal.woff2'), ('Inter', 300, 'inter-latin-300-normal.woff2'),
                                           ('Unbounded', 300, 'unbounded-latin-300-normal.woff2')])
    speed = lambda s: (f"{dec(s['ttft_s_median'])} s bis zum ersten Wort · {s['words_s_median']:.0f} Wörter/s"
                       if s.get('ttft_s_median') is not None and s.get('words_s_median') is not None else '—')
    return f'''<!doctype html><html lang="de"><head><meta charset="utf-8"><title>Serviceheft · Eintrag {e(str(entry_no))}</title><style>
{fonts}
@page {{ size: A5; margin: 12mm; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; font: 300 10.5pt/1.45 Inter, system-ui, sans-serif; color: #1a1a24; background: #fff; }}
.sheet {{ position: relative; width: 148mm; min-height: 210mm; padding: 12mm; overflow: hidden; }}
h1 {{ font: 300 15pt/1.2 Unbounded, Inter, sans-serif; margin: 0 0 1mm; letter-spacing: -.01em; }}
.meta {{ color: #606075; font-size: 9pt; margin-bottom: 6mm; }}
.meta b {{ color: #1a1a24; font-weight: 400; }}
h2 {{ font: 400 9pt/1.2 Inter, sans-serif; text-transform: uppercase; letter-spacing: .12em; color: #606075; margin: 6mm 0 2mm; }}
table {{ width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }}
th, td {{ text-align: left; padding: 1.6mm 0; border-bottom: .3mm solid #e6e6f0; }}
th {{ font-weight: 400; color: #606075; font-size: 9pt; }}
td:not(:first-child), th:not(:first-child) {{ text-align: right; }}
tr.total td {{ font-weight: 400; border-bottom: .5mm solid #1a1a24; }}
.ok, .no {{ font: 300 12pt/1.3 Unbounded, Inter, sans-serif; margin: 5mm 0 1mm; }}
.ok {{ color: #3f7a12; }} .no {{ color: #a3283f; }}
ul {{ margin: 1mm 0 0; padding-left: 5mm; font-size: 9pt; }}
.small {{ font-size: 8.5pt; color: #606075; }}
.sign {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10mm; margin-top: 12mm; }}
.sign div {{ border-top: .3mm solid #1a1a24; padding-top: 1.5mm; font-size: 8.5pt; color: #606075; }}
.stamp {{ position: absolute; left: 34mm; bottom: 9mm; width: 30mm; height: 30mm; border: .6mm solid #4a69c9; border-radius: 50%;
  color: #4a69c9; display: flex; align-items: center; justify-content: center; text-align: center; font-size: 7.5pt; line-height: 1.25; transform: rotate(-12deg); opacity: .8; }}
.muster {{ position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; pointer-events: none;
  font: 300 64pt Unbounded, Inter, sans-serif; color: rgba(201, 66, 90, .14); transform: rotate(-28deg); letter-spacing: .1em; }}
</style></head><body><div class="sheet">
{'<div class="muster">MUSTER</div>' if muster else ''}
<h1>Serviceheft · Update-Prüfung</h1>
<p class="meta">Eintrag <b>{e(str(entry_no))}</b> · {when.strftime('%d.%m.%Y')} · Gerät <b>{e(device)}</b><br>{e(client)}</p>
<h2>Geprüft auf Ihren eigenen Aufgaben</h2>
<p class="small">{n_tasks} Aufgaben aus Ihrer Arbeit, jede {runs * samples}-mal beantwortet ({runs} Läufe × {samples} Antworten). Bewertet wird, ob Fakten, Fristen und Beträge stimmen und nichts erfunden wird.</p>
<table><tr><th>Bereich</th><th>bisher</th><th>neu</th><th>Änderung</th></tr>{rows}
<tr class="total"><td>Gesamt</td><td>{pct(cs['score'])}</td><td>{pct(ns['score'])}</td><td>{sign(ns['score'] - cs['score'])}</td></tr></table>
<p class="small">Unsicherheit der Änderung (95&nbsp;%): {'+' if decision['diff']['ci'][0] >= 0 else '−'}{dec(abs(decision['diff']['ci'][0]) * 100)} bis {'+' if decision['diff']['ci'][1] >= 0 else '−'}{dec(abs(decision['diff']['ci'][1]) * 100)} Punkte.</p>
<h2>Tempo</h2>
<table><tr><td>bisher</td><td>{speed(cs)}</td></tr><tr><td>neu</td><td>{speed(ns)}</td></tr></table>
<h2>Modell</h2>
<table><tr><td>bisher</td><td>{e(decision['current']['label'])}</td></tr><tr><td>neu</td><td>{e(decision['candidate']['label'])}</td></tr></table>
{verdict}
<p class="small">{'Gemessen im Koffer, ohne Internet. Keine Ihrer Daten hat Vita verlassen.' if local else 'Achtung: nicht auf diesem Gerät gemessen.'}</p>
<div class="stamp">Vita AI<br>Concierge<br>geprüft</div>
<div class="sign"><div>Concierge{(': ' + e(concierge)) if concierge else ''}</div><div>Kunde</div></div>
</div></body></html>'''


# ----------------------------------------------------------------------------------------------
# Command line
# ----------------------------------------------------------------------------------------------

def report_md(result):
    s = result['summary']
    lines = [f"# Prüfstand: {result['label']}", '',
             f"{len(result['tasks'])} Aufgaben × {result['runs']} Läufe × {result['samples']} Antworten · gestartet {result['started']}"
             + ('' if result['endpoint_local'] else ' · **Endpunkt nicht lokal**'), '',
             f"Gesamt: {s['score']:.1%} (95 %: {s['score_ci'][0]:.1%} bis {s['score_ci'][1]:.1%})",
             f"Tempo (Median): {s['ttft_s_median']} s bis zum ersten Wort, {s['words_s_median']} Wörter/s, "
             f"{s['decode_tok_s_median']} Token/s beim Schreiben, {s['prefill_tok_s_median']} Token/s beim Lesen"
             + (' (Token geschätzt)' if s['tokens_estimated'] else ''), '',
             '| Aufgabe | Bereich | Ergebnis |', '|---|---|---|']
    lines += [f"| {t['title']} | {PROFESSIONS[t['profession']]} | {t['mean_score']:.0%} |" for t in result['tasks']]
    return '\n'.join(lines) + '\n'


def main(argv=None):
    ap = argparse.ArgumentParser(prog='pruefstand', description='Vita Prüfstand: measure, decide, record.')
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run', help='run tasks against a model')
    r.add_argument('--endpoint', default='http://127.0.0.1:8080/v1')
    r.add_argument('--model', required=True)
    r.add_argument('--label')
    r.add_argument('--tasks', default=os.path.join(os.path.dirname(__file__), 'tasks'))
    r.add_argument('--only', help='comma-separated task ids')
    r.add_argument('--runs', type=int, default=5)
    r.add_argument('--samples', type=int, default=5)
    r.add_argument('--temperature', type=float, default=0.7)
    r.add_argument('--max-tokens', type=int, default=700)
    r.add_argument('--api-key', default=os.environ.get('PRUEFSTAND_API_KEY'))
    r.add_argument('--out', required=True)
    c = sub.add_parser('compare', help='decide whether a candidate may replace the current model')
    c.add_argument('current'); c.add_argument('candidate')
    c.add_argument('--tolerance', type=float, default=0.02)
    c.add_argument('--max-critical-drop', type=float, default=0.10)
    c.add_argument('--max-speed-drop', type=float)
    c.add_argument('--out', required=True)
    m = sub.add_parser('modes', help='pick Schnell / Gründlich / Ausgewogen from result files')
    m.add_argument('results', nargs='+'); m.add_argument('--floor', type=float, default=0.10)
    s = sub.add_parser('serviceheft', help='write the printable service-book entry for a decision')
    s.add_argument('decision'); s.add_argument('--client', default=''); s.add_argument('--device', default='')
    s.add_argument('--entry', default='1'); s.add_argument('--concierge', default=''); s.add_argument('--date')
    s.add_argument('--muster', action='store_true'); s.add_argument('--fonts-dir'); s.add_argument('--out', required=True)
    v = sub.add_parser('validate', help='check task files'); v.add_argument('tasks', nargs='?', default=os.path.join(os.path.dirname(__file__), 'tasks'))
    sub.add_parser('selftest', help='run the unit tests')
    a = ap.parse_args(argv)

    if a.cmd == 'validate':
        tasks = load_tasks(a.tasks)
        problems = validate_tasks(tasks)
        for p in problems:
            print('✗', p)
        print(f'{len(tasks)} tasks, {sum(len(t["checks"]) for t in tasks)} checks: ' + ('ok' if not problems else f'{len(problems)} problems'))
        return 1 if problems else 0
    if a.cmd == 'run':
        tasks = load_tasks(a.tasks)
        if a.only:
            keep = set(a.only.split(','))
            tasks = [t for t in tasks if t['id'] in keep]
        problems = validate_tasks(tasks)
        if problems:
            sys.exit('task problems:\n' + '\n'.join(problems))
        if not is_local(a.endpoint):
            print(f'! endpoint {a.endpoint} is not on this machine: client data must not leave the case', file=sys.stderr)
        print(f'{a.label or a.model}: {len(tasks)} tasks × {a.runs} runs × {a.samples} answers')
        res = run_tasks(a.endpoint, a.model, tasks, a.runs, a.samples, a.temperature, a.max_tokens, a.api_key, a.label)
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, 'w') as fh:
            json.dump(res, fh, ensure_ascii=False, indent=1)
        with open(os.path.splitext(a.out)[0] + '.md', 'w') as fh:
            fh.write(report_md(res))
        sm = res['summary']
        print(f"score {sm['score']:.1%} [{sm['score_ci'][0]:.1%}, {sm['score_ci'][1]:.1%}] · first word {sm['ttft_s_median']} s · {sm['words_s_median']} words/s → {a.out}")
        return 0
    if a.cmd == 'compare':
        cur, cand = (json.load(open(p)) for p in (a.current, a.candidate))
        d = compare(cur, cand, a.tolerance, a.max_critical_drop, a.max_speed_drop)
        with open(a.out, 'w') as fh:
            json.dump(d, fh, ensure_ascii=False, indent=1)
        print(('RELEASE' if d['release'] else 'HOLD') + f" · change {d['diff']['mean']:+.1%} [{d['diff']['ci'][0]:+.1%}, {d['diff']['ci'][1]:+.1%}]")
        for reason in d['reasons']:
            print('  -', reason)
        return 0 if d['release'] else 2
    if a.cmd == 'modes':
        res = [json.load(open(p)) for p in a.results]
        modes = pareto_modes(res, a.floor)
        for k, name in (('schnell', 'Schnell'), ('ausgewogen', 'Ausgewogen'), ('gruendlich', 'Gründlich')):
            p = modes[k]
            print(f"{name:<11} {p['label']:<28} score {p['score']:.1%} · {p['speed']} tok/s · first word {p['ttft']} s")
        return 0
    if a.cmd == 'serviceheft':
        d = json.load(open(a.decision))
        when = date.fromisoformat(a.date) if a.date else None
        with open(a.out, 'w') as fh:
            fh.write(serviceheft_html(d, a.client, a.device, a.entry, a.concierge, when, a.muster, a.fonts_dir))
        print('→', a.out)
        return 0
    if a.cmd == 'selftest':
        import unittest
        suite = unittest.defaultTestLoader.discover(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))
        return 0 if unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
