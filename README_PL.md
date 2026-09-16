# OpenCode Mission Control 4.0

Przebudowany `opencode_dashboard.py`: jeden lokalny panel dla OpenCode, logów Codexa, projektów, agentów, modeli, historii i MCP. Aplikacja pozostaje pojedynczym plikiem Python. HTML, CSS, JavaScript, serwer HTTP, czytniki i most MCP są w środku. Nie wymaga npm, Reacta, bundlera, pip ani zewnętrznego CDN.

## Szybki start na Windows

Wymagany jest Python **3.10 lub nowszy**. Rozpakuj cały ZIP do stałego folderu i uruchom dwuklikiem **START_MISSION_CONTROL.cmd**. Launcher użyje `pyw` lub `pythonw`, gdy są dostępne, aby nie pozostawiać okna terminala. Otworzy panel w przeglądarce. Jeśli start się nie uda, uruchom `START_DEBUG.cmd`, który pokazuje komunikaty.

Alternatywnie:

```powershell
py -3 opencode_dashboard.py --open
```

Domyślny adres to `http://127.0.0.1:8765`. Launcher otwiera adres z jednorazowo usuwanym z paska fragmentem zawierającym klucz właściciela. Klucz pozostaje w pamięci danej karty (`sessionStorage`), dopóki karta istnieje. Nie udostępniaj adresu z fragmentem logowania.

Zamknięcie karty nie zatrzymuje obserwatora. Zakończ go przez **Ustawienia → Zatrzymaj obserwator**. To wyłącza panel i jego most MCP, ale nie zatrzymuje agentów. W trybie konsolowym działa także Ctrl+C. Ponowne uruchomienie launchera otworzy istniejący panel, jeśli zgadza się tożsamość aplikacji i klucz właściciela.

Stary dashboard należy wcześniej zamknąć, jeżeli zajmuje ten sam port. Ta aplikacja nie odinstalowuje ani nie zatrzymuje innych usług. Możesz też wybrać inny port:

```powershell
py -3 opencode_dashboard.py --open --port 8766
```

## Dziesięć obszarów funkcjonalnych

| Obszar | Co zostało zaimplementowane |
| --- | --- |
| Centrum dowodzenia | Liczniki aktywności z poziomem pewności, karty projektów, ostatnie sesje, historia i zdrowie źródeł. |
| ChatGPT MCP | Chroniony endpoint `/mcp`, narzędzia odczytu, opcjonalny `report_event`, identyfikacja zadeklarowanych klientów, OAuth z PKCE dla połączeń zdalnych. |
| Codex | Odczyt lokalnych logów `sessions` i `archived_sessions`, znaczniki tur, narzędzia, modele i narastające zużycie tokenów. |
| Graf agentów | Relacje rodzic/dziecko, rozróżnienie delegacji i forków, przesuwanie, powiększanie, klikany inspektor. Limit 120 węzłów w widoku. |
| Historia | Wspólny strumień zdarzeń ze źródeł i raportów, wyszukiwanie i stronicowanie. |
| Inspektor | Zadanie, model, źródło stanu, narzędzia, pliki, tokeny, definicja agenta i wpisana przez właściciela ocena wyniku. |
| Wykrywanie źródeł | Skan wybranych folderów, wyniki z checkboxami i osobna decyzja o monitorowaniu. |
| Modele i zużycie | Okresy, źródła, projekty, grupy porównywalnych zadań, cache, ceny, oceny testów i poprawek, wykresy, mapa aktywności oraz CSV/JSON. |
| Alerty | Brak nowych dowodów aktywności, niezgodny model, błędy, powtarzane narzędzia, budżet, edycje poza zakresem i możliwe konflikty plików. Opcjonalne powiadomienia przeglądarki. |
| Globalny panel projektów | Wspólny widok projektów OpenCode/Codex/MCP oraz kontekst Git; każde źródło zachowuje własną tożsamość. |

## Podłączenie istniejącego OpenCode

Najpierw otwórz **Źródła i MCP**. Panel próbuje znaleźć bazę OpenCode w standardowej lokalizacji użytkownika. Nie musi jednak trafić na niestandardową instalację. Wtedy wskaż plik bazy przez konfigurację lub argument `--db`:

```powershell
py -3 opencode_dashboard.py --open --db "C:\Users\Matt\.local\share\opencode\opencode.db"
```

Ścieżka powyżej jest przykładem, a nie potwierdzeniem lokalizacji Twojej bazy. Można wskazać kilka baz, powtarzając argument.

Dla **potwierdzonej bieżącej aktywności** potrzebny jest również adres HTTP już działającej instancji OpenCode. Dodaj go w sekcji „Połączenie z istniejącym OpenCode”. Domyślny kandydat to `http://127.0.0.1:4096`, ale port aplikacji desktopowej może być inny. Odczyt samej bazy daje historię, nie pewność, że proces nadal pracuje.

Panel nie uruchamia drugiego serwera OpenCode, nie skanuje portów i nie wysyła poleceń do agentów. Obsługuje wyłącznie jawnie wskazane adresy loopback. Jeśli serwer wymaga Basic Auth, przekaż `OPENCODE_SERVER_PASSWORD` i opcjonalne `OPENCODE_SERVER_USERNAME` w środowisku procesu panelu. Hasła nie wpisuje się w adres URL ani w czacie.

Czytnik rozpoznaje dostępne kolumny SQLite, zamiast zakładać jedną sztywną wersję schematu. Zmiana formatu przez przyszłą wersję OpenCode może jednak wymagać aktualizacji adaptera; błąd pojawi się w sekcji zdrowia źródeł.

## Podłączenie logów Codexa

Domyślnie używany jest lokalny katalog `.codex`, z uwzględnieniem `CODEX_HOME`, gdy został ustawiony. Niestandardowy katalog można wskazać przez `--codex-home` albo konfigurację:

```powershell
py -3 opencode_dashboard.py --open --codex-home "C:\Users\Matt\.codex"
```

Odczyt jest przyrostowy i obsługuje niedokończone linie JSONL, obrót logu, częściowe znaki UTF-8 oraz uszkodzone rekordy. Najnowsze logi wybierane są do ustawionego limitu; zakres i pominięcia są raportowane.

Logi lokalne nie zapewniają automatycznego dostępu do zadań wykonywanych wyłącznie w chmurze. Nie są też sondą żywotności procesu. Zdarzenie zakończenia tury oznacza zakończenie tury, nie dowód, że zadanie przeszło testy.

## Codex jako klient MCP panelu

Uruchom panel. W **Źródła i MCP → Codex · lokalnie** skopiuj wygenerowany fragment TOML do konfiguracji MCP Codexa. Fragment ma już właściwą ścieżkę do aktualnego pliku i katalogu stanu.

Przykład struktury:

```toml
[mcp_servers.mission_control]
command = "C:\\Path\\To\\Python\\python.exe"
args = ["D:\\MissionControl\\opencode_dashboard.py", "--mcp-stdio", "--state-dir", "C:\\Users\\Matt\\.opencode-mission-control"]
startup_timeout_sec = 20
tool_timeout_sec = 30
```

Most stdio nie tworzy drugiego obserwatora. Odczytuje jego port z `runtime.json` i osobny lokalny token MCP. Panel musi być uruchomiony. Do stdio używany jest konsolowy `python.exe`, również wtedy, gdy sam interfejs uruchomiono przez `pythonw.exe`.

Dostępny jest też wariant HTTP, generowany w interfejsie. Wymaga `MISSION_CONTROL_MCP_TOKEN` w środowisku Codexa. Nie publikuj tej wartości ani nie wysyłaj jej do rozmowy.

## ChatGPT jako zdalny klient MCP

**Ta część wymaga konfiguracji po Twojej stronie. Nie jest automatycznie połączona z kontem ChatGPT.**

1. Skonfiguruj stabilny tunel lub reverse proxy HTTPS do lokalnego portu panelu. Aplikacja nie instaluje ani nie otwiera tunelu.
2. W sekcji MCP ustaw `public_origin`, na przykład `https://mc.twoja-domena.pl`, bez ścieżki. Podaj dokładne adresy callback OAuth, jakie akceptuje konfiguracja klienta ChatGPT. Domyślnie uwzględniono oficjalny stały callback `https://chatgpt.com/connector_platform_oauth_redirect`; przy innym wariancie klienta trzeba użyć pokazanego przez niego adresu.
3. Utwórz połączenie ChatGPT z `https://twój-host/mcp`, wybierając OAuth i dynamiczną rejestrację klienta DCR. Nie wpisuj wymyślonych statycznych danych klienta.
4. Na stronie autoryzacji **tego obserwatora** wklej klucz parowania z lokalnego panelu. Klucza nie przekazuje się w czacie ani obcemu serwerowi MCP.

Implementacja zawiera metadata serwera i zasobu, DCR z listą callbacków, PKCE S256, kody jednorazowe, powiązanie tokenu z zasobem, odświeżanie z rotacją i unieważnianie. Dostęp zdalny nie obejmuje właścicielskich ustawień i zatrzymywania agentów. Token dostępu wygasa po godzinie; restart obserwatora unieważnia wydane tokeny, ale zachowuje rejestracje klientów.

To lokalne narzędzie dla jednego właściciela, a nie niezależnie audytowany system tożsamości dla publicznej usługi wieloużytkownikowej. Przed wystawieniem do Internetu użyj prawidłowo skonfigurowanej warstwy TLS, ograniczenia ruchu i zabezpieczonego pośrednika. Nie wyłączaj kontroli Origin/Host, aby „naprawić” tunel. Proxy powinno przekazywać zaakceptowany Host, bez przepisywania autoryzacji.

Połączenie ChatGPT nie zostało przetestowane end-to-end z Twoim kontem. Testy lokalne sprawdziły protokół MCP i przepływ OAuth na kontrolowanym kliencie.

## Narzędzia MCP

Domyślnie dostępnych jest dziesięć narzędzi: `mission_overview`, `list_agents`, `agent_details`, `list_projects`, `timeline`, `model_comparison`, `alerts`, `sources`, `search`, `fetch`. Po włączeniu raportowania dochodzi `report_event`.

Przykładowa instrukcja dla klienta:

> Sprawdź mission_overview. Następnie list_agents. Oddziel aktywność potwierdzoną od historycznej i zgłoszonej. Podaj projekt, rzeczywisty model i ostatnie narzędzie. Nie licz definicji agentów jako uruchomionych workerów.

## Raportowanie „to zadanie przyszło z ChatGPT”

Włącz `enable_reporting` przełącznikiem w integracjach. Klient musi odświeżyć listę narzędzi i uzyskać zakres zapisu raportów. Następnie może wywołać `report_event` z identyfikatorem istniejącej sesji zwróconym przez `list_agents`:

```json
{
  "event_id": "unikalny-id-zdarzenia",
  "source": "chatgpt",
  "session_id": "opencode:ses_TUTAJ_PRAWDZIWE_ID",
  "task": "Przegląd regresji panelu",
  "task_group": "dashboard-ui-round-1",
  "state": "running"
}
```

Raport jest deklaracją klienta. Nie zastępuje stanu API, nie nalicza dodatkowych tokenów i nie uruchamia pracy. Ponowienie identycznego `event_id` nie dubluje zdarzenia; zmiana treści pod tym samym ID jest odrzucana. Dla kolejnego zdarzenia użyj nowego ID.

Nie da się z tego mostu automatycznie zobaczyć wszystkich rozmów ChatGPT ani wywołań do innych serwerów MCP. Monitorowane są własne źródła i wywołania przechodzące przez ten most. Inne orkiestratory muszą przesyłać raporty świadomie.

## Znaczenie stanów i liczb

`verified` oznacza świeży status odczytany z API OpenCode. `recorded` oznacza zapisany stan lub znacznik w danych źródłowych. `reported` oznacza deklarację klienta. `unknown` i `stale` sygnalizują brak wystarczającego dowodu lub jego utratę świeżości. Sam niedawny timestamp nie tworzy potwierdzonego RUNNING. Również stan w inspektorze traci ważność po przekroczeniu okna świeżości.

Rodzic zapisany w sesji nie wystarcza do rozpoznania subagenta. Wywołanie narzędzia delegującego lub jawna informacja o uruchomieniu dziecka daje mocniejszy dowód; fork jest osobną relacją. Graf nie dopisuje fikcyjnych ról CTO/TL na podstawie samej nazwy.

Cache i reasoning są normalizowane zależnie od źródła. Nie sumujemy jednocześnie zapisów wiadomości i odpowiadających im step-finish. Narastające liczniki Codexa nie są doliczane od nowa przy każdym odczycie. Router JSONL pozostaje osobnym rejestrem, bo jego requesty mogą pokrywać się z natywnymi sesjami.

Czas od utworzenia sesji nie jest czasem pracy modelu. W ocenie można wpisać rzeczywiście zmierzony czas, rezultat testów, grupę zadania i liczbę poprawek. Brak danych pozostaje brakiem danych. Testy nie są uznawane za zaliczone tylko dlatego, że agent wywołał komendę o nazwie `test`.

Koszt pochodzi z zapisanych danych albo z jawnie skonfigurowanych cen. Waluta cennika to USD za milion tokenów; nie ma wbudowanych zgadywanych cen. Tabela plików pokazuje wyraźnie oznaczony równy podział kosztu tokenowego sesji między odnotowane pliki. Nie przedstawiamy go jako pomiaru faktycznego kosztu każdej edycji. Widok Git pokazuje kontekst commitów, ale nie wycenia ich za pomocą przypadkowego okna czasowego.

## Alerty i granice interwencji

W `expected_models` ustaw dokładny identyfikator modelu dla nazwy agenta albo canonical ID sesji. To pozwala wykryć użycie droższego lub po prostu innego modelu. `allowed_paths` mapuje nazwę agenta na dozwolone foldery edycji. Reguły tylko alarmują; nie przełączają modeli i nie cofają edycji.

Przerwanie agenta OpenCode jest domyślnie wyłączone. Po ustawieniu `allow_abort: true` właściciel może użyć przycisku przy sesji znanej podłączonemu API, ale musi wpisać jej dokładny natywny ID. Zwykły token MCP i token OAuth nie mają tej możliwości. Panel nie zapewnia odpowiednika abort dla lokalnych logów Codexa.

## Skanowanie, retencja i prywatność

Skanuj wybrane foldery, np. własny katalog projektów, zamiast całego dysku. Skan ma ograniczoną głębokość, limit 6000 folderów i 12 sekund oraz nie podąża za dowiązaniami. Zaznaczenie wyników i osobne zatwierdzenie dopiero dodaje źródła. Nie przeszukuje plików `auth.json` ani `.env`.

Aplikacja czyta bazy OpenCode w trybie read-only. Nie zmienia repozytoriów, logów Codexa ani konfiguracji OpenCode. Własny stan przechowuje w `~/.opencode-mission-control`: `config.json`, `observer.sqlite`, `runtime.json`, logach oraz plikach `owner.token`, `mcp.token`, `pairing.key`. Te trzy klucze są poufne. Nie umieszczaj katalogu stanu w publicznym repozytorium ani synchronizacji udostępnionej innym osobom.

Domyślnie odczytywanych jest do 1000 sesji z każdej bazy i 400 najnowszych logów Codexa. Własna historia zdarzeń jest ograniczona retencją 90 dni i limitem rekordów. Ograniczenie źródła jest pokazywane w panelu. Duża baza może wymagać zmniejszenia okna albo dłuższego interwału odczytu.

Prompty i wyniki narzędzi mogą zawierać dane wrażliwe. Redakcja znanych wzorców kluczy jest tylko pomocą, nie gwarancją usunięcia wszystkich sekretów. `show_prompts: false` ukrywa prompty i treści definicji, ale nie gwarantuje bezpiecznej publikacji wyników narzędzi. Uprawnienia Windows zależą także od ACL katalogu i konta użytkownika.

## Weryfikacja tej wersji

W środowisku testowym Linux/Python wykonano **91 testów regresyjnych**, **10 wbudowanych testów kontrolnych** i **25 sprawdzeń interfejsu w Chromium**. Używano wyłącznie sztucznych baz, logów i zadań. Sprawdzono m.in. HTTP/MCP, OAuth/PKCE, zakresy dostępu, cache i tokeny, forki, niepełne logi, zapis ocen, skaner, eksport, wszystkie widoki i układ mobilny.

Przeglądarka testowa miała zablokowaną nawigację sieciową przez politykę środowiska. W testach UI wstrzyknięto dostarczony HTML/CSS/JS i połączono fetch z rzeczywistym lokalnym serwerem fixture przez adapter testowy. Polityk przeglądarki nie zmieniano. Zwykłe żądania HTTP i MCP zostały osobno sprawdzone zestawem regresyjnym.

Nie przeprowadzono rzeczywistego uruchomienia na Twoim Windows, na Twojej bazie ani end-to-end z Twoim kontem ChatGPT/Codex. Launcher Windows jest przygotowany, lecz nie był uruchomiony na Windows w tym środowisku. To nie jest niezależny audyt bezpieczeństwa.

Do odtworzenia testów standardowej biblioteki:

```powershell
py -3 opencode_dashboard.py --self-test
py -3 test_mission_control.py
```

Test uprawnień POSIX jest pomijany na Windows; test dowiązań pomija się, jeśli ich tworzenie jest niedozwolone. Nie są potrzebne dane użytkownika. Szczegóły wykonania znajdują się w `TEST_REPORT.json`.

## Źródła dokumentacji integracji

Dokumentacja użyta przy implementacji, sprawdzona 16 września 2026:

* OpenCode server: https://opencode.ai/docs/server/
* Codex MCP: https://developers.openai.com/codex/mcp
* OpenAI authentication: https://developers.openai.com/plugins/build/auth
* MCP Streamable HTTP: https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
* MCP tools: https://modelcontextprotocol.io/specification/2025-11-25/server/tools

Serwer jawnie negocjuje wersje MCP `2025-11-25` i `2025-06-18`. Nie deklaruje automatycznej zgodności ze wszystkimi przyszłymi wersjami protokołu. Format lokalnych logów może zmieniać się niezależnie od protokołu MCP.

## Powrót do poprzedniej wersji

Kopia przesłanego oryginału jest w `backup/opencode_dashboard_original.py`. W razie potrzeby zatrzymaj nowy obserwator, zachowaj jego katalog stanu i zastąp główny plik kopią. Źródłowe dane OpenCode i Codexa nie wymagają przywracania, ponieważ ta wersja ich nie nadpisuje.
