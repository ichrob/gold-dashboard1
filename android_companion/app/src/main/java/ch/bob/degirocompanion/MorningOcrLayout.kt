package ch.bob.degirocompanion

/** Reassemble bounded OCR lines by their image positions, never block order.
 * Coordinates and unfiltered text stay on the device. Product allowlisting is
 * still performed by MorningLocalOcr after this layout-only transformation. */
internal object MorningOcrLayout {
    data class Line(val text:String,val left:Int,val top:Int,val right:Int,val bottom:Int)
    data class ProductBand(val id:String,val top:Int,val bottom:Int)
    enum class PlanIssue { INPUT_BOUNDS, IDENTITY_MISSING, IDENTITY_DUPLICATE,
        IDENTITY_ORDER, HEADING_MISSING, FOOTER_MISSING, REGION_IDENTITY }

    /** A later incomplete optical pass must not erase a usable layout plan.
     * The plan is only geometry; product values still need two fresh reads. */
    class RecoveryPlanner(private val expected:List<String>,private val height:Int) {
        var bands:List<ProductBand>?=null;private set
        fun offer(lines:List<Line>,rejected:(PlanIssue)->Unit={}) {
            if(bands==null) bands=MorningOcrLayout.productBands(lines,expected,height,rejected)
        }
    }

    /** Local-only recovery plan. Every expected original identity needs a
     * unique visible position, its own preceding heading and following OTC
     * footer. A missing/ambiguous row never borrows a neighbouring identity. */
    fun productBands(lines:List<Line>,expected:List<String>,height:Int,
                     rejected:(PlanIssue)->Unit={}):List<ProductBand>? {
        fun reject(issue:PlanIssue):List<ProductBand>? { rejected(issue);return null }
        val rows=readingLines(lines) ?: return reject(PlanIssue.INPUT_BOUNDS)
        if(expected.isEmpty() || expected.size>6 || height<=0 ||
            expected.distinct()!=expected || expected.any { !SeriesEvidence.validIsin(it) } ||
            rows.any { it.bottom>height }) return reject(PlanIssue.INPUT_BOUNDS)
        val identity=Regex("\\b[A-Z]{2}[A-Z0-9]{9}[0-9]\\b")
        // Use the SAME fixed-anchor visual rows as the strict text parser.
        // ML Kit can split "SG", "Gold", venue and currency across blocks.
        val headings=rows.filter { Regex("(?iu)^(?:SG|BNP)\\s*Gold\\b").containsMatchIn(it.text.trim()) }
        val located=expected.map { id ->
            val matches=rows.filter { identity.findAll(it.text).map { m -> m.value }.toList()==listOf(id) }
            if(matches.isEmpty()) return reject(PlanIssue.IDENTITY_MISSING)
            if(matches.size!=1) return reject(PlanIssue.IDENTITY_DUPLICATE)
            matches.single()
        }
        if(located.zipWithNext().any { (a,b) -> a.bottom>=b.top }) return reject(PlanIssue.IDENTITY_ORDER)
        return located.mapIndexed { index,line ->
            val previous=if(index==0) -1 else located[index-1].bottom
            val next=if(index==located.lastIndex) height else located[index+1].top
            val heading=headings.filter { it.top>previous && it.top<=line.bottom }.maxByOrNull { it.top }
                ?: return reject(PlanIssue.HEADING_MISSING)
            val footer=rows.filter { it.top>=line.top && it.top<next && Regex("(?i)\\bOTC\\b").containsMatchIn(it.text) }
                .minByOrNull { it.top } ?: return reject(PlanIssue.FOOTER_MISSING)
            val padding=maxOf(heading.bottom-heading.top,footer.bottom-footer.top)
            val top=maxOf(0,heading.top-padding)
            val bottom=minOf(height,footer.bottom+padding)
            val ids=rows.filter { (it.top+it.bottom)/2 in top until bottom }
                .flatMap { identity.findAll(it.text).map { m -> m.value }.toList() }
            if(ids!=listOf(expected[index]) || bottom<=top) return reject(PlanIssue.REGION_IDENTITY)
            ProductBand(expected[index],top,bottom)
        }
    }

    fun readingOrder(lines:List<Line>):String? = readingLines(lines)?.joinToString("\n") { it.text }

    private fun readingLines(lines:List<Line>):List<Line>? {
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
        return bands.map { band -> Line(band.sortedBy { it.left }.joinToString(" ") { it.text },
            band.minOf { it.left },band.minOf { it.top },band.maxOf { it.right },band.maxOf { it.bottom }) }
    }
}
