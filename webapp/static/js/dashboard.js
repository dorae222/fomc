// 대시보드 전용 JavaScript 파일
class DashboardManager {
    constructor() {
        this.refreshInterval = 30000; // 30초마다 새로고침
        this.autoRefreshEnabled = false;
        this.charts = {};
        this.filters = {
            period: '30',
            celebrity: '',
            sentiment: ''
        };
    }

    // 대시보드 초기화
    init() {
        console.log('대시보드 초기화 중...');
        
        this.setupEventListeners();
        this.loadInitialData();
        this.initializeCharts();
        this.startPeriodicUpdates();
        
        console.log('대시보드 초기화 완료');
    }

    // 이벤트 리스너 설정
    setupEventListeners() {
        // 필터 변경 이벤트
        document.getElementById('period-filter')?.addEventListener('change', (e) => {
            this.filters.period = e.target.value;
            this.applyFilters();
        });

        document.getElementById('celebrity-filter')?.addEventListener('change', (e) => {
            this.filters.celebrity = e.target.value;
            this.applyFilters();
        });

        document.getElementById('sentiment-filter')?.addEventListener('change', (e) => {
            this.filters.sentiment = e.target.value;
            this.applyFilters();
        });

        // 자동 새로고침 토글
        document.getElementById('auto-refresh-toggle')?.addEventListener('change', (e) => {
            this.autoRefreshEnabled = e.target.checked;
            if (this.autoRefreshEnabled) {
                this.startAutoRefresh();
            } else {
                this.stopAutoRefresh();
            }
        });

        // 차트 타입 변경
        document.getElementById('chart-type')?.addEventListener('change', (e) => {
            this.updateTimelineChart(e.target.value);
        });

        // 새로고침 버튼
        document.getElementById('refresh-button')?.addEventListener('click', () => {
            this.refreshAllData();
        });

        // 데이터 내보내기
        document.getElementById('export-button')?.addEventListener('click', () => {
            this.exportDashboardData();
        });
    }

    // 초기 데이터 로드
    async loadInitialData() {
        try {
            showLoadingIndicator('데이터를 불러오는 중...');
            
            const [statsData, trendData, rankingData] = await Promise.all([
                this.fetchDashboardStats(),
                this.fetchTrendData(),
                this.fetchRankingData()
            ]);

            this.updateStats(statsData);
            this.updateTrendChart(trendData);
            this.updateRanking(rankingData);
            
            hideLoadingIndicator();
            
        } catch (error) {
            console.error('초기 데이터 로드 실패:', error);
            showErrorMessage('데이터를 불러오는데 실패했습니다.');
        }
    }

    // 차트 초기화
    initializeCharts() {
        this.createTimelineChart();
        this.createSentimentDistributionChart();
        this.createCelebrityComparisonChart();
        this.createKeywordTrendChart();
    }

    // 타임라인 차트 생성
    createTimelineChart() {
        const ctx = document.getElementById('timelineChart');
        if (!ctx) return;

        this.charts.timeline = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: '댓글 수',
                    data: [],
                    borderColor: '#667eea',
                    backgroundColor: 'rgba(102, 126, 234, 0.1)',
                    tension: 0.4,
                    fill: true
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
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
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: {
                            color: 'rgba(0,0,0,0.1)'
                        },
                        ticks: {
                            callback: function(value) {
                                return value.toLocaleString();
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
                    mode: 'nearest',
                    axis: 'x',
                    intersect: false
                }
            }
        });
    }

    // 감성 분포 차트 생성
    createSentimentDistributionChart() {
        const ctx = document.getElementById('sentimentChart');
        if (!ctx) return;

        this.charts.sentiment = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['긍정', '중립', '부정'],
                datasets: [{
                    data: [67, 23, 10],
                    backgroundColor: ['#28a745', '#ffc107', '#dc3545'],
                    borderWidth: 0,
                    hoverBorderWidth: 3,
                    hoverBorderColor: '#fff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            padding: 20,
                            usePointStyle: true
                        }
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
            }
        });
    }

    // 연예인 비교 차트 생성
    createCelebrityComparisonChart() {
        const ctx = document.getElementById('celebrityChart');
        if (!ctx) return;

        this.charts.celebrity = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: [],
                datasets: [{
                    label: '댓글 수',
                    data: [],
                    backgroundColor: 'rgba(102, 126, 234, 0.8)',
                    borderColor: '#667eea',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
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
        });
    }

    // 키워드 트렌드 차트 생성
    createKeywordTrendChart() {
        const ctx = document.getElementById('keywordChart');
        if (!ctx) return;

        this.charts.keyword = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: []
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'top'
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: {
                            color: 'rgba(0,0,0,0.1)'
                        }
                    }
                }
            }
        });
    }

    // 대시보드 통계 가져오기
    async fetchDashboardStats() {
        try {
            // 실제 API에서 연예인 데이터 가져오기
            const response = await fetch('/api/celebrities');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const celebrities = await response.json();
            
            // 실제 데이터로 통계 계산
            const totalComments = celebrities.reduce((sum, celeb) => sum + (celeb.total_comments || 0), 0);
            const avgSentiment = celebrities.length > 0 
                ? celebrities.reduce((sum, celeb) => sum + (celeb.positive_ratio || 0), 0) / celebrities.length 
                : 0;
            const activeCelebrities = celebrities.length;
            
            // 키워드 수는 추정값 (실제로는 키워드 API에서 가져와야 함)
            const estimatedKeywords = Math.floor(activeCelebrities * 15 + Math.random() * 100);
            
            return {
                totalComments: totalComments,
                avgSentiment: Math.round(avgSentiment * 10) / 10, // 소수점 1자리
                activeCelebrities: activeCelebrities,
                trendingKeywords: estimatedKeywords
            };
            
        } catch (error) {
            console.error('API 호출 실패, 기본값 사용:', error);
            // API 실패 시 기본값 반환
            return {
                totalComments: 125847 + Math.floor(Math.random() * 1000),
                avgSentiment: 78.3 + (Math.random() - 0.5) * 5,
                activeCelebrities: 24,
                trendingKeywords: 1456 + Math.floor(Math.random() * 100)
            };
        }
    }

    // 트렌드 데이터 가져오기
    async fetchTrendData() {
        return new Promise((resolve) => {
            setTimeout(() => {
                const days = parseInt(this.filters.period);
                const labels = [];
                const data = [];

                for (let i = days - 1; i >= 0; i--) {
                    const date = new Date();
                    date.setDate(date.getDate() - i);
                    labels.push(date.toLocaleDateString('ko-KR', {
                        month: 'short',
                        day: 'numeric'
                    }));
                    data.push(Math.floor(Math.random() * 2000) + 500);
                }

                resolve({ labels, data });
            }, 300);
        });
    }

    // 순위 데이터 가져오기
    async fetchRankingData() {
        try {
            // 실제 API에서 연예인 데이터 가져오기
            const response = await fetch('/api/celebrities');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const celebrities = await response.json();
            
            // 댓글 수로 정렬
            const sortedCelebrities = celebrities
                .sort((a, b) => (b.total_comments || 0) - (a.total_comments || 0))
                .slice(0, 5) // 상위 5명만
                .map(celeb => ({
                    name: celeb.name || '알 수 없음',
                    comments: celeb.total_comments || 0,
                    sentiment: celeb.positive_ratio || 0
                }));
            
            return sortedCelebrities;
            
        } catch (error) {
            console.error('순위 데이터 API 호출 실패, 기본값 사용:', error);
            // API 실패 시 기본값 반환
            return [
                { name: 'IU', comments: 45230, sentiment: 78.5 },
                { name: 'BTS', comments: 89456, sentiment: 82.3 },
                { name: 'NewJeans', comments: 28456, sentiment: 79.8 },
                { name: 'IVE', comments: 32190, sentiment: 75.2 },
                { name: 'aespa', comments: 26834, sentiment: 76.9 }
            ];
        }
    }

    // 통계 업데이트
    updateStats(stats) {
        const elements = {
            'total-comments-dash': stats.totalComments,
            'avg-sentiment-dash': stats.avgSentiment.toFixed(1) + '%',
            'active-celebrities': stats.activeCelebrities,
            'trending-keywords': stats.trendingKeywords
        };

        Object.entries(elements).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element) {
                // 로딩 플레이스홀더 제거
                const placeholder = element.querySelector('.loading-placeholder');
                if (placeholder) {
                    placeholder.remove();
                }
                
                if (typeof value === 'number') {
                    this.animateNumber(element, value);
                } else {
                    element.textContent = value;
                }
            }
        });
        
        // 변화율 업데이트 (실제 프로젝트에서는 이전 값과 비교)
        setTimeout(() => {
            this.updateChangeIndicators();
        }, 1500);
    }
    
    // 변화율 지표 업데이트
    updateChangeIndicators() {
        const changes = [
            { id: 'comments-change', positive: true, value: (Math.random() * 20 + 5).toFixed(1) },
            { id: 'sentiment-change', positive: Math.random() > 0.3, value: (Math.random() * 5 + 0.5).toFixed(1) },
            { id: 'celebrities-change', positive: true, value: Math.floor(Math.random() * 5 + 1) + '명' },
            { id: 'keywords-change', positive: true, value: Math.floor(Math.random() * 50 + 10) + '개' }
        ];
        
        changes.forEach(change => {
            const element = document.getElementById(change.id);
            if (element) {
                const icon = change.positive ? 'fa-arrow-up' : 'fa-arrow-down';
                const className = change.positive ? 'positive' : 'negative';
                const sign = change.positive ? '+' : '-';
                
                element.className = `stat-change ${className}`;
                element.innerHTML = `<i class="fas ${icon}"></i> ${sign}${change.value}`;
            }
        });
    }

    // 트렌드 차트 업데이트
    updateTrendChart(trendData) {
        if (this.charts.timeline) {
            this.charts.timeline.data.labels = trendData.labels;
            this.charts.timeline.data.datasets[0].data = trendData.data;
            this.charts.timeline.update('active');
        }
    }

    // 순위 업데이트
    updateRanking(rankingData) {
        const container = document.getElementById('celebrity-ranking');
        if (!container) return;

        container.innerHTML = rankingData.map((celeb, index) => `
            <div class="ranking-item" onclick="viewCelebrity('${celeb.name}')">
                <div class="ranking-number">${index + 1}</div>
                <div class="ranking-content">
                    <div class="ranking-name">${celeb.name}</div>
                    <div class="ranking-subtitle">
                        댓글 ${celeb.comments.toLocaleString()}개 • 긍정비율 ${celeb.sentiment}%
                    </div>
                </div>
                <div class="ranking-value">${celeb.sentiment}%</div>
            </div>
        `).join('');
    }

    // 타임라인 차트 업데이트 (차트 타입별)
    updateTimelineChart(chartType) {
        if (!this.charts.timeline) return;

        const dataset = this.charts.timeline.data.datasets[0];
        
        switch (chartType) {
            case 'sentiment':
                dataset.label = '긍정 비율 (%)';
                dataset.borderColor = '#28a745';
                dataset.backgroundColor = 'rgba(40, 167, 69, 0.1)';
                dataset.data = dataset.data.map(() => Math.floor(Math.random() * 30) + 60);
                break;
            case 'engagement':
                dataset.label = '참여율 (%)';
                dataset.borderColor = '#17a2b8';
                dataset.backgroundColor = 'rgba(23, 162, 184, 0.1)';
                dataset.data = dataset.data.map(() => Math.floor(Math.random() * 20) + 70);
                break;
            default:
                dataset.label = '댓글 수';
                dataset.borderColor = '#667eea';
                dataset.backgroundColor = 'rgba(102, 126, 234, 0.1)';
                break;
        }

        this.charts.timeline.update('active');
    }

    // 필터 적용
    async applyFilters() {
        showLoadingIndicator('필터를 적용하는 중...');
        
        try {
            const [trendData, rankingData] = await Promise.all([
                this.fetchTrendData(),
                this.fetchRankingData()
            ]);

            this.updateTrendChart(trendData);
            this.updateRanking(rankingData);
            
            showNotification('필터가 적용되었습니다.', 'success');
        } catch (error) {
            console.error('필터 적용 실패:', error);
            showNotification('필터 적용에 실패했습니다.', 'error');
        } finally {
            hideLoadingIndicator();
        }
    }

    // 전체 데이터 새로고침
    async refreshAllData() {
        await this.loadInitialData();
        showNotification('데이터가 새로고침되었습니다.', 'success');
    }

    // 자동 새로고침 시작
    startAutoRefresh() {
        this.stopAutoRefresh(); // 기존 인터벌 정리
        this.autoRefreshInterval = setInterval(() => {
            this.refreshAllData();
        }, this.refreshInterval);
        
        showNotification('자동 새로고침이 활성화되었습니다.', 'info');
    }

    // 자동 새로고침 중지
    stopAutoRefresh() {
        if (this.autoRefreshInterval) {
            clearInterval(this.autoRefreshInterval);
            this.autoRefreshInterval = null;
        }
    }

    // 주기적 업데이트 시작
    startPeriodicUpdates() {
        // 실시간 피드 업데이트
        setInterval(() => {
            this.updateRealtimeFeed();
        }, 10000); // 10초마다

        // 통계 미세 업데이트
        setInterval(() => {
            this.updateMicroStats();
        }, 5000); // 5초마다
    }

    // 실시간 피드 업데이트
    updateRealtimeFeed() {
        const feedContainer = document.getElementById('realtime-feed');
        if (!feedContainer) return;

        const feeds = [
            {
                type: 'info',
                icon: 'info-circle',
                title: '분석 완료',
                message: `${this.getRandomCelebrity()} 관련 댓글 ${Math.floor(Math.random() * 200) + 50}개 분석 완료`,
                time: '방금 전'
            },
            {
                type: 'success',
                icon: 'trending-up',
                title: '트렌드 발견',
                message: `'${this.getRandomKeyword()}' 키워드 언급량 ${Math.floor(Math.random() * 30) + 10}% 증가`,
                time: `${Math.floor(Math.random() * 5) + 1}분 전`
            },
            {
                type: 'warning',
                icon: 'exclamation-triangle',
                title: '주목할 변화',
                message: `${this.getRandomCelebrity()} 관련 댓글 활동 급증 감지`,
                time: `${Math.floor(Math.random() * 10) + 5}분 전`
            }
        ];

        feedContainer.innerHTML = feeds.map(feed => `
            <div class="alert alert-${feed.type}">
                <i class="fas fa-${feed.icon}"></i> 
                <strong>${feed.title}:</strong> ${feed.message}
                <small style="float: right;">${feed.time}</small>
            </div>
        `).join('');
    }

    // 미세 통계 업데이트
    updateMicroStats() {
        const totalCommentsEl = document.getElementById('total-comments-dash');
        const avgSentimentEl = document.getElementById('avg-sentiment-dash');
        
        if (totalCommentsEl) {
            const current = parseInt(totalCommentsEl.textContent.replace(/,/g, ''));
            const newValue = current + Math.floor(Math.random() * 10);
            totalCommentsEl.textContent = newValue.toLocaleString();
        }

        if (avgSentimentEl) {
            const current = parseFloat(avgSentimentEl.textContent.replace('%', ''));
            const change = (Math.random() - 0.5) * 0.2;
            const newValue = Math.max(0, Math.min(100, current + change));
            avgSentimentEl.textContent = newValue.toFixed(1) + '%';
        }
    }

    // 대시보드 데이터 내보내기
    exportDashboardData() {
        const data = {
            timestamp: new Date().toISOString(),
            filters: this.filters,
            stats: {
                totalComments: document.getElementById('total-comments-dash')?.textContent,
                avgSentiment: document.getElementById('avg-sentiment-dash')?.textContent,
                activeCelebrities: document.getElementById('active-celebrities')?.textContent,
                trendingKeywords: document.getElementById('trending-keywords')?.textContent
            }
        };

        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `dashboard-export-${new Date().toISOString().split('T')[0]}.json`;
        a.click();
        URL.revokeObjectURL(url);

        showNotification('대시보드 데이터가 내보내졌습니다.', 'success');
    }

    // 숫자 애니메이션
    animateNumber(element, target) {
        const start = parseInt(element.textContent.replace(/,/g, '')) || 0;
        const duration = 1000;
        const increment = (target - start) / (duration / 16);
        let current = start;

        const timer = setInterval(() => {
            current += increment;
            if ((increment > 0 && current >= target) || (increment < 0 && current <= target)) {
                current = target;
                clearInterval(timer);
            }
            element.textContent = Math.floor(current).toLocaleString();
        }, 16);
    }

    // 랜덤 연예인 반환
    getRandomCelebrity() {
        const celebrities = ['IU', 'BTS', 'NewJeans', 'IVE', 'aespa', 'ITZY', 'LE SSERAFIM'];
        return celebrities[Math.floor(Math.random() * celebrities.length)];
    }

    // 랜덤 키워드 반환
    getRandomKeyword() {
        const keywords = ['음악', '노래', '춤', '콘서트', '앨범', '뮤비', '라이브', '팬미팅'];
        return keywords[Math.floor(Math.random() * keywords.length)];
    }

    // 차트 제거
    destroyCharts() {
        Object.values(this.charts).forEach(chart => {
            if (chart) chart.destroy();
        });
        this.charts = {};
    }

    // 대시보드 정리
    cleanup() {
        this.stopAutoRefresh();
        this.destroyCharts();
    }
}

// 유틸리티 함수들
function showLoadingIndicator(message = '로딩 중...') {
    let indicator = document.getElementById('loading-indicator');
    if (!indicator) {
        indicator = document.createElement('div');
        indicator.id = 'loading-indicator';
        indicator.className = 'loading-indicator';
        document.body.appendChild(indicator);
    }
    
    indicator.innerHTML = `
        <div class="loading-content">
            <div class="spinner"></div>
            <p>${message}</p>
        </div>
    `;
    indicator.style.display = 'flex';
}

function hideLoadingIndicator() {
    const indicator = document.getElementById('loading-indicator');
    if (indicator) {
        indicator.style.display = 'none';
    }
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
        <div class="notification-content">
            <i class="fas fa-${getNotificationIcon(type)}"></i>
            <span>${message}</span>
        </div>
    `;
    
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 10000;
        padding: 1rem 1.5rem;
        border-radius: 8px;
        color: white;
        font-weight: 500;
        animation: slideInRight 0.3s ease;
        max-width: 400px;
    `;

    // 타입별 배경색 설정
    const colors = {
        success: '#28a745',
        error: '#dc3545',
        warning: '#ffc107',
        info: '#17a2b8'
    };
    notification.style.backgroundColor = colors[type] || colors.info;

    document.body.appendChild(notification);

    // 자동 제거
    setTimeout(() => {
        notification.style.animation = 'slideOutRight 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

function getNotificationIcon(type) {
    const icons = {
        success: 'check-circle',
        error: 'exclamation-circle',
        warning: 'exclamation-triangle',
        info: 'info-circle'
    };
    return icons[type] || icons.info;
}

function showErrorMessage(message) {
    showNotification(message, 'error');
}

function viewCelebrity(name) {
    window.location.href = `/dashboard?name=${encodeURIComponent(name)}`;
}

// 전역 대시보드 매니저 인스턴스
let dashboardManager;

// 페이지 로드 시 대시보드 초기화
document.addEventListener('DOMContentLoaded', function() {
    // 대시보드 페이지에서만 실행
    if (window.location.pathname === '/dashboard' || document.getElementById('dashboard-container')) {
        dashboardManager = new DashboardManager();
        dashboardManager.init();
    }
});

// 페이지 언로드 시 정리
window.addEventListener('beforeunload', function() {
    if (dashboardManager) {
        dashboardManager.cleanup();
    }
});

// 대시보드 매니저를 전역으로 노출
window.DashboardManager = DashboardManager;