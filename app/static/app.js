// Professional IMDb Intelligence JavaScript

$(document).ready(function() {
    // Initialize enhanced DataTable
    if ($('#resultsTable').length) {
        initializeDataTable();
    }
    
    // Initialize suggestion buttons
    initializeSuggestions();
    
    // Initialize search form enhancements
    initializeSearchForm();
    
    // Initialize tooltips
    initializeTooltips();
    
    // Initialize copy button functionality
    initializeCopyButtons();
    
    console.log('IMDb Intelligence initialized successfully');
});

function initializeDataTable() {
    $('#resultsTable').DataTable({
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
        columnDefs: [
            {
                targets: '_all',
                className: 'text-nowrap'
            }
        ],
        order: [], // No default ordering
        dom: '<"row"<"col-sm-12 col-md-6"l><"col-sm-12 col-md-6"f>>' +
             '<"row"<"col-sm-12"tr>>' +
             '<"row"<"col-sm-12 col-md-5"i><"col-sm-12 col-md-7"p>>',
        drawCallback: function(settings) {
            // Add fade-in animation to new rows
            $(this.api().table().node()).find('tbody tr').addClass('fade-in');
        }
    });
    
    console.log('DataTable initialized with advanced features');
}

function initializeSuggestions() {
    $('.suggestion-btn').click(function(e) {
        e.preventDefault();
        const query = $(this).data('query');
        
        // Animate button press
        $(this).addClass('btn-primary').removeClass('btn-outline-primary');
        setTimeout(() => {
            $(this).removeClass('btn-primary').addClass('btn-outline-primary');
        }, 200);
        
        // Update search input with animation
        const $input = $('#query');
        $input.val('').focus();
        
        // Type-writer effect
        typeWriterEffect($input[0], query, 50);
        
        console.log('Suggestion selected:', query);
    });
}

function typeWriterEffect(element, text, speed = 100) {
    let i = 0;
    element.value = '';
    
    function typeWriter() {
        if (i < text.length) {
            element.value += text.charAt(i);
            i++;
            setTimeout(typeWriter, speed);
        }
    }
    
    typeWriter();
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
    $('button, .suggestion-btn').click(function() {
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

function initializeCopyButtons() {
    // Handle copy SQL button clicks
    $(document).on('click', '.copy-sql-btn', function() {
        const sqlQuery = $(this).data('sql');
        copyToClipboard(sqlQuery);
    });
}