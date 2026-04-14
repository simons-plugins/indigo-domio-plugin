# STRUCTURE.md — Domio Indigo Plugin

## Repository Root

```
indigo-domio-plugin/
├── .github/
│   └── workflows/
│       ├── version-check.yml    # PR check: PluginVersion must not already be a git tag
│       └── create-release.yml   # On main merge: zip plugin bundle + create GitHub release
├── .planning/
│   └── codebase/                # Codebase map documents (this directory)
├── Domio.indigoPlugin/          # The Indigo plugin bundle
├── CLAUDE.md                    # Project-specific instructions for Claude
└── readme.md                    # End-user setup and feature documentation
```

## Plugin Bundle

```
Domio.indigoPlugin/
└── Contents/
    ├── Info.plist               # Plugin metadata (ID, version, API version)
    ├── Resources/
    │   ├── icon.png             # Plugin icon shown in Indigo Plugins menu
    │   └── static/
    │       ├── js/
    │       │   └── indigo-api.js    # Bundled JS client (served by IWS)
    │       └── pages/
    │           └── domio-example-home-summary.html  # Demo dashboard page
    └── Server Plugin/
        ├── plugin.py            # Main plugin class (Plugin)
        ├── history_db.py        # HistoryDB database abstraction
        ├── Actions.xml          # Action definitions
        ├── MenuItems.xml        # Plugin menu items
        └── PluginConfig.xml     # Plugin preferences UI
```

## Key Files

### `Domio.indigoPlugin/Contents/Info.plist`

Declares:
- `PluginVersion` — version string (`YYYY.M.patch`), must be bumped per PR
- `CFBundleIdentifier` — `com.simons-plugins.domio`
- `ServerApiVersion` — `3.6`
- `IwsApiVersion` — `1.0.0`

### `Domio.indigoPlugin/Contents/Server Plugin/plugin.py`

Single `Plugin` class inheriting `indigo.PluginBase`. ~741 lines. Sections:
- Lifecycle (`startup`, `shutdown`, `closedPrefsConfigUi`)
- Variable watching (`variableUpdated`)
- HTTP helper (`_post_json`)
- Token management (`_ensure_app_token_variable`, `_get_app_tokens`, `_remove_token`)
- Token substitution (`substitute_tokens`)
- Dynamic list generators for UI dropdowns
- Deep link builder (`_build_deep_link`)
- Push sending (`_send_push`)
- Widget refresh (`_send_widget_refresh`)
- Action callbacks (`sendPushNotification`, `refreshWidgets`)
- DB connection management (`_connect_db`, `_auto_detect_sqlite_path`)
- IWS HTML pages endpoint (`handle_pages`, `_scan_pages_dir`, `_parse_page_meta`)
- IWS history endpoints (`handle_status`, `handle_history`, `_handle_columns`)
- Menu callbacks (`sendTestNotification`, `showStatus`, `toggleDebugging`)

### `Domio.indigoPlugin/Contents/Server Plugin/history_db.py`

`HistoryDB` class (~320 lines). No Indigo imports. Sections:
- Constants: `RANGE_BUCKETS`, `RANGE_DELTAS`
- Connection/test helpers
- Backend executors: `_execute_sqlite`, `_execute_pg`, `_execute` (dispatcher)
- Schema inspection: `get_device_tables`, `get_columns`
- Query: `query_history`, `_query_raw`, `_query_bucketed`

### `Domio.indigoPlugin/Contents/Server Plugin/Actions.xml`

Defines four actions:

| Action ID | UI visible | Callback |
|-----------|-----------|----------|
| `sendPushNotification` | Yes | `sendPushNotification` |
| `refreshWidgets` | Yes | `refreshWidgets` |
| `pages` | No (`uiPath="hidden"`) | `handle_pages` |
| `status` | No (`uiPath="hidden"`) | `handle_status` |
| `history` | No (`uiPath="hidden"`) | `handle_history` |

### `Domio.indigoPlugin/Contents/Server Plugin/MenuItems.xml`

Three menu items: `sendTestNotification`, `showStatus`, `toggleDebugging`.

### `Domio.indigoPlugin/Contents/Server Plugin/PluginConfig.xml`

Plugin-level settings (saved in `pluginPrefs`):
- `showDebugInfo` — checkbox (default: false)
- `dbType` — menu: `sqlite` / `postgresql`
- `sqlitePath` — text (blank = auto-detect), shown when dbType=sqlite
- `pgHost`, `pgPort`, `pgUser`, `pgPassword` (secure), `pgDatabase` — shown when dbType=postgresql

### `Domio.indigoPlugin/Contents/Resources/static/pages/domio-example-home-summary.html`

Demo dashboard page bundled with the plugin. Served by IWS at the plugin's
static path. Contains `<meta name="indigo-page-*" content="...">` tags.

### `Domio.indigoPlugin/Contents/Resources/static/js/indigo-api.js`

Bundled JavaScript client library for dashboard pages to interact with the
Indigo REST API from within an IWS-served HTML page.

## No Packages Directory

`Contents/Packages/` does not exist. The plugin has zero bundled Python
dependencies — all imports are from the Python stdlib or the Indigo framework.
