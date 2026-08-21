class App {
    constructor() {
        this.currentView = 'dashboard';
        this.currentPeriod = 'today';
        this.isPyWebViewReady = false;
        
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
        }, 1000);
    }

    showLoader(show) {
        document.getElementById('loader').classList.toggle('hidden', !show);
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
        if(activeNav) {
            activeNav.classList.add('bg-primary/10', 'text-primary');
            activeNav.classList.remove('text-slate-400');
            const icon = activeNav.querySelector('i, svg');
            if (icon) icon.classList.replace('text-slate-400', 'text-primary');
        }

        // Show View
        document.querySelectorAll('.page-view').forEach(el => {
            el.classList.add('hidden');
        });
        document.getElementById(`view-${viewId}`).classList.remove('hidden');
        
        // Update Title
        const titles = {
            'dashboard': 'Dashboard',
            'applications': 'Applications',
            'settings': 'Paramètres'
        };
        document.getElementById('page-title').textContent = titles[viewId];
        
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
        } else if (this.currentView === 'applications') {
            this.loadApplications();
        } else if (this.currentView === 'settings') {
            this.loadSettings();
        }
    }

    formatDuration(seconds) {
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        if (h > 0) return `${h}h ${m}m`;
        return `${m}m`;
    }

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

            // Top Apps List
            const topAppsContainer = document.getElementById('top-apps-list');
            topAppsContainer.innerHTML = '';
            
            data.top_apps.forEach((app, index) => {
                const percentage = data.total_active > 0 ? ((app.total_duration / data.total_active) * 100).toFixed(1) : 0;
                const html = `
                    <div class="flex items-center justify-between mb-3 last:mb-0">
                        <div class="flex items-center space-x-3 overflow-hidden">
                            <div class="w-6 text-center text-slate-500 font-medium">${index + 1}</div>
                            <div class="truncate">
                                <p class="text-sm font-medium text-white truncate">${app.app_name}</p>
                                <p class="text-xs text-slate-400">${app.category}</p>
                            </div>
                        </div>
                        <div class="text-right pl-4">
                            <p class="text-sm font-medium text-white">${this.formatDuration(app.total_duration)}</p>
                            <p class="text-xs text-slate-400">${percentage}%</p>
                        </div>
                    </div>
                `;
                topAppsContainer.insertAdjacentHTML('beforeend', html);
            });

            // Timeline
            window.charts.renderTimeline('timelineChart', data.timeline);

            // Heatmap (always last week or month, maybe fixed to 'week')
            const heatmapData = await window.pywebview.api.get_heatmap('week');
            window.charts.renderHeatmap('heatmap-container', heatmapData);

        } catch (e) {
            console.error(e);
        } finally {
            this.showLoader(false);
        }
    }

    async loadApplications() {
        this.showLoader(true);
        try {
            const apps = await window.pywebview.api.get_all_apps(this.currentPeriod);
            const tbody = document.getElementById('all-apps-table');
            tbody.innerHTML = '';
            
            let total = apps.reduce((acc, curr) => acc + curr.total_duration, 0);
            
            apps.forEach(app => {
                const pct = total > 0 ? ((app.total_duration / total) * 100).toFixed(1) : 0;
                const tr = document.createElement('tr');
                tr.className = 'border-b border-slate-700/50 hover:bg-slate-800/50 transition-colors';
                tr.innerHTML = `
                    <td class="px-6 py-4 font-medium text-white flex items-center">
                        <i data-lucide="monitor" class="w-4 h-4 mr-3 text-slate-400"></i> ${app.app_name}
                    </td>
                    <td class="px-6 py-4 text-slate-400"><span class="bg-slate-700 px-2 py-1 rounded text-xs">${app.category}</span></td>
                    <td class="px-6 py-4">${this.formatDuration(app.total_duration)}</td>
                    <td class="px-6 py-4">
                        <div class="flex items-center">
                            <span class="mr-2">${pct}%</span>
                            <div class="w-full bg-slate-700 rounded-full h-1.5">
                                <div class="bg-primary h-1.5 rounded-full" style="width: ${pct}%"></div>
                            </div>
                        </div>
                    </td>
                `;
                tbody.appendChild(tr);
            });
            lucide.createIcons();
        } catch (e) {
            console.error(e);
        } finally {
            this.showLoader(false);
        }
    }

    async loadSettings() {
        this.showLoader(true);
        try {
            const settings = await window.pywebview.api.get_settings();
            document.getElementById('setting-startup').checked = settings.startup;
            document.getElementById('setting-idle').value = settings.idle_timeout;
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
                idle_timeout: parseInt(document.getElementById('setting-idle').value) || 300,
                retention_days: parseInt(document.getElementById('setting-retention').value) || 30,
                categories: catObj
            };

            await window.pywebview.api.save_settings(newSettings);
            
            // Show success (simple alert or toast)
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

    // Mock for local browser testing
    initLocal() {
        console.warn("PyWebView non détecté, exécution en mode local simulé.");
        window.pywebview = {
            api: {
                get_dashboard_data: async () => ({
                    total_active: 14500,
                    total_idle: 3600,
                    top_apps: [
                        {app_name: "Code.exe", total_duration: 7200, category: "Development"},
                        {app_name: "chrome.exe", total_duration: 3600, category: "Web"},
                        {app_name: "discord.exe", total_duration: 1200, category: "Communication"}
                    ],
                    timeline: [
                        {hour: "9", duration: 1800},
                        {hour: "10", duration: 3600},
                        {hour: "11", duration: 2400}
                    ]
                }),
                get_all_apps: async () => ([
                    {app_name: "Code.exe", total_duration: 7200, category: "Development"},
                    {app_name: "chrome.exe", total_duration: 3600, category: "Web"}
                ]),
                get_heatmap: async () => ([
                    {weekday: "1", hour: "10", duration: 3600},
                    {weekday: "1", hour: "11", duration: 1800},
                    {weekday: "2", hour: "9", duration: 2400},
                ]),
                get_settings: async () => ({
                    startup: true,
                    idle_timeout: 300,
                    retention_days: 30,
                    categories: {"Dev": ["code"]}
                }),
                save_settings: async () => true,
                export_csv: async () => ({success: true, path: "C:/test.csv"})
            }
        };
        this.init();
    }
}

const app = new App();
