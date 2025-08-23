function filterChanges() {
    console.log('Document type filter changed');
    
    const selected = Array.from(document.querySelectorAll('.doc-type-card input:checked')).map(cb => cb.value);
    console.log('Selected types:', selected);
    
    // Update UI to show selected cards
    document.querySelectorAll('.doc-type-card').forEach(card => {
        const input = card.querySelector('input');
        if (input.checked) {
            card.classList.add('selected');
        } else {
            card.classList.remove('selected');
        }
    });

    if (selected.length === 0) {
        console.log('No document types selected, loading all meetings');
        loadAvailableMeetings();
        return;
    }

    // Load filtered meetings
    console.log('Loading meetings for types:', selected);
    loadAvailableMeetings(selected);
}

function loadAvailableMeetings(docTypes = null) {
    console.log('Loading meetings, docTypes:', docTypes);
    
    const meeting1Select = document.getElementById('meeting1');
    const meeting2Select = document.getElementById('meeting2');
    const statusDiv = document.getElementById('status-message') || createStatusMessage();

    if (!meeting1Select || !meeting2Select) {
        console.error('Meeting select elements not found');
        return;
    }

    // Show loading status
    statusDiv.innerHTML = '<div class="status-message status-loading"><i class="bi bi-hourglass-split me-2"></i>Loading meetings...</div>';
    statusDiv.style.display = 'block';

    // Clear existing options
    clearSelectOptions([meeting1Select, meeting2Select]);

    let url = '/api/meetings';
    if (docTypes && docTypes.length > 0) {
        url += `?doc_types=${docTypes.join(',')}`;
    }

    console.log('🌐 Fetching:', url);

    fetch(url)
        .then(response => {
            console.log('📡 Response status:', response.status);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('📊 API Response:', data);
            
            if (!data.meetings || data.meetings.length === 0) {
                statusDiv.innerHTML = '<div class="status-message status-error"><i class="bi bi-exclamation-triangle me-2"></i>No meetings found for selected document types</div>';
                return;
            }

            // Populate both dropdowns with meetings data
            console.log('📝 Populating dropdowns with', data.meetings.length, 'meetings');
            data.meetings.forEach(meeting => {
                const formattedDate = formatMeetingDate(meeting.date);
                const optionText = `${formattedDate} (${meeting.count} documents)`;
                
                // Add to meeting1 select
                const option1 = new Option(optionText, meeting.date);
                option1.className = 'meeting-option';
                meeting1Select.add(option1);
                
                // Add to meeting2 select
                const option2 = new Option(optionText, meeting.date);
                option2.className = 'meeting-option';
                meeting2Select.add(option2);
            });

            // Update status
            const typeText = docTypes && docTypes.length > 0 ? 
                ` for ${docTypes.length} document type(s)` : '';
            statusDiv.innerHTML = `<div class="status-message status-loading"><i class="bi bi-check-circle me-2"></i>Loaded ${data.meetings.length} meetings${typeText}</div>`;
            
            // Auto-hide status after 2 seconds
            setTimeout(() => {
                statusDiv.style.display = 'none';
            }, 2000);

            // Enable compare button if both meetings can be selected
            updateCompareButtonState();
            console.log('✅ Meetings loaded successfully');
        })
        .catch(error => {
            console.error('❌ Error loading meetings:', error);
            statusDiv.innerHTML = `<div class="status-message status-error"><i class="bi bi-exclamation-triangle me-2"></i>Failed to load meetings: ${error.message}</div>`;
        });
}

function createStatusMessage() {
    const existing = document.getElementById('status-message');
    if (existing) return existing;
    
    const statusDiv = document.createElement('div');
    statusDiv.id = 'status-message';
    statusDiv.style.display = 'none';
    
    const controlPanel = document.querySelector('.control-panel');
    if (controlPanel) {
        controlPanel.appendChild(statusDiv);
    }
    
    return statusDiv;
}

function clearSelectOptions(selects) {
    selects.forEach(select => {
        // Clear all options except the first placeholder
        while (select.options.length > 1) {
            select.remove(1);
        }
        select.selectedIndex = 0;
    });
}

function formatMeetingDate(dateStr) {
    try {
        const date = new Date(dateStr + 'T00:00:00'); // Force local timezone
        const options = { 
            year: 'numeric', 
            month: 'long', 
            day: 'numeric',
            timeZone: 'UTC' // Ensure consistent formatting
        };
        return date.toLocaleDateString('en-US', options);
    } catch (e) {
        console.warn('Date formatting error:', e, 'for date:', dateStr);
        return dateStr; // Fallback to original string
    }
}

function updateCompareButtonState() {
    const meeting1 = document.getElementById('meeting1')?.value;
    const meeting2 = document.getElementById('meeting2')?.value;
    const compareBtn = document.getElementById('compare-btn');
    
    if (compareBtn) {
        const canCompare = meeting1 && meeting2 && meeting1 !== meeting2;
        compareBtn.disabled = !canCompare;
        
        if (canCompare) {
            compareBtn.innerHTML = '<i class="bi bi-graph-up me-2"></i>Compare Meetings';
        } else {
            compareBtn.innerHTML = '<i class="bi bi-hourglass-split me-2"></i>Select Two Different Meetings';
        }
    }
}

function setupComparisonListeners() {
    console.log('Setting up comparison listeners');
    
    // Document type filter listeners
    const docTypeInputs = document.querySelectorAll('.doc-type-card input[type="checkbox"]');
    docTypeInputs.forEach(input => {
        input.addEventListener('change', filterChanges);
    });
    
    // Meeting selection listeners
    const meeting1Select = document.getElementById('meeting1');
    const meeting2Select = document.getElementById('meeting2');
    
    if (meeting1Select) {
        meeting1Select.addEventListener('change', updateCompareButtonState);
    }
    
    if (meeting2Select) {
        meeting2Select.addEventListener('change', updateCompareButtonState);
    }
    
    // Compare button listener
    const compareBtn = document.getElementById('compare-btn');
    if (compareBtn) {
        compareBtn.addEventListener('click', function(e) {
            e.preventDefault();
            const meeting1 = meeting1Select?.value;
            const meeting2 = meeting2Select?.value;
            
            if (meeting1 && meeting2 && meeting1 !== meeting2) {
                performComparison(meeting1, meeting2);
            }
        });
    }
}

function performComparison(date1, date2) {
    console.log('Comparing meetings:', date1, 'vs', date2);
    
    const compareBtn = document.getElementById('compare-btn');
    const resultsDiv = document.getElementById('results');
    
    if (!resultsDiv) {
        console.error('Results div not found');
        return;
    }
    
    // Update button state
    if (compareBtn) {
        compareBtn.disabled = true;
        compareBtn.innerHTML = '<i class="bi bi-hourglass-split me-2"></i>Comparing...';
    }
    
    // Show loading in results
    resultsDiv.innerHTML = `
        <div class="text-center my-5">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <p class="mt-3">Analyzing meeting data...</p>
        </div>`;
    resultsDiv.style.display = 'block';
    
    // Perform comparison
    fetch('/compare', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: `meeting1=${encodeURIComponent(date1)}&meeting2=${encodeURIComponent(date2)}`
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        return response.text();
    })
    .then(html => {
        resultsDiv.innerHTML = html;
        
        // Scroll to results
        resultsDiv.scrollIntoView({ 
            behavior: 'smooth',
            block: 'start'
        });
    })
    .catch(error => {
        console.error('Comparison error:', error);
        resultsDiv.innerHTML = `
            <div class="alert alert-danger" role="alert">
                <i class="bi bi-exclamation-triangle me-2"></i>
                <strong>Error:</strong> Failed to compare meetings. ${error.message}
            </div>`;
    })
    .finally(() => {
        // Reset button
        if (compareBtn) {
            compareBtn.disabled = false;
            updateCompareButtonState();
        }
    });
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM loaded, initializing comparison page');
    setupComparisonListeners();
    loadAvailableMeetings(); // Load all meetings initially
});