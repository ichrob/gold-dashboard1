package ch.bob.degirocompanion

/** Device-local geometry from the already authorised accessibility capture.
 * These anchors never supply OCR text, prices or proof of a second read. */
internal object MorningListRegions {
    data class Candidate(val text:String,val top:Int,val bottom:Int,val safe:Boolean=true)
    data class Anchor(val id:String,val top:Int,val bottom:Int)
    private val identities=Regex("\\b[A-Z]{2}[A-Z0-9]{9}[0-9]\\b")

    fun anchors(candidates:List<Candidate>,expected:List<String>,height:Int):List<Anchor>? {
        if(candidates.size>500 || !validExpected(expected,height))return null
        val usable=candidates.filter { it.safe && it.text.length<=2000 && it.top>=0 && it.bottom<=height && it.bottom>it.top }
        return expected.map { id ->
            // Nested parent/child references to one visible identity must
            // share a physical intersection. Distinct occurrences are unsafe.
            val found=usable.filter { identities.findAll(it.text).map { m -> m.value }.distinct().toList()==listOf(id) }
            if(found.isEmpty())return null
            val top=found.maxOf { it.top };val bottom=found.minOf { it.bottom }
            if(bottom-top<4 || bottom-top>height/2)return null
            Anchor(id,top,bottom)
        }.takeIf { anchors -> anchors.zipWithNext().all { (a,b) -> a.bottom<b.top } }
    }

    fun stable(before:List<Anchor>?,after:List<Anchor>?,expected:List<String>,height:Int):List<Anchor>? =
        before?.takeIf { it==after && bands(it,expected,height)!=null }

    private fun validExpected(expected:List<String>,height:Int)=height in 200..5000 && expected.size in 1..6 &&
        expected.distinct()==expected && expected.all { SeriesEvidence.validIsin(it) }

    fun bands(anchors:List<Anchor>?,expected:List<String>,height:Int):List<MorningOcrLayout.ProductBand>? {
        if(anchors==null || !validExpected(expected,height) || anchors.map { it.id }!=expected ||
            anchors.any { it.top<0 || it.bottom>height || it.bottom-it.top<4 || it.bottom-it.top>height/2 } ||
            anchors.zipWithNext().any { (a,b) -> a.bottom>=b.top })return null
        return anchors.mapIndexed { index,anchor ->
            // Context extends from the preceding identity to the following
            // identity. Clipped neighbouring headings are handled by the
            // existing strict row parser; neighbouring ISINs stay outside.
            val top=if(index==0)0 else anchors[index-1].bottom
            val bottom=if(index==anchors.lastIndex)height else anchors[index+1].top
            if(top>anchor.top || bottom<anchor.bottom || bottom-top<40)return null
            MorningOcrLayout.ProductBand(anchor.id,top,bottom)
        }
    }
}
