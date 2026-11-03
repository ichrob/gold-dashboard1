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
    private val heading=Regex("(?iu)\\b(?:SG|BNP)\\s+Gold\\b")
    private val isin=Regex("\\b[A-Z]{2}[A-Z0-9]{9}[0-9]\\b")
    private val footer=Regex(
        "(?iu)(?:Soci[eé]t[eé]\\s+G[eé]n[eé]rale|BNP(?:\\s+Paribas)?)\\s+OTC\\s+(?:EUR|CHF)\\b")
    private val unsafe=Regex(
        "(?iu)\\b(?:Passwort|password|Kontostand|Konto|Portfolio|order bestätigen|confirm order|stückzahl kaufen)\\b")

    fun productRows(raw:String,expected:List<String>):List<String>? {
        if(expected.isEmpty() || expected.size>10 ||
           expected.distinct()!=expected || expected.any { !SeriesEvidence.validIsin(it) } ||
           raw.length>20000) return null
        val page=raw.replace(Regex("(?i)\\bSG(?=Gold)"),"SG ")
            .replace(Regex("\\s+")," ").trim()
        val starts=heading.findAll(page).map { it.range.first }.toList()
        if(starts.size!=expected.size) return null
        val result=mutableListOf<String>()
        for(index in starts.indices) {
            val end=if(index+1<starts.size) starts[index+1] else page.length
            val segment=page.substring(starts[index],end)
            if(segment.length>1000) return null
            val ids=isin.findAll(segment).toList()
            if(ids.size!=1 || ids[0].value!=expected[index]) return null
            val venue=footer.find(segment,ids[0].range.last+1) ?: return null
            val row=segment.substring(0,venue.range.last+1).trim()
            if(row.length>800 || unsafe.containsMatchIn(row)) return null
            result+=row
        }
        return result
    }

    fun read(crop:Bitmap,expected:List<String>,done:(JSONObject?)->Unit) {
        if(crop.isRecycled || crop.width<200 || crop.height<200 || crop.width*crop.height>16_000_000) {
            if(!crop.isRecycled) crop.recycle()
            done(null);return
        }
        val client=TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
        var scaled:Bitmap?=null
        var finished=false
        fun complete(value:JSONObject?) {
            if(finished)return
            finished=true
            runCatching { client.close() }
            scaled?.let { if(it!==crop && !it.isRecycled) it.recycle() }
            if(!crop.isRecycled)crop.recycle()
            done(value)
        }
        runCatching {
            client.process(InputImage.fromBitmap(crop,0)).addOnCompleteListener { first ->
                val rows=if(first.isSuccessful)
                    productRows(first.result.text,expected) else null
                if(rows==null) { complete(null);return@addOnCompleteListener }
                runCatching {
                    val width=minOf(1600,(crop.width*1.15).toInt())
                    val height=maxOf(1,(crop.height.toDouble()*width/crop.width).toInt())
                    scaled=Bitmap.createScaledBitmap(crop,width,height,true)
                    client.process(InputImage.fromBitmap(scaled!!,0)).addOnCompleteListener { second ->
                        val other=if(second.isSuccessful)
                            productRows(second.result.text,expected) else null
                        // Do not require identical OCR strings: the existing
                        // server grammar independently reconciles field votes.
                        val paired=if(other!=null && other.size==rows.size)
                            runCatching { JSONObject()
                                .put("expectedIsins",JSONArray(expected))
                                .put("passes",JSONArray().put(JSONArray(rows)).put(JSONArray(other)))
                            }.getOrNull() else null
                        complete(paired)
                    }
                }.onFailure { complete(null) }
            }
        }.onFailure { complete(null) }
    }
}
