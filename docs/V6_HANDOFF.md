# V6 — Handoff (stan na 2026-09-17, po C.1/D.1/D.2, przed etapem E)

Dokument przekazania roboczego stanu V6. Publiczny: brak sekretów, brak prywatnych promptów,
brak danych użytkownika. Ścieżki użytkownika podano jako `%USERPROFILE%` — nie kopiuj ich do repo.

## 1. Gdzie jest projekt

| Rola | Ścieżka | Gałąź | Uwaga |
| --- | --- | --- | --- |
| v5 (produkcja, działająca) | `D:\TESTY!\Dashboard\V2\OpenCode_Mission_Control_v4` | `fix/mission-control-v5-hardening-ui` @ `5685080` | instancja na porcie 8765 (PID może się zmienić) |
| V6 (praca) | `D:\TESTY!\Dashboard\V6\UglyDashboard` (git worktree) | `feat/mission-control-v6` @ `fd0088a` | port testowy 8780, osobny katalog stanu |
| Dashboard porównawczy | `D:\TESTY!\Dashboard\opencode_dashboard.py` | — | port 8770; NIE modyfikować |
| Raport odniesienia | `D:\TESTY!\V3\little-better-dashboard` | — | nie był źródłem procesu na 8770 |

Repo: `https://github.com/zsoXi/UglyDashboard`
- PR v5: #1 (`fix/mission-control-v5-hardening-ui` → `main`), nadal otwarty, nie scalony.
- PR V6: #2 (draft) — baza `fix/mission-control-v5-hardening-ui`, head `feat/mission-control-v6`.

## 2. Stan wykonania

| Etap | Status | Dowód |
| --- | --- | --- |
| A — izolacja i baseline | IMPLEMENTED AND VERIFIED | worktree od `5685080`; 144 testy baseline; `npm ci` 87 pakietów / 0 podatności |
| B — sekrety + uzgodnienie zużycia | IMPLEMENTED AND VERIFIED | `Store.rotate_secret`, CLI `--rotate-owner-token`, `scripts/check_secrets.py`; `docs/V6_RECONCILIATION.md` |
| C — przyrostowe pełne pokrycie (OpenCode + Codex) | IMPLEMENTED AND VERIFIED | commity `b4941dd`, `b105ecf`; 100k → 12 347 213 = wzorzec / 9,5 s; 1M → 126 001 216 = wzorzec / 103,6 s / 6 cykli; restart bez utraty i podwójnego liczenia |
| C.1 — precyzyjny kontrakt kompletności | IMPLEMENTED AND VERIFIED | commit `c7e8bca`; `tests/test_v6_coverage.py`; eksport CSV + MCP na tym samym bloku |
| D.1 — pełne English / Polski | IMPLEMENTED AND VERIFIED | commit `8459551`; 454 klucze EN = 454 PL; `scripts/check_i18n.mjs`; Playwright 32/32 |
| D.2 — raport zużycia | IMPLEMENTED AND VERIFIED | commit `fd0088a`; `tests/browser/usage.spec.mjs`; Playwright 38/38 |
| E — MCP, produkcyjny dist, migracja, benchmarki, odbiór | NOT COMPLETED (następny krok) | plan w `docs/V6_STATUS.md` |

Stan bieżący (zweryfikowany przed handoffem):

- HEAD `fd0088a` wypchnięty na `origin/feat/mission-control-v6`, drzewo czyste.
- `scripts/run_tests.py` → 165 testów, 0 błędów, 2 pominięcia środowiskowe, 0 `ResourceWarning`.
- `npm run check` zielony (lint, strict typecheck, prettier, `check:i18n` 454 = 454, build odtwarzalny).
- `npx playwright test` → 38/38 (desktop + mobile).
- `scripts/check_secrets.py` → czysto.

## 3. Jak wznowić po resecie (kolejność)

```powershell
# 1. Worktree (jeśli istnieje — nic nie rób; jeśli zniknie, odtwórz z v5-repo):
git -C "D:\TESTY!\Dashboard\V2\OpenCode_Mission_Control_v4" worktree list
git -C "D:\TESTY!\Dashboard\V2\OpenCode_Mission_Control_v4" worktree add -b feat/mission-control-v6 "D:\TESTY!\Dashboard\V6\UglyDashboard" fd0088a

# 2. Zależności frontendu w V6:
npm --prefix "D:\TESTY!\Dashboard\V6\UglyDashboard" ci

# 3. Testy Python (v5-venv 3.14 albo dowolne Python 3.10+; runtime jest stdlib):
# zalecane: uruchamiaj skryptami z katalogu V6:
#   python -X utf8 scripts/run_tests.py
#   python -X utf8 scripts/check_secrets.py

# 4. Front + przeglądarka:
npm run check
npx playwright test
```

Uruchamianie instancji V6 do testów manualnych: **port 8780 + osobny katalog stanu**, np.
`python -X utf8 opencode_dashboard.py --port 8780 --state-dir <katalog tymczasowy> --no-open`.
Nie dotykać 8765 (produkcyjna v5) ani 8770 (dashboard porównawczy). Nie kończyć cudzych procesów.

## 4. Następny krok — E.1 (produkcyjny `dist`)

1. `scripts/build.mjs`: kopiowanie `web/index.html` → `web/dist/index.html`; manifest ma
   objąć wejścia `i18n/en.js`, `i18n/pl.js`, `i18n/core.js` oraz wyjścia
   `index.html`, `app.js`, `style.css`.
2. `mission_control/server.py`: domyślnie serwuj `web/dist/*` z weryfikacją sha256 wobec
   `web/dist/manifest.json`; przy braku lub niezgodności — czytelna strona komunikatu
   (i 503 dla `app.js`/`style.css`), **bez cichego fallbacku na `web/`**; `/i18n/*`
   tylko w trybie `dev_web`; parametr `Server(..., dev_web=False)`.
3. `mission_control/cli.py`: flaga `--dev-web`; domyślnie produkcja.
4. `tests/browser/global-setup.mjs`: przed startem fixture uruchom `npm run build`.
5. Nowe `tests/test_v6_dist.py`: zgodność serwowanych bajtów z manifestem; brak fallbacku;
   `dev_web` + `/i18n` 200/404; brak dostępu do konfiguracji/logów/sekretów; praca z innego CWD.
6. Odbiór: `npm run check`, `scripts/run_tests.py`, pełny Playwright na `dist`.

Potem E.2 (migracja `observer.sqlite`), E.3 (MCP + bezpieczeństwo), E.4 (odbiór końcowy,
benchmarki 100k/1M, dokumentacja + zrzuty EN/PL, wersja 6.0.0, CI, PR #2). Szczegóły:
`docs/V6_STATUS.md`, sekcje E.1–E.4.

## 5. Dowody i artefakty

- `docs/V6_STATUS.md` — status etapów i co pozostało.
- `docs/V6_RECONCILIATION.md` — uzgodnienie OpenCode/Codex z liczbami i wnioskami.
- `scripts/check_i18n.mjs` — kontrole słowników i tekstów UI.
- `scripts/check_secrets.py` — guard wycieków (ścieżka/linia/etykieta/długość; exit 1 przy trafieniu).
- `tests/test_v6_coverage.py` — macierz kompletności (C.1).
- `tests/browser/i18n.spec.mjs`, `tests/browser/usage.spec.mjs` — odbiór UI w obu językach i raport zużycia.

## 6. Rzeczy otwarte / wymagające decyzji użytkownika

- **Rotacja produkcyjnego tokenu właściciela v5 NIE została wykonana** (świadomie — wymaga zgody).
  Procedura: zatrzymać instancję, `python -X utf8 opencode_dashboard.py --rotate-owner-token
  --state-dir <stan>`, uruchomić ponownie z `--open`. Zachowuje bazę, konfigurację,
  `mcp.token` i `pairing.key`.
- **Rzeczywiste połączenie klientów MCP (ChatGPT/Codex) NIE zostało zweryfikowane** — są tylko
  lokalne testy protokołu; potrzebny jest test na realnym kliencie (checklist w E.3).
- Historyczne tokeny z logów terminala są nieaktywne (sesje zakończone), ale rotacja
  produkcyjna pozostaje zalecana przy najbliższym restarcie v5.

## 7. Stan instancji po resecie

Reset komputera zatrzyma działającą v5 na 8765. Po resecie uruchom ją ponownie z katalogu v5:
`START_MISSION_CONTROL.cmd` albo `python -X utf8 opencode_dashboard.py --open`
(zwróć uwagę: `--open` otwiera przeglądarkę z fragmentem `#access` — nie kopiuj tego adresu do
czatu ani logów). Dashboard porównawczy na 8770 uruchamiasz ręcznie, jeśli będzie potrzebny.
