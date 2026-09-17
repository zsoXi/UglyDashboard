# V6 — Status prac

Dokument roboczy odbioru V6. Bez sekretów, bez prywatnych promptów i bez
lokalnych danych użytkownika. Aktualizowany po każdym etapie.

- Wersja docelowa: **6.0.0** (obecnie kod nadal raportuje 5.0.0 — ujednolicenie w E.4)
- Gałąź: `feat/mission-control-v6` — HEAD `fd0088a`, wypchnięty, drzewo czyste
- Baza: `fix/mission-control-v5-hardening-ui` @ `5685080` (PR #1 wciąż otwarty)
- Worktree: `V6/UglyDashboard` (izolowany od działającej v5 na porcie 8765)
- Port testowy V6: 8780, osobny katalog stanu

## Etapy A–C (wcześniejsze, bez zmian)

Stan: `IMPLEMENTED AND VERIFIED` (szczegóły w historii commitów
`ac4d70f`, `b4941dd`, `b105ecf`, `5fe314a`).

- A: worktree + baseline w V6; `npm ci` 87 pakietów / 0 podatności.
- B: `Store.rotate_secret`, CLI `--rotate-owner-token`, `scripts/check_secrets.py`,
  `tests/test_v6_secrets.py`; uzgodnienie OpenCode — usunięty błąd
  174 609 418 tokenów (`docs/V6_RECONCILIATION.md`).
- C: przyrostowe pełne pokrycie OpenCode (checkpointy `usage_checkpoint`,
  `incremental.py`, budżet 5 s/cykl) i Codex (`discover_all_codex_files`,
  kursor rotacji, cache plików). Dowody: 100 tys. zdarzeń → 1000/1000 sesji,
  12 347 213 = wzorzec, 9,5 s, 1 cykl; 1 mln → 1000/1000, 126 001 216 = wzorzec,
  103,6 s, 6 cykli; restart w połowie i po imporcie bez utraty/podwójnego
  liczenia; Codex 12/12 plików + 1860 tokenów z limitem partii 10.

## Etap C.1 — precyzyjny kontrakt kompletności — IMPLEMENTED AND VERIFIED

Commit `c7e8bca` (3 pliki, +670/-11). Nowy, wspólny blok kompletności
(`engine.py: assemble_coverage/range_coverage/session_flags`):

- `metadata_complete`, `aggregates_complete`, `history_limited`,
  `breakdowns {daily,model,file}`, `breakdown_details`,
  `details_truncated`, `detail_events_evicted`, `catching_up`,
  `source_stale`, `read_blocked`, `discovered_sessions`,
  `processed_sessions`, `last_successful_read_at`.
- `_mark_read`/`_apply_coverage` w `Engine`; trwały
  `source_read_health` w `observer.sqlite`.
- Analiza zakresu: `compute_analytics(..., basis)` dokłada
  `coverage` o zakresie wybranych filtrów; eksport CSV przenosi ten sam
  blok w nagłówku `X-Mission-Control-Coverage`; MCP
  (`mission_overview`, `model_comparison`, `list_agents`) korzysta z
  tego samego obiektu.
- Zasady: pełna suma ≠ pełny podział; brak znanego mianownika = `null`,
  nie zero; nieświeży odczyt = ostatni dobry wynik + `source_stale`;
  zablokowany odczyt = `read_blocked`.
- Testy: `tests/test_v6_coverage.py` (8 przypadków, w tym 4001-częściowa
  sesja → sumy pełne, szczegóły ograniczone, 1 zdarzenie wyparte; restart
  budżetu; brak mianownika; spójność UI/eksport/MCP).
- Weryfikacja: 165 testów Python 0 błędów / 2 pominięcia; ruff czysty;
  `npm run check` zielony.

## Etap D.1 — pełne English / Polski — IMPLEMENTED AND VERIFIED

Commit `8459551` (22 pliki, +2464/-485), wypchnięty.

- `web/i18n/{core,en,pl}.js`: 454 klucze w każdej wersji, offline,
  `Intl` (liczby, daty, USD, plurals), interpolacja `{name}`,
  brakujące klucze raportowane (`window.mcMissingKeys`).
- `web/index.html`: `lang="en"`, angielskie fallbacki, `data-i18n*`,
  marka przez `data-i18n-skip`, skrypt jako moduł, przycisk `#lang`.
- `web/app.js`: zero polskich literałów; domyślnie EN; przełącznik
  zapisuje `mc-lang`, aktualizuje `html lang`, nie resetuje filtrów,
  widoku ani otwartego inspektora; bezpieczny odczyt/zapis storage.
- Kontrola: `scripts/check_i18n.mjs` (parytet kluczy/placeholderów/
  kategorii liczby mnogiej, mojibake, surowe klucze, polskie literały) —
  wpięta w `npm run check` (`check:i18n`).
- `server.py`: allowlist `/i18n/{en,pl,core}.js` (tryb źródłowy).
- Build: `scripts/build.mjs` z `bundle:true` (słowniki w jednym
  `dist/app.js`).
- Testy przeglądarkowe: `tests/browser/i18n.spec.mjs` (3) + zaktualizowane
  specy; `npx playwright test` 32/32.

## Etap D.2 — raport zużycia i spójność V6 — IMPLEMENTED AND VERIFIED

Commit `fd0088a` (9 plików, +446/-34), wypchnięty.

- Okresy: Today / 7 / 30 / 90 / rok / cała zarejestrowana historia
  (te same filtry projektu i źródła dla wszystkich elementów).
- Karty podsumowania nad raportem: tokeny (`data-total`), sesje,
  koszt zapisany, koszt szacowany, brak znanego kosztu (liczba mnoga),
  nota o walucie źródłowej.
- Przełączniki prezentacji: „Zwiń reasoning do outputu” (suma bez zmian)
  i widok udziału procentowego (składniki rozłączne, suma 100% ±1).
- Tabela sesji w okresie (`data-tokens`, wiersze klikalne), panel
  projektów, pliki z wierszem `Unassigned` i notą o heurystyce równego
  podziału, heatmapa globalna z rozróżnieniem „brak rekordów” od
  potwierdzanego zera, nota zakresu przy rejestrze routera.
- `coverageNotice(cov, windowLimit)` używa kompletności zakresu analizy.
- Testy: `tests/browser/usage.spec.mjs` (6) + pełny zestaw 38/38;
  `npm run check` zielony (i18n 454 = 454).

## Co pozostało — Etap E (E.1–E.4)

### E.1 — produkcyjny frontend z `dist` (następny krok)

- `scripts/build.mjs`: kopiuj `web/index.html` → `web/dist/index.html`;
  manifest ma objąć też wejścia `i18n/en.js`, `i18n/pl.js`, `i18n/core.js`
  i wyjście `index.html`.
- `server.py`: domyślnie serwuj `web/dist/*` z weryfikacją sha256 wobec
  `web/dist/manifest.json`; brak/zgodność build → czytelny komunikat
  (503 dla zasobów), **nigdy cichego fallbacku na `web/`**; `/i18n/*`
  tylko w jawnym trybie `dev_web`; `Server(..., dev_web=False)`.
- `cli.py`: flaga `--dev-web`; domyślnie produkcja.
- `tests/browser/global-setup.mjs`: przed startem fixture uruchom
  `npm run build` (świeży artefakt).
- Nowe testy `tests/test_v6_dist.py`: zgodność bajtów z manifestem,
  brak fallbacku przy braku/uszkodzeniu, `dev_web` + `/i18n` 200/404,
  brak dostępu do konfiguracji/logów/sekretów, praca z innego CWD.
- Odbiór: `npm run check`, `scripts/run_tests.py`, Playwright na `dist`.

### E.2 — migracja stanu obserwatora v5→V6

- Wersjonowana, transakcyjna, idempotentna, odporna na przerwanie;
  zachowuje ustawienia, oceny, źródła i sekrety (bez rotacji).
- Uwzględnia obecny stan V6 (nie tylko pustą bazę i czyste v5).
- Stare agregaty o niepotwierdzonej semantyce oznaczane do jawnego
  przeliczenia. Bez ręcznego kasowania `-wal`/`-shm`; backup przez
  SQLite backup API.
- Testy: pusta instalacja, stan v5, obecny V6, powtórzenie, przerwanie,
  błąd zapisu, zachowanie konfiguracji/ocen/sekretów.

### E.3 — MCP i bezpieczeństwo

- MCP: te same uzgodnione dane z kompletnością i pochodzeniem; testy
  `initialize`/`tools/list`/`tools/call`/`resources`, paginacja, brak
  dostępu do ustawień/sekretów/abort/shutdown, czysty stdout stdio,
  launcher z innego CWD i ścieżki Windows ze spacjami.
- Rzeczywiste klienty (ChatGPT/Codex) — checklist odbioru; lokalnie
  gotowe, zewnętrzna weryfikacja oznaczona jawnie.
- Bezpieczeństwo: potwierdzenie braku wycieku tokenu w logach/skryptach
  testów; procedura rotacji owner token (bez wykonania na produkcji).

### E.4 — odbiór końcowy, benchmarki, dokumentacja, CI, PR

- `ruff`, `compileall`, pełne testy Python, self-test, czyste `npm ci`,
  `npm run check`, Playwright na `dist`, `check_secrets.py`.
- Benchmarki 100 tys. i 1 mln zdarzeń (te same generatory; suma, cykle,
  restart w połowie i po imporcie, bez podwójnego liczenia,
  responsywność; RSS pozostaje `null`, jeśli niedostępny).
- Dokumentacja: README, README_PL, CHANGELOG, SECURITY, TEST_REPORT,
  V6_STATUS/HANDOFF + zrzuty EN/PL na syntetycznych danych.
- Wersja **6.0.0** spójna w backendzie, froncie, CLI, MCP i pakiecie.
- CI: krok i18n + Playwright na `dist`; przegląd wersji akcji;
  aktualizacja PR #2 (bez auto-merge, bez force-pusha).
