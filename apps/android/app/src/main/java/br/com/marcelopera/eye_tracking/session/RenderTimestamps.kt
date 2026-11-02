package br.com.marcelopera.eye_tracking.session

import java.util.concurrent.ConcurrentHashMap

/** The codec uses Media3 stream offsets; only renderer metadata supplies media time. */
internal class RenderTimestamps {
    private val outputTimes = mutableMapOf<Int, Long>()
    private val mediaTimes = ConcurrentHashMap<Long, Long>()
    private var nextMediaTime: Long? = null
    fun output(index: Int, codecPts: Long) { outputTimes[index] = codecPts }
    fun metadata(mediaPts: Long) { nextMediaTime = mediaPts }
    fun release(index: Int, render: Boolean) {
        val codecPts = outputTimes.remove(index) ?: return
        if (render) {
            val mediaPts = nextMediaTime
            nextMediaTime = null
            if (mediaPts != null) mediaTimes[codecPts] = mediaPts
        }
    }
    fun rendered(codecPts: Long): Long? = mediaTimes.remove(codecPts)
    fun clear() { outputTimes.clear(); mediaTimes.clear(); nextMediaTime = null }
}
