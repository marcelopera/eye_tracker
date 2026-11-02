package br.com.marcelopera.eye_tracking.data

import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import java.util.UUID

class ApiClient(private val base: String) {
    private fun connection(path: String, method: String): HttpURLConnection =
        (URL(base.trimEnd('/') + path).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 15000
            readTimeout = 300000
            instanceFollowRedirects = false
        }

    private fun response(c: HttpURLConnection): String {
        val code = c.responseCode
        if (code !in 200..299) throw IllegalStateException("Servidor retornou HTTP $code")
        return c.inputStream.bufferedReader().use { it.readText() }
    }

    fun fetchExperiment(code: String, protocol: JSONObject, directory: File): Pair<String, String> {
        require(code.matches(Regex("[A-Fa-f0-9]{8}"))) { "Código de experimento inválido." }
        val experiment = connection("/api/published-experiments/$code", "GET").let { c ->
            try { JSONObject(response(c)) } finally { c.disconnect() }
        }
        require(equalJson(experiment.getJSONObject("protocol"), protocol)) { "Protocolo incompatível com esta versão do aplicativo." }
        val id = experiment.getString("id")
        UUID.fromString(id)
        val stimulus = experiment.getJSONObject("stimulus")
        val target = File(directory, "stimulus-$id.mp4")
        val temporary = File(directory, "stimulus-$id.tmp")
        val c = connection("/api/experiments/$id/stimulus", "GET")
        try {
            if (c.responseCode != 200) throw IllegalStateException("Falha ao baixar o estímulo: HTTP ${c.responseCode}")
            c.inputStream.use { input -> temporary.outputStream().use { input.copyTo(it) } }
            require(temporary.length() == stimulus.getLong("size") && hash(temporary) == stimulus.getString("sha256")) { "Integridade do estímulo inválida." }
            check(temporary.renameTo(target)) { "Não foi possível salvar o estímulo." }
        } finally { c.disconnect(); temporary.delete() }
        return id to target.toURI().toString()
    }

    fun upload(experimentId: String, participant: String, localId: String, directory: File): String {
        val video = File(directory, "face.mp4")
        val events = File(directory, "sessao.json")
        val videoHash = hash(video)
        val eventsHash = hash(events)
        val c = connection("/api/sessions", "POST")
        val serverId = try {
            c.doOutput = true
            c.setRequestProperty("Content-Type", "application/json")
            val body = JSONObject().put("experiment_id", experimentId).put("local_id", localId).put("participant_code", participant).toString()
            c.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            JSONObject(response(c)).getString("id").also { UUID.fromString(it) }
        } finally { c.disconnect() }
        val boundary = "eye-${UUID.randomUUID()}"
        val fields = listOf("video_sha256" to videoHash, "events_sha256" to eventsHash)
        fun field(name: String, value: String) = "--$boundary\r\nContent-Disposition: form-data; name=\"$name\"\r\n\r\n$value\r\n".toByteArray()
        fun header(name: String, filename: String, type: String) = "--$boundary\r\nContent-Disposition: form-data; name=\"$name\"; filename=\"$filename\"\r\nContent-Type: $type\r\n\r\n".toByteArray()
        val prefix = fields.map { field(it.first, it.second) }
        val vh = header("video", "face.mp4", "video/mp4")
        val eh = header("events", "sessao.json", "application/json")
        val separator = "\r\n".toByteArray()
        val end = "--$boundary--\r\n".toByteArray()
        val length = prefix.sumOf { it.size.toLong() } + vh.size + video.length() + separator.size + eh.size + events.length() + separator.size + end.size
        val upload = connection("/api/sessions/$serverId/files", "PUT")
        try {
            upload.doOutput = true
            upload.setRequestProperty("Content-Type", "multipart/form-data; boundary=$boundary")
            upload.setFixedLengthStreamingMode(length)
            upload.outputStream.use { out ->
                prefix.forEach { out.write(it) }
                out.write(vh); video.inputStream().use { it.copyTo(out) }; out.write(separator)
                out.write(eh); events.inputStream().use { it.copyTo(out) }; out.write(separator); out.write(end)
            }
            check(JSONObject(response(upload)).getBoolean("received"))
        } finally { upload.disconnect() }
        return serverId
    }

    private fun hash(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(1024 * 1024)
            while (true) { val count = input.read(buffer); if (count < 0) break; digest.update(buffer, 0, count) }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    private fun equalJson(a: Any?, b: Any?): Boolean = when {
        a is JSONObject && b is JSONObject -> {
            val keys = a.keys().asSequence().toSet()
            keys == b.keys().asSequence().toSet() && keys.all { equalJson(a.get(it), b.get(it)) }
        }
        a is JSONArray && b is JSONArray -> a.length() == b.length() && (0 until a.length()).all { equalJson(a.get(it), b.get(it)) }
        a is Number && b is Number -> a.toDouble() == b.toDouble()
        else -> a == b
    }
}
