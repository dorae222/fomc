// Chart configurations and utilities for FOMC Dashboard
class ChartManager {
    constructor() {
        this.defaultColors = {
            hawkish: '#d32f2f',
            dovish: '#1976d2',
            neutral: '#757575'
        };
    }

    // Create sentiment distribution pie chart
    createSentimentChart(containerId, data) {
        const ctx = document.getElementById(containerId).getContext('2d');
        return new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Hawkish', 'Dovish', 'Neutral'],
                datasets: [{
                    data: [data.hawkish, data.dovish, data.neutral],
                    backgroundColor: [
                        this.defaultColors.hawkish,
                        this.defaultColors.dovish,
                        this.defaultColors.neutral
                    ],
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });
    }

    // Create timeline chart
    createTimelineChart(containerId, data) {
        const ctx = document.getElementById(containerId).getContext('2d');
        return new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.dates,
                datasets: [
                    {
                        label: 'Hawkish',
                        data: data.hawkish,
                        borderColor: this.defaultColors.hawkish,
                        backgroundColor: this.defaultColors.hawkish + '20',
                        tension: 0.1
                    },
                    {
                        label: 'Dovish',
                        data: data.dovish,
                        borderColor: this.defaultColors.dovish,
                        backgroundColor: this.defaultColors.dovish + '20',
                        tension: 0.1
                    },
                    {
                        label: 'Neutral',
                        data: data.neutral,
                        borderColor: this.defaultColors.neutral,
                        backgroundColor: this.defaultColors.neutral + '20',
                        tension: 0.1
                    }
                ]
            },
            options: {
                responsive: true,
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 1
                    }
                },
                plugins: {
                    legend: {
                        position: 'top'
                    }
                }
            }
        });
    }

    // Create confidence chart
    createConfidenceChart(containerId, data) {
        const ctx = document.getElementById(containerId).getContext('2d');
        return new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.labels,
                datasets: [{
                    label: 'Average Confidence',
                    data: data.values,
                    backgroundColor: '#4caf50',
                    borderColor: '#388e3c',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 1
                    }
                }
            }
        });
    }
}

// Initialize chart manager
const chartManager = new ChartManager();
