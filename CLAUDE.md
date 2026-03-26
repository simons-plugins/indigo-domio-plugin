# CLAUDE.md — Domio Push Notifications Indigo Plugin

Indigo plugin that sends push notifications and widget refresh signals to the Domio iOS app via a Cloudflare Worker relay.

## System Overview

This plugin is one part of a three-component push notification system:

```
Indigo Plugin (this) → Cloudflare Relay → APNs → Domio iOS App
```

| Component | Repo | Purpose |
|-----------|------|---------|
| **Indigo Plugin** | This repo | Sends push requests from Indigo triggers |
| **Cloudflare Relay** | [domio-push-relay](https://github.com/simons-plugins/domio-push-relay) | Authenticates, rate-limits, and forwards to APNs |
| **Domio iOS App** | [domio-code](https://github.com/simons-plugins/domio-code) | Receives pushes, registers tokens, handles deep links |

## How It Works

1. Domio iOS app registers with the relay
2. Relay issues an HMAC app token, iOS app writes it to `domio_app_token` Indigo variable
3. This plugin reads tokens from that variable and POSTs to the relay
4. Relay forwards to APNs → notification arrives on device

## Plugin Structure

```
domio push.IndigoPlugin/
└── Contents/
    └── Server Plugin/
        ├── plugin.py        # Main plugin logic
        ├── Actions.xml      # Action definitions (Send Push, Refresh Widgets)
        ├── MenuItems.xml    # Plugin menu (Test, Status, Debug Toggle)
        └── PluginConfig.xml # Plugin preferences UI
```

## Actions

### Send Push Notification (`sendPushNotification`)
- **Title**: Supports `%%v:varName%%` and `%%d:deviceId:stateName%%` substitution
- **Body**: Same substitution support (required field)
- **Deep link**: device, page, action group, log, or none
- **Sound**: Optional notification sound
- POSTs to `https://push.domio-smart-home.app/v2/push`

### Refresh Domio Widgets (`refreshWidgets`)
- Sends silent push (`content-available: 1`) to trigger background widget refresh
- POSTs to `https://push.domio-smart-home.app/v2/widget-update`
- iOS app receives this → fetches fresh device/variable state via REST → updates widgets
- Use in triggers after device state changes that should appear on home screen widgets

## Token Management

- Reads from `domio_app_token` Indigo variable (JSON array)
- Format: `[{"token": "eyJ...", "name": "Simon's iPhone"}, ...]`
- Auto-creates variable if missing
- Watches for variable changes (`variableUpdated`)
- Auto-removes expired tokens on 410 response from relay

## Error Handling

| HTTP Code | Meaning | Action |
|-----------|---------|--------|
| 200 | Success | Log and continue |
| 403 | Unauthorised | Log warning, skip sends |
| 410 | Token invalid/expired | Remove from variable |
| 429 | Rate limited | Stop fan-out, log warning |

## Menu Items

- **Send Test Notification** — fixed test push to all devices
- **Show Status** — registration count and last push result
- **Toggle Debug Logging** — verbose HTTP request/response logging

## Versioning & Release

### Version bump is required for every PR

The `PluginVersion` in `Domio.indigoPlugin/Contents/Info.plist` must be bumped in every PR. CI runs a version-check that fails if the version already exists as a git tag. **Do not merge with failing checks.**

Version format: `YYYY.M.patch` (e.g. `2026.3.1`). Bump the patch for fixes/docs, minor for features.

On merge to main, the `create-release` workflow automatically creates a GitHub release with a `.zip` bundle of the plugin.

### PR checklist

1. Bump `PluginVersion` in `Info.plist`
2. Push and create PR
3. Wait for version-check CI to pass
4. Merge only after all checks are green

## Development

### Testing on Indigo Server

```bash
# Copy plugin to Indigo server
cp -r "domio push.IndigoPlugin" "/Volumes/Macintosh HD-1/Library/Application Support/Perceptive Automation/Indigo 2025.1/Plugins/"
```

Then enable via **Plugins → Manage Plugins** in Indigo.

### Plugin ID

`com.simons-plugins.domio`

### Relay URL

`https://push.domio-smart-home.app` — production Cloudflare Worker

### Requirements

- Indigo 2023+ (Python 3.10+)
- Domio iOS app with push notifications enabled
- Internet connection
