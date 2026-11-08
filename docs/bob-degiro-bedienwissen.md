# Bob Handy: DEGIRO-Bedienwissen

Recherche: 8. November 2026. Offizielle DEGIRO-Hilfe, deutsche App-Beschreibung.

| Ziel | Dokumentierter Weg | Kontrolle vor und nach Bedienung |
|---|---|---|
| Produkt suchen | Lupe unten → Suchfeld → Name, ISIN oder Ticker mit mehr als drei Zeichen | Eindeutiger aktueller Suchknopf, danach ein Suchfeld, exakter Eingabewert; bei ISIN zusätzlich Listing/Handelsplatz prüfen |
| Favoriten ansehen | Register Favoriten | Ausgewählter Zustand; sichtbarer Text allein reicht nicht |
| Favorit hinzufügen | Stern auf Produktseite | Produktidentität und geänderter Sternzustand; kein pauschaler Koordinatenklick |
| Konto-/Transaktionsauszug | Inbox → gewünschter Bericht | Aktueller Bereich und Berichtstitel; Start-/Enddatum nach Nutzerauftrag |
| Jahresübersicht | Inbox → Dokumente | Dokumenttitel und Jahr prüfen |
| Portfolioübersicht exportieren | Portfolio → Export/Pfeil nach unten → Datum und Format | Gewünschtes Datum und XLS/CSV/PDF prüfen |

## Quellen

- https://www.degiro.de/helpdesk/handelsplattform/verwendung-der-handelsplattform/wie-suche-ich-nach-einem-produkt
- https://www.degiro.de/helpdesk/handelsplattform/verwendung-der-handelsplattform/kann-ich-eine-liste-meiner-favoriten-produkte
- https://www.degiro.de/helpdesk/steuer/welche-berichte-gibt-es-und-wo-kann-ich-sie-finden-1

## In Bob umgesetzt

Unter **Bob etwas beibringen → DEGIRO-Anleitung und letzte Ansicht**, oder per Auftrag **DEGIRO-Anleitung** / **Wo bin ich?**, ist die lokale Anleitung mit Quellen verfügbar. Sie benötigt keine externe KI und überträgt keine Kontoinhalte.

Der Ansichtsdetektor unterscheidet eine eindeutig erkennbare Suche, ausgewählte Register (Favoriten/Portfolio/Inbox/Markt), Verbindungsfehler und unbekannte oder geschützte Ansichten. Eine gespeicherte Beobachtung wird höchstens 60 Sekunden als frisch bezeichnet, mit Alter angezeigt und niemals als kontinuierlicher Live-Zugriff dargestellt. Die allgemeine Bedienung liest keine geschützten Ansichten ein.

Ein Auftrag für das dynamisch erkannte Suchfeld kann die eindeutig sichtbare Suchschaltfläche jetzt ohne vorher angelernten Ablauf öffnen. Das bestehende Ausführungsmodul prüft danach das Suchfeld und die Eingabe. Andere Zwischenwege müssen weiterhin erfolgreich lokal gelernt sein; mehrere mögliche Wege führen nicht zu einer willkürlichen Auswahl.

## Grenzen

Die Hilfe ist keine vollständige Android-Schaltflächeninventur. Version, Sprache, Konto und Ansicht können abweichen. Beschriebene Positionen sind Orientierung, niemals Ausführungskoordinaten. Für Inbox, Export und Sternaktionen liefert diese Erweiterung Wissen, keine neuen ungetesteten automatischen Routinen. Bisherige Anmeldung, Gold-/Silber-/ISIN-Suche und gespeicherte Wege bleiben erhalten. Keine Echtgeldorders, Zahlungen oder Weitergabe von PIN/Passwörtern. Kein Nachweis eines vollständigen Ablaufs auf dem Samsung allein durch Emulator-Tests.
