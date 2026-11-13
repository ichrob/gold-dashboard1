package ch.bob.degirocompanion

/** OCR supplies a label only. The owner selects the action and any value/result. */
internal object WorkflowComposer {
    fun validText(value: String) = LocalWorkflow.safeText(value) &&
        value.none { it in "\"„“”" }

    fun command(action: WorkflowAction, target: String, value: String = "", expected: String = ""): String? {
        val label = target.trim()
        if (!validText(label)) return null
        val step = when (action) {
            WorkflowAction.CLICK -> {
                if (!validText(expected.trim())) return null
                WorkflowStep(action, label, expected = expected.trim())
            }
            WorkflowAction.WRITE -> {
                if (!validText(value)) return null
                WorkflowStep(action, label, value = value)
            }
            WorkflowAction.WAIT -> WorkflowStep(action, label)
        }
        val command = WorkflowAiPolicy.commands(listOf(step))
        return command.takeIf { LocalWorkflow.parse(it) == listOf(step) }
    }
}
