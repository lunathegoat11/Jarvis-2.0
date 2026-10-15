package com.lunathegoat11.jarvis

import org.json.JSONArray
import org.json.JSONObject

/** The things the AI can do on the phone, in each provider's tool format. */
object Tools {

    private data class Tool(val name: String, val desc: String, val params: Map<String, String>)

    private val tools = listOf(
        Tool("open_app", "Open an app by name, e.g. 'YouTube', 'Settings', 'Messages'.", mapOf("name" to "string")),
        Tool("go_home", "Go to the home screen.", emptyMap()),
        Tool("go_back", "Press the back button.", emptyMap()),
        Tool("read_screen", "Read the text and buttons currently on the screen.", emptyMap()),
        Tool("tap_text", "Tap the on-screen element that shows this text or label.", mapOf("text" to "string")),
        Tool("tap_at", "Tap at a point on the screen (pixels from the top-left).", mapOf("x" to "integer", "y" to "integer")),
        Tool("type_text", "Type text into the field that's focused. Tap it first.", mapOf("text" to "string")),
        Tool("swipe", "Swipe the screen 'up', 'down', 'left' or 'right'.", mapOf("direction" to "string")),
        Tool("open_url", "Open a web address in the browser.", mapOf("url" to "string")),
    )

    fun openAi(): JSONArray {
        val array = JSONArray()
        for (t in tools) {
            val params = JSONObject().put("type", "object")
            val props = JSONObject()
            t.params.forEach { (k, v) -> props.put(k, JSONObject().put("type", v)) }
            params.put("properties", props).put("required", JSONArray(t.params.keys.toList()))
            val fn = JSONObject().put("name", t.name).put("description", t.desc).put("parameters", params)
            array.put(JSONObject().put("type", "function").put("function", fn))
        }
        return array
    }

    fun anthropic(): JSONArray {
        val array = JSONArray()
        for (t in tools) {
            val schema = JSONObject().put("type", "object")
            val props = JSONObject()
            t.params.forEach { (k, v) -> props.put(k, JSONObject().put("type", v)) }
            schema.put("properties", props).put("required", JSONArray(t.params.keys.toList()))
            array.put(JSONObject().put("name", t.name).put("description", t.desc).put("input_schema", schema))
        }
        return array
    }
}
