# STACK.md — Domio Indigo Plugin

## Runtime

- **Python**: 3.10+ (Indigo 2023+ requirement, enforced by Indigo framework)
- **Python location**: `/Library/Frameworks/Python.framework/Versions/Current/bin/python3`
- **Indigo Server API version**: `3.6` (declared in `Domio.indigoPlugin/Contents/Info.plist`)
- **IWS API version**: `1.0.0` (Indigo Web Server, used for HTTP endpoints)

## Indigo SDK

- Plugin ID: `com.simons-plugins.domio`
- Plugin version format: `YYYY.M.patch` (currently `2026.4.5`)
- Base class: `indigo.PluginBase` from the Indigo framework
- Indigo 2025.1 server on `jarvis.local`

Key Indigo APIs used:

| API | Usage |
|-----|-------|
| `indigo.variables` | Read/write `domio_app_token`; subscribe to changes |
| `indigo.variable.create` | Auto-create token variable on startup |
| `indigo.variable.updateValue` | Remove stale tokens from variable |
| `indigo.devices` | Device list for deep-link UI dropdown |
| `indigo.controlPages` | Control page list for deep-link dropdown |
| `indigo.actionGroups` | Action group list for deep-link dropdown |
| `indigo.server.getInstallFolderPath` | Locate SQL Logger DB and Web Assets dir |
| `indigo.Dict` | IWS reply objects |
| `self.pluginFolderPath` | Locate bundled HTML pages |
| `self.pluginPrefs` | Plugin settings + last push result cache |

## HTTP Client

- **Library**: `urllib.request` / `urllib.error` (Python stdlib — no third-party deps)
- No packages in `Contents/Packages/` — zero external dependencies
- All outbound HTTP is JSON POST to the Cloudflare relay
- Timeout: 10 seconds per request

## Database (History feature)

- **SQLite**: `sqlite3` (Python stdlib)
- **PostgreSQL**: `psql` CLI via `subprocess` (Postgres.app assumed at
  `/Applications/Postgres.app/Contents/Versions/latest/bin/psql`)
- No ORM, no connection pool — SQLite opens a new connection per query;
  PostgreSQL shells out to `psql` each time
- Database is read-only (`PRAGMA query_only = ON` for SQLite)

## CI / Release

- GitHub Actions (`.github/workflows/`)
- `version-check.yml` — runs on PR, fails if `PluginVersion` is already a git tag
- `create-release.yml` — runs on merge to `main`, zips plugin bundle and creates GitHub release
