package br.com.marcelopera.eye_tracking.session

import android.os.SystemClock

/** Bounds the elapsed-realtime reading corresponding to a monotonic-clock reading. */
data class ClockSample(val elapsedBeforeNanos: Long, val monotonicNanos: Long, val elapsedAfterNanos: Long)

fun readClockSample(): ClockSample {
    val before = SystemClock.elapsedRealtimeNanos()
    val monotonic = System.nanoTime()
    val after = SystemClock.elapsedRealtimeNanos()
    return ClockSample(before, monotonic, after)
}
