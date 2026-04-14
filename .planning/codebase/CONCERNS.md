# CONCERNS.md — Domio Indigo Plugin

## Security

### Token Storage (Medium Risk)

- `domio_app_token` is an Indigo variable containing an array of HMAC Bearer tokens
- Indigo variables are visible to any script, action, or plugin with Indigo access
- Tokens are stored in plaintext in the variable value
- Any Indigo trigger, script, or third-party plugin can read the tokens
- Mitigation: tokens are scoped to the relay's subscription validation; a leaked token
  can only be used to send pushes to the subscribed device, not to access Indigo itself

### PostgreSQL Password (Low Risk)

- PG password is stored in `pluginPrefs` via `PluginConfig.xml` with `secure="true"`
- Indigo encrypts `secure` fields in its preferences store
- The password is passed to `psql` via `PGPASSWORD` environment variable —
  not visible in process arguments, but visible in the environment of the subprocess

### Path Traversal in HTML Page Scanner (Addressed)

- `_scan_pages_dir` uses `os.path.realpath` to guard against symlink-based traversal
- Files outside the scanned directory are skipped silently
- Only `.html` files are processed (extension check)

### No HMAC Verification on Inbound Requests

- IWS endpoints (`handle_history`, `handle_pages`, `handle_status`) are unauthenticated
- Any client with network access to the Indigo server can query device history
- This matches the stated design ("Device history is available to all users")
- Risk: depends on Indigo Web Server network exposure (typically LAN-only)

## Tech Debt

### Last Push Result Stored in pluginPrefs (Minor)

- `lastPushResult` and `lastPushTime` are written to `self.pluginPrefs` in `_send_push()`
- `pluginPrefs` is designed for user settings, not runtime state
- This works but is non-idiomatic; a better pattern would be instance variables
- `showStatus()` reads these back from prefs to display in the event log

### PostgreSQL Uses psql CLI Subprocess (Notable)

- `_execute_pg()` shells out to `psql` for every query — no persistent connection
- Requires Postgres.app at `/Applications/Postgres.app/Contents/Versions/latest/bin/psql`
- Hardcoded path with glob fallback, but no support for homebrew/system postgres
- Manual SQL parameter interpolation via string replacement (`%s` → `'escaped value'`)
  instead of proper parameterised queries — mitigated by the narrow input surface
  (only timestamps and validated table/column names from schema inspection)
- Could be replaced with `psycopg2` bundled in `Contents/Packages/` for robustness

### No Connection Pooling for SQLite

- SQLite opens a new connection for every query in `_execute_sqlite()`
- Each `handle_history` HTTP request opens and closes a connection
- Acceptable for the expected query rate (low, triggered by app refreshes)
- WAL mode not explicitly enabled, which can cause lock contention if SQL Logger
  is writing frequently

### `_subscription_expired` State Not Persisted

- If the plugin is restarted while subscription is expired, the flag resets to `False`
- First send attempt after restart will hit the relay, get a 403, and re-set the flag
- One extra failed push per restart cycle when subscription is lapsed — acceptable

### `variableUpdated` Called for All Variable Changes

- Indigo calls `variableUpdated` for every variable change across the entire Indigo instance
- Plugin filters to only `domio_app_token` changes, which is correct
- Minimal performance impact but worth noting for future variable-watching additions

## TODOs / Missing Features

- No device targeting for widget refresh in documentation (the action supports
  `targetDevice` but CLAUDE.md description does not mention it)
- No `Devices.xml` — the plugin has no Indigo device types (pure action/API plugin)
- No `runConcurrentThread` — the plugin is entirely event-driven (no polling)
- The `indigo-api.js` bundled at `Contents/Resources/static/js/indigo-api.js` is
  used by the bundled demo page but has no documentation of its API surface
- `handle_history` does not enforce `max_points` — the parameter is accepted but
  passed to `query_history` which does not apply a LIMIT to raw queries (only bucketed
  queries are implicitly limited by bucket count)

## Version / Release

- Version format is `YYYY.M.patch` — the patch number resets semantically per release
  but is not enforced programmatically
- The CI `create-release.yml` does not validate the version format; a malformed version
  string would still create a release
