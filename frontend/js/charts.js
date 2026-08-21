class ChartManager {
    constructor() {
        this.timelineChart = null;
        Chart.defaults.color = '#94a3b8'; // slate-400
        Chart.defaults.font.family = 'Inter, sans-serif';
    }

    renderTimeline(canvasId, data) {
        const ctx = document.getElementById(canvasId).getContext('2d');
        
        if (this.timelineChart) {
            this.timelineChart.destroy();
        }

        // Prepare data (24 hours)
        const labels = Array.from({length: 24}, (_, i) => `${i}h`);
        const dataset = new Array(24).fill(0);
        
        data.forEach(item => {
            const hour = parseInt(item.hour, 10);
            if (!isNaN(hour) && hour >= 0 && hour < 24) {
                dataset[hour] = item.duration / 60; // in minutes
            }
        });

        this.timelineChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Minutes actives',
                    data: dataset,
                    backgroundColor: '#3b82f6', // primary
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
                            label: function(context) {
                                let val = context.raw;
                                return Math.round(val) + ' min';
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: { color: '#334155' }, // slate-700
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

    renderHeatmap(containerId, data) {
        const container = document.getElementById(containerId);
        container.innerHTML = '';
        
        // Data format: [{weekday: "0", hour: "14", duration: 120}, ...]
        // 0 = Sunday, 1 = Monday ... 6 = Saturday
        const days = ['Dim', 'Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam'];
        
        // Find max duration for scaling
        let maxDuration = 0;
        data.forEach(d => { if(d.duration > maxDuration) maxDuration = d.duration; });
        
        const getHeatClass = (duration) => {
            if (duration === 0) return 'heat-0';
            const ratio = duration / (maxDuration || 1);
            if (ratio < 0.2) return 'heat-1';
            if (ratio < 0.4) return 'heat-2';
            if (ratio < 0.6) return 'heat-3';
            if (ratio < 0.8) return 'heat-4';
            return 'heat-5';
        };

        // Header (Hours)
        const headerRow = document.createElement('div');
        headerRow.className = 'flex gap-1 mb-1 ml-8';
        for(let h=0; h<24; h++) {
            const hDiv = document.createElement('div');
            hDiv.className = 'w-[14px] text-[8px] text-slate-500 text-center';
            if (h % 2 === 0) hDiv.textContent = h;
            headerRow.appendChild(hDiv);
        }
        container.appendChild(headerRow);

        // Grid (Days)
        for (let d = 0; d < 7; d++) {
            // Start from Monday (1) to Sunday (0)
            const realDay = (d + 1) % 7; 
            
            const row = document.createElement('div');
            row.className = 'flex gap-1 items-center';
            
            const dayLabel = document.createElement('div');
            dayLabel.className = 'w-8 text-xs text-slate-400 text-right pr-2';
            dayLabel.textContent = days[realDay];
            row.appendChild(dayLabel);
            
            for (let h = 0; h < 24; h++) {
                const block = document.createElement('div');
                
                // find data
                const entry = data.find(item => parseInt(item.weekday) === realDay && parseInt(item.hour) === h);
                const duration = entry ? entry.duration : 0;
                
                block.className = `heat-block ${getHeatClass(duration)}`;
                block.title = `${days[realDay]} ${h}h: ${Math.round(duration/60)} min`;
                
                row.appendChild(block);
            }
            container.appendChild(row);
        }
    }
}

window.charts = new ChartManager();
