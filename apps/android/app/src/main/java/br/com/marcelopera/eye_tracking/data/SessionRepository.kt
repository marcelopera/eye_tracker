package br.com.marcelopera.eye_tracking.data

import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.nio.charset.StandardCharsets
import java.util.UUID

class SessionRepository(private val filesDir: File) : SessionStore {
    private val writeLock = Mutex()

    override suspend fun createSession(experimentId: String): SessionHandle? =
        withContext(Dispatchers.IO) {
            val sessionId = UUID.randomUUID().toString()
            val directory = File(filesDir, "sessoes/$sessionId")
            if (directory.mkdirs()) SessionHandle(sessionId, directory) else null
        }

    override suspend fun save(
        handle: SessionHandle,
        experimentId: String,
        completed: Boolean,
        events: List<SessionEvent>,
    ): Boolean = writeLock.withLock {
        withContext(Dispatchers.IO) {
            try {
                val metadata = JSONObject()
                metadata.put("experimento", experimentId)
                metadata.put("coleta_local", handle.sessionId)
                metadata.put("estado", if (completed) "concluida" else "interrompida")
                metadata.put("envio", "pendente_backend")

                val eventArray = JSONArray()
                events.forEach { event ->
                    val item = JSONObject()
                    item.put("evento", event.name)
                    item.put("tempo_nanos", event.timeNanos)
                    item.put("relogio", event.clock)
                    event.data?.let { item.put("dados", it) }
                    eventArray.put(item)
                }
                metadata.put("eventos", eventArray)

                FileOutputStream(File(handle.directory, "sessao.json")).use { output ->
                    output.write(metadata.toString(2).toByteArray(StandardCharsets.UTF_8))
                }
                true
            } catch (error: Exception) {
                Log.e("EyeTracking", "Falha ao salvar metadados", error)
                false
            }
        }
    }
}
