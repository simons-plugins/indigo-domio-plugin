"""Domio Push Notifications plugin for Indigo home automation.

Bridges Indigo triggers to APNs push notifications via a Cloudflare Worker
relay. Supports variable and device-state substitution in notification text,
deep link construction, and automatic relay registration.
"""

import indigo
import json
import re
import urllib.request
import urllib.error
from datetime import datetime

# Must match the relay's REGISTRATION_SECRET environment variable.
# Change this before deploying. Phase 4 removes this entirely.
REGISTRATION_SECRET = "CHANGE-ME-domio-phase3-testing"
APP_ID = "com.simons-plugins.domio"


class Plugin(indigo.PluginBase):
    """Domio Push Notifications plugin."""

    def __init__(self, plugin_id, plugin_display_name, plugin_version, plugin_prefs, **kwargs):
        """Initialize plugin instance variables."""
        super().__init__(plugin_id, plugin_display_name, plugin_version, plugin_prefs, **kwargs)
        self.debug = False
        self.device_token = ""

    # ── Lifecycle ────────────────────────────────────────────────

    def startup(self):
        """Subscribe to variable changes, ensure token variable exists, auto-register."""
        self.debug = self.pluginPrefs.get("showDebugInfo", False)
        indigo.variables.subscribeToChanges()

        self._ensure_push_token_variable()

        # Read current device token
        try:
            self.device_token = indigo.variables["domio_push_token"].value
        except KeyError:
            self.device_token = ""

        # Auto-register if we have a device token but no app token
        if not self.pluginPrefs.get("appToken") and self.device_token:
            self._register_with_relay()
        elif not self.device_token:
            self.logger.info("Waiting for device token from Domio app")

    def shutdown(self):
        """Clean shutdown."""
        self.logger.debug("Domio Push plugin shutting down")

    # ── Variable Watching ────────────────────────────────────────

    def variableUpdated(self, orig_var, new_var):
        """React to domio_push_token variable changes."""
        super().variableUpdated(orig_var, new_var)
        if new_var.name == "domio_push_token" and orig_var.value != new_var.value:
            self.device_token = new_var.value
            if new_var.value:
                self.logger.info("Device push token updated -- re-registering with relay")
                self._register_with_relay()
            else:
                self.logger.debug("Device push token cleared")

    # ── Config ───────────────────────────────────────────────────

    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        """Handle plugin config dialog close."""
        if userCancelled:
            return

        self.debug = valuesDict.get("showDebugInfo", False)

        old_url = self.pluginPrefs.get("relayUrl", "")
        new_url = valuesDict.get("relayUrl", "")
        if old_url != new_url and new_url:
            self.logger.info("Relay URL changed -- re-registering")
            self.pluginPrefs["appToken"] = ""
            # pluginPrefs not yet updated by Indigo, pass new URL explicitly
            self._register_with_relay(relay_url=new_url)

    # ── HTTP Helper ──────────────────────────────────────────────

    def _post_json(self, url: str, payload: dict, bearer_token: str) -> dict:
        """POST JSON to URL with Bearer auth, return parsed response."""
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {bearer_token}")
        req.add_header("User-Agent", "DomioPush/1.0")

        self.logger.debug(f"POST {url}")

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                response_data = json.loads(resp.read().decode("utf-8"))
                self.logger.debug(f"Response: {response_data}")
                return response_data
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            self.logger.debug(f"HTTP {e.code}: {error_body}")
            try:
                return {"_http_error": e.code, **json.loads(error_body)}
            except json.JSONDecodeError:
                return {"_http_error": e.code, "error": error_body}
        except Exception as e:
            self.logger.error(f"Request failed: {e}")
            return {"error": str(e)}

    # ── Registration ─────────────────────────────────────────────

    def _ensure_push_token_variable(self):
        """Create domio_push_token variable if it doesn't exist."""
        try:
            indigo.variable.create("domio_push_token", value="")
            self.logger.info("Created domio_push_token variable")
        except Exception:
            self.logger.debug("domio_push_token variable already exists")

    def _get_device_token(self) -> str:
        """Read fresh device token from Indigo variable."""
        try:
            return indigo.variables["domio_push_token"].value
        except (KeyError, Exception):
            return ""

    def _register_with_relay(self, relay_url: str | None = None) -> bool:
        """Register with relay, store app token in pluginPrefs."""
        if relay_url is None:
            relay_url = self.pluginPrefs.get("relayUrl", "https://push.domio-smart-home.app")

        device_token = self.device_token or self._get_device_token()
        if not device_token:
            self.logger.error("Cannot register: no device token available")
            return False

        response = self._post_json(
            f"{relay_url}/v1/register",
            {"deviceToken": device_token, "appId": APP_ID},
            REGISTRATION_SECRET,
        )

        if "token" in response:
            self.pluginPrefs["appToken"] = response["token"]
            self.logger.info("Successfully registered with relay")
            return True

        http_code = response.get("_http_error", "")
        error_msg = response.get("error", "Unknown error")
        self.logger.error(f"Registration failed (HTTP {http_code}): {error_msg}")
        return False

    # ── Substitution ─────────────────────────────────────────────

    def substitute_tokens(self, text: str) -> str:
        """Replace %%v:name%% and %%d:id:state%% tokens with current values."""

        def replace_var(match):
            var_name = match.group(1)
            try:
                return indigo.variables[var_name].value
            except KeyError:
                self.logger.warning(f"Unknown variable in substitution: {var_name}")
                return f"[unknown: {var_name}]"

        def replace_device(match):
            dev_id_str = match.group(1)
            state_name = match.group(2)
            try:
                dev = indigo.devices[int(dev_id_str)]
                value = dev.states.get(state_name)
                if value is None:
                    self.logger.warning(f"Unknown state '{state_name}' for device {dev_id_str}")
                    return f"[unknown: {dev_id_str}:{state_name}]"
                return str(value)
            except (KeyError, ValueError):
                self.logger.warning(f"Unknown device in substitution: {dev_id_str}")
                return f"[unknown: {dev_id_str}:{state_name}]"

        text = re.sub(r'%%v:(.+?)%%', replace_var, text)
        text = re.sub(r'%%d:(\d+):(.+?)%%', replace_device, text)
        return text

    # ── Deep Link ────────────────────────────────────────────────

    def _build_deep_link(self, action_props: dict) -> str | None:
        """Build deep link URL from action config, or None if type is 'none'."""
        link_type = action_props.get("deepLinkType", "none")
        link_id = action_props.get("deepLinkId", "").strip()

        if link_type == "none":
            return None
        elif link_type == "device":
            return f"domio://device/{link_id}" if link_id else None
        elif link_type == "page":
            return f"domio://page/{link_id}" if link_id else None
        elif link_type == "action":
            return f"domio://action/{link_id}" if link_id else None
        elif link_type == "log":
            return "domio://log"
        return None

    # ── Push Sending ─────────────────────────────────────────────

    def _send_push(self, title: str, body: str, deep_link: str | None = None,
                   play_sound: bool = True) -> bool:
        """Send push notification via relay."""
        app_token = self.pluginPrefs.get("appToken", "")
        if not app_token:
            self.logger.error("Not registered with relay -- use Plugin menu to register")
            return False

        device_token = self._get_device_token()
        if not device_token:
            self.logger.error("No device token available")
            return False

        payload: dict = {"title": title, "body": body}
        if play_sound:
            payload["sound"] = "default"
        if deep_link:
            payload["data"] = {"url": deep_link}

        relay_url = self.pluginPrefs.get("relayUrl", "https://push.domio-smart-home.app")
        response = self._post_json(f"{relay_url}/v1/push", payload, app_token)

        # Record result
        push_result = json.dumps({
            "success": response.get("success", False),
            "error": response.get("error", ""),
        })
        self.pluginPrefs["lastPushResult"] = push_result
        self.pluginPrefs["lastPushTime"] = datetime.now().isoformat()

        http_error = response.get("_http_error")

        if response.get("success"):
            self.logger.info(f"Push notification sent: {title}")
            return True

        if http_error == 410:
            self.logger.warning("Device token expired -- waiting for new token from app")
        elif http_error == 401:
            self.logger.error("Push failed: invalid app token -- re-register via Plugin menu")
        elif http_error == 429:
            self.logger.warning("Push failed: rate limited -- try again later")
        else:
            error_msg = response.get("error", "Unknown error")
            self.logger.error(f"Push failed (HTTP {http_error}): {error_msg}")

        return False

    # ── Action Callback ──────────────────────────────────────────

    def sendPushNotification(self, action):
        """Send Push Notification action callback (called when trigger fires)."""
        title = action.props.get("title", "Domio")
        body = action.props.get("body", "")
        play_sound = action.props.get("playSound", "true") == "true"

        if not body:
            self.logger.error("Notification body is required")
            return

        title = self.substitute_tokens(title)
        body = self.substitute_tokens(body)
        deep_link = self._build_deep_link(action.props)

        self._send_push(title, body, deep_link, play_sound)

    # ── Menu Item Callbacks ──────────────────────────────────────

    def sendTestNotification(self):
        """Send a fixed test notification."""
        self._send_push("Domio", "Test notification from Indigo", play_sound=True)

    def registerWithRelay(self):
        """Manual registration trigger."""
        if self._register_with_relay():
            self.logger.info("Registration successful")
        else:
            self.logger.error("Registration failed -- check event log for details")

    def showStatus(self):
        """Print plugin status to event log."""
        relay_url = self.pluginPrefs.get("relayUrl", "https://push.domio-smart-home.app")
        has_app_token = bool(self.pluginPrefs.get("appToken", ""))
        device_token = self._get_device_token()
        last_result_json = self.pluginPrefs.get("lastPushResult", "")
        last_time = self.pluginPrefs.get("lastPushTime", "")

        self.logger.info("=== Domio Push Status ===")
        self.logger.info(f"Relay URL: {relay_url}")
        self.logger.info(f"Registered: {'Yes' if has_app_token else 'No'}")
        self.logger.info(f"Device token: {'Present' if device_token else 'Missing'}")

        if last_result_json:
            try:
                result = json.loads(last_result_json)
                status = "Success" if result.get("success") else f"Failed: {result.get('error', 'unknown')}"
                self.logger.info(f"Last push: {status} at {last_time}")
            except json.JSONDecodeError:
                self.logger.info(f"Last push: {last_result_json} at {last_time}")
        else:
            self.logger.info("Last push: None")

        self.logger.info(f"Debug logging: {'On' if self.debug else 'Off'}")

    def toggleDebugging(self):
        """Toggle debug logging on/off."""
        self.debug = not self.debug
        self.pluginPrefs["showDebugInfo"] = self.debug
        self.logger.info(f"Debug logging {'enabled' if self.debug else 'disabled'}")
