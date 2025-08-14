// 차트 관련 함수들
class ChartManager {
    constructor() {
        this.charts = {};
        this.defaultOptions = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                }
            }
        };
    }

    // 라인 차트 생성
    createLineChart(canvasId, data, options = {}) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) {
            console.error(`Canvas with id '${canvasId}' not found`);
            return null;
        }

        const ctx = canvas.getContext('2d');
        const config = {
            type: 'line',
            data: data,
            options: {
                ...this.defaultOptions,
                ...options,
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: {
                            color: 'rgba(0,0,0,0.1)'
                        },
                        ticks: {
                            callback: function(value) {
                                return typeof value === 'number' ? value.toLocaleString() : value;
                            }
                        }
                    },
                    x: {
                        grid: {
                            color: 'rgba(0,0,0,0.1)'
                        }
                    }
                },
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                plugins: {
                    ...this.defaultOptions.plugins,
                    tooltip: {
                        backgroundColor: 'rgba(0,0,0,0.8)',
                        titleColor: 'white',
                        bodyColor: 'white',
                        borderColor: '#667eea',
                        borderWidth: 1
                    }
                }
            }
        };

        const chart = new Chart(ctx, config);
        this.charts[canvasId] = chart;
        return chart;
    }

    // 바 차트 생성
    createBarChart(canvasId, data, options = {}) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) {
            console.error(`Canvas with id '${canvasId}' not found`);
            return null;
        }

        const ctx = canvas.getContext('2d');
        const config = {
            type: 'bar',
            data: data,
            options: {
                ...this.defaultOptions,
                ...options,
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: {
                            color: 'rgba(0,0,0,0.1)'
                        }
                    },
                    x: {
                        grid: {
                            display: false
                        }
                    }
                }
            }
        };

        const chart = new Chart(ctx, config);
        this.charts[canvasId] = chart;
        return chart;
    }

    // 도넛 차트 생성
    createDoughnutChart(canvasId, data, options = {}) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) {
            console.error(`Canvas with id '${canvasId}' not found`);
            return null;
        }

        const ctx = canvas.getContext('2d');
        const config = {
            type: 'doughnut',
            data: data,
            options: {
                ...this.defaultOptions,
                ...options,
                plugins: {
                    ...this.defaultOptions.plugins,
                    legend: {
                        position: 'bottom',
                        labels: {
                            padding: 20,
                            usePointStyle: true
                        }
                    }
                }
            }
        };

        const chart = new Chart(ctx, config);
        this.charts[canvasId] = chart;
        return chart;
    }

    // 극지방 차트 생성
    createPolarAreaChart(canvasId, data, options = {}) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) {
            console.error(`Canvas with id '${canvasId}' not found`);
            return null;
        }

        const ctx = canvas.getContext('2d');
        const config = {
            type: 'polarArea',
            data: data,
            options: {
                ...this.defaultOptions,
                ...options,
                scales: {
                    r: {
                        beginAtZero: true,
                        grid: {
                            color: 'rgba(0,0,0,0.1)'
                        }
                    }
                }
            }
        };

        const chart = new Chart(ctx, config);
        this.charts[canvasId] = chart;
        return chart;
    }

    // 레이더 차트 생성
    createRadarChart(canvasId, data, options = {}) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) {
            console.error(`Canvas with id '${canvasId}' not found`);
            return null;
        }

        const ctx = canvas.getContext('2d');
        const config = {
            type: 'radar',
            data: data,
            options: {
                ...this.defaultOptions,
                ...options,
                scales: {
                    r: {
                        beginAtZero: true,
                        max: 100,
                        grid: {
                            color: 'rgba(0,0,0,0.1)'
                        },
                        pointLabels: {
                            font: {
                                size: 12
                            }
                        }
                    }
                }
            }
        };

        const chart = new Chart(ctx, config);
        this.charts[canvasId] = chart;
        return chart;
    }

    // 차트 업데이트
    updateChart(canvasId, newData) {
        const chart = this.charts[canvasId];
        if (!chart) {
            console.error(`Chart with id '${canvasId}' not found`);
            return false;
        }

        chart.data = newData;
        chart.update('active');
        return true;
    }

    // 차트 데이터만 업데이트
    updateChartData(canvasId, newDatasets) {
        const chart = this.charts[canvasId];
        if (!chart) {
            console.error(`Chart with id '${canvasId}' not found`);
            return false;
        }

        chart.data.datasets = newDatasets;
        chart.update('active');
        return true;
    }

    // 차트 라벨 업데이트
    updateChartLabels(canvasId, newLabels) {
        const chart = this.charts[canvasId];
        if (!chart) {
            console.error(`Chart with id '${canvasId}' not found`);
            return false;
        }

        chart.data.labels = newLabels;
        chart.update('active');
        return true;
    }

    // 차트 제거
    destroyChart(canvasId) {
        const chart = this.charts[canvasId];
        if (chart) {
            chart.destroy();
            delete this.charts[canvasId];
            return true;
        }
        return false;
    }

    // 모든 차트 제거
    destroyAllCharts() {
        Object.keys(this.charts).forEach(canvasId => {
            this.destroyChart(canvasId);
        });
    }

    // 차트 색상 팔레트
    getColorPalette(count = 1, opacity = 1) {
        const colors = [
            '#667eea', '#764ba2', '#f093fb', '#f5576c',
            '#4facfe', '#00f2fe', '#43e97b', '#38f9d7',
            '#ffecd2', '#fcb69f', '#a8edea', '#fed6e3',
            '#ff9a9e', '#fecfef', '#ffeaa7', '#81ecec'
        ];

        if (count === 1) {
            const color = colors[0];
            return opacity < 1 ? this.hexToRgba(color, opacity) : color;
        }

        return colors.slice(0, count).map(color => 
            opacity < 1 ? this.hexToRgba(color, opacity) : color
        );
    }

    // Hex 색상을 RGBA로 변환
    hexToRgba(hex, opacity) {
        const r = parseInt(hex.slice(1, 3), 16);
        const g = parseInt(hex.slice(3, 5), 16);
        const b = parseInt(hex.slice(5, 7), 16);
        return `rgba(${r}, ${g}, ${b}, ${opacity})`;
    }

    // 그라디언트 생성
    createGradient(ctx, colorStart, colorEnd, vertical = false) {
        const gradient = vertical 
            ? ctx.createLinearGradient(0, 0, 0, 400)
            : ctx.createLinearGradient(0, 0, 400, 0);
        
        gradient.addColorStop(0, colorStart);
        gradient.addColorStop(1, colorEnd);
        return gradient;
    }

    // 감성 분석 차트 생성 (특화)
    createSentimentChart(canvasId, data) {
        return this.createDoughnutChart(canvasId, {
            labels: ['긍정', '중립', '부정'],
            datasets: [{
                data: data,
                backgroundColor: ['#28a745', '#ffc107', '#dc3545'],
                borderWidth: 0,
                hoverBorderWidth: 3,
                hoverBorderColor: '#fff'
            }]
        }, {
            plugins: {
                legend: {
                    position: 'bottom'
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = ((context.parsed / total) * 100).toFixed(1);
                            return `${context.label}: ${percentage}%`;
                        }
                    }
                }
            }
        });
    }

    // 시간별 트렌드 차트 생성 (특화)
    createTrendChart(canvasId, labels, datasets) {
        const canvas = document.getElementById(canvasId);
        const ctx = canvas.getContext('2d');
        
        // 그라디언트 배경 생성
        const gradient = this.createGradient(ctx, 
            this.hexToRgba('#667eea', 0.3), 
            this.hexToRgba('#667eea', 0.05), 
            true
        );

        return this.createLineChart(canvasId, {
            labels: labels,
            datasets: datasets.map((dataset, index) => ({
                ...dataset,
                borderColor: this.getColorPalette(datasets.length)[index],
                backgroundColor: index === 0 ? gradient : this.hexToRgba(this.getColorPalette(datasets.length)[index], 0.1),
                tension: 0.4,
                fill: index === 0,
                pointBackgroundColor: '#fff',
                pointBorderWidth: 2,
                pointRadius: 4,
                pointHoverRadius: 6
            }))
        }, {
            plugins: {
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    callbacks: {
                        title: function(tooltipItems) {
                            return `날짜: ${tooltipItems[0].label}`;
                        },
                        label: function(context) {
                            return `${context.dataset.label}: ${context.parsed.y.toLocaleString()}`;
                        }
                    }
                }
            },
            interaction: {
                mode: 'nearest',
                axis: 'x',
                intersect: false
            }
        });
    }

    // 키워드 빈도 차트 생성 (특화)
    createKeywordChart(canvasId, keywords, counts) {
        return this.createBarChart(canvasId, {
            labels: keywords,
            datasets: [{
                label: '언급 횟수',
                data: counts,
                backgroundColor: this.getColorPalette(keywords.length, 0.8),
                borderColor: this.getColorPalette(keywords.length),
                borderWidth: 1,
                borderRadius: 4,
                borderSkipped: false
            }]
        }, {
            indexAxis: 'y',
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `${context.parsed.x.toLocaleString()}회 언급`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(0,0,0,0.1)'
                    }
                },
                y: {
                    grid: {
                        display: false
                    }
                }
            }
        });
    }

    // 연예인 비교 차트 생성 (특화)
    createComparisonChart(canvasId, celebrities, metrics) {
        return this.createRadarChart(canvasId, {
            labels: ['댓글 수', '긍정 비율', '활동성', '트렌드', '영향력'],
            datasets: celebrities.map((celeb, index) => ({
                label: celeb.name,
                data: [
                    metrics[celeb.name]?.comments || 0,
                    metrics[celeb.name]?.positive || 0,
                    metrics[celeb.name]?.activity || 0,
                    metrics[celeb.name]?.trend || 0,
                    metrics[celeb.name]?.influence || 0
                ],
                borderColor: this.getColorPalette(celebrities.length)[index],
                backgroundColor: this.hexToRgba(this.getColorPalette(celebrities.length)[index], 0.2),
                pointBackgroundColor: this.getColorPalette(celebrities.length)[index],
                pointBorderColor: '#fff',
                pointHoverBackgroundColor: '#fff',
                pointHoverBorderColor: this.getColorPalette(celebrities.length)[index]
            }))
        });
    }

    // 차트 이미지로 다운로드
    downloadChart(canvasId, filename = 'chart.png') {
        const chart = this.charts[canvasId];
        if (!chart) {
            console.error(`Chart with id '${canvasId}' not found`);
            return false;
        }

        const link = document.createElement('a');
        link.download = filename;
        link.href = chart.toBase64Image();
        link.click();
        return true;
    }

    // 차트 애니메이션 실행
    animateChart(canvasId, duration = 1000) {
        const chart = this.charts[canvasId];
        if (!chart) {
            console.error(`Chart with id '${canvasId}' not found`);
            return false;
        }

        chart.reset();
        chart.update('active');
        return true;
    }

    // 차트 크기 조정
    resizeChart(canvasId) {
        const chart = this.charts[canvasId];
        if (!chart) {
            console.error(`Chart with id '${canvasId}' not found`);
            return false;
        }

        chart.resize();
        return true;
    }

    // 모든 차트 크기 조정
    resizeAllCharts() {
        Object.values(this.charts).forEach(chart => {
            chart.resize();
        });
    }
}

// 전역 차트 매니저 인스턴스
const chartManager = new ChartManager();

// Chart.js 기본 설정
Chart.defaults.font.family = "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif";
Chart.defaults.font.size = 12;
Chart.defaults.color = '#333';

// 반응형 차트를 위한 리사이즈 이벤트
window.addEventListener('resize', debounce(() => {
    chartManager.resizeAllCharts();
}, 250));

// 유틸리티 함수들
function generateTimeLabels(days) {
    const labels = [];
    for (let i = days - 1; i >= 0; i--) {
        const date = new Date();
        date.setDate(date.getDate() - i);
        labels.push(date.toLocaleDateString('ko-KR', {
            month: 'short',
            day: 'numeric'
        }));
    }
    return labels;
}

function generateRandomData(length, min, max) {
    return Array.from({length}, () => 
        Math.floor(Math.random() * (max - min + 1)) + min
    );
}

function generateTrendData(length, baseValue, variance) {
    const data = [];
    let current = baseValue;
    
    for (let i = 0; i < length; i++) {
        current += (Math.random() - 0.5) * variance;
        current = Math.max(0, current);
        data.push(Math.floor(current));
    }
    
    return data;
}

// 차트 매니저를 전역으로 내보내기
window.ChartManager = ChartManager;
window.chartManager = chartManager;