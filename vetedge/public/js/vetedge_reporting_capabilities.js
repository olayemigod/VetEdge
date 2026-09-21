(function () {
	const cache = new Map();

	function key(scopeName, scopeType) {
		return `${String(scopeType || "report").toLowerCase()}:${String(scopeName || "").trim()}`;
	}

	async function get(scopeName, scopeType = "report", { refresh = false } = {}) {
		const cacheKey = key(scopeName, scopeType);
		if (!refresh && cache.has(cacheKey)) return cache.get(cacheKey);
		const response = await frappe.call({
			method: "vetedge.services.reporting_capabilities.get_shell_capabilities",
			args: { scope_name: scopeName, scope_type: scopeType },
		});
		const capabilities = response.message || {
			can_view: false,
			can_print: false,
			can_export: false,
		};
		cache.set(cacheKey, capabilities);
		return capabilities;
	}

	function clear(scopeName, scopeType = "report") {
		if (scopeName) cache.delete(key(scopeName, scopeType));
		else cache.clear();
	}

	window.VetEdgeReportingCapabilities = Object.freeze({ get, clear });
})();
