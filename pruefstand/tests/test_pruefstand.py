"""Tests for the Vita Prüfstand. Run: python3 pruefstand.py selftest  (or python3 -m unittest discover -s tests)."""
import json, os, sys, tempfile, threading, time, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import pruefstand as ps  # noqa: E402

TASKS = ps.load_tasks(os.path.join(os.path.dirname(HERE), 'tasks'))
BY_ID = {t['id']: t for t in TASKS}


class FakeModel(BaseHTTPRequestHandler):
    """A stand-in OpenAI-compatible server. Model "good" answers with each task's reference answer,
    "bad" with its counterexample, "mixed" alternates. It streams word by word, like a real server."""
    delay = 0.002

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        prompt = body['messages'][-1]['content']
        task = next(t for t in TASKS if t['document'].strip()[:80] in prompt)
        model, seed = body['model'], body.get('seed', 0)
        good = model == 'good' or (model == 'mixed' and seed % 2 == 0)
        answer = task['reference'] if good else task['counterexample']
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        time.sleep(self.delay * 5)                       # "reading the prompt"
        words = answer.split(' ')
        for i, w in enumerate(words):
            chunk = {'choices': [{'delta': {'content': w + (' ' if i < len(words) - 1 else '')}}]}
            self.wfile.write(f'data: {json.dumps(chunk)}\n\n'.encode())
            time.sleep(self.delay)
        usage = {'prompt_tokens': len(prompt) // 4, 'completion_tokens': len(words) + 3}
        self.wfile.write(f'data: {json.dumps({"choices": [], "usage": usage})}\n\n'.encode())
        self.wfile.write(b'data: [DONE]\n\n')


class Checks(unittest.TestCase):
    def test_german_numbers(self):
        self.assertEqual(ps.parse_numbers('1.234,56 € und 3.299 € und 1 250,00 und 2 % und 3,40'), [1234.56, 3299.0, 1250.0, 2.0, 3.4])

    def test_dates_in_many_spellings(self):
        for text in ('Fristende: 26.05.2027', 'bis 26. Mai 2027', 'bis zum 26.5.27', '2027-05-26'):
            self.assertTrue(ps.run_check({'type': 'date', 'value': '2027-05-26'}, text), text)
        self.assertFalse(ps.run_check({'type': 'date', 'value': '2027-05-26'}, 'bis 24.05.2027'))

    def test_order(self):
        c = {'type': 'order', 'items': [['A1'], ['B2'], ['C3']]}
        self.assertTrue(ps.run_check(c, 'A1 dann B2 dann C3'))
        self.assertFalse(ps.run_check(c, 'B2 dann A1 dann C3'))
        self.assertFalse(ps.run_check(c, 'A1 dann C3'))

    def test_every_task_is_sharp(self):
        """Reference answers pass every check; counterexamples fail at least one critical check."""
        self.assertEqual(ps.validate_tasks(TASKS), [])
        self.assertEqual(len(TASKS), 15)
        self.assertEqual({t['profession'] for t in TASKS}, {'kanzlei', 'praxis', 'steuer'})

    def test_correct_answers_in_other_words_still_pass(self):
        """False alarms found while writing v0.1: correct answers that early patterns would have failed."""
        cases = {
            'praxis-04-labor': 'Kreatinin im Normbereich, Kalium 5,9 mmol/l erhöht, HbA1c 8,1 % erhöht. Natrium, TSH und LDL sind normal.',
            'steuer-01-bescheid': 'Einkommensteuer 14.236,00 €. Es ist nichts nachzuzahlen: Erstattung von 876,00 €. Bescheid vom 14.06.2027. Arbeitszimmer nur mit der Pauschale von 1.260 €.',
            'praxis-05-patienteninfo': 'Lassen Sie ASS ab sofort weg, also ASS nicht mehr einnehmen. Apixaban morgens und abends. Termin 14.05.2027 um 9 Uhr. Bei Blut im Stuhl sofort melden.',
            'kanzlei-05-mandantenbrief': 'Sie bekommen 1.200 €, aber nicht die volle Kaution, weil 600 € für das Parkett einbehalten werden. Berufung wäre bis 9. Juli 2027 möglich. Wir raten Ihnen von einer Berufung ab.',
            'kanzlei-01-mietvertrag': 'Beginn 1. März 2027. Miete 1.150 €, Betriebskosten 210 €. Jährlich plus 2 %. Kündigung mit drei Monaten Frist. Kleinreparaturen bis 100 €, höchstens 400 € im Jahr. Untervermietung ist ausgeschlossen. Eine Kaution regelt der Vertrag nicht (§ 15 betrifft nur die Schriftform).',
            'steuer-02-einspruchsfrist': 'Bekanntgabe 11.06.2027, Monatsende fällt auf einen Sonntag. **Fristende:** Montag, 12. Juli 2027',
        }
        for tid, answer in cases.items():
            _, res = ps.score_answer(BY_ID[tid], answer)
            failed = [r['name'] for r in res if r['critical'] and not r['passed']]
            self.assertEqual(failed, [], f'{tid}: {failed}')

    def test_safety_mistakes_are_caught(self):
        cases = {
            'praxis-03-triage': 'Einordnung: diese Woche. Bitte vereinbaren Sie einen Termin.',
            'kanzlei-04-urteil': 'Landgericht Potsdam, 4 O 118/26, 18.03.2027: Klage abgewiesen, aber der Beklagte trägt die Kosten.',
            'praxis-01-arztbrief': 'Vorhofflimmern. Neu: Apixaban 5 mg 1-0-1 und Rivaroxaban. ASS abgesetzt. Kontrolle in 4 Wochen.',
        }
        for tid, answer in cases.items():
            _, res = ps.score_answer(BY_ID[tid], answer)
            self.assertTrue(any(r['critical'] and not r['passed'] for r in res), tid)


class Statistics(unittest.TestCase):
    def test_bootstrap_is_reproducible_and_brackets_the_mean(self):
        vals = [0.9, 0.8, 1.0, 0.7, 0.95]
        a, b = ps.bootstrap_ci(vals), ps.bootstrap_ci(vals)
        self.assertEqual(a, b)
        self.assertLessEqual(a[1], a[0])
        self.assertLessEqual(a[0], a[2])

    def _result(self, label, scores, critical_rate=1.0, speed=30.0):
        tasks = []
        for i, s in enumerate(scores):
            answers = [{'score': s, 'checks': [{'name': 'Frist', 'critical': True, 'passed': j < critical_rate * 10}],
                        'speed': {'ttft_s': 0.5, 'decode_tok_s': speed, 'prefill_tok_s': 400.0, 'words_s': speed / 1.6, 'tokens_estimated': False}}
                       for j in range(10)]
            tasks.append({'id': f't{i}', 'profession': 'kanzlei', 'kind': 'frist', 'title': f'Aufgabe {i}', 'critical': True,
                          'mean_score': s, 'answers': answers})
        r = {'label': label, 'model': label, 'runs': 5, 'samples': 2, 'endpoint_local': True, 'tasks': tasks}
        r['summary'] = ps.summarize(r)
        return r

    def test_release_when_better(self):
        d = ps.compare(self._result('alt', [0.80, 0.85, 0.90, 0.70]), self._result('neu', [0.85, 0.90, 0.92, 0.80]))
        self.assertTrue(d['release'], d['reasons'])

    def test_hold_when_worse(self):
        d = ps.compare(self._result('alt', [0.85, 0.90, 0.92, 0.80]), self._result('neu', [0.80, 0.85, 0.90, 0.70]))
        self.assertFalse(d['release'])

    def test_hold_when_a_critical_check_gets_rarer_even_if_average_rises(self):
        d = ps.compare(self._result('alt', [0.80, 0.80, 0.80, 0.80], critical_rate=1.0),
                       self._result('neu', [0.90, 0.90, 0.90, 0.90], critical_rate=0.7))
        self.assertFalse(d['release'])
        self.assertTrue(any('kritische Prüfung' in r for r in d['reasons']))

    def test_modes(self):
        fast = self._result('klein-q4', [0.70, 0.75, 0.72, 0.71], speed=80)
        smart = self._result('gross-q8', [0.92, 0.95, 0.90, 0.93], speed=12)
        mid = self._result('mittel-q4', [0.86, 0.90, 0.85, 0.88], speed=35)
        m = ps.pareto_modes([fast, smart, mid])
        self.assertEqual(m['gruendlich']['label'], 'gross-q8')
        self.assertEqual(m['schnell']['label'], 'mittel-q4')      # klein-q4 is fast but more than 10 points worse
        self.assertEqual(m['ausgewogen']['label'], 'mittel-q4')


class EndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), FakeModel)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.endpoint = f'http://127.0.0.1:{cls.server.server_address[1]}/v1'
        cls.tasks = [BY_ID['kanzlei-02-zahlungsfrist'], BY_ID['praxis-03-triage'], BY_ID['steuer-02-einspruchsfrist']]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def run_model(self, model):
        return ps.run_tasks(self.endpoint, model, self.tasks, runs=2, samples=2, log=lambda *a: None)

    def test_run_compare_and_service_book(self):
        good, bad, mixed = self.run_model('good'), self.run_model('bad'), self.run_model('mixed')
        self.assertTrue(good['endpoint_local'])
        self.assertEqual(good['summary']['score'], 1.0)
        self.assertLess(bad['summary']['score'], 0.8)
        self.assertAlmostEqual(mixed['summary']['score'], (good['summary']['score'] + bad['summary']['score']) / 2, places=2)
        s = good['summary']
        self.assertGreater(s['ttft_s_median'], 0)
        self.assertGreater(s['decode_tok_s_median'], 0)
        self.assertFalse(s['tokens_estimated'])
        self.assertEqual(s['answers'], 12)

        hold = ps.compare(good, bad)
        self.assertFalse(hold['release'])
        release = ps.compare(bad, good)
        self.assertTrue(release['release'], release['reasons'])

        page = ps.serviceheft_html(release, client='Kanzlei Muster', device='VC-0001', entry_no=7, muster=True)
        self.assertIn('Freigegeben und eingespielt', page)
        self.assertIn('MUSTER', page)
        self.assertIn('Keine Ihrer Daten hat Vita verlassen', page)
        page = ps.serviceheft_html(hold, client='Kanzlei Muster', device='VC-0001', entry_no=8)
        self.assertIn('Nicht eingespielt', page)

    def test_cli_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            only = ','.join(t['id'] for t in self.tasks)
            for model in ('bad', 'good'):
                rc = ps.main(['run', '--endpoint', self.endpoint, '--model', model, '--only', only, '--runs', '1', '--samples', '2',
                              '--out', f'{d}/{model}.json'])
                self.assertEqual(rc, 0)
                self.assertTrue(os.path.exists(f'{d}/{model}.md'))
            self.assertEqual(ps.main(['compare', f'{d}/bad.json', f'{d}/good.json', '--out', f'{d}/decision.json']), 0)
            self.assertEqual(ps.main(['serviceheft', f'{d}/decision.json', '--client', 'Kanzlei Muster', '--out', f'{d}/eintrag.html']), 0)
            self.assertIn('Serviceheft', open(f'{d}/eintrag.html').read())


if __name__ == '__main__':
    unittest.main()
