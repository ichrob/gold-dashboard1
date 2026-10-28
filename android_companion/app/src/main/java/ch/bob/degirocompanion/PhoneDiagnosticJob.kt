package ch.bob.degirocompanion
import android.app.job.JobService
import android.app.job.JobParameters
import android.os.Handler
import android.os.Looper
import java.util.concurrent.ConcurrentHashMap

class PhoneDiagnosticJob:JobService() {
    private val active=ConcurrentHashMap<Int,JobParameters>()
    override fun onStartJob(params:JobParameters):Boolean {
        if(!PhoneDiagnostics.enabled(this))return false
        val report=runCatching { PhoneDiagnostics.nextReport(this) }.getOrElse { return false }
        active[params.jobId]=params
        Thread {
            val retry=PhoneDiagnostics.deliver(applicationContext,report)
            Handler(Looper.getMainLooper()).post {
                if(active.remove(params.jobId,params)) {
                    jobFinished(params,retry)
                    if(!retry && PhoneDiagnostics.enabled(this) && PhoneDiagnostics.hasPending(this)) {
                        // One follow-up for a state change during a successful send, not auth retry loops.
                        val prefs=getSharedPreferences("phone_diagnostics_v1",MODE_PRIVATE)
                        if(prefs.getString("lastAckId",null)==org.json.JSONObject(report).getString("reportId"))Handler(Looper.getMainLooper()).postDelayed({PhoneDiagnostics.queue(this)},1500)
                    }
                }
            }
        }.start()
        return true
    }
    override fun onStopJob(params:JobParameters):Boolean {
        active.remove(params.jobId,params);return PhoneDiagnostics.enabled(this)
    }
}
