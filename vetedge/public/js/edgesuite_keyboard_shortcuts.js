(() => {
	const COMMAND_VERSION = "1.0.0";
	if (window.EdgeSuiteCommands?.version === COMMAND_VERSION) return;
	const registry = (window.EdgeSuiteCommands = window.EdgeSuiteCommands || {});
	const saveHandlers = new Map();
	let activeSaveHandler = null;

	function isMac() {
		return /Mac|iPhone|iPad|iPod/i.test(navigator.platform || navigator.userAgent || "");
	}

	function primaryModifier(event) {
		return isMac() ? event.metaKey : event.ctrlKey;
	}

	function editingSurface(target) {
		if (!(target instanceof Element)) return false;
		return Boolean(target.closest("textarea, [contenteditable='true'], .ql-editor, .CodeMirror, .ace_editor"));
	}

	function isVisible(element) {
		return Boolean(element && !element.hidden && element.getClientRects().length && getComputedStyle(element).visibility !== "hidden");
	}

	function notify(message, indicator = "blue") {
		if (window.frappe?.show_alert) frappe.show_alert({ message: __(message), indicator }, 4);
	}

	function registerSaveHandler(key, handler) {
		if (!key || typeof handler !== "function") return () => {};
		saveHandlers.set(key, handler);
		activeSaveHandler = key;
		return () => {
			saveHandlers.delete(key);
			if (activeSaveHandler === key) activeSaveHandler = null;
		};
	}

	function activateSaveHandler(key) {
		activeSaveHandler = saveHandlers.has(key) ? key : null;
	}

	async function invokeRegisteredSave() {
		const handler = activeSaveHandler ? saveHandlers.get(activeSaveHandler) : null;
		if (!handler) return false;
		const result = await handler({ source: "keyboard", command: "save" });
		return result !== false;
	}

	async function invokeEventSave() {
		const detail = { handled: false, promise: null, source: "keyboard", command: "save" };
		window.dispatchEvent(new CustomEvent("edgesuite:save-request", { detail }));
		if (!detail.handled) return false;
		if (detail.promise && typeof detail.promise.then === "function") await detail.promise;
		return true;
	}

	function findVisibleSaveControl() {
		const explicit = [...document.querySelectorAll("[data-edgesuite-save]:not([disabled])")].reverse().find(isVisible);
		if (explicit) return explicit;
		const activeDialog = [...document.querySelectorAll(".modal.show, .edge-modal[open], .edge-modal.is-open")].reverse().find(isVisible);
		if (!activeDialog) return null;
		const labels = new Set(["save", "save changes", "update", "apply changes"]);
		return [...activeDialog.querySelectorAll("button:not([disabled]), [role='button']:not([aria-disabled='true'])")]
			.reverse()
			.find((control) => {
				if (!isVisible(control)) return false;
				const label = String(control.dataset.label || control.getAttribute("aria-label") || control.textContent || "").trim().toLowerCase();
				return labels.has(label);
			}) || null;
	}

	async function invokeVisibleSaveControl() {
		const control = findVisibleSaveControl();
		if (!control) return false;
		control.click();
		return true;
	}

	async function invokeFrappeFormSave() {
		const form = window.cur_frm;
		if (!form?.doc || typeof form.save !== "function") return false;
		if (Number(form.doc.docstatus || 0) !== 0) {
			notify("Submitted documents cannot be changed with this shortcut.", "orange");
			return true;
		}
		if (typeof form.is_dirty === "function" && !form.is_dirty()) {
			notify("No unsaved changes.");
			return true;
		}
		await form.save();
		return true;
	}

	async function saveCurrentContext() {
		try {
			if (await invokeRegisteredSave()) return true;
			if (await invokeEventSave()) return true;
			if (await invokeVisibleSaveControl()) return true;
			return await invokeFrappeFormSave();
		} catch (error) {
			console.error("EdgeSuite save command failed", error);
			notify(error?.message || "Unable to save the current page.", "red");
			return true;
		}
	}

	function openCommandPalette() {
		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		if (typeof runtime?.openCommandPalette === "function") {
			runtime.openCommandPalette();
			return true;
		}
		const detail = { handled: false, source: "keyboard", command: "search" };
		window.dispatchEvent(new CustomEvent("edgesuite:command-palette-request", { detail }));
		return Boolean(detail.handled);
	}

	async function onKeydown(event) {
		if (!primaryModifier(event) || event.altKey) return;
		const key = String(event.key || "").toLowerCase();
		if (key === "s") {
			if (editingSurface(event.target) && !event.shiftKey) return;
			event.preventDefault();
			event.stopPropagation();
			await saveCurrentContext();
			return;
		}
		if (key === "k") {
			event.preventDefault();
			event.stopPropagation();
			openCommandPalette();
		}
	}

	registry.version = COMMAND_VERSION;
	registry.registerSaveHandler = registerSaveHandler;
	registry.activateSaveHandler = activateSaveHandler;
	registry.saveCurrentContext = saveCurrentContext;
	registry.openCommandPalette = openCommandPalette;

	if (!window.__edgeSuiteKeyboardCommandsBound) {
		window.__edgeSuiteKeyboardCommandsBound = true;
		document.addEventListener("keydown", onKeydown, true);
	}
})();
