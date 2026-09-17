# V6 — Status prac (stan końcowy, 6.0.0)

Dokument odbioru V6. Bez sekretów, bez prywatnych promptów i bez
lokalnych danych użytkownika. Liczby pochodzą z `TEST_REPORT.json`
(Windows / Python 3.14.3); Linux należy do CI.

- Wersja: **6.0.0** — backend, frontend, CLI, pakiet npm i dystrybucja
  raportują tę samą wersję.
- Gałąź: `feat/mission-control-v6`; etapy A–E.4 w jednym łańcuchu
  commitów. E.4 to commit końcowy (zawiera m.in. ten dokument).
- Baza: `fix/mission-control-v5-hardening-ui` @ `5685080` (PR #1 nadal
  otwarty). PR V6: #2 (draft, aktualizowany na końcowym commicie).
- Worktree: `<ścieżka do worktree V6>` — izolowany od
  działającej v5 na porcie 8765; jej dane nie były modyfikowane.
- Testy manualne V6: port 8780 + osobny katalog stanu.
- CI (`.github/workflows/ci.yml`): Windows + Ubuntu × Python 3.10/3.14,
  job przeglądarkowy (Node 22) na produkcyjnym `dist`; wynik końcowego
  commita śledzony w PR #2.

## Tabela etapów

| Etap | Status | Commit | Dowód / zakres |
| --- | --- | --- | --- |
| A–C — izolacja, sekrety, przyrostowe pokrycie | IMPLEMENTED AND VERIFIED | `ac4d70f`, `5fe314a`, `b4941dd`, `b105ecf` | 144 testy baseline; `npm ci` 87 pakietów / 0 podatności; `Store.rotate_secret`, CLI `--rotate-owner-token`, `scripts/check_secrets.py`; `docs/V6_RECONCILIATION.md` |
| C.1 — precyzyjny kontrakt kompletności | IMPLEMENTED AND VERIFIED | `c7e8bca` | `tests/test_v6_coverage.py` (8); wspólny blok kompletności w UI, eksporcie CSV (nagłówek `X-Mission-Control-Coverage` + sekcja `# coverage` w pobranym pliku) i MCP |
| D.1 — pełne English / Polski | IMPLEMENTED AND VERIFIED | `8459551` | 454 klucze EN = 454 PL; `scripts/check_i18n.mjs` w `npm run check`; przełącznik języka bez resetu filtrów, widoku ani inspektora |
| D.2 — raport zużycia | IMPLEMENTED AND VERIFIED | `fd0088a` | okresy Today/7/30/90/rok/całość; karty KPI; `tests/browser/usage.spec.mjs` (6) |
| E.1 — produkcyjny frontend z `dist` | IMPLEMENTED AND VERIFIED | `fbdb4a9` | `web/dist` + manifest sha256; czytelna strona „wymagany build”; brak cichego fallbacku na źródła; `--dev-web`; `tests/test_v6_dist.py` (6) |
| E.2 — migracja stanu v5→V6 | IMPLEMENTED AND VERIFIED | `d775849` | `mission_control/migration.py`; jedna transakcja + kopia SQLite; `--migrate-state` (0/1/2); `tests/test_v6_migration.py` (8); `docs/V6_MIGRATION.md` |
| E.3 — MCP i bezpieczeństwo | IMPLEMENTED AND VERIFIED | `eaefb75` | `tests/test_v6_mcp.py` (10); protokoły obu wersji MCP, brak dostępu do ustawień/sekretów/abort/shutdown, czysty stdout stdio |
| E.4 — odbiór końcowy | IMPLEMENTED AND VERIFIED | commit E.4 (ten dokument) | wersja 6.0.0, benchmarki 100k/1M, dokumentacja + zrzuty EN/PL, CI, PR #2 |

## Pomiary końcowe (skrót z `TEST_REPORT.json`)

- Python: 190 testów, 0 błędów, 2 pominięcia środowiskowe (tworzenie
  symlinków niedostępne; tryb POSIX plików sekretów na Windows),
  0 `ResourceWarning`, 55,0 s.
- Wbudowane self-testy: 10/10. `ruff`: czysto.
- Frontend: `npm run check` zielony — eslint, ścisły typecheck, prettier,
  parytet i18n (454 = 454), odtwarzalny build (`index.html`, `app.js`,
  `style.css`).
- Przeglądarka: 38/38 na produkcyjnym `dist` (desktop + mobile).
- MCP: 10/10. Migracja: 8/8. `scripts/check_secrets.py`: czysto.
- Restart (dane rzeczywiste, 2026-09-17): trwałe checkpointy sesji Codex
  odtwarzają sumy i sesje bez ponownego odczytu niezmienionych logów.
  - Pełna skala (2 192 → 2 194 sesje): przed przerwaniem 254 404 119 600
    (odczyt w toku); pierwszy snapshot po restarcie 252 241 696 868
    z 2 192/2 192 sesjami odtworzonymi z trwałych checkpointów (99,15%
    sumy częściowej); po zakończeniu wznowienia 256 187 084 501 przy
    agregatach kompletnych; ponowny restart dał tę samą sumę — 0 sesji
    ze zmienioną sumą.
  - Zakres zamrożony (10 rzeczywistych plików rollout, 119,4 MB, sha256
    w dowodach): pełny odczyt 344 632 181 → restart 344 632 181 →
    ponowny restart 344 632 181; przerwanie w trakcie importu przy
    152 840 456 — po wznowieniu 344 632 181 (różnica 0 wobec pełnego
    odczytu tego samego zakresu).
  - Wzór odbioru: `Zakres:` te same zdarzenia sprzed przerwania procesu;
    `Suma przed przerwaniem:` 152 840 456 (zakres zamrożony, odczyt
    w toku) / 254 404 119 600 (pełna skala, odczyt w toku);
    `Suma po zakończonym wznowieniu:` 344 632 181 / 256 187 084 501;
    `Różnica:` 0; `Kompletność agregatów dla tego zakresu:` complete;
    `Ponowny restart:` bez zmiany sumy.
  - Dowody poza repozytorium: snapshoty overview wszystkich faz, skrypty
    odtworzenia i provenance plików (lokalny folder dowodów restartu).
  - Test regresyjny: `test_restart_republishes_durable_checkpoints_without_recounting`.

## Benchmarki (syntetyczne, `scripts/benchmark_incremental.py`)

| Zakres | Suma tokenów | Cykle | Czas pełnego pokrycia | Szczegóły |
| --- | --- | --- | --- | --- |
| 100 tys. zdarzeń (1000 sesji, 98 000 części) | 12 347 213 = wzorzec | 1 | 10,56 s | metadata 10 510,2 ms; pierwszy przegląd 20,4 ms; analytics 0,033 / 0,001 s; tracemalloc 90 318 555 B |
| 1 mln zdarzeń (1000 sesji, 1 000 000 części) | 126 001 216 = wzorzec | 7 | 126,946 s | metadata 18 490,9 ms; pierwszy przegląd 23,1 ms; analytics 0,027 / 0,002 s; tracemalloc 242 816 596 B; 148/1000 sesji z pełnymi szczegółami w ograniczonym oknie (agregaty pełne) |

- Restart w połowie importu 1M: 87 317 016 → 126 001 216 po 1 wznowionym
  cyklu; sumy zgodne, bez podwójnego liczenia. Restart po pełnym imporcie
  nie zmienia sum.
- Metoda: `tracemalloc`; RSS raportowany jako `null`, gdy niedostępny
  (nie udajemy pomiaru). Porównanie z Etapem C: 9,5 s / 1 cykl (100k)
  i 103,6 s / 6 cykli (1M) — obecny przebieg 10,56 / 1 i 126,946 / 7;
  różnica wynika z księgowości kompletności i obciążenia maszyny, sumy
  bez zmian. Metoda i pełne tabele: `docs/V6_BENCHMARKS.md`.

## Co pozostaje użytkownikowi

- **Rotacja produkcyjnego tokenu właściciela NIE wykonana** (wymaga
  zgody): `python -X utf8 opencode_dashboard.py --rotate-owner-token --state-dir <stan>`
  przy zatrzymanej instancji; baza, konfiguracja, `mcp.token` i
  `pairing.key` zostają nietknięte.
- **Rzeczywiste klienty MCP (ChatGPT / Codex)**: lokalne testy protokołu
  przechodzą; połączenie realnego klienta wymaga zewnętrznej weryfikacji
  (checklista w E.3).
- **Migracja, deploy i merge produkcji**: kod gotowy i przetestowany;
  wykonanie na v5 oraz scalenie PR #2 dopiero za zgodą właściciela.
