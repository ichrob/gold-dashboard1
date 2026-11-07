package ch.bob.degirocompanion

/** Known Gold goals retain the existing reader; other goals use the checked workflow engine. */
internal object WorkflowAppRoute {
    const val DEGIRO = "nl.degiro.trader"
    fun selectable(app: String) = app == DEGIRO || LocalWorkflow.allowedApp(app)
    fun goldRead(goal: String): Boolean = LocalWorkflow.normalize(goal) in setOf(
        "gold", "gold suchen", "suche gold", "goldprodukte lesen", "gold-produkte suchen und auslesen",
        "schreibe gold in das suchfeld", "schreibe gold in die suche",
        "schreibe \"gold\" in das suchfeld", "schreibe \"gold\" in \"suchfeld\"")
}
