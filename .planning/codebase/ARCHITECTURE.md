# ARCHITECTURE.md — Domio Indigo Plugin

## Plugin Responsibilities

The plugin combines three features under one plugin ID (`com.simons-plugins.domio`):

1. **Push Notifications** — visible alerts sent to the Domio iOS app via relay
2. **Widget Refresh** — silent background pushes triggering widget data refresh
3. **Device History API** — HTTP endpoints exposing SQL Logger data for in-app charts
4. **HTML Pages API** — HTTP endpoint listing available dashboard HTML pages

## Module Structure

```
Domio.indigoPlugin/Contents/Server Plugin/
├── plugin.py       # Plugin class — all push, IWS, and lifecycle logic
└── history_db.py   # HistoryDB abstraction — SQLite and PostgreSQL read access
```

`history_db.py` is a pure data-access module with no Indigo imports. It is
instantiated by `plugin.py` in `_connect_db()` and stored as `self.db`.

## Plugin Lifecycle

### `__init__`

- Calls `super().__init__(...)`
- Sets `self.debug = False`
- Initialises state flags: `_subscription_expired`, `_expired_logged_at`
- Sets `self.db = None` (no DB connection yet)

### `startup`

1. Reads `showDebugInfo` pref
2. Subscribes to Indigo variable changes (`indigo.variables.subscribeToChanges()`)
3. Auto-creates `domio_app_token` variable if missing
4. Logs count of registered devices
5. Connects to history database (`_connect_db()`)
6. Counts and logs bundled + user-installed HTML pages

### `shutdown`

- Closes the DB connection if open (no-op for SQLite/psql since no persistent conn)

### `closedPrefsConfigUi`

- Updates `self.debug`
- Reconnects DB with updated settings (e.g. when user changes DB type or path)

## Action Types

### `sendPushNotification` (visible push)

Declared in `Actions.xml`, configured via:
- `title` — notification title (default `"Domio"`), supports `%%v:%%` / `%%d:%%` substitution
- `body` — notification body (required), same substitution
- `targetDevice` — "all" or a specific registered device name
- `deepLinkType` — `none`, `device`, `page`, `action`, `log`
- `deepLinkDeviceId` / `deepLinkPageId` / `deepLinkActionId` — ID for selected link type
- `playSound` — boolean checkbox

Flow: `sendPushNotification(action)` → `substitute_tokens()` → `_build_deep_link()` → `_send_push()`

`_send_push()` fans out to all matching tokens, calling `_post_json()` per device.

### `refreshWidgets` (silent push)

- Configured with just a `targetDevice` selector
- Flow: `refreshWidgets(action)` → `_send_widget_refresh()`
- Posts `{}` to `/v2/widget-update` — relay adds `content-available: 1`
- Intended for use in Indigo triggers after device state changes

### IWS Hidden Actions

Three actions exposed as HTTP endpoints (not shown in Indigo UI):
- `handle_pages` → `pages` endpoint
- `handle_status` → `status` endpoint
- `handle_history` → `history` endpoint

Each returns an `indigo.Dict` with `status`, `content` (JSON string), and
`headers` fields.

## Subscription Expiry Gate

`_subscription_expired` is a module-level flag (instance variable) that short-
circuits all push sends when set. It is set on a `403` from the relay. It is
cleared in `variableUpdated()` when `domio_app_token` changes — the assumption
being that a new token means a renewed subscription.

To avoid log spam, expiry errors are throttled: only one error log per hour
(`_expired_logged_at` stores the last log timestamp).

## Token Fan-Out

Both `_send_push()` and `_send_widget_refresh()` iterate all tokens in
`domio_app_token`. Each token gets its own HTTP request. The loop short-circuits
on `403` (subscription expired) and `429` (rate limited).

## Variable Watching

`variableUpdated(orig_var, new_var)` is called by Indigo whenever any Indigo
variable changes. The plugin filters for `domio_app_token` changes and:
- Resets `_subscription_expired` when the token value changes
- Logs the new device count at debug level

## HTML Pages Feature

- Plugin-bundled pages: `Contents/Resources/static/pages/` (demo pages, replaced on plugin update)
- User-created pages: `{install_folder}/Web Assets/static/pages/` (survives updates)
- Page metadata is parsed from `<meta name="indigo-page-*" content="...">` tags in the
  first 4 KB of each HTML file (name, icon, description)
- Path traversal guard: `os.path.realpath` check before reading any file

## History Feature

`HistoryDB` (`history_db.py`) handles:
- `test_connection()` — verifies connectivity at startup
- `get_device_tables()` — lists devices with history tables
- `get_columns(device_id)` — returns schema with normalised type names
- `query_history(device_id, column, time_range, max_points)` — time-bucketed query

Bucketing strategy (to limit points returned):

| Range | Bucket size |
|-------|-------------|
| 1h | None (raw) |
| 6h | 2 minutes |
| 24h | 5 minutes |
| 7d | 30 minutes |
| 30d | 3 hours |

## Menu Items

Registered in `MenuItems.xml`, callable from Indigo's Plugins menu:

| Menu item | Callback | Purpose |
|-----------|----------|---------|
| Send Test Notification | `sendTestNotification` | Fire a fixed test push |
| Show Status | `showStatus` | Log push + history status to event log |
| Toggle Debug Logging | `toggleDebugging` | Flip `self.debug` and persist in prefs |
