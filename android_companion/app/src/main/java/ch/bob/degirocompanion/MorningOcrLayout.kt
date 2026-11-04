package ch.bob.degirocompanion

/** Reassemble bounded OCR lines by their image positions, never block order.
 * Coordinates and unfiltered text stay on the device. Product allowlisting is
 * still performed by MorningLocalOcr after this layout-only transformation. */
internal object MorningOcrLayout {
    data class Line(val text:String,val left:Int,val top:Int,val right:Int,val bottom:Int)

    fun readingOrder(lines:List<Line>):String? {
        if(lines.isEmpty() || lines.size>300 || lines.sumOf { it.text.length }>20000 ||
            lines.any { it.left<0 || it.top<0 || it.right<=it.left || it.bottom<=it.top }) return null
        fun center(line:Line)=(line.top.toDouble()+line.bottom)/2
        val bands=mutableListOf<MutableList<Line>>()
        for(line in lines.sortedWith(compareBy<Line> { center(it) }.thenBy { it.left })) {
            val band=bands.lastOrNull()
            val anchor=band?.first()
            // Fixed anchor prevents a chain of slightly offset fragments from
            // merging separate product lines. Use the smaller text height.
            if(band!=null && anchor!=null && kotlin.math.abs(center(line)-center(anchor))<=
                minOf(line.bottom-line.top,anchor.bottom-anchor.top)*0.45) band.add(line)
            else bands.add(mutableListOf(line))
        }
        return bands.joinToString("\n") { band -> band.sortedBy { it.left }.joinToString(" ") { it.text } }
    }
}
