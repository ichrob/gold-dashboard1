package ch.bob.degirocompanion

/** Reuse only explicitly requested stored steps; recognize already-open search navigation. */
internal object WorkflowReplay {
    fun prepare(steps: List<WorkflowStep>, frame: WorkflowFrame): List<WorkflowStep> {
        val oneSearch = WorkflowSearch.fields(frame).size == 1
        val remaining = steps.dropWhile { step ->
            step.action == WorkflowAction.CLICK && (
                (oneSearch && (step.opensSearch || LocalWorkflow.normalize(step.expected) in WorkflowAuto.labels)) ||
                (!step.opensSearch && step.expected.isNotBlank() && frame.contains(step.expected) && LocalWorkflow.candidates(step,frame).isEmpty()))
        }
        return remaining.map { step ->
            if (step.action == WorkflowAction.WRITE && oneSearch && LocalWorkflow.target(step,frame) == null &&
                LocalWorkflow.normalize(step.target) in WorkflowAuto.labels) step.copy(target = WorkflowSearch.FIELD) else step
        }
    }
}
