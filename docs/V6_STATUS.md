# V6 — Status prac

Dokument roboczy odbioru V6. Bez sekretów, bez prywatnych promptów i bez
lokalnych danych użytkownika. Aktualizowany po każdym etapie.

- Wersja docelowa: **6.0.0**
- Gałąź: `feat/mission-control-v6`
- Baza: `fix/mission-control-v5-hardening-ui` @ `5685080` (PR #1 wciąż otwarty)
- Worktree: `V6/UglyDashboard` (izolowany od działającej v5 na porcie 8765)
- Port testowy V6: 8780, osobny katalog stanu

## Etap A — stan bazowy i izolacja

Stan: `IMPLEMENTED AND VERIFIED`.

- Worktree V6 utworzony z commita `5685080`; `git worktree list` pokazuje
  v5 i V6 jako osobne katalogi robocze.
- Jedna rejestracja worktree dla v5 i jedna dla V6; brak zmian w v5.
- Baseline zmierzony wewnątrz V6 (nie przepisany z raportów v5):
  - `scripts/run_tests.py` → 144 testy, 0 błędów, 2 pominięcia
    środowiskowe, 0 `ResourceWarning`, 33,2 s (Python 3.14.3, Windows).
  - `npm ci` → 87 pakietów, 0 podatności.
  - `npm run check` → lint, strict typecheck, format, build (reproducible).
  - `npx playwright test` → 27/27 (desktop + mobile).
- Instancje 8765 i 8770 nie były zatrzymywane ani modyfikowane.

## Etap B — sekrety i uzgodnienie liczników

Stan: `IMPLEMENTED AND VERIFIED` (sekrety oraz uzgodnienie liczb
OpenCode; zakres Codexa udokumentowany jako różnica zbiorów danych).

Wykonane:

- `Store.rotate_secret(name)` — atomowa rotacja pojedynczego poświadczenia
  (`os.replace` nowego pliku tymczasowego; brak kopii starej wartości).
  Zachowuje `observer.sqlite`, `config.json`, `mcp.token` i `pairing.key`.
- CLI `--rotate-owner-token` — rotuje wyłącznie `owner.token` w katalogu
  stanu, nie uruchamia serwera i nie wypisuje wartości tokenu. Rotacja
  unieważnia stary token po restarcie działającej instancji.
- `scripts/check_secrets.py` — strażnik wycieków: skanuje pliki repo oraz
  lokalne katalogi dowodowe (`artifacts/`, `test-results/`,
  `playwright-report/`), nie wypisuje wartości (tylko ścieżkę, linię,
  etykietę i długość), kończy się kodem 1 przy trafieniu. Wyklucza
  świadome pliki poświadczeń (`.fixture-info.json`, `owner.token`,
  `mcp.token`, `pairing.key`) i odrzuca fałszywe trafienia (ciągi jednego
  znaku, wartości bez liter i cyfr).
- `tests/test_v6_secrets.py` — testy rotacji (tylko `owner.token` się
  zmienia; brak pliku `.bak`; walidacja nazwy) i strażnika (wykrycie
  wzorca, brak wycieku wartości, czysty katalog = 0).

Dowody (V6 worktree, Python 3.14.3, Windows):

- `python -m ruff check .` → `All checks passed!`
- `python -X utf8 scripts/check_secrets.py` →
  `OK: no secret patterns in 71 scanned file(s).`
- `python -X utf8 scripts/run_tests.py` → 149 testów, 0 błędów,
  2 pominięcia środowiskowe, 0 `ResourceWarning`, 33,5 s.
- CI verify job zawiera krok strażnika sekretów.

Blokady i uwagi:

- Przyczyna wcześniejszego wycieku leżała w narzędziach diagnostycznych
  (log polecenia, tymczasowy probe i zrzuty ekranu), nie w produkcyjnej
  ścieżce wypisywania. Ścieżka produktu nie loguje tokenu.
- Rotacja tokenu działającej v5 (port 8765) **nie została wykonana** —
  wymaga osobnej zgody na wdrożenie. Procedura: zatrzymać instancję,
  `python -X utf8 opencode_dashboard.py --rotate-owner-token --state-dir <stan>`,
  uruchomić ponownie z `--open`.
- Uzgodnienie liczb OpenCode/Codex: `IMPLEMENTED AND VERIFIED` —
  szczegóły w `docs/V6_RECONCILIATION.md`.

### Uzgodnienie zużycia (OpenCode / Codex)

OpenCode (ta sama kopia bazy, SQLite backup API z WAL):

- Przyczyna różnicy to limit szczegółów `MAX_OC_PARTS_PER_SESSION = 4000`:
  suma zużycia była liczona wyłącznie z najnowszego okna części, więc
  starsze zdarzenia `step-finish` ginęły. Dokładnie 2 sesje z >4000 części
  odpowiadały za całą różnicę.
- Przed poprawką: adapter `1 357 185 076` vs pełna suma `1 531 794 494`
  → różnica `174 609 418` (11,4%); emulacja limitu odtwarzała adapter co
  do tokenu (różnica 0,0).
- Po poprawce (161 sesji): adapter == suma pełna == suma z wiadomości
  == `1 559 229 849` (różnica 0,0). Limit nadal ogranicza wyłącznie
  historię szczegółów (`parts_loaded 63 270`, `truncated_sessions 2`).
- Nowe pole pokrycia `aggregate_truncated_sessions`; regresja
  `ReaderBoundsTests` zaktualizowana do kontraktu „szczegóły ograniczone,
  sumy kompletne”.

Codex:

- Porównanie `45,4 mld` (okno 400 plików) z `9,58 mld` (syntetyzowany
  ledger routera w panelu porównawczym) dotyczy różnych zbiorów danych i
  nie jest porównaniem sum plików.
- Pełny lokalny zbiór: `255 602 691 857` tokenów, 2184 pliki, 2182
  unikalne sesje logiczne; 0 duplikatów treści; 507 resetów licznika.
- Wniosek dla V6: discovery i przetwarzanie Codexa muszą dojść do pełnego
  pokrycia przyrostowo, z deduplikacją po tożsamości sesji i kontrolą
  nakładających się korzeni (`~/.codex`, `~/.codex/browser`).

## Etap C — przyrostowe pełne pokrycie (OpenCode) — IMPLEMENTED AND VERIFIED

Wdrożone:

- trwała tabela `usage_checkpoint` w `observer.sqlite`
  (`Store.checkpoints` / `put_checkpoints` / `delete_checkpoint`),
- `mission_control/incremental.py`: `aggregate_session` (keyset ASC po
  `(time_created, id)`, kursor i suma zatwierdzane razem, wykrywanie
  dopisania i przepisania źródła) oraz `aggregate_source` (rotacja
  `next_index`, aby jedna ogromna sesja nie blokowała pozostałych),
- `Engine._aggregate_db_source` wywoływany w każdym `_poll` z budżetem
  `AGGREGATE_BUDGET_SECONDS = 5,0`; sesje bez szczegółów pozostają
  opublikowane jako metadane, a kompletność liczona jest względem
  `metadata_sessions`, nie względem okna szczegółów.

Dowody (syntetyczne zbiory; sumy oczekiwane z arytmetyki generatora, nie
z ponownego wywołania readera):

| Zbiór | Sesje uwzględnione | Suma zgodna ze wzorcem | Pełne pokrycie | Cykle | Restart |
| --- | --- | --- | --- | --- | --- |
| 100 tys. zdarzeń | 1000/1000 | 12 347 213 = 12 347 213 | 9,5 s | 1 | identyczna suma |
| 1 mln zdarzeń | 1000/1000 | 126 001 216 = 126 001 216 | 103,6 s | 6 | identyczna suma |

Restart w połowie importu: pierwszy cykl częściowy (~106–114 mln),
wznowienie kończy import dokładnie na 126 001 216 — bez utraty i bez
podwójnego doliczenia.

Responsywność podczas importu: overview ~20 ms, analytics ciepła ~1 ms,
zimna 0,02–0,06 s. Pamięć: tracemalloc szczyt 90 MB (100 tys.) i 270 MB
(1 mln); pomiar RSS niedostępny na tym hoście (metoda raportowana jako
null).

Co pozostaje: przyrostowe discovery/dedup Codexa do pełnego pokrycia
(oraz pola kompletności w API/UI/MCP), następnie Etap D (pełne EN/PL) i
Etap E (MCP, build produkcyjny, migracja, odbiór).
