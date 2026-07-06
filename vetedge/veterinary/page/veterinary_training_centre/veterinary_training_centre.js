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
		this.body = $(`
			<div class="vetedge-training-centre">
				<div class="vtc-toolbar">
					<div>
						<h3>${__("Training Centre")}</h3>
						<p class="text-muted">${__("Read Veterinary training guides module by module. Videos can be added later.")}</p>
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
				this.render_list();
			},
			error: () => {
				this.body.find(".vtc-status").text(__("Unable to load training modules."));
			},
		});
	}

	render_list() {
		const query = (this.body.find(".vtc-search").val() || "").toLowerCase().trim();
		const modules = this.modules.filter((module) => {
			const haystack = `${module.title || ""} ${module.description || ""} ${module.role_group || ""}`.toLowerCase();
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
		return `
			<div class="frappe-card vtc-card">
				<div>
					<div class="vtc-card-meta">${this.escape(module.role_group)} · ${this.escape(module.status)}</div>
					<h4>${this.escape(module.title)}</h4>
					<p class="text-muted">${this.escape(module.description || __("No description provided."))}</p>
				</div>
				<div class="vtc-card-actions">
					<button class="btn btn-primary btn-sm vtc-open" data-module="${this.escape_attr(module.module_id)}">${__("Read Guide")}</button>
					<button class="btn btn-default btn-sm" ${disabled}>${videoLabel}</button>
				</div>
			</div>
		`;
	}

	open_module(moduleId) {
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
		this.body.find(".vtc-reader-meta").text(`${module.role_group || ""} · ${module.status || ""}`);
		this.body.find(".vtc-guide").html(this.render_markdown(payload.markdown || ""));
		this.render_video(module);
		this.render_screenshots(payload.screenshots || []);
		this.body.find(".vtc-practice").html(
			payload.practice_exercise
				? this.render_markdown(payload.practice_exercise)
				: `<div class="frappe-card p-4 text-muted">${__("No practice exercise section was found in this guide.")}</div>`
		);
		this.show_tab("guide");
	}

	render_video(module) {
		if (module.video_embed_url) {
			this.body.find(".vtc-video").html(`
				<div class="vtc-video-frame">
					<iframe src="${this.escape_attr(module.video_embed_url)}" title="${this.escape_attr(module.title || __("Training video"))}" allowfullscreen loading="lazy"></iframe>
				</div>
			`);
			return;
		}
		this.body.find(".vtc-video").html(`
			<div class="frappe-card p-4">
				<h4>${this.escape(module.video_status || __("Video coming soon"))}</h4>
				<p class="text-muted mb-0">${__("A YouTube training video can be linked later in the module manifest.")}</p>
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
		this.render_list();
	}

	show_tab(tab) {
		this.body.find(".vtc-tab").removeClass("btn-primary").addClass("btn-default");
		this.body.find(`.vtc-tab[data-tab="${tab}"]`).removeClass("btn-default").addClass("btn-primary");
		this.body.find(".vtc-panel").addClass("hidden");
		this.body.find(`.vtc-${tab}`).removeClass("hidden");
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
			return `<div class="vtc-bullet">• ${this.inline(bullet[1])}</div>`;
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
			.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_match, label, href) => `<a href="${this.escape_attr(href)}" target="_blank" rel="noopener noreferrer">${label}</a>`)
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
			.vtc-video-frame { position: relative; padding-top: 56.25%; background: #000; border-radius: 8px; overflow: hidden; }
			.vtc-video-frame iframe { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; }
			.vtc-screenshot-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 10px; }
			.vtc-shot { padding: 12px; }
			@media (max-width: 768px) { .vtc-toolbar, .vtc-reader-header { flex-direction: column; } .vtc-search-wrap { min-width: 100%; } }
		</style>`).appendTo(document.head);
	}
}
