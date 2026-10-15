package com.lunathegoat11.jarvis

import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.net.HttpURLConnection
import java.net.URL

/**
 * Talks to the AI. NVIDIA and Ollama use the OpenAI chat-completions format;
 * Anthropic uses its Messages API. The AI can call Android tools (open an app,
 * tap, type, read the screen) which run through the accessibility service.
 */
class Brain(private val settings: Settings, private val device: DeviceActions) {

    private val history = mutableListOf<JSONObject>()
    private var lastUsed = 0L
    private val memoryMs = 15 * 60 * 1000L

    private val systemPrompt = """
        You are Jarvis, a voice assistant on the user's Android phone. Carry out
        what they say with your tools, then reply in one or two short spoken
        sentences with no markdown. You can open apps, go home or back, tap,
        type, swipe, and read what's on the screen. To do something inside an
        app (play a video, send a message), open the app, read the screen, then
        tap or type step by step, reading the screen again after each step. Don't
        buy anything, send messages or delete things unless asked to exactly
        that. If a request is unclear or you can't do it, say so.
    """.trimIndent()

    fun run(command: String, onReply: (String) -> Unit) {
        val now = System.currentTimeMillis()
        if (now - lastUsed > memoryMs) history.clear()
        lastUsed = now
        history.add(userMsg(command))

        try {
            for (round in 0 until 12) {
                val reply = step()
                history.add(reply.assistant)
                if (reply.calls.isEmpty()) {
                    onReply(reply.text.ifBlank { "Done." })
                    return
                }
                val results = JSONArray()
                for (call in reply.calls) {
                    val output = runTool(call)
                    results.put(toolResult(call, output))
                }
                history.add(JSONObject().put("role", "user").put("content", results.toString()))
            }
            onReply("That took too many steps, so I stopped.")
        } catch (e: Exception) {
            onReply("Something went wrong: ${e.message}")
        }
    }

    private fun runTool(call: ToolCall): String = try {
        when (call.name) {
            "open_app" -> device.openApp(call.args.getString("name"))
            "go_home" -> device.goHome()
            "go_back" -> device.goBack()
            "read_screen" -> device.readScreen()
            "tap_text" -> device.tapText(call.args.getString("text"))
            "tap_at" -> device.tapAt(call.args.getInt("x"), call.args.getInt("y"))
            "type_text" -> device.typeText(call.args.getString("text"))
            "swipe" -> device.swipe(call.args.getString("direction"))
            "open_url" -> device.openUrl(call.args.getString("url"))
            else -> "Unknown tool: ${call.name}"
        }
    } catch (e: Exception) {
        "Failed: ${e.message}"
    }

    // ---- provider plumbing ---------------------------------------------------

    private data class ToolCall(val id: String, val name: String, val args: JSONObject)
    private data class Reply(val text: String, val calls: List<ToolCall>, val assistant: JSONObject)

    private fun step(): Reply =
        if (settings.provider == "anthropic") stepAnthropic() else stepOpenAi()

    private fun userMsg(text: String) =
        JSONObject().put("role", "user").put("content", text)

    private fun toolResult(call: ToolCall, output: String): JSONObject =
        if (settings.provider == "anthropic")
            JSONObject().put("type", "tool_result").put("tool_use_id", call.id).put("content", output)
        else
            JSONObject().put("role", "tool").put("tool_call_id", call.id).put("content", output)

    private fun stepOpenAi(): Reply {
        val body = JSONObject()
        body.put("model", settings.defaultModel())
        body.put("max_tokens", 4096)
        val messages = JSONArray()
        messages.put(JSONObject().put("role", "system").put("content", systemPrompt))
        history.forEach { messages.put(it) }
        body.put("messages", messages)
        body.put("tools", Tools.openAi())
        if (settings.provider == "nvidia") {
            body.put("extra_body", JSONObject())  // ignored by server; placeholder
        }

        val response = postJson("${settings.baseUrl()}/chat/completions", body, bearer = settings.apiKey)
        val message = response.getJSONArray("choices").getJSONObject(0).getJSONObject("message")
        val text = Speech.stripThink(message.optString("content", "")).trim()

        val calls = mutableListOf<ToolCall>()
        val assistant = JSONObject().put("role", "assistant").put("content", message.optString("content", ""))
        val toolCalls = message.optJSONArray("tool_calls")
        if (toolCalls != null) {
            assistant.put("tool_calls", toolCalls)
            for (i in 0 until toolCalls.length()) {
                val tc = toolCalls.getJSONObject(i)
                val fn = tc.getJSONObject("function")
                val args = try { JSONObject(fn.optString("arguments", "{}")) } catch (e: Exception) { JSONObject() }
                calls.add(ToolCall(tc.getString("id"), fn.getString("name"), args))
            }
        }
        return Reply(text, calls, assistant)
    }

    private fun stepAnthropic(): Reply {
        val body = JSONObject()
        body.put("model", settings.defaultModel())
        body.put("max_tokens", 4096)
        body.put("system", systemPrompt)
        val messages = JSONArray()
        history.forEach { messages.put(it) }
        body.put("messages", messages)
        body.put("tools", Tools.anthropic())

        val conn = (URL("${settings.baseUrl()}/messages").openConnection() as HttpURLConnection)
        conn.requestMethod = "POST"
        conn.doOutput = true
        conn.setRequestProperty("Content-Type", "application/json")
        conn.setRequestProperty("x-api-key", settings.apiKey)
        conn.setRequestProperty("anthropic-version", "2023-06-01")
        conn.outputStream.use { it.write(body.toString().toByteArray()) }
        val response = JSONObject(readBody(conn))

        val content = response.getJSONArray("content")
        val sb = StringBuilder()
        val calls = mutableListOf<ToolCall>()
        for (i in 0 until content.length()) {
            val block = content.getJSONObject(i)
            when (block.getString("type")) {
                "text" -> sb.append(block.getString("text"))
                "tool_use" -> calls.add(
                    ToolCall(block.getString("id"), block.getString("name"), block.getJSONObject("input"))
                )
            }
        }
        val assistant = JSONObject().put("role", "assistant").put("content", content)
        return Reply(sb.toString().trim(), calls, assistant)
    }

    private fun postJson(url: String, body: JSONObject, bearer: String): JSONObject {
        val conn = (URL(url).openConnection() as HttpURLConnection)
        conn.requestMethod = "POST"
        conn.doOutput = true
        conn.connectTimeout = 15000
        conn.readTimeout = 60000
        conn.setRequestProperty("Content-Type", "application/json")
        if (bearer.isNotEmpty()) conn.setRequestProperty("Authorization", "Bearer $bearer")
        conn.outputStream.use { it.write(body.toString().toByteArray()) }
        return JSONObject(readBody(conn))
    }

    private fun readBody(conn: HttpURLConnection): String {
        val stream = if (conn.responseCode in 200..299) conn.inputStream else conn.errorStream
        val text = stream.bufferedReader().use(BufferedReader::readText)
        if (conn.responseCode !in 200..299) {
            throw RuntimeException("AI error ${conn.responseCode}: ${text.take(300)}")
        }
        return text
    }
}
