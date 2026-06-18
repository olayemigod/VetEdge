(function () {
	const BADGE_ID = "veterinary-unread-bell-badge";
	const DRAWER_ID = "veterinary-unread-badge-drawer";
	const API_METHOD = "vetedge.services.notification_api.get_my_veterinary_unread_bell_count";
	const MARK_LOG_METHOD = "vetedge.services.notification_api.mark_my_veterinary_notification_read_for_log";
	const FEED_METHOD = "vetedge.services.notification_api.get_my_notifications";
	const MARK_ALL_READ_METHOD = "vetedge.services.notification_api.mark_all_my_veterinary_notifications_read";
	const ACTION_METHODS = {
		read: "vetedge.services.notification_api.mark_my_notification_read",
		acknowledge: "vetedge.services.notification_api.acknowledge_my_notification",
		done: "vetedge.services.notification_api.mark_my_notification_done",
		dismiss: "vetedge.services.notification_api.dismiss_my_notification",
		archive: "vetedge.services.notification_api.archive_my_notification",
	};

	function __(text) {
		return window.__ ? window.__(text) : text;
	}

	function escapeHtml(value) {
		return String(value == null ? "" : value)
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;")
			.replace(/'/g, "&#039;");
	}

	function scrub(value) {
		return String(value || "")
			.trim()
			.toLowerCase()
			.replace(/[^a-z0-9]+/g, "-")
			.replace(/^-|-$/g, "");
	}

	function call(method, args) {
		return new Promise((resolve, reject) => {
			if (!window.frappe || !frappe.call) {
				reject(new Error("Frappe Desk is not ready."));
				return;
			}
			frappe.call({
				method,
				args: args || {},
				callback(response) {
					resolve((response && response.message) || {});
				},
				error(error) {
					reject(error);
				},
			});
		});
	}

	function findAnchor() {
		const selectors = [
			".standard-items-sections .sidebar-notification",
			".sidebar-notification",
			".notifications-icon",
			".dropdown-notifications",
			".navbar .navbar-nav.ms-auto",
			".navbar .navbar-nav.ml-auto",
			".navbar .navbar-right",
		];
		for (const selector of selectors) {
			const element = document.querySelector(selector);
			if (element) {
				return element;
			}
		}
		return null;
	}

	function createBadge() {
		const badge = document.createElement("button");
		badge.id = BADGE_ID;
		badge.type = "button";
		badge.className = "veterinary-unread-bell-badge hidden";
		badge.title = __("Veterinary notifications");
		badge.setAttribute("aria-label", __("Veterinary unread notifications"));
		badge.innerHTML = `<span class="veterinary-unread-bell-badge-label">${__("Veterinary")}</span><span class="veterinary-unread-bell-badge-count">0</span>`;
		badge.addEventListener("click", function (event) {
			event.preventDefault();
			event.stopPropagation();
			toggleDrawer();
		});
		return badge;
	}

	function ensureBadge() {
		const existingBadges = Array.from(document.querySelectorAll("#" + BADGE_ID));
		if (existingBadges.length > 1) {
			existingBadges.slice(1).forEach((badge) => badge.remove());
		}
		if (existingBadges[0] && document.body.contains(existingBadges[0])) {
			return existingBadges[0];
		}

		const anchor = findAnchor();
		if (!anchor || !anchor.parentNode) {
			return null;
		}

		const badge = createBadge();
		if (anchor.classList.contains("sidebar-notification")) {
			anchor.insertAdjacentElement("afterend", badge);
		} else if (anchor.classList.contains("dropdown-notifications")) {
			anchor.parentNode.insertBefore(badge, anchor);
		} else {
			anchor.insertAdjacentElement("afterend", badge);
		}
		return badge;
	}

	function setCount(count) {
		const badge = ensureBadge();
		if (!badge) {
			return;
		}
		const unreadCount = Number(count || 0);
		const countElement = badge.querySelector(".veterinary-unread-bell-badge-count");
		if (countElement) {
			countElement.textContent = unreadCount > 99 ? "99+" : String(unreadCount);
		}
		badge.classList.toggle("hidden", unreadCount <= 0);
	}

	function refreshCount() {
		if (!window.frappe || !frappe.call) {
			return;
		}
		ensureBadge();
		frappe.call({
			method: API_METHOD,
			callback(response) {
				setCount(response && response.message ? response.message.unread_count : 0);
			},
			error() {
				setCount(0);
			},
		});
	}

	function markNativeNotificationRead(notificationLog) {
		if (!notificationLog || !window.frappe || !frappe.call) {
			return;
		}
		frappe.call({
			method: MARK_LOG_METHOD,
			args: { notification_log: notificationLog },
			callback(response) {
				setCount(response && response.message ? response.message.unread_count : 0);
			},
		});
	}

	function openNativeNotifications() {
		const nativeButton = document.querySelector(".standard-items-sections .sidebar-notification");
		if (nativeButton) {
			nativeButton.click();
			return;
		}
		if (window.frappe && frappe.set_route) {
			frappe.route_options = {
				for_user: frappe.session && frappe.session.user,
				read: 0,
			};
			frappe.set_route("List", "Notification Log");
		}
	}

	function ensureDrawer() {
		const drawers = Array.from(document.querySelectorAll("#" + DRAWER_ID));
		if (drawers.length > 1) {
			drawers.slice(1).forEach((drawer) => drawer.remove());
		}
		if (drawers[0] && document.body.contains(drawers[0])) {
			return drawers[0];
		}

		const drawer = document.createElement("div");
		drawer.id = DRAWER_ID;
		drawer.className = "veterinary-unread-badge-drawer hidden";
		drawer.innerHTML = `
			<div class="veterinary-unread-badge-drawer-header">
				<div class="veterinary-unread-badge-drawer-title">${__("Veterinary notifications")}</div>
				<button type="button" class="veterinary-unread-badge-drawer-action" data-drawer-action="mark-all-read">${__("Mark all read")}</button>
			</div>
			<div class="veterinary-unread-badge-drawer-body">
				<div class="veterinary-unread-badge-drawer-empty">${__("Loading Veterinary notifications...")}</div>
			</div>
		`;
		document.body.appendChild(drawer);
		drawer.addEventListener("click", handleDrawerClick);
		return drawer;
	}

	function positionDrawer() {
		const badge = document.getElementById(BADGE_ID);
		const drawer = ensureDrawer();
		if (!badge || !drawer) {
			return;
		}
		const rect = badge.getBoundingClientRect();
		const width = Math.min(420, Math.max(320, window.innerWidth - 24));
		const left = Math.min(Math.max(12, rect.left), window.innerWidth - width - 12);
		drawer.style.width = width + "px";
		drawer.style.left = left + "px";
		drawer.style.top = rect.bottom + 8 + "px";
	}

	function toggleDrawer() {
		const drawer = ensureDrawer();
		if (!drawer) {
			openNativeNotifications();
			return;
		}
		const shouldShow = drawer.classList.contains("hidden");
		if (!shouldShow) {
			closeDrawer();
			return;
		}
		positionDrawer();
		drawer.classList.remove("hidden");
		loadDrawer();
	}

	function closeDrawer() {
		const drawer = document.getElementById(DRAWER_ID);
		if (drawer) {
			drawer.classList.add("hidden");
		}
	}

	function drawerBody() {
		const drawer = ensureDrawer();
		return drawer ? drawer.querySelector(".veterinary-unread-badge-drawer-body") : null;
	}

	function setDrawerHtml(html) {
		const body = drawerBody();
		if (body) {
			body.innerHTML = html;
		}
	}

	function loadDrawer() {
		setDrawerHtml(`<div class="veterinary-unread-badge-drawer-empty">${__("Loading Veterinary notifications...")}</div>`);
		call(FEED_METHOD, { limit: 30 })
			.then((message) => {
				renderDrawer(message.items || []);
				refreshCount();
			})
			.catch(() => {
				setDrawerHtml(`<div class="veterinary-unread-badge-drawer-empty">${__("Veterinary notifications could not be loaded.")}</div>`);
			});
	}

	function activeItems(items) {
		const hiddenStatuses = new Set(["Done", "Dismissed", "Archived"]);
		return (items || [])
			.filter((item) => !hiddenStatuses.has(item.status))
			.sort((left, right) => {
				if (left.status === "Unread" && right.status !== "Unread") return -1;
				if (left.status !== "Unread" && right.status === "Unread") return 1;
				return String(right.creation || "").localeCompare(String(left.creation || ""));
			})
			.slice(0, 30);
	}

	function renderDrawer(items) {
		const rows = activeItems(items);
		if (!rows.length) {
			setDrawerHtml(`<div class="veterinary-unread-badge-drawer-empty">${__("No active Veterinary notifications.")}</div>`);
			return;
		}
		setDrawerHtml(rows.map(renderItem).join(""));
	}

	function renderItem(item) {
		const status = item.status || "Unread";
		const title = item.title || __("Veterinary notification");
		const actions = [
			item.action_url || item.reference_doctype || item.reference_name ? "open" : "",
			status === "Unread" ? "read" : "",
			status !== "Acknowledged" ? "acknowledge" : "",
			"done",
			"dismiss",
			"archive",
		].filter(Boolean);
		return `
			<div class="veterinary-unread-badge-drawer-item ${status === "Unread" ? "is-unread" : ""}" data-name="${escapeHtml(item.name)}" data-action-url="${escapeHtml(item.action_url || "")}" data-reference-doctype="${escapeHtml(item.reference_doctype || "")}" data-reference-name="${escapeHtml(item.reference_name || "")}">
				<div class="veterinary-unread-badge-drawer-item-title">${escapeHtml(title)}</div>
				${item.message ? `<div class="veterinary-unread-badge-drawer-message">${escapeHtml(item.message)}</div>` : ""}
				<div class="veterinary-unread-badge-drawer-meta">
					${item.category ? `<span>${escapeHtml(item.category)}</span>` : ""}
					${item.priority ? `<span>${escapeHtml(item.priority)}</span>` : ""}
					<span>${escapeHtml(status)}</span>
					${item.creation ? `<span>${escapeHtml(item.creation)}</span>` : ""}
					${item.due_datetime ? `<span>${__("Due")}: ${escapeHtml(item.due_datetime)}</span>` : ""}
				</div>
				<div class="veterinary-unread-badge-drawer-actions">
					${actions.map((action) => renderAction(action)).join("")}
				</div>
			</div>
		`;
	}

	function renderAction(action) {
		const labels = {
			open: __("Open"),
			read: __("Mark Read"),
			acknowledge: __("Acknowledge"),
			done: __("Done"),
			dismiss: __("Dismiss"),
			archive: __("Archive"),
		};
		return `<button type="button" class="veterinary-unread-badge-drawer-action" data-item-action="${escapeHtml(action)}">${labels[action]}</button>`;
	}

	function handleDrawerClick(event) {
		const drawerAction = event.target.closest("[data-drawer-action]");
		if (drawerAction && drawerAction.getAttribute("data-drawer-action") === "mark-all-read") {
			event.preventDefault();
			call(MARK_ALL_READ_METHOD)
				.then(() => {
					refreshCount();
					loadDrawer();
				})
				.catch(refreshCount);
			return;
		}

		const itemAction = event.target.closest("[data-item-action]");
		if (!itemAction) {
			return;
		}
		event.preventDefault();
		const item = itemAction.closest(".veterinary-unread-badge-drawer-item");
		const action = itemAction.getAttribute("data-item-action");
		if (action === "open") {
			routeToItem(item);
			closeDrawer();
			return;
		}
		const method = ACTION_METHODS[action];
		const name = item && item.getAttribute("data-name");
		if (!method || !name) {
			return;
		}
		call(method, { notification_name: name })
			.then(() => {
				refreshCount();
				loadDrawer();
			})
			.catch(refreshCount);
	}

	function routeToItem(item) {
		if (!window.frappe || !frappe.set_route || !item) {
			return;
		}
		const actionUrl = item.getAttribute("data-action-url");
		if (actionUrl) {
			frappe.set_route(actionUrl.replace(/^\/app\//, "").split("/"));
			return;
		}
		const referenceDoctype = item.getAttribute("data-reference-doctype");
		const referenceName = item.getAttribute("data-reference-name");
		if (referenceDoctype && referenceName) {
			frappe.set_route("Form", referenceDoctype, referenceName);
			return;
		}
		const name = item.getAttribute("data-name");
		if (name) {
			frappe.set_route("Form", "Veterinary Notification Item", name);
		}
	}

	function scheduleRefresh(delay) {
		window.setTimeout(refreshCount, delay);
	}

	function bindEvents() {
		if (window.frappe && frappe.router && frappe.router.on) {
			frappe.router.on("change", function () {
				closeDrawer();
				scheduleRefresh(250);
				scheduleRefresh(1000);
			});
		}
		if (window.frappe && frappe.realtime && frappe.realtime.on) {
			frappe.realtime.on("notification", function () {
				scheduleRefresh(250);
			});
		}
		document.addEventListener("visibilitychange", function () {
			if (!document.hidden) {
				refreshCount();
			}
		});
		document.addEventListener(
			"click",
			function (event) {
				const item = event.target.closest(".notification-item[data-name]");
				if (!item) {
					return;
				}
				markNativeNotificationRead(item.getAttribute("data-name"));
				scheduleRefresh(750);
				scheduleRefresh(1500);
			},
			true
		);
		document.addEventListener("click", function (event) {
			const drawer = document.getElementById(DRAWER_ID);
			const badge = document.getElementById(BADGE_ID);
			if (!drawer || drawer.classList.contains("hidden")) {
				return;
			}
			if (drawer.contains(event.target) || (badge && badge.contains(event.target))) {
				return;
			}
			closeDrawer();
		});
		window.addEventListener("resize", positionDrawer);
	}

	function boot() {
		ensureBadge();
		refreshCount();
		scheduleRefresh(500);
		scheduleRefresh(1500);
		bindEvents();
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", boot);
	} else {
		boot();
	}
})();
