# OpenCode Mission Control v6

Lokalny panel obserwatora dla OpenCode, logów Codexa, projektów,
agentów, modeli, historii i MCP. Jeden właściciel, jedna maszyna:
czyta lokalne źródła tylko do odczytu i pokazuje aktywność,
analitykę, alerty oraz integracje w przeglądarce. Nie uruchamia
agentów, nie wysyła do nich poleceń ani nie modyfikuje repozytoriów.

> Stan: v6 (6.0.0) zaimplementowane i zweryfikowane w izolowanym
> worktree na gałęzi `feat/mission-control-v6` (kontrakt kompletności
> danych, lokalizacja EN/PL, raport użycia, serwowanie produkcyjnego
> bundla, wersjonowana migracja stanu, kontrole MCP/bezpieczeństwa).
> Działająca instancja v5 i jej dane nie są modyfikowane. Nic tutaj nie
> twierdzi, że nieuruchomiona kontrola przeszła.

## Struktura pakietu

```text
opencode_dashboard.py      Cienki launcher / API zgodności (importuje mission_control)
mission_control/           Pakiet backendu: cli, core, engine, locking,
                           mcp, migration, oauth, server, sources, store
web/                       Źródła frontendu (index.html, app.js, style.css, i18n/)
web/dist/                  Zbudowany bundle produkcyjny (serwowany domyślnie, manifest sha256)
scripts/build.mjs          Krok budowania frontendu (npm run build)
test_mission_control.py    Regresja offline (katalog główny)
tests/                     Dodatkowe suity hardeningowe
scripts/run_tests.py       Runner unittestów offline (uczciwy kod wyjścia)
scripts/smoke_startup.py   Test dymny prawdziwego panelu na porcie loopback
scripts/benchmark.py       Syntetyczny benchmark dużych danych (tylko stdlib)
scripts/benchmark_incremental.py  Benchmark importu przyrostowego (syntetyczne 100k / 1M)
docs/benchmarks/           Oczyszczone wyniki benchmarków + opis metody
.github/workflows/ci.yml   CI Windows + Linux (Python 3.10/3.14, Node 22)
```

Starsze opisy „jednego pliku Pythona ze wszystkim w środku” są
nieaktualne: od podziału v5 HTML/CSS/JS mieszkają w `web/`, a backend
Pythona w `mission_control/`. Launcher zachowuje dawną powierzchnię
linii poleceń (`--db`, `--port`, `--self-test`, …).

Źródła frontendu mieszkają w `web/` i są bundlowane przez
`npm run build` (esbuild → `web/dist/app.js` + `style.css` +
`manifest.json` z hashami wejść/wyjść). Wymagania: Node **≥ 22.13**
i czyste `npm ci` z zacommitowanego lockfile. Domyślnie serwer serwuje
zbudowany bundle `web/dist` i weryfikuje go hashami sha256 z manifestu;
gdy bundla brakuje, pokazuje czytelną stronę „wymagany build” zamiast
cichego fallbacku do źródeł. `--dev-web` serwuje źródła z `web/`
bezpośrednio (tryb developerski); `npm run check` (lint, ścisłe typy,
prettier, kontrola kluczy i18n, odtwarzalny build) to brama frontendu.

## Co nowego w V6 (6.0.0)

- Kompletność danych: jeden kontrakt pokrycia współdzielony przez UI,
  eksporty JSON/CSV i MCP. Metadane są dostępne od razu; agregaty są
  kompletne dla załadowanego okna, a szczegółowe wiersze pozostają
  w ograniczonym oknie i jest to jawnie raportowane
  (`details_truncated`), nigdy cicho zerowane. Eksporty CSV niosą
  nagłówek `X-Mission-Control-Coverage`. Szczegóły:
  `docs/V6_COVERAGE.md`.
- Języki: pełne słowniki angielski/polski (po 454 klucze), domyślnie
  angielski, przełącznik w górnym pasku zapamiętywany między
  odświeżeniami i zachowujący filtry, widok oraz inspektora.
- Raport użycia: okresy dziś / 7 / 30 / 90 dni / ostatni rok / całość ze
  współdzielonych agregatów, z kosztem zarejestrowanym vs szacowanym vs
  nieznanym, panelami sesji i projektów oraz widokiem plików, którego
  heurystyka równego przydziału jest oznaczona jako heurystyka
  (nieprzypisane wiersze zostają jako `Unassigned`).
- Serwowanie produkcyjne: `web/dist` z weryfikacją sha256 z manifestu
  (patrz wyżej); `--dev-web` dla źródeł.
- MCP: sposoby konfiguracji z sekcji poniżej bez zmian (lokalna
  konfiguracja stdio z widoku Integracje, ChatGPT przez OAuth z
  `public_origin` i dokładnym adresem callback); v6 dodaje kontrole
  protokołu dla obu wspieranych wersji MCP, stabilne narzędzia
  odczytu, warunkowe `report_event` i ściślejszą walidację.
- Migracja stanu: `python -X utf8 opencode_dashboard.py --migrate-state --state-dir <katalog>`
  podnosi katalog stanu v5 w jednej transakcji (kod wyjścia 0/1/2)
  i zostawia kopię SQLite przed migracją
  (`observer.sqlite.pre-migration-v1-to-v2-<timestamp>`); nowsze
  schematy są odrzucane. Szczegóły: `docs/V6_MIGRATION.md`.
- Rotacja tokenu: `python -X utf8 opencode_dashboard.py --rotate-owner-token --state-dir <katalog>`
  atomowo podmienia tylko `owner.token`; baza, konfiguracja, `mcp.token`
  i `pairing.key` zostają nietknięte. Uruchom przy zatrzymanym
  obserwatorze; restart unieważnia wydane tokeny OAuth.
- Liczby benchmarków: `docs/V6_BENCHMARKS.md`; stan implementacji:
  `docs/V6_STATUS.md` i `docs/V6_HANDOFF.md`.

Aby uruchomić v6 obok istniejącej instancji bez dotykania jej, użyj
osobnego portu i katalogu stanu:

```powershell
py -3 opencode_dashboard.py --open --port 8780 --state-dir ".\state-v6"
```

## Szybki start (Windows)

Wymagany Python **3.10+**. Dwuklik `START_MISSION_CONTROL.cmd`
(użyje `pyw`/`pythonw`, gdy dostępne, więc nie zostaje okno konsoli)
albo z PowerShella — cytuj ścieżkę, instalacje często leżą w folderach
ze spacjami lub znakami `!`:

```powershell
py -3 "D:\Ścieżka Ze Spacjami\MissionControl\opencode_dashboard.py" --open
```

Domyślny adres: `http://127.0.0.1:8765`. Launcher otwiera adres, którego
fragment niesie jednorazowy klucz właściciela; klucz zostaje w
`sessionStorage` tej karty. Nie udostępniaj adresu z fragmentem
logowania. Zamknięcie karty **nie** zatrzymuje obserwatora — użyj
**Ustawienia → Zatrzymaj obserwator** (konsola: Ctrl+C). Ponowny start
launchera otworzy istniejący panel, gdy zgadza się tożsamość aplikacji
i klucz właściciela.

Przy zajętym porcie wybierz inny:

```powershell
py -3 opencode_dashboard.py --open --port 8766
```

Linux działa tak samo przez `python3`. Zweryfikowano na Windows /
Python 3.14.3 dla 6.0.0 (patrz `TEST_REPORT.json`); linuksowe CI
puszcza tę samą suitę przy każdym pushu (`.github/workflows/ci.yml`).

## Podłączenie istniejącego OpenCode

Wskaż panelowi bazę (`--db` można powtarzać). Przykład z symbolem
zastępczym — podmień własną nazwę użytkownika:

```powershell
py -3 opencode_dashboard.py --open --db "$env:USERPROFILE\.local\share\opencode\opencode.db"
```

Do *potwierdzonej bieżącej* aktywności dodaj też adres HTTP już
działającej instancji OpenCode („Połączenie z istniejącym OpenCode”,
domyślny kandydat `http://127.0.0.1:4096`; port aplikacji desktopowej
może być inny). Sama baza daje historię, nie dowód, że proces nadal
pracuje. Panel nigdy nie startuje drugiego serwera OpenCode, nie skanuje
portów, nie wysyła poleceń agentom i rozmawia tylko z jawnie wskazanymi
adresami loopback. Jeśli serwer wymaga Basic Auth, wyeksportuj
`OPENCODE_SERVER_PASSWORD` (i opcjonalne `OPENCODE_SERVER_USERNAME`) w
środowisku panelu — haseł nie wkleja się do URL-i ani do czatu.

Czytnik dopasowuje się do zastanych kolumn SQLite zamiast zakładać jeden
schemat; niezgodny przyszły schemat zgłosi się w zdrowiu źródeł, nie
przeczyta po cichu błędnie.

## Podłączenie logów Codexa

Domyślnie lokalny katalog `.codex` (szanuje `CODEX_HOME`); nadpisanie
przez `--codex-home` albo konfigurację:

```powershell
py -3 opencode_dashboard.py --open --codex-home "$env:USERPROFILE\.codex"
```

Odczyt jest przyrostowy i znosi niedokończone linie JSONL, obrót logu,
częściowe UTF-8 i uszkodzone rekordy; okno wyboru i pominięcia są
raportowane. Lokalne logi nigdy nie pokazują prac wyłącznie chmurowych
i nie są sondą żywotności procesu. Zdarzenie końca tury znaczy koniec
tury — nie to, że zadanie przeszło testy.

## Codex jako lokalny klient MCP

Uruchom panel, otwórz **Źródła i MCP → Codex · lokalnie** i skopiuj
wygenerowany fragment TOML do konfiguracji MCP Codexa. Ma już prawdziwą
ścieżkę interpretera, bieżący plik i katalog stanu:

```toml
[mcp_servers.mission_control]
command = "C:\\Path\\To\\Python\\python.exe"
args = ["D:\\MissionControl\\opencode_dashboard.py", "--mcp-stdio", "--state-dir", "C:\\Users\\ty\\.opencode-mission-control"]
startup_timeout_sec = 20
tool_timeout_sec = 30
```

Most stdio nie tworzy drugiego obserwatora: czyta port z
`runtime.json` plus osobny lokalny token MCP. Panel musi działać. Do
stdio używaj konsolowego `python.exe`, nawet gdy UI startował przez
`pythonw.exe`. Wariant HTTP też generuje się w UI i wymaga
`MISSION_CONTROL_MCP_TOKEN` w środowisku Codexa — trzymaj go w tajemnicy.

## ChatGPT jako zdalny klient MCP (konfiguracja ręczna)

**Nic tutaj nie łączy się samo z Twoim kontem ChatGPT, a most nie czyta
w magiczny sposób wszystkich Twoich rozmów.** Widoczne są tylko wywołania
przechodzące przez ten most oraz zdarzenia jawnie zaraportowane przez
`report_event`. Konfiguracja leży po Twojej stronie:

1. Wystaw stabilny tunel HTTPS albo reverse proxy na lokalny port
   panelu. Aplikacja tunelu nie instaluje ani nie otwiera. Zdalne MCP
   działa tylko przez zewnętrzny HTTPS; zwykłe lokalne użycie nie
   potrzebuje tunelu.
2. W ustawieniach MCP ustaw `public_origin` (np.
   `https://mc.twoja-domena.pl`, bez ścieżki) i dokładne callbacki
   OAuth pokazane przez Twojego klienta ChatGPT. Domyślnie akceptowany
   jest oficjalny `https://chatgpt.com/connector_platform_oauth_redirect`.
3. Utwórz połączenie ChatGPT do `https://twój-host/mcp` z OAuth i
   dynamiczną rejestracją klienta (DCR). Nie wymyślaj statycznych danych
   klienta.
4. Na stronie autoryzacji *tego obserwatora* wklej klucz parowania z
   lokalnego panelu. Nie wysyłaj go czatem ani obcemu serwerowi MCP.

Zdalny OAuth jest praktycznie **domyślnie wyłączony** (pusty
`public_origin`, brak publicznej ekspozycji). Implementacja obejmuje
metadane serwera/zasobu, DCR z listą callbacków, PKCE S256, kody
jednorazowe, tokeny związane z odbiorcą, rotację przy odświeżaniu i
unieważnianie. Dostęp zdalny nie obejmuje ustawień właściciela ani
zatrzymywania agentów. Tokeny dostępu żyją godzinę; restart obserwatora
unieważnia wydane tokeny, zachowując rejestracje klientów. To lokalne
narzędzie jednego właściciela, nie audytowany system tożsamości dla
usług wieloużytkownikowych: zakończ poprawnie TLS, ogranicz ruch,
przekazuj zaakceptowany Host nietknięty i nigdy nie wyłączaj kontroli
Origin/Host, żeby „naprawić” tunel. Logowania end-to-end prawdziwym
kontem ChatGPT nie testowano; protokół i OAuth zweryfikowano
kontrolowanym klientem lokalnym.

## Narzędzia MCP

Domyślne narzędzia odczytu: `mission_overview`, `list_agents`,
`agent_details`, `list_projects`, `timeline`, `model_comparison`,
`alerts`, `sources`, `search`, `fetch`. Włączenie raportowania dodaje
`report_event` (opt-in, `enable_reporting`, domyślnie wyłączone).
Sugerowana instrukcja dla klienta:

> Sprawdź mission_overview, potem list_agents. Oddziel aktywność
> potwierdzoną od historycznej i zgłoszonej. Podaj projekt, rzeczywisty
> model i ostatnie narzędzie. Nie licz definicji agentów jako
> uruchomionych workerów.

`report_event` wymaga istniejącego ID sesji z `list_agents`; to
deklaracja klienta (bez rozliczania tokenów, bez startu pracy).
Powtórzenie `event_id` jest idempotentne; zmiana treści pod tym samym ID
jest odrzucana.

## Znaczenie stanów i liczb

`verified` = świeży status z API OpenCode. `recorded` = zapisany
stan/znacznik w danych źródłowych. `reported` = czyjeś oświadczenie.
`unknown` / `stale` = za mało dowodów albo wygasły. Sam świeży timestamp
nigdy nie robi RUNNING; stan inspektora wygasa po oknie świeżości.

Zapisany rodzic nie dowodzi subagenta: tylko delegujące wywołanie
narzędzia (albo jawna informacja o starcie dziecka) awansuje do
`delegated`; forki zostają osobno. Graf nie dopisuje ról CTO/TL z nazw
i pokazuje co najwyżej 120 węzłów.

Matematyka tokenów: cache/reasoning normalizowane na źródło; zapisów
wiadomości i odpowiadających im step-finish nie sumujemy podwójnie;
narastających liczników Codexa nie doliczamy od nowa; rejestr routera
jest osobny (może pokrywać się z sesjami natywnymi). Wiek sesji to nie
czas pracy modelu. Tabele plików dzielą tokeny sesji równo między
odnotowane pliki — oznaczone jako podział, nie pomiar kosztu edycji.
Koszt pochodzi z zapisanych danych albo z jawnie ustawionych cen
USD-za-milion; nie ma zgadywanych cen wbudowanych.

Alerty tylko alarmują (nieświeże źródło, niezgodny model, błędy, pętle
narzędzi, budżet, edycje poza zakresem, konflikty plików): ustaw dokładne
ID modeli w `expected_models` i foldery w `allowed_paths`. Zatrzymanie
agenta OpenCode wymaga jawnego `allow_abort: true` **i** wpisania przez
właściciela dokładnego natywnego ID; zwykłe tokeny MCP/OAuth nigdy nie
mogą przerywać, a logi Codexa nie mają przerywania wcale.

## Skanowanie, retencja i prywatność

Skanuj wybrane foldery (np. katalog projektów), nigdy całe dyski:
ograniczona głębokość, 6000 folderów, 12 s, bez podążania za
dowiązaniami, `auth.json`/`.env` nigdy nie przeszukiwane. Wyniki
zaznaczasz checkboxami, monitorowanie startuje dopiero osobną decyzją.
Źródła otwierane są read-only; własny stan mieszka w
`~/.opencode-mission-control` (`config.json`, `observer.sqlite`,
`runtime.json`, logi, `owner.token`, `mcp.token`, `pairing.key`) — trzy
klucze są poufne, tego katalogu nigdy nie commituj ani nie synchronizuj.

Limity pokrycia (domyślne; ograniczenia źródeł widać w panelu):

| Źródło | Limit |
| --- | --- |
| Sesje OpenCode DB | `history_limit` 1000 najnowszych na bazę |
| Pliki logów Codexa | 400 najnowszych |
| Wiadomości / sesję | 800 najnowszych |
| Party / sesję | 4000 najnowszych, łącznie 250000 |
| Zdarzenia / sesję | ostatnie 120 |
| Własna historia zdarzeń | retencja 90 dni |
| Graf agentów (widok) | 120 węzłów |
| Cache analityki | 16 wpisów |

Prompty i wyniki narzędzi mogą nieść sekrety; redakcja znanych wzorców
kluczy to pomoc, nie gwarancja. `show_prompts: false` chowa prompty
i definicje, ale nie czyni wyników narzędzi bezpiecznymi do publikacji.
Na Windows uprawnienia plików zależą dodatkowo od ACL katalogu i konta.

## Cykl życia silnika i blokady (jak w kodzie)

`Engine` (`mission_control/engine.py`) zbiera źródła w niezmienny
publikowany snapshot. `lock` (RLock) chroni sesje/snapshot/konfigurację/
fakty/cache; `poll_lock` serializuje cykle kolektora; cały I/O sieciowy,
bazodanowy i gitowy dzieje się **poza** `lock`, a publikowane obiekty
są podmieniane kopiuj-i-zamień pod `lock`. Cykl: konstrukcja →
`start()` (pętla `poll()` w tle) → `poll()` na cykl → `close()`; użycie
po zamknięciu rzuca `LifecycleError`. Uszkodzone lokalne sekrety rzucają
`SecretError` zamiast cichej rotacji — odzysk jest jawny (usuń plik
tokenu przy zatrzymanym obserwatorze; świeży sekret utworzy się przy
starcie), a uszkodzone bajty lądują w kwarantannie (`.bak`).

## Weryfikacja (tylko faktyczne wyniki)

* Regresja: **144 przebiegi, 0 porażek, 2 pominięcia** (Windows,
  Python 3.14.3, ~37 s, zero `ResourceWarning`) przez `python -X utf8
  scripts/run_tests.py`. Pominięcia: brak tworzenia dowiązań, asercja
  uprawnień POSIX (Windows używa ACL).
* Test wbudowany: **10/10** przez `opencode_dashboard.py --self-test`.
* Lint: `ruff check` jest czysty (0 błędów).
* Benchmark syntetyczny (po poprawce, `docs/benchmarks/*-after.json`):
  1000 sesji / 100 tys. zdarzeń → zimny parse ~1,4 s, zimny poll **8,9 s**,
  pełne pokrycie; 1 mln zdarzeń → zimny poll **12,6 s**, publikuje
  **96 z 1000** sesji z `deadline_exceeded=true` / `truncated=true`
  (wcześniej 0 sesji / `OperationalError: interrupted`). Niepełne okno
  jest świadomie przyjętym, zapisanym ograniczeniem i jest oznaczone w
  interfejsie („Statystyki niepełne”). Szczegóły i uczciwa metoda pamięci
  w `docs/benchmarks/README.md`.
* CI (`.github/workflows/ci.yml`, Windows+Ubuntu × Python 3.10/3.14,
  Node 22, przypięty ruff, self-test, regresja, `npm run check`,
  wymagany Playwright na obu systemach z wyłącznie syntetycznymi
  artefaktami błędów): **brak przebiegu na GitHubie** — nie twierdzimy,
  że jest zielone, dopóki nie zostanie uruchomione.
* Testy przeglądarkowe: `playwright.config.mjs` (MUSE-1), global setup
  stawia syntetyczny fixture (`scripts/browser_fixture.py`, prawdziwy
  Engine + Server, dane ulotne). **27/27 przechodzi lokalnie**
  (desktop + mobile) przez `npx playwright test`; publikowalne zrzuty
  lądują w `docs/screenshots/`, dodatkowe w `artifacts/`.
* Bramki frontendu (DS-1): `npm run lint`, `npm run typecheck`
  (ścisły), `npm run format:check` oraz `npm run build` (odtwarzalny
  bundle) przechodzą — zweryfikowano lokalnie 2026-09-16 (Windows, Node
  z tego repozytorium).

```powershell
py -3 opencode_dashboard.py --self-test
py -3 scripts/run_tests.py
py -3 scripts/smoke_startup.py
py -3 scripts/benchmark.py
```

Pełny log: `artifacts/unittest.log` (lokalny, ignorowany przez git).
Maszynowe podsumowanie: `TEST_REPORT.json`.

## Źródła dokumentacji integracji (sprawdzone 2026-09-16)

* OpenCode server: https://opencode.ai/docs/server/
* Codex MCP: https://developers.openai.com/codex/mcp
* OpenAI app auth: https://developers.openai.com/plugins/build/auth
* MCP Streamable HTTP: https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
* MCP tools: https://modelcontextprotocol.io/specification/2025-11-25/server/tools

Negocjowane wersje MCP to tylko `2025-11-25` i `2025-06-18`. Lokalne
formaty logów ewoluują niezależnie od specyfikacji MCP.

## Powrót do poprzedniej wersji

`backup/opencode_dashboard_original.py` przechowuje wcześniej wydany
plik. Zatrzymaj nowy obserwator, odłóż jego katalog stanu i przywróć
kopię. Źródłowych danych OpenCode/Codexa nie trzeba przywracać — ta
aplikacja ich nigdy nie zapisuje.
