# Domio Push Notifications — Indigo Plugin

Bridges Indigo home automation triggers to APNs push notifications via the [Domio Push Relay](https://github.com/simons-plugins/domio-push-relay). Delivers notifications to the [Domio iOS app](https://github.com/simons-plugins/domio-code).

## How It Works

1. The Domio iOS app registers with the push relay
2. The relay issues an HMAC app token, which the iOS app writes to the `domio_app_token` Indigo variable
3. This plugin reads those tokens and uses them to send push notifications via the relay's `/v2/push` endpoint
4. The relay forwards notifications to APNs for delivery to the user's device

```
Indigo Trigger → Plugin → /v2/push → Relay → APNs → iPhone
```

## Features

- **Multi-device fan-out** — pushes to all registered devices
- **Variable substitution** — use `%%v:variableName%%` in notification text
- **Device state substitution** — use `%%d:deviceId:stateName%%` in notification text
- **Deep links** — tap notification to open device, page, action group, or log in Domio
- **Stale token cleanup** — removes expired device tokens (410) automatically

## Deep Link Types

| Type | URL | Action |
|------|-----|--------|
| Device | `domio://device/{id}` | Opens device detail sheet |
| Page | `domio://page/{id}` | Navigates to control page |
| Action | `domio://action/{id}` | Executes action group |
| Log | `domio://log` | Switches to log tab |

## Setup

1. Install the plugin in Indigo
2. Enable push notifications in the Domio iOS app
3. The app automatically registers and writes tokens to the `domio_app_token` variable
4. Create Indigo triggers with the "Send Push Notification" action

## Plugin Menu

- **Send Test Notification** — sends a fixed test push to all registered devices
- **Show Status** — displays registration, subscription, and last push status
- **Toggle Debug Logging** — enables verbose HTTP request/response logging

## Requirements

- Indigo 2023+ (Python 3.10+)
- Domio iOS app with push notifications enabled
- Internet connection (relay is hosted on Cloudflare)
