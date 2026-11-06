"""Hands a request to the inkmcp extension inside the running Inkscape, the macOS way.

Inkscape has no AppleScript dictionary, so a request travels like this:

1. The request is written to REQUEST_FILE in ~/Library/Caches/inkmcp.
2. Inkscape is brought to the front through Launch Services, because it ignores
   keyboard events while in the background. The extension's keyboard shortcut
   (Cmd+Shift+F12, bound in Inkscape's keys/default.xml) is then posted to
   Inkscape's process alone as Quartz keyboard events.
3. The extension reads and deletes the request, edits the live document, and
   writes the response file named in the request.

Posting keyboard events needs Accessibility permission for the app that runs
this: System Settings > Privacy & Security > Accessibility.

The extension imports REQUEST_FILE from here, inside Inkscape's own Python, so
this module keeps to the standard library and loads macOS frameworks lazily.
"""

import ctypes
import json
import os
import subprocess
import time
import uuid
from typing import Any, Dict, Optional

BUNDLE_ID = "org.inkscape.Inkscape"
IPC_DIR = os.path.expanduser("~/Library/Caches/inkmcp")
REQUEST_FILE = os.path.join(IPC_DIR, "request.json")
EXTENSION_SCRIPT = "inkscape_mcp.py"

SHORTCUT_LABEL = "Cmd+Shift+F12"
SHORTCUT_KEYCODE = 111  # kVK_F12
SHORTCUT_FLAGS = 0x100000 | 0x20000  # kCGEventFlagMaskCommand | kCGEventFlagMaskShift

PICKUP_SECONDS = 2.0
RESPONSE_SECONDS = 60.0


class BridgeError(Exception):
    """Inkscape could not be reached or did not answer."""


def inkscape_pid() -> Optional[int]:
    """The running Inkscape app's pid, or None when it is not running."""
    out = subprocess.run(
        ["lsappinfo", "info", "-only", "pid", "-app", BUNDLE_ID],
        capture_output=True, text=True,
    ).stdout
    digits = "".join(c for c in out.split("=")[-1] if c.isdigit())
    return int(digits) if digits else None


def accessibility_trusted(prompt: bool = False) -> bool:
    """Whether this process may post keyboard events. prompt asks macOS to offer the setting."""
    hi = ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
    if not prompt:
        hi.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(hi.AXIsProcessTrusted())
    cf = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    cf.CFDictionaryCreate.restype = ctypes.c_void_p
    cf.CFDictionaryCreate.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
                                      ctypes.POINTER(ctypes.c_void_p), ctypes.c_long,
                                      ctypes.c_void_p, ctypes.c_void_p]
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    keys = (ctypes.c_void_p * 1)(ctypes.c_void_p.in_dll(hi, "kAXTrustedCheckOptionPrompt").value)
    values = (ctypes.c_void_p * 1)(ctypes.c_void_p.in_dll(cf, "kCFBooleanTrue").value)
    options = cf.CFDictionaryCreate(
        None, keys, values, 1,
        ctypes.addressof(ctypes.c_char.in_dll(cf, "kCFTypeDictionaryKeyCallBacks")),
        ctypes.addressof(ctypes.c_char.in_dll(cf, "kCFTypeDictionaryValueCallBacks")))
    hi.AXIsProcessTrustedWithOptions.restype = ctypes.c_bool
    hi.AXIsProcessTrustedWithOptions.argtypes = [ctypes.c_void_p]
    trusted = bool(hi.AXIsProcessTrustedWithOptions(options))
    cf.CFRelease(options)
    return trusted


def _post_shortcut(pid: int) -> None:
    """Posts the shortcut to Inkscape's process only, so no other app can receive it."""
    cg = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    cf = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    cg.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
    cg.CGEventCreateKeyboardEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_bool]
    cg.CGEventSetFlags.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    cg.CGEventPostToPid.argtypes = [ctypes.c_int, ctypes.c_void_p]
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    for key_down in (True, False):
        event = cg.CGEventCreateKeyboardEvent(None, SHORTCUT_KEYCODE, key_down)
        cg.CGEventSetFlags(event, SHORTCUT_FLAGS)
        cg.CGEventPostToPid(pid, event)
        cf.CFRelease(event)
        time.sleep(0.03)


def _frontmost_bundle_id() -> str:
    front = subprocess.run(["lsappinfo", "front"], capture_output=True, text=True).stdout.strip()
    out = subprocess.run(["lsappinfo", "info", "-only", "bundleid", front],
                         capture_output=True, text=True).stdout
    return out.split("=")[-1].strip().strip('"')


def _bring_inkscape_forward() -> None:
    subprocess.run(["open", "-b", BUNDLE_ID], check=False)
    deadline = time.time() + 3.0
    while time.time() < deadline and _frontmost_bundle_id() != BUNDLE_ID:
        time.sleep(0.05)
    if _frontmost_bundle_id() != BUNDLE_ID:
        raise BridgeError("Inkscape would not come to the front.")
    time.sleep(0.15)


def _extension_running() -> bool:
    return subprocess.run(["pgrep", "-f", EXTENSION_SCRIPT], capture_output=True).returncode == 0


def _picked_up(seconds: float) -> bool:
    """Waits for the extension to take the request: it deletes the request file when it reads it."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        if not os.path.exists(REQUEST_FILE) or _extension_running():
            return True
        time.sleep(0.05)
    return False


def _wait_for_extension_exit(seconds: float) -> None:
    """Lets Inkscape take the edited document back before the next request can arrive."""
    deadline = time.time() + seconds
    while time.time() < deadline and _extension_running():
        time.sleep(0.05)
    time.sleep(0.2)


def check_ready() -> None:
    """Raises BridgeError with the fix when a request could not reach Inkscape."""
    if inkscape_pid() is None:
        raise BridgeError("Inkscape is not running. Open Inkscape with a document window.")
    if not accessibility_trusted():
        accessibility_trusted(prompt=True)
        raise BridgeError(
            "macOS is blocking keyboard events from this app. Allow it in System Settings > "
            "Privacy & Security > Accessibility, then try again.")


def send(operation: Dict[str, Any]) -> Dict[str, Any]:
    """Runs one operation in Inkscape and returns the extension's response."""
    check_ready()
    os.makedirs(IPC_DIR, exist_ok=True)
    response_file = os.path.join(IPC_DIR, f"response-{uuid.uuid4().hex}.json")
    request = dict(operation, response_file=response_file)
    staging = REQUEST_FILE + ".tmp"
    with open(staging, "w") as f:
        json.dump(request, f)
    os.replace(staging, REQUEST_FILE)
    try:
        if _frontmost_bundle_id() != BUNDLE_ID:
            _bring_inkscape_forward()
        pid = inkscape_pid()
        _post_shortcut(pid)
        if not _picked_up(PICKUP_SECONDS):
            # A shortcut sent while the window was still taking focus can be lost: send it once more.
            _post_shortcut(pid)
            if not _picked_up(PICKUP_SECONDS):
                raise BridgeError(
                    f"Inkscape did not run the MCP extension. Check that a document window is "
                    f"open with no dialog in front, and that {SHORTCUT_LABEL} runs the extension.")
        deadline = time.time() + RESPONSE_SECONDS
        while not os.path.exists(response_file):
            if time.time() > deadline:
                raise BridgeError(f"The MCP extension gave no answer within {RESPONSE_SECONDS:.0f} s.")
            time.sleep(0.05)
        _wait_for_extension_exit(10.0)
        with open(response_file) as f:
            return json.load(f)
    finally:
        for path in (REQUEST_FILE, response_file):
            if os.path.exists(path):
                os.remove(path)
