# My Podcasts - Home Assistant Dodatek

[![Angleščina](https://img.shields.io/badge/Jezik-Angleščina-blue)](README.md) [![Slovenščina](https://img.shields.io/badge/Jezik-Slovenščina-green)](README.sl.md)

My Podcasts je celovit Home Assistant dodatek za upravljanje in poslušanje podcastov v vašem pametnem domu. Omogoča popolno rešitev za upravljanje podcastov z večuporabniško podporo, avtomatskimi posodobitvami in brezhibno integracijo z Home Assistant medijskimi predvajalniki.

## 🎯 Ključne Funkcionalnosti

### 📡 Upravljanje Podcastov
- **Podpora RSS Virov**: Dodajanje podcastov preko RSS URL-jev z avtomatskim odkrivanjem epizod
- **Ročni RSS Uvoz**: Nalaganje XML datotek za dodajanje manjkajočih epizod iz arhivov
- **Avtomatske Posodobitve**: Načrtovane avtomatske posodobitve za vse podcaste
- **Pametno Sledenje Epizod**: Avtomatsko zaznavanje novih epizod s preprečevanjem podvojitev

### 👥 Večuporabniška Podpora
- **Individualni Uporabniški Računi**: Vsak uporabnik ima svojo knjižnico podcastov
- **Administratorski Nadzor**: Admin uporabniki lahko upravljajo vse podcaste in uporabnike
- **Javni/Zasebni Podcasti**: Delite podcaste z vsemi uporabniki ali jih obdržite zasebne
- **Centralni Uporabniški Način**: Posebni vmesnik za tablete/TV za skupne naprave

### 🎵 Funkcije Predvajanja
- **Vgrajen Brskalniški Predvajalnik**: Predvajajte epizode neposredno v spletnem vmesniku
- **Home Assistant Integracija**: Predvajajte na katerikoli povezani medijski predvajalnik
- **Sledenje Pozicije Predvajanja**: Nadaljujte epizode tam, kjer ste končali
- **Status Poslušanja**: Označite epizode kot poslušane z vizualnimi označevalci

### 🎨 Uporabniški Vmesnik
- **Odzivni Dizajn**: Optimiziran za namizne računalnike, tablete in mobilne naprave
- **Tablični Način**: Posebni vmesnik za skupne naprave (TV-ji, tableti)
- **Večjezična Podpora**: Angleški in slovenski vmesnik
- **Temna/Svetla Tema**: Samodejno prilagajanje vašim preferencam

### 🔧 Napredne Funkcije
- **Nadzor Vidnosti Podcastov**: Skrijte nezaželene podcaste iz vašega prikaza
- **Opisi Epizod**: Polni opisi epizod z razširljivim besedilom
- **Paginacija**: Učinkovito brskanje po velikih seznamih epizod
- **Iskanje in Filtriranje**: Enostavna navigacija po vaši knjižnici podcastov

## 🚀 Namestitev

### Metoda 1: Dodajanje Repozitorija (Priporočeno)

1. **Dodajte Repozitorij**
   - V Home Assistant pojdite na Nastavitve → Dodatki → Trgovina dodatkov
   - Kliknite tri pike v zgornjem desnem kotu in izberite "Repozitoriji"
   - Dodajte URL tega repozitorija in kliknite "Dodaj"
   - Osvežite stran

2. **Namestite Dodatek**
   - Poiščite "My Podcasts" v trgovini dodatkov
   - Kliknite na "My Podcasts" in nato "Namesti"
   - Počakajte, da se namestitev završi

3. **Zaženite Dodatek**
   - Po namestitvi kliknite "Zaženi"
   - Dodatek se bo prikazal v stranski vrstici Home Assistant

### Metoda 2: Ročna Namestitev

1. Kopirajte mapo `my_podcasts` v vašo Home Assistant `addons` mapo
2. Ponovno zaženite Home Assistant
3. Pojdite na Nastavitve → Dodatki → Trgovina dodatkov
4. Osvežite stran in namestite "My Podcasts"

## 📖 Vodič za Uporabo

### 🎯 Prvi Koraki

1. **Prva Prijava**: Prvi uporabnik, ki dostopa do dodatka, postane samodejno administrator
2. **Dodajte Prvi Podcast**: Vnesite ime podcasta in RSS URL
3. **Izberite Vidnost**: Odločite, ali naj bo podcast javen (viden vsem uporabnikom) ali zaseben
4. **Avtomatske Posodobitve**: Epizode se samodejno pridobijo in posodobijo

### 👤 Upravljanje Uporabnikov

#### Administratorski Uporabniki
- Lahko vidijo in upravljajo vse podcaste od vseh uporabnikov
- Lahko brišejo katerikoli podcast ali epizodo
- Lahko povišajo druge uporabnike v administratorski status
- Lahko nastavijo centralnega uporabnika za skupne naprave

#### Običajni Uporabniki
- Lahko dodajajo in upravljajo svoje podcaste
- Lahko vidijo javne podcaste od drugih uporabnikov
- Lahko skrijejo nezaželene javne podcaste
- Ne morejo brisati podcastov v lasti drugih

#### Centralni Uporabnik (Tablični Način)
- Posebni način za skupne naprave kot so tableti ali TV-ji
- Poenostavljen vmesnik, optimiziran za dotikove naprave
- Lahko preklaplja med knjižnicami podcastov različnih uporabnikov
- Popolno za družinsko uporabo ali javne prostore

### 🎵 Poslušanje Podcastov

#### Predvajanje v Brskalniku
- Kliknite "Predvajaj" na katerikoli epizodi za takojšnje predvajanje v brskalniku
- Pozicija predvajanja se samodejno shrani
- Nadaljujte s poslušanjem tam, kjer ste končali
- Epizode so samodejno označene kot poslušane, ko se končajo

#### Home Assistant Medijski Predvajalniki
- Izberite katerikoli konfiguriran medijski predvajalnik iz spustnega seznama
- Predvajanje se začne s shranjeno pozicijo (če je na voljo)
- Popolno za sisteme avdia za cel dom
- Podpira vse s Home Assistant kompatibilne medijske predvajalnike

### ⚙️ Konfiguracija Nastavitev

#### Avtomatske Posodobitve
- **Frekvenca**: Izberite dnevne ali tedenske posodobitve
- **Čas**: Nastavite želeni čas posodobitve (privzeto: 3:00)
- **Ročno Prepisovanje**: Vsaj kadarkoli prisilno posodobite vse podcaste

#### Izbira Medijskih Predvajalnikov
- Izberite katere Home Assistant medijske predvajalnike prikazati
- Podpira vse tipe: Sonos, Chromecast, AirPlay, itd.
- Izberite vse ali prilagodite vaše prednostne predvajalnike

#### Jezikovne Nastavitve
- Preklapljajte med angleščino in slovenščino
- Jezikovna preference se shrani po brskalniku
- Vpliva na vse elemente vmesnika in sporočila

#### Upravljanje Uporabnikov (Samo Administratorji)
- Nastavite centralnega uporabnika za dostop preko tableta/TV
- Povišajte uporabnike v administratorski status
- Preglejte informacije o registraciji uporabnikov
- Upravljajte dovolenja za večuporabniški dostop

### 📱 Tablični/TV Način

Dostopajte do za tablete optimiziranega vmesnika na `/tablet.html`:

1. **Izberite Uporabnika**: Izberite čigavo knjižnico podcastov prikazati
2. **Brskajte po Podcastih**: Mreža podcastov, prijazna za dotik
3. **Hiter Dostop**: Vidite najnovejše epizode in vsebino na pavzi
4. **Predvajanje Epizod**: Velike, enostavne za dotik kontrole predvajanja

Popolno za:
- Tablete v dnevnih sobah
- Kuhinjske zaslone
- Družinske skupne naprave
- Javne čakalnice

### 🔒 Vidnost Podcastov

#### Javni Podcasti
- Vidni vsem uporabnikom v sistemu
- Lahko jih posamezni uporabniki skrijejo (vendar ne izbrišejo)
- Popolni za družinske podcaste ali skupne interese
- Administratorji lahko brišejo javne podcaste

#### Zasebni Podcasti
- Vidni samo lastniku
- Jih ne morejo videti drugi uporabniki
- Lastnik jih lahko kadar koli spremeni v javne
- Popolni za osebne interese

#### Skriti Podcasti
- Javni podcasti, ki ste jih izbrali za skritje
- Ostanejo v sistemu, vendar se ne prikazujejo na vašem seznamu
- Lahko jih obnovite iz Nastavitve → Skriti Podcasti
- Uporabno za filtriranje nezaželene vsebine

## 🛠️ Tehnične Specifikacije

### Sistemske Zahteve
- Home Assistant OS, Supervised ali Container
- Minimum 512MB RAM
- 100MB prostora za shranjevanje dodatka
- Dodaten prostor za metadata epizod podcastov

### Podprte Arhitekture
- `amd64` (Intel/AMD 64-bit)
- `aarch64` (ARM 64-bit, Raspberry Pi 4)
- `armv7` (ARM 32-bit, Raspberry Pi 3)
- `armhf` (ARM 32-bit)
- `i386` (Intel 32-bit)

### Podatkovna Baza
- SQLite podatkovna baza za zanesljivo shranjevanje podatkov
- Avtomatske migracije podatkovne baze
- Podatki shranjeni v `/data/mypodcasts.db`
- Priporočene redne avtomatske varnostne kopije

### API Končne Točke
Dodatek zagotavlja RESTful API končne točke za:
- Upravljanje podcastov (`/api/podcasts`)
- Sledenje epizod (`/api/episodes`)
- Upravljanje uporabnikov (`/api/users`)
- Integracijo medijskih predvajalnikov (`/api/media_players`)
- Konfiguracijo nastavitev (`/api/settings`)

## 🔧 Možnosti Konfiguracije

```yaml
log_level: info          # Raven beleženja (debug, info, warning, error)
update_interval: 60      # Interval preverjanja posodobitev v minutah
db_file: "/data/mypodcasts.db"  # Lokacija datoteke podatkovne baze
safe_mode: false         # Omogoči varni način za odpravljanje napak
```

## 📋 Dnevnik Sprememb

Glejte [CHANGELOG.md](CHANGELOG.md) za podrobno zgodovino verzij in opombe o posodobitvah.

## 🆘 Odpravljanje Napak

### Pogoste Težave

**Epizode se ne posodabljajo**
- Preverite internetno povezavo
- Preverite, ali je RSS URL še vedno veljaven
- Preverite nastavitve avtomatskih posodobitev
- Poskusite z ročno posodobitvijo iz vmesnika

**Medijski predvajalniki se ne prikazujejo**
- Zagotovite, da je omogočen dostop do Home Assistant API
- Preverite, da so medijski predvajalniki odkrti v HA
- Osvežite konfiguracijo dodatka
- Preglejte dnevnike Home Assistant za napake

**Težave z zmogljivostjo**
- Razmislite o zmanjšanju frekvence posodobitev
- Preverite razpoložljive sistemske vire
- Preglejte velikost podatkovne baze in razmislite o čiščenju
- Zagotovite dovolj prostora za shranjevanje

**Težave z dostopom uporabnikov**
- Preverite avtentifikacijo Home Assistant
- Preverite uporabniška dovoljenja v HA
- Počistite predpomnilnik in piškotke brskalnika
- Preverite dnevnike dodatka za napake avtentifikacije

### Način Odpravljanja Napak

Omogočite beleženje napak z nastavitvijo `log_level: debug` v konfiguraciji:

1. Pojdite na Nastavitve → Dodatki → My Podcasts
2. Kliknite zavihek Konfiguracija
3. Nastavite `log_level` na `debug`
4. Ponovno zaženite dodatek
5. Preverite dnevnike za podrobne informacije

### Pridobivanje Pomoči

1. **Preverite Dnevnike**: Vedno najprej preverite dnevnike dodatka
2. **GitHub Težave**: Prijavite napake na projektni GitHub strani
3. **Home Assistant Skupnost**: Postavite vprašanja na HA forumih
4. **Dokumentacija**: Preglejte to README datoteko in dnevnik sprememb

## 🤝 Prispevanje

Dobrodošli so prispevki! Prosimo:

1. Naredite fork repozitorija
2. Ustvarite vejo za funkcionalnost
3. Naredite spremembe s testi
4. Pošljite pull request
5. Sledite standardom kodiranja in dokumentacije

### Razvojna Nastavitev

1. Klonirajte repozitorij
2. Nastavite razvojno okolje Home Assistant
3. Namestite dodatek v razvojnem načinu
4. Naredite spremembe in temeljito testirajte
5. Pošljite pull request s podrobnim opisom


## 📄 Licenca

Ta projekt je licenciran pod MIT licenco - glejte datoteko [LICENSE](LICENSE) za podrobnosti.

## 🙏 Zahvale

- Ekipi Home Assistant za odlično platformo
- Python skupnosti za neverjetne knjižnice
- RSS/Podcast ekosistemu za standardizirane vire
- Prispevatelja in testerjem, ki delajo ta projekt boljši

## 📞 Podpora

- **Dokumentacija**: Ta README in projektni wiki
- **Težave**: GitHub sledilnik težav
- **Skupnost**: Home Assistant forumi
- **Posodobitve**: Spremljajte repozitorij za obvestila

---

**Uživajte v vaši izkušnji poslušanja podcastov z Home Assistant! 🎧**