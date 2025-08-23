// Chart configurations and rendering functions

// Render timeline chart
function renderTimelineChart(data) {
    // Process data for stacked area chart
    const dates = [...new Set(data.map(d => d.date))].sort();
    const sentiments = ['hawkish', 'neutral', 'dovish'];
    
    const traces = sentiments.map(sentiment => {
        const values = dates.map(date => {
            const items = data.filter(d => d.date === date && d.pred_label === sentiment);
            const total = data.filter(d => d.date === date).length;
            return total > 0 ? (items.length / total) * 100 : 0;
        });
        
        return {
            x: dates,
            y: values,
            name: sentiment.charAt(0).toUpperCase() + sentiment.slice(1),
            type: 'scatter',
            mode: 'lines',
            stackgroup: 'one',
            fillcolor: getColor(sentiment),
            line: { color: getColor(sentiment), width: 0.5 }
        };
    });
    
    const layout = {
        title: '',
        xaxis: { title: 'Date', showgrid: false },
        yaxis: { title: 'Percentage (%)', ticksuffix: '%', range: [0, 100] },
        hovermode: 'x unified',
        showlegend: true,
        legend: { orientation: 'h', y: -0.2 },
        margin: { t: 20, b: 60 },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)'
    };
    
    Plotly.newPlot('timeline-chart', traces, layout, {responsive: true});
}

// Render sentiment pie chart
function renderSentimentPie(data) {
    const trace = {
        values: data.map(d => d.count),
        labels: data.map(d => d.pred_label.charAt(0).toUpperCase() + d.pred_label.slice(1)),
        type: 'pie',
        hole: 0.4,
        marker: {
            colors: data.map(d => getColor(d.pred_label))
        },
        textposition: 'inside',
        textinfo: 'label+percent'
    };
    
    const layout = {
        title: '',
        showlegend: false,
        margin: { t: 20, b: 20 },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)'
    };
    
    Plotly.newPlot('sentiment-pie', [trace], layout, {responsive: true});
}

// Render sentiment flow chart
function renderSentimentFlow(sentences) {
    const traces = [];
    const sentiments = ['hawkish', 'neutral', 'dovish'];
    
    // Create scatter plot for each sentiment
    sentiments.forEach(sentiment => {
        const filtered = sentences.filter(s => s.pred_label === sentiment);
        
        traces.push({
            x: filtered.map(s => s.sentence_id || sentences.indexOf(s)),
            y: filtered.map(s => s.max_prob),
            mode: 'markers',
            name: sentiment.charAt(0).toUpperCase() + sentiment.slice(1),
            marker: {
                size: filtered.map(s => s.max_prob * 15),
                color: getColor(sentiment),
                opacity: 0.6,
                line: { width: 1, color: 'white' }
            },
            text: filtered.map(s => s.text.substring(0, 100) + '...'),
            hovertemplate: '%{text}<br>Confidence: %{y:.1%}<extra></extra>'
        });
    });
    
    // Add rolling average lines
    const windowSize = 10;
    sentiments.forEach(sentiment => {
        const rolling = calculateRollingAverage(sentences, sentiment, windowSize);
        
        traces.push({
            x: rolling.x,
            y: rolling.y,
            mode: 'lines',
            name: `${sentiment} trend`,
            line: {
                color: getColor(sentiment),
                width: 2,
                dash: 'dash'
            },
            showlegend: false,
            hoverinfo: 'skip'
        });
    });
    
    const layout = {
        title: 'Sentiment Flow Through Document',
        xaxis: { title: 'Sentence Position' },
        yaxis: { title: 'Confidence', tickformat: '.0%' },
        hovermode: 'closest',
        showlegend: true,
        legend: { orientation: 'h', y: -0.15 },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(248,249,250,0.5)'
    };
    
    Plotly.newPlot('sentiment-flow', traces, layout, {responsive: true});
}

// Render confidence distribution
function renderConfidenceDistribution(sentences) {
    const sentiments = ['hawkish', 'neutral', 'dovish'];
    const traces = [];
    
    sentiments.forEach(sentiment => {
        const values = sentences
            .filter(s => s.pred_label === sentiment)
            .map(s => s.max_prob);
        
        traces.push({
            y: values,
            type: 'box',
            name: sentiment.charAt(0).toUpperCase() + sentiment.slice(1),
            marker: { color: getColor(sentiment) },
            boxpoints: 'outliers'
        });
    });
    
    const layout = {
        title: 'Confidence Distribution by Sentiment',
        yaxis: { title: 'Confidence', tickformat: '.0%' },
        showlegend: false,
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(248,249,250,0.5)'
    };
    
    Plotly.newPlot('confidence-distribution', traces, layout, {responsive: true});
}

// Calculate rolling average
function calculateRollingAverage(sentences, sentiment, windowSize) {
    const x = [];
    const y = [];
    
    for (let i = 0; i < sentences.length; i++) {
        const start = Math.max(0, i - Math.floor(windowSize / 2));
        const end = Math.min(sentences.length, i + Math.floor(windowSize / 2) + 1);
        const window = sentences.slice(start, end);
        
        const sentimentCount = window.filter(s => s.pred_label === sentiment).length;
        const avg = sentimentCount / window.length;
        
        x.push(i);
        y.push(avg);
    }
    
    return { x, y };
}

// Get color for sentiment
function getColor(sentiment) {
    const colors = {
        hawkish: '#FF6B6B',
        neutral: '#95A5A6',
        dovish: '#4ECDC4'
    };
    return colors[sentiment] || '#95A5A6';
}

// Export functions
window.chartFunctions = {
    renderTimelineChart,
    renderSentimentPie,
    renderSentimentFlow,
    renderConfidenceDistribution
};