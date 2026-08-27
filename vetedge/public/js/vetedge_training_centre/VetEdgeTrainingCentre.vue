<template>
  <EdgeAppShell
    product="vetedge"
    activeRoute="/app/veterinary-training-centre"
    title="Veterinary"
    :tenantName="tenantName"
    :branchName="branchName"
    :userName="userName"
    data-edge-product="vetedge"
  >
    <EdgePageLayout>
      <template #header>
        <EdgePageHeader
          title="Training Centre"
          eyebrow="Help & Training"
          subtitle="Role-aware Veterinary guides, workflow references, videos and practice exercises."
        />
      </template>

      <div v-if="!currentModule" class="vtc-list-view">
        <div class="vtc-toolbar">
          <EdgeInput v-model="search" label="Search Training" placeholder="Search modules" />
          <button class="edge-button" type="button" :disabled="loading" @click="loadModules">Refresh</button>
        </div>

        <EdgeLoadingState v-if="loading" message="Loading training modules…" />
        <EdgeErrorState v-else-if="error" title="Training Centre could not load" :message="error" action-label="Try again" @retry="loadModules" />
        <EdgeEmptyState
          v-else-if="!filteredModules.length"
          title="No training modules found"
          description="No published training module matches the current search or your role."
        />
        <div v-else class="vtc-grid">
          <article v-for="module in filteredModules" :key="module.module_id" class="vtc-card">
            <div>
              <div class="vtc-card-meta">{{ module.role_group }} · {{ module.status }}</div>
              <h3>{{ module.title }}</h3>
              <p>{{ module.short_description || 'No description provided.' }}</p>
            </div>
            <div class="vtc-card-actions">
              <button class="edge-button edge-button--primary" type="button" @click="openModule(module.module_id)">Read Guide</button>
              <span class="vtc-video-status" :class="{ 'vtc-video-status--available': module.has_video }">
                {{ module.has_video ? 'Video available' : (module.video_display_status || 'Video coming soon') }}
              </span>
            </div>
          </article>
        </div>
      </div>

      <div v-else class="vtc-reader">
        <div class="vtc-reader-header">
          <button class="edge-button" type="button" @click="showList">Back to modules</button>
          <div class="vtc-reader-title-wrap">
            <div class="vtc-card-meta">{{ currentModule.module?.role_group }} · {{ currentModule.module?.status }}</div>
            <h2>{{ currentModule.module?.title || 'Training Module' }}</h2>
          </div>
        </div>

        <div class="vtc-tabs" role="tablist" aria-label="Training module sections">
          <button
            v-for="tab in tabs"
            :key="tab.value"
            class="edge-button"
            :class="{ 'edge-button--primary': activeTab === tab.value }"
            type="button"
            @click="activeTab = tab.value"
          >
            {{ tab.label }}
          </button>
        </div>

        <EdgeLoadingState v-if="moduleLoading" message="Loading guide…" />
        <EdgeErrorState
          v-else-if="moduleError"
          title="Training guide could not load"
          :message="moduleError"
          action-label="Try again"
          @retry="openModule(currentModuleId, { updateUrl: false })"
        />
        <div v-else class="vtc-panel">
          <div
            v-if="activeTab === 'guide'"
            ref="guidePanel"
            class="vtc-markdown-host"
            v-html="renderedGuide"
            @click="handleContentClick"
          ></div>

          <div v-else-if="activeTab === 'video'">
            <div v-if="currentModule.module?.video_embed_url" class="vtc-video-frame">
              <iframe
                :src="currentModule.module.video_embed_url"
                :title="currentModule.module.video_title || currentModule.module.title || 'Training video'"
                allowfullscreen
                loading="lazy"
              ></iframe>
            </div>
            <div v-else class="vtc-note-card">
              <h3>{{ currentModule.module?.video_display_status || 'Video coming soon' }}</h3>
              <p>This guide is available now. A validated training video can be added to the module later.</p>
            </div>
          </div>

          <div v-else-if="activeTab === 'screenshots'">
            <div v-if="currentModule.screenshots?.length" class="vtc-screenshot-grid">
              <article v-for="shot in currentModule.screenshots" :key="`${shot.path}:${shot.alt}`" class="vtc-shot">
                <div>{{ shot.alt || 'Screenshot reference' }}</div>
                <code>{{ shot.path }}</code>
              </article>
            </div>
            <EdgeEmptyState v-else title="No screenshot references" description="This guide does not currently contain screenshot references." />
          </div>

          <div v-else-if="activeTab === 'practice'">
            <div
              v-if="currentModule.practice_exercise"
              ref="practicePanel"
              class="vtc-markdown-host"
              v-html="renderedPractice"
              @click="handleContentClick"
            ></div>
            <EdgeEmptyState v-else title="No practice exercise" description="This guide does not currently contain a practice exercise section." />
          </div>
        </div>
      </div>
    </EdgePageLayout>
  </EdgeAppShell>
</template>

<script>
const runtimeComponents = () => {
  const runtime = typeof window !== 'undefined' ? (window.EdgeSuiteUI || window.EdgeUI || {}) : {};
  return runtime.components || runtime;
};

const requiredComponents = [
  'EdgeAppShell',
  'EdgePageLayout',
  'EdgePageHeader',
  'EdgeInput',
  'EdgeLoadingState',
  'EdgeErrorState',
  'EdgeEmptyState'
];

const MODULES_API = 'vetedge.services.training_centre.get_training_modules';
const CONTENT_API = 'vetedge.services.training_centre.get_training_module_content';
const MERMAID_ASSET = '/assets/vetedge/js/lib/mermaid.min.js';

export default {
  name: 'VetEdgeTrainingCentre',
  components: Object.fromEntries(requiredComponents.map((name) => [name, runtimeComponents()[name]])),
  data() {
    return {
      modules: [],
      search: '',
      loading: true,
      error: '',
      currentModule: null,
      currentModuleId: '',
      moduleLoading: false,
      moduleError: '',
      activeTab: 'guide',
      mermaidLoadPromise: null,
      mermaidInitialized: false,
      tenantName: '',
      branchName: 'All Branches',
      userName: '',
      tabs: [
        { value: 'guide', label: 'Read Guide' },
        { value: 'video', label: 'Watch Video' },
        { value: 'screenshots', label: 'Screenshots' },
        { value: 'practice', label: 'Practice Exercise' }
      ]
    };
  },
  computed: {
    filteredModules() {
      const query = String(this.search || '').trim().toLowerCase();
      if (!query) return this.modules;
      return this.modules.filter((module) => {
        const haystack = `${module.title || ''} ${module.short_description || ''} ${module.role_group || ''}`.toLowerCase();
        return haystack.includes(query);
      });
    },
    renderedGuide() {
      return this.renderMarkdown(this.currentModule?.markdown || '');
    },
    renderedPractice() {
      return this.renderMarkdown(this.currentModule?.practice_exercise || '');
    }
  },
  watch: {
    activeTab() {
      this.$nextTick(() => this.renderVisibleMermaid());
    }
  },
  mounted() {
    const missing = requiredComponents.filter((name) => !runtimeComponents()[name]);
    if (missing.length) {
      this.error = `The current EdgeSuite UI is missing: ${missing.join(', ')}`;
      this.loading = false;
      return;
    }
    window.VetedgeProductMenu?.mount?.();
    this.syncShellContext();
    this.loadModules();
  },
  methods: {
    syncShellContext() {
      const boot = window.frappe?.boot || {};
      const user = window.frappe?.session?.user || '';
      this.userName = boot.user_info?.[user]?.fullname || user || 'Veterinary User';
      this.tenantName = boot.sysdefaults?.company || 'Veterinary';
      this.branchName = boot.session_defaults?.branch || boot.edgesuite_product_menu?.branch || boot.user_info?.[user]?.branch || 'All Branches';
    },
    callFrappe(method, args = {}) {
      return new Promise((resolve, reject) => {
        if (!window.frappe?.call) return reject(new Error('Frappe Desk is not ready.'));
        frappe.call({ method, args, callback: (response) => resolve(response?.message || null), error: reject });
      });
    },
    requestedModuleId() {
      return new URLSearchParams(window.location.search || '').get('module')?.trim() || '';
    },
    async loadModules() {
      this.loading = true;
      this.error = '';
      try {
        const payload = await this.callFrappe(MODULES_API);
        this.modules = Array.isArray(payload) ? payload : [];
        const requested = this.requestedModuleId();
        if (requested) {
          if (this.modules.some((module) => module.module_id === requested)) {
            await this.openModule(requested, { updateUrl: false });
          } else {
            this.error = 'That training module is not available for your role.';
            this.updateTrainingUrl('');
          }
        }
      } catch (error) {
        this.error = error?.message || 'Unable to load training modules.';
      } finally {
        this.loading = false;
      }
    },
    async openModule(moduleId, options = {}) {
      moduleId = String(moduleId || '').trim();
      if (!moduleId || !this.modules.some((module) => module.module_id === moduleId)) {
        this.error = 'That training module is not available for your role.';
        return;
      }
      if (options.updateUrl !== false) this.updateTrainingUrl(moduleId);
      this.currentModuleId = moduleId;
      this.currentModule = { module: this.modules.find((module) => module.module_id === moduleId) || {} };
      this.moduleLoading = true;
      this.moduleError = '';
      this.activeTab = 'guide';
      try {
        this.currentModule = (await this.callFrappe(CONTENT_API, { module_id: moduleId })) || {};
        await this.$nextTick();
        await this.renderVisibleMermaid();
      } catch (error) {
        this.moduleError = error?.message || 'Unable to load this training guide.';
      } finally {
        this.moduleLoading = false;
      }
    },
    showList() {
      this.currentModule = null;
      this.currentModuleId = '';
      this.moduleError = '';
      this.activeTab = 'guide';
      this.updateTrainingUrl('');
    },
    updateTrainingUrl(moduleId) {
      const route = moduleId
        ? `/app/veterinary-training-centre?module=${encodeURIComponent(moduleId)}`
        : '/app/veterinary-training-centre';
      const current = `${window.location.pathname}${window.location.search}`;
      if (current !== route) window.history.pushState({}, '', route);
    },
    handleContentClick(event) {
      const link = event.target?.closest?.('a[data-training-module]');
      if (!link) return;
      event.preventDefault();
      const moduleId = link.getAttribute('data-training-module') || '';
      if (moduleId) this.openModule(moduleId);
    },
    escape(value) {
      return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    },
    escapeAttr(value) {
      return this.escape(value).replace(/`/g, '&#96;');
    },
    inlineText(text) {
      return this.escape(text)
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    },
    renderLink(label, href) {
      href = String(href || '').trim();
      const training = href.match(/^training-module:([A-Za-z0-9_-]+)(#[A-Za-z0-9_.:-]+)?$/);
      if (training && this.modules.some((module) => module.module_id === training[1])) {
        const target = `/app/veterinary-training-centre?module=${encodeURIComponent(training[1])}${training[2] || ''}`;
        return `<a href="${this.escapeAttr(target)}" data-training-module="${this.escapeAttr(training[1])}">${this.inlineText(label)}</a>`;
      }
      if (!/^(https?:\/\/|\/)/i.test(href)) return this.inlineText(label);
      return `<a href="${this.escapeAttr(href)}" target="_blank" rel="noopener noreferrer">${this.inlineText(label)}</a>`;
    },
    inline(text) {
      return this.escape(text)
        .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_match, alt, src) => {
          const safeSrc = /^(\/|https?:\/\/)/i.test(src) ? this.escapeAttr(src) : '';
          return safeSrc
            ? `<img class="vtc-guide-image" src="${safeSrc}" alt="${this.escapeAttr(alt)}" loading="lazy">`
            : this.escape(alt);
        })
        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_match, label, href) => this.renderLink(label, href))
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    },
    renderTable(lines) {
      const split = (row) => row.split('|').slice(1, -1).map((cell) => cell.trim());
      const header = split(lines[0]);
      const rows = lines.slice(2).map(split);
      return `<div class="vtc-table-wrap"><table><thead><tr>${header.map((cell) => `<th>${this.inline(cell)}</th>`).join('')}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${this.inline(cell)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
    },
    renderLine(line) {
      const heading = line.match(/^(#{1,6})\s+(.+)$/);
      if (heading) {
        const level = Math.min(6, heading[1].length + 1);
        return `<h${level}>${this.inline(heading[2])}</h${level}>`;
      }
      const quote = line.match(/^>\s?(.*)$/);
      if (quote) return `<blockquote>${this.inline(quote[1])}</blockquote>`;
      const checklist = line.match(/^-\s+\[( |x|X)\]\s+(.+)$/);
      if (checklist) {
        const checked = checklist[1].toLowerCase() === 'x' ? 'checked' : '';
        return `<div class="vtc-check"><input type="checkbox" disabled ${checked}> <span>${this.inline(checklist[2])}</span></div>`;
      }
      const bullet = line.match(/^-\s+(.+)$/);
      if (bullet) return `<div class="vtc-bullet">&bull; ${this.inline(bullet[1])}</div>`;
      if (/^\d+\.\s+/.test(line)) return `<div class="vtc-numbered">${this.inline(line)}</div>`;
      return `<p>${this.inline(line)}</p>`;
    },
    renderMarkdown(markdown) {
      const blocks = [];
      let inCode = false;
      let codeLang = '';
      let codeLines = [];
      const lines = String(markdown || '').split('\n');
      for (let index = 0; index < lines.length; index += 1) {
        const line = lines[index];
        const fence = line.match(/^```(.*)$/);
        if (fence) {
          if (inCode) {
            blocks.push(`<pre><code class="language-${this.escapeAttr(codeLang)}">${this.escape(codeLines.join('\n'))}</code></pre>`);
            inCode = false;
            codeLang = '';
            codeLines = [];
          } else {
            inCode = true;
            codeLang = String(fence[1] || '').trim();
          }
          continue;
        }
        if (inCode) {
          codeLines.push(line);
          continue;
        }
        if (!line.trim()) {
          blocks.push('');
          continue;
        }
        if (line.startsWith('|') && lines[index + 1] && /^\|\s*:?-{3,}/.test(lines[index + 1])) {
          const tableLines = [line, lines[index + 1]];
          index += 2;
          while (index < lines.length && lines[index].startsWith('|')) {
            tableLines.push(lines[index]);
            index += 1;
          }
          index -= 1;
          blocks.push(this.renderTable(tableLines));
          continue;
        }
        blocks.push(this.renderLine(line));
      }
      if (inCode) {
        blocks.push(`<pre><code class="language-${this.escapeAttr(codeLang)}">${this.escape(codeLines.join('\n'))}</code></pre>`);
      }
      return `<div class="vtc-markdown">${blocks.join('\n')}</div>`;
    },
    loadMermaid() {
      if (window.mermaid) return Promise.resolve(window.mermaid);
      if (this.mermaidLoadPromise) return this.mermaidLoadPromise;
      this.mermaidLoadPromise = new Promise((resolve) => {
        const existing = document.querySelector(`script[src="${MERMAID_ASSET}"]`);
        if (existing) {
          existing.addEventListener('load', () => resolve(window.mermaid || null), { once: true });
          existing.addEventListener('error', () => resolve(null), { once: true });
          return;
        }
        const script = document.createElement('script');
        script.src = MERMAID_ASSET;
        script.async = true;
        script.onload = () => resolve(window.mermaid || null);
        script.onerror = () => resolve(null);
        document.head.appendChild(script);
      });
      return this.mermaidLoadPromise;
    },
    async renderVisibleMermaid() {
      const container = this.activeTab === 'practice' ? this.$refs.practicePanel : this.$refs.guidePanel;
      if (!container) return;
      const blocks = container.querySelectorAll('pre code.language-mermaid, pre code.lang-mermaid, pre code[class*="mermaid"]');
      if (!blocks.length) return;
      const mermaid = await this.loadMermaid();
      if (!mermaid) return;
      if (!this.mermaidInitialized) {
        mermaid.initialize({ startOnLoad: false, securityLevel: 'strict' });
        this.mermaidInitialized = true;
      }
      for (let index = 0; index < blocks.length; index += 1) {
        const code = blocks[index];
        const pre = code.closest('pre');
        if (!pre || pre.dataset.mermaidRendered === '1') continue;
        const source = String(code.textContent || '').trim();
        if (!source) continue;
        try {
          const result = await mermaid.render(`vetedge-training-${Date.now()}-${index}`, source);
          const wrapper = document.createElement('div');
          wrapper.className = 'vetedge-training-mermaid';
          wrapper.innerHTML = result.svg || result;
          pre.dataset.mermaidRendered = '1';
          pre.replaceWith(wrapper);
        } catch (_error) {
          pre.classList.add('vtc-mermaid-fallback');
        }
      }
    }
  }
};
</script>

<style scoped>
.vtc-list-view, .vtc-reader { width: 100%; }
.vtc-toolbar { display: flex; gap: 12px; align-items: flex-end; justify-content: space-between; margin-bottom: 18px; }
.vtc-toolbar > :first-child { flex: 1; max-width: 420px; }
.vtc-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(270px, 1fr)); gap: 14px; }
.vtc-card, .vtc-note-card, .vtc-shot, .vtc-reader { border: 1px solid var(--edge-border, #dfe3e8); border-radius: 10px; background: var(--edge-surface, #fff); }
.vtc-card { display: flex; flex-direction: column; justify-content: space-between; min-height: 190px; padding: 18px; }
.vtc-card h3 { margin: 7px 0 8px; font-size: 1rem; }
.vtc-card p, .vtc-note-card p { color: var(--edge-text-muted, #667085); }
.vtc-card-meta { color: var(--edge-text-muted, #667085); font-size: 0.75rem; letter-spacing: .04em; text-transform: uppercase; }
.vtc-card-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-top: 14px; }
.vtc-video-status { font-size: .78rem; color: var(--edge-text-muted, #667085); }
.vtc-video-status--available { color: var(--edge-success, #16803b); }
.vtc-reader { padding: 20px; }
.vtc-reader-header { display: flex; gap: 16px; align-items: flex-start; margin-bottom: 16px; }
.vtc-reader-title-wrap { flex: 1; }
.vtc-reader-title-wrap h2 { margin: 5px 0 0; }
.vtc-tabs { display: flex; gap: 8px; flex-wrap: wrap; }
.vtc-panel { margin-top: 18px; }
.vtc-note-card, .vtc-shot { padding: 16px; }
.vtc-video-frame { position: relative; padding-top: 56.25%; background: #000; border-radius: 10px; overflow: hidden; }
.vtc-video-frame iframe { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; }
.vtc-screenshot-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 12px; }
.vtc-shot code { display: block; margin-top: 8px; overflow-wrap: anywhere; }
@media (max-width: 700px) {
  .vtc-toolbar, .vtc-reader-header { flex-direction: column; align-items: stretch; }
  .vtc-toolbar > :first-child { max-width: none; }
}
</style>

<style>
.vtc-markdown { line-height: 1.65; color: var(--edge-text, #172033); }
.vtc-markdown h2, .vtc-markdown h3, .vtc-markdown h4 { margin-top: 22px; }
.vtc-markdown pre { overflow: auto; padding: 12px; border: 1px solid var(--edge-border, #dfe3e8); border-radius: 8px; background: var(--edge-surface-muted, #f6f7f9); }
.vtc-markdown blockquote { margin-left: 0; padding: 8px 12px; border-left: 3px solid var(--edge-primary, #2563eb); background: var(--edge-surface-muted, #f6f7f9); color: var(--edge-text-muted, #667085); }
.vtc-bullet, .vtc-numbered, .vtc-check { margin: 4px 0; }
.vtc-guide-image { max-width: 100%; height: auto; margin: 8px 0; border: 1px solid var(--edge-border, #dfe3e8); border-radius: 8px; }
.vtc-table-wrap { overflow-x: auto; }
.vtc-table-wrap table { width: 100%; border-collapse: collapse; }
.vtc-table-wrap th, .vtc-table-wrap td { padding: 8px; border: 1px solid var(--edge-border, #dfe3e8); text-align: left; vertical-align: top; }
.vetedge-training-mermaid { overflow-x: auto; margin: 16px 0; padding: 16px; border: 1px solid var(--edge-border, #dfe3e8); border-radius: 8px; background: var(--edge-surface, #fff); }
.vetedge-training-mermaid svg { max-width: 100%; height: auto; }
.vtc-mermaid-fallback { border-color: var(--edge-warning, #d97706) !important; }
</style>
