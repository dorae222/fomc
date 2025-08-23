// Main dashboard functionality
document.addEventListener('DOMContentLoaded', function() {
    // Initialize dashboard
    initializeDashboard();
    
    // Load initial data
    loadDashboardData();
});

function initializeDashboard() {
    // Set up event listeners
    setupEventListeners();
    
    // Initialize date pickers if present
    initializeDatePickers();
    
    // Set up refresh functionality
    setupRefresh();
}

function setupEventListeners() {
    // Navigation menu handlers
    // Only intercept clicks for elements explicitly using data-target (single-page sections)
    const navTargets = document.querySelectorAll('[data-target]');
    navTargets.forEach(el => {
        el.addEventListener('click', function(e) {
            const target = this.getAttribute('data-target');
            if (target) {
                e.preventDefault();
                navigateToSection(target);
            }
        });
    });

    // Filter handlers
    const filterButtons = document.querySelectorAll('.filter-btn');
    filterButtons.forEach(btn => {
        btn.addEventListener('click', function() {
            const filter = this.getAttribute('data-filter');
            applyFilter(filter);
        });
    });
}

function initializeDatePickers() {
    const datePickers = document.querySelectorAll('.date-picker');
    datePickers.forEach(picker => {
        // Initialize with flatpickr or similar date picker library
        if (typeof flatpickr !== 'undefined') {
            flatpickr(picker, {
                dateFormat: "Y-m-d",
                onChange: function(selectedDates, dateStr, instance) {
                    handleDateChange(dateStr, picker);
                }
            });
        }
    });
}

function setupRefresh() {
    const refreshBtn = document.getElementById('refresh-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function() {
            refreshDashboard();
        });
    }
    
    // Auto-refresh every 5 minutes
    setInterval(refreshDashboard, 300000);
}

function loadDashboardData() {
    // Show loading state
    showLoading();
    
    // Load summary statistics
    fetch('/api/summary')
        .then(response => response.json())
        .then(data => {
            updateSummaryCards(data);
        })
        .catch(error => {
            console.error('Error loading summary:', error);
            showError('Failed to load summary data');
        });
    
    // Load timeline data
    fetch('/api/timeline')
        .then(response => response.json())
        .then(data => {
            updateTimeline(data);
            hideLoading();
        })
        .catch(error => {
            console.error('Error loading timeline:', error);
            showError('Failed to load timeline data');
            hideLoading();
        });
}

function updateSummaryCards(data) {
    // Update total predictions
    const totalElement = document.getElementById('total-docs');
    if (totalElement) {
        totalElement.textContent = data.total_predictions || 0;
    }
    
    // Update sentiment distribution percentages
    const sentimentData = data.sentiment_distribution || {};
    
    const hawkishPct = document.getElementById('hawkish-pct');
    if (hawkishPct) {
        const hawkishPercent = ((sentimentData.hawkish || 0) * 100).toFixed(1);
        hawkishPct.textContent = hawkishPercent + '%';
    }
    
    const dovishPct = document.getElementById('dovish-pct');
    if (dovishPct) {
        const dovishPercent = ((sentimentData.dovish || 0) * 100).toFixed(1);
        dovishPct.textContent = dovishPercent + '%';
    }
    
    // Update confidence score
    const confidenceElement = document.getElementById('avg-confidence');
    if (confidenceElement) {
        confidenceElement.textContent = (data.avg_confidence || 0).toFixed(3);
    }
    
    // Create sentiment pie chart if container exists
    const sentimentPieContainer = document.getElementById('sentiment-pie');
    if (sentimentPieContainer) {
        createSentimentPieChart(sentimentData);
    }
}

function updateTimeline(data) {
    // Update timeline chart using Plotly
    const timelineContainer = document.getElementById('timeline-chart');
    if (timelineContainer) {
        createTimelineChart(data);
    }
}

function createSentimentPieChart(sentimentData) {
    const data = [{
        values: [
            (sentimentData.hawkish || 0) * 100,
            (sentimentData.dovish || 0) * 100,
            (sentimentData.neutral || 0) * 100
        ],
        labels: ['Hawkish', 'Dovish', 'Neutral'],
        type: 'pie',
        marker: {
            colors: ['#d32f2f', '#1976d2', '#757575']
        }
    }];

    const layout = {
        showlegend: true,
        height: 350,
        margin: { t: 40, b: 40, l: 40, r: 40 }
    };

    const config = {
        responsive: true,
        displayModeBar: false
    };

    Plotly.newPlot('sentiment-pie', data, layout, config);
}

function createTimelineChart(data) {
    const traces = [];
    
    if (data.hawkish && data.hawkish.length > 0) {
        traces.push({
            x: data.dates,
            y: data.hawkish,
            type: 'scatter',
            mode: 'lines+markers',
            name: 'Hawkish',
            line: { color: '#d32f2f' }
        });
    }
    
    if (data.dovish && data.dovish.length > 0) {
        traces.push({
            x: data.dates,
            y: data.dovish,
            type: 'scatter',
            mode: 'lines+markers',
            name: 'Dovish',
            line: { color: '#1976d2' }
        });
    }
    
    if (data.neutral && data.neutral.length > 0) {
        traces.push({
            x: data.dates,
            y: data.neutral,
            type: 'scatter',
            mode: 'lines+markers',
            name: 'Neutral',
            line: { color: '#757575' }
        });
    }

    const layout = {
        title: 'Sentiment Evolution Over Time',
        xaxis: { title: 'Date' },
        yaxis: { title: 'Percentage (%)' },
        height: 350,
        margin: { t: 60, b: 60, l: 60, r: 60 },
        showlegend: true
    };

    const config = {
        responsive: true,
        displayModeBar: true
    };

    // Ensure x values are ISO strings to avoid Invalid Date issues
    const normalizedTraces = traces.map(t => ({
        ...t,
        x: (t.x || []).map(d => normalizeDateString(d))
    }));
    Plotly.newPlot('timeline-chart', normalizedTraces, layout, config);
}

function navigateToSection(target) {
    // Handle navigation between sections
    const sections = document.querySelectorAll('.dashboard-section');
    sections.forEach(section => {
        section.style.display = 'none';
    });
    
    const targetSection = document.getElementById(target);
    if (targetSection) {
        targetSection.style.display = 'block';
    }
    
    // Update active nav item
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.classList.remove('active');
    });
    
    const activeNav = document.querySelector(`[data-target="${target}"]`);
    if (activeNav) {
        activeNav.classList.add('active');
    }
}

// Normalize date strings to YYYY-MM-DD to avoid Invalid Date in browsers
function normalizeDateString(d) {
    if (!d) return d;
    // Already ISO-like
    if (/^\d{4}-\d{2}-\d{2}$/.test(d)) return d;
    // Try YYYY/MM/DD
    const m1 = d.match(/^(\d{4})[\/](\d{1,2})[\/](\d{1,2})$/);
    if (m1) {
        const y = m1[1];
        const m = String(m1[2]).padStart(2, '0');
        const day = String(m1[3]).padStart(2, '0');
        return `${y}-${m}-${day}`;
    }
    // Try Date parse fallback
    const dt = new Date(d);
    if (!isNaN(dt.getTime())) {
        const y = dt.getFullYear();
        const m = String(dt.getMonth() + 1).padStart(2, '0');
        const day = String(dt.getDate()).padStart(2, '0');
        return `${y}-${m}-${day}`;
    }
    return d;
}

function applyFilter(filter) {
    // Apply filters to data display
    console.log('Applying filter:', filter);
    
    // Update filter buttons
    const filterButtons = document.querySelectorAll('.filter-btn');
    filterButtons.forEach(btn => {
        btn.classList.remove('active');
    });
    
    const activeFilter = document.querySelector(`[data-filter="${filter}"]`);
    if (activeFilter) {
        activeFilter.classList.add('active');
    }
    
    // Reload data with filter
    loadDashboardData();
}

function handleDateChange(dateStr, picker) {
    // Handle date picker changes
    console.log('Date changed:', dateStr);
    loadDashboardData();
}

function refreshDashboard() {
    console.log('Refreshing dashboard...');
    loadDashboardData();
}

function showLoading() {
    const loadingElements = document.querySelectorAll('.loading');
    loadingElements.forEach(el => {
        el.style.display = 'block';
    });
}

function hideLoading() {
    const loadingElements = document.querySelectorAll('.loading');
    loadingElements.forEach(el => {
        el.style.display = 'none';
    });
}

function showError(message) {
    // Show error message to user
    const errorContainer = document.getElementById('error-message');
    if (errorContainer) {
        errorContainer.textContent = message;
        errorContainer.style.display = 'block';
        
        // Hide after 5 seconds
        setTimeout(() => {
            errorContainer.style.display = 'none';
        }, 5000);
    }
}
