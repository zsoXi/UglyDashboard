# V6 — Handoff (stan na 2026-09-17, przed resetem PC)

Dokument przekazania roboczego stanu V6. Publiczny: brak sekretów, brak prywatnych promptów,
brak danych użytkownika. Ścieżki użytkownika podano jako `%USERPROFILE%` — nie kopiuj ich do repo.

## 1. Gdzie jest projekt

| Rola | Ścieżka | Gałąź | Uwaga |
| --- | --- | --- | --- |
| v5 (produkcja, działająca) | `D:\TESTY!\Dashboard\V2\OpenCode_Mission_Control_v4` | `fix/mission-control-v5-hardening-ui` @ `5685080` | instancja na porcie 8765 (PID może się zmienić) |
| V6 (praca) | `D:\TESTY!\Dashboard\V6\UglyDashboard` (git worktree) | `feat/mission-control-v6` @ `ac4d70f` | port testowy 8780, osobny katalog stanu |
| Dashboard porównawczy | `D:\TESTY!\Dashboard\opencode_dashboard.py` | — | port 8770; NIE modyfikować |
| Raport odniesienia | `D:\TESTY!\V3\little-better-dashboard` | — | nie był źródłem procesu na 8770 |

Repo: `https://github.com/zsoXi/UglyDashboard`
- PR v5: #1 (`fix/mission-control-v5-hardening-ui` → `main`), nadal otwarty, nie scalony.
- PR V6: #2 (draft) — baza `fix/mission-control-v5-hardening-ui`, head `feat/mission-control-v6`.

## 2. Stan wykonania (Etap A / B / C / D / E)

| Etap | Status | Dowód |
| --- | --- | --- |
| A — izolacja i baseline | IMPLEMENTED AND VERIFIED | worktree od `5685080`; baseline w V6: 144 testy / 0 błędów / 2 pominięcia / 0 `ResourceWarning`; `npm ci` 87 pakietów / 0 podatności; `npm run check` zielone; Playwright 27/27 |
| B — sekrety + uzgodnienie zużycia | IMPLEMENTED AND VERIFIED | `Store.rotate_secret`, CLI `--rotate-owner-token`, `scripts/check_secrets.py`, `tests/test_v6_secrets.py`; uzgodnienie OpenCode: błąd 174 609 418 tokenów usunięty; `docs/V6_RECONCILIATION.md` |
| C — przyrostowe pełne pokrycie | NOT COMPLETED (następny krok) | — |
| D — English/Polski + raport zużycia | NOT COMPLETED | — |
| E — MCP, produkcyjny build, migracja, benchmarki, odbiór | NOT COMPLETED | — |

CI dla `ac4d70f`: obie runs zielone (pull_request `35171630327`, push `35171621991`), 6/6 zadań,
w tym nowy krok „Secret leak guard” w zadaniu verify.

Aktualne liczby testów w V6: **149 testów Python** (0 błędów, 2 pominięcia środowiskowe:
symlinki, uprawnienia POSIX), **27/27 Playwright**, ruff czysty, build odtwarzalny.

## 3. Jak wznowić po resecie (kolejność)

```powershell
# 1. Worktree (jeśli istnieje — nic nie rób; jeśli zniknie, odtwórz z v5-repo):
git -C "D:\TESTY!\Dashboard\V2\OpenCode_Mission_Control_v4" worktree list
git -C "D:\TESTY!\Dashboard\V2\OpenCode_Mission_Control_v4" worktree add -b feat/mission-control-v6 "D:\TESTY!\Dashboard\V6\UglyDashboard" ac4d70f

# 2. Zależności frontendu w V6:
npm --prefix "D:\TESTY!\Dashboard\V6\UglyDashboard" ci

# 3. Testy Python (v5-venv 3.14; jeśli brak, utwórz nowe venv i tylko testuj — runtime jest stdlib):
& "D:\TESTY!\Dashboard\V2\OpenCode_Mission_Control_v4\.venv\Scripts\python.exe" -X utf8 `
  -c "import os; os.chdir(r'D:\TESTY!\Dashboard\V6\UglyDashboard')"
# zalecane: uruchamiaj skryptem (nie inline), z katalogu V6:
#   scripts\run_tests.py , scripts\check_secrets.py , scripts\reconcile_usage.py

# 4. Przeglądarka (produkcyjny build wg Etapu E):
npm run check ; npx playwright test
```

Uruchamianie instancji V6 do testów manualnych: **port 8780 + osobny katalog stanu**, np.
`opencode_dashboard.py --port 8780 --state-dir <katalog tymczasowy> --no-open`. Nie dotykać 8765
(produkcyjna v5) ani 8770 (dashboard porównawczy). Nie kończyć cudzych procesów.

## 4. Co dokładnie pozostało

### Etap C — przyrostowe pełne pokrycie (priorytet)
1. Rozdzielić warstwy: agregaty (pełne), szczegóły (ograniczane), checkpointy (własne, w `observer.sqlite`).
2. OpenCode: dokończyć niezależność agregatów od limitów szczegółów — zrobione dla części
   (`MAX_OC_PARTS_PER_SESSION` nie obcina już sum); dodać checkpointy per sesja i kontynuację po budżecie.
3. Codex: discovery pełnego zbioru przyrostowo (`~/.codex` + `~/.codex/browser`, dedup po tożsamości
   sesji i treści pliku); limit `codex_file_limit` nie może powodować, że pliki znikają na zawsze.
4. UI/API: pola kompletności (`usage_aggregates_complete`, `detail_history_truncated`,
   `catching_up`, `aggregate_truncated_sessions`, `discovered/processed`), wspólne dla UI, eksportu i MCP.
5. Testy: regresje z macierzy w specyfikacji V6 (restart z checkpointu, powtórny odczyt bez wzrostu sum,
   rotacja/przepisanie pliku, reset licznika, forki, zmiana modelu w sesji).

### Etap D — English / Polski + raport zużycia
- Pełne i18n (klucze stabilne, walidacja zgodności EN/PL, placeholdery, `Intl`), przełącznik w UI,
  domyślnie English, zachowanie preferencji; `lang` w `<html>`; testy Playwright w obu językach.
- Widok „Zużycie”: Today / 7 / 30 / całość / zakres, OpenCode / Codex / Combined z jasnym zakresem,
  input/output/reasoning/cache read/write, koszt źródłowy vs szacowany vs ręczny, heatmapa, eksport.

### Etap E — MCP, build, migracja, odbiór
- MCP: te same uzgodnione dane z kompletnością i pochodzeniem; paginacja; brak uprawnień do
  konfiguracji/sekretów/abort/shutdown z odczytowego MCP; testy stdio i ścieżek Windows.
- Produkcyjny frontend: serwer domyślnie serwuje `dist/` z manifestem; tryb developerski jawnie źródła;
  Playwright na artefakcie produkcyjnym; hash serwowanego JS/CSS zgodny z manifestem.
- Migracja v5→V6 `observer.sqlite`: transakcyjna, idempotentna, zachowuje ustawienia/oceny;
  oznacza stare agregaty jako wymagające kontrolowanego przeliczenia.
- Benchmarki: 100k i 1M zdarzeń z generatorem znającym oczekiwane sumy; pełne pokrycie
  1000/1000 sesji przyrostowo; warm analytics; latencja overview podczas importu; restart.
- CI: dodać kroki i18n oraz Playwright na dist; zadbać o ostrzeżenia Node 20 w akcjach.
- PR #2 doprowadzić do stanu gotowego (bez auto-merge); dokumentacja: README/README_PL/CHANGELOG/
  SECURITY/TEST_REPORT + zrzuty EN/PL (syntetyczne dane).

## 5. Dowody i artefakty

- `docs/V6_STATUS.md` — status etapów i dowody.
- `docs/V6_RECONCILIATION.md` — uzgodnienie OpenCode/Codex z liczbami i wnioskami.
- `scripts/check_secrets.py` — guard wycieków (skan repo + `artifacts/`, `test-results/`,
  `playwright-report/`; wypisuje tylko ścieżkę/linię/etykietę/długość; exit 1 przy trafieniach).
- `scripts/reconcile_usage.py`, `scripts/reconcile_codex.py` — reprodukcja uzgodnienia
  (kopia SQLite przez backup API z WAL; sesje hashowane; brak tytułów/promptów/ścieżek).
- `tests/test_v6_secrets.py` — testy rotacji i guarda.
- Tymczasowe JSON-y uzgodnienia w `%USERPROFILE%\AppData\Local\Temp\opencode\` — nie są w repo,
  można je wygenerować ponownie skryptami.

## 6. Rzeczy otwarte / wymagające decyzji użytkownika

- **Rotacja produkcyjnego tokenu właściciela v5 NIE została wykonana** (świadomie — wymaga zgody
  na wdrożenie). Procedura: zatrzymać instancję, `python -X utf8 opencode_dashboard.py
  --rotate-owner-token --state-dir <stan>`, uruchomić ponownie z `--open`. Zachowuje bazę,
  konfigurację, `mcp.token` i `pairing.key`.
- **Rzeczywiste połączenie klientów MCP (ChatGPT/Codex) NIE zostało zweryfikowane** — są tylko
  testy lokalne protokołu; potrzebne jest sprawdzenie na realnym kliencie.
- Historyczne tokeny, które pojawiły się w logach terminala podczas wcześniejszych prac, są już
  nieaktywne (sesje zakończone), ale rotacja produkcyjna i tak pozostaje zalecana przy okazji
  najbliższego restartu v5.

## 7. Stan instancji po resecie

Reset komputera zatrzyma działającą v5 na 8765. Po resecie uruchom ją ponownie z katalogu v5:
`START_MISSION_CONTROL.cmd` albo `python -X utf8 opencode_dashboard.py --open`
(zwróć uwagę: `--open` otwiera przeglądarkę z fragmentem `#access` — nie kopiuj tego adresu do
czatu ani logów). Dashboard porównawczy na 8770 uruchamiasz ręcznie, jeśli będzie potrzebny.
