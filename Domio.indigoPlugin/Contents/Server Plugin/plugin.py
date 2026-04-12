"""Domio plugin for Indigo home automation.

Combines two features for the Domio iOS app:

1. Push Notifications (subscription required) — sends visible and silent
   push notifications via the Cloudflare relay to APNs.

2. Device History API (free) — serves device history data from the
   SQL Logger database via HTTP endpoints for in-app charts.
"""

import indigo
import json
import os
import re
import urllib.request
import urllib.error
from datetime import datetime

from history_db import HistoryDB

RELAY_URL = "https://push.domio-smart-home.app"
APP_TOKEN_VARIABLE = "domio_app_token"


class Plugin(indigo.PluginBase):
    """Domio plugin — push notifications + device history API."""

    def __init__(self, plugin_id, plugin_display_name, plugin_version, plugin_prefs, **kwargs):
        super().__init__(plugin_id, plugin_display_name, plugin_version, plugin_prefs, **kwargs)
        self.debug = False
        self._subscription_expired = False
        self._expired_logged_at = None
        self.db = None

    # ═══════════════════════════════════════════════════
    # Lifecycle
    # ═══════════════════════════════════════════════════

    def startup(self):
        self.debug = self.pluginPrefs.get("showDebugInfo", False)

        # Push: subscribe to variable changes, ensure token variable
        indigo.variables.subscribeToChanges()
        self._ensure_app_token_variable()
        tokens = self._get_app_tokens()
        self.logger.info(f"Push: {len(tokens)} registered device(s)")

        # History: connect to SQL Logger database
        self._connect_db()

        # HTML Pages: report available pages
        pages_dir = os.path.join(self.pluginFolderPath, "Contents", "Resources", "static", "pages")
        if os.path.isdir(pages_dir):
            page_count = len([f for f in os.listdir(pages_dir) if f.lower().endswith(".html")])
            self.logger.info(f"HTML Pages: {page_count} page(s) available")

        self.logger.info("Domio plugin started")

    def shutdown(self):
        self.logger.debug("Domio plugin shutting down")
        if self.db:
            self.db.close()

    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        if userCancelled:
            return
        self.debug = valuesDict.get("showDebugInfo", False)
        # Reconnect DB with new settings
        if self.db:
            self.db.close()
        self._connect_db()

    # ═══════════════════════════════════════════════════
    # Variable Watching (Push)
    # ═══════════════════════════════════════════════════

    def variableUpdated(self, orig_var, new_var):
        super().variableUpdated(orig_var, new_var)
        if new_var.name == APP_TOKEN_VARIABLE and orig_var.value != new_var.value:
            tokens = self._get_app_tokens()
            if self._subscription_expired:
                self._subscription_expired = False
                self._expired_logged_at = None
                self.logger.info("Subscription expired flag cleared (tokens updated)")
            self.logger.debug(f"App tokens updated: {len(tokens)} device(s) registered")

    # ═══════════════════════════════════════════════════
    # HTTP Helper (Push)
    # ═══════════════════════════════════════════════════

    def _post_json(self, url: str, payload: dict, bearer_token: str) -> dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {bearer_token}")
        req.add_header("User-Agent", "Domio/3.0")

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

    # ═══════════════════════════════════════════════════
    # Token Management (Push)
    # ═══════════════════════════════════════════════════

    def _ensure_app_token_variable(self):
        try:
            indigo.variable.create(APP_TOKEN_VARIABLE, value="")
            self.logger.info(f"Created {APP_TOKEN_VARIABLE} variable")
        except Exception:
            self.logger.debug(f"{APP_TOKEN_VARIABLE} variable already exists")

    def _get_app_tokens(self) -> list[dict]:
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

    # ═══════════════════════════════════════════════════
    # Substitution (Push)
    # ═══════════════════════════════════════════════════

    def substitute_tokens(self, text: str) -> str:
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

    # ═══════════════════════════════════════════════════
    # Dynamic List Generators
    # ═══════════════════════════════════════════════════

    def deviceListGenerator(self, filter="", valuesDict=None, typeId="", targetId=0):
        """Return list of devices for the deep link dropdown."""
        device_list = []
        for dev in indigo.devices:
            device_list.append((dev.id, dev.name))
        device_list.sort(key=lambda x: x[1].lower())
        return device_list

    def controlPageListGenerator(self, filter="", valuesDict=None, typeId="", targetId=0):
        """Return list of control pages for the deep link dropdown."""
        page_list = []
        for page in indigo.controlPages:
            page_list.append((page.id, page.name))
        page_list.sort(key=lambda x: x[1].lower())
        return page_list

    def actionGroupListGenerator(self, filter="", valuesDict=None, typeId="", targetId=0):
        """Return list of action groups for the deep link dropdown."""
        group_list = []
        for group in indigo.actionGroups:
            group_list.append((group.id, group.name))
        group_list.sort(key=lambda x: x[1].lower())
        return group_list

    def appDeviceListGenerator(self, filter="", valuesDict=None, typeId="", targetId=0):
        """Return list of registered Domio app devices for targeting notifications."""
        device_list = [("all", "All Devices")]
        tokens = self._get_app_tokens()
        for entry in tokens:
            name = entry.get("name", "unknown")
            device_list.append((name, name))
        return device_list

    # ═══════════════════════════════════════════════════
    # Deep Link (Push)
    # ═══════════════════════════════════════════════════

    def _build_deep_link(self, action_props: dict) -> str | None:
        link_type = action_props.get("deepLinkType", "none")

        if link_type == "none":
            return None
        elif link_type == "device":
            link_id = action_props.get("deepLinkDeviceId", "") or action_props.get("deepLinkId", "")
            return f"domio://device/{link_id}" if link_id else None
        elif link_type == "page":
            link_id = action_props.get("deepLinkPageId", "") or action_props.get("deepLinkId", "")
            return f"domio://page/{link_id}" if link_id else None
        elif link_type == "action":
            link_id = action_props.get("deepLinkActionId", "") or action_props.get("deepLinkId", "")
            return f"domio://action/{link_id}" if link_id else None
        elif link_type == "log":
            return "domio://log"
        return None

    # ═══════════════════════════════════════════════════
    # Push Sending
    # ═══════════════════════════════════════════════════

    def _send_push(self, title: str, body: str, deep_link: str | None = None,
                   play_sound: bool = True, target_device: str = "all") -> bool:
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

        if target_device != "all":
            tokens = [t for t in tokens if t.get("name") == target_device]
            if not tokens:
                self.logger.error(f"No registered device named '{target_device}'")
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
                f"{RELAY_URL}/v2/push", payload, app_token
            )
            http_error = response.get("_http_error")

            if response.get("success"):
                self.logger.info(f"Push sent to {device_name}")
                any_success = True
            elif http_error == 403:
                self._subscription_expired = True
                self._expired_logged_at = datetime.now()
                self.logger.error(
                    "Push failed: subscription expired. Open Domio app to renew."
                )
                break
            elif http_error == 410:
                self.logger.debug(f"Token expired for {device_name} -- removing")
                self._remove_token(app_token)
            elif http_error == 429:
                self.logger.warning("Push rate limited -- try again later")
                break
            else:
                error_msg = response.get("error", "Unknown error")
                self.logger.error(f"Push to {device_name} failed: {error_msg}")

        self.pluginPrefs["lastPushResult"] = json.dumps({"success": any_success})
        self.pluginPrefs["lastPushTime"] = datetime.now().isoformat()

        if any_success:
            self.logger.info(f"Push notification sent: {title}")
        return any_success

    # ═══════════════════════════════════════════════════
    # Action Callbacks (Push)
    # ═══════════════════════════════════════════════════

    def sendPushNotification(self, action):
        title = action.props.get("title", "Domio")
        body = action.props.get("body", "")
        play_sound = action.props.get("playSound", "true") == "true"
        target_device = action.props.get("targetDevice", "all")

        if not body:
            self.logger.error("Notification body is required")
            return

        title = self.substitute_tokens(title)
        body = self.substitute_tokens(body)
        deep_link = self._build_deep_link(action.props)

        self._send_push(title, body, deep_link, play_sound, target_device)

    # ═══════════════════════════════════════════════════
    # Widget Refresh (Push)
    # ═══════════════════════════════════════════════════

    def _send_widget_refresh(self, target_device: str = "all") -> bool:
        if self._subscription_expired:
            now = datetime.now()
            if not self._expired_logged_at or (now - self._expired_logged_at).total_seconds() > 3600:
                self.logger.error("Widget refresh skipped: subscription expired. Open Domio app to renew.")
                self._expired_logged_at = now
            return False

        tokens = self._get_app_tokens()
        if not tokens:
            self.logger.error("No registered devices -- install Domio app and subscribe")
            return False

        if target_device != "all":
            tokens = [t for t in tokens if t.get("name") == target_device]
            if not tokens:
                self.logger.error(f"No registered device named '{target_device}'")
                return False

        any_success = False
        for entry in tokens:
            app_token = entry.get("token", "")
            device_name = entry.get("name", "unknown")
            if not app_token:
                continue

            response = self._post_json(
                f"{RELAY_URL}/v2/widget-update", {}, app_token
            )
            http_error = response.get("_http_error")

            if response.get("success"):
                self.logger.debug(f"Widget refresh sent to {device_name}")
                any_success = True
            elif http_error == 403:
                self._subscription_expired = True
                self._expired_logged_at = datetime.now()
                self.logger.error("Widget refresh failed: subscription expired.")
                break
            elif http_error == 410:
                self.logger.debug(f"Token expired for {device_name} -- removing")
                self._remove_token(app_token)
            elif http_error == 429:
                self.logger.warning("Widget refresh rate limited -- try again later")
                break
            else:
                error_msg = response.get("error", "Unknown error")
                self.logger.error(f"Widget refresh to {device_name} failed: {error_msg}")

        if any_success:
            self.logger.info("Widget refresh sent to all devices")
        return any_success

    def refreshWidgets(self, action):
        target_device = action.props.get("targetDevice", "all")
        self._send_widget_refresh(target_device)

    # ═══════════════════════════════════════════════════
    # Database Connection (History)
    # ═══════════════════════════════════════════════════

    def _connect_db(self):
        db_type = self.pluginPrefs.get("dbType", "sqlite")

        if db_type == "sqlite":
            sqlite_path = self.pluginPrefs.get("sqlitePath", "").strip()
            if not sqlite_path:
                sqlite_path = self._auto_detect_sqlite_path()

            if not sqlite_path:
                self.logger.warning("History: Could not find SQL Logger database. "
                                    "Configure the path in plugin settings or ensure SQL Logger is enabled.")
                self.db = None
                return

            if not os.path.exists(sqlite_path):
                self.logger.error(f"History: SQLite database not found: {sqlite_path}")
                self.db = None
                return

            self.db = HistoryDB(
                db_type="sqlite",
                logger=self.logger,
                sqlite_path=sqlite_path,
            )
            self.logger.info(f"History: Connected to SQLite: {sqlite_path}")

        else:
            self.db = HistoryDB(
                db_type="postgresql",
                logger=self.logger,
                pg_host=self.pluginPrefs.get("pgHost", "127.0.0.1"),
                pg_port=self.pluginPrefs.get("pgPort", "5432"),
                pg_user=self.pluginPrefs.get("pgUser", "postgres"),
                pg_password=self.pluginPrefs.get("pgPassword", ""),
                pg_database=self.pluginPrefs.get("pgDatabase", "indigo_history"),
            )
            self.logger.info("History: Connecting to PostgreSQL")

        if self.db and self.db.test_connection():
            device_ids = self.db.get_device_tables()
            self.logger.info(f"History: Database connected ({len(device_ids)} device tables)")
        else:
            self.logger.error("History: Database connection failed")
            self.db = None

    def _auto_detect_sqlite_path(self):
        try:
            install_path = indigo.server.getInstallFolderPath()
            candidate = os.path.join(install_path, "Logs", "indigo_history.sqlite")
            if os.path.exists(candidate):
                return candidate
        except Exception:
            pass

        for version in ["Indigo 2025.1", "Indigo 2024.1", "Indigo 2023.2"]:
            candidate = f"/Library/Application Support/Perceptive Automation/{version}/Logs/indigo_history.sqlite"
            if os.path.exists(candidate):
                return candidate

        return None

    # ═══════════════════════════════════════════════════
    # IWS HTTP Endpoints (HTML Pages)
    # ═══════════════════════════════════════════════════

    def handle_pages(self, action, dev=None, caller_waiting_for_result=None):
        """GET /message/com.simons-plugins.domio/pages/ — return HTML page manifest."""
        reply = indigo.Dict()
        reply["headers"] = indigo.Dict({"Content-Type": "application/json"})

        pages_dir = os.path.join(self.pluginFolderPath, "Contents", "Resources", "static", "pages")
        pages = []

        if not os.path.isdir(pages_dir):
            self.logger.debug("Pages directory does not exist — returning empty manifest")
            reply["status"] = 200
            reply["content"] = json.dumps({"pages": []})
            return reply

        real_pages_dir = os.path.realpath(pages_dir)

        for filename in sorted(os.listdir(pages_dir)):
            if not filename.lower().endswith(".html"):
                continue

            filepath = os.path.join(pages_dir, filename)

            # Path traversal guard
            if not os.path.realpath(filepath).startswith(real_pages_dir):
                continue

            try:
                meta = self._parse_page_meta(filepath)
                page_id = os.path.splitext(filename)[0]
                pages.append({
                    "id": page_id,
                    "name": meta.get("name", page_id.replace("-", " ").title()),
                    "icon": meta.get("icon", "doc.richtext"),
                    "description": meta.get("description", ""),
                    "path": filename,
                })
            except (OSError, UnicodeDecodeError) as exc:
                self.logger.warning(f"Skipping page file {filename}: {exc}")

        self.logger.debug(f"Pages manifest: {len(pages)} page(s)")
        reply["status"] = 200
        reply["content"] = json.dumps({"pages": pages})
        return reply

    def _parse_page_meta(self, filepath):
        """Parse indigo-page-* meta tags from the first 4KB of an HTML file."""
        meta = {}
        with open(filepath, "r", encoding="utf-8") as f:
            head_content = f.read(4096)
        for match in re.finditer(
            r'<meta\s+name="indigo-page-(\w+)"\s+content="([^"]*)"',
            head_content, re.IGNORECASE,
        ):
            meta[match.group(1)] = match.group(2)
        return meta

    # ═══════════════════════════════════════════════════
    # IWS HTTP Endpoints (History)
    # ═══════════════════════════════════════════════════

    def handle_status(self, action, dev=None, caller_waiting_for_result=None):
        """GET /message/com.simons-plugins.domio/status/"""
        reply = indigo.Dict()
        reply["headers"] = indigo.Dict({"Content-Type": "application/json"})

        if self.db is None:
            reply["status"] = 200
            reply["content"] = json.dumps({
                "available": False,
                "error": "Database not connected",
            })
            return reply

        try:
            device_ids = self.db.get_device_tables()
            reply["status"] = 200
            reply["content"] = json.dumps({
                "available": True,
                "backend": self.pluginPrefs.get("dbType", "sqlite"),
                "device_count": len(device_ids),
            })
        except Exception as e:
            self.logger.error(f"Status check failed: {e}")
            reply["status"] = 500
            reply["content"] = json.dumps({
                "available": False,
                "error": str(e),
            })
        return reply

    def handle_history(self, action, dev=None, caller_waiting_for_result=None):
        """GET /message/com.simons-plugins.domio/history/?device_id=123&column=temperature&range=24h"""
        reply = indigo.Dict()
        reply["headers"] = indigo.Dict({"Content-Type": "application/json"})

        if self.db is None:
            reply["status"] = 503
            reply["content"] = json.dumps({"success": False, "error": "Database not connected"})
            return reply

        props = dict(action.props)
        query_args = props.get("url_query_args", {})

        device_id_str = query_args.get("device_id", "")
        if not device_id_str:
            reply["status"] = 400
            reply["content"] = json.dumps({"success": False, "error": "Missing required parameter: device_id"})
            return reply

        try:
            device_id = int(device_id_str)
        except (ValueError, TypeError):
            reply["status"] = 400
            reply["content"] = json.dumps({"success": False, "error": "device_id must be an integer"})
            return reply

        if query_args.get("columns", "").lower() == "true":
            return self._handle_columns(reply, device_id)

        column = query_args.get("column", "")
        time_range = query_args.get("range", "24h")
        max_points = int(query_args.get("max_points", "300"))

        if time_range not in ("1h", "6h", "24h", "7d", "30d"):
            reply["status"] = 400
            reply["content"] = json.dumps({"success": False, "error": f"Invalid range: {time_range}. Use 1h, 6h, 24h, 7d, or 30d"})
            return reply

        if not column:
            columns_info = self.db.get_columns(device_id)
            if not columns_info:
                reply["status"] = 404
                reply["content"] = json.dumps({"success": False, "error": f"No history table found for device {device_id}"})
                return reply
            for c in columns_info:
                if c["type"] in ("float", "int"):
                    column = c["name"]
                    break
            if not column:
                column = columns_info[0]["name"]

        try:
            result = self.db.query_history(device_id, column, time_range, max_points)

            reply["status"] = 200
            reply["content"] = json.dumps({
                "success": True,
                "device_id": device_id,
                "column": column,
                "range": time_range,
                "type": result["type"],
                "points": result["points"],
                "min": result["min"],
                "max": result["max"],
                "current": result["current"],
            })
        except Exception as e:
            self.logger.error(f"History query failed: {e}")
            reply["status"] = 500
            reply["content"] = json.dumps({"success": False, "error": str(e)})

        return reply

    def _handle_columns(self, reply, device_id):
        try:
            columns = self.db.get_columns(device_id)
            if not columns:
                reply["status"] = 404
                reply["content"] = json.dumps({
                    "success": False,
                    "error": f"No history table found for device {device_id}",
                })
                return reply

            reply["status"] = 200
            reply["content"] = json.dumps({
                "success": True,
                "device_id": device_id,
                "columns": columns,
            })
        except Exception as e:
            self.logger.error(f"Column query failed: {e}")
            reply["status"] = 500
            reply["content"] = json.dumps({"success": False, "error": str(e)})
        return reply

    # ═══════════════════════════════════════════════════
    # Menu Item Callbacks
    # ═══════════════════════════════════════════════════

    def sendTestNotification(self):
        self._send_push("Domio", "Test notification from Indigo", play_sound=True)

    def showStatus(self):
        tokens = self._get_app_tokens()
        last_result_json = self.pluginPrefs.get("lastPushResult", "")
        last_time = self.pluginPrefs.get("lastPushTime", "")

        self.logger.info("=== Domio Status ===")

        # Push status
        self.logger.info(f"Registered devices: {len(tokens)}")
        for entry in tokens:
            name = entry.get("name", "unknown")
            self.logger.info(f"  - {name}")
        if self._subscription_expired:
            self.logger.info("Push subscription: EXPIRED")
        elif tokens:
            self.logger.info("Push subscription: Active")
        else:
            self.logger.info("Push subscription: No devices registered")

        if last_result_json:
            try:
                result = json.loads(last_result_json)
                status = "Success" if result.get("success") else "Failed"
                self.logger.info(f"Last push: {status} at {last_time}")
            except json.JSONDecodeError:
                self.logger.info(f"Last push: {last_result_json} at {last_time}")
        else:
            self.logger.info("Last push: None")

        # History status
        if self.db:
            device_ids = self.db.get_device_tables()
            backend = self.pluginPrefs.get("dbType", "sqlite")
            self.logger.info(f"History database: {backend} ({len(device_ids)} device tables)")
        else:
            self.logger.info("History database: Not connected")

        self.logger.info(f"Debug logging: {'On' if self.debug else 'Off'}")

    def toggleDebugging(self):
        self.debug = not self.debug
        self.pluginPrefs["showDebugInfo"] = self.debug
        self.logger.info(f"Debug logging {'enabled' if self.debug else 'disabled'}")
