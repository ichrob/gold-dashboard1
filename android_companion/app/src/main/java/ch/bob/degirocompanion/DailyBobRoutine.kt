package ch.bob.degirocompanion

import android.Manifest
import android.app.AlarmManager
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

/**
 * Only a user-approved, device-local daily health check and reminder.
 * Never launches a broker, scrapes other apps, taps a screen or sends data.
 * AlarmManager is intentionally inexact: Android may defer reminders.
 */
internal object DailyBobRoutine {
    private const val PREFS = "bob_device_routines_v1"
    private const val ENABLED = "enabled"
    private const val HOUR = "hour"
    private const val MINUTE = "minute"
    private const val LAST_RUN = "last_run"
    private const val LAST_OCR = "last_ocr"
    private const val CHANNEL = "bob_local_check"
    private const val REQUEST = 7401

    private fun prefs(context: Context) =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    private fun alarmIntent(context: Context): PendingIntent {
        val intent = Intent(context, DailyBobRoutineReceiver::class.java)
            .setAction("ch.bob.degirocompanion.LOCAL_CHECK")
        return PendingIntent.getBroadcast(
            context, REQUEST, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
    }

    fun enable(context: Context, hour: Int, minute: Int) {
        require(hour in 0..23 && minute in 0..59)
        prefs(context).edit().putBoolean(ENABLED, true).putInt(HOUR, hour)
            .putInt(MINUTE, minute).apply()
        scheduleNext(context)
    }

    fun stop(context: Context) {
        prefs(context).edit().putBoolean(ENABLED, false).apply()
        (context.getSystemService(Context.ALARM_SERVICE) as AlarmManager)
            .cancel(alarmIntent(context))
    }

    fun rearmAfterBoot(context: Context) { scheduleNext(context) }

    fun recordOcr(context: Context) {
        // Save only the local event time, never an image, ISIN, quote or account ID.
        prefs(context).edit().putLong(LAST_OCR, System.currentTimeMillis()).apply()
    }

    fun summary(context: Context): String {
        val state = prefs(context)
        if (!state.getBoolean(ENABLED, false)) return "Tagesroutine ausgeschaltet."
        val time = "%02d:%02d".format(
            Locale.ROOT, state.getInt(HOUR, 8), state.getInt(MINUTE, 0)
        )
        val lastRun = state.getLong(LAST_RUN, 0L)
        val lastOcr = state.getLong(LAST_OCR, 0L)
        fun formatted(timestamp: Long): String = if (timestamp == 0L) "noch nie" else
            SimpleDateFormat("dd.MM.yyyy HH:mm", Locale.GERMANY).format(Date(timestamp))
        return "Täglicher lokaler Check gegen $time (nicht minutengenau). " +
            "Letzter Check: ${formatted(lastRun)}. " +
            "Letzte bestätigte lokale OCR-Verarbeitung: ${formatted(lastOcr)}. " +
            "Keine automatische Brokerbedienung."
    }

    private fun scheduleNext(context: Context) {
        val p = prefs(context)
        val approved = p.getBoolean(ENABLED, false)
        if (!BobRoutinePolicy.permits(
                BobRoutinePolicy.Action.LOCAL_HEALTH_CHECK,
                BobRoutinePolicy.Origin.SCHEDULE, approved
            )) return
        val next = Calendar.getInstance().apply {
            set(Calendar.HOUR_OF_DAY, p.getInt(HOUR, 8))
            set(Calendar.MINUTE, p.getInt(MINUTE, 0))
            set(Calendar.SECOND, 0)
            set(Calendar.MILLISECOND, 0)
            if (timeInMillis <= System.currentTimeMillis() + 60_000L)
                add(Calendar.DAY_OF_YEAR, 1)
        }
        (context.getSystemService(Context.ALARM_SERVICE) as AlarmManager)
            .setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, next.timeInMillis, alarmIntent(context))
    }

    fun handleAlarm(context: Context) {
        if (!BobRoutinePolicy.permits(
                BobRoutinePolicy.Action.LOCAL_HEALTH_CHECK,
                BobRoutinePolicy.Origin.SCHEDULE,
                prefs(context).getBoolean(ENABLED, false)
            )) return
        // Deterministic work only: inspect own local event log and send a reminder.
        val p = prefs(context)
        val lastScan = p.getLong(LAST_OCR, 0L)
        val recentlyScanned = lastScan > 0L &&
            System.currentTimeMillis() - lastScan in 0L..(24L * 60 * 60 * 1000)
        p.edit().putLong(LAST_RUN, System.currentTimeMillis()).apply()
        scheduleNext(context)

        if (Build.VERSION.SDK_INT >= 33 &&
            context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED) return
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.createNotificationChannel(NotificationChannel(
            CHANNEL, "Bob: lokal freigegebene Routine", NotificationManager.IMPORTANCE_DEFAULT
        ))
        val openApp = PendingIntent.getActivity(
            context, REQUEST, Intent(context, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val description = if (recentlyScanned)
            "In den letzten 24 Stunden wurde eine Bildserie lokal geprüft. Bei Bedarf Bob öffnen."
        else "Noch keine aktuelle lokale Bildserie geprüft. Bitte Bilder selbst auswählen oder teilen."
        val notice = Notification.Builder(context, CHANNEL)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("Bob: lokaler Tagescheck")
            .setContentText(description)
            .setContentIntent(openApp)
            .setAutoCancel(true)
            .build()
        manager.notify(REQUEST, notice)
    }
}

class DailyBobRoutineReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        when (intent?.action) {
            Intent.ACTION_BOOT_COMPLETED -> DailyBobRoutine.rearmAfterBoot(context)
            "ch.bob.degirocompanion.LOCAL_CHECK" -> DailyBobRoutine.handleAlarm(context)
        }
    }
}
