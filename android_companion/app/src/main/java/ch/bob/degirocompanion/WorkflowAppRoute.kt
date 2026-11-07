package ch.bob.degirocompanion

/** DEGIRO uses its existing bounded reader, never arbitrary or AI-generated actions. */
internal object WorkflowAppRoute {
    const val DEGIRO = "nl.degiro.trader"
    fun selectable(app: String) = app == DEGIRO || LocalWorkflow.allowedApp(app)
    fun goldRead(goal: String): Boolean = LocalWorkflow.normalize(goal) in setOf(
        "gold", "gold suchen", "suche gold", "goldprodukte lesen", "gold-produkte suchen und auslesen",
        "schreibe gold in das suchfeld", "schreibe gold in die suche",
        "schreibe \"gold\" in das suchfeld", "schreibe \"gold\" in \"suchfeld\"")
}
