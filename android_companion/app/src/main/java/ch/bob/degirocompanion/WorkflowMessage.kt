package ch.bob.degirocompanion

/** The owner's text supplies actions; local screenshot OCR supplies labels only. */
internal object WorkflowMessage {
    private val reference = Regex("(?i)^(?:diese schaltfläche|diesen button|dieses feld|dieses eingabefeld|hier|das feld)$")
    fun needsTarget(text: String): Boolean = text.lines().any { line ->
        reference.matches(line.substringAfterLast(" in ", line.substringAfter("auf ")).substringBefore(" -> ").trim())
    }

    fun resolve(text: String, labels: List<String>, selected: String? = null): String? {
        val safeLabels = labels.filter { WorkflowComposer.validText(it) }.distinct()
        if (safeLabels.isEmpty() || (selected != null && selected !in safeLabels)) return null
        fun target(raw: String): String? {
            val value = raw.trim().removeSurrounding("\"")
            if (reference.matches(value)) return selected ?: safeLabels.singleOrNull()
            return safeLabels.singleOrNull { LocalWorkflow.normalize(it) == LocalWorkflow.normalize(value) }
        }
        val explicit = LocalWorkflow.parse(text)
        if (explicit != null) {
            // Later sequence targets may only appear after an earlier navigation step.
            if (target(explicit.first().target) == null) return null
            val resolved = explicit.map { step ->
                if (reference.matches(step.target)) step.copy(target = target(step.target) ?: return null) else step
            }
            return WorkflowAiPolicy.commands(resolved)
        }
        val lines = text.trim().lines()
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
