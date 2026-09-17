# V6 — Handoff (stan końcowy, 2026-09-17, po E.4)

Dokument przekazania stanu V6. Publiczny: brak sekretów, brak
prywatnych promptów, brak danych użytkownika. Ścieżki użytkownika podano
jako `%USERPROFILE%` — nie kopiuj ich do repo.

## 1. Gdzie jest projekt

| Rola | Ścieżka | Gałąź / stan | Uwaga |
| --- | --- | --- | --- |
| v5 (produkcja, działająca) | `<ścieżka do checkoutu v5>` | `fix/mission-control-v5-hardening-ui` @ `5685080` | instancja na porcie 8765 (PID może się zmienić) |
| V6 (ukończone E.4) | `<ścieżka do worktree V6>` (git worktree) | `feat/mission-control-v6` @ commit E.4 | port testowy 8780, osobny katalog stanu |
| Dashboard porównawczy | `<ścieżka do dashboardu porównawczego>` | — | port 8770; NIE modyfikować |
| Raport odniesienia | `<ścieżka do raportu odniesienia>` | — | nie był źródłem procesu na 8770 |

Repo: `https://github.com/zsoXi/UglyDashboard`

- PR v5: #1 (`fix/mission-control-v5-hardening-ui` → `main`) — otwarty.
- PR V6: #2 (draft) — baza `fix/mission-control-v5-hardening-ui`, head
  `feat/mission-control-v6`.

## 2. Stan wykonania

| Etap | Status | Dowód |
| --- | --- | --- |
| A–C — izolacja, sekrety, przyrostowe pokrycie | IMPLEMENTED AND VERIFIED | commity `ac4d70f`, `5fe314a`, `b4941dd`, `b105ecf`; `docs/V6_RECONCILIATION.md` |
| C.1 — kontrakt kompletności | IMPLEMENTED AND VERIFIED | `c7e8bca`; `tests/test_v6_coverage.py` |
| D.1 — English / Polski | IMPLEMENTED AND VERIFIED | `8459551`; 454 klucze EN = 454 PL |
| D.2 — raport zużycia | IMPLEMENTED AND VERIFIED | `fd0088a`; `tests/browser/usage.spec.mjs` |
| E.1 — produkcyjny `dist` | IMPLEMENTED AND VERIFIED | `fbdb4a9`; `tests/test_v6_dist.py` |
| E.2 — migracja stanu | IMPLEMENTED AND VERIFIED | `d775849`; `tests/test_v6_migration.py`; `docs/V6_MIGRATION.md` |
| E.3 — MCP i bezpieczeństwo | IMPLEMENTED AND VERIFIED | `eaefb75`; `tests/test_v6_mcp.py` |
| E.4 — odbiór końcowy | IMPLEMENTED AND VERIFIED | commit końcowy; `TEST_REPORT.json`, `docs/V6_COVERAGE.md`, `docs/V6_BENCHMARKS.md` |

Stan bieżący (zweryfikowany na końcowym stanie):

- HEAD `feat/mission-control-v6` wypchnięty; drzewo czyste.
- `python -X utf8 scripts/run_tests.py` → 189 testów, 0 błędów,
  2 pominięcia środowiskowe, 0 `ResourceWarning`.
- `--self-test` → 10/10; `ruff` czysty.
- `npm run check` zielony (lint, strict typecheck, prettier,
  `check:i18n` 454 = 454, build odtwarzalny).
- `npx playwright test` → 38/38 (desktop + mobile, produkcyjny `dist`).
- `python -X utf8 scripts/check_secrets.py` → czysto.

## 3. Jak wznowić po resecie (kolejność)

```powershell
# 1. Worktree (jeśli istnieje — nic nie rób; jeśli zniknie, odtwórz):
git -C "<ścieżka do checkoutu v5>" fetch origin
git -C "<ścieżka do checkoutu v5>" worktree add "<ścieżka do worktree V6>" feat/mission-control-v6

# 2. Zależności frontendu (potrzebne do testów i buildu; samo uruchomienie
#    panelu w trybie produkcyjnym działa z zacommitowanego web/dist):
npm --prefix "<ścieżka do worktree V6>" ci

# 3. Testy Python (Python 3.10+; runtime jest stdlib):
python -X utf8 scripts/run_tests.py
python -X utf8 scripts/check_secrets.py

# 4. Front + przeglądarka:
npm run check
npx playwright test
```

## 4. Jak uruchomić V6

- Świeży checkout działa bez Node — serwer domyślnie serwuje
  zacommitowany `web/dist` (weryfikacja sha256 z manifestu). Przykład
  obok działającej v5:
  `python -X utf8 opencode_dashboard.py --port 8780 --state-dir <katalog tymczasowy> --no-open`
- Tryb źródeł dla developmentu: po `npm ci` i `npm run build` uruchom
  z `--dev-web`.
- Migracja katalogu stanu v5:
  `python -X utf8 opencode_dashboard.py --migrate-state --state-dir <stan v5>`
  (kod wyjścia 0/1/2; kopia
  `observer.sqlite.pre-migration-v1-to-v2-<timestamp>`).
- Rotacja tokenu właściciela (przy zatrzymanym obserwatorze):
  `python -X utf8 opencode_dashboard.py --rotate-owner-token --state-dir <stan>`.
- Nie dotykać 8765 (produkcyjna v5) ani 8770 (dashboard porównawczy).
  Nie kończyć cudzych procesów.

## 5. Artefakty i dowody

- `TEST_REPORT.json` — końcowe liczby (wersja 6.0.0).
- `docs/V6_STATUS.md` — tabela etapów i pomiary.
- `docs/V6_MIGRATION.md` — migracja stanu.
- `docs/V6_COVERAGE.md` — model danych i kontrakt kompletności.
- `docs/V6_BENCHMARKS.md` — generator, metoda i wyniki 100k/1M.
- `docs/V6_RECONCILIATION.md` — uzgodnienie OpenCode/Codex.
- `scripts/check_i18n.mjs`, `scripts/check_secrets.py`,
  `scripts/benchmark_incremental.py`.
- `tests/test_v6_*.py`, `tests/browser/*.spec.mjs`.
- `docs/screenshots/` — zrzuty EN i PL (dane syntetyczne).

## 6. Rzeczy otwarte / wymagające decyzji użytkownika

- **Rotacja produkcyjnego tokenu właściciela v5 NIE została wykonana**
  (świadomie — wymaga zgody). Procedura: zatrzymać instancję,
  `python -X utf8 opencode_dashboard.py --rotate-owner-token --state-dir <stan>`,
  uruchomić ponownie z `--open`. Zachowuje bazę, konfigurację,
  `mcp.token` i `pairing.key`; restart unieważnia wydane tokeny OAuth.
- **Rzeczywiste połączenie klientów MCP (ChatGPT/Codex) NIE zostało
  zweryfikowane** — są lokalne testy protokołu; potrzebny test na
  realnym kliencie (checklista w E.3).
- **Migracja, deploy i merge produkcji** — kod gotowy i przetestowany;
  wykonanie i scalenie PR #2 wyłącznie za zgodą właściciela.

## 7. Stan instancji po resecie

Reset komputera zatrzyma działającą v5 na 8765. Po resecie uruchom ją
ponownie z katalogu v5: `START_MISSION_CONTROL.cmd` albo
`python -X utf8 opencode_dashboard.py --open` (uwaga: `--open` otwiera
przeglądarkę z fragmentem `#access` — nie kopiuj tego adresu do czatu
ani logów). Dashboard porównawczy na 8770 uruchamiasz ręcznie, jeśli
będzie potrzebny.
