"""Browsing the web in your own browser: open tabs, read pages, click links
and buttons, fill in boxes.

Jarvis talks to Safari or Chrome (also Brave and Edge) through AppleScript
and reads the page itself, so it clicks the actual link or button by number
instead of guessing where to click on a screenshot. You stay signed in to
your sites, and you can watch it work.

The browser has to allow this once:
  Safari: Settings > Advanced > tick "Show features for web developers",
          then Develop menu > Allow JavaScript from Apple Events.
  Chrome: View > Developer > Allow JavaScript from Apple Events.
"""

import json
import subprocess
import time

from .config import config

CHROME_LIKE = ("Google Chrome", "Brave Browser", "Microsoft Edge")
SUPPORTED = ("Safari", *CHROME_LIKE)

# How much of a page's text the AI gets to read at once.
MAX_TEXT = 6000
MAX_ELEMENTS = 80

# Numbers the interactive parts of the page (data-jarvis-id) and reports
# them with the page's visible text.
READ_PAGE_JS = """
(() => {
  document.querySelectorAll('[data-jarvis-id]').forEach(e => e.removeAttribute('data-jarvis-id'));
  const visible = e => {
    const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const inView = e => {
    const r = e.getBoundingClientRect();
    return r.bottom > -200 && r.top < innerHeight + 800;
  };
  const label = e => (e.getAttribute('aria-label') || e.innerText || e.value || e.placeholder ||
    e.title || e.alt || e.name || '').replace(/\\s+/g, ' ').trim().slice(0, 80);
  const kinds = 'a[href], button, input:not([type=hidden]), textarea, select, ' +
    '[role=button], [role=link], [role=tab], [role=menuitem], [role=checkbox], [contenteditable=true]';
  const items = [];
  let n = 0;
  for (const e of document.querySelectorAll(kinds)) {
    if (items.length >= %(max_elements)d) break;
    if (!visible(e) || !inView(e)) continue;
    n += 1;
    e.setAttribute('data-jarvis-id', n);
    const tag = e.tagName.toLowerCase();
    const kind = tag === 'a' ? 'link' : tag === 'input' ? 'input:' + (e.type || 'text') :
      (e.getAttribute('role') || tag);
    items.push('[' + n + '] ' + kind + ' "' + label(e) + '"');
  }
  const text = (document.body ? document.body.innerText : '').replace(/\\n{3,}/g, '\\n\\n');
  return JSON.stringify({
    title: document.title, url: location.href,
    scroll: Math.round(scrollY) + ' of ' + Math.max(0, document.body.scrollHeight - innerHeight),
    text: text.slice(0, %(max_text)d), more: text.length > %(max_text)d, items: items
  });
})()
""" % {"max_elements": MAX_ELEMENTS, "max_text": MAX_TEXT}


def _find(number: int) -> str:
    return f"document.querySelector('[data-jarvis-id=\"{int(number)}\"]')"


CLICK_JS = """
(() => {
  const e = %(find)s;
  if (!e) return 'missing';
  e.scrollIntoView({block: 'center'});
  e.focus && e.focus();
  e.click();
  return 'ok';
})()
"""

# Sets the value the way typing would, so sites built with React and the
# like notice the change, then optionally submits it.
TYPE_JS = """
(() => {
  const e = %(find)s;
  if (!e) return 'missing';
  e.scrollIntoView({block: 'center'});
  e.focus();
  const text = %(text)s;
  if (e.isContentEditable) {
    document.execCommand('selectAll', false, null);
    document.execCommand('insertText', false, text);
  } else {
    const proto = e.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(e, text);
    e.dispatchEvent(new Event('input', {bubbles: true}));
    e.dispatchEvent(new Event('change', {bubbles: true}));
  }
  if (%(submit)s) {
    const options = {key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true};
    e.dispatchEvent(new KeyboardEvent('keydown', options));
    e.dispatchEvent(new KeyboardEvent('keypress', options));
    e.dispatchEvent(new KeyboardEvent('keyup', options));
    if (e.form) { e.form.requestSubmit ? e.form.requestSubmit() : e.form.submit(); }
  }
  return 'ok';
})()
"""


def _quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _osascript(script: str, timeout: float = 20) -> str:
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        message = result.stderr.strip()
        lowered = message.lower()
        if "allow javascript from apple events" in lowered or "javascript through applescript" in lowered:
            raise RuntimeError(
                "The browser hasn't allowed Jarvis to read pages yet. In Safari: Settings > "
                "Advanced > tick 'Show features for web developers', then Develop > Allow "
                "JavaScript from Apple Events. In Chrome: View > Developer > Allow JavaScript "
                "from Apple Events."
            )
        if "-1743" in message or "not authori" in lowered:
            raise RuntimeError(
                "macOS hasn't let Jarvis control the browser yet. In System Settings > Privacy & "
                "Security > Automation, turn on the browser under Terminal (or Jarvis)."
            )
        raise RuntimeError(message or "The browser didn't respond.")
    return result.stdout.strip()


def _running(app: str) -> bool:
    script = f'application {_quote(app)} is running'
    try:
        return _osascript(script, timeout=5) == "true"
    except Exception:
        return False


def pick_browser() -> str:
    """The browser in front if it's one Jarvis can drive, else one that's
    open, else Safari."""
    try:
        front = _osascript(
            'tell application "System Events" to get name of first application process '
            "whose frontmost is true",
            timeout=5,
        )
    except Exception:
        front = ""
    if front in SUPPORTED:
        return front
    for app in SUPPORTED:
        if _running(app):
            return app
    return "Safari"


def _run_js(browser: str, js: str) -> str:
    js = " ".join(line.strip() for line in js.strip().splitlines())
    if browser == "Safari":
        script = f'tell application "Safari" to do JavaScript {_quote(js)} in current tab of front window'
    else:
        script = f"tell application {_quote(browser)} to execute active tab of front window javascript {_quote(js)}"
    return _osascript(script)


def _wait_for_load(browser: str, seconds: float = 10) -> None:
    deadline = time.monotonic() + seconds
    time.sleep(0.5)
    while time.monotonic() < deadline:
        try:
            if _run_js(browser, "document.readyState") == "complete":
                time.sleep(0.4)  # many pages keep drawing for a moment
                return
        except RuntimeError:
            pass
        time.sleep(0.4)


def _page(browser: str) -> str:
    data = json.loads(_run_js(browser, READ_PAGE_JS))
    lines = [f"{data['title']}\n{data['url']}\n(scrolled {data['scroll']} pixels)"]
    if data["items"]:
        lines.append("Things you can click or type into, by number:\n" + "\n".join(data["items"]))
    lines.append("Page text:\n" + data["text"] + ("\n[more below; scroll down to read on]" if data["more"] else ""))
    return "\n\n".join(lines)


def _require_mac() -> None:
    if not config.is_mac:
        raise RuntimeError("Browsing the web this way needs a Mac for now.")


# ---- what the tools call ------------------------------------------------------


def open_page(url: str, new_tab: bool = True) -> str:
    _require_mac()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    browser = pick_browser()
    if browser == "Safari":
        if new_tab:
            script = (
                'tell application "Safari"\n'
                "    activate\n"
                f"    if (count of windows) = 0 then make new document\n"
                f"    tell front window to set current tab to (make new tab with properties {{URL:{_quote(url)}}})\n"
                "end tell"
            )
        else:
            script = (
                'tell application "Safari"\n    activate\n'
                f"    if (count of windows) = 0 then make new document\n"
                f"    set URL of current tab of front window to {_quote(url)}\nend tell"
            )
    else:
        target = (
            f"make new tab at end of tabs with properties {{URL:{_quote(url)}}}"
            if new_tab
            else f"set URL of active tab to {_quote(url)}"
        )
        script = (
            f"tell application {_quote(browser)}\n    activate\n"
            "    if (count of windows) = 0 then make new window\n"
            f"    tell front window to {target}\nend tell"
        )
    _osascript(script)
    _wait_for_load(browser)
    return _page(browser)


def read_page() -> str:
    _require_mac()
    return _page(pick_browser())


def click(number: int) -> str:
    _require_mac()
    browser = pick_browser()
    if _run_js(browser, CLICK_JS % {"find": _find(number)}) == "missing":
        raise RuntimeError(f"There's no item {number} on the page now. Read the page again.")
    _wait_for_load(browser)
    return "Clicked.\n\n" + _page(browser)


def type_into(number: int, text: str, submit: bool) -> str:
    _require_mac()
    browser = pick_browser()
    js = TYPE_JS % {"find": _find(number), "text": json.dumps(text), "submit": "true" if submit else "false"}
    if _run_js(browser, js) == "missing":
        raise RuntimeError(f"There's no item {number} on the page now. Read the page again.")
    if submit:
        _wait_for_load(browser)
        return "Typed it and submitted.\n\n" + _page(browser)
    return "Typed it."


def scroll(direction: str) -> str:
    _require_mac()
    browser = pick_browser()
    step = {"down": "innerHeight * 0.85", "up": "-innerHeight * 0.85"}.get(direction)
    if step is None:
        js = "scrollTo(0, 0)" if direction == "top" else "scrollTo(0, document.body.scrollHeight)"
    else:
        js = f"scrollBy(0, {step})"
    _run_js(browser, js)
    time.sleep(0.5)
    return _page(browser)


def go_back() -> str:
    _require_mac()
    browser = pick_browser()
    _run_js(browser, "history.back()")
    _wait_for_load(browser)
    return _page(browser)
