package ch.bob.degirocompanion

/** Local activity-thread request ownership; a late old response cannot restart navigation. */
internal class ReadPreparationTickets {
    private var generation=0L
    fun issue():Long { generation++;return generation }
    fun cancel() { generation++ }
    fun accepts(ticket:Long):Boolean = ticket==generation
}
