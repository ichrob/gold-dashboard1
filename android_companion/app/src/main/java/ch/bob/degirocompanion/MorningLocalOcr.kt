package ch.bob.degirocompanion

import android.graphics.Bitmap
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import org.json.JSONArray
import org.json.JSONObject

/**
 * Locally recognize ONLY product-list rows from an already approved DEGIRO
 * screenshot crop. Never export the unfiltered ML Kit text, accounts, orders,
 * screen coordinates or PIN data. Two differently scaled passes of the SAME
 * original image are OCR agreement, NOT two independent issuer sources.
 */
internal object MorningLocalOcr {
    data class Rows(val ids:List<String>,val values:List<String>)
    enum class Rejection { INPUT_LIMIT, MISSING_BOX, LAYOUT, HEADING_COUNT,
        ROW_LIMIT, MULTIPLE_IDENTITIES, INTERIOR_FRAGMENT, COMPLETE_EXTRA,
        IDENTITY_ORDER, FOOTER_MISSING, UNSAFE_ROW, ROW_COUNT, PAIR_IDENTITY,
        REGION_INPUT_BOUNDS, REGION_IDENTITY_MISSING, REGION_IDENTITY_DUPLICATE,
        REGION_IDENTITY_ORDER, REGION_HEADING_MISSING, REGION_FOOTER_MISSING,
        REGION_IDENTITY_CONFLICT }

    /** Three sequential optical attempts at most; one successful read is never
     * evidence. A failed first pass must not prevent the scaled recovery pair.
     * Conflicting valid identity subsets terminate instead of cherry-picking. */
    fun collectPasses(recognize:(Int,(Rows?)->Unit)->Unit,done:(List<Rows>?)->Unit) {
        val accepted=mutableListOf<Rows>()
        var finished=false
        fun finish(value:List<Rows>?) { if(!finished) { finished=true;done(value) } }
        fun next(index:Int) {
            if(index>=3) { finish(null);return }
            var received=false
            recognize(index) { rows ->
                if(!finished && !received) {
                    received=true
                    if(rows!=null) {
                        if(accepted.isNotEmpty() && rows.ids!=accepted.first().ids) {
                            ProductReadDiagnostics.localOcr(Rejection.PAIR_IDENTITY)
                            finish(null)
                        } else accepted.add(rows)
                    }
                    if(!finished) {
                        if(accepted.size==2) finish(accepted.toList()) else next(index+1)
                    }
                }
            }
        }
        next(0)
    }

    /** Unique widths: retrying an identical bitmap is not an optical second pass. */
    fun passWidths(width:Int):List<Int> = listOf(width,minOf(1600,(width*1.15).toInt()),
        minOf(1600,(width*1.5).toInt()),maxOf(200,(minOf(width,1600)*.85).toInt()),maxOf(200,(minOf(width,1600)*.7).toInt()))
        .distinct().take(3)

    /** A viewport can include an expected ISIN whose footer is off-screen.
     * Keep only complete contiguous rows. Missing edge rows must be supplied
     * by another original image; the server still requires ten agreed rows. */
    fun completeViewportRows(raw:String,expected:List<String>,diagnose:Boolean=false):Rows? {
        if(expected.isEmpty() || expected.size>10 || expected.distinct()!=expected ||
            expected.any { !SeriesEvidence.validIsin(it) }) return null
        var reason=Rejection.INPUT_LIMIT
        parseRows(raw,expected) { reason=it }?.let { return Rows(expected,it) }
        val candidates=mutableListOf<Rows>()
        for((left,right) in listOf(0 to 1,1 to 0,1 to 1)) {
            if(expected.size<=left+right) continue
            val subset=expected.subList(left,expected.size-right)
            productRows(raw,subset)?.let { candidates.add(Rows(subset.toList(),it)) }
        }
        // Ambiguous alternatives are not interchangeable evidence.
        val result=candidates.distinctBy { it.ids }.singleOrNull()
        if(result==null && diagnose) ProductReadDiagnostics.localOcr(reason)
        return result
    }

    private fun positionedLines(text:com.google.mlkit.vision.text.Text):List<MorningOcrLayout.Line>? {
        val lines=mutableListOf<MorningOcrLayout.Line>()
        for(block in text.textBlocks) for(line in block.lines) {
            val box=line.boundingBox ?: run { ProductReadDiagnostics.localOcr(Rejection.MISSING_BOX);return null }
            lines.add(MorningOcrLayout.Line(line.text,box.left,box.top,box.right,box.bottom))
        }
        if(MorningOcrLayout.readingOrder(lines)==null) { ProductReadDiagnostics.localOcr(Rejection.LAYOUT);return null }
        return lines
    }
    private val heading=Regex("(?iu)\\b(?:SG|BNP)\\s+Gold\\b")
    private val isin=Regex("\\b[A-Z]{2}[A-Z0-9]{9}[0-9]\\b")
    private val footer=Regex(
        "(?iu)(?:Soci[eé]t[eé]\\s+G[eé]n[eé]rale|BNP(?:\\s+Paribas)?)\\s+OTC\\s+(?:EUR|CHF)\\b")
    private val unsafe=Regex(
        "(?iu)\\b(?:Passwort|password|Kontostand|Konto|Portfolio|order bestätigen|confirm order|stückzahl kaufen)\\b")

    fun productRows(raw:String,expected:List<String>):List<String>? = parseRows(raw,expected) {}

    private fun parseRows(raw:String,expected:List<String>,rejected:(Rejection)->Unit):List<String>? {
        fun reject(reason:Rejection):List<String>? { rejected(reason);return null }
        if(expected.isEmpty() || expected.size>10 ||
           expected.distinct()!=expected || expected.any { !SeriesEvidence.validIsin(it) } ||
           raw.length>20000) return reject(Rejection.INPUT_LIMIT)
        val page=raw.replace(Regex("(?i)\\bSG(?=Gold)"),"SG ")
            .replace(Regex("\\s+")," ").trim()
        val starts=heading.findAll(page).map { it.range.first }.toList()
        if(starts.size<expected.size || starts.size>expected.size+2) return reject(Rejection.HEADING_COUNT)
        val result=mutableListOf<String>()
        for(index in starts.indices) {
            val end=if(index+1<starts.size) starts[index+1] else page.length
            val segment=page.substring(starts[index],end)
            if(segment.length>1000) return reject(Rejection.ROW_LIMIT)
            val ids=isin.findAll(segment).toList()
            if(ids.size>1) return reject(Rejection.MULTIPLE_IDENTITIES)
            val id=ids.singleOrNull()
            val venue=id?.let { footer.find(segment,it.range.last+1) }
            if(id==null || id.value !in expected) {
                // Only an incomplete edge neighbour may sit outside the
                // accessibility-approved complete rows. Never export it, skip
                // a complete extra product, or ignore an interior fragment.
                if(index!=0 && index!=starts.lastIndex) return reject(Rejection.INTERIOR_FRAGMENT)
                if(venue!=null) return reject(Rejection.COMPLETE_EXTRA)
                continue
            }
            if(result.size>=expected.size || id.value!=expected[result.size]) return reject(Rejection.IDENTITY_ORDER)
            if(venue==null) return reject(Rejection.FOOTER_MISSING)
            val row=segment.substring(0,venue.range.last+1).trim()
            if(row.length>800 || unsafe.containsMatchIn(row)) return reject(Rejection.UNSAFE_ROW)
            result+=row
        }
        return if(result.size==expected.size) result else reject(Rejection.ROW_COUNT)
    }

    fun read(crop:Bitmap,expected:List<String>,appAnchors:List<MorningListRegions.Anchor>?=null,done:(JSONObject?)->Unit) {
        if(crop.isRecycled || crop.width<200 || crop.height<200 || crop.width*crop.height>16_000_000) {
            if(!crop.isRecycled) crop.recycle()
            done(null);return
        }
        val client=TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
        var scaled:Bitmap?=null
        var finished=false
        val recovery=MorningOcrLayout.RecoveryPlanner(expected,crop.height)
        fun planIssue(issue:MorningOcrLayout.PlanIssue) {
            ProductReadDiagnostics.localOcr(when(issue) {
                MorningOcrLayout.PlanIssue.INPUT_BOUNDS -> Rejection.REGION_INPUT_BOUNDS
                MorningOcrLayout.PlanIssue.IDENTITY_MISSING -> Rejection.REGION_IDENTITY_MISSING
                MorningOcrLayout.PlanIssue.IDENTITY_DUPLICATE -> Rejection.REGION_IDENTITY_DUPLICATE
                MorningOcrLayout.PlanIssue.IDENTITY_ORDER -> Rejection.REGION_IDENTITY_ORDER
                MorningOcrLayout.PlanIssue.HEADING_MISSING -> Rejection.REGION_HEADING_MISSING
                MorningOcrLayout.PlanIssue.FOOTER_MISSING -> Rejection.REGION_FOOTER_MISSING
                MorningOcrLayout.PlanIssue.REGION_IDENTITY -> Rejection.REGION_IDENTITY_CONFLICT
            })
        }
        fun complete(value:JSONObject?) {
            if(finished)return
            finished=true
            runCatching { client.close() }
            scaled?.let { if(it!==crop && !it.isRecycled) it.recycle() }
            if(!crop.isRecycled)crop.recycle()
            done(value)
        }
        val widths=passWidths(crop.width)
        fun pack(pair:List<Rows>?):JSONObject?=pair?.let { reads -> runCatching { JSONObject()
            .put("expectedIsins",JSONArray(reads.first().ids))
            .put("passes",JSONArray().put(JSONArray(reads[0].values)).put(JSONArray(reads[1].values)))
        }.getOrNull() }
        fun recoverRegions() {
            // Independent app geometry breaks the circular dependency: an
            // unreadable full-image ISIN need not seed its own optical crop.
            val fromApp=MorningListRegions.bands(appAnchors,expected,crop.height)
            val bands=fromApp ?: recovery.bands
            if(bands==null) { complete(null);return }
            if(fromApp!=null)ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.LIST_LOCAL_OCR_APP_ANCHORS)
            ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.LIST_LOCAL_OCR_REGIONS_STARTED)
            val first=mutableListOf<String>();val second=mutableListOf<String>()
            fun nextBand(index:Int) {
                if(index==bands.size) {
                    ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.LIST_LOCAL_OCR_REGIONS_ACCEPTED)
                    complete(pack(listOf(Rows(expected,first),Rows(expected,second))));return
                }
                val band=bands[index]
                val region=runCatching { Bitmap.createBitmap(crop,0,band.top,crop.width,band.bottom-band.top) }.getOrNull()
                if(region==null) { complete(null);return }
                collectPasses({ pass,accept ->
                    runCatching {
                        val width=passWidths(region.width)[pass]
                        val height=maxOf(1,(region.height.toDouble()*width/region.width).toInt())
                        check(width.toLong()*height<=16_000_000)
                        val input=if(width==region.width) region else Bitmap.createScaledBitmap(region,width,height,true)
                        scaled=input.takeIf { it!==region }
                        client.process(InputImage.fromBitmap(input,0)).addOnCompleteListener { task ->
                            val lines=if(task.isSuccessful) runCatching { positionedLines(task.result) }.getOrNull() else null
                            val text=lines?.let { MorningOcrLayout.readingOrder(it) }
                            val values=text?.let { parseRows(it,listOf(band.id)) { reason -> ProductReadDiagnostics.localOcr(reason) } }
                            if(input!==region && !input.isRecycled) input.recycle()
                            scaled=null
                            accept(values?.let { Rows(listOf(band.id),it) })
                        }
                    }.onFailure {
                        scaled?.let { if(it!==crop && it!==region && !it.isRecycled) it.recycle() };scaled=null
                        accept(null)
                    }
                }) { pair ->
                    if(region!==crop && !region.isRecycled) region.recycle()
                    if(pair==null) complete(null)
                    else { first.add(pair[0].values.single());second.add(pair[1].values.single());nextBand(index+1) }
                }
            }
            nextBand(0)
        }
        collectPasses({ index, accept ->
            if(index>=widths.size) { accept(null) }
            else runCatching {
                val width=widths[index]
                val height=maxOf(1,(crop.height.toDouble()*width/crop.width).toInt())
                check(width.toLong()*height<=16_000_000)
                val input=if(width==crop.width) crop else
                    Bitmap.createScaledBitmap(crop,width,height,true).also { scaled=it }
                client.process(InputImage.fromBitmap(input,0)).addOnCompleteListener { task ->
                    val lines=if(task.isSuccessful) runCatching { positionedLines(task.result) }.getOrNull() else null
                    // Restore positions to the original cropped PNG before
                    // planning local recovery; coordinates never leave phone.
                    val rows=lines?.let { MorningOcrLayout.readingOrder(it) }?.let { completeViewportRows(it,expected,diagnose=true) }
                    if(lines!=null) recovery.offer(lines.map { line ->
                        val factor=crop.width.toDouble()/width
                        MorningOcrLayout.Line(line.text,(line.left*factor).toInt(),(line.top*factor).toInt(),
                            kotlin.math.ceil(line.right*factor).toInt(),kotlin.math.ceil(line.bottom*factor).toInt())
                    }) { issue -> if(rows==null) planIssue(issue) }
                    if(rows==null) ProductReadDiagnostics.record(if(task.isSuccessful)
                        when(index) {
                            0 -> ProductReadDiagnostics.Outcome.LIST_LOCAL_OCR_FIRST_REJECTED
                            1 -> ProductReadDiagnostics.Outcome.LIST_LOCAL_OCR_SECOND_REJECTED
                            else -> ProductReadDiagnostics.Outcome.LIST_LOCAL_OCR_THIRD_REJECTED
                        } else ProductReadDiagnostics.Outcome.LIST_LOCAL_OCR_ENGINE_FAILED)
                    // Release each temporary bitmap before scheduling another.
                    if(input!==crop && !input.isRecycled) input.recycle()
                    scaled=null
                    accept(rows)
                }
            }.onFailure {
                ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.LIST_LOCAL_OCR_ENGINE_FAILED)
                scaled?.let { if(it!==crop && !it.isRecycled) it.recycle() };scaled=null
                accept(null)
            }
        }) { pair ->
            // The server still reconciles every field across the two genuine
            // optical reads; never duplicate one pass to manufacture agreement.
            if(pair==null) recoverRegions() else complete(pack(pair))
        }
    }
}
