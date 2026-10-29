package ch.bob.degirocompanion

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import org.json.JSONObject
import org.json.JSONArray
import java.util.UUID
import java.util.concurrent.Executors

/** Memory-only, locally started session. No background restart or arbitrary UI commands. */
internal object PhoneRemote {
    private val handler=Handler(Looper.getMainLooper())
    private val network=Executors.newSingleThreadExecutor()
    private var session=""
    private var deadline=0L
    private var expires=0L
    private var busy=false
    private var ack:JSONObject?=null
    private var commands=PhoneCommandPolicy()
    var reader:((JSONObject?)->JSONObject)?=null
    var onStop:((String)->Unit)?=null
    var message="Handy-Sitzung ausgeschaltet."
        private set
    fun sessionId()=session
    fun active()=session.isNotEmpty() && SystemClock.elapsedRealtime()<deadline
    fun empty(code:String)=JSONObject().put("at",System.currentTimeMillis()/1000).put("code",code)
        .put("nodeCount",0).put("isins",JSONArray()).put("draft","")
        .put("diagnostics",ProductReadDiagnostics.report(SystemClock.elapsedRealtime()))
    fun start(c:Context) {
        check(PhoneDiagnostics.paired(c)) { "Zuerst automatische Diagnose verbinden und im Browser freigeben." }
        check(reader!=null && ProductReadDiagnostics.connected) { "Lesedienst zuerst einschalten." }
        check(!active() && !busy && !ProductReadRequest.active(SystemClock.elapsedRealtime()) && !MorningReadRun.running && !GoldSearchRun.running) { "Aktuelle Prüfung zuerst stoppen." }
        session=UUID.randomUUID().toString().replace("-","");deadline=SystemClock.elapsedRealtime()+900000
        expires=System.currentTimeMillis()/1000+900;ack=null;commands=PhoneCommandPolicy();ProductReadSession.clear()
        message="Handy-Sitzung aktiv · höchstens 15 Minuten · STOPP oder Sperrtaste beendet sie."
        val id=session
        handler.postDelayed({ if(session==id)stop(c.applicationContext,"SESSION_EXPIRED") },900000)
        poll(c.applicationContext,session)
    }
    fun stop(c:Context,code:String="STOPPED") {
        if(session.isEmpty())return
        val old=session;session="";deadline=0;message="Handy-Sitzung beendet: $code"
        onStop?.invoke(code)
        val body=payload(old,false,empty(code))
        network.execute { runCatching { PhoneDiagnostics.remoteExchange(c.applicationContext,body) } }
    }
    private fun payload(id:String,active:Boolean,observation:JSONObject)=JSONObject()
        .put("sessionId",id).put("expiresAt",expires).put("active",active)
        .put("observation",observation).put("ack",ack ?: JSONObject.NULL)
    private fun poll(c:Context,id:String) {
        if(session!=id)return
        if(!active() || !PhoneDiagnostics.paired(c)) { stop(c,"SESSION_EXPIRED");return }
        val observation=runCatching { reader?.invoke(null) ?: empty("SERVICE_MISSING") }.getOrElse { empty("READ_ERROR") }
        if(PhoneObservationPolicy.mustStop(observation.optString("code"))) { stop(c,observation.optString("code"));return }
        val body=payload(id,true,observation);busy=true
        network.execute {
            val result=runCatching { PhoneDiagnostics.remoteExchange(c,body) }
            handler.post {
                busy=false
                if(session!=id)return@post
                if(!active()) { stop(c,"SESSION_EXPIRED");return@post }
                result.onSuccess { response ->
                    if(response.optString("sessionId")!=id) { stop(c,"SESSION_MISMATCH");return@onSuccess }
                    message="Handy-Sitzung verbunden · Status wird übertragen."
                    response.optJSONObject("command")?.let { command ->
                        val request=command.optString("requestId")
                        if(commands.accept(command.optString("sessionId"),id,request,command.optString("action"),command.optString("isin"),command.optLong("expiresAt"),System.currentTimeMillis()/1000)) {
                            val valid=command.optString("sessionId")==id && command.optLong("expiresAt")>System.currentTimeMillis()/1000
                            val code=if(!valid) "COMMAND_EXPIRED" else if(command.optString("action")=="stop") "STOPPED"
                                else runCatching { reader?.invoke(command)?.optString("code") ?: "SERVICE_MISSING" }.getOrDefault("ACTION_ERROR")
                            ack=JSONObject().put("requestId",request).put("code",code)
                            if(command.optString("action")=="stop")stop(c,"REMOTE_STOP")
                        }
                    }
                }.onFailure { message="Handy-Sitzung: Verbindung unterbrochen; noch kein Ausführungsnachweis." }
                if(session==id)handler.postDelayed({poll(c,id)},2000)
            }
        }
    }
}
