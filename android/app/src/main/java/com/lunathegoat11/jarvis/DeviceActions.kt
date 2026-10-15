package com.lunathegoat11.jarvis

/** What Jarvis can do to the phone. Implemented by the accessibility service. */
interface DeviceActions {
    fun openApp(name: String): String
    fun openUrl(url: String): String
    fun goHome(): String
    fun goBack(): String
    fun readScreen(): String
    fun tapText(text: String): String
    fun tapAt(x: Int, y: Int): String
    fun typeText(text: String): String
    fun swipe(direction: String): String
}

/** Stand-in used before the accessibility service is turned on. */
class NoDevice : DeviceActions {
    private val off = "Turn on Jarvis in Settings > Accessibility so I can control the phone."
    override fun openApp(name: String) = off
    override fun openUrl(url: String) = off
    override fun goHome() = off
    override fun goBack() = off
    override fun readScreen() = off
    override fun tapText(text: String) = off
    override fun tapAt(x: Int, y: Int) = off
    override fun typeText(text: String) = off
    override fun swipe(direction: String) = off
}
