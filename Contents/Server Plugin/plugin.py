"""Domio Push Notifications plugin for Indigo home automation (v2).

Bridges Indigo triggers to APNs push notifications via a Cloudflare Worker
relay. Supports variable and device-state substitution in notification text,
deep link construction, and multi-device token fan-out.

v2 changes: Removes self-registration (iOS app registers with relay).
Reads app tokens from domio_app_token Indigo variable (JSON array).
Handles 403 (subscription expired) with suppression until renewal.
"""

import indigo
import json
import re
import urllib.request
import urllib.error
from datetime import datetime

RELAY_URL = "https://push.domio-smart-home.app"
APP_TOKEN_VARIABLE = "domio_app_token"


class Plugin(indigo.PluginBase):
    """Domio Push Notifications plugin."""

    def __init__(self, plugin_id, plugin_display_name, plugin_version, plugin_prefs, **kwargs):
        """Initialize plugin instance variables."""
        super().__init__(plugin_id, plugin_display_name, plugin_version, plugin_prefs, **kwargs)
        self.debug = False
        self._subscription_expired = False
        self._expired_logged_at = None

    # -- Lifecycle ----------------------------------------------------

    def startup(self):
        """Subscribe to variable changes, ensure token variable exists."""
        self.debug = self.pluginPrefs.get("showDebugInfo", False)
        indigo.variables.subscribeToChanges()

        self._ensure_app_token_variable()

        tokens = self._get_app_tokens()
        self.logger.info(f"Domio Push v2 started ({len(tokens)} registered device(s))")

    def shutdown(self):
        """Clean shutdown."""
        self.logger.debug("Domio Push plugin shutting down")

    # -- Variable Watching --------------------------------------------

    def variableUpdated(self, orig_var, new_var):
        """React to domio_app_token variable changes."""
        super().variableUpdated(orig_var, new_var)
        if new_var.name == APP_TOKEN_VARIABLE and orig_var.value != new_var.value:
            tokens = self._get_app_tokens()
            if self._subscription_expired:
                self._subscription_expired = False
                self._expired_logged_at = None
                self.logger.info("Subscription expired flag cleared (tokens updated)")
            self.logger.debug(f"App tokens updated: {len(tokens)} device(s) registered")

    # -- Config -------------------------------------------------------

    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        """Handle plugin config dialog close."""
        if userCancelled:
            return
        self.debug = valuesDict.get("showDebugInfo", False)

    # -- HTTP Helper --------------------------------------------------

    def _post_json(self, url: str, payload: dict, bearer_token: str) -> dict:
        """POST JSON to URL with Bearer auth, return parsed response."""
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {bearer_token}")

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

    # -- Token Management ---------------------------------------------

    def _ensure_app_token_variable(self):
        """Create domio_app_token variable if it doesn't exist."""
        try:
            indigo.variable.create(APP_TOKEN_VARIABLE, value="")
            self.logger.info(f"Created {APP_TOKEN_VARIABLE} variable")
        except Exception:
            self.logger.debug(f"{APP_TOKEN_VARIABLE} variable already exists")

    def _get_app_tokens(self) -> list[dict]:
        """Parse app tokens from domio_app_token variable."""
        try:
            raw = indigo.variables[APP_TOKEN_VARIABLE].value
            if not raw:
                return []
            tokens = json.loads(raw)
            if isinstance(tokens, list):
                return [t for t in tokens if isinstance(t, dict) and "token" in t]
            return []
        except (KeyError, json.JSONDecodeError) as e:
            self.logger.debug(f"Could not parse app tokens: {e}")
            return []

    def _remove_token(self, token: str):
        """Remove a token entry from the domio_app_token variable."""
        try:
            var_obj = indigo.variables[APP_TOKEN_VARIABLE]
            raw = var_obj.value
            if not raw:
                return
            entries = json.loads(raw)
            if not isinstance(entries, list):
                return
            updated = [e for e in entries if e.get("token") != token]
            new_value = json.dumps(updated)
            indigo.variable.updateValue(var_obj, value=new_value)
            self.logger.debug(f"Removed stale token, {len(updated)} device(s) remaining")
        except (KeyError, json.JSONDecodeError) as e:
            self.logger.debug(f"Could not remove token: {e}")

    # -- Substitution -------------------------------------------------

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

    # -- Deep Link ----------------------------------------------------

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

    # -- Push Sending -------------------------------------------------

    def _send_push(self, title: str, body: str, deep_link: str | None = None,
                   play_sound: bool = True) -> bool:
        """Send push notification to all registered devices via relay."""
        if self._subscription_expired:
            now = datetime.now()
            if not self._expired_logged_at or (now - self._expired_logged_at).total_seconds() > 3600:
                self.logger.error("Push skipped: subscription expired. Open Domio app to renew.")
                self._expired_logged_at = now
            return False

        tokens = self._get_app_tokens()
        if not tokens:
            self.logger.error("No registered devices -- install Domio app and subscribe")
            return False

        payload: dict = {"title": title, "body": body}
        if play_sound:
            payload["sound"] = "default"
        if deep_link:
            payload["data"] = {"url": deep_link}

        any_success = False
        for entry in tokens:
            app_token = entry.get("token", "")
            device_name = entry.get("name", "unknown")
            if not app_token:
                continue

            response = self._post_json(
                f"{RELAY_URL}/v1/push", payload, app_token
            )
            http_error = response.get("_http_error")

            if response.get("success"):
                self.logger.debug(f"Push sent to {device_name}")
                any_success = True
            elif http_error == 403:
                self._subscription_expired = True
                self._expired_logged_at = datetime.now()
                self.logger.error(
                    "Push failed: subscription expired. Open Domio app to renew."
                )
                break  # All tokens share the same subscription
            elif http_error == 410:
                self.logger.debug(f"Token expired for {device_name} -- removing")
                self._remove_token(app_token)
            elif http_error == 429:
                self.logger.warning("Push rate limited -- try again later")
                break
            else:
                error_msg = response.get("error", "Unknown error")
                self.logger.error(f"Push to {device_name} failed: {error_msg}")

        # Record result
        push_result = json.dumps({"success": any_success})
        self.pluginPrefs["lastPushResult"] = push_result
        self.pluginPrefs["lastPushTime"] = datetime.now().isoformat()

        if any_success:
            self.logger.info(f"Push notification sent: {title}")
        return any_success

    # -- Action Callback ----------------------------------------------

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

    # -- Menu Item Callbacks ------------------------------------------

    def sendTestNotification(self):
        """Send a fixed test notification."""
        self._send_push("Domio", "Test notification from Indigo", play_sound=True)

    def showStatus(self):
        """Print plugin status to event log."""
        tokens = self._get_app_tokens()
        last_result_json = self.pluginPrefs.get("lastPushResult", "")
        last_time = self.pluginPrefs.get("lastPushTime", "")

        self.logger.info("=== Domio Push Status ===")
        self.logger.info(f"Registered devices: {len(tokens)}")
        for entry in tokens:
            name = entry.get("name", "unknown")
            self.logger.info(f"  - {name}")
        if self._subscription_expired:
            self.logger.info("Subscription: EXPIRED")
        else:
            self.logger.info("Subscription: Active")

        if last_result_json:
            try:
                result = json.loads(last_result_json)
                status = "Success" if result.get("success") else "Failed"
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
