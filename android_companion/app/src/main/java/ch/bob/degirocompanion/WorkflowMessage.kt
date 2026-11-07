package ch.bob.degirocompanion

/** The owner's text supplies actions; local screenshot OCR supplies labels only. */
internal object WorkflowMessage {
    private val reference = Regex("(?i)^(?:diese schaltfläche|diesen button|dieses feld|dieses eingabefeld|hier|das feld)$")
    private fun ownerLine(text: String) = WorkflowLanguage.line(text)
    private fun label(raw: String, candidates: List<String>, selected: String?): String? {
        val value = raw.trim().removeSurrounding("\"")
        if (reference.matches(value)) return selected?.takeIf { it in candidates } ?: candidates.singleOrNull()
        fun match(value: String) = candidates.singleOrNull { LocalWorkflow.normalize(it) == LocalWorkflow.normalize(value) }
        match(value)?.let { return it }
        val named = value.replace(Regex("(?i)^(?:(?:die|den|das)\\s+)?(?:schaltfläche|button|reiter|registerkarte|feld|eingabefeld)\\s+"), "")
            .trim().removeSurrounding("\"")
        return match(named)
    }
    fun clickTarget(text: String, labels: List<String>, selected: String? = null): String? {
        val match = Regex("(?i)^(?:tippe|klicke) auf ([^\\n]+)$").matchEntire(ownerLine(text)) ?: return null
        val raw = match.groupValues[1].trim().removeSurrounding("\"")
        val candidates = labels.filter { WorkflowComposer.validText(it) }.distinct()
        return label(raw, candidates, selected)
    }
    fun needsTarget(text: String): Boolean = text.lines().any { line ->
        reference.matches(line.substringAfterLast(" in ", line.substringAfter("auf ")).substringBefore(" -> ").trim())
    }

    fun resolve(text: String, labels: List<String>, selected: String? = null): String? {
        val safeLabels = labels.filter { WorkflowComposer.validText(it) }.distinct()
        if (safeLabels.isEmpty() || (selected != null && selected !in safeLabels)) return null
        fun target(raw: String): String? {
            return label(raw, safeLabels, selected)
        }
        val normalizedText = text.trim().lines().joinToString("\n", transform=::ownerLine)
        val explicit = LocalWorkflow.parse(normalizedText)
        if (explicit != null) {
            // Later sequence targets may only appear after an earlier navigation step.
            if (target(explicit.first().target) == null) return null
            val resolved = explicit.mapIndexed { index, step ->
                if (index == 0 || reference.matches(step.target)) step.copy(target = target(step.target) ?: return null) else step
            }
            return WorkflowAiPolicy.commands(resolved)
        }
        clickTarget(normalizedText, safeLabels, selected)?.let { target ->
            if (WorkflowNavigation.isTab(target)) return WorkflowAiPolicy.commands(listOf(
                WorkflowStep(WorkflowAction.CLICK, target, selectsTab=true)))
        }
        val lines = normalizedText.lines()
        if (lines.size !in 1..12) return null
        val result = lines.map { line ->
            val write = Regex("(?i)^schreibe (.+?) in (.+)$").matchEntire(line.trim())
            val click = Regex("(?i)^(?:tippe|klicke) auf (.+?) -> (.+)$").matchEntire(line.trim())
            val wait = Regex("(?i)^warte auf (.+)$").matchEntire(line.trim())
            when {
                write != null -> WorkflowComposer.command(WorkflowAction.WRITE,
                    target(write.groupValues[2]) ?: return null,
                    write.groupValues[1].removeSurrounding("\""))
                click != null -> WorkflowComposer.command(WorkflowAction.CLICK,
                    target(click.groupValues[1]) ?: return null,
                    expected = click.groupValues[2].trim().removeSurrounding("\""))
                wait != null -> WorkflowComposer.command(WorkflowAction.WAIT,
                    target(wait.groupValues[1]) ?: return null)
                else -> null
            } ?: return null
        }.joinToString("\n")
        return result.takeIf { LocalWorkflow.parse(it) != null }
    }
}
