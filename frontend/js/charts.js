class ChartManager {
    constructor() {
        this.charts = {};
        Chart.defaults.color = '#94a3b8'; // slate-400
        Chart.defaults.font.family = 'Inter, system-ui, -apple-system, sans-serif';
    }

    _destroyChart(id) {
        if (this.charts[id]) {
            this.charts[id].destroy();
            this.charts[id] = null;
        }
    }

    _formatDurationTooltip(minutes) {
        const totalMinutes = Math.round(minutes);
        const h = Math.floor(totalMinutes / 60);
        const m = totalMinutes % 60;
        if (h > 0) return `${h}h ${m > 0 ? m + 'm' : ''}`;
        return `${m} min`;
    }

    getCategoryColor(categoryName) {
        const palette = {
            "Développement": "#3b82f6",       // blue-500
            "Navigation Web": "#06b6d4",      // cyan-500
            "Jeux": "#ec4899",                // pink-500
            "Communication": "#8b5cf6",       // violet-500
            "Productivité": "#10b981",        // emerald-500
            "Multimédia & Musique": "#f59e0b",// amber-500
            "Création & Design": "#f97316",   // orange-500
            "Système & Utilitaires": "#64748b",// slate-500
            "Non catégorisé": "#475569",       // slate-600
            "Inconnu": "#334155"              // slate-700
        };
        return palette[categoryName] || "#3b82f6";
    }

    // 1. Dashboard Timeline
    renderTimeline(canvasId, data, peakHour = null) {
        const el = document.getElementById(canvasId);
        if (!el) return;
        this._destroyChart(canvasId);

        const labels = Array.from({ length: 24 }, (_, i) => `${i}h`);
        const dataset = new Array(24).fill(0);
        
        data.forEach(item => {
            const hour = parseInt(item.hour, 10);
            if (!isNaN(hour) && hour >= 0 && hour < 24) {
                dataset[hour] = item.duration / 60; // minutes
            }
        });

        const bgColors = dataset.map((val, idx) => {
            if (peakHour !== null && idx === peakHour && val > 0) {
                return '#f59e0b'; // Amber highlight for peak hour
            }
            return '#3b82f6';
        });

        const ctx = el.getContext('2d');
        this.charts[canvasId] = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Minutes actives',
                    data: dataset,
                    backgroundColor: bgColors,
                    borderRadius: 4,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (context) => this._formatDurationTooltip(context.raw)
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: { color: '#334155' },
                        border: { display: false }
                    },
                    x: {
                        grid: { display: false },
                        border: { display: false }
                    }
                }
            }
        });
    }

    // 2. Peak Hours 24h Distribution
    renderPeakHoursChart(canvasId, hourlyData, peakHour = null) {
        const el = document.getElementById(canvasId);
        if (!el) return;
        this._destroyChart(canvasId);

        const labels = Array.from({ length: 24 }, (_, i) => `${i}h`);
        const dataset = new Array(24).fill(0);

        if (Array.isArray(hourlyData)) {
            hourlyData.forEach(item => {
                const h = parseInt(item.hour, 10);
                if (!isNaN(h) && h >= 0 && h < 24) {
                    dataset[h] = item.duration / 60; // in minutes
                }
            });
        }

        const bgColors = dataset.map((val, idx) => {
            if (peakHour !== null && idx === peakHour && val > 0) {
                return '#f59e0b'; // Amber for the peak hour
            }
            return '#3b82f6'; // Blue
        });

        const hoverColors = dataset.map((val, idx) => {
            if (peakHour !== null && idx === peakHour && val > 0) {
                return '#d97706';
            }
            return '#2563eb';
        });

        const ctx = el.getContext('2d');
        this.charts[canvasId] = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Activité',
                    data: dataset,
                    backgroundColor: bgColors,
                    hoverBackgroundColor: hoverColors,
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            title: (items) => {
                                const h = items[0].label.replace('h', '');
                                return `Créneau : ${h}h00 - ${parseInt(h) + 1}h00`;
                            },
                            label: (context) => {
                                const isPeak = peakHour !== null && context.dataIndex === peakHour;
                                const suffix = isPeak ? ' ⭐ (Heure de pointe)' : '';
                                return `Temps : ${this._formatDurationTooltip(context.raw)}${suffix}`;
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: { color: '#334155' },
                        border: { display: false }
                    },
                    x: {
                        grid: { display: false },
                        border: { display: false }
                    }
                }
            }
        });
    }

    // 3. Peak Days of the Week (Lun-Dim)
    renderPeakDaysChart(canvasId, weekdayData, peakWeekdayName = null) {
        const el = document.getElementById(canvasId);
        if (!el) return;
        this._destroyChart(canvasId);

        const labels = [];
        const dataset = [];

        weekdayData.forEach(item => {
            labels.push(item.short || item.name);
            dataset.push(item.avg_duration / 60); // in minutes
        });

        const bgColors = weekdayData.map(item => {
            if (peakWeekdayName && item.name === peakWeekdayName && item.avg_duration > 0) {
                return '#8b5cf6'; // Purple highlight for peak day
            }
            if (item.weekday === 6 || item.weekday === 0) {
                return '#64748b'; // Slate for weekend
            }
            return '#3b82f6'; // Primary for weekdays
        });

        const ctx = el.getContext('2d');
        this.charts[canvasId] = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Moyenne par jour',
                    data: dataset,
                    backgroundColor: bgColors,
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            title: (items) => weekdayData[items[0].dataIndex].name,
                            label: (context) => {
                                const idx = context.dataIndex;
                                const item = weekdayData[idx];
                                const isPeak = peakWeekdayName && item.name === peakWeekdayName;
                                const peakTxt = isPeak ? ' ⭐ (Jour de pointe)' : '';
                                return [
                                    `Moyenne : ${this._formatDurationTooltip(context.raw)}${peakTxt}`,
                                    `Total cumulé : ${item.formatted_total} (${item.day_count} j)`
                                ];
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: { color: '#334155' },
                        border: { display: false }
                    },
                    x: {
                        grid: { display: false },
                        border: { display: false }
                    }
                }
            }
        });
    }

    // 4. Time Series of Activity & Spike Detection
    renderPeaksTimeSeries(canvasId, timeSeriesData, peakDate = null) {
        const el = document.getElementById(canvasId);
        if (!el) return;
        this._destroyChart(canvasId);

        if (!timeSeriesData || timeSeriesData.length === 0) return;

        const labels = timeSeriesData.map(d => {
            const parts = d.date_str.split('-');
            return `${parts[2]}/${parts[1]}`;
        });
        const dataset = timeSeriesData.map(d => d.duration / 3600); // in hours

        const bgColors = timeSeriesData.map(d => {
            if (peakDate && d.date_str === peakDate) {
                return '#eab308'; // Bright gold for peak day!
            }
            return 'rgba(59, 130, 246, 0.7)';
        });

        const borderColors = timeSeriesData.map(d => {
            if (peakDate && d.date_str === peakDate) {
                return '#facc15';
            }
            return '#3b82f6';
        });

        const ctx = el.getContext('2d');
        this.charts[canvasId] = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Heures d\'activité',
                    data: dataset,
                    backgroundColor: bgColors,
                    borderColor: borderColors,
                    borderWidth: 1,
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            title: (items) => timeSeriesData[items[0].dataIndex].date_str,
                            label: (context) => {
                                const idx = context.dataIndex;
                                const item = timeSeriesData[idx];
                                const isPeak = peakDate && item.date_str === peakDate;
                                const suffix = isPeak ? ' 🏆 PIC DE LA PÉRIODE' : '';
                                return `Activité : ${item.formatted}${suffix}`;
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: { color: '#334155' },
                        border: { display: false },
                        ticks: {
                            callback: (val) => `${val}h`
                        }
                    },
                    x: {
                        grid: { display: false },
                        border: { display: false }
                    }
                }
            }
        });
    }

    // 5. Category Doughnut
    renderCategoryDoughnut(canvasId, categoriesData) {
        const el = document.getElementById(canvasId);
        if (!el) return;
        this._destroyChart(canvasId);

        if (!categoriesData || categoriesData.length === 0) return;

        const labels = categoriesData.map(c => c.category);
        const data = categoriesData.map(c => c.duration / 60); // minutes
        const bgColors = categoriesData.map(c => this.getCategoryColor(c.category));

        const ctx = el.getContext('2d');
        this.charts[canvasId] = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: data,
                    backgroundColor: bgColors,
                    borderColor: '#1e293b',
                    borderWidth: 2,
                    hoverOffset: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '68%',
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            boxWidth: 12,
                            padding: 10,
                            font: { size: 11 },
                            color: '#cbd5e1'
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: (context) => {
                                const cat = categoriesData[context.dataIndex];
                                return ` ${cat.category} : ${cat.formatted} (${cat.percentage}%)`;
                            }
                        }
                    }
                }
            }
        });
    }

    // 6. Heatmap Grid (Week Intensity)
    renderHeatmap(containerId, data) {
        const container = document.getElementById(containerId);
        if (!container) return;
        container.innerHTML = '';
        
        const days = ['Dim', 'Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam'];
        
        let maxDuration = 0;
        data.forEach(d => { if (d.duration > maxDuration) maxDuration = d.duration; });
        
        const getHeatClass = (duration) => {
            if (duration === 0) return 'heat-0';
            const ratio = duration / (maxDuration || 1);
            if (ratio < 0.2) return 'heat-1';
            if (ratio < 0.4) return 'heat-2';
            if (ratio < 0.6) return 'heat-3';
            if (ratio < 0.8) return 'heat-4';
            return 'heat-5';
        };

        const headerRow = document.createElement('div');
        headerRow.className = 'flex gap-1 mb-1 ml-8';
        for (let h = 0; h < 24; h++) {
            const hDiv = document.createElement('div');
            hDiv.className = 'w-[14px] text-[8px] text-slate-500 text-center';
            if (h % 2 === 0) hDiv.textContent = h;
            headerRow.appendChild(hDiv);
        }
        container.appendChild(headerRow);

        for (let d = 0; d < 7; d++) {
            const realDay = (d + 1) % 7; 
            
            const row = document.createElement('div');
            row.className = 'flex gap-1 items-center';
            
            const dayLabel = document.createElement('div');
            dayLabel.className = 'w-8 text-xs text-slate-400 text-right pr-2';
            dayLabel.textContent = days[realDay];
            row.appendChild(dayLabel);
            
            for (let h = 0; h < 24; h++) {
                const block = document.createElement('div');
                
                const entry = data.find(item => parseInt(item.weekday) === realDay && parseInt(item.hour) === h);
                const duration = entry ? entry.duration : 0;
                
                block.className = `heat-block ${getHeatClass(duration)}`;
                block.title = `${days[realDay]} ${h}h: ${Math.round(duration / 60)} min`;
                
                row.appendChild(block);
            }
            container.appendChild(row);
        }
    }
}

window.charts = new ChartManager();
