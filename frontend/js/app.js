class App {
    constructor() {
        this.currentView = 'dashboard';
        this.currentPeriod = 'week';
        this.isPyWebViewReady = false;
        this.searchQuery = '';
        this.categoryFilter = '';
        this.availableCategories = [];
        this.searchDebounceTimer = null;
        
        // Wait for pywebview to be ready
        window.addEventListener('pywebviewready', () => {
            this.isPyWebViewReady = true;
            this.init();
        });
        
        // For local testing in browser without pywebview
        setTimeout(() => {
            if (!this.isPyWebViewReady) {
                this.initLocal();
            }
        }, 800);
    }

    showLoader(show) {
        const loader = document.getElementById('loader');
        if (loader) loader.classList.toggle('hidden', !show);
    }

    navigate(viewId) {
        // Update nav UI
        document.querySelectorAll('nav a').forEach(el => {
            el.classList.remove('bg-primary/10', 'text-primary');
            el.classList.add('text-slate-400');
            const icon = el.querySelector('i, svg');
            if (icon) icon.classList.replace('text-primary', 'text-slate-400');
        });
        
        const activeNav = document.getElementById(`nav-${viewId}`);
        if (activeNav) {
            activeNav.classList.add('bg-primary/10', 'text-primary');
            activeNav.classList.remove('text-slate-400');
            const icon = activeNav.querySelector('i, svg');
            if (icon) icon.classList.replace('text-slate-400', 'text-primary');
        }

        // Show View
        document.querySelectorAll('.page-view').forEach(el => {
            el.classList.add('hidden');
        });
        const targetView = document.getElementById(`view-${viewId}`);
        if (targetView) targetView.classList.remove('hidden');
        
        // Update Title
        const titles = {
            'dashboard': 'Dashboard',
            'analytics': 'Statistiques Avancées',
            'applications': 'Applications',
            'settings': 'Paramètres'
        };
        document.getElementById('page-title').textContent = titles[viewId] || 'Trackr';
        
        this.currentView = viewId;
        this.refreshData();
    }

    changePeriod(period) {
        this.currentPeriod = period;
        this.refreshData();
    }

    refreshData() {
        if (!window.pywebview || !window.pywebview.api) return;
        
        if (this.currentView === 'dashboard') {
            this.loadDashboard();
        } else if (this.currentView === 'analytics') {
            this.loadAnalytics();
        } else if (this.currentView === 'applications') {
            this.loadApplications();
        } else if (this.currentView === 'settings') {
            this.loadSettings();
        }
    }

    formatDuration(seconds) {
        if (!seconds || seconds <= 0) return '0m';
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        if (h > 0) return `${h}h ${m > 0 ? (m < 10 ? '0' + m : m) + 'm' : ''}`;
        return `${m}m`;
    }

    // --- VIEW: DASHBOARD ---
    async loadDashboard() {
        this.showLoader(true);
        try {
            const data = await window.pywebview.api.get_dashboard_data(this.currentPeriod);
            
            // KPIs
            document.getElementById('kpi-active').textContent = this.formatDuration(data.total_active);
            document.getElementById('kpi-idle').textContent = this.formatDuration(data.total_idle);
            
            if (data.top_apps && data.top_apps.length > 0) {
                document.getElementById('kpi-top-app').textContent = data.top_apps[0].app_name;
            } else {
                document.getElementById('kpi-top-app').textContent = '-';
            }

            const peakHourEl = document.getElementById('kpi-peak-hour-dash');
            if (peakHourEl) {
                peakHourEl.textContent = data.peak_hour !== null && data.peak_hour !== undefined ? `${data.peak_hour}h - ${data.peak_hour + 1}h` : '-';
            }

            // Top Apps List
            const topAppsContainer = document.getElementById('top-apps-list');
            topAppsContainer.innerHTML = '';
            
            if (data.top_apps && data.top_apps.length > 0) {
                data.top_apps.forEach((app, index) => {
                    const percentage = data.total_active > 0 ? ((app.total_duration / data.total_active) * 100).toFixed(1) : 0;
                    const catColor = window.charts ? window.charts.getCategoryColor(app.category) : '#3b82f6';
                    const html = `
                        <div class="flex items-center justify-between mb-3 last:mb-0">
                            <div class="flex items-center space-x-3 overflow-hidden">
                                <div class="w-5 text-center text-slate-500 font-bold text-xs">${index + 1}</div>
                                <div class="truncate">
                                    <p class="text-sm font-medium text-white truncate">${app.app_name}</p>
                                    <span class="inline-block text-[10px] px-1.5 py-0.5 rounded font-medium mt-0.5" style="background-color: ${catColor}20; color: ${catColor}; border: 1px solid ${catColor}40;">
                                        ${app.category}
                                    </span>
                                </div>
                            </div>
                            <div class="text-right pl-4">
                                <p class="text-sm font-semibold text-white">${this.formatDuration(app.total_duration)}</p>
                                <p class="text-xs text-slate-400">${percentage}%</p>
                            </div>
                        </div>
                    `;
                    topAppsContainer.insertAdjacentHTML('beforeend', html);
                });
            } else {
                topAppsContainer.innerHTML = '<p class="text-sm text-slate-500 text-center py-6">Aucune activité enregistrée</p>';
            }

            // Timeline chart
            window.charts.renderTimeline('timelineChart', data.timeline, data.peak_hour);

            // Heatmap
            const heatmapData = await window.pywebview.api.get_heatmap(this.currentPeriod);
            window.charts.renderHeatmap('heatmap-container', heatmapData);

            // Dashboard Categories Preview
            const catPreview = document.getElementById('dash-categories-preview');
            if (catPreview) {
                catPreview.innerHTML = '';
                if (data.top_categories && data.top_categories.length > 0) {
                    data.top_categories.forEach(cat => {
                        const color = window.charts.getCategoryColor(cat.category);
                        const row = `
                            <div class="space-y-1">
                                <div class="flex justify-between text-xs">
                                    <span class="text-slate-300 font-medium">${cat.category}</span>
                                    <span class="text-slate-400">${cat.percentage}% (${this.formatDuration(cat.duration)})</span>
                                </div>
                                <div class="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                                    <div class="h-1.5 rounded-full" style="width: ${cat.percentage}%; background-color: ${color};"></div>
                                </div>
                            </div>
                        `;
                        catPreview.insertAdjacentHTML('beforeend', row);
                    });
                } else {
                    catPreview.innerHTML = '<p class="text-xs text-slate-500 text-center py-4">Pas de données de catégorie</p>';
                }
            }

            lucide.createIcons();
        } catch (e) {
            console.error("Dashboard error:", e);
        } finally {
            this.showLoader(false);
        }
    }

    // --- VIEW: STATISTIQUES AVANCÉES ---
    async loadAnalytics() {
        this.showLoader(true);
        try {
            const data = await window.pywebview.api.get_advanced_analytics(this.currentPeriod);

            // 1. Highlights KPIs
            // Peak Hour
            document.getElementById('adv-peak-hour').textContent = data.peak_hour_label || '-';
            document.getElementById('adv-peak-hour-sub').textContent = data.peak_hour_duration > 0 ? `${data.peak_hour_formatted} au total` : 'Aucune donnée';

            // Peak Day
            document.getElementById('adv-peak-day').textContent = data.peak_weekday || '-';
            document.getElementById('adv-peak-day-sub').textContent = data.max_avg_day_duration > 0 ? `Moyenne : ${data.max_avg_day_formatted}/j` : '-';

            // Record Day
            if (data.peak_day) {
                document.getElementById('adv-record-day').textContent = data.peak_day.formatted;
                document.getElementById('adv-record-day-sub').textContent = `${data.peak_day.date} (${data.peak_day.top_app})`;
            } else {
                document.getElementById('adv-record-day').textContent = '-';
                document.getElementById('adv-record-day-sub').textContent = 'Pas de record';
            }

            // Productivity Score
            const scoreEl = document.getElementById('adv-productivity-score');
            scoreEl.textContent = `${data.productivity_score}%`;
            if (data.productivity_score >= 65) {
                scoreEl.className = 'text-2xl font-bold text-emerald-400';
            } else if (data.productivity_score >= 40) {
                scoreEl.className = 'text-2xl font-bold text-amber-400';
            } else {
                scoreEl.className = 'text-2xl font-bold text-rose-400';
            }
            document.getElementById('adv-productivity-sub').textContent = `Utile : ${data.productive_time_formatted} | Loisir : ${data.entertainment_time_formatted}`;

            // Concentration & Focus
            const focusStatusEl = document.getElementById('adv-focus-status');
            focusStatusEl.textContent = data.focus_label || 'Normal';
            if (data.focus_status === 'excellent') {
                focusStatusEl.className = 'text-lg font-bold text-emerald-400 truncate';
            } else if (data.focus_status === 'good') {
                focusStatusEl.className = 'text-lg font-bold text-blue-400 truncate';
            } else {
                focusStatusEl.className = 'text-lg font-bold text-amber-400 truncate';
            }
            document.getElementById('adv-focus-sub').textContent = `${data.switches_per_hour} changements d'app/h (Série : ${data.streak} j)`;

            // 2. Peak Hours Chart & Quadrants
            document.getElementById('badge-dominant-quadrant').textContent = `Dominant : ${data.quadrants.dominant_label}`;
            window.charts.renderPeakHoursChart('peakHoursChart', data.hourly_distribution, data.peak_hour);

            const quadrantsContainer = document.getElementById('quadrants-breakdown');
            if (quadrantsContainer) {
                const q = data.quadrants;
                quadrantsContainer.innerHTML = `
                    <div class="p-2 rounded bg-slate-800/80 border border-slate-700/50">
                        <span class="text-slate-400 block text-[10px] uppercase">Nuit (00-06h)</span>
                        <span class="font-bold text-white text-xs">${q.percentages.nuit}%</span>
                    </div>
                    <div class="p-2 rounded bg-slate-800/80 border border-slate-700/50">
                        <span class="text-slate-400 block text-[10px] uppercase">Matin (06-12h)</span>
                        <span class="font-bold text-white text-xs">${q.percentages.matin}%</span>
                    </div>
                    <div class="p-2 rounded bg-slate-800/80 border border-slate-700/50">
                        <span class="text-slate-400 block text-[10px] uppercase">Aprem (12-18h)</span>
                        <span class="font-bold text-white text-xs">${q.percentages.apres_midi}%</span>
                    </div>
                    <div class="p-2 rounded bg-slate-800/80 border border-slate-700/50">
                        <span class="text-slate-400 block text-[10px] uppercase">Soir (18-24h)</span>
                        <span class="font-bold text-white text-xs">${q.percentages.soiree}%</span>
                    </div>
                `;
            }

            // 3. Peak Weekdays Chart
            window.charts.renderPeakDaysChart('peakDaysChart', data.weekdays_distribution, data.peak_weekday);
            const splitSummary = document.getElementById('weekday-split-summary');
            if (splitSummary) {
                const sp = data.weekday_split;
                splitSummary.innerHTML = `
                    <div class="flex items-center space-x-2">
                        <span class="w-2.5 h-2.5 rounded-full bg-primary inline-block"></span>
                        <span>Semaine (Lun-Ven) : <strong class="text-white">${sp.weekday_pct}%</strong></span>
                    </div>
                    <div class="flex items-center space-x-2">
                        <span class="w-2.5 h-2.5 rounded-full bg-slate-500 inline-block"></span>
                        <span>Week-end (Sam-Dim) : <strong class="text-white">${sp.weekend_pct}%</strong></span>
                    </div>
                `;
            }

            // 4. Time Series & Spikes Detection Chart
            const peakDateStr = data.peak_day ? data.peak_day.date : null;
            window.charts.renderPeaksTimeSeries('peaksTimeSeriesChart', data.time_series, peakDateStr);

            // 5. Category Doughnut & Detail Cards
            window.charts.renderCategoryDoughnut('categoryDoughnutChart', data.categories);
            const catListContainer = document.getElementById('adv-categories-list');
            if (catListContainer) {
                catListContainer.innerHTML = '';
                if (data.categories && data.categories.length > 0) {
                    data.categories.forEach(c => {
                        const color = window.charts.getCategoryColor(c.category);
                        const topAppsStr = c.apps.map(a => `${a.app_name} (${a.formatted})`).join(', ');
                        const catHtml = `
                            <div class="p-3 bg-slate-800/60 rounded-lg border border-slate-700/50 hover:border-slate-600 transition-colors">
                                <div class="flex items-center justify-between mb-1.5">
                                    <div class="flex items-center space-x-2">
                                        <span class="w-3 h-3 rounded-full" style="background-color: ${color};"></span>
                                        <span class="text-sm font-semibold text-white">${c.category}</span>
                                    </div>
                                    <div class="text-right">
                                        <span class="text-sm font-bold text-white">${c.formatted}</span>
                                        <span class="text-xs text-slate-400 ml-1.5">(${c.percentage}%)</span>
                                    </div>
                                </div>
                                <div class="w-full bg-slate-900 rounded-full h-1.5 mb-2 overflow-hidden">
                                    <div class="h-1.5 rounded-full" style="width: ${c.percentage}%; background-color: ${color};"></div>
                                </div>
                                <p class="text-xs text-slate-400 truncate">
                                    <span class="text-slate-500">Apps :</span> ${topAppsStr || 'Aucune'}
                                </p>
                            </div>
                        `;
                        catListContainer.insertAdjacentHTML('beforeend', catHtml);
                    });
                } else {
                    catListContainer.innerHTML = '<p class="text-sm text-slate-500 text-center py-8">Aucune catégorie à afficher</p>';
                }
            }

            // 6. Top Apps & Trends Table (N vs N-1)
            const trendsTbody = document.getElementById('adv-apps-trends-table');
            if (trendsTbody) {
                trendsTbody.innerHTML = '';
                if (data.top_apps_trends && data.top_apps_trends.length > 0) {
                    data.top_apps_trends.slice(0, 12).forEach(app => {
                        const catColor = window.charts.getCategoryColor(app.category);
                        let trendBadge = '';
                        if (app.trend === 'up') {
                            trendBadge = `<span class="inline-flex items-center text-xs font-semibold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">↗️ +${app.pct_change}%</span>`;
                        } else if (app.trend === 'down') {
                            trendBadge = `<span class="inline-flex items-center text-xs font-semibold text-rose-400 bg-rose-500/10 px-2 py-0.5 rounded border border-rose-500/20">↘️ ${app.pct_change}%</span>`;
                        } else if (app.trend === 'new') {
                            trendBadge = `<span class="inline-flex items-center text-xs font-semibold text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20">✨ Nouveau</span>`;
                        } else {
                            trendBadge = `<span class="inline-flex items-center text-xs font-medium text-slate-400 bg-slate-700/50 px-2 py-0.5 rounded">≈ Stable</span>`;
                        }

                        const prevText = app.prev_duration > 0 ? this.formatDuration(app.prev_duration) : '-';

                        const tr = document.createElement('tr');
                        tr.className = 'border-b border-slate-700/40 hover:bg-slate-800/40 transition-colors';
                        tr.innerHTML = `
                            <td class="px-5 py-3 font-medium text-white flex items-center">
                                <i data-lucide="monitor" class="w-4 h-4 mr-2.5 text-slate-400"></i> ${app.app_name}
                            </td>
                            <td class="px-5 py-3">
                                <span class="text-xs px-2 py-0.5 rounded font-medium" style="background-color: ${catColor}15; color: ${catColor}; border: 1px solid ${catColor}30;">
                                    ${app.category}
                                </span>
                            </td>
                            <td class="px-5 py-3 font-semibold text-white">${app.formatted_current}</td>
                            <td class="px-5 py-3 text-slate-400">${prevText}</td>
                            <td class="px-5 py-3">${trendBadge}</td>
                            <td class="px-5 py-3">
                                <div class="flex items-center space-x-2">
                                    <span class="text-xs text-slate-300 w-10">${app.percentage_of_total}%</span>
                                    <div class="w-20 bg-slate-800 rounded-full h-1.5 overflow-hidden">
                                        <div class="h-1.5 rounded-full bg-primary" style="width: ${app.percentage_of_total}%;"></div>
                                    </div>
                                </div>
                            </td>
                        `;
                        trendsTbody.appendChild(tr);
                    });
                } else {
                    trendsTbody.innerHTML = '<tr><td colspan="6" class="text-center py-6 text-slate-500">Aucune donnée disponible</td></tr>';
                }
            }

            lucide.createIcons();
        } catch (e) {
            console.error("Analytics error:", e);
        } finally {
            this.showLoader(false);
        }
    }

    // --- VIEW: APPLICATIONS ---
    onAppsSearch(value) {
        clearTimeout(this.searchDebounceTimer);
        this.searchDebounceTimer = setTimeout(() => {
            this.searchQuery = value;
            this.loadApplications();
        }, 200);
    }

    onCategoryFilterChange(value) {
        this.categoryFilter = value;
        this.loadApplications();
    }

    async loadApplications() {
        this.showLoader(true);
        try {
            // Load categories list if not cached
            if (this.availableCategories.length === 0) {
                const catsData = await window.pywebview.api.get_categories();
                this.availableCategories = catsData.categories || [];
                
                // Populate filter dropdown
                const filterSelect = document.getElementById('apps-category-filter');
                if (filterSelect) {
                    filterSelect.innerHTML = '<option value="">Toutes les catégories</option>';
                    this.availableCategories.forEach(cat => {
                        const opt = document.createElement('option');
                        opt.value = cat;
                        opt.textContent = cat;
                        filterSelect.appendChild(opt);
                    });
                }
            }

            const apps = await window.pywebview.api.get_all_apps(this.currentPeriod, this.searchQuery, this.categoryFilter);
            const tbody = document.getElementById('all-apps-table');
            tbody.innerHTML = '';
            
            const badge = document.getElementById('apps-count-badge');
            if (badge) badge.textContent = `${apps.length} application${apps.length > 1 ? 's' : ''}`;

            if (apps.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="5" class="text-center py-8 text-slate-500">
                            Aucune application trouvée pour ces critères
                        </td>
                    </tr>
                `;
                return;
            }

            apps.forEach(app => {
                const tr = document.createElement('tr');
                tr.className = 'border-b border-slate-700/50 hover:bg-slate-800/40 transition-colors';
                
                // Build category dropdown options for 1-click update
                let catOptions = '';
                this.availableCategories.forEach(c => {
                    const selected = c.toLowerCase() === app.category.toLowerCase() ? 'selected' : '';
                    catOptions += `<option value="${c}" ${selected}>${c}</option>`;
                });

                tr.innerHTML = `
                    <td class="px-6 py-4 font-medium text-white flex items-center">
                        <i data-lucide="monitor" class="w-4 h-4 mr-3 text-slate-400"></i>
                        <span class="truncate max-w-[200px]" title="${app.app_name}">${app.app_name}</span>
                    </td>
                    <td class="px-6 py-4">
                        <select onchange="app.changeAppCategory('${app.app_name.replace(/'/g, "\\'")}', this.value)" class="cat-badge-select">
                            ${catOptions}
                        </select>
                    </td>
                    <td class="px-6 py-4 text-slate-400 text-xs">${app.sessions_count || '-'}</td>
                    <td class="px-6 py-4 font-medium text-slate-200">${this.formatDuration(app.total_duration)}</td>
                    <td class="px-6 py-4">
                        <div class="flex items-center space-x-2">
                            <span class="text-xs text-slate-400 w-10">${app.percentage}%</span>
                            <div class="w-32 bg-slate-700 rounded-full h-1.5 overflow-hidden">
                                <div class="bg-primary h-1.5 rounded-full" style="width: ${app.percentage}%"></div>
                            </div>
                        </div>
                    </td>
                `;
                tbody.appendChild(tr);
            });
            lucide.createIcons();
        } catch (e) {
            console.error("Applications error:", e);
        } finally {
            this.showLoader(false);
        }
    }

    async changeAppCategory(appName, newCategory) {
        if (!window.pywebview || !window.pywebview.api) return;
        try {
            await window.pywebview.api.set_app_category(appName, newCategory);
            // Refresh applications without reloading category dropdown
            const apps = await window.pywebview.api.get_all_apps(this.currentPeriod, this.searchQuery, this.categoryFilter);
            this.loadApplications();
        } catch (e) {
            console.error("Failed to update category:", e);
        }
    }

    // --- VIEW: SETTINGS ---
    async loadSettings() {
        this.showLoader(true);
        try {
            const settings = await window.pywebview.api.get_settings();
            document.getElementById('setting-startup').checked = settings.startup;
            document.getElementById('setting-refresh-interval').value = settings.refresh_interval || 5;
            document.getElementById('setting-detect-idle').checked = settings.detect_idle !== false;
            document.getElementById('setting-idle-timeout').value = settings.idle_timeout;
            document.getElementById('setting-detect-fullscreen').checked = settings.detect_fullscreen !== false;
            document.getElementById('setting-retention').value = settings.retention_days;
            document.getElementById('setting-categories').value = JSON.stringify(settings.categories, null, 4);
        } catch (e) {
            console.error(e);
        } finally {
            this.showLoader(false);
        }
    }

    async saveSettings() {
        if (!window.pywebview) return;
        
        try {
            let catObj = {};
            try {
                catObj = JSON.parse(document.getElementById('setting-categories').value);
            } catch (err) {
                alert("Format JSON des catégories invalide.");
                return;
            }

            const newSettings = {
                startup: document.getElementById('setting-startup').checked,
                refresh_interval: parseInt(document.getElementById('setting-refresh-interval').value) || 5,
                detect_idle: document.getElementById('setting-detect-idle').checked,
                idle_timeout: parseInt(document.getElementById('setting-idle-timeout').value) || 300,
                detect_fullscreen: document.getElementById('setting-detect-fullscreen').checked,
                retention_days: parseInt(document.getElementById('setting-retention').value) || 30,
                categories: catObj
            };

            await window.pywebview.api.save_settings(newSettings);
            this.availableCategories = []; // Reset cached categories
            alert("Paramètres enregistrés avec succès.");
        } catch (e) {
            console.error(e);
            alert("Erreur lors de l'enregistrement.");
        }
    }

    async exportData() {
        if (!window.pywebview) return;
        try {
            const res = await window.pywebview.api.export_csv();
            if (res && res.success) {
                alert("Données exportées vers : " + res.path);
            }
        } catch(e) {
            console.error(e);
        }
    }

    init() {
        this.navigate('dashboard');
    }

    // Standalone mock for local browser preview
    initLocal() {
        console.warn("PyWebView non détecté, exécution en mode local simulé.");
        window.pywebview = {
            api: {
                get_dashboard_data: async () => ({
                    total_active: 28800,
                    total_idle: 3600,
                    top_apps: [
                        { app_name: "Code.exe", total_duration: 14400, category: "Développement" },
                        { app_name: "msedge.exe", total_duration: 7200, category: "Navigation Web" },
                        { app_name: "Discord.exe", total_duration: 3600, category: "Communication" },
                        { app_name: "Spotify.exe", total_duration: 2400, category: "Multimédia & Musique" },
                        { app_name: "explorer.exe", total_duration: 1200, category: "Système & Utilitaires" }
                    ],
                    timeline: [
                        { hour: "9", duration: 1800 },
                        { hour: "10", duration: 3600 },
                        { hour: "14", duration: 4200 },
                        { hour: "15", duration: 5400 }
                    ],
                    peak_hour: 15,
                    top_categories: [
                        { category: "Développement", duration: 14400, percentage: 50.0 },
                        { category: "Navigation Web", duration: 7200, percentage: 25.0 },
                        { category: "Communication", duration: 3600, percentage: 12.5 }
                    ]
                }),
                get_advanced_analytics: async () => ({
                    total_active: 28800,
                    total_idle: 3600,
                    total_active_formatted: "8h 00m",
                    peak_hour: 15,
                    peak_hour_label: "15h - 16h",
                    peak_hour_duration: 5400,
                    peak_hour_formatted: "1h 30m",
                    hourly_distribution: Array.from({length: 24}, (_, i) => ({
                        hour: i, label: `${i}h`, duration: i === 15 ? 5400 : (i > 8 && i < 19 ? 2400 : 0)
                    })),
                    quadrants: {
                        dominant: "apres_midi",
                        dominant_label: "Après-midi (12h - 18h)",
                        percentages: { nuit: 0, matin: 30, apres_midi: 55, soiree: 15 }
                    },
                    peak_weekday: "Jeudi",
                    max_avg_day_duration: 18000,
                    max_avg_day_formatted: "5h 00m",
                    weekdays_distribution: [
                        { weekday: 1, name: "Lundi", short: "Lun", avg_duration: 14400, day_count: 1, formatted_total: "4h" },
                        { weekday: 2, name: "Mardi", short: "Mar", avg_duration: 16000, day_count: 1, formatted_total: "4h 26m" },
                        { weekday: 3, name: "Mercredi", short: "Mer", avg_duration: 12000, day_count: 1, formatted_total: "3h 20m" },
                        { weekday: 4, name: "Jeudi", short: "Jeu", avg_duration: 18000, day_count: 1, formatted_total: "5h" },
                        { weekday: 5, name: "Vendredi", short: "Ven", avg_duration: 14000, day_count: 1, formatted_total: "3h 53m" },
                        { weekday: 6, name: "Samedi", short: "Sam", avg_duration: 7200, day_count: 1, formatted_total: "2h" },
                        { weekday: 0, name: "Dimanche", short: "Dim", avg_duration: 3600, day_count: 1, formatted_total: "1h" }
                    ],
                    weekday_split: { weekday_pct: 82, weekend_pct: 18 },
                    peak_day: { date: "2026-09-10", duration: 18000, formatted: "5h 00m", top_app: "Code.exe" },
                    time_series: [
                        { date_str: "2026-09-07", duration: 14400, formatted: "4h 00m" },
                        { date_str: "2026-09-08", duration: 16000, formatted: "4h 26m" },
                        { date_str: "2026-09-09", duration: 12000, formatted: "3h 20m" },
                        { date_str: "2026-09-10", duration: 18000, formatted: "5h 00m" },
                        { date_str: "2026-09-11", duration: 10000, formatted: "2h 46m" }
                    ],
                    top_apps_trends: [
                        { app_name: "Code.exe", category: "Développement", formatted_current: "4h 00m", prev_duration: 10800, pct_change: 33.3, trend: "up", percentage_of_total: 50.0 },
                        { app_name: "msedge.exe", category: "Navigation Web", formatted_current: "2h 00m", prev_duration: 9000, pct_change: -20.0, trend: "down", percentage_of_total: 25.0 }
                    ],
                    categories: [
                        { category: "Développement", duration: 14400, percentage: 50, formatted: "4h 00m", apps: [{ app_name: "Code.exe", formatted: "4h 00m" }] },
                        { category: "Navigation Web", duration: 7200, percentage: 25, formatted: "2h 00m", apps: [{ app_name: "msedge.exe", formatted: "2h 00m" }] }
                    ],
                    productivity_score: 75,
                    productive_time_formatted: "4h 00m",
                    entertainment_time_formatted: "1h 20m",
                    switches_per_hour: 12.4,
                    focus_label: "Deep Work (Forte concentration)",
                    focus_status: "excellent",
                    streak: 5
                }),
                get_all_apps: async () => ([
                    { app_name: "Code.exe", total_duration: 14400, category: "Développement", percentage: 50.0, sessions_count: 32 },
                    { app_name: "msedge.exe", total_duration: 7200, category: "Navigation Web", percentage: 25.0, sessions_count: 45 }
                ]),
                get_categories: async () => ({
                    categories: ["Développement", "Navigation Web", "Jeux", "Communication", "Productivité", "Multimédia & Musique", "Création & Design", "Système & Utilitaires", "Non catégorisé"],
                    app_overrides: {}
                }),
                set_app_category: async () => true,
                get_heatmap: async () => ([
                    { weekday: "1", hour: "10", duration: 3600 },
                    { weekday: "2", hour: "14", duration: 4200 }
                ]),
                get_settings: async () => ({
                    startup: true,
                    idle_timeout: 300,
                    retention_days: 30,
                    categories: { "Développement": ["code"] }
                }),
                save_settings: async () => true,
                export_csv: async () => ({ success: true, path: "C:/test.csv" })
            }
        };
        this.init();
    }
}

const app = new App();
