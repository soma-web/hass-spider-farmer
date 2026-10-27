# Spider Farmer → Home Assistant Integration – Plan

> Lebendes Dokument. Stand: 2026-10-27
> Quelle der Protokoll-Infos: `reverse-spider-farmer/` (03-api-reference.md, 04-mqtt-control.md, client/)
> Repo: https://github.com/somesoma/spider-farmer-hass · Domain: `spider_farmer`

## Status

- [x] Reverse-Engineering-Repo geklont (`reverse-spider-farmer/`, per `.gitignore` ausgeschlossen)
- [x] Doku gelesen und Protokoll zusammengefasst
- [x] Offene Fragen geklärt
- [x] Architektur festgelegt
- [x] Meilensteine definiert
- [x] M0 – Projekt-Setup (lokal; offen: GitHub-Repo anlegen, WSL2)
- [ ] **In Arbeit:** M1 – Library + CLI fertig (20 Tests grün), Hardware-Verifikation steht aus

---

## 1. Was wir über das Protokoll wissen

### REST (Cloud)
- `POST https://api.spider-farmer.com/api/android/<module>/<action>/v2`
- Body: JSON → AES-128-CBC/PKCS7 (statischer Key `Meizhi1234567890`, IV `1234567890123456`) → Base64
- Header `systemdata` (Klartext-JSON) mit `token`, `reqId`, `timestamp`, `appVersion` …
- Antwort: `{"code":"000","msg":"success","data":…}`
- Region: `getBelongingUrlInfo` liefert z. B. `EU` / `https://spiderfarmer.eu` (Auswirkung auf API-Basis unklar)

### Login
1. `ulogin/getEmailCode/v2` `{email, isLogin:1}` → OTP per Mail
2. `ulogin/mailLogin/v2` `{email, loginMethod:2, otpCode}` → `token`, `userId`, `mqttName`, `mqttPwd`
- Kein Passwort-Login dokumentiert → Config Flow in 2 Schritten (E-Mail, dann Code)
- Token-Lebensdauer unbekannt → Reauth-Flow

### Geräte-Discovery
- `udm/getUserRooms/v2` → Räume
- `udm/getDeviceList/v2` `{belonginRoomId, userId}` → Geräte inkl. `productType`, `deviceSerialnum`, `deviceInfo` (JSON-String, doppelt parsen)
- `udm/getSocketCustomizeName/v2` → eigene Namen der Steckdosen

### Realtime + Steuerung (MQTT, Cloud)
- `mqtts://sf.mqtt.spider-farmer.com:8883`, self-signed Cert, Login `mqttName`/`mqttPwd`
- Topics: `<prefix>/API/UP/<serial>` (Gerät → App), `<prefix>/API/DOWN/<serial>` (App → Gerät), `SF/Offline/<userId>`
  - `<prefix>` = `productType` mit `-` → `/` (z. B. `SF/GGS/PS5`)
- Abfragen (auf DOWN): `getDevSta`, `getSysSta`, `getConfigFile`, `getDevOpLog`
- Steuern: `setConfigField` mit `keyPath:["device",<comp>]` + **komplettem** Sub-Config-Objekt (`mOnOff`, `mLevel`, …)
  - Ablauf: `getConfigFile` → Feld ändern → ganzes Objekt senden
  - Bestätigt: blower on/off/level, fan on/off. **Nicht bestätigt:** light, outlet

### Datenpunkte (aus `getDevSta`)
| Komponente | Felder | HA-Entity |
|---|---|---|
| sensor | temp, humi, vpd, ppfd, co2, tempSoil, humiSoil, ECSoil | `sensor` |
| outlet | psmode, O1–O5 `{on, modeType}` | `switch` je Steckdose |
| light | level, modeType | `light` (Helligkeit) |
| blower | on, level (0–100?) | `fan` mit Prozent |
| fan | on, level (1–10?) | `fan` mit Stufen |
| sys (`getSysSta`) | ver, hwver, wifi.rssi, upTime, mqtt.isConnect | Diagnose-`sensor` |

### Erkenntnisse aus dem Hardware-Test (2026-10-27, GGS PS5, FW 3.14)
- ✅ REST-Login per OTP, Region (`EU`, `https://spiderfarmer.eu` – API funktioniert trotzdem über `api.spider-farmer.com`), Räume (Key `id`), Geräte
- ✅ `deviceInfo` aus der REST-Geräteliste ist **veraltet** (Stand Mai 2025) → Live-Werte nur über MQTT
- ✅ `getSocketCustomizeName` liefert `null` (keine eigenen Namen vergeben, oder Payload falsch)
- ✅ MQTT-Login + `getSysSta`, `getDevSta`, `getConfigFile` antworten sofort
- `getDevSta` enthält zusätzlich `sensors[]` (je Bodensensor eine ID, z. B. `AA01`, plus `avg`) und `oplogLast`/`alarmLast`
- `getConfigFile` → `data.configFile` mit `device.{light,fan,blower}`, `outlet.{O1..O5}`, `target.{dayTime,temp,humi,co2}`
  - `keyPath` ist der Pfad in `configFile` → Steckdosen vermutlich `["outlet","O3"]` (noch zu bestätigen)
  - `modeType` z. B. Licht 1 (Zeitplan), Steckdose O1 3 (Zyklus), viele 0 (manuell?)
- ✅ Historie `getDeviceTHPData`: Zeitbereich und `addTime` in **UTC**, Werte als Strings, 5-Min-Raster
- Antworten enthalten `pcode`, `UTC`, `code: 200`
- ✅ **Steuerung bestätigt:**
  - Umluft: `keyPath ["device","fan"]`, `mLevel` 2 → 3 → 2
  - Steckdose: `keyPath ["outlet","O3"]`, Params `{"O3": {…komplett…, "mOnOff": 1}}`, an → aus
  - Das Gerät bestätigt mit `{"method":"setConfigField","msgId":<gleich>,"code":200,"msg":"ok"}`
  - Danach **pusht** es von selbst `getDevSta` (ohne `msgId`) und `getSysSta` → Zustand ist sofort aktuell
  - Lampe absichtlich nicht getestet (Dunkelphase), Form ist aber dieselbe (`["device","light"]`, `mOnOff`/`mLevel`)
- ⚠️ **Login aus HA/CLI meldet die Handy-App ab** (ein Token pro Konto). Folgen:
  - Im README deutlich warnen; Empfehlung: **zweites Spider-Farmer-Konto** für HA anlegen und das Gerät damit teilen (falls die App Teilen unterstützt – prüfen)
  - Umgekehrt meldet ein neuer App-Login vermutlich HA ab → Reauth-Flow muss sauber funktionieren
  - ✅ Geprüft: Neuer App-Login macht den REST-Token ungültig (`code "102"`, „The token is registered remotely.“), **MQTT läuft aber weiter** – bestehende Verbindung bleibt, und ein neuer MQTT-Login mit den alten `mqttName`/`mqttPwd` funktioniert ebenfalls
  - Geräte teilen mit einem Zweitkonto: **von der App nicht unterstützt**
- `getConfigFile` enthält außerdem `system` (buzzer, 24h), `alarm` (Min/Max-Grenzen je Sensor), `calibration`
- Umluft: App zeigt Stärke 1–10 (`mLevel`) und Oszillation 1–10 (vermutlich `shakeLevel`, noch zu bestätigen); `natural` = Naturwind?
- ✅ **Push bestätigt:** Das Gerät sendet ungefragt `getDevSta` alle ~6 s und `getSysSta` alle ~10 s (beobachtet über 4 Min.). Ob das dauerhaft so ist oder nur nach einer Anfrage für eine Weile, ist offen → HA fragt sicherheitshalber alle 60 s selbst nach
- Die App fragt zusätzlich `getGGSDev` ab (Inhalt noch unbekannt, evtl. angeschlossene Zusatzgeräte) und `getDevOpLog`

## 2. Entscheidungen

- **D1 – Architektur:** Native Custom Integration `custom_components/spider_farmer`. REST-API für Login, Geräteliste, Namen, Historie; Cloud-MQTT für Live-Status (Push) und Steuerung. Alles direkt aus HA, kein Zusatzdienst. `iot_class: cloud_push`.
- **D2 – MVP:** Alle Sensoren + An/Aus/Stufe für Steckdosen O1–O5, Lampe, Abluft, Umluft. Modi (`modeType`, Zeitplan/Zyklus) nicht im MVP.
- **D3 – Verteilung:** Öffentliches GitHub-Repo `somesoma/spider-farmer-hass`, HACS-kompatibel (`hacs.json`, Releases, README, HACS- und hassfest-Validierung per GitHub Action).
- **D4 – Auth:** Config Flow E-Mail → OTP; bei ungültigem Token Reauth-Flow mit neuem Code. Gespeichert werden `token`, `userId`, `mqttName`, `mqttPwd`.
- **D5 – Entwicklung:** Windows-venv für Code + Unit-Tests; HA-Core zum End-to-End-Test in **WSL2** (HA-Core läuft unter Windows nicht offiziell). Python-Version wie die aktuelle HA-Version.
- **D6 – Entities:** Lampe = `light` (0–100 %), Abluft = `fan` mit Prozent, Umluft = `fan` mit 10 Stufen (`mLevel` 1–10) + `number` für Oszillation 1–10, Steckdosen = `switch` (Namen aus `getSocketCustomizeName`), Messwerte = `sensor`, Online = `binary_sensor`, WLAN/Firmware/Uptime = Diagnose-`sensor`.
- **D7 – Schalten im Auto-Modus:** Gleiche Payload wie die App bei manueller Bedienung. Verhalten an der Hardware prüfen.
- **D8 – Historie:** Cloud-Historie (`dr/getDeviceTHPData/v2`, 5-Min-Samples) als importierte Statistik beim Einrichten; später Lücken nach Ausfällen füllen.
- **D9 – Code-Struktur:** Protokoll-Code eingebettet als Unterpaket `custom_components/spider_farmer/sfcloud/` **ohne HA-Imports** → unter Windows testbar, später als PyPI-Paket auslagerbar. Innerhalb von `sfcloud` nur relative Imports; Tests/CLI importieren es als Top-Level-Paket `sfcloud` (sonst würde `spider_farmer/__init__.py` HA nachladen).
- **D10 – Transport:** Cloud-only. Lokale Steuerung (BLE/LAN) ist ein späteres, eigenes Thema.
- **D11 – Koexistenz mit der App:** HA arbeitet im Betrieb **nur über MQTT**. REST wird nur beim Einrichten gebraucht (Login, Geräteliste, Steckdosennamen) und für den Historie-Import. Die Geräteliste wird im Config Entry gespeichert. Folge: Einmal in HA einloggen (App wird dabei abgemeldet), danach wieder in der App einloggen – HA läuft weiter. Ein ungültiger REST-Token (`102`) löst **keinen** Reauth aus, sondern nur, wenn er wirklich gebraucht wird (z. B. Historie, neue Geräte suchen); Reauth zwingend nur, wenn der MQTT-Login abgelehnt wird.

## 3. Geplante Struktur

```
spider-farmer-hass/
├─ custom_components/spider_farmer/
│  ├─ __init__.py          Setup, Coordinator starten
│  ├─ manifest.json        domain, iot_class cloud_push, requirements
│  ├─ config_flow.py       E-Mail → OTP → fertig; Reauth
│  ├─ coordinator.py       hält Gerätestatus, verteilt MQTT-Push an Entities
│  ├─ entity.py            Basis-Entity, DeviceInfo
│  ├─ sensor.py / binary_sensor.py / switch.py / light.py / fan.py
│  ├─ history.py           Import der Cloud-Historie in Statistiken
│  ├─ diagnostics.py       Diagnose-Download (Secrets geschwärzt)
│  ├─ strings.json, translations/{de,en}.json
│  └─ sfcloud/             Protokoll-Library (ohne HA)
│     ├─ crypto.py         AES-Body-Cipher
│     ├─ rest.py           REST-Client (aiohttp)
│     ├─ mqtt.py           Cloud-MQTT-Client (aiomqtt/paho), Status + setConfigField
│     └─ models.py         Device, DeviceState, Config
├─ scripts/sf_cli.py       CLI: login, devices, status, set … (Hardware-Tests)
├─ tests/
├─ hacs.json, README.md, LICENSE
└─ .github/workflows/      hassfest, HACS-Validierung, Tests
```

## 4. Meilensteine

### M0 – Projekt-Setup
- [x] `git init` (Branch `main`), Remote `somesoma/spider-farmer-hass`, `.gitignore` (inkl. `reverse-spider-farmer/`, venv, Secrets)
- [ ] GitHub-Repo `somesoma/spider-farmer-hass` existiert noch nicht → anlegen, dann erster Push
- [x] Windows-venv `.venv` (Python 3.15.1), `pyproject.toml` (ruff, pytest) – `pytest` + `ruff check` grün
- [x] Grundgerüst `custom_components/spider_farmer` + `manifest.json` + `hacs.json` + README + CI-Workflow (hassfest, HACS, pytest)
  - `config_flow` im Manifest vorerst `false`, wird in M2 auf `true` gesetzt
- [ ] WSL2: **noch nicht installiert** (`wsl --install` als Admin + Neustart), danach HA-Core-venv, `custom_components` per Symlink auf das Repo. Wird erst für M2 gebraucht.

### M1 – Protokoll-Library + CLI (Windows)
- [x] `crypto.py` (+ `exceptions.py`, `models.py`) mit Tests
- [x] `rest.py`: Login (OTP), Region, Rooms, Devices (über alle Räume), Socket-Namen, Historie, `call_raw` für beliebige Endpunkte
- [x] `mqtt.py`: eine Verbindung für alle Geräte, Auto-Reconnect, eindeutige Client-ID, State-Cache, `request`/`query` (wartet auf Antwort), `set_component` (Merge in komplette Sub-Config)
- [x] CLI `scripts/sf_cli.py`: `login`, `devices [--raw]`, `status`, `watch`, `set`, `history`, `call` (Session in `sf.session.json`, git-ignored)
- [x] Room-ID-Key (`id`) und Verschachtelung von `getConfigFile` (`configFile.device/outlet/target`) geklärt → Library auf beliebige `keyPath`s umgestellt (`set_config`)
- [ ] Fehlercodes bei ungültigem Token (`AUTH_ERROR_CODES`) – erst sichtbar, wenn ein Token abläuft
- [ ] **Hardware-Verifikation:**
  - [x] Outlet-Steuerung bestätigt (O3), Light gleiche Form (nicht geschaltet)
  - [ ] Level-Bereiche Blower/Fan/Light
  - [x] Parallel-Betrieb mit der App: **App wird beim Login abgemeldet** (siehe Erkenntnisse)
  - [ ] Pusht das Gerät von selbst, oder muss `getDevSta` gepollt werden?
  - [x] Region EU: `api.spider-farmer.com` funktioniert

### M2 – HA-Grundgerüst (nur lesen)
- [ ] Config Flow E-Mail → OTP, Reauth
- [ ] Coordinator mit MQTT-Push + Fallback-Poll
- [ ] Device Registry (Serial, Modell, Firmware)
- [ ] `sensor`, `binary_sensor`, Diagnose-Sensoren
- [ ] Übersetzungen de/en

### M3 – Steuerung
- [ ] Config-Cache (`getConfigFile`) + Merge für `setConfigField`
- [ ] `switch` (O1–O5), `light`, `fan` (Abluft Prozent, Umluft Stufen)
- [ ] Zustand nach Befehl über `getDevSta` bestätigen

### M4 – Historie
- [ ] Import `getDeviceTHPData` als Statistik beim Einrichten
- [ ] Optional: Lücken nach Ausfall nachladen

### M5 – Release
- [ ] `diagnostics.py` (Token/Passwort geschwärzt)
- [ ] README (Installation über HACS, Einrichtung, Hinweis „inoffiziell“)
- [ ] GitHub Actions: hassfest, HACS-Validierung, pytest
- [ ] Release v0.1.0

### Später
- Modi (Zeitplan/Zyklus/Auto) als `select`/`number`
- Alarme (`alarmLog`), Stromdaten (`getDevicePowerData`)
- Lokale Steuerung (BLE/LAN)

## 5. Risiken

- **Light/Outlet-Payload unbestätigt:** wird in M1 an der Hardware geklärt
- **Session-Konflikt mit der App (bestätigt, entschärft):** Login in HA wirft die App raus und umgekehrt; MQTT bleibt aber gültig → siehe D11. Offen: Ändert sich `mqttPwd` irgendwann (z. B. bei Passwort-/Konto-Änderung)?
- **Inoffizielle API:** Spider Farmer kann sie jederzeit ändern (App-Version im `systemdata`-Header)
- **Self-signed MQTT-Zertifikat:** TLS ohne Prüfung nötig, im README dokumentieren
