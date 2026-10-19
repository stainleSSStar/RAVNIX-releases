# RAVNIX — instalowanie programów i ręczne dodanie pulpitu

Poradnik dla **zainstalowanego na dysku RAVNIX 26.05**, w tym wydania
`v26.05-r24`. Polecenia działają w domyślnym shellu **Fish**. Potrzebujesz
internetu i swojego hasła do `sudo`. Nie wykonuj tych zmian w sesji live z USB:
tam dotyczą one uruchomionego obrazu, a nie systemu na dysku.

RAVNIX używa NixOS. Programy instaluje się przez Nix i konfigurację systemu;
nie przez `apt`, `pacman` ani pobieranie plików `.deb`/`.rpm`.

## Spis treści

- [Przygotowanie i ważne pliki](#przygotowanie-i-ważne-pliki)
- [Programy instalowane na stałe](#programy-instalowane-na-stałe)
- [Wyszukiwanie i uruchamianie tymczasowe](#wyszukiwanie-i-uruchamianie-tymczasowe)
- [Ręczna instalacja XFCE](#ręczna-instalacja-xfce)
- [Powrót do konsoli i odzyskiwanie systemu](#powrót-do-konsoli-i-odzyskiwanie-systemu)
- [Aktualizacje i rozwiązywanie problemów](#aktualizacje-i-rozwiązywanie-problemów)

## Przygotowanie i ważne pliki

Sprawdź połączenie:

```fish
nmcli device status
```

Jeżeli trzeba połączyć Wi-Fi, uruchom `nmtui`. Zrób kopię konfiguracji:

```fish
sudo cp -a /etc/nixos /etc/nixos.backup-(date +%Y%m%d-%H%M%S)
```

Najważniejsze pliki:

| Plik | Przeznaczenie |
| --- | --- |
| `/etc/nixos/host.nix` | Ustawienia tego komputera i miejsce importowania własnych modułów. |
| `/etc/nixos/hardware-configuration.nix` | Konfiguracja wykrytego sprzętu i systemów plików. |
| `/etc/nixos/modules/base.nix` | Wspólna, tekstowa baza RAVNIX. |
| `/etc/nixos/flake.nix` i `flake.lock` | Definicja systemu `ravnix` i przypięta wersja Nixpkgs. |

W RAVNIX przebudowa przez flake korzysta z `host.nix`. Samo dopisanie ustawień
do `configuration.nix` **nie zmieni** systemu budowanego poniższymi poleceniami.
Zostaw istniejące ustawienia dysku, GRUB, użytkownika i nazwy komputera.
Nie zastępuj całego `host.nix` krótkimi przykładami z poradnika.

W Nano: **Ctrl+O**, Enter zapisuje plik, **Ctrl+X** zamyka edytor.

## Programy instalowane na stałe

### 1. Utwórz listę swoich programów

```fish
sudo nano /etc/nixos/packages.nix
```

Wklej cały poniższy moduł:

```nix
{ pkgs, ... }: {
  environment.systemPackages = with pkgs; [
    htop
    git
    ripgrep
    wget
  ];
}
```

Nazwy w liście to atrybuty pakietów Nixpkgs. Na przykład pakiet `ripgrep`
udostępnia polecenie `rg`. Lista dodaje programy do narzędzi już obecnych w bazie.

### 2. Zaimportuj plik

```fish
sudo nano /etc/nixos/host.nix
```

Bezpośrednio po początkowym `{ ... }: {` dodaj:

```nix
  imports = [ ./packages.nix ];
```

Jeśli `imports` już istnieje, dopisz `./packages.nix` do tej samej listy.
Nie twórz drugiego pola `imports` w tym samym module. Pozostałe ustawienia
zostają w pliku.

### 3. Zbuduj i zastosuj

```fish
sudo nixos-rebuild switch --flake path:/etc/nixos#ravnix
```

Po pomyślnym zakończeniu możesz uruchomić `htop`, `git --version` lub `rg --version`.
Programy pozostają dostępne po restarcie dla wszystkich użytkowników. Nie trzeba
ponownie instalować systemu ani wykonywać `git add`: używamy jawnego `path:`.

### Dodawanie i usuwanie kolejnych programów

Edytuj listę w `packages.nix`, dodając lub usuwając nazwę, a następnie wykonaj
ponownie polecenie `nixos-rebuild switch` powyżej. Usunięcie z własnej listy
nie wyłącza programu wymaganego przez inny moduł systemu.

Starsze generacje i ich pakiety mogą nadal zajmować miejsce w `/nix/store`.
To umożliwia rollback. Nie usuwaj ręcznie plików z `/nix/store`.

## Wyszukiwanie i uruchamianie tymczasowe

Wydanie `v26.05-r24` przypina Nixpkgs do rewizji
`26f4107e47e3ad0ffd0db220469ba83b6f6d96e8`. Poniższe przykłady używają dokładnie
tej rewizji, bez polegania na domyślnym rejestrze `nixpkgs`.

Wyszukanie `htop`:

```fish
nix search github:NixOS/nixpkgs/26f4107e47e3ad0ffd0db220469ba83b6f6d96e8 htop
```

Jednorazowe uruchomienie bez edytowania konfiguracji:

```fish
nix shell github:NixOS/nixpkgs/26f4107e47e3ad0ffd0db220469ba83b6f6d96e8#htop --command htop
```

Nie używaj `sudo` do tych dwóch poleceń. Po zamknięciu programu nie zostaje on
dodany do konfiguracji ani stałego profilu. Pobrane pliki mogą pozostać w magazynie
Nix. Dla programu potrzebnego na co dzień zastosuj metodę z `packages.nix`.

Po świadomej aktualizacji Nixpkgs używaj w takich poleceniach nowej rewizji
z `/etc/nixos/flake.lock`. Wyniki wyszukiwania na
[search.nixos.org/packages](https://search.nixos.org/packages) mogą dotyczyć
innej wersji niż przypięta w twoim systemie.

## Ręczna instalacja XFCE

Poniżej dodajemy **XFCE na X11, ekran logowania LightDM, dźwięk PipeWire
i przeglądarkę Firefox**. To opcjonalne rozszerzenie zainstalowanego systemu;
standardowe ISO RAVNIX pozostaje tekstowe. Pobieranie może obejmować kilka GB.

Samo dodanie pakietu pulpitu do `environment.systemPackages` nie uruchamia
potrzebnych usług. Użyj modułu poniżej.

### 1. Utwórz moduł pulpitu

```fish
sudo nano /etc/nixos/desktop.nix
```

Wklej cały moduł:

```nix
{ lib, pkgs, ... }: {
  # Baza RAVNIX ustawia tę opcję na false. Zwykłe true spowoduje konflikt.
  services.xserver.enable = lib.mkForce true;
  services.xserver.displayManager.lightdm.enable = true;
  services.xserver.desktopManager.xfce.enable = true;
  services.displayManager.defaultSession = "xfce";

  hardware.graphics.enable = true;
  services.libinput.enable = true;
  security.polkit.enable = true;
  services.udisks2.enable = true;

  # Profil minimalny wyłącza te integracje domyślnie.
  xdg.autostart.enable = true;
  xdg.icons.enable = true;
  xdg.mime.enable = true;
  xdg.sounds.enable = true;

  services.pulseaudio.enable = false;
  security.rtkit.enable = true;
  services.pipewire = {
    enable = true;
    alsa.enable = true;
    pulse.enable = true;
  };

  environment.systemPackages = with pkgs; [
    firefox
    pavucontrol
  ];
}
```

XFCE dostarcza m.in. panel, menedżer plików i terminal. Przy włączonym już
NetworkManagerze jego moduł dodaje także aplet sieciowy. `pavucontrol` służy
do wyboru urządzeń i regulacji dźwięku.

### 2. Dodaj import

W `/etc/nixos/host.nix` rozbuduj istniejącą listę:

```nix
  imports = [
    ./packages.nix
    ./desktop.nix
  ];
```

Jeśli pominąłeś sekcję o programach i nie utworzyłeś `packages.nix`, dodaj tylko
`./desktop.nix`. Zachowaj ewentualne inne importy.

### 3. Sprawdź budowanie, a potem włącz pulpit przy następnym starcie

```fish
sudo nixos-rebuild build --flake path:/etc/nixos#ravnix
```

Jeśli polecenie zakończy się błędem, popraw go przed dalszymi krokami.
Samo `build` nie przełącza działającego systemu. Po sukcesie:

```fish
sudo nixos-rebuild boot --flake path:/etc/nixos#ravnix
sudo reboot
```

`boot` przygotowuje nową generację do następnego uruchomienia. Po restarcie
powinien pojawić się LightDM. Wybierz sesję XFCE i zaloguj się swoim istniejącym
kontem oraz hasłem. Fish pozostaje domyślnym shellem; BIOS/UEFI i układ partycji
nie są zmieniane przez ten moduł.

### Opcjonalnie: polski język i klawiatura

Wewnątrz modułu `desktop.nix`, przed końcowym `}`, możesz dodać:

```nix
  i18n.defaultLocale = lib.mkForce "pl_PL.UTF-8";
  services.xserver.xkb.layout = "pl";
  console.keyMap = lib.mkForce "pl";
```

`mkForce` nadpisuje angielskie locale i amerykańską klawiaturę ustawione w bazie.
Polskie locale jest już dostępne w RAVNIX. Tłumaczenia zależą od programu;
nie wszystkie narzędzia będą po polsku. Zastosuj zmianę przez `nixos-rebuild boot`
i restart. W XFCE układ klawiatury możesz też zmieniać w ustawieniach klawiatury.

## Powrót do konsoli i odzyskiwanie systemu

### Trwałe usunięcie pulpitu

1. Przejdź na konsolę przez **Ctrl+Alt+F2** i zaloguj się.
2. W `/etc/nixos/host.nix` usuń z `imports` wpis `./desktop.nix`.
3. Zachowaj `./packages.nix`, jeśli chcesz pozostawić swoje programy.
4. Wykonaj:

```fish
sudo nixos-rebuild boot --flake path:/etc/nixos#ravnix
sudo reboot
```

System wróci do tekstowej bazy. Nie trzeba kasować samego pliku `desktop.nix`.
Jeśli polskie ustawienia miałyby pozostać po usunięciu pulpitu, przenieś je
do osobnego importowanego modułu, z argumentem `lib`, bez ustawienia X11.

### Gdy nowa konfiguracja nie działa

- Jeżeli system nie uruchamia się prawidłowo, wybierz poprzednią generację
  w menu GRUB. Przebudowa nie usuwa automatycznie wcześniejszych generacji.
- Jeżeli możesz zalogować się na konsoli, możesz cofnąć ostatnie przełączenie:

```fish
sudo nixos-rebuild switch --rollback
```

Rollback przełącza generację systemu, **nie przywraca treści plików w
`/etc/nixos`**. Popraw konfigurację lub przywróć odpowiednie pliki z kopii,
zanim ponownie wykonasz zwykłą przebudowę. Jeśli uruchomiłeś już starszą generację
z GRUB, nie cofaj jej ponownie w ciemno — popraw źródła i przebuduj system.

## Aktualizacje i rozwiązywanie problemów

- **Pakiet nie istnieje:** sprawdź nazwę w przypiętej rewizji Nixpkgs.
- **Błąd składni Nix:** sprawdź średniki, nawiasy i czy nie dodałeś drugi raz
  tego samego pola. Definicje w pliku muszą być wewnątrz zewnętrznych `{ ... }`.
- **Zmiana nie daje efektu:** sprawdź import w `host.nix` i użycie
  `--flake path:/etc/nixos#ravnix`, a nie samego `configuration.nix`.
- **Błąd pobierania:** sprawdź sieć i dostęp do `cache.nixos.org` oraz GitHub.
- **Brak ekranu logowania:** z konsoli sprawdź:

```fish
systemctl status display-manager
journalctl -b -u display-manager
lspci -nnk
```

Ten przykład korzysta ze standardowego stosu graficznego NixOS. Niektóre karty,
zwłaszcza wymagające własnościowego sterownika NVIDIA lub konfiguracji hybrydowej,
wymagają ustawień dopasowanych do konkretnego sprzętu. Nie instaluj sterownika
przez zewnętrzny instalator `.run`.

Zmiana listy pakietów **nie aktualizuje automatycznie Nixpkgs**. RAVNIX używa
przypiętej rewizji i nie ma automatycznych aktualizacji. Przy świadomej
aktualizacji zmień rewizję wejścia `nixpkgs` w `/etc/nixos/flake.nix`, odśwież
lockfile i ponownie zbuduj system. Samo `nix flake update` nie przeniesie wejścia
zawierającego konkretny hash na najnowszą wersję.

Opcje przykładów sprawdzono w źródłach Nixpkgs przypiętych przez `v26.05-r24`.
Testy wydania obejmują bazę tekstową w BIOS/UEFI; **ten dodatkowy pulpit nie był
testowany w uruchomionej maszynie ani na fizycznym GPU**.

## Dokumentacja źródłowa

- [Podręcznik NixOS](https://nixos.org/manual/nixos/stable/)
- [Instalowanie programów — oficjalna wiki NixOS](https://wiki.nixos.org/wiki/Adding_programs_to_PATH)
- [Wyszukiwanie pakietów — podręcznik Nix](https://nix.dev/manual/nix/latest/command-ref/new-cli/nix3-search.html)
- [XFCE — oficjalna wiki NixOS](https://wiki.nixos.org/wiki/Xfce)
- [PipeWire — oficjalna wiki NixOS](https://wiki.nixos.org/wiki/PipeWire)
- [Źródła Nixpkgs używane przez to wydanie](https://github.com/NixOS/nixpkgs/tree/26f4107e47e3ad0ffd0db220469ba83b6f6d96e8)

Dokumentacja „stable” i wiki zmieniają się z czasem. Dla istniejącej instalacji
decydująca jest jej własna wersja `flake.lock`.
