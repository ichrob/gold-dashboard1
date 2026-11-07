package ch.bob.degirocompanion

/** Known Gold goals retain the existing reader; other goals use the checked workflow engine. */
internal object WorkflowAppRoute {
    const val DEGIRO = "nl.degiro.trader"
    data class Capability(val title: String, val command: String, val aliases: Set<String> = emptySet())
    // One catalog drives both discoverability and routing to existing local handlers.
    val capabilities = listOf(
        Capability("Gespeicherte PIN einmal eingeben", "DEGIRO entsperren"),
        Capability("Bob starten", "DEGIRO anmelden und Goldprodukte einlesen", setOf("starte den vollständigen degiro-ablauf", "degiro komplett starten")),
        Capability("Gold-Produkte suchen und auslesen", "Gold suchen"),
        Capability("Seite prüfen · DEGIRO öffnen, automatisch scrollen und lesen", "Aktuelles DEGIRO-Produkt einlesen", setOf("produktseite lesen", "degiro produkt lesen")),
        Capability("Morgenliste automatisch von Bob holen und lesen", "Morgenliste holen und lesen"),
        Capability("Unterbrochenen Listenlauf fortsetzen", "Listenlauf fortsetzen"),
        Capability("Gespeicherten Listenlauf an Bob übertragen / erneut versuchen", "Gespeicherte Produktergebnisse übertragen"),
        Capability("Bisherige Morgenliste prüfen / übertragen", "Morgenliste prüfen"),
        Capability("Gelesene Werte in Bob prüfen", "Gelesene Produktwerte anzeigen"),
        Capability("DEGIRO-PIN nur auf diesem Handy einrichten", "DEGIRO-PIN einrichten"),
        Capability("Gespeicherte DEGIRO-PIN löschen", "Gespeicherte DEGIRO-PIN löschen"),
        Capability("PIN-Anmeldeseite technisch prüfen · ohne PIN", "DEGIRO-PIN-Seite prüfen"),
        Capability("Eine Testziffer eingeben und löschen", "DEGIRO-Tastaturtest starten"),
        Capability("Leseprüfung einschalten / Android-Einstellungen", "DEGIRO-Lesedienst einrichten"),
        Capability("Automatische Diagnose verbinden / Freigabe öffnen", "DEGIRO-Diagnose verbinden"),
        Capability("Automatische Diagnose ausschalten", "DEGIRO-Diagnose ausschalten"),
        Capability("ChatGPT-Handy-Sitzung starten · 15 Minuten", "DEGIRO-Handy-Sitzung starten"),
        Capability("Technische Diagnose kopieren", "DEGIRO-Diagnose kopieren"),
        Capability("Einrichtung und weitere Möglichkeiten", "DEGIRO-Einstellungen öffnen"),
        Capability("Prüfung stoppen", "DEGIRO-Prüfung stoppen")
    )
    fun capability(goal: String): Capability? {
        if (localLogin(goal)) return capabilities[0]
        if (goldRead(goal)) return capabilities[2]
        val text = LocalWorkflow.normalize(goal).removeSuffix(".")
        return capabilities.singleOrNull { text == LocalWorkflow.normalize(it.command) ||
            text == LocalWorkflow.normalize(it.title) || text in it.aliases }
    }
    fun asksCapabilities(goal: String) = LocalWorkflow.normalize(goal).removeSuffix("?") in setOf(
        "was kannst du", "was kannst du in degiro", "was kannst du bei degiro", "degiro-funktionen", "hilfe")
    fun selectable(app: String) = app == DEGIRO || LocalWorkflow.allowedApp(app)
    // Recognize only a request to use the already enrolled local PIN. No secret
    // values, additional actions, OCR text or cloud proposals enter this route.
    fun localLogin(goal: String): Boolean {
        val text = LocalWorkflow.normalize(goal).removeSuffix(".")
        if (text in setOf("degiro entsperren", "degiro anmelden", "bei degiro anmelden",
                "melde mich bei degiro an", "degiro mit gespeicherter pin öffnen",
                "gespeicherte degiro-pin eingeben")) return true
        return Regex("(?:öffne|starte) (?:die )?degiro(?:-app| app)? und (?:gib|gebe) (?:selbstständig |automatisch )?(?:das passwort|die (?:gespeicherte |lokale )?pin) ein(?: zum öffnen der app)?").matches(text)
    }
    fun goldRead(goal: String): Boolean = LocalWorkflow.normalize(goal) in setOf(
        "gold", "gold suchen", "suche gold", "goldprodukte lesen", "gold-produkte suchen und auslesen",
        "schreibe gold in das suchfeld", "schreibe gold in die suche",
        "schreibe \"gold\" in das suchfeld", "schreibe \"gold\" in \"suchfeld\"")
}
