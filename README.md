# Inkscape macOS MCP

Lets Claude, or any MCP client, edit the document open in Inkscape on macOS: draw elements, run inkex Python against the live document, read document and selection info, and take screenshots.

It is a macOS port of [Shriinivas/inkmcp](https://github.com/Shriinivas/inkmcp). The original reaches Inkscape over D-Bus, which macOS does not have.

## How it works

Inkscape has no AppleScript dictionary, so each request goes like this:

1. The MCP server writes the request to `~/Library/Caches/inkmcp/request.json`.
2. It brings Inkscape to the front and posts the extension's shortcut, Cmd+Shift+F12, to Inkscape's process as Quartz keyboard events.
3. The extension, running inside Inkscape, reads the request, edits the live document, and writes a response file beside it.
4. The server waits for the response and for the extension to exit, then answers.

The transport lives in [`extension/inkmcp/macos_bridge.py`](extension/inkmcp/macos_bridge.py).

## Requirements

- macOS, with Inkscape 1.4 in `/Applications` (tested with 1.4.3).
- Python 3.10 or newer for the server, such as Homebrew's `python3.13`. The extension itself runs in Inkscape's bundled Python.

## Install

1. Link the extension into Inkscape's extensions folder:

   ```bash
   ln -s "$PWD/extension" ~/Library/Application\ Support/org.inkscape.Inkscape/config/inkscape/extensions/inkscape-macos-mcp
   ```

2. Bind the shortcut. If you have no custom Inkscape shortcuts yet, copy the file:

   ```bash
   mkdir -p ~/Library/Application\ Support/org.inkscape.Inkscape/config/inkscape/keys
   cp keys/default.xml ~/Library/Application\ Support/org.inkscape.Inkscape/config/inkscape/keys/default.xml
   ```

   If you already have that file, add the `<bind>` line from [`keys/default.xml`](keys/default.xml) to it instead.

3. Register the server with your MCP client. For Claude Code:

   ```bash
   claude mcp add --scope user inkscape -- "$PWD/extension/inkmcp/run_inkscape_mcp.sh"
   ```

   The first start creates the server's virtual environment in `extension/inkmcp/venv`.

4. Allow keyboard events. In System Settings > Privacy & Security > Accessibility, add and enable the app that runs the server. For Claude Code inside the Claude desktop app, that is Claude Code's own `claude.app`, not Claude itself: `~/Library/Application Support/Claude/claude-code/<version>/<hash>/claude.app`. After a Claude Code update you may need to add the new one.

5. Quit and reopen Inkscape so it loads the extension and the shortcut, then open a document window.

Check it from the command line:

```bash
extension/inkmcp/venv/bin/python extension/inkmcp/inkmcpcli.py get-info ""
```

## Use

- Keep a document window open in Inkscape, with no dialog in front of it.
- Inkscape comes to the front on every request.
- Errors say what to fix: Inkscape not running, keyboard events not allowed, or the extension not picking up the request.

## Changes from inkmcp v1.0.0

Modified on 2026-11-06 for macOS:

- Added `extension/inkmcp/macos_bridge.py`, which replaces the D-Bus calls with the shortcut transport above.
- `inkscape_mcp_server.py` and `inkmcpcli.py` send requests through the bridge. `inkscape_mcp.py` reads them from the bridge's request file.
- `export_operations.py` exports with Inkscape's own binary, because an Inkscape opened from Finder has no `inkscape` on its PATH.
- `run_inkscape_mcp.sh` finds Python 3.10 or newer, keeps setup output off the MCP stream, and drops the Linux D-Bus variables.
- `requirements.txt` pins `mcp>=1.2,<2`, the SDK version the server is written against. The server does not import inkex, which comes with Inkscape.
- Added `keys/default.xml` for the shortcut.

## License

AGPL-3.0, the license of the original inkmcp. See [LICENSE](LICENSE).
