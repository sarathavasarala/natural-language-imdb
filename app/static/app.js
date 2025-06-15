// Professional IMDb Intelligence JavaScript

$(document).ready(function() {
    console.log('IMDb Intelligence JavaScript loading...');
    
    // Initialize enhanced DataTable
    if ($('#resultsTable').length) {
        console.log('Results table found, initializing DataTable...');
        initializeDataTable();
    } else {
        console.log('No results table found');
    }
    
    // Initialize search form enhancements
    console.log('Initializing search form...');
    initializeSearchForm();
    
    // Initialize tooltips
    console.log('Initializing tooltips...');
    initializeTooltips();
    
    // Initialize SQL query collapse functionality
    console.log('Initializing SQL collapse...');
    initializeSQLCollapse();
    
    // Initialize AI summary functionality
    console.log('Initializing AI Summary...');
    initializeAISummary();
    
    // Check for AI summary buttons on the page
    const aiButtons = $('.ai-summary-btn');
    console.log(`Found ${aiButtons.length} AI summary buttons on the page`);
    aiButtons.each(function(index) {
        const $btn = $(this);
        console.log(`AI Button ${index + 1}:`, {
            titleId: $btn.data('title-id'),
            titleName: $btn.data('title-name'),
            element: $btn[0]
        });
    });
    
    console.log('IMDb Intelligence initialized successfully');
});

function initializeDataTable() {
    // First, determine which columns are numeric based on their headers
    const table = $('#resultsTable');
    const columnDefs = [];
    let votesColumnIndex = -1;
    
    // Find numeric columns and set up proper sorting
    table.find('thead th').each(function(index) {
        const $th = $(this);
        const columnName = $th.data('column');
        const isNumeric = $th.data('type') === 'numeric';
        
        // Track votes column index for default sorting
        if (columnName === 'votes') {
            votesColumnIndex = index;
        }
        
        if (isNumeric) {
            columnDefs.push({
                targets: index,
                type: 'num',
                render: function(data, type, row, meta) {
                    if (type === 'sort' || type === 'type') {
                        // Use data-sort attribute if available
                        const $cell = $(table.find('tbody tr').eq(meta.row).find('td').eq(meta.col));
                        const sortValue = $cell.attr('data-sort');
                        if (sortValue !== undefined) {
                            return parseFloat(sortValue) || 0;
                        }
                        
                        // Fallback: extract numeric value from formatted text
                        if (columnName === 'votes') {
                            if (typeof data === 'string') {
                                const numMatch = data.match(/[\d,]+/);
                                return numMatch ? parseInt(numMatch[0].replace(/,/g, '')) : 0;
                            }
                        } else if (columnName === 'rating') {
                            if (typeof data === 'string') {
                                const numMatch = data.match(/[\d.]+/);
                                return numMatch ? parseFloat(numMatch[0]) : 0;
                            }
                        }
                        return parseFloat(data) || 0;
                    }
                    return data; // Return original data for display
                }
            });
        }
        
        // Add text-nowrap to all columns
        columnDefs.push({
            targets: index,
            className: 'text-nowrap'
        });
    });
    
    table.DataTable({
        pageLength: 25,
        ordering: true,
        searching: true,
        responsive: true,
        stateSave: true,
        language: {
            search: "Filter results:",
            lengthMenu: "Show _MENU_ entries per page",
            info: "Showing _START_ to _END_ of _TOTAL_ results",
            paginate: {
                first: "First",
                last: "Last",
                next: "Next →",
                previous: "← Previous"
            },
            emptyTable: "No matching results found",
            zeroRecords: "No matching results found"
        },
        columnDefs: columnDefs,
        order: votesColumnIndex >= 0 ? [[votesColumnIndex, 'desc']] : [], // Default sort by votes desc if available
        dom: '<"row"<"col-sm-12 col-md-6"l><"col-sm-12 col-md-6"f>>' +
             '<"row"<"col-sm-12"tr>>' +
             '<"row"<"col-sm-12 col-md-5"i><"col-sm-12 col-md-7"p>>',
        drawCallback: function(settings) {
            // Add fade-in animation to new rows
            $(this.api().table().node()).find('tbody tr').addClass('fade-in');
        }
    });
    
    console.log('DataTable initialized with enhanced numeric sorting');
}

function initializeSearchForm() {
    const $form = $('form[method="POST"]');
    const $searchBtn = $('#searchBtn');
    const $loadingState = $('#loadingState');
    
    // Enhanced form submission
    $form.submit(function(e) {
        const query = $('#query').val().trim();
        
        if (!query) {
            e.preventDefault();
            showAlert('Please enter a search query.', 'warning');
            return;
        }
        
        // Show loading state
        $searchBtn.prop('disabled', true).html('<i class="fas fa-spinner fa-spin me-2"></i>Searching...');
        $loadingState.removeClass('d-none').addClass('fade-in');
        
        // Store query in localStorage for history
        addToQueryHistory(query);
        
        console.log('Search initiated:', query);
    });
    
    // Auto-save draft queries
    $('#query').on('input', debounce(function() {
        const query = $(this).val();
        if (query.length > 3) {
            localStorage.setItem('draftQuery', query);
        }
    }, 500));
    
    // Restore draft query on page load
    const draftQuery = localStorage.getItem('draftQuery');
    if (draftQuery && !$('#query').val()) {
        $('#query').val(draftQuery);
    }
    
    // Add keyboard shortcuts
    $('#query').keydown(function(e) {
        // Ctrl/Cmd + Enter to submit
        if ((e.ctrlKey || e.metaKey) && e.keyCode === 13) {
            $form.submit();
        }
        
        // Escape to clear
        if (e.keyCode === 27) {
            $(this).val('').focus();
        }
    });
}

function initializeTooltips() {
    // Initialize Bootstrap tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

function addToQueryHistory(query) {
    let history = JSON.parse(localStorage.getItem('queryHistory') || '[]');
    
    // Remove duplicate if exists
    history = history.filter(item => item.query !== query);
    
    // Add to beginning
    history.unshift({
        query: query,
        timestamp: Date.now()
    });
    
    // Keep only last 10 queries
    history = history.slice(0, 10);
    
    localStorage.setItem('queryHistory', JSON.stringify(history));
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(function() {
        showAlert('SQL query copied to clipboard!', 'success', 2000);
    }).catch(function(err) {
        console.error('Could not copy text: ', err);
        showAlert('Failed to copy to clipboard', 'error', 3000);
    });
}

function showAlert(message, type = 'info', duration = 5000) {
    const alertClass = {
        'success': 'alert-success',
        'error': 'alert-danger',
        'warning': 'alert-warning',
        'info': 'alert-info'
    }[type] || 'alert-info';
    
    const icon = {
        'success': 'fas fa-check-circle',
        'error': 'fas fa-exclamation-triangle',
        'warning': 'fas fa-exclamation-circle',
        'info': 'fas fa-info-circle'
    }[type] || 'fas fa-info-circle';
    
    const alertHtml = `
        <div class="alert ${alertClass} alert-dismissible fade show position-fixed" 
             style="top: 20px; right: 20px; z-index: 9999; min-width: 300px;" role="alert">
            <i class="${icon} me-2"></i>
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    
    $('body').append(alertHtml);
    
    // Auto-dismiss after duration
    setTimeout(() => {
        $('.alert').not('[data-bs-dismiss]').fadeOut(300, function() {
            $(this).remove();
        });
    }, duration);
}

// Utility function for debouncing
function debounce(func, wait, immediate) {
    let timeout;
    return function() {
        const context = this, args = arguments;
        const later = function() {
            timeout = null;
            if (!immediate) func.apply(context, args);
        };
        const callNow = immediate && !timeout;
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
        if (callNow) func.apply(context, args);
    };
}

// Add smooth scrolling for anchor links
$(document).on('click', 'a[href^="#"]', function(e) {
    e.preventDefault();
    const target = $(this.getAttribute('href'));
    if (target.length) {
        $('html, body').animate({
            scrollTop: target.offset().top - 80
        }, 600);
    }
});

// Performance monitoring
$(window).on('load', function() {
    const loadTime = window.performance.timing.domContentLoadedEventEnd - window.performance.timing.navigationStart;
    console.log(`Page loaded in ${loadTime}ms`);
    
    // Track user interactions
    $('button').click(function() {
        const element = $(this).text().trim();
        console.log('User interaction:', element);
    });
});

// Add visual feedback for form validation
$('#query').on('blur', function() {
    const $this = $(this);
    const value = $this.val().trim();
    
    if (value.length > 0 && value.length < 5) {
        $this.addClass('is-invalid');
        if (!$this.next('.invalid-feedback').length) {
            $this.after('<div class="invalid-feedback">Query seems too short. Try being more specific.</div>');
        }
    } else {
        $this.removeClass('is-invalid');
        $this.next('.invalid-feedback').remove();
    }
});

// Enhanced error handling
window.addEventListener('error', function(e) {
    console.error('JavaScript error:', e.error);
    showAlert('An unexpected error occurred. Please refresh the page.', 'error');
});

// Add loading animation for IMDB links
$(document).on('click', 'a[href*="imdb.com"]', function() {
    const $this = $(this);
    const originalText = $this.html();
    
    $this.html('<i class="fas fa-spinner fa-spin"></i> Loading...');
    
    setTimeout(() => {
        $this.html(originalText);
    }, 1000);
});

function initializeSQLCollapse() {
    // Handle SQL query collapse toggle
    $('#sqlQueryCollapse').on('shown.bs.collapse', function() {
        $('.toggle-icon').addClass('rotated');
    });
    
    $('#sqlQueryCollapse').on('hidden.bs.collapse', function() {
        $('.toggle-icon').removeClass('rotated');
    });
}

function initializeAISummary() {
    console.log('Initializing AI Summary functionality...');
    
    // Handle AI summary button clicks
    $(document).on('click', '.ai-summary-btn', function(e) {
        e.preventDefault();
        e.stopPropagation();
        
        console.log('AI Summary button clicked');
        
        const $btn = $(this);
        const titleId = $btn.data('title-id');
        const titleName = $btn.data('title-name');
        
        console.log('Title ID:', titleId);
        console.log('Title Name:', titleName);
        console.log('Button data attributes:', $btn.data());
        
        if (!titleId || !titleName) {
            console.error('Missing title information - titleId:', titleId, 'titleName:', titleName);
            showAlert('Missing title information', 'error');
            return;
        }
        
        console.log('Showing AI Summary modal...');
        
        // Show modal and start loading - using simpler Bootstrap method
        const $modal = $('#aiSummaryModal');
        console.log('Modal element found:', $modal.length > 0);
        
        if ($modal.length === 0) {
            console.error('AI Summary modal not found in DOM');
            showAlert('Modal not found. Please refresh the page.', 'error');
            return;
        }
        
        // Use Bootstrap modal show method
        try {
            $modal.modal('show');
            console.log('Modal shown successfully');
        } catch (modalError) {
            console.error('Error showing modal:', modalError);
            showAlert('Failed to show modal', 'error');
            return;
        }
        
        // Reset modal state
        $('#aiSummaryLoading').removeClass('d-none');
        $('#aiSummaryContent').addClass('d-none');
        $('#aiSummaryError').addClass('d-none');
        $('#regenerateSummary').hide();
        
        console.log('Generating AI summary for:', titleName, 'with ID:', titleId);
        
        // Generate summary
        generateAISummary(titleId, titleName);
    });
    
    // Handle regenerate button
    $('#regenerateSummary').click(function() {
        const titleId = $(this).data('title-id');
        const titleName = $(this).data('title-name');
        
        if (titleId && titleName) {
            $('#aiSummaryLoading').removeClass('d-none');
            $('#aiSummaryContent').addClass('d-none');
            $('#aiSummaryError').addClass('d-none');
            $(this).hide();
            
            generateAISummary(titleId, titleName);
        }
    });
}

function generateAISummary(titleId, titleName) {
    console.log('Starting AJAX request for AI summary...');
    console.log('Request URL: /api/generate-summary');
    console.log('Request data:', {
        title_id: titleId,
        title_name: titleName
    });
    
    $.ajax({
        url: '/api/generate-summary',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            title_id: titleId,
            title_name: titleName
        }),
        timeout: 30000, // 30 second timeout
        beforeSend: function(xhr) {
            console.log('Sending AJAX request...');
        },
        success: function(response) {
            console.log('AI Summary API response received:', response);
            
            if (response.success) {
                console.log('Summary generation successful');
                displayAISummary(response.title_name, response.summary, titleId, titleName);
            } else {
                console.error('Summary generation failed:', response.error);
                showAISummaryError(response.error || 'Unknown error occurred', titleId, titleName);
            }
        },
        error: function(xhr, status, error) {
            console.error('AJAX request failed');
            console.error('Status:', status);
            console.error('Error:', error);
            console.error('Response Text:', xhr.responseText);
            console.error('Response Status:', xhr.status);
            console.error('XHR object:', xhr);
            
            let errorMessage = 'Failed to generate summary';
            
            if (status === 'timeout') {
                errorMessage = 'Request timed out. Please try again.';
                console.error('Request timed out after 30 seconds');
            } else if (xhr.responseJSON && xhr.responseJSON.error) {
                errorMessage = xhr.responseJSON.error;
                console.error('Server returned error:', xhr.responseJSON.error);
            } else if (error) {
                errorMessage = error;
                console.error('JavaScript error:', error);
            }
            
            console.error('Final error message:', errorMessage);
            showAISummaryError(errorMessage, titleId, titleName);
        }
    });
}

function displayAISummary(titleName, summary, titleId, originalTitleName) {
    console.log('Displaying AI summary for:', titleName);
    console.log('Summary length:', summary.length, 'characters');
    
    $('#aiSummaryLoading').addClass('d-none');
    $('#aiSummaryError').addClass('d-none');
    
    $('#aiSummaryTitle').text(titleName);
    $('#aiSummaryText').html(formatSummaryText(summary));
    $('#aiSummaryContent').removeClass('d-none');
    
    // Setup regenerate button
    $('#regenerateSummary')
        .data('title-id', titleId)
        .data('title-name', originalTitleName)
        .show();
    
    console.log('AI summary displayed successfully');
}

function showAISummaryError(errorMessage, titleId, titleName) {
    console.error('Showing AI summary error:', errorMessage);
    
    $('#aiSummaryLoading').addClass('d-none');
    $('#aiSummaryContent').addClass('d-none');
    
    $('#aiSummaryErrorMessage').text(errorMessage);
    $('#aiSummaryError').removeClass('d-none');
    
    // Setup regenerate button
    $('#regenerateSummary')
        .data('title-id', titleId)
        .data('title-name', titleName)
        .show();
    
    console.log('Error display complete');
}

function formatSummaryText(summary) {
    // Since the AI now generates HTML, we need to handle it properly
    // First, clean up any potential issues and ensure proper formatting
    
    // Remove any markdown artifacts that might slip through
    let formattedText = summary
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') // Convert **text** to <strong>text</strong>
        .replace(/\*(.*?)\*/g, '<em>$1</em>') // Convert *text* to <em>text</em>
        .replace(/#{1,6}\s(.+)/g, '<strong>$1</strong>') // Convert ### Header to <strong>Header</strong>
        .trim();
    
    // If the text doesn't already have paragraph tags, wrap sections in paragraphs
    if (!formattedText.includes('<p>')) {
        // Split by double line breaks and wrap each section in <p> tags
        formattedText = formattedText
            .split(/\n\s*\n/)
            .map(section => section.trim())
            .filter(section => section.length > 0)
            .map(section => `<p>${section.replace(/\n/g, '<br>')}</p>`)
            .join('');
    } else {
        // If already has paragraph tags, just clean up line breaks
        formattedText = formattedText.replace(/\n/g, ' ');
    }
    
    return formattedText;
}