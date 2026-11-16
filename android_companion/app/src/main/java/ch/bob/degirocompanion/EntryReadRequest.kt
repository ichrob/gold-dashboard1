package ch.bob.degirocompanion

import org.json.JSONObject
import java.time.Instant

internal data class EntryReadRequest(val requestId:String,val isin:String,
    val listBatchId:String,val listUploadedAt:String) {
    companion object {
        fun parse(value:JSONObject, now:Long):EntryReadRequest? = runCatching {
            val id=value.getString("requestId")
            val batch=value.getString("listBatchId")
            val isin=value.getString("isin")
            val at=value.getString("listUploadedAt")
            require(value.getString("action")=="entry_read")
            require(valid(id,isin,batch,at,now))
            EntryReadRequest(id,isin,batch,at)
        }.getOrNull()
        fun valid(id:String,isin:String,batch:String,at:String,now:Long):Boolean = runCatching {
            require(id.matches(Regex("[a-f0-9]{32}")) && batch.matches(Regex("[a-f0-9]{32}")))
            require(SeriesEvidence.validIsin(isin))
            require(now-Instant.parse(at).toEpochMilli() in 0..14*60*60*1000L)
            true
        }.getOrDefault(false)
    }
}
