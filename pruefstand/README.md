# Vita Prüfstand

Nov 13, 2026 · Charles Finney +1 (332) 249-3276

The test bench behind two promises of Vita AI Concierge:

1. **Your AI only gets better, never quietly worse.** Before every update, the new model and the current one answer the client's own tasks inside the case. The update is installed only if it does no worse on average and slips on no critical check (a deadline, an amount, an emergency warning). The result is printed into the service book and signed.
2. **An open test for German professional work.** As far as we know, there is no open benchmark of local models on German legal, medical and tax tasks. This is version 0.1 of one: tasks, checks, code and (from the first series on) results, all in the open.

Status: v0.1, Nov 13, 2026. 15 tasks, 86 checks, 13 tests passing. No model results yet: the first published results will be measured on Vita's own hardware, after a practitioner from each field has reviewed the tasks.

## What it measures

| | How |
|---|---|
| Correctness | Each task carries its own checks: facts, deadlines, amounts, diagnoses, order, length, and things that must **not** appear (an invented deposit, a second anticoagulant, the wrong category). An answer's score is the share of checks it passes. |
| Variance | Every task is answered `runs × samples` times (default 5 × 5 = 25), because answers vary. We report the mean with a 95 % bootstrap interval over tasks. |
| Speed | From the streamed answer: time to first token (the prompt being read), tokens per second while writing (decode), prompt tokens per second (prefill), and words per second, the figure the website quotes. |
| Privacy | The endpoint must be on the same machine; the result records whether it was. A service-book entry measured elsewhere says so. |

## Every task is tested before it tests a model

Each task file has a correct `reference` answer and a typical wrong `counterexample`. `validate` fails unless the reference passes **every** check and the counterexample fails **at least one critical** check. The test suite adds correct answers in other words (false alarms we found while writing v0.1, such as "ASS" matching inside "lassen") and safety mistakes that must be caught.

## The release rule

`compare current.json candidate.json` releases the candidate only if all of these hold, on the same tasks:

1. The mean change is not negative.
2. The lower end of the 95 % interval is above −2 points (`--tolerance`).
3. No critical check is passed less often by more than 10 points (`--max-critical-drop`), even if the average rises.
4. Optionally, decode speed does not drop by more than `--max-speed-drop`.

Otherwise the current model stays, and the service book says why.

## Three settings, chosen by measurement

`modes` takes several result files (models or compressions measured on the same tasks):

- **Gründlich** (thorough): the best score.
- **Schnell** (fast): the fastest model within 10 points of the best (`--floor`).
- **Ausgewogen** (balanced): among those within 10 points, the best of score² × speed. Quality counts twice: for a law firm or a practice, a much faster model that gets more wrong is not balanced.

## Use

Python 3.11+, standard library only. Any OpenAI-compatible server works: llama.cpp `llama-server`, Ollama, vLLM, LM Studio.

```
python3 pruefstand.py validate
python3 pruefstand.py run --endpoint http://127.0.0.1:8080/v1 --model current --out results/current.json
python3 pruefstand.py run --endpoint http://127.0.0.1:8080/v1 --model candidate --out results/candidate.json
python3 pruefstand.py compare results/current.json results/candidate.json --out results/decision.json
python3 pruefstand.py serviceheft results/decision.json --client "Kanzlei …" --device VC-0001 --entry 7 --concierge "…" --out eintrag.html
python3 pruefstand.py modes results/*.json
python3 pruefstand.py selftest
```

`run` writes a JSON file with every answer and a short Markdown report next to it. `serviceheft` writes an A5 page in German, ready to print; `--muster` stamps it as a sample.

## Task format

One TOML file per task in `tasks/`: `id`, `profession` (`kanzlei`, `praxis`, `steuer`), `kind`, `title`, `instruction`, `document` (invented, never real client data), `reference`, `counterexample`, and `[[checks]]` of type `contains`, `absent`, `number` (reads German formats: 1.234,56), `date` (accepts 26.05.2027, 26. Mai 2027, 2027-05-26), `order`, `max_words`. Mark the checks that must never get worse with `critical = true`.

A client's own test set uses the same format and never leaves the case.

## v0.1 tasks

| Kanzlei | Arztpraxis | Steuerberatung |
|---|---|---|
| Lease in eight points (no invented deposit) | Discharge letter: diagnoses, medication changes, no invented anticoagulant | Tax assessment: refund, not back payment |
| Payment deadline counted from receipt, not from the letter's date | Medication plan; discontinued drug flagged | Objection deadline that ends on a Sunday |
| Incoming mail: recognise a court summons with personal attendance ordered | Patient message: chest pain means 112, not an appointment | Receipts summed by category |
| Judgment: who won, who pays | Lab report: only the values outside the range | Invoice with 19 % and 7 % VAT |
| Client letter in plain language, ≤ 150 words | Patient reminder in plain language, ≤ 120 words | Deadlines in the right order |

## Next

1. Review of every task by a practising lawyer, doctor and tax adviser; v0.2 with 50 tasks, including tasks that need legal knowledge, not only reading.
2. First measured results on Vita's hardware: several open models and compressions, published with the method, including what does badly.
3. A guided session for setting up a client's own 20 tasks at installation.
4. Licence for publishing the code and tasks: to be decided (suggestion: Apache 2.0 for the code, CC BY 4.0 for the tasks).
