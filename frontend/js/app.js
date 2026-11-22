const AUTO_REFRESH_MS = 60 * 1000;

const PERIOD_PREV_LABELS = {
    today: "vs hier à la même heure",
    week: "vs semaine dernière au même moment",
    month: "vs mois dernier au même moment",
    year: "vs l'an dernier au même moment",
    all: ""
};

function esc(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function localDateStr(d = new Date()) {
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

class App {
    constructor() {
        this.currentView = 'dashboard';
        this.currentPeriod = 'week';
        this.ready = false;
        this.searchQuery = '';
        this.categoryFilter = '';
        this.availableCategories = [];
        this.searchDebounceTimer = null;
        this.timelineDate = null; // null = today
        this.requestIds = {};
        this.loadingCount = 0;
        this.modalApp = null;

        // pywebview injects window.pywebview.api then fires "pywebviewready".
        // It may already be there if the event fired before this script ran.
        if (window.pywebview && window.pywebview.api) {
            this.init();
        } else {
            window.addEventListener('pywebviewready', () => this.init());
        }

        // Keep the displayed data fresh while the window is visible
        setInterval(() => this.autoRefresh(), AUTO_REFRESH_MS);
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible') this.autoRefresh();
        });
        window.addEventListener('focus', () => this.autoRefresh());
        document.querySelectorAll('#evo-granularity .seg-btn').forEach(b =>
            b.addEventListener('click', () => this.setEvolutionGranularity(b.dataset.g)));
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') this.closeAppModal();
        });
    }

    get api() {
        return window.pywebview && window.pywebview.api;
    }

    init() {
        if (this.ready) return;
        this.ready = true;
        this.navigate('dashboard');
    }

    // Called by Python every time the window is shown from the tray icon
    onWindowShown() {
        if (!this.ready) {
            if (this.api) this.init();
            return;
        }
        this.refreshData();
    }

    autoRefresh() {
        if (!this.ready || document.visibilityState !== 'visible') return;
        if (this.modalApp) return;
        if (Date.now() - (this.lastRefresh || 0) < AUTO_REFRESH_MS / 2) return;
        // Only refresh read-only views (do not interfere with editing)
        if (['dashboard', 'timeline', 'analytics'].includes(this.currentView)) {
            this.refreshData({ silent: true });
        }
    }

    // A new request for a view invalidates the previous one still in flight
    _newRequest(key) {
        this.requestIds[key] = (this.requestIds[key] || 0) + 1;
        return this.requestIds[key];
    }

    _isStale(key, id) {
        return this.requestIds[key] !== id;
    }

    showLoader(show) {
        this.loadingCount = Math.max(0, this.loadingCount + (show ? 1 : -1));
        const loader = document.getElementById('loader');
        if (loader) loader.classList.toggle('hidden', this.loadingCount === 0);
    }

    toast(message, type = 'success') {
        const el = document.getElementById('toast');
        if (!el) return;
        el.textContent = message;
        el.className = `toast ${type}`;
        clearTimeout(this.toastTimer);
        this.toastTimer = setTimeout(() => el.classList.add('hidden'), 4000);
    }

    markUpdated() {
        this.lastRefresh = Date.now();
        const el = document.getElementById('last-update');
        if (el) {
            const t = new Date();
            el.textContent = `Mis à jour à ${String(t.getHours()).padStart(2, '0')}:${String(t.getMinutes()).padStart(2, '0')}`;
        }
    }

    navigate(viewId) {
        document.querySelectorAll('nav a').forEach(el => el.classList.remove('active'));
        const activeNav = document.getElementById(`nav-${viewId}`);
        if (activeNav) activeNav.classList.add('active');

        document.querySelectorAll('.page-view').forEach(el => el.classList.add('hidden'));
        const targetView = document.getElementById(`view-${viewId}`);
        if (targetView) targetView.classList.remove('hidden');

        const titles = {
            dashboard: 'Dashboard',
            timeline: 'Chronologie',
            analytics: 'Statistiques avancées',
            applications: 'Applications',
            settings: 'Paramètres'
        };
        document.getElementById('page-title').textContent = titles[viewId] || 'Trackr';

        // The period selector is meaningless for the timeline and the settings
        const controls = document.getElementById('period-controls');
        if (controls) controls.classList.toggle('invisible', viewId === 'timeline' || viewId === 'settings');

        this.currentView = viewId;
        this.refreshData();
    }

    changePeriod(period) {
        const range = document.getElementById('custom-range');
        if (period === 'custom') {
            range.classList.remove('hidden');
            range.classList.add('flex');
            const startInput = document.getElementById('custom-start');
            const endInput = document.getElementById('custom-end');
            const today = localDateStr();
            startInput.max = endInput.max = today;
            if (!startInput.value || !endInput.value) {
                const weekAgo = new Date();
                weekAgo.setDate(weekAgo.getDate() - 6);
                startInput.value = localDateStr(weekAgo);
                endInput.value = today;
            }
            this.applyCustomRange();
            return;
        }
        range.classList.add('hidden');
        range.classList.remove('flex');
        this.currentPeriod = period;
        this.refreshData();
    }

    applyCustomRange() {
        const startInput = document.getElementById('custom-start');
        const endInput = document.getElementById('custom-end');
        let start = startInput.value;
        let end = endInput.value;
        if (!start || !end) return;
        if (start > end) {
            [start, end] = [end, start];
            startInput.value = start;
            endInput.value = end;
        }
        this.currentPeriod = `custom:${start}:${end}`;
        this.refreshData();
    }

    isCustomPeriod(period = this.currentPeriod) {
        return typeof period === 'string' && period.startsWith('custom:');
    }

    // Human label of a period ("Cette semaine", "du 03/11 au 09/11"...)
    periodLabel(period = this.currentPeriod) {
        if (this.isCustomPeriod(period)) {
            const [, start, end] = period.split(':');
            const fmt = (d) => new Date(d + 'T12:00:00').toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' });
            return start === end ? `Le ${fmt(start)}` : `Du ${fmt(start)} au ${fmt(end)}`;
        }
        const opt = document.querySelector(`#period-selector option[value="${period}"]`);
        return opt ? opt.textContent : '';
    }

    prevLabel(period = this.currentPeriod) {
        if (this.isCustomPeriod(period)) {
            const [, start, end] = period.split(':');
            const days = Math.round((new Date(end + 'T12:00:00') - new Date(start + 'T12:00:00')) / 86400000) + 1;
            return days === 1 ? 'vs la veille' : `vs les ${days} jours précédents`;
        }
        return PERIOD_PREV_LABELS[period] || '';
    }

    refreshData(options = {}) {
        if (!this.api) return;
        const silent = !!options.silent;
        window.charts.setAnimated(!silent);

        if (this.currentView === 'dashboard') {
            this.loadDashboard(silent);
        } else if (this.currentView === 'timeline') {
            this.loadTimeline(silent);
        } else if (this.currentView === 'analytics') {
            this.loadAnalytics(silent);
        } else if (this.currentView === 'applications') {
            this.loadApplications(silent);
        } else if (this.currentView === 'settings') {
            this.loadSettings();
        }
    }

    formatDuration(seconds) {
        if (!seconds || seconds <= 0) return '0m';
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        if (h > 0) return `${h}h${m > 0 ? ' ' + String(m).padStart(2, '0') + 'm' : ''}`;
        if (m === 0) return `${Math.floor(seconds)}s`;
        return `${m}m`;
    }

    deltaHtml(pct, suffix = '') {
        if (pct === null || pct === undefined) return `<span class="text-slate-500">${suffix ? 'Pas de comparaison' : '-'}</span>`;
        const up = pct > 0;
        const cls = Math.abs(pct) < 1 ? 'text-slate-400' : (up ? 'delta-up' : 'delta-down');
        const arrow = Math.abs(pct) < 1 ? '≈' : (up ? '▲' : '▼');
        return `<span class="${cls} font-semibold">${arrow} ${up ? '+' : ''}${pct}%</span> <span class="text-slate-500">${esc(suffix)}</span>`;
    }

    categoryBadge(category, size = 'text-[10px]') {
        const color = window.charts.getCategoryColor(category);
        return `<span class="inline-block ${size} px-1.5 py-0.5 rounded font-medium" style="background-color:${color}20;color:${color};border:1px solid ${color}40;">${esc(category)}</span>`;
    }

    appRowHtml(appItem, index, duration, percentage) {
        return `
            <div class="app-row" data-app="${esc(appItem.app_name)}">
                <div class="flex items-center space-x-3 overflow-hidden">
                    <div class="w-5 text-center text-slate-500 font-bold text-xs">${index + 1}</div>
                    <div class="min-w-0">
                        <p class="text-sm font-medium text-white truncate">${esc(appItem.app_name)}</p>
                        ${this.categoryBadge(appItem.category)}
                    </div>
                </div>
                <div class="text-right pl-4 shrink-0">
                    <p class="text-sm font-semibold text-white">${this.formatDuration(duration)}</p>
                    <p class="text-xs text-slate-400">${percentage}%</p>
                </div>
            </div>`;
    }

    bindAppRows(container) {
        container.querySelectorAll('[data-app]').forEach(el => {
            el.addEventListener('click', () => this.openAppModal(el.dataset.app));
        });
    }

    // ------------------------------------------------------------------ DASHBOARD
    async loadDashboard(silent = false) {
        const req = this._newRequest('dashboard');
        if (!silent) this.showLoader(true);
        try {
            const [data, heatmapData] = await Promise.all([
                this.api.get_dashboard_data(this.currentPeriod),
                this.api.get_heatmap(this.currentPeriod)
            ]);
            if (this._isStale('dashboard', req)) return;

            const focus = data.focus || {};
            const rhythm = data.rhythm || {};

            document.getElementById('kpi-active').textContent = this.formatDuration(data.total_active);
            document.getElementById('kpi-active-delta').innerHTML =
                this.currentPeriod === 'all'
                    ? `<span class="text-slate-500">Inactif : ${this.formatDuration(data.total_idle)}</span>`
                    : this.deltaHtml(data.active_pct_change, this.prevLabel());

            document.getElementById('kpi-daily-avg').textContent = this.formatDuration(data.daily_average);
            document.getElementById('kpi-daily-avg-sub').textContent =
                `${data.days_count} jour${data.days_count > 1 ? 's' : ''} d'activité · ${data.apps_count} app${data.apps_count > 1 ? 's' : ''}`;

            document.getElementById('kpi-deep-work').textContent = focus.deep_work_formatted || '0m';
            document.getElementById('kpi-deep-work-sub').textContent =
                data.total_active > 0 ? `${focus.deep_work_pct}% du temps en sessions de 25 min ou plus` : '-';

            const top = data.top_apps && data.top_apps[0];
            document.getElementById('kpi-top-app').textContent = top ? top.app_name : '-';
            document.getElementById('kpi-top-app-sub').textContent = top ? `${this.formatDuration(top.total_duration)} · ${top.percentage}% du temps` : '-';

            document.getElementById('mini-sessions').textContent = focus.sessions_count ?? '-';
            document.getElementById('mini-avg-session').textContent = focus.avg_session_formatted || '-';
            const longest = focus.longest_session;
            const longestEl = document.getElementById('mini-longest');
            longestEl.textContent = longest ? `${longest.formatted} · ${longest.app_name}` : '-';
            longestEl.title = longest ? `${longest.app_name} — ${longest.date} ${longest.start_label} → ${longest.end_label}` : '';
            document.getElementById('mini-switches').textContent = data.total_active > 0 ? focus.switches_per_hour : '-';
            document.getElementById('mini-rhythm').textContent =
                rhythm.days ? `${rhythm.avg_start} → ${rhythm.avg_end}` : '-';
            document.getElementById('mini-rhythm-label').textContent =
                this.currentPeriod === 'today' ? 'Début → fin' : 'Début → fin (moy.)';

            const peakEl = document.getElementById('dash-peak-hour');
            peakEl.textContent = data.peak_hour !== null && data.peak_hour !== undefined
                ? `Pic : ${data.peak_hour}h - ${data.peak_hour + 1}h` : '';

            // Top apps
            const topAppsContainer = document.getElementById('top-apps-list');
            if (data.top_apps && data.top_apps.length > 0) {
                topAppsContainer.innerHTML = data.top_apps
                    .map((a, i) => this.appRowHtml(a, i, a.total_duration, a.percentage)).join('');
                this.bindAppRows(topAppsContainer);
            } else {
                topAppsContainer.innerHTML = '<p class="text-sm text-slate-500 text-center py-6">Aucune activité enregistrée</p>';
            }

            window.charts.renderTimeline('timelineChart', data.timeline, data.peak_hour);
            window.charts.renderHeatmap('heatmap-container', heatmapData);

            const catPreview = document.getElementById('dash-categories-preview');
            if (data.top_categories && data.top_categories.length > 0) {
                catPreview.innerHTML = data.top_categories.map(cat => {
                    const color = window.charts.getCategoryColor(cat.category);
                    return `
                        <div class="space-y-1">
                            <div class="flex justify-between text-xs">
                                <span class="text-slate-300 font-medium">${esc(cat.category)}</span>
                                <span class="text-slate-400">${cat.percentage}% (${this.formatDuration(cat.duration)})</span>
                            </div>
                            <div class="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                                <div class="h-1.5 rounded-full" style="width:${cat.percentage}%;background-color:${color};"></div>
                            </div>
                        </div>`;
                }).join('');
            } else {
                catPreview.innerHTML = '<p class="text-xs text-slate-500 text-center py-4">Pas de données de catégorie</p>';
            }

            lucide.createIcons();
            this.markUpdated();
        } catch (e) {
            console.error("Dashboard error:", e);
            if (!silent) this.toast("Impossible de charger le dashboard.", 'error');
        } finally {
            if (!silent) this.showLoader(false);
        }
    }

    // ------------------------------------------------------------------ TIMELINE
    shiftTimelineDay(delta) {
        const base = this.timelineDate ? new Date(this.timelineDate + 'T12:00:00') : new Date();
        base.setDate(base.getDate() + delta);
        const str = localDateStr(base);
        this.setTimelineDay(str > localDateStr() ? null : str);
    }

    setTimelineDay(dateStr) {
        this.timelineDate = (!dateStr || dateStr === localDateStr()) ? null : dateStr;
        this.loadTimeline();
    }

    async loadTimeline(silent = false) {
        const req = this._newRequest('timeline');
        if (!silent) this.showLoader(true);
        try {
            const data = await this.api.get_day_timeline(this.timelineDate);
            if (this._isStale('timeline', req)) return;

            const dateInput = document.getElementById('timeline-date');
            dateInput.value = data.date;
            dateInput.max = localDateStr();
            document.getElementById('timeline-next').disabled = data.is_today;
            const d = new Date(data.date + 'T12:00:00');
            document.getElementById('timeline-date-label').textContent =
                d.toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });

            const focus = data.focus || {};
            document.getElementById('tl-active').textContent = data.total_active_formatted;
            document.getElementById('tl-idle').textContent =
                `${data.total_idle_formatted}${focus.breaks_count ? ` · ${focus.breaks_count} pause${focus.breaks_count > 1 ? 's' : ''}` : ''}`;
            document.getElementById('tl-span').textContent =
                data.first_activity !== '-' ? `${data.first_activity} → ${data.last_activity}` : '-';
            document.getElementById('tl-sessions').textContent =
                focus.sessions_count ? `${focus.sessions_count} (${focus.avg_session_formatted})` : '-';
            document.getElementById('tl-deep').textContent =
                data.total_active > 0 ? `${focus.deep_work_formatted} (${focus.deep_work_pct}%)` : '-';

            this.renderDayStrip(data);

            const tbody = document.getElementById('tl-sessions-table');
            if (data.sessions.length > 0) {
                tbody.innerHTML = data.sessions.slice().reverse().map(s => `
                    <tr class="border-b border-slate-700/40 hover:bg-slate-800/40 cursor-pointer" data-app="${esc(s.app_name)}">
                        <td class="px-4 py-2 text-slate-400 whitespace-nowrap font-mono text-xs">${s.start_label} → ${s.end_label}</td>
                        <td class="px-4 py-2">
                            <div class="flex items-center gap-2">
                                <span class="w-2 h-2 rounded-full shrink-0" style="background-color:${window.charts.getCategoryColor(s.category)}"></span>
                                <span class="text-white font-medium truncate max-w-[160px]">${esc(s.app_name)}</span>
                            </div>
                        </td>
                        <td class="px-4 py-2 text-slate-400 text-xs"><span class="block truncate max-w-[320px]" title="${esc(s.title)}">${esc(s.title) || '-'}</span></td>
                        <td class="px-4 py-2 text-right font-semibold text-white whitespace-nowrap">${s.formatted}</td>
                    </tr>`).join('');
                this.bindAppRows(tbody);
            } else {
                tbody.innerHTML = '<tr><td colspan="4" class="text-center py-8 text-slate-500">Aucune session ce jour-là</td></tr>';
            }

            const topApps = document.getElementById('tl-top-apps');
            if (data.top_apps.length > 0) {
                topApps.innerHTML = data.top_apps.map((a, i) => this.appRowHtml(a, i, a.duration, a.percentage)).join('');
                this.bindAppRows(topApps);
            } else {
                topApps.innerHTML = '<p class="text-sm text-slate-500 text-center py-6">Aucune activité</p>';
            }

            lucide.createIcons();
            this.markUpdated();
        } catch (e) {
            console.error("Timeline error:", e);
            if (!silent) this.toast("Impossible de charger la chronologie.", 'error');
        } finally {
            if (!silent) this.showLoader(false);
        }
    }

    renderDayStrip(data) {
        const strip = document.getElementById('day-strip');
        const ticks = document.getElementById('day-strip-ticks');
        const tooltip = document.getElementById('day-strip-tooltip');
        const wrapper = document.getElementById('day-strip-wrapper');
        const DAY = 24 * 60;

        strip.innerHTML = data.blocks.map((b, i) => {
            const left = (Math.max(0, b.start_min) / DAY) * 100;
            const width = Math.max(((b.end_min - b.start_min) / DAY) * 100, 0.08);
            const style = b.kind === 'idle'
                ? `left:${left}%;width:${width}%;`
                : `left:${left}%;width:${width}%;background-color:${window.charts.getCategoryColor(b.category)};`;
            return `<div class="strip-block ${b.kind === 'idle' ? 'idle' : ''}" data-i="${i}" style="${style}"></div>`;
        }).join('');

        if (data.is_today) {
            const now = new Date();
            const pos = ((now.getHours() * 60 + now.getMinutes()) / DAY) * 100;
            strip.insertAdjacentHTML('beforeend', `<div class="strip-now" style="left:${pos}%" title="Maintenant"></div>`);
        }

        let tickHtml = '';
        for (let h = 0; h <= 24; h += 2) {
            const align = h === 0 ? 'translateX(0)' : (h === 24 ? 'translateX(-100%)' : 'translateX(-50%)');
            tickHtml += `<span class="absolute" style="left:${(h / 24) * 100}%;transform:${align}">${h}h</span>`;
        }
        ticks.innerHTML = tickHtml;

        strip.onmousemove = (e) => {
            const target = e.target.closest('.strip-block');
            if (!target) { tooltip.classList.add('hidden'); return; }
            const b = data.blocks[+target.dataset.i];
            tooltip.innerHTML = b.kind === 'idle'
                ? `<p class="font-semibold">Inactif</p><p class="text-slate-400">${b.start_label} → ${b.end_label} · ${b.formatted}</p>`
                : `<p class="font-semibold text-white">${esc(b.app_name)}</p>
                   <p class="text-slate-400">${esc(b.category)}</p>
                   <p class="text-slate-300 mt-1">${b.start_label} → ${b.end_label} · <strong>${b.formatted}</strong></p>`;
            tooltip.classList.remove('hidden');
            const rect = wrapper.getBoundingClientRect();
            let x = e.clientX - rect.left + 12;
            if (x + tooltip.offsetWidth > rect.width) x = e.clientX - rect.left - tooltip.offsetWidth - 12;
            tooltip.style.left = `${Math.max(0, x)}px`;
            tooltip.style.top = `${e.clientY - rect.top + 14}px`;
        };
        strip.onmouseleave = () => tooltip.classList.add('hidden');
        strip.onclick = (e) => {
            const target = e.target.closest('.strip-block');
            if (!target) return;
            const b = data.blocks[+target.dataset.i];
            if (b.kind !== 'idle') this.openAppModal(b.app_name, 'today');
        };

        const legend = document.getElementById('day-strip-legend');
        if (data.categories.length > 0) {
            legend.innerHTML = data.categories.map(c => `
                <span class="inline-flex items-center gap-1.5 text-slate-300">
                    <span class="w-2.5 h-2.5 rounded-sm" style="background-color:${window.charts.getCategoryColor(c.category)}"></span>
                    ${esc(c.category)} <span class="text-slate-500">${c.formatted}</span>
                </span>`).join('') +
                `<span class="inline-flex items-center gap-1.5 text-slate-400">
                    <span class="w-2.5 h-2.5 rounded-sm strip-block idle" style="position:static;display:inline-block"></span> Inactif
                </span>`;
        } else {
            legend.innerHTML = '<span class="text-slate-500">Aucune activité enregistrée ce jour-là</span>';
        }
    }

    // ------------------------------------------------------------------ ANALYTICS
    async loadAnalytics(silent = false) {
        const req = this._newRequest('analytics');
        if (!silent) this.showLoader(true);
        try {
            const data = await this.api.get_advanced_analytics(this.currentPeriod);
            if (this._isStale('analytics', req)) return;
            const focus = data.focus || {};
            const rhythm = data.rhythm || {};

            // KPIs
            document.getElementById('adv-total').textContent = data.total_active_formatted;
            document.getElementById('adv-total-sub').innerHTML = this.currentPeriod === 'all'
                ? `<span class="text-slate-400">${data.active_days_count} jours · ${data.daily_average_formatted}/j</span>`
                : this.deltaHtml(data.active_pct_change, `(préc. ${data.prev_total_active_formatted})`);

            document.getElementById('adv-peak-hour').textContent = data.peak_hour_label || '-';
            document.getElementById('adv-peak-hour-sub').textContent = data.peak_hour_duration > 0 ? `${data.peak_hour_formatted} cumulés` : 'Aucune donnée';

            if (data.peak_day) {
                const d = new Date(data.peak_day.date + 'T12:00:00');
                document.getElementById('adv-record-day').textContent = data.peak_day.formatted;
                document.getElementById('adv-record-day-sub').textContent =
                    `${d.toLocaleDateString('fr-FR', { weekday: 'short', day: 'numeric', month: 'short' })} · ${data.peak_day.top_app}`;
            } else {
                document.getElementById('adv-record-day').textContent = '-';
                document.getElementById('adv-record-day-sub').textContent = 'Pas de record';
            }

            const scoreEl = document.getElementById('adv-productivity-score');
            scoreEl.textContent = data.total_active > 0 ? `${data.productivity_score}%` : '-';
            scoreEl.className = 'text-2xl font-bold ' + (data.total_active === 0 ? 'text-white'
                : data.productivity_score >= 65 ? 'text-emerald-400'
                : data.productivity_score >= 40 ? 'text-amber-400' : 'text-rose-400');
            document.getElementById('adv-productivity-sub').textContent =
                `Productif : ${data.productive_time_formatted} · Loisirs : ${data.entertainment_time_formatted}`;

            const focusStatusEl = document.getElementById('adv-focus-status');
            focusStatusEl.textContent = focus.focus_label || '-';
            focusStatusEl.className = 'text-base font-bold truncate ' + ({
                excellent: 'text-emerald-400', good: 'text-blue-400', dispersed: 'text-amber-400'
            }[focus.focus_status] || 'text-white');
            document.getElementById('adv-focus-sub').textContent =
                data.total_active > 0 ? `${focus.switches_per_hour} changements d'app/h · série de ${data.streak} j` : '-';

            // Sessions & rhythm
            window.charts.renderSessionBuckets('sessionBucketsChart', focus.session_buckets);
            document.getElementById('adv-sessions').textContent = focus.sessions_count ?? '-';
            document.getElementById('adv-avg-session').textContent = focus.avg_session_formatted || '-';
            document.getElementById('adv-deep-work').textContent =
                data.total_active > 0 ? `${focus.deep_work_formatted} (${focus.deep_work_pct}%)` : '-';
            document.getElementById('adv-breaks').textContent =
                focus.breaks_count ? `${focus.breaks_count} (${focus.avg_break_formatted})` : '0';
            document.getElementById('adv-avg-start').textContent = rhythm.avg_start || '-';
            document.getElementById('adv-avg-end').textContent = rhythm.avg_end || '-';
            document.getElementById('adv-avg-span').textContent = rhythm.avg_span_formatted || '-';
            document.getElementById('adv-fullscreen').textContent = data.total_fullscreen_formatted || '-';

            const lb = focus.longest_block;
            const lbDate = lb ? new Date(lb.date + 'T12:00:00').toLocaleDateString('fr-FR', { weekday: 'short', day: 'numeric', month: 'short' }) : '';
            document.getElementById('adv-longest-block').innerHTML = lb
                ? `Plus longue période devant l'écran : <strong class="text-white">${lb.formatted}</strong> (${lbDate}, ${lb.start_label} → ${lb.end_label})`
                : '';

            const topSessions = document.getElementById('adv-top-sessions');
            if (focus.top_sessions && focus.top_sessions.length > 0) {
                topSessions.innerHTML = focus.top_sessions.map(s => {
                    const d = new Date(s.date + 'T12:00:00');
                    return `
                    <div class="app-row !py-1.5" data-app="${esc(s.app_name)}">
                        <div class="flex items-center gap-2 min-w-0">
                            <span class="w-2 h-2 rounded-full shrink-0" style="background-color:${window.charts.getCategoryColor(s.category)}"></span>
                            <span class="text-sm text-white font-medium shrink-0">${esc(s.app_name)}</span>
                            <span class="text-xs text-slate-500 truncate hidden md:inline" title="${esc(s.title)}">${esc(s.title)}</span>
                        </div>
                        <div class="text-right shrink-0 pl-3">
                            <span class="text-sm font-semibold text-white">${s.formatted}</span>
                            <span class="text-xs text-slate-500 ml-2">${d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })} ${s.start_label}</span>
                        </div>
                    </div>`;
                }).join('');
                this.bindAppRows(topSessions);
            } else {
                topSessions.innerHTML = '<p class="text-sm text-slate-500">Aucune session</p>';
            }

            // Hours
            document.getElementById('badge-dominant-quadrant').textContent =
                data.quadrants.dominant ? `Dominant : ${data.quadrants.dominant_label}` : '-';
            window.charts.renderPeakHoursChart('peakHoursChart', data.hourly_distribution, data.peak_hour);
            const q = data.quadrants.percentages;
            document.getElementById('quadrants-breakdown').innerHTML = [
                ['Nuit (00-06h)', q.nuit], ['Matin (06-12h)', q.matin],
                ['Aprem (12-18h)', q.apres_midi], ['Soir (18-24h)', q.soiree]
            ].map(([label, pct]) => `
                <div class="p-2 rounded bg-slate-800/80 border border-slate-700/50">
                    <span class="text-slate-400 block text-[10px] uppercase">${label}</span>
                    <span class="font-bold text-white text-xs">${pct}%</span>
                </div>`).join('');

            // Weekdays
            document.getElementById('badge-peak-day').textContent =
                data.peak_weekday !== '-' ? `Pic : ${data.peak_weekday} (${data.max_avg_day_formatted})` : '-';
            window.charts.renderPeakDaysChart('peakDaysChart', data.weekdays_distribution, data.peak_weekday);
            const sp = data.weekday_split;
            document.getElementById('weekday-split-summary').innerHTML = `
                <div class="flex items-center space-x-2">
                    <span class="w-2.5 h-2.5 rounded-full bg-primary inline-block"></span>
                    <span>Semaine (lun-ven) : <strong class="text-white">${sp.weekday_pct}%</strong></span>
                </div>
                <div class="flex items-center space-x-2">
                    <span class="w-2.5 h-2.5 rounded-full bg-slate-500 inline-block"></span>
                    <span>Week-end (sam-dim) : <strong class="text-white">${sp.weekend_pct}%</strong></span>
                </div>`;

            this.loadEvolution(silent);

            // Categories
            window.charts.renderCategoryDoughnut('categoryDoughnutChart', data.categories);
            const catListContainer = document.getElementById('adv-categories-list');
            if (data.categories && data.categories.length > 0) {
                catListContainer.innerHTML = data.categories.map(c => {
                    const color = window.charts.getCategoryColor(c.category);
                    const topAppsStr = c.apps.map(a => `${esc(a.app_name)} (${a.formatted})`).join(', ');
                    return `
                        <div class="p-3 bg-slate-800/60 rounded-lg border border-slate-700/50">
                            <div class="flex items-center justify-between mb-1.5">
                                <div class="flex items-center space-x-2">
                                    <span class="w-3 h-3 rounded-full" style="background-color:${color};"></span>
                                    <span class="text-sm font-semibold text-white">${esc(c.category)}</span>
                                </div>
                                <div class="text-right">
                                    <span class="text-sm font-bold text-white">${c.formatted}</span>
                                    <span class="text-xs text-slate-400 ml-1.5">(${c.percentage}%)</span>
                                </div>
                            </div>
                            <div class="w-full bg-slate-900 rounded-full h-1.5 mb-2 overflow-hidden">
                                <div class="h-1.5 rounded-full" style="width:${c.percentage}%;background-color:${color};"></div>
                            </div>
                            <p class="text-xs text-slate-400 truncate"><span class="text-slate-500">Apps :</span> ${topAppsStr || 'Aucune'}</p>
                        </div>`;
                }).join('');
            } else {
                catListContainer.innerHTML = '<p class="text-sm text-slate-500 text-center py-8">Aucune catégorie à afficher</p>';
            }

            // Trends
            document.getElementById('adv-trends-sub').textContent = this.currentPeriod === 'all'
                ? "Pas de période de comparaison pour tout l'historique"
                : `Comparaison ${this.prevLabel()}`;
            const trendsTbody = document.getElementById('adv-apps-trends-table');
            if (data.top_apps_trends && data.top_apps_trends.length > 0) {
                trendsTbody.innerHTML = data.top_apps_trends.slice(0, 15).map(a => {
                    let trendBadge;
                    if (a.trend === 'up') {
                        trendBadge = `<span class="text-xs font-semibold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">▲ +${a.pct_change}% (${a.formatted_diff})</span>`;
                    } else if (a.trend === 'down') {
                        trendBadge = `<span class="text-xs font-semibold text-rose-400 bg-rose-500/10 px-2 py-0.5 rounded border border-rose-500/20">▼ ${a.pct_change}% (${a.formatted_diff})</span>`;
                    } else if (a.trend === 'new') {
                        trendBadge = `<span class="text-xs font-semibold text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20">Nouveau</span>`;
                    } else {
                        trendBadge = `<span class="text-xs font-medium text-slate-400 bg-slate-700/50 px-2 py-0.5 rounded">≈ Stable</span>`;
                    }
                    return `
                        <tr class="border-b border-slate-700/40 hover:bg-slate-800/40 cursor-pointer" data-app="${esc(a.app_name)}">
                            <td class="px-5 py-3 font-medium text-white">${esc(a.app_name)}</td>
                            <td class="px-5 py-3">${this.categoryBadge(a.category, 'text-xs')}</td>
                            <td class="px-5 py-3 font-semibold text-white">${a.formatted_current}</td>
                            <td class="px-5 py-3 text-slate-400">${a.prev_duration > 0 ? this.formatDuration(a.prev_duration) : '-'}</td>
                            <td class="px-5 py-3">${trendBadge}</td>
                            <td class="px-5 py-3">
                                <div class="flex items-center space-x-2">
                                    <span class="text-xs text-slate-300 w-10">${a.percentage_of_total}%</span>
                                    <div class="w-20 bg-slate-800 rounded-full h-1.5 overflow-hidden">
                                        <div class="h-1.5 rounded-full bg-primary" style="width:${a.percentage_of_total}%;"></div>
                                    </div>
                                </div>
                            </td>
                        </tr>`;
                }).join('');
                this.bindAppRows(trendsTbody);
            } else {
                trendsTbody.innerHTML = '<tr><td colspan="6" class="text-center py-6 text-slate-500">Aucune donnée disponible</td></tr>';
            }

            lucide.createIcons();
            this.markUpdated();
        } catch (e) {
            console.error("Analytics error:", e);
            if (!silent) this.toast("Impossible de charger les statistiques.", 'error');
        } finally {
            if (!silent) this.showLoader(false);
        }
    }

    // ------------------------------------------------------------------ EVOLUTION
    setEvolutionGranularity(g) {
        this.evoGranularity = g;
        document.querySelectorAll('#evo-granularity .seg-btn').forEach(b => b.classList.toggle('active', b.dataset.g === g));
        this.loadEvolution();
    }

    async loadEvolution(silent = false) {
        const req = this._newRequest('evolution');
        try {
            const evo = await this.api.get_evolution(this.currentPeriod, this.evoGranularity || 'auto');
            if (this._isStale('evolution', req)) return;

            const unit = { day: 'jour', week: 'semaine', month: 'mois' }[evo.granularity];
            const hasData = evo.buckets.some(b => b.total > 0);
            document.getElementById('evolutionChart').parentElement.classList.toggle('hidden', !hasData);
            document.getElementById('evo-empty').classList.toggle('hidden', hasData);
            document.getElementById('evo-sub').innerHTML = hasData
                ? `Temps actif par ${unit} · moyenne <strong class="text-slate-200">${evo.average_formatted}</strong> par ${unit} (hors ${unit === 'semaine' ? 'semaines' : unit === 'jour' ? 'jours' : 'mois'} sans activité)` +
                  (evo.best ? ` · record : <strong class="text-slate-200">${esc(evo.best.label)}</strong> (${evo.best.formatted})` : '')
                : 'Temps actif par période, découpé par catégorie';
            if (hasData) window.charts.renderEvolution('evolutionChart', evo);

            const tbody = document.getElementById('evo-table');
            const rows = evo.buckets.slice().reverse();
            tbody.innerHTML = rows.map(b => {
                let delta = '<span class="text-slate-500">-</span>';
                if (b.pct_change !== null && b.pct_change !== undefined) {
                    const cls = Math.abs(b.pct_change) < 1 ? 'text-slate-400' : (b.pct_change > 0 ? 'delta-up' : 'delta-down');
                    delta = `<span class="${cls} font-semibold">${b.pct_change > 0 ? '▲ +' : (b.pct_change < 0 ? '▼ ' : '≈ ')}${b.pct_change}%</span>`;
                }
                const prod = b.productivity_score === null ? '-' : `${b.productivity_score}%`;
                return `
                    <tr class="border-b border-slate-700/40 hover:bg-slate-800/40 cursor-pointer ${b.total ? '' : 'opacity-50'}" data-first="${b.first_day}" data-last="${b.last_day}">
                        <td class="px-4 py-2 text-white font-medium whitespace-nowrap">${esc(b.label)}${b.is_current ? ' <span class="text-[10px] text-primary">(en cours)</span>' : ''}</td>
                        <td class="px-4 py-2 font-semibold text-white">${b.total ? b.formatted : '-'}</td>
                        <td class="px-4 py-2">${delta}</td>
                        <td class="px-4 py-2 text-slate-400">${b.active_days}</td>
                        <td class="px-4 py-2 text-slate-300">${b.daily_average_formatted}</td>
                        <td class="px-4 py-2 text-slate-300">${b.top_app ? `${esc(b.top_app)} <span class="text-slate-500 text-xs">${b.top_app_formatted}</span>` : '-'}</td>
                        <td class="px-4 py-2 text-slate-300">${prod}</td>
                    </tr>`;
            }).join('') || '<tr><td colspan="7" class="text-center py-6 text-slate-500">Aucune donnée</td></tr>';
            tbody.querySelectorAll('tr[data-first]').forEach(tr => {
                tr.addEventListener('click', () => this.applyRange(tr.dataset.first, tr.dataset.last));
            });
        } catch (e) {
            console.error("Evolution error:", e);
        }
    }

    // Switch the period selector to a custom range
    applyRange(first, last) {
        const selector = document.getElementById('period-selector');
        selector.value = 'custom';
        document.getElementById('custom-start').value = first;
        document.getElementById('custom-end').value = last;
        const range = document.getElementById('custom-range');
        range.classList.remove('hidden');
        range.classList.add('flex');
        this.applyCustomRange();
        document.getElementById('view-analytics').scrollTop = 0;
    }

    // ------------------------------------------------------------------ APPLICATIONS
    onAppsSearch(value) {
        clearTimeout(this.searchDebounceTimer);
        this.searchDebounceTimer = setTimeout(() => {
            this.searchQuery = value;
            this.loadApplications(true);
        }, 200);
    }

    onCategoryFilterChange(value) {
        this.categoryFilter = value;
        this.loadApplications();
    }

    async ensureCategories() {
        if (this.availableCategories.length > 0) return;
        const catsData = await this.api.get_categories();
        this.availableCategories = catsData.categories || [];
        const filterSelect = document.getElementById('apps-category-filter');
        if (filterSelect) {
            filterSelect.innerHTML = '<option value="">Toutes les catégories</option>' +
                this.availableCategories.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
            filterSelect.value = this.categoryFilter;
        }
    }

    async loadApplications(silent = false) {
        const req = this._newRequest('applications');
        if (!silent) this.showLoader(true);
        try {
            await this.ensureCategories();
            const apps = await this.api.get_all_apps(this.currentPeriod, this.searchQuery, this.categoryFilter);
            if (this._isStale('applications', req)) return;

            const tbody = document.getElementById('all-apps-table');
            const badge = document.getElementById('apps-count-badge');
            if (badge) badge.textContent = `${apps.length} application${apps.length > 1 ? 's' : ''}`;

            if (apps.length === 0) {
                tbody.innerHTML = '<tr><td colspan="8" class="text-center py-8 text-slate-500">Aucune application trouvée pour ces critères</td></tr>';
                return;
            }

            tbody.innerHTML = apps.map(a => {
                const catOptions = this.availableCategories.map(c =>
                    `<option value="${esc(c)}" ${c.toLowerCase() === a.category.toLowerCase() ? 'selected' : ''}>${esc(c)}</option>`
                ).join('');
                return `
                    <tr class="border-b border-slate-700/50 hover:bg-slate-800/40 cursor-pointer" data-app="${esc(a.app_name)}">
                        <td class="px-5 py-3.5 font-medium text-white">
                            <div class="flex items-center">
                                <span class="w-2 h-2 rounded-full mr-3 shrink-0" style="background-color:${window.charts.getCategoryColor(a.category)}"></span>
                                <span class="truncate max-w-[200px]" title="${esc(a.app_name)}">${esc(a.app_name)}</span>
                            </div>
                        </td>
                        <td class="px-5 py-3.5">
                            <select class="cat-badge-select" data-cat-app="${esc(a.app_name)}">${catOptions}</select>
                        </td>
                        <td class="px-5 py-3.5 text-slate-300 text-xs">${a.sessions_count}</td>
                        <td class="px-5 py-3.5 text-slate-300 text-xs">${a.avg_session_formatted}</td>
                        <td class="px-5 py-3.5 text-slate-300 text-xs">${a.longest_session_formatted}</td>
                        <td class="px-5 py-3.5 text-slate-400 text-xs">${a.last_used_label}</td>
                        <td class="px-5 py-3.5 font-semibold text-slate-100 whitespace-nowrap">${this.formatDuration(a.total_duration)}</td>
                        <td class="px-5 py-3.5">
                            <div class="flex items-center space-x-2">
                                <span class="text-xs text-slate-400 w-10">${a.percentage}%</span>
                                <div class="w-24 bg-slate-700 rounded-full h-1.5 overflow-hidden">
                                    <div class="bg-primary h-1.5 rounded-full" style="width:${a.percentage}%"></div>
                                </div>
                            </div>
                        </td>
                    </tr>`;
            }).join('');

            tbody.querySelectorAll('select[data-cat-app]').forEach(sel => {
                sel.addEventListener('click', e => e.stopPropagation());
                sel.addEventListener('change', e => this.changeAppCategory(sel.dataset.catApp, e.target.value));
            });
            this.bindAppRows(tbody);
            this.markUpdated();
        } catch (e) {
            console.error("Applications error:", e);
            if (!silent) this.toast("Impossible de charger les applications.", 'error');
        } finally {
            if (!silent) this.showLoader(false);
        }
    }

    async changeAppCategory(appName, newCategory) {
        if (!this.api) return;
        try {
            await this.api.set_app_category(appName, newCategory);
            this.toast(`${appName} → ${newCategory}`);
            this.loadApplications(true);
        } catch (e) {
            console.error("Failed to update category:", e);
            this.toast("Impossible de modifier la catégorie.", 'error');
        }
    }

    // ------------------------------------------------------------------ APP DETAILS MODAL
    async openAppModal(appName, period = null) {
        if (!this.api || !appName) return;
        const usedPeriod = period || (this.currentView === 'timeline' ? 'today' : this.currentPeriod);
        this.modalApp = appName;
        const req = this._newRequest('modal');
        document.getElementById('app-modal').classList.remove('hidden');
        document.getElementById('modal-app-name').textContent = appName;
        document.getElementById('modal-app-sub').textContent = 'Chargement...';
        try {
            const d = await this.api.get_app_details(appName, usedPeriod);
            if (this._isStale('modal', req) || this.modalApp !== appName) return;
            window.charts.setAnimated(true);

            document.getElementById('modal-app-sub').innerHTML =
                `${this.categoryBadge(d.category, 'text-xs')} <span class="ml-2">${esc(this.periodLabel(usedPeriod))} · ${d.percentage_of_total}% du temps actif</span>`;
            document.getElementById('modal-total').textContent = d.formatted_total;
            document.getElementById('modal-sessions').textContent = `${d.sessions_count} (${d.avg_session_formatted})`;
            const l = d.longest_session;
            document.getElementById('modal-longest').textContent = l ? `${l.formatted}` : '-';
            document.getElementById('modal-longest').title = l ? `${l.date} ${l.start_label} → ${l.end_label}` : '';
            document.getElementById('modal-days').textContent = d.days_used ? `${d.days_used} (${d.daily_average_formatted}/j)` : '-';

            const daily = d.daily;
            window.charts.renderMinutesBars('appDailyChart',
                daily.map(p => { const s = p.date_str.split('-'); return `${s[2]}/${s[1]}`; }),
                daily.map(p => p.duration), '#3b82f6', daily.map(p => p.date_str));
            window.charts.renderMinutesBars('appHourlyChart',
                d.hourly.map(h => `${h.hour}h`), d.hourly.map(h => h.duration), '#f59e0b');

            const titles = document.getElementById('modal-titles');
            titles.innerHTML = d.top_titles.length > 0 ? d.top_titles.map(t => `
                <div>
                    <div class="flex justify-between gap-4 text-xs mb-1">
                        <span class="text-slate-200 truncate" title="${esc(t.title)}">${esc(t.title)}</span>
                        <span class="text-slate-400 shrink-0">${t.formatted} · ${t.percentage}%</span>
                    </div>
                    <div class="w-full bg-slate-800 rounded-full h-1 overflow-hidden">
                        <div class="h-1 rounded-full bg-violet-500" style="width:${t.percentage}%"></div>
                    </div>
                </div>`).join('') : '<p class="text-sm text-slate-500">Aucune fenêtre</p>';

            document.getElementById('modal-seen').textContent =
                `Première utilisation enregistrée : ${d.first_seen} · Dernière : ${d.last_seen}` +
                (d.fullscreen_duration > 0 ? ` · Plein écran : ${d.fullscreen_formatted}` : '');
            lucide.createIcons();
        } catch (e) {
            console.error("App details error:", e);
            document.getElementById('modal-app-sub').textContent = 'Erreur de chargement';
        }
    }

    closeAppModal() {
        this.modalApp = null;
        document.getElementById('app-modal').classList.add('hidden');
    }

    // ------------------------------------------------------------------ SETTINGS
    async loadSettings() {
        this.showLoader(true);
        try {
            const [settings, startup] = await Promise.all([
                this.api.get_settings(),
                this.api.get_startup_status()
            ]);
            document.getElementById('setting-startup').checked = !!settings.startup;
            document.getElementById('setting-refresh-interval').value = settings.refresh_interval || 5;
            document.getElementById('setting-detect-idle').checked = settings.detect_idle !== false;
            document.getElementById('setting-idle-timeout').value = settings.idle_timeout;
            document.getElementById('setting-detect-fullscreen').checked = settings.detect_fullscreen !== false;
            document.getElementById('setting-retention').value = settings.retention_days;
            document.getElementById('setting-categories').value = JSON.stringify(settings.categories, null, 4);
            this.renderStartupStatus(!!settings.startup, startup);
        } catch (e) {
            console.error(e);
        } finally {
            this.showLoader(false);
        }
    }

    renderStartupStatus(wanted, status) {
        const el = document.getElementById('startup-status');
        if (!el || !status) return;
        let msg = '';
        let cls = 'text-slate-400';
        if (!status.supported) {
            msg = '';
        } else if (wanted && !status.registered) {
            msg = "⚠ Pas encore enregistré dans Windows : cliquez sur « Enregistrer les modifications ».";
            cls = 'text-amber-400';
        } else if (wanted && status.disabled_by_windows) {
            msg = "⚠ Trackr est désactivé dans Paramètres Windows › Applications › Démarrage (ou le Gestionnaire des tâches). Enregistrez avec l'option activée pour le réactiver.";
            cls = 'text-amber-400';
        } else if (wanted && !status.up_to_date) {
            msg = "⚠ L'entrée de démarrage pointe vers un autre emplacement. Enregistrez pour la mettre à jour.";
            cls = 'text-amber-400';
        } else if (wanted) {
            msg = "✓ Actif : Trackr se lancera en arrière-plan à la prochaine ouverture de session.";
            cls = 'text-emerald-400';
        } else if (status.registered) {
            msg = "⚠ Une entrée de démarrage existe encore : enregistrez pour la supprimer.";
            cls = 'text-amber-400';
        }
        el.textContent = msg;
        el.className = `text-xs mt-2 ${cls}`;
        el.classList.toggle('hidden', !msg);
    }

    async saveSettings() {
        if (!this.api) return;
        let catObj;
        try {
            catObj = JSON.parse(document.getElementById('setting-categories').value);
            if (!catObj || typeof catObj !== 'object' || Array.isArray(catObj)) throw new Error();
        } catch (err) {
            this.toast("Format JSON des catégories invalide.", 'error');
            return;
        }

        const newSettings = {
            startup: document.getElementById('setting-startup').checked,
            refresh_interval: parseInt(document.getElementById('setting-refresh-interval').value) || 5,
            detect_idle: document.getElementById('setting-detect-idle').checked,
            idle_timeout: parseInt(document.getElementById('setting-idle-timeout').value) || 300,
            detect_fullscreen: document.getElementById('setting-detect-fullscreen').checked,
            retention_days: parseInt(document.getElementById('setting-retention').value) || 365,
            categories: catObj
        };

        try {
            const res = await this.api.save_settings(newSettings);
            this.availableCategories = [];
            this.toast("Paramètres enregistrés.");
            this.loadSettings();
            if (res && res.startup) this.renderStartupStatus(newSettings.startup, res.startup);
        } catch (e) {
            console.error(e);
            this.toast("Erreur lors de l'enregistrement.", 'error');
        }
    }

    async exportData() {
        if (!this.api) return;
        try {
            const res = await this.api.export_csv();
            if (res && res.success) {
                this.toast("Données exportées vers : " + res.path);
            } else if (res && res.error && res.error !== 'Cancelled') {
                this.toast("Export impossible : " + res.error, 'error');
            }
        } catch (e) {
            console.error(e);
            this.toast("Erreur lors de l'export.", 'error');
        }
    }
}

window.app = new App();
