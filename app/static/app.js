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
    
    // // Initialize filters
    // initializeFilters();
    
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

// Filter functionality
let filterOptions = {};
let currentFilters = {};

// Initialize filters when document is ready
$(document).ready(function() {
    // Initialize filters
    initializeFilters();
});

function initializeFilters() {
    // Load filter options from API
    loadFilterOptions();
    
    // Setup range slider event handlers
    setupRangeSliders();
    
    // Setup filter button handlers
    setupFilterButtons();
    
    // Setup collapse animation
    setupCollapseAnimation();
}

// function loadFilterOptions() {
//     $.get('/api/filter-options')
//         .done(function(data) {
//             filterOptions = data;
//             populateFilterOptions();
//             console.log('Filter options loaded:', data);
//         })
//         .fail(function(xhr, status, error) {
//             console.error('Failed to load filter options:', error);
//             showNotification('Failed to load filter options', 'error');
//         });
// }

function populateFilterOptions() {
    // Update slider ranges
    $('#yearMin').attr('min', filterOptions.years.min).attr('max', filterOptions.years.max).val(filterOptions.years.min);
    $('#yearMax').attr('min', filterOptions.years.min).attr('max', filterOptions.years.max).val(filterOptions.years.max);
    $('#yearMinValue').text(filterOptions.years.min);
    $('#yearMaxValue').text(filterOptions.years.max);
    
    $('#ratingMin').attr('min', filterOptions.ratings.min).attr('max', filterOptions.ratings.max).val(filterOptions.ratings.min);
    $('#ratingMax').attr('min', filterOptions.ratings.min).attr('max', filterOptions.ratings.max).val(filterOptions.ratings.max);
    $('#ratingMinValue').text(filterOptions.ratings.min.toFixed(1));
    $('#ratingMaxValue').text(filterOptions.ratings.max.toFixed(1));
    
    $('#votesMin').attr('min', Math.log10(filterOptions.votes.min)).attr('max', Math.log10(filterOptions.votes.max)).val(Math.log10(filterOptions.votes.min));
    $('#votesMinValue').text(formatNumber(filterOptions.votes.min));
    
    // Populate genres
    const genreSelect = $('#genreSelect');
    genreSelect.empty();
    filterOptions.genres.forEach(genre => {
        genreSelect.append(`<option value="${genre}">${genre}</option>`);
    });
    
    // Populate types
    const typeSelect = $('#typeSelect');
    typeSelect.empty();
    filterOptions.types.forEach(type => {
        typeSelect.append(`<option value="${type}">${type}</option>`);
    });
}

function setupRangeSliders() {
    // Year sliders
    $('#yearMin, #yearMax').on('input', function() {
        const minVal = parseInt($('#yearMin').val());
        const maxVal = parseInt($('#yearMax').val());
        
        if (minVal >= maxVal) {
            if (this.id === 'yearMin') {
                $('#yearMax').val(minVal + 1);
            } else {
                $('#yearMin').val(maxVal - 1);
            }
        }
        
        $('#yearMinValue').text($('#yearMin').val());
        $('#yearMaxValue').text($('#yearMax').val());
    });
    
    // Rating sliders
    $('#ratingMin, #ratingMax').on('input', function() {
        const minVal = parseFloat($('#ratingMin').val());
        const maxVal = parseFloat($('#ratingMax').val());
        
        if (minVal >= maxVal) {
            if (this.id === 'ratingMin') {
                $('#ratingMax').val((minVal + 0.1).toFixed(1));
            } else {
                $('#ratingMin').val((maxVal - 0.1).toFixed(1));
            }
        }
        
        $('#ratingMinValue').text(parseFloat($('#ratingMin').val()).toFixed(1));
        $('#ratingMaxValue').text(parseFloat($('#ratingMax').val()).toFixed(1));
    });
    
    // Votes slider (logarithmic scale)
    $('#votesMin').on('input', function() {
        const logValue = parseFloat(this.value);
        const actualValue = Math.round(Math.pow(10, logValue));
        $('#votesMinValue').text(formatNumber(actualValue));
    });
}

function setupFilterButtons() {
    $('#applyFilters').on('click', function() {
        applyFilters();
    });
    
    $('#clearFilters').on('click', function() {
        clearFilters();
    });
}

function setupCollapseAnimation() {
    $('#advancedFilters').on('show.bs.collapse', function() {
        $('.toggle-icon').addClass('rotate');
    }).on('hide.bs.collapse', function() {
        $('.toggle-icon').removeClass('rotate');
    });
}

function applyFilters() {
    const filters = collectFilterValues();
    currentFilters = filters;
    
    // Show loading state
    showFilterLoading(true);
    
    // Send request to backend
    $.ajax({
        url: '/api/filtered-search',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(filters),
        success: function(response) {
            displayFilteredResults(response);
            showAppliedFilters(filters);
            showNotification(`Found ${response.count} results`, 'success');
        },
        error: function(xhr, status, error) {
            console.error('Filter search failed:', error);
            showNotification('Filter search failed: ' + error, 'error');
        },
        complete: function() {
            showFilterLoading(false);
        }
    });
}

function collectFilterValues() {
    const filters = {};
    
    // Year range
    const yearMin = parseInt($('#yearMin').val());
    const yearMax = parseInt($('#yearMax').val());
    if (yearMin > filterOptions.years.min || yearMax < filterOptions.years.max) {
        filters.yearMin = yearMin;
        filters.yearMax = yearMax;
    }
    
    // Rating range
    const ratingMin = parseFloat($('#ratingMin').val());
    const ratingMax = parseFloat($('#ratingMax').val());
    if (ratingMin > filterOptions.ratings.min || ratingMax < filterOptions.ratings.max) {
        filters.ratingMin = ratingMin;
        filters.ratingMax = ratingMax;
    }
    
    // Votes minimum
    const votesLogValue = parseFloat($('#votesMin').val());
    const votesMin = Math.round(Math.pow(10, votesLogValue));
    if (votesMin > filterOptions.votes.min) {
        filters.votesMin = votesMin;
        filters.votesMax = filterOptions.votes.max; // Set max to maximum available
    }
    
    // Genres
    const selectedGenres = $('#genreSelect').val();
    if (selectedGenres && selectedGenres.length > 0) {
        filters.genres = selectedGenres;
    }
    
    // Types
    const selectedTypes = $('#typeSelect').val();
    if (selectedTypes && selectedTypes.length > 0) {
        filters.types = selectedTypes;
    }
    
    // Text search
    const titleSearch = $('#titleSearch').val().trim();
    if (titleSearch) {
        filters.searchText = titleSearch;
    }
    
    return filters;
}

function displayFilteredResults(response) {
    // Hide any existing results
    $('#resultsSection').remove();
    
    if (response.results.length === 0) {
        const noResultsHtml = `
            <div id="resultsSection" class="filter-results-section">
                <div class="alert alert-info">
                    <i class="fas fa-info-circle me-2"></i>
                    No results found matching your criteria. Try adjusting your filters.
                </div>
            </div>
        `;
        $('.main-content').append(noResultsHtml);
        return;
    }
    
    // Create results table
    let tableHtml = `
        <div id="resultsSection" class="filter-results-section">
            <div class="card results-table">
                <div class="card-header bg-primary text-white d-flex justify-content-between align-items-center">
                    <span><i class="fas fa-table me-2"></i>Filter Results (${response.count} found)</span>
                    <button class="btn btn-sm btn-outline-light" id="exportResults">
                        <i class="fas fa-download me-1"></i>Export
                    </button>
                </div>
                <div class="card-body p-0">
                    <div class="table-responsive">
                        <table class="table table-hover mb-0" id="filteredResultsTable">
                            <thead>
                                <tr>
                                    <th>Title</th>
                                    <th>Type</th>
                                    <th>Year</th>
                                    <th>Genre</th>
                                    <th>Rating</th>
                                    <th>Votes</th>
                                    <th>Runtime</th>
                                </tr>
                            </thead>
                            <tbody>
    `;
    
    response.results.forEach(row => {
        tableHtml += `
            <tr>
                <td><strong>${escapeHtml(row.primary_title || 'N/A')}</strong></td>
                <td><span class="badge bg-secondary">${escapeHtml(row.type || 'N/A')}</span></td>
                <td>${row.premiered || 'N/A'}</td>
                <td>${escapeHtml(row.genres || 'N/A')}</td>
                <td>${row.rating ? `<span class="badge bg-warning text-dark">${row.rating}</span>` : 'N/A'}</td>
                <td>${row.votes ? formatNumber(row.votes) : 'N/A'}</td>
                <td>${row.runtime_minutes ? row.runtime_minutes + ' min' : 'N/A'}</td>
            </tr>
        `;
    });
    
    tableHtml += `
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    $('.main-content').append(tableHtml);
    
    // Initialize DataTable for filtered results
    $('#filteredResultsTable').DataTable({
        pageLength: 25,
        ordering: true,
        searching: true,
        responsive: true,
        language: {
            search: "Search results:",
            lengthMenu: "Show _MENU_ entries per page",
            info: "Showing _START_ to _END_ of _TOTAL_ results"
        }
    });
    
    // Scroll to results
    $('html, body').animate({
        scrollTop: $('#resultsSection').offset().top - 100
    }, 500);
}

function showAppliedFilters(filters) {
    let filtersHtml = '<div class="applied-filters mb-3"><h6>Applied Filters:</h6>';
    
    if (filters.yearMin || filters.yearMax) {
        filtersHtml += `<span class="filter-applied-badge">Years: ${filters.yearMin}-${filters.yearMax}</span>`;
    }
    if (filters.ratingMin || filters.ratingMax) {
        filtersHtml += `<span class="filter-applied-badge">Rating: ${filters.ratingMin}-${filters.ratingMax}</span>`;
    }
    if (filters.votesMin) {
        filtersHtml += `<span class="filter-applied-badge">Min Votes: ${formatNumber(filters.votesMin)}</span>`;
    }
    if (filters.genres) {
        filtersHtml += `<span class="filter-applied-badge">Genres: ${filters.genres.join(', ')}</span>`;
    }
    if (filters.types) {
        filtersHtml += `<span class="filter-applied-badge">Types: ${filters.types.join(', ')}</span>`;
    }
    if (filters.searchText) {
        filtersHtml += `<span class="filter-applied-badge">Title: "${filters.searchText}"</span>`;
    }
    
    filtersHtml += '</div>';
    
    $('#resultsSection').prepend(filtersHtml);
}

function clearFilters() {
    // Reset all sliders to their default values
    if (filterOptions) {
        $('#yearMin').val(filterOptions.years.min);
        $('#yearMax').val(filterOptions.years.max);
        $('#yearMinValue').text(filterOptions.years.min);
        $('#yearMaxValue').text(filterOptions.years.max);
        
        $('#ratingMin').val(filterOptions.ratings.min);
        $('#ratingMax').val(filterOptions.ratings.max);
        $('#ratingMinValue').text(filterOptions.ratings.min.toFixed(1));
        $('#ratingMaxValue').text(filterOptions.ratings.max.toFixed(1));
        
        $('#votesMin').val(Math.log10(filterOptions.votes.min));
        $('#votesMinValue').text(formatNumber(filterOptions.votes.min));
    }
    
    // Clear select boxes
    $('#genreSelect').val([]);
    $('#typeSelect').val([]);
    $('#titleSearch').val('');
    
    // Remove filter results and applied filters display
    $('#resultsSection').remove();
    $('.applied-filters').remove();
    
    // Clear current filters
    currentFilters = {};
    
    showNotification('Filters cleared', 'info');
}

function showFilterLoading(show) {
    if (show) {
        $('#applyFilters').prop('disabled', true).html('<i class="fas fa-spinner fa-spin me-2"></i>Applying...');
        $('.filters-section .card').addClass('filter-loading');
    } else {
        $('#applyFilters').prop('disabled', false).html('<i class="fas fa-search me-2"></i>Apply Filters');
        $('.filters-section .card').removeClass('filter-loading');
    }
}

function showNotification(message, type = 'info') {
    const alertClass = type === 'error' ? 'alert-danger' : (type === 'success' ? 'alert-success' : 'alert-info');
    const iconClass = type === 'error' ? 'fa-exclamation-triangle' : (type === 'success' ? 'fa-check-circle' : 'fa-info-circle');
    
    const notification = $(`
        <div class="alert ${alertClass} alert-dismissible fade show notification-toast" role="alert">
            <i class="fas ${iconClass} me-2"></i>
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `);
    
    // Remove existing notifications
    $('.notification-toast').remove();
    
    // Add new notification
    $('.main-content').prepend(notification);
    
    // Auto-hide after 5 seconds
    setTimeout(() => {
        notification.fadeOut();
    }, 5000);
}

function formatNumber(num) {
    if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}