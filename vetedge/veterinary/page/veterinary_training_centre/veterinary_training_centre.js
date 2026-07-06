frappe.pages["veterinary-training-centre"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Veterinary Training Centre"),
		single_column: true,
	});

	const view = new VetEdgeTrainingCentre(page);
	view.setup();
};

class VetEdgeTrainingCentre {
	constructor(page) {
		this.page = page;
		this.modules = [];
		this.currentModule = null;
		this.mermaidAssetPath = "/assets/vetedge/js/lib/mermaid.min.js";
		this.mermaidLoadPromise = null;
		this.body = $(`
			<div class="vetedge-training-centre">
				<div class="vtc-toolbar">
					<div>
						<h3>${__("Training Centre")}</h3>
						<p class="text-muted">${__("Open each Veterinary training module, read the guide, review screenshot references, and use the practice exercises. Videos can be added later.")}</p>
					</div>
					<div class="vtc-search-wrap">
						<input class="form-control vtc-search" placeholder="${__("Search modules")}">
					</div>
				</div>
				<div class="vtc-status text-muted">${__("Loading training modules...")}</div>
				<div class="vtc-list"></div>
				<div class="vtc-reader hidden">
					<div class="vtc-reader-header">
						<button class="btn btn-default btn-sm vtc-back">${__("Back to modules")}</button>
						<div>
							<h3 class="vtc-reader-title"></h3>
							<div class="text-muted vtc-reader-meta"></div>
						</div>
					</div>
					<div class="vtc-tabs">
						<button class="btn btn-primary btn-sm vtc-tab" data-tab="guide">${__("Read Guide")}</button>
						<button class="btn btn-default btn-sm vtc-tab" data-tab="video">${__("Watch Video")}</button>
						<button class="btn btn-default btn-sm vtc-tab" data-tab="screenshots">${__("Screenshots")}</button>
						<button class="btn btn-default btn-sm vtc-tab" data-tab="practice">${__("Practice Exercise")}</button>
					</div>
					<div class="vtc-panel vtc-guide"></div>
					<div class="vtc-panel vtc-video hidden"></div>
					<div class="vtc-panel vtc-screenshots hidden"></div>
					<div class="vtc-panel vtc-practice hidden"></div>
				</div>
			</div>
		`).appendTo(page.body);
	}

	setup() {
		this.add_styles();
		this.body.on("input", ".vtc-search", () => this.render_list());
		this.body.on("click", ".vtc-open", (event) => this.open_module($(event.currentTarget).data("module")));
		this.body.on("click", "a[data-training-module]", (event) => {
			event.preventDefault();
			this.open_module($(event.currentTarget).data("training-module"));
		});
		this.body.on("click", ".vtc-back", () => this.show_list());
		this.body.on("click", ".vtc-tab", (event) => this.show_tab($(event.currentTarget).data("tab")));
		this.load_modules();
	}

	load_modules() {
		frappe.call({
			method: "vetedge.services.training_centre.get_training_modules",
			freeze: true,
			freeze_message: __("Loading training modules..."),
			callback: (result) => {
				this.modules = result.message || [];
				this.open_requested_module_or_list();
			},
			error: () => {
				this.body.find(".vtc-status").text(__("Unable to load training modules."));
			},
		});
	}

	open_requested_module_or_list() {
		const moduleId = this.get_requested_module_id();
		if (!moduleId) {
			this.render_list();
			return;
		}
		if (!this.is_visible_module(moduleId)) {
			this.render_list();
			this.body.find(".vtc-status").removeClass("hidden").text(__("That training module is not available for your role."));
			this.update_training_url("");
			return;
		}
		this.open_module(moduleId, { updateUrl: false });
	}

	render_list() {
		const query = (this.body.find(".vtc-search").val() || "").toLowerCase().trim();
		const modules = this.modules.filter((module) => {
			const haystack = `${module.title || ""} ${module.short_description || module.description || ""} ${module.role_group || ""}`.toLowerCase();
			return !query || haystack.includes(query);
		});

		this.body.find(".vtc-reader").addClass("hidden");
		this.body.find(".vtc-toolbar, .vtc-list").removeClass("hidden");
		this.body.find(".vtc-status").toggleClass("hidden", Boolean(modules.length)).text(
			modules.length ? "" : __("No training modules found.")
		);
		this.body.find(".vtc-list").html(modules.map((module) => this.module_card(module)).join(""));
	}

	module_card(module) {
		const videoLabel = module.has_video ? __("Watch Video") : __("Video coming soon");
		const disabled = module.has_video ? "" : "disabled";
		const description = module.short_description || module.description || __("No description provided.");
		return `
			<div class="frappe-card vtc-card">
				<div>
					<div class="vtc-card-meta">${this.escape(module.role_group)} &middot; ${this.escape(module.status)}</div>
					<h4>${this.escape(module.title)}</h4>
					<p class="text-muted">${this.escape(description)}</p>
				</div>
				<div class="vtc-card-actions">
					<button class="btn btn-primary btn-sm vtc-open" data-module="${this.escape_attr(module.module_id)}">${__("Read Guide")}</button>
					<button class="btn btn-default btn-sm" ${disabled}>${videoLabel}</button>
				</div>
			</div>
		`;
	}

	open_module(moduleId, options = {}) {
		moduleId = String(moduleId || "").trim();
		if (!this.is_visible_module(moduleId)) {
			this.render_list();
			this.body.find(".vtc-status").removeClass("hidden").text(__("That training module is not available for your role."));
			this.update_training_url("");
			return;
		}
		if (options.updateUrl !== false) {
			this.update_training_url(moduleId);
		}
		frappe.call({
			method: "vetedge.services.training_centre.get_training_module_content",
			args: { module_id: moduleId },
			freeze: true,
			freeze_message: __("Loading guide..."),
			callback: (result) => this.render_module(result.message || {}),
		});
	}

	render_module(payload) {
		this.currentModule = payload;
		const module = payload.module || {};
		this.body.find(".vtc-toolbar, .vtc-list, .vtc-status").addClass("hidden");
		this.body.find(".vtc-reader").removeClass("hidden");
		this.body.find(".vtc-reader-title").text(module.title || __("Training Module"));
		this.body.find(".vtc-reader-meta").text(`${module.role_group || ""} - ${module.status || ""}`);
		const guide = this.body.find(".vtc-guide");
		guide.html(this.render_markdown(payload.markdown || ""));
		this.render_mermaid_blocks(guide.get(0));
		this.render_video(module);
		this.render_screenshots(payload.screenshots || []);
		const practice = this.body.find(".vtc-practice");
		practice.html(
			payload.practice_exercise
				? this.render_markdown(payload.practice_exercise)
				: `<div class="frappe-card p-4 text-muted">${__("No practice exercise section was found in this guide.")}</div>`
		);
		this.render_mermaid_blocks(practice.get(0));
		this.show_tab("guide");
	}

	render_video(module) {
		if (module.video_embed_url) {
			this.body.find(".vtc-video").html(`
				<div class="vtc-video-frame">
					<iframe src="${this.escape_attr(module.video_embed_url)}" title="${this.escape_attr(module.video_title || module.title || __("Training video"))}" allowfullscreen loading="lazy"></iframe>
				</div>
			`);
			return;
		}
		this.body.find(".vtc-video").html(`
			<div class="frappe-card p-4">
				<h4>${this.escape(module.video_display_status || __("Video coming soon"))}</h4>
				<p class="text-muted mb-0">${__("This module is ready for a future YouTube training video. Add the video URL later in the training module setup.")}</p>
			</div>
		`);
	}

	render_screenshots(screenshots) {
		if (!screenshots.length) {
			this.body.find(".vtc-screenshots").html(`<div class="frappe-card p-4 text-muted">${__("No screenshot references were found in this guide.")}</div>`);
			return;
		}
		this.body.find(".vtc-screenshots").html(`
			<div class="vtc-screenshot-grid">
				${screenshots.map((shot) => `
					<div class="frappe-card vtc-shot">
						<div class="text-muted small">${this.escape(shot.alt || __("Screenshot reference"))}</div>
						<code>${this.escape(shot.path || "")}</code>
					</div>
				`).join("")}
			</div>
		`);
	}

	show_list() {
		this.update_training_url("");
		this.render_list();
	}

	is_visible_module(moduleId) {
		return this.modules.some((module) => module.module_id === moduleId);
	}

	get_requested_module_id() {
		const params = new URLSearchParams(window.location.search || "");
		return (params.get("module") || "").trim();
	}

	update_training_url(moduleId) {
		const path = moduleId
			? `/app/veterinary-training-centre?module=${encodeURIComponent(moduleId)}`
			: "/app/veterinary-training-centre";
		if (window.location.pathname + window.location.search === path) {
			return;
		}
		window.history.pushState({}, "", path);
	}

	show_tab(tab) {
		this.body.find(".vtc-tab").removeClass("btn-primary").addClass("btn-default");
		this.body.find(`.vtc-tab[data-tab="${tab}"]`).removeClass("btn-default").addClass("btn-primary");
		this.body.find(".vtc-panel").addClass("hidden");
		this.body.find(`.vtc-${tab}`).removeClass("hidden");
	}

	async render_mermaid_blocks(container) {
		if (!container) {
			return;
		}
		const blocks = container.querySelectorAll(
			'pre code.language-mermaid, pre code.lang-mermaid, pre code[class*="mermaid"]'
		);
		if (!blocks.length) {
			return;
		}

		await this.load_mermaid_asset();

		if (window.mermaid) {
			this.initialize_mermaid();
		} else {
			console.warn("Mermaid is not available. Using the Training Centre flowchart renderer where possible.");
		}

		for (let i = 0; i < blocks.length; i++) {
			const code = blocks[i];
			const pre = code.closest("pre");
			const source = (code.textContent || "").trim();
			if (!pre || !source) {
				continue;
			}

			if (window.mermaid) {
				const wrapper = document.createElement("div");
				wrapper.className = "vetedge-training-mermaid";
				const diagramId = `vetedge-training-mermaid-${Date.now()}-${i}`;
				try {
					const result = await window.mermaid.render(diagramId, source);
					wrapper.innerHTML = result.svg || result;
					pre.replaceWith(wrapper);
					continue;
				} catch (error) {
					console.warn("Could not render Mermaid diagram", error);
					const fallback = this.render_simple_mermaid_flowchart(source);
					if (fallback) {
						pre.replaceWith(fallback);
						continue;
					}
					this.show_mermaid_fallback_note(pre);
				}
			}

			const fallback = this.render_simple_mermaid_flowchart(source);
			if (fallback) {
				pre.replaceWith(fallback);
			} else {
				this.show_mermaid_fallback_note(pre);
			}
		}
	}

	load_mermaid_asset() {
		if (window.mermaid) {
			return Promise.resolve(window.mermaid);
		}
		if (this.mermaidLoadPromise) {
			return this.mermaidLoadPromise;
		}

		this.mermaidLoadPromise = new Promise((resolve) => {
			const existing = document.querySelector(`script[src="${this.mermaidAssetPath}"]`);
			if (existing) {
				existing.addEventListener("load", () => resolve(window.mermaid || null), { once: true });
				existing.addEventListener("error", () => resolve(null), { once: true });
				return;
			}

			const script = document.createElement("script");
			script.src = this.mermaidAssetPath;
			script.async = true;
			script.onload = () => resolve(window.mermaid || null);
			script.onerror = () => {
				console.warn("Mermaid library could not be loaded from the local VetEdge asset.");
				resolve(null);
			};
			document.head.appendChild(script);
		});
		return this.mermaidLoadPromise;
	}

	initialize_mermaid() {
		if (this.mermaidInitialized) {
			return;
		}
		window.mermaid.initialize({
			startOnLoad: false,
			securityLevel: "strict",
			theme: "default",
			flowchart: {
				htmlLabels: false,
				useMaxWidth: true,
			},
		});
		this.mermaidInitialized = true;
	}

	show_mermaid_fallback_note(pre) {
		if (!pre || pre.classList.contains("vetedge-mermaid-render-error")) {
			return;
		}
		pre.classList.add("vetedge-mermaid-render-error");
		const note = document.createElement("div");
		note.className = "text-muted small vtc-mermaid-note";
		note.textContent = __("Diagram could not be rendered. Showing diagram source instead.");
		pre.parentNode.insertBefore(note, pre);
	}

	render_simple_mermaid_flowchart(source) {
		const lines = source.split("\n").map((line) => line.trim()).filter(Boolean);
		const first = lines[0] || "";
		const match = first.match(/^(flowchart|graph)\s+(TD|TB|BT|LR|RL)\s*$/i);
		if (!match) {
			return null;
		}

		const direction = match[2].toUpperCase();
		const nodes = new Map();
		const edges = [];
		const nodePattern = /([A-Za-z0-9_]+)(?:\[([^\]]+)\]|\{([^}]+)\})?/g;
		const addNode = (id, label, shape) => {
			if (!id) {
				return;
			}
			const cleanLabel = (label || nodes.get(id)?.label || id).trim();
			const existing = nodes.get(id);
			nodes.set(id, {
				id,
				label: cleanLabel,
				shape: shape || existing?.shape || "box",
			});
		};

		lines.slice(1).forEach((line) => {
			if (line.startsWith("%%")) {
				return;
			}
			const parts = line.split(/-->|---/).map((part) => part.replace(/^\|[^|]*\|/, "").trim()).filter(Boolean);
			if (parts.length < 2) {
				return;
			}
			const parsedParts = parts.map((part) => {
				const matches = [...part.matchAll(nodePattern)];
				const node = matches[matches.length - 1];
				if (!node) {
					return null;
				}
				const shape = node[3] ? "decision" : "box";
				addNode(node[1], node[2] || node[3], shape);
				return node[1];
			}).filter(Boolean);

			for (let idx = 0; idx < parsedParts.length - 1; idx++) {
				edges.push([parsedParts[idx], parsedParts[idx + 1]]);
			}
		});

		if (!nodes.size || !edges.length) {
			return null;
		}

		const wrapper = document.createElement("div");
		wrapper.className = `vetedge-training-mermaid vtc-simple-flowchart vtc-flow-${direction}`;

		const ordered = this.order_flowchart_nodes(nodes, edges);
		ordered.forEach((node, index) => {
			const nodeEl = document.createElement("div");
			nodeEl.className = `vtc-flow-node ${node.shape === "decision" ? "vtc-flow-decision" : ""}`;
			nodeEl.textContent = node.label;
			wrapper.appendChild(nodeEl);

			if (index < ordered.length - 1) {
				const arrow = document.createElement("div");
				arrow.className = "vtc-flow-arrow";
				arrow.textContent = direction === "LR" || direction === "RL" ? "→" : "↓";
				wrapper.appendChild(arrow);
			}
		});
		return wrapper;
	}

	order_flowchart_nodes(nodes, edges) {
		const indegree = new Map([...nodes.keys()].map((id) => [id, 0]));
		const outgoing = new Map([...nodes.keys()].map((id) => [id, []]));
		edges.forEach(([from, to]) => {
			if (!nodes.has(from) || !nodes.has(to)) {
				return;
			}
			indegree.set(to, (indegree.get(to) || 0) + 1);
			outgoing.get(from).push(to);
		});

		const queue = [...nodes.keys()].filter((id) => !indegree.get(id));
		const seen = new Set();
		const ordered = [];
		while (queue.length) {
			const id = queue.shift();
			if (seen.has(id)) {
				continue;
			}
			seen.add(id);
			ordered.push(nodes.get(id));
			(outgoing.get(id) || []).forEach((next) => {
				indegree.set(next, indegree.get(next) - 1);
				if (indegree.get(next) <= 0) {
					queue.push(next);
				}
			});
		}
		nodes.forEach((node, id) => {
			if (!seen.has(id)) {
				ordered.push(node);
			}
		});
		return ordered;
	}

	render_markdown(markdown) {
		const blocks = [];
		let inCode = false;
		let codeLang = "";
		let codeLines = [];
		const lines = (markdown || "").split("\n");

		for (let i = 0; i < lines.length; i++) {
			const line = lines[i];
			const codeMatch = line.match(/^```(.*)$/);
			if (codeMatch) {
				if (inCode) {
					blocks.push(`<pre><code class="language-${this.escape_attr(codeLang)}">${this.escape(codeLines.join("\n"))}</code></pre>`);
					inCode = false;
					codeLines = [];
					codeLang = "";
				} else {
					inCode = true;
					codeLang = (codeMatch[1] || "").trim();
				}
				continue;
			}
			if (inCode) {
				codeLines.push(line);
				continue;
			}

			if (!line.trim()) {
				blocks.push("");
				continue;
			}
			if (line.startsWith("|") && lines[i + 1] && /^\|\s*:?-{3,}/.test(lines[i + 1])) {
				const tableLines = [line, lines[i + 1]];
				i += 2;
				while (i < lines.length && lines[i].startsWith("|")) {
					tableLines.push(lines[i]);
					i++;
				}
				i--;
				blocks.push(this.render_table(tableLines));
				continue;
			}
			blocks.push(this.render_line(line));
		}
		if (inCode) {
			blocks.push(`<pre><code class="language-${this.escape_attr(codeLang)}">${this.escape(codeLines.join("\n"))}</code></pre>`);
		}
		return `<div class="vtc-markdown">${blocks.join("\n")}</div>`;
	}

	render_line(line) {
		const heading = line.match(/^(#{1,6})\s+(.+)$/);
		if (heading) {
			const level = Math.min(6, heading[1].length + 1);
			return `<h${level}>${this.inline(heading[2])}</h${level}>`;
		}
		const quote = line.match(/^>\s?(.*)$/);
		if (quote) {
			return `<blockquote>${this.inline(quote[1])}</blockquote>`;
		}
		const checklist = line.match(/^-\s+\[( |x|X)\]\s+(.+)$/);
		if (checklist) {
			const checked = checklist[1].toLowerCase() === "x" ? "checked" : "";
			return `<div class="vtc-check"><input type="checkbox" disabled ${checked}> <span>${this.inline(checklist[2])}</span></div>`;
		}
		const bullet = line.match(/^-\s+(.+)$/);
		if (bullet) {
			return `<div class="vtc-bullet">&bull; ${this.inline(bullet[1])}</div>`;
		}
		const numbered = line.match(/^\d+\.\s+(.+)$/);
		if (numbered) {
			return `<div class="vtc-numbered">${this.inline(line)}</div>`;
		}
		return `<p>${this.inline(line)}</p>`;
	}

	render_table(lines) {
		const split = (row) => row.split("|").slice(1, -1).map((cell) => cell.trim());
		const header = split(lines[0]);
		const rows = lines.slice(2).map(split);
		return `
			<div class="table-responsive">
				<table class="table table-bordered table-sm">
					<thead><tr>${header.map((cell) => `<th>${this.inline(cell)}</th>`).join("")}</tr></thead>
					<tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${this.inline(cell)}</td>`).join("")}</tr>`).join("")}</tbody>
				</table>
			</div>
		`;
	}

	inline(text) {
		return this.escape(text)
			.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_match, alt, src) => `<img class="vtc-guide-image" src="${this.escape_attr(src)}" alt="${this.escape_attr(alt)}" onerror="this.replaceWith(Object.assign(document.createElement('div'), {className: 'text-muted small', textContent: '${__("Screenshot pending or unavailable")}' }))">`)
			.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_match, label, href) => this.render_link(label, href))
			.replace(/`([^`]+)`/g, "<code>$1</code>")
			.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
	}

	render_link(label, href) {
		const converted = this.convert_training_href(href);
		const safeLabel = this.inline_text(label);
		if (converted.moduleId) {
			return `<a href="${this.escape_attr(converted.href)}" data-training-module="${this.escape_attr(converted.moduleId)}">${safeLabel}</a>`;
		}
		return `<a href="${this.escape_attr(converted.href)}" target="_blank" rel="noopener noreferrer">${safeLabel}</a>`;
	}

	convert_training_href(href) {
		href = String(href || "").trim();
		const match = href.match(/^training-module:([A-Za-z0-9_-]+)(#[A-Za-z0-9_.:-]+)?$/);
		if (!match || !this.is_visible_module(match[1])) {
			return { href, moduleId: "" };
		}
		const hash = match[2] || "";
		return {
			href: `/app/veterinary-training-centre?module=${encodeURIComponent(match[1])}${hash}`,
			moduleId: match[1],
		};
	}

	inline_text(text) {
		return this.escape(text)
			.replace(/`([^`]+)`/g, "<code>$1</code>")
			.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
	}

	escape(value) {
		return String(value ?? "")
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;")
			.replace(/'/g, "&#39;");
	}

	escape_attr(value) {
		return this.escape(value).replace(/`/g, "&#96;");
	}

	add_styles() {
		if (document.getElementById("vetedge-training-centre-styles")) {
			return;
		}
		$(`<style id="vetedge-training-centre-styles">
			.vetedge-training-centre { max-width: 1180px; margin: 0 auto; }
			.vtc-toolbar, .vtc-reader-header { display: flex; gap: 16px; align-items: flex-start; justify-content: space-between; margin-bottom: 16px; }
			.vtc-toolbar h3, .vtc-reader-title { margin: 0 0 6px; }
			.vtc-search-wrap { min-width: 260px; max-width: 360px; flex: 1; }
			.vtc-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; }
			.vtc-card { padding: 16px; display: flex; flex-direction: column; justify-content: space-between; min-height: 190px; }
			.vtc-card h4 { margin: 6px 0 8px; }
			.vtc-card-meta { font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: .04em; }
			.vtc-card-actions, .vtc-tabs { display: flex; gap: 8px; flex-wrap: wrap; }
			.vtc-reader { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 8px; padding: 18px; }
			.vtc-panel { margin-top: 16px; }
			.vtc-markdown { line-height: 1.6; }
			.vtc-markdown h2, .vtc-markdown h3, .vtc-markdown h4 { margin-top: 22px; }
			.vtc-markdown pre { background: var(--fg-color); border: 1px solid var(--border-color); border-radius: 6px; padding: 12px; overflow: auto; }
			.vtc-markdown blockquote { border-left: 3px solid var(--primary); padding: 8px 12px; background: var(--fg-color); color: var(--text-muted); }
			.vtc-bullet, .vtc-numbered, .vtc-check { margin: 4px 0; }
			.vtc-guide-image { max-width: 100%; border: 1px solid var(--border-color); border-radius: 6px; margin: 8px 0; }
			.vetedge-training-mermaid { background: var(--card-bg, #fff); border: 1px solid var(--border-color, #d1d8dd); border-radius: 8px; padding: 16px; margin: 16px 0; overflow-x: auto; }
			.vetedge-training-mermaid svg { max-width: 100%; height: auto; }
			.vtc-simple-flowchart { display: flex; flex-direction: column; align-items: center; gap: 8px; }
			.vtc-flow-LR, .vtc-flow-RL { flex-direction: row; align-items: stretch; }
			.vtc-flow-node { display: flex; align-items: center; justify-content: center; min-width: 180px; max-width: 260px; min-height: 48px; padding: 10px 12px; border: 1px solid var(--border-color, #d1d8dd); border-radius: 6px; background: var(--fg-color, #f8f8f8); color: var(--text-color, #1f272e); text-align: center; line-height: 1.35; }
			.vtc-flow-decision { border-radius: 999px; background: var(--control-bg, #fff); }
			.vtc-flow-arrow { display: flex; align-items: center; justify-content: center; color: var(--text-muted); font-size: 18px; min-width: 24px; }
			.vtc-mermaid-note { margin: 8px 0; }
			.vetedge-mermaid-render-error { border-color: var(--orange-300, #f4b860); }
			.vtc-video-frame { position: relative; padding-top: 56.25%; background: #000; border-radius: 8px; overflow: hidden; }
			.vtc-video-frame iframe { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; }
			.vtc-screenshot-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 10px; }
			.vtc-shot { padding: 12px; }
			@media (max-width: 768px) { .vtc-toolbar, .vtc-reader-header { flex-direction: column; } .vtc-search-wrap { min-width: 100%; } }
		</style>`).appendTo(document.head);
	}
}
