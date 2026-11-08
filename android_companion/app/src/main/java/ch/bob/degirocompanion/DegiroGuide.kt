package ch.bob.degirocompanion

/** Reviewed public documentation is knowledge, never proof of the current screen or permission to act. */
internal object DegiroGuide {
    const val reviewed = "08.11.2026"
    data class Topic(val title: String, val explanation: String, val source: String)
    private const val help = "https://www.degiro.de/helpdesk/"
    val topics = listOf(
        Topic("Suche · Lupe · Name oder ISIN", "Die Lupe in der unteren Menüleiste öffnet laut DEGIRO die Suche. In das Suchfeld gehören Produktname, ISIN oder ein Ticker mit mehr als drei Zeichen. Beispiel: Silber oder DE000PM96QY2. Gleiche ISIN kann mehrere Börsenplätze haben: Treffer und Handelsplatz prüfen. Bob nutzt nur eine eindeutig beschriftete Suchschaltfläche und prüft danach das Eingabefeld.", help + "handelsplattform/verwendung-der-handelsplattform/wie-suche-ich-nach-einem-produkt"),
        Topic("Favoriten · Stern", "Das Register Favoriten führt zur Favoritenliste. Der Stern auf einer Produktseite fügt das Produkt hinzu; laut DEGIRO wird er danach blau. Ein Stern auf der Produktseite ist nicht dasselbe wie das Register Favoriten. Bob muss Ziel und Ergebnis unterscheiden; ein unbeschriftetes Symbol einmal über Bob etwas beibringen erklären.", help + "handelsplattform/verwendung-der-handelsplattform/kann-ich-eine-liste-meiner-favoriten-produkte"),
        Topic("Inbox · Dokumente und Berichte", "Laut DEGIRO liegt die Inbox in der App unten rechts. Dort befinden sich Kontoauszug und Transaktionsauszug; Dokumente führt zu Jahresübersichten und Geldkontoauszügen. Startdatum und Enddatum begrenzen einen Bericht. Der Pfeil nach unten bedeutet Export. Positionen sind Orientierung, keine festen Klickkoordinaten.", help + "steuer/welche-berichte-gibt-es-und-wo-kann-ich-sie-finden-1"),
        Topic("Portfolio · Übersicht exportieren", "Im Portfolio bietet der Export eine Übersicht für ein ausgewähltes Datum. In der App ist das Symbol ein Pfeil nach unten. Anschließend Datum und Format auswählen: XLS, CSV oder PDF. Bob soll die sichtbaren Feldbeschriftungen prüfen und nur die von dir gewünschten Werte verwenden.", help + "steuer/welche-berichte-gibt-es-und-wo-kann-ich-sie-finden-1"),
        Topic("Anmelden und zum Ziel gelangen", "Bob verwendet für die Anmeldung ausschließlich den bereits eingerichteten lokalen PIN-Ablauf. Die Anleitung enthält keine Zugangsdaten. Danach prüft Bob die aktuelle Ansicht. Gold-, Silber- und ISIN-Aufträge nutzen die bestehenden Suchabläufe. Weitere Zwischenwege stammen aus erfolgreich geprüften gespeicherten Abläufen. Unbekannte oder mehrdeutige Wege müssen einmal gezeigt werden.", "Bob: lokale Abläufe und geprüfte gespeicherte Wege"),
        Topic("Was ist erkannt, was ist noch unklar?", "Eine sichtbare Registerbeschriftung beweist nicht, dass das Register geöffnet ist. Bob berücksichtigt den ausgewählten Zustand und eindeutig erkannte Suchfelder. Die angezeigte Ansicht ist eine zeitlich begrenzte letzte Beobachtung. Screenshot und Anleitung sind keine Live-Bestätigung. Kaufen, Verkaufen, Orders und Zahlungen werden durch diese Anleitung nicht freigeschaltet.", "Bob: lokale Ansichtsprüfung")
    )
    fun requested(text: String) = LocalWorkflow.normalize(text).removeSuffix("?") in setOf(
        "degiro-anleitung", "degiro anleitung", "bedienungsanleitung", "wie funktioniert degiro", "wo bin ich", "wo bin ich in degiro")

    fun screen(frame: WorkflowFrame): String {
        if (frame.app != WorkflowAppRoute.DEGIRO) return "Andere App"
        if (LocalWorkflow.protected(frame)) return "Geschützte Ansicht · keine allgemeine Bedienung"
        val labels = frame.nodes.map { LocalWorkflow.normalize(it.label) }
        if (labels.any { it == "connection error" || it == "verbindungsfehler" }) return "Verbindungsfehler"
        val fields = WorkflowSearch.fields(frame)
        if (fields.size > 1) return "Mehrdeutige Suchansicht"
        if (fields.size == 1) return "Suche · Eingabefeld erkannt"
        val selectedSections = frame.nodes.filter { it.selected && !it.editable && !it.password }
            .mapNotNull { sections[LocalWorkflow.normalize(it.label)] }.distinct()
        return if (selectedSections.size == 1) "Register ${selectedSections.single()} · Auswahl erkannt" else "Ansicht noch nicht eindeutig erkannt"
    }
    private val sections = mapOf("favoriten" to "Favoriten", "favorites" to "Favoriten", "watchlist" to "Favoriten",
        "portfolio" to "Portfolio", "inbox" to "Inbox", "markt" to "Markt", "markets" to "Markt")

    fun observation(frame: WorkflowFrame?, age: Long): String =
        if (frame == null || frame.app != WorkflowAppRoute.DEGIRO || age !in 0..60_000)
            "Keine frische DEGIRO-Beobachtung · Ansicht unbekannt"
        else "Letzte DEGIRO-Beobachtung (vor ${age / 1000} s): ${screen(frame)}"

    /** Only the documented search edge is executable without a learned route, and only when visible. */
    fun approach(steps: List<WorkflowStep>, frame: WorkflowFrame): List<WorkflowStep>? {
        if (frame.app != WorkflowAppRoute.DEGIRO || LocalWorkflow.protected(frame) || steps.size !in 1..11) return null
        val first = steps.first()
        if (first.action != WorkflowAction.WRITE || first.target != WorkflowSearch.FIELD ||
            !LocalWorkflow.safeText(first.value) || WorkflowSearch.fields(frame).isNotEmpty()) return null
        val button = WorkflowSearch.buttons(frame).singleOrNull() ?: return null
        val label = frame.nodes[button].label
        // Do not treat duplicate text nodes as a uniquely actionable target.
        val open = WorkflowStep(WorkflowAction.CLICK, label, opensSearch=true)
        if (LocalWorkflow.target(open, frame) == null) return null
        return listOf(open) + steps
    }
}
