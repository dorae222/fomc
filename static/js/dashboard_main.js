// Global variables
let currentData = {};
let selectedMeeting = null;

// Initialize dashboard
function loadDashboard() {
    loadOverview();
    loadMeetingDates();
    setupEventListeners();
}

// Load overview statistics
async function loadOverview() {
    try {
    const typesSel = document.getElementById('doc-types-dashboard');
    const types = typesSel ? Array.from(typesSel.selectedOptions).map(o=>o.value).join(',') : '';
    const response = await fetch(`/api/overview${types ? `?doc_types=${encodeURIComponent(types)}` : ''}`);
        const data = await response.json();
        
        updateStatCards(data);
    renderTimelineChart(data.trend_data);
        renderSentimentPie(data.sentiment_distribution);
        
        currentData.overview = data;
    } catch (error) {
        console.error('Error loading overview:', error);
        showError('Failed to load overview data');
    }
}

// Update statistics cards
function updateStatCards(data) {
    const totalDocs = data.sentiment_distribution.reduce((sum, item) => sum + item.count, 0);
    const hawkishPct = calculatePercentage(data.sentiment_distribution, 'hawkish');
    const dovishPct = calculatePercentage(data.sentiment_distribution, 'dovish');
    const avgConfidence = calculateAvgConfidence(data.sentiment_distribution);
    
    animateNumber('total-docs', totalDocs);
    animateNumber('hawkish-pct', hawkishPct, '%');
    animateNumber('dovish-pct', dovishPct, '%');
    animateNumber('avg-confidence', avgConfidence, '%');
}

// Calculate percentage for sentiment
function calculatePercentage(distribution, sentiment) {
    const total = distribution.reduce((sum, item) => sum + item.count, 0);
    const sentimentCount = distribution.find(item => item.pred_label === sentiment)?.count || 0;
    return ((sentimentCount / total) * 100).toFixed(1);
}

// Calculate average confidence
function calculateAvgConfidence(distribution) {
    const weightedSum = distribution.reduce((sum, item) => sum + (item.avg_confidence * item.count), 0);
    const total = distribution.reduce((sum, item) => sum + item.count, 0);
    return ((weightedSum / total) * 100).toFixed(1);
}

// Animate number changes
function animateNumber(elementId, value, suffix = '') {
    const element = document.getElementById(elementId);
    const start = parseInt(element.textContent) || 0;
    const end = typeof value === 'string' ? parseFloat(value) : value;
    const duration = 1000;
    const startTime = performance.now();
    
    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const current = start + (end - start) * easeOutQuad(progress);
        
        element.textContent = current.toFixed(suffix === '%' ? 1 : 0) + suffix;
        
        if (progress < 1) {
            requestAnimationFrame(update);
        }
    }
    
    requestAnimationFrame(update);
}

// Easing function
function easeOutQuad(t) {
    return t * (2 - t);
}

// Load meeting dates for selector from official meetings API
async function loadMeetingDates() {
    try {
    const typesSel = document.getElementById('doc-types-dashboard');
    const types = typesSel ? Array.from(typesSel.selectedOptions).map(o=>o.value).join(',') : '';
    const response = await fetch(`/api/meetings${types ? `?doc_types=${encodeURIComponent(types)}` : ''}`);
        const data = await response.json();
        const dates = (data && data.dates) ? data.dates : [];
        const selector = document.getElementById('meeting-selector');
            selector.innerHTML = '<option value="">Select Meeting Date</option>';
            (dates || []).forEach(date => {
                const option = document.createElement('option');
                option.value = date;
                option.textContent = formatDate(date);
                selector.appendChild(option);
            });
    } catch (error) {
        console.error('Error loading meeting dates:', error);
    }
}

// Format date for display
function formatDate(dateStr) {
    const iso = normalizeDateString(dateStr);
    const date = new Date(iso);
    return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

// Normalize date strings to YYYY-MM-DD
function normalizeDateString(d) {
    if (!d) return d;
    if (/^\d{4}-\d{2}-\d{2}$/.test(d)) return d;
    const m1 = d.match(/^(\d{4})[\/](\d{1,2})[\/](\d{1,2})$/);
    if (m1) {
        const y = m1[1];
        const m = String(m1[2]).padStart(2, '0');
        const day = String(m1[3]).padStart(2, '0');
        return `${y}-${m}-${day}`;
    }
    const dt = new Date(d);
    if (!isNaN(dt.getTime())) {
        const y = dt.getFullYear();
        const m = String(dt.getMonth() + 1).padStart(2, '0');
        const day = String(dt.getDate()).padStart(2, '0');
        return `${y}-${m}-${day}`;
    }
    return d;
}

// Setup event listeners
function setupEventListeners() {
    // Meeting selector
    document.getElementById('meeting-selector').addEventListener('change', async (e) => {
        if (e.target.value) {
            await loadMeetingDetails(e.target.value);
        } else {
            document.getElementById('meeting-details').style.display = 'none';
        }
    });
    
    // Time range buttons
    document.querySelectorAll('[data-range]').forEach(button => {
        button.addEventListener('click', (e) => {
            document.querySelectorAll('[data-range]').forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            updateTimelineRange(e.target.dataset.range);
        });
    });
}

// Load meeting details
async function loadMeetingDetails(date) {
    try {
    const typesSel = document.getElementById('doc-types-dashboard');
    const types = typesSel ? Array.from(typesSel.selectedOptions).map(o=>o.value).join(',') : '';
    const response = await fetch(`/api/meeting/${date}${types ? `?doc_types=${encodeURIComponent(types)}` : ''}`);
        const data = await response.json();
        
        selectedMeeting = data;
        
        // Show details section
        document.getElementById('meeting-details').style.display = 'block';
        
        // Render charts
        renderSentimentFlow(data.sentences);
        renderConfidenceDistribution(data.sentences);
        
        // Display high confidence statements
        displayHighConfidenceStatements(data.high_confidence);
    // Load and render full text with color-coded sentiments
    await renderFullText(date, types);
        
    } catch (error) {
        console.error('Error loading meeting details:', error);
        showError('Failed to load meeting details');
    }
}

// Display high confidence statements
function displayHighConfidenceStatements(statements) {
    const container = document.getElementById('high-confidence-statements');
    container.innerHTML = '';
    
    statements.slice(0, 10).forEach(statement => {
        const item = document.createElement('div');
        item.className = `statement-item ${statement.pred_label} animate-slide-in`;
        
        const confidenceLevel = getConfidenceLevel(statement.max_prob);
        
        item.innerHTML = `
            <div class="statement-text">${statement.text.substring(0, 200)}...</div>
            <div class="statement-meta">
                <span class="sentiment-badge ${statement.pred_label}">${statement.pred_label}</span>
                <span class="confidence-pill confidence-${confidenceLevel}">
                    ${(statement.max_prob * 100).toFixed(1)}% confidence
                </span>
            </div>
        `;
        
        container.appendChild(item);
    });
}

// Get confidence level category
function getConfidenceLevel(prob) {
    if (prob > 0.8) return 'high';
    if (prob > 0.6) return 'medium';
    return 'low';
}

// Update timeline range
function updateTimelineRange(range) {
    if (!currentData.overview) return;
    
    const data = filterDataByRange(currentData.overview.trend_data, range);
    renderTimelineChart(data);
}

// Filter data by time range
function filterDataByRange(data, range) {
    const now = new Date();
    let startDate = new Date();
    
    switch(range) {
        case '1m':
            startDate.setMonth(now.getMonth() - 1);
            break;
        case '3m':
            startDate.setMonth(now.getMonth() - 3);
            break;
        case '6m':
            startDate.setMonth(now.getMonth() - 6);
            break;
        case '1y':
            startDate.setFullYear(now.getFullYear() - 1);
            break;
        case 'all':
            return data;
    }
    
    return data.filter(item => new Date(item.date) >= startDate);
}

// Show error message
function showError(message) {
    // Create toast notification
    const toast = document.createElement('div');
    toast.className = 'toast-notification error';
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => toast.remove(), 5000);
}

// Export for use in other modules
window.dashboardUtils = {
    loadDashboard,
    loadMeetingDetails,
    updateTimelineRange,
    formatDate,
    getConfidenceLevel
};

// Load recent changes (uses optional doc types from dashboard selector)
async function loadRecentChanges() {
    const tbody = document.getElementById('changes-tbody');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="5">Loading...</td></tr>';
    try {
        const sel = document.getElementById('doc-types-dashboard');
        const types = sel ? Array.from(sel.selectedOptions).map(o=>o.value).join(',') : '';
        const res = await fetch(`/api/recent-changes${types ? `?doc_types=${encodeURIComponent(types)}` : ''}`);
        const data = await res.json();
        const rows = [];
        const d1 = data.dates && data.dates[0] ? data.dates[0] : '';
        const d2 = data.dates && data.dates[1] ? data.dates[1] : '';
        const pushRow = (date, doc, change, conf, text) => {
            rows.push(`<tr>
                <td>${formatDate(date)}</td>
                <td>${doc}</td>
                <td>${change}</td>
                <td>${conf}</td>
                <td>${text}</td>
            </tr>`);
        };
        // Sentiment changed
        (data.changes?.sentiment_changed || []).forEach(c => {
            pushRow(d2, c.doc_type || '—', `${c.from_sentiment} → ${c.to_sentiment}`, `${(Math.abs(c.confidence_change)*100).toFixed(1)}%`, c.text);
        });
        // Added
        (data.changes?.added || []).forEach(c => {
            pushRow(d2, c.doc_type || '—', 'Added', `${(c.confidence*100).toFixed(1)}%`, c.text);
        });
        // Removed
        (data.changes?.removed || []).forEach(c => {
            pushRow(d1, c.doc_type || '—', 'Removed', `${(c.confidence*100).toFixed(1)}%`, c.text);
        });
        // Modified
        (data.changes?.modified || []).forEach(c => {
            pushRow(d2, c.doc_type || '—', `Modified (${(c.similarity*100).toFixed(0)}%)`, '', `${c.original} ⇄ ${c.modified}`);
        });
        tbody.innerHTML = rows.length ? rows.join('') : '<tr><td colspan="5">No recent changes found</td></tr>';
    } catch (e) {
        console.error('Failed to load recent changes', e);
        tbody.innerHTML = '<tr><td colspan="5">Failed to load</td></tr>';
    }
}

// Render full text viewer
async function renderFullText(date, typesCsv) {
    try {
        const url = `/api/fulltext/${date}${typesCsv ? `?doc_types=${encodeURIComponent(typesCsv)}` : ''}`;
        const res = await fetch(url);
        const data = await res.json();
        const container = document.getElementById('full-text-viewer');
        if (!container) return;
        container.innerHTML = '';
        data.forEach((s) => {
            const span = document.createElement('span');
            const prob = Number(s.max_prob || 0);
            const shade = Math.min(1, Math.max(0.2, prob));
            let color = '#95A5A6'; // neutral default
            if (s.pred_label === 'hawkish') color = '#FF6B6B';
            if (s.pred_label === 'dovish') color = '#4ECDC4';
            span.textContent = s.text + ' ';
            span.style.backgroundColor = hexToRgba(color, shade * 0.25);
            span.style.borderRadius = '4px';
            span.style.padding = '1px 2px';
            container.appendChild(span);
        });
    } catch (e) {
        console.error('Failed to render full text', e);
    }
}

function hexToRgba(hex, alpha) {
    const c = hex.replace('#','');
    const bigint = parseInt(c, 16);
    const r = (bigint >> 16) & 255;
    const g = (bigint >> 8) & 255;
    const b = bigint & 255;
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}