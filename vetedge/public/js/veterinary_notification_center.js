(function () {
	const ROOT_ID = "veterinary-notification-center";
	const BADGE_SELECTOR = ".veterinary-notification-badge";
	const API = {
		count: "vetedge.services.notification_api.get_my_notification_count",
		feed: "vetedge.services.notification_api.get_my_notifications",
		read: "vetedge.services.notification_api.mark_my_notification_read",
		unread: "vetedge.services.notification_api.mark_my_notification_unread",
		acknowledge: "vetedge.services.notification_api.acknowledge_my_notification",
		done: "vetedge.services.notification_api.mark_my_notification_done",
		dismiss: "vetedge.services.notification_api.dismiss_my_notification",
		archive: "vetedge.services.notification_api.archive_my_notification",
		markAllRead: "vetedge.services.notification_api.mark_all_my_notifications_read",
	};
	const ACTIONS_BY_STATUS = {
		Unread: ["read", "acknowledge", "done", "dismiss", "archive"],
		Read: ["acknowledge", "done", "dismiss", "archive"],
		Acknowledged: ["done", "dismiss", "archive"],
		Done: ["archive"],
		Dismissed: ["archive"],
	};
	const ACTION_LABELS = {
		read: "Mark Read",
		unread: "Mark Unread",
		acknowledge: "Acknowledge",
		done: "Done",
		dismiss: "Dismiss",
		archive: "Archive",
	};

	const state = {
		dialog: null,
		drawerOpen: false,
		items: [],
		bootAttempts: 0,
	};

	function selectorEscape(value) {
		if (window.CSS && CSS.escape) {
			return CSS.escape(String(value));
		}
		return String(value).replace(/[^a-zA-Z0-9_-]/g, function (match) {
			return "\\" + match;
		});
	}

	function escapeHtml(value) {
		if (window.frappe && frappe.utils && frappe.utils.escape_html) {
			return frappe.utils.escape_html(value == null ? "" : String(value));
		}
		return String(value == null ? "" : value)
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;")
			.replace(/'/g, "&#039;");
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
				callback(r) {
					resolve(r.message || {});
				},
				error(error) {
					reject(error);
				},
			});
		});
	}

	function getNavbarTarget() {
		const selectors = [
			".navbar .navbar-nav.ms-auto",
			".navbar .navbar-nav.ml-auto",
			".navbar .navbar-right",
			".navbar .navbar-nav:last",
		];
		for (const selector of selectors) {
			const target = $(selector).last();
			if (target.length) {
				return target;
			}
		}
		return $();
	}

	function ensureIcon() {
		if ($("#" + ROOT_ID).length) {
			return true;
		}

		const target = getNavbarTarget();
		if (!target.length) {
			return false;
		}

		const item = $(`
			<li id="${ROOT_ID}" class="nav-item veterinary-notification-nav-item">
				<button class="nav-link veterinary-notification-button" type="button" title="${__("Notifications")}" aria-label="${__("Notifications")}">
					<span class="veterinary-notification-bell" aria-hidden="true">
						<svg viewBox="0 0 24 24" width="18" height="18" focusable="false">
							<path d="M18 16v-5a6 6 0 0 0-5-5.92V4a1 1 0 1 0-2 0v1.08A6 6 0 0 0 6 11v5l-2 2v1h16v-1l-2-2Zm-6 6a2.5 2.5 0 0 0 2.45-2h-4.9A2.5 2.5 0 0 0 12 22Z"></path>
						</svg>
					</span>
					<span class="veterinary-notification-badge hidden">0</span>
				</button>
			</li>
		`);

		target.append(item);
		item.on("click", ".veterinary-notification-button", () => openDrawer());
		return true;
	}

	function updateBadge(count) {
		const badge = $(`#${ROOT_ID} ${BADGE_SELECTOR}`);
		if (!badge.length) {
			return;
		}
		const unreadCount = Number(count || 0);
		if (unreadCount > 0) {
			badge.text(unreadCount > 99 ? "99+" : String(unreadCount)).removeClass("hidden");
		} else {
			badge.text("0").addClass("hidden");
		}
	}

	function refreshBadge() {
		return call(API.count)
			.then((message) => updateBadge(message.unread_count))
			.catch(() => updateBadge(0));
	}

	function formatDate(value) {
		if (!value) {
			return "";
		}
		if (window.frappe && frappe.datetime && frappe.datetime.str_to_user) {
			return frappe.datetime.str_to_user(value);
		}
		return value;
	}

	function sortNotifications(items) {
		return (items || []).slice().sort((left, right) => {
			if (left.status === "Unread" && right.status !== "Unread") {
				return -1;
			}
			if (left.status !== "Unread" && right.status === "Unread") {
				return 1;
			}
			return String(right.creation || "").localeCompare(String(left.creation || ""));
		});
	}

	function renderActionButton(action, item) {
		return `
			<button class="btn btn-xs btn-default veterinary-notification-action" data-action="${escapeHtml(action)}" data-name="${escapeHtml(item.name)}">
				${__(ACTION_LABELS[action])}
			</button>
		`;
	}

	function renderItem(item) {
		const status = item.status || "Unread";
		const actions = ACTIONS_BY_STATUS[status] || [];
		const openButton = item.action_url
			? `<button class="btn btn-xs btn-default veterinary-notification-open" data-url="${escapeHtml(item.action_url)}">${__("Open")}</button>`
			: "";
		const due = item.due_datetime
			? `<span class="veterinary-notification-meta-item">${__("Due")}: ${escapeHtml(formatDate(item.due_datetime))}</span>`
			: "";
		return `
			<div class="veterinary-notification-item ${status === "Unread" ? "is-unread" : ""}" data-name="${escapeHtml(item.name)}" data-status="${escapeHtml(status)}">
				<div class="veterinary-notification-item-main">
					<div class="veterinary-notification-title">${escapeHtml(item.title || __("Notification"))}</div>
					${item.message ? `<div class="veterinary-notification-message">${escapeHtml(item.message)}</div>` : ""}
					<div class="veterinary-notification-meta">
						${item.category ? `<span class="veterinary-notification-chip">${escapeHtml(item.category)}</span>` : ""}
						${item.priority ? `<span class="veterinary-notification-priority priority-${escapeHtml(String(item.priority).toLowerCase())}">${escapeHtml(item.priority)}</span>` : ""}
						<span class="veterinary-notification-status">${escapeHtml(status)}</span>
						${item.creation ? `<span class="veterinary-notification-meta-item">${escapeHtml(formatDate(item.creation))}</span>` : ""}
						${due}
					</div>
				</div>
				<div class="veterinary-notification-actions">
					${openButton}
					${actions.map((action) => renderActionButton(action, item)).join("")}
				</div>
			</div>
		`;
	}

	function drawerBody() {
		return state.dialog && state.dialog.fields_dict && state.dialog.fields_dict.notifications_html
			? state.dialog.fields_dict.notifications_html.$wrapper
			: $();
	}

	function renderDrawerLoading() {
		drawerBody().html(`<div class="veterinary-notification-empty">${__("Loading notifications...")}</div>`);
	}

	function renderDrawerError() {
		drawerBody().html(`<div class="veterinary-notification-empty">${__("Notifications could not be loaded.")}</div>`);
	}

	function renderDrawer(items) {
		const body = drawerBody();
		if (!items || !items.length) {
			body.html(`<div class="veterinary-notification-empty">${__("No active notifications.")}</div>`);
			return;
		}
		body.html(`<div class="veterinary-notification-list">${items.map(renderItem).join("")}</div>`);
	}

	function fetchDrawerFeed() {
		renderDrawerLoading();
		return call(API.feed, { limit: 50 })
			.then((message) => {
				state.items = sortNotifications(message.items || []);
				updateBadge(message.unread_count);
				renderDrawer(state.items);
			})
			.catch(() => {
					renderDrawerError();
				});
	}

	function ensureDialog() {
		if (state.dialog) {
			return state.dialog;
		}
		state.dialog = new frappe.ui.Dialog({
			title: __("Notifications"),
			size: "large",
			fields: [
				{
					fieldtype: "HTML",
					fieldname: "notifications_html",
				},
			],
			primary_action_label: __("Mark all read"),
			primary_action() {
				call(API.markAllRead)
					.then((message) => {
						updateBadge(message.unread_count);
						return fetchDrawerFeed();
					})
					.catch(() => frappe.show_alert({ message: __("Could not mark notifications read."), indicator: "red" }));
			},
		});
		state.dialog.$wrapper.addClass("veterinary-notification-dialog");
		state.dialog.$wrapper.on("hidden.bs.modal", () => {
			state.drawerOpen = false;
		});
		state.dialog.$wrapper.on("click", ".veterinary-notification-open", function () {
			openActionUrl($(this).data("url"));
		});
		state.dialog.$wrapper.on("click", ".veterinary-notification-action", function () {
			const button = $(this);
			runStatusAction(button.data("action"), button.data("name"), button);
		});
		return state.dialog;
	}

	function openDrawer() {
		if (!window.frappe || !frappe.ui || !frappe.ui.Dialog) {
			return;
		}
		const dialog = ensureDialog();
		state.drawerOpen = true;
		dialog.show();
		fetchDrawerFeed();
	}

	function runStatusAction(action, notificationName, button) {
		if (!API[action] || !notificationName) {
			return;
		}
		button.prop("disabled", true);
		call(API[action], { notification_name: notificationName })
			.then((message) => {
				updateBadge(message.unread_count);
				const row = state.dialog.$wrapper.find(`.veterinary-notification-item[data-name="${selectorEscape(notificationName)}"]`);
				row.attr("data-status", message.status || "").removeClass("is-unread");
				row.find(".veterinary-notification-status").text(message.status || "");
				return fetchDrawerFeed();
			})
			.catch(() => {
				frappe.show_alert({ message: __("Could not update notification."), indicator: "red" });
				button.prop("disabled", false);
			});
	}

	function normalizeDeskActionUrl(actionUrl) {
		const raw = String(actionUrl || "").trim();
		if (!raw) return "";
		if (raw === "/app" || raw.indexOf("/app/") === 0) return `/desk${raw.slice(4)}`;
		return raw;
	}

	function openActionUrl(actionUrl) {
		const target = normalizeDeskActionUrl(actionUrl);
		if (!target) {
			return;
		}
		if ((target === "/desk" || target.indexOf("/desk/") === 0) && window.frappe && frappe.set_route) {
			const url = new URL(target, window.location.origin);
			const route = url.pathname.replace(/^\/desk\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
			frappe.route_options = {};
			for (const [key, value] of url.searchParams) frappe.route_options[key] = value;
			if (route.length) frappe.set_route(...route);
			if (state.dialog) {
				state.dialog.hide();
			}
			return;
		}
		if (target[0] === "#" && window.frappe && frappe.set_route) {
			frappe.set_route(target.slice(1).split("/").filter(Boolean));
			if (state.dialog) {
				state.dialog.hide();
			}
			return;
		}
		window.location.href = target;
	}

	function bindRealtime() {
		if (!window.frappe || !frappe.realtime || !frappe.realtime.on || window.__veterinaryNotificationRealtimeBound) {
			return;
		}
		window.__veterinaryNotificationRealtimeBound = true;
		frappe.realtime.on("veterinary_notification_update", () => {
			refreshBadge();
			if (state.drawerOpen) {
				fetchDrawerFeed();
			}
		});
	}

	function boot() {
		if (!ensureIcon()) {
			if (state.bootAttempts < 5) {
				state.bootAttempts += 1;
				setTimeout(boot, 500);
			}
			return;
		}
		state.bootAttempts = 0;
		refreshBadge();
		bindRealtime();
	}

	function scheduleBoot() {
		if (!window.frappe || !window.$) {
			return;
		}
		setTimeout(boot, 0);
		$(document).on("page-change", boot);
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", scheduleBoot);
	} else {
		scheduleBoot();
	}

	window.veterinaryNotificationCenter = {
		boot,
		refreshBadge,
		openDrawer,
	};
})();
