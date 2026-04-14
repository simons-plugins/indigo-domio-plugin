# CONVENTIONS.md — Domio Indigo Plugin

## Python Style

- Python 3.10+ syntax throughout
- Type hints used on method signatures where practical:
  - Return types: `-> str | None`, `-> list[dict]`, `-> bool`, `-> dict`
  - No full annotation coverage — params generally unannotated
- f-strings for all string formatting
- Double-quoted strings (consistent)
- PEP 8 naming: `snake_case` for methods and variables, `UPPER_CASE` for module
  constants (`RELAY_URL`, `APP_TOKEN_VARIABLE`, `RANGE_BUCKETS`, `RANGE_DELTAS`)
- Private methods prefixed with `_` (`_send_push`, `_get_app_tokens`, etc.)
- Public callbacks (called by Indigo) are camelCase to match Indigo XML declarations
  (`sendPushNotification`, `refreshWidgets`, `variableUpdated`, etc.)

## Code Organisation

- `plugin.py` uses `# ═══...` Unicode banner comments to separate logical sections
  (Lifecycle, Token Management, Push Sending, etc.)
- Each section is self-contained — methods within a section only call helpers from
  lower sections or peer sections, not upward
- No class-level state beyond what is set in `__init__` and `startup`

## Logging

Uses `self.logger` (Indigo-provided, writes to Event Log):

| Level | Usage |
|-------|-------|
| `self.logger.debug(msg)` | HTTP request/response details, token counts, verbose state |
| `self.logger.info(msg)` | Successful sends, startup counts, status display |
| `self.logger.warning(msg)` | Rate limiting, substitution of unknown variables |
| `self.logger.error(msg)` | Send failures, missing body, DB errors, subscription expiry |
| `self.logger.exception(exc)` | Not currently used — exceptions are caught and logged with `.error()` |

Debug logging is gated on `self.debug` implicitly by Indigo's logger. The
`toggleDebugging()` menu action flips `self.debug` and persists the value.

Error throttling: subscription expiry errors are limited to one per hour using
`_expired_logged_at` timestamp comparison.

## Error Handling

- All HTTP errors caught via `urllib.error.HTTPError` and `Exception`
- `_post_json()` never raises — it always returns a dict (with `_http_error` key
  for HTTP errors, or `{"error": str(e)}` for network failures)
- Callers check `response.get("success")`, `response.get("_http_error")`, etc.
- Database errors are caught and logged; `self.db` is set to `None` on failure
- IWS handlers return structured error responses (status 400/404/500/503) rather
  than raising
- Token parsing errors (bad JSON, missing keys) are caught and logged at debug
  level; functions return empty list/None gracefully

## Action Callbacks

- Indigo calls action callbacks with a single `action` parameter
- Action properties accessed via `action.props.get(key, default)`
- Boolean prefs stored as strings `"true"` / `"false"` — compared as
  `action.props.get("playSound", "true") == "true"`
- IWS callbacks receive `(self, action, dev=None, caller_waiting_for_result=None)`

## Dynamic List Generators

Return lists of `(value, label)` tuples, sorted case-insensitively by label.
`appDeviceListGenerator` prepends `("all", "All Devices")` as the first option.

## Token Substitution

`substitute_tokens(text)` applies two regex patterns:
- `%%v:varName%%` → replaced with `indigo.variables[varName].value`
- `%%d:deviceId:stateName%%` → replaced with `dev.states.get(stateName)`
Unknown references replaced with `[unknown: ...]` placeholder; warning logged.

## Settings / Prefs

Plugin preferences (`self.pluginPrefs`) are accessed by string key with `.get(key, default)`.
Two runtime-state values are also stored in prefs (not ideal — see CONCERNS.md):
- `lastPushResult` — JSON string `{"success": bool}`
- `lastPushTime` — ISO 8601 datetime string

## HTML Page Metadata

Pages declare metadata via HTML `<meta>` tags in the `<head>`:
```html
<meta name="indigo-page-name" content="Home Summary">
<meta name="indigo-page-icon" content="house.fill">
<meta name="indigo-page-description" content="Overview of all rooms">
```
The plugin reads only the first 4 KB of each file to extract these.
