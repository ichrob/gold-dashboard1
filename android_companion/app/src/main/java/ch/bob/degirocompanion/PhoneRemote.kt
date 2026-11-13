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
    // One redacted account-settings receipt awaits the next authenticated exchange.
    // Never persisted on Android; a failed network attempt retries the same receipt.
    private var pendingSettings:JSONObject?=null
    private var pendingSettingsCode=""
    private var lastReportedAutoFx:String?=null
    private var lastReportedProfile:String?=null
    private var locallyConfirmedProfile:String?=null
    // Only the specifically labelled local settings button enables one
    // local redacted read; normal product sessions never do this.
    private var settingsOnly=false
    private var localSettingsPending=false
    private var commands=PhoneCommandPolicy()
    var reader:((JSONObject?)->JSONObject)?=null
    var onStop:((String)->Unit)?=null
    var message="Handy-Sitzung ausgeschaltet."
        private set
    fun sessionId()=session
    fun active()=session.isNotEmpty() && SystemClock.elapsedRealtime()<deadline
    fun ownerConfirmationAllowed(profile:String)=active() && settingsOnly &&
        locallyConfirmedProfile==profile
    fun empty(code:String)=JSONObject().put("at",System.currentTimeMillis()/1000).put("code",code)
        .put("nodeCount",0).put("isins",JSONArray()).put("draft","")
        .put("diagnostics",ProductReadDiagnostics.report(SystemClock.elapsedRealtime()))
    fun start(c:Context, accountSettingsOnly:Boolean=false,
              ownerConfirmedProfile:String?=null) {
        require(ownerConfirmedProfile==null ||
            (accountSettingsOnly && ownerConfirmedProfile in setOf("BASIC","ACTIVE","TRADER"))) {
            "Ein bestätigtes Profil benötigt die ausdrückliche Nur-Lesen-Freigabe."
        }
        check(PhoneDiagnostics.paired(c)) { "Zuerst automatische Diagnose verbinden und im Browser freigeben." }
        check(reader!=null && ProductReadDiagnostics.connected) { "Lesedienst zuerst einschalten." }
        check(!active() && !busy && !ProductReadRequest.active(SystemClock.elapsedRealtime()) && !MorningReadRun.running && !GoldSearchRun.running) { "Aktuelle Prüfung zuerst stoppen." }
        session=UUID.randomUUID().toString().replace("-","");deadline=SystemClock.elapsedRealtime()+900000
        expires=System.currentTimeMillis()/1000+900;ack=null;pendingSettings=null;pendingSettingsCode=""
        lastReportedAutoFx=null;lastReportedProfile=null
        locallyConfirmedProfile=ownerConfirmedProfile
        settingsOnly=accountSettingsOnly;localSettingsPending=accountSettingsOnly
        commands=PhoneCommandPolicy();ProductReadSession.clear()
        message="Handy-Sitzung aktiv · höchstens 15 Minuten · STOPP oder Sperrtaste beendet sie."
        val id=session
        handler.postDelayed({ if(session==id)stop(c.applicationContext,"SESSION_EXPIRED") },900000)
        poll(c.applicationContext,session)
    }
    fun stop(c:Context,code:String="STOPPED") {
        if(session.isEmpty())return
        val old=session;session="";deadline=0;pendingSettings=null;message="Handy-Sitzung beendet: $code"
        onStop?.invoke(code)
        val body=payload(old,false,empty(code))
        settingsOnly=false;localSettingsPending=false;pendingSettingsCode=""
        lastReportedAutoFx=null;lastReportedProfile=null
        locallyConfirmedProfile=null
        network.execute { runCatching { PhoneDiagnostics.remoteExchange(c.applicationContext,body) } }
    }
    private fun payload(id:String,active:Boolean,observation:JSONObject)=JSONObject()
        .put("sessionId",id).put("expiresAt",expires).put("active",active)
        .put("observation",observation).put("ack",ack ?: JSONObject.NULL)
        .put("purpose",if(settingsOnly)"owner_account_settings" else "product_read")
    private fun poll(c:Context,id:String) {
        if(session!=id)return
        if(!active() || !PhoneDiagnostics.paired(c)) { stop(c,"SESSION_EXPIRED");return }
        val observation=runCatching { reader?.invoke(null) ?: empty("SERVICE_MISSING") }.getOrElse { empty("READ_ERROR") }
        if(PhoneObservationPolicy.mustStop(observation.optString("code"))) { stop(c,observation.optString("code"));return }
        // A user explicitly selected the separate account-settings button.
        // Only once, only after the foreground DEGIRO page has passed the
        // ordinary privacy guards, do the device-side read locally. This does
        // not use the remotely callable product-navigation actions.
        if(AccountSettingsEvidence.ownerReadAllowed(
                settingsOnly,localSettingsPending,observation.optString("code"))) {
            val receipt=runCatching {
                val localRequest=JSONObject().put("action","read_account_settings")
                locallyConfirmedProfile?.let {
                    localRequest.put("ownerConfirmedProfile",it)
                }
                reader?.invoke(localRequest)
            }.getOrNull()
            val receiptCode=receipt?.optString("code").orEmpty()
            if(receiptCode in setOf("ACCOUNT_SETTINGS_COMPLETE","ACCOUNT_SETTINGS_PARTIAL")) {
                pendingSettings=receipt?.optJSONObject("accountSettings")
                if(pendingSettings!=null) {
                    pendingSettingsCode=receiptCode
                    localSettingsPending=false
                }
            }
        }
        // Normal heartbeat never collects account data. A redacted enum
        // receipt from either explicit local consent OR an acknowledged,
        // separately delivered read command is retried until accepted.
        val sentSettings=pendingSettings
        if(sentSettings!=null) {
            observation.put("accountSettings",sentSettings)
            observation.put("code",if(settingsOnly) pendingSettingsCode
                 else ack?.optString("code","ACCOUNT_SETTINGS_PARTIAL"))
        }
        val body=payload(id,true,observation);busy=true
        network.execute {
            val result=runCatching { PhoneDiagnostics.remoteExchange(c,body) }
            handler.post {
                busy=false
                if(session!=id)return@post
                if(!active()) { stop(c,"SESSION_EXPIRED");return@post }
                result.onSuccess { response ->
                    if(response.optString("sessionId")!=id) { stop(c,"SESSION_MISMATCH");return@onSuccess }
                    if(sentSettings!=null && pendingSettings===sentSettings)pendingSettings=null
                    if(sentSettings!=null) {
                        if(sentSettings.has("autoFx") && !sentSettings.isNull("autoFx"))
                            lastReportedAutoFx=sentSettings.optString("autoFx")
                        if(sentSettings.has("feeProfile") && !sentSettings.isNull("feeProfile"))
                            lastReportedProfile=sentSettings.optString("feeProfile")
                    }
                    message=if(lastReportedAutoFx!=null || lastReportedProfile!=null) {
                        "DEGIRO-Einstellungen übertragen" +
                            (lastReportedProfile?.let { " · Profil: $it" } ?: "") +
                            (lastReportedAutoFx?.let {
                                " · AutoFX: " + when(it) {
                                    "ON" -> "EIN"
                                    "OFF" -> "AUS"
                                    else -> "UNBESTÄTIGT"
                                }
                            } ?: "") +
                            " · tatsächliche Orderkosten weiterhin unbestätigt."
                    } else "Handy-Sitzung verbunden · Status wird übertragen."
                    response.optJSONObject("command")?.let { command ->
                        val request=command.optString("requestId")
                        if(commands.accept(command.optString("sessionId"),id,request,command.optString("action"),command.optString("isin"),command.optLong("expiresAt"),System.currentTimeMillis()/1000)) {
                            val valid=command.optString("sessionId")==id && command.optLong("expiresAt")>System.currentTimeMillis()/1000
                            val action=command.optString("action")
                            val reply=if(valid && action!="stop") runCatching { reader?.invoke(command) }.getOrNull() else null
                            val code=if(!valid) "COMMAND_EXPIRED" else if(action=="stop") "STOPPED"
                                else reply?.optString("code") ?: "ACTION_ERROR"
                            if(action=="read_account_settings" && code in setOf(
                                    "ACCOUNT_SETTINGS_COMPLETE","ACCOUNT_SETTINGS_PARTIAL"))
                                pendingSettings=reply?.optJSONObject("accountSettings")
                            if(action=="read_account_settings")pendingSettingsCode=code
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
