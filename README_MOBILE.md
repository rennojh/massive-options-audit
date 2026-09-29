# Massive Options Audit — Handy/GitHub

Dieser Test prüft den eingeschränkten Massive-Zugang für das BCI-CSP-Projekt.

## Einrichtung

1. In GitHub ein privates Repository anlegen.
2. `massive_options_audit.py` ins Hauptverzeichnis hochladen.
3. `massive-options-audit.yml` nach `.github/workflows/massive-options-audit.yml` hochladen.
4. GitHub: Settings → Secrets and variables → Actions → New repository secret
5. Name: `MASSIVE_API_KEY`
6. Wert: Massive-Test-API-Key
7. Actions → Massive Options Audit → Run workflow
8. AAPL stehen lassen und Run workflow drücken.
9. Lauf öffnen → Job `audit` → Schritt `Run Massive options audit`.

## Geprüft werden

- API/Auth
- Option Chain Snapshot
- Put-Optionen mit 7–45 Kalendertagen DTE
- Strike
- Expiration
- Bid
- Ask
- Open Interest
- Implied Volatility
- Delta

`PASS` bedeutet: Mindestens ein Kontrakt enthält alle sieben Pflichtfelder.

`PLAN/ENTITLEMENT restriction` bedeutet: Der Testzugang ist zu eingeschränkt. Das ist noch kein negatives Urteil über den $29-Starter-Tarif.

Der API-Key wird vom Skript nicht ausgegeben. Niemals den Key direkt in eine Datei schreiben.
