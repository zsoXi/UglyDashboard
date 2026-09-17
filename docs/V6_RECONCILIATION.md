# V6 — Uzgodnienie liczenia zużycia (OpenCode / Codex)

Dokument opisuje, skąd biorą się rozbieżności liczbowe raportowane między
panelami, i co z tego wynika dla V6. Wszystkie liczby pochodzą z jednego,
spójnego materiału, przeliczonego niezależnym narzędziem kontrolnym.

## Metoda

* Kopia źródłowej bazy OpenCode jest wykonywana przez SQLite backup API
  (`scripts/reconcile_usage.py`), więc uwzględnia WAL i stan spójny.
  Kopia żyje wyłącznie w prywatnym katalogu tymczasowym i jest usuwana po
  pomiarze; nie trafia do repozytorium ani do artefaktów.
* Warstwa Codexa jest liczona z lokalnych plików rollout
  (`scripts/reconcile_codex.py`), bez zapisu i bez zmiany plików źródłowych.
* Identyfikatory sesji są hashowane (`sha256[:16]`). Dokument nie zawiera
  tytułów sesji, promptów, ścieżek użytkownika ani sekretów.
* „Adapter" oznacza rzeczywisty czytnik produktu (`read_opencode`), a nie
  uproszczoną atrapę.

## OpenCode — dowód mechanizmu

Materiał: 160 sesji, 66 201 części, 13 343 zdarzenia zużycia.

| Miara | Wartość (tokeny) |
| --- | ---: |
| Suma po wszystkich częściach (`uncapped`) | **1 531 794 494** |
| Suma po wiadomościach asystenta (`message_level`) | **1 531 794 494** |
| Adapter produktu (v5/v6 reader) | **1 357 185 076** |
| Różnica (`uncapped` − adapter) | **174 609 418** (11,4%) |
| Emulacja capu oparta na częściach | **1 357 185 076** |

Emulacja limitu, która zachowuje wyłącznie najnowsze
`MAX_OC_PARTS_PER_SESSION = 4000` części na sesję, odtwarza wynik adaptera
**co do tokena (różnica 0,0)**. To dowodzi przyczyny bez zgadywania.

Dokładnie **dwie sesje** przekraczają 4000 części i odpowiadają za całą
różnicę:

| Sesja (sha256[16]) | Części | Okno części | Suma pełna | Adapter | Różnica |
| --- | ---: | ---: | ---: | ---: | ---: |
| `02b96c084677c344` | 6981 | 4000 | 279 421 550 | 108 309 355 | **171 112 195** |
| `a1d38b47a9df83a0` | 4356 | 4000 | 110 606 301 | 107 109 078 | 3 497 223 |
| pozostałe 158 sesji | ≤ 4000 | pełne | — | — | 0,0 |

Pokrycie raportowane przez czytnik: `truncated_sessions = 2`,
`parts_loaded = 62 864` z `66 201` (`truncated = true`).

**Wniosek:** suma zużycia sesji zależy od limitu przechowywanych
szczegółów. Starsze części `step-finish` są odcinane, a ich zużycie znika
z sumy. To nie jest błąd zaokrągleń ani różnica modeli — to skutek
`MAX_OC_PARTS_PER_SESSION`.

Ustalenie dodatkowe: na tym materiale suma tokenów z wiadomości
asystenta równa się sumie po wszystkich częściach (różnica 0,0). To czyni
okno wiadomości kandydatem na tanie źródło pełnych sum, ale samo ma
własny limit (`MAX_OC_MESSAGES_PER_SESSION = 800`), więc wymaga
osobnego, udowodnionego kontraktu, a nie założenia.

## Codex — różnica zakresu, nie tego samego pomiaru

| Źródło | Wartość | Co to jest |
| --- | ---: | --- |
| v5 UI „Codex session logs" | 45 435 355 912 | suma silnika w oknie **400 plików** |
| panel porównawczy | 9 581 676 500 | jego **syntetyzowany ledger routera** — inny zbiór danych |
| wszystkie lokalne pliki (pomiar) | **255 602 691 857** | 2184 pliki, 2182 unikalne sesje logiczne |
| suma po unikalnych sesjach (`max`) | 255 585 986 156 | po deduplikacji wielu plików jednej sesji |

Pomiar plików: 506 356 rekordów tokenów, 0 duplikatów identycznej treści,
3 sesje z wieloma plikami, 0 pominiętych rekordów out-of-order,
507 resetów licznika kumulatywnego.

**Wniosek:** raportowane „45,44 mld kontra 9,58 mld" to porównanie dwóch
różnych zbiorów danych, a nie dwóch metod liczenia tego samego. Prawdziwa
suma lokalna jest rzędu **255,6 mld** i mieści się w całości dopiero po
przetworzeniu wszystkich plików. Okno 400 plików sprawia, że suma Codexa
w v5 jest **strukturalnie niepełna**, nawet jeśli pojedyncze pliki są
liczone poprawnie.

## Konsekwencje dla V6 (wymagania wynikające z dowodu)

1. **Agregaty nie mogą zależeć od limitów szczegółów.** Limit części i
   limit plików Codexa mogą ograniczać to, co pokazujemy w inspektorze,
   ale nie mogą obcinać pełnych sum.
2. **Trzy rozdzielone warstwy:** agregaty (pełne, wszystkie poprawnie
   przetworzone dane w zakresie), szczegóły (limitowane liczba i
   retencja), checkpointy (wznowienie bez utraty i bez powtórzenia).
3. **Osobne znaczniki kompletności** w API i UI: metadane sesji, agregaty
   zużycia, ograniczenie szczegółów, trwające uzupełnianie, odkryte i
   przetworzone sesje. Udział „96/1000 sesji" nie jest udziałem tokenów.
4. **Codex discovery musi dojść do pełnego pokrycia** przyrostowo, z
   deduplikacją po tożsamości sesji i kontrolą nakładających się korzeni
   (`~/.codex` i `~/.codex/browser`).

## Ograniczenia tego pomiaru

* Jedna maszyna i jeden moment; źródłowa baza oraz katalog Codexa rosły
  w trakcie pracy, więc liczby bezwzględne zmieniają się między odczytami.
* Brak niezależnego generatora prawdy dla rzeczywistych danych; generator
  benchmarkowy istnieje tylko dla danych syntetycznych.
* Równość „wiadomości = części" zaobserwowano na tym materiale; nie jest
  to uniwersalna gwarancja i wymaga testu kontraktu w V6.
* Pomiar nie rozstrzyga, czy pojedyncze pliki Codexa zawierają pełną
  historię sesji; mierzy sumę tego, co jest lokalnie dostępne.

## Weryfikacja po poprawce (V6)

Po rozdzieleniu agregatów od szczegółów w `mission_control/sources.py`
(limit `MAX_OC_PARTS_PER_SESSION` ogranicza teraz wyłącznie historię
szczegółów, a suma zużycia obejmuje wszystkie części) ponowny pomiar na
świeższej kopii tej samej bazy dał:

| Miara | Tokeny |
| --- | ---: |
| Suma po wszystkich częściach (`uncapped_parts`) | **1 559 229 849** |
| Suma po wiadomościach (`message_level`) | **1 559 229 849** |
| Adapter produktu po poprawce | **1 559 229 849** |

* `delta.uncapped_minus_adapter = 0.0`
* `delta.uncapped_minus_message = 0.0`
* `delta.capped_minus_adapter = −178 287 801` — tylko jako dowód, ile
  wynosiłby stary błąd na tym materiale.
* Pokrycie czytnika: 161/161 sesji, `parts_loaded = 63 270`. Szczegóły
  pozostają ograniczone: `truncated = true` i 2 sesje z przyciętym oknem
  szczegółów, `deadline_exceeded = false`.
* Największa sesja w raporcie: 1173 części, wszystkie sumy równe
  (24 786 847), różnica 0,0.

Test regresyjny
`ReaderBoundsTests.test_part_paging_caps_detail_but_totals_cover_all_parts`
utrwala ten kontrakt: okno szczegółów jest przycinane do najnowszych
`MAX_OC_PARTS_PER_SESSION` części, a suma zużycia obejmuje wszystkie
części. `parts_loaded` pozostaje liczbą wczytanych szczegółów, a nowe
`aggregate_truncated_sessions` mówi, czy dopełnianie agregatu nie
zatrzymało się na budżecie odczytu.
