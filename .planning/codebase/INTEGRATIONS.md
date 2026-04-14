# INTEGRATIONS.md — Domio Indigo Plugin

## Push Stack Overview

```
Indigo Trigger
  └─> plugin.py (this plugin)
        └─> POST https://push.domio-smart-home.app/v2/push
              └─> domio-push-relay (Cloudflare Worker)
                    └─> APNs
                          └─> Domio iOS app
```

## Cloudflare Relay Endpoints

All calls use Bearer token auth (the HMAC app token). No HMAC signing is
performed in the plugin itself — the token issued by the relay IS the credential.

### `/v2/push`

- **Method**: POST
- **Auth**: `Authorization: Bearer <app_token>`
- **Body**:
  ```json
  {
    "title": "Notification title",
    "body":  "Notification body",
    "sound": "default",          // present only when play_sound=true
    "data": {"url": "domio://..."} // present only when deep_link is set
  }
  ```
- **Success**: `{"success": true}`
- **Error codes** handled:
  - `403` — subscription expired; sets `_subscription_expired` flag, stops fan-out
  - `410` — token invalid/expired; removes token from `domio_app_token` variable
  - `429` — rate limited; stops fan-out, logs warning
  - other — logs error and continues

### `/v2/widget-update`

- **Method**: POST
- **Auth**: `Authorization: Bearer <app_token>`
- **Body**: `{}` (empty)
- **Purpose**: Silent push triggering background widget refresh (`content-available: 1`)
- Same error handling as `/v2/push`

## HMAC App Token

The relay issues HMAC-signed tokens when the iOS app registers. The plugin
treats the token as an opaque Bearer credential — it does not compute or
validate HMACs locally. Token format from the `domio_app_token` variable:

```json
[
  {"token": "eyJ...", "name": "Simon's iPhone"},
  {"token": "eyJ...", "name": "Simon's iPad"}
]
```

Token lifecycle:

1. iOS app registers with relay → relay issues token
2. iOS app writes token (as JSON array entry) to `domio_app_token` Indigo variable
3. Plugin reads tokens from variable on every send
4. On `410` from relay: plugin removes that entry and updates the variable
5. On `403` from relay: plugin sets `_subscription_expired = True`, skips all future sends
   until tokens are refreshed (detected via `variableUpdated` callback)

## APNs Flow

The plugin never communicates with APNs directly. The relay handles:
- APNs JWT authentication (ES256 key management)
- APNs HTTP/2 connection
- Subscription validation
- Rate limiting

## `domio_app_token` Indigo Variable

- **Name**: `domio_app_token` (constant in `plugin.py` line 23)
- **Type**: Indigo variable (string)
- **Content**: JSON-encoded array of `{token, name}` dicts
- **Auto-created**: Yes — `_ensure_app_token_variable()` called in `startup()`
- **Watched**: Yes — `variableUpdated()` listens for changes and resets
  the `_subscription_expired` flag when tokens are updated

## History Database (SQL Logger)

The plugin reads from the Indigo SQL Logger database — a separate Indigo plugin
that records device state history.

- **Table naming**: `device_history_{device_id}` (one table per device)
- **Timestamp column**: `ts` (stored in GMT/UTC)
- **Supported backends**: SQLite, PostgreSQL (via psql CLI)
- **SQLite auto-detect path**:
  `{install_folder}/Logs/indigo_history.sqlite`
  Falls back to hardcoded paths for Indigo 2025.1, 2024.1, 2023.2

## IWS HTTP Endpoints

Served through Indigo Web Server (IWS) at the plugin message path:
`/message/com.simons-plugins.domio/{endpoint}/`

| Endpoint | Action ID | Method | Description |
|----------|-----------|--------|-------------|
| `pages` | `pages` | GET | HTML page manifest (list of available dashboard pages) |
| `status` | `status` | GET | History DB connection status |
| `history` | `history` | GET | Device history data (query params: `device_id`, `column`, `range`, `max_points`) |

All IWS actions are declared with `uiPath="hidden"` in `Actions.xml` so they
do not appear in the Indigo UI action picker.

## Deep Link URLs

The plugin constructs `domio://` scheme URLs that the iOS app handles:

| Link type | URL pattern |
|-----------|-------------|
| Device | `domio://device/{indigo_device_id}` |
| Control page | `domio://page/{indigo_page_id}` |
| Action group | `domio://action/{indigo_action_group_id}` |
| Event log | `domio://log` |
| None | (omitted from payload) |
