# TESTING.md — Domio Indigo Plugin

## Test Coverage

There are **no automated tests** in this repository. The CLAUDE.md explicitly
states: `Testing: none`.

No test files, no test framework configuration, and no test-related CI steps
are present.

## Manual Testing Approach

### During Development

1. Copy the plugin bundle to the Indigo server:
   ```bash
   cp -r "Domio.indigoPlugin" "/Volumes/Macintosh HD-1/Library/Application Support/Perceptive Automation/Indigo 2025.1/Plugins/"
   ```
2. For incremental changes to `plugin.py` or `history_db.py`, copy just the file:
   ```bash
   cp "Domio.indigoPlugin/Contents/Server Plugin/plugin.py" \
     "/Volumes/Macintosh HD-1/Library/Application Support/Perceptive Automation/Indigo 2025.1/Plugins/Domio.indigoPlugin/Contents/Server Plugin/plugin.py"
   ```
3. Restart the plugin via MCP: `mcp__indigo__restart_plugin(plugin_id="com.simons-plugins.domio")`
4. Verify via `mcp__indigo__query_event_log` — look for startup messages and any errors

### Push Notification Testing

- **Plugins menu → Send Test Notification** fires a fixed test push to all registered devices
- **Plugins menu → Show Status** displays registered device count and last push result
- Enable debug logging via **Plugins menu → Toggle Debug Logging** to see HTTP request/response

### History API Testing

- Hit IWS endpoints directly:
  - `GET http://jarvis.local:8176/message/com.simons-plugins.domio/status/`
  - `GET http://jarvis.local:8176/message/com.simons-plugins.domio/history/?device_id=12345&range=24h`
  - `GET http://jarvis.local:8176/message/com.simons-plugins.domio/history/?device_id=12345&columns=true`

### HTML Pages Testing

- `GET http://jarvis.local:8176/message/com.simons-plugins.domio/pages/` returns page manifest
- Add HTML files to `Web Assets/static/pages/` on the Indigo server to test user page scanning

## CI Checks

The only automated check is the version-check workflow in `.github/workflows/version-check.yml`.
It verifies `PluginVersion` in `Info.plist` is not already a git tag. This prevents
accidentally merging without bumping the version.

## Testing Gaps

- No unit tests for `history_db.py` logic (bucketing, type normalisation, column filtering)
- No unit tests for `substitute_tokens()` regex patterns
- No unit tests for `_build_deep_link()` path logic
- No integration tests for push error handling (403, 410, 429 paths)
- No mock for the Indigo `indigo` module — tests would require the full Indigo Python framework
- The `history_db.py` module has no Indigo imports and is theoretically testable in isolation
