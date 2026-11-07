package ch.bob.degirocompanion

/** Known Gold goals retain the existing reader; other goals use the checked workflow engine. */
internal object WorkflowAppRoute {
    const val DEGIRO = "nl.degiro.trader"
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
