/**
 * Indigo API JavaScript Helper — V1
 *
 * Provides a clean client-side API for HTML pages served by Indigo plugins.
 * Reads connection credentials from window.INDIGO_CONFIG (injected by the
 * Domio iOS app's WKWebView, or set manually for browser testing).
 *
 * Usage:
 *   const indigo = new IndigoAPI();
 *   const devices = await indigo.getDevices();
 *   await indigo.turnOn(deviceId);
 */

class IndigoAPI {
    /**
     * @param {Object} [config] - Optional config override.
     * @param {string} config.baseURL - Indigo server base URL.
     * @param {string} config.apiKey - Bearer token for authentication.
     */
    constructor(config) {
        const cfg = config || window.INDIGO_CONFIG || IndigoAPI._configFromURL();
        if (!cfg || !cfg.baseURL || !cfg.apiKey) {
            this._configured = false;
            this._showConfigError();
            return;
        }
        this._configured = true;
        this._baseURL = cfg.baseURL.replace(/\/+$/, "");
        this._apiKey = cfg.apiKey;
        this._errorHandler = null;
        this._authFailureHandler = null;
    }

    // ── Configuration Check ──────────────────────────

    /** Check whether INDIGO_CONFIG is available. */
    static isConfigured() {
        const cfg = window.INDIGO_CONFIG || IndigoAPI._configFromURL();
        return !!(cfg && cfg.baseURL && cfg.apiKey);
    }

    /**
     * Derive config from the page's own URL for browser testing.
     * When loaded via IWS with `?api-key=KEY`, the origin is the Indigo
     * server and the key is in the query string.
     */
    static _configFromURL() {
        if (typeof location === "undefined") return null;
        const params = new URLSearchParams(location.search);
        const apiKey = params.get("api-key");
        if (!apiKey) return null;
        return { baseURL: location.origin, apiKey };
    }

    // ── Devices ──────────────────────────────────────

    /** Fetch all devices. @returns {Promise<Object[]>} */
    async getDevices() {
        return this._getList("/v2/api/indigo.devices");
    }

    /** Fetch a single device by ID. @returns {Promise<Object>} */
    async getDevice(id) {
        return this._get(`/v2/api/indigo.devices/${id}`);
    }

    /** Turn a device on. */
    async turnOn(id) {
        return this._command(id, "indigo.device.turnOn");
    }

    /** Turn a device off. */
    async turnOff(id) {
        return this._command(id, "indigo.device.turnOff");
    }

    /** Toggle a device. */
    async toggle(id) {
        return this._command(id, "indigo.device.toggle");
    }

    /** Set dimmer brightness (0-100). */
    async setBrightness(id, value) {
        return this._command(id, "indigo.dimmer.setBrightness", { value });
    }

    /** Set thermostat heat setpoint. */
    async setHeatSetpoint(id, value) {
        return this._command(id, "indigo.thermostat.setHeatSetpoint", { value });
    }

    /** Set thermostat cool setpoint. */
    async setCoolSetpoint(id, value) {
        return this._command(id, "indigo.thermostat.setCoolSetpoint", { value });
    }

    // ── Action Groups ────────────────────────────────

    /** Fetch all action groups. @returns {Promise<Object[]>} */
    async getActionGroups() {
        return this._getList("/v2/api/indigo.actionGroups");
    }

    /** Execute an action group by ID. */
    async executeActionGroup(id) {
        return this._post("/v2/api/command", {
            message: "indigo.actionGroup.execute",
            objectId: id,
        });
    }

    // ── Variables ────────────────────────────────────

    /** Fetch all variables. @returns {Promise<Object[]>} */
    async getVariables() {
        return this._getList("/v2/api/indigo.variables");
    }

    /** Fetch a single variable by ID. @returns {Promise<Object>} */
    async getVariable(id) {
        return this._get(`/v2/api/indigo.variables/${id}`);
    }

    // ── Reactive Polling ─────────────────────────────

    /**
     * Observe a single device, calling back when its state changes.
     * @param {number} deviceId - Device ID to observe.
     * @param {Function} callback - Called with the device object on each poll.
     * @param {number} [intervalMs=5000] - Poll interval in milliseconds.
     * @returns {{ stop: Function }} Call stop() to end observation.
     */
    observe(deviceId, callback, intervalMs = 5000) {
        let lastJson = null;
        const poll = async () => {
            try {
                const device = await this.getDevice(deviceId);
                const json = JSON.stringify(device);
                if (json !== lastJson) {
                    lastJson = json;
                    callback(device);
                }
            } catch (err) {
                this._handleError(err);
            }
        };
        poll(); // initial fetch
        const timer = setInterval(poll, intervalMs);
        return { stop: () => clearInterval(timer) };
    }

    /**
     * Observe all devices, calling back when any device state changes.
     * @param {Function} callback - Called with the full device array on each poll.
     * @param {number} [intervalMs=5000] - Poll interval in milliseconds.
     * @returns {{ stop: Function }} Call stop() to end observation.
     */
    observeAll(callback, intervalMs = 5000) {
        let lastJson = null;
        const poll = async () => {
            try {
                const devices = await this.getDevices();
                const json = JSON.stringify(devices);
                if (json !== lastJson) {
                    lastJson = json;
                    callback(devices);
                }
            } catch (err) {
                this._handleError(err);
            }
        };
        poll(); // initial fetch
        const timer = setInterval(poll, intervalMs);
        return { stop: () => clearInterval(timer) };
    }

    // ── Event Handlers ───────────────────────────────

    /** Register a global error handler. */
    onError(callback) {
        this._errorHandler = callback;
    }

    /** Register a handler for authentication failures (401/403). */
    onAuthFailure(callback) {
        this._authFailureHandler = callback;
    }

    // ── Internal Methods ─────────────────────────────

    async _get(path) {
        return this._fetch(path, { method: "GET" });
    }

    async _getList(path) {
        // Indigo REST API wraps lists in an outer object; extract the array.
        const data = await this._fetch(path, { method: "GET" });
        if (Array.isArray(data)) return data;
        // The API returns an array directly for list endpoints.
        return data;
    }

    async _post(path, body) {
        return this._fetch(path, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
    }

    async _put(path, body) {
        return this._fetch(path, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
    }

    async _command(deviceId, message, parameters) {
        const body = { message, objectId: deviceId };
        if (parameters) body.parameters = parameters;
        return this._post("/v2/api/command", body);
    }

    async _fetch(path, options = {}) {
        this._requireConfigured();

        const url = `${this._baseURL}${path}`;
        const headers = {
            Authorization: `Bearer ${this._apiKey}`,
            Accept: "application/json",
            ...options.headers,
        };

        let response;
        try {
            response = await fetch(url, { ...options, headers });
        } catch (err) {
            const error = new IndigoAPIError("Network error: " + err.message, 0, err);
            this._handleError(error);
            throw error;
        }

        if (response.status === 401 || response.status === 403) {
            const error = new IndigoAPIError(
                "Authentication failed — check your API key",
                response.status
            );
            if (this._authFailureHandler) this._authFailureHandler(error);
            this._handleError(error);
            throw error;
        }

        if (!response.ok) {
            const text = await response.text().catch(() => "");
            const error = new IndigoAPIError(
                `HTTP ${response.status}: ${text || response.statusText}`,
                response.status
            );
            this._handleError(error);
            throw error;
        }

        // Some commands return empty responses (204).
        const contentType = response.headers.get("Content-Type") || "";
        if (!contentType.includes("json")) return null;

        try {
            return await response.json();
        } catch (err) {
            const error = new IndigoAPIError("Invalid JSON response", response.status, err);
            this._handleError(error);
            throw error;
        }
    }

    _requireConfigured() {
        if (!this._configured) {
            throw new IndigoAPIError(
                "IndigoAPI is not configured — window.INDIGO_CONFIG is missing or incomplete",
                0
            );
        }
    }

    _handleError(error) {
        if (this._errorHandler) {
            try { this._errorHandler(error); } catch (_) { /* prevent handler errors from cascading */ }
        }
    }

    _showConfigError() {
        if (typeof document === "undefined") return;
        const banner = document.createElement("div");
        banner.id = "indigo-config-error";
        banner.style.cssText =
            "position:fixed;top:0;left:0;right:0;padding:12px 16px;" +
            "background:#dc3545;color:#fff;font:14px/1.4 -apple-system,sans-serif;" +
            "text-align:center;z-index:99999;";
        banner.textContent = "Indigo connection not configured. Open this page in the Domio app.";
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", () => document.body.prepend(banner));
        } else {
            document.body.prepend(banner);
        }
    }
}

/** Typed error class for Indigo API failures. */
class IndigoAPIError extends Error {
    /**
     * @param {string} message - Human-readable error description.
     * @param {number} status - HTTP status code (0 for network errors).
     * @param {Error} [cause] - Original error, if any.
     */
    constructor(message, status, cause) {
        super(message);
        this.name = "IndigoAPIError";
        this.status = status;
        if (cause) this.cause = cause;
    }
}
