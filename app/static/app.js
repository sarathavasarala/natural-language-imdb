// Professional IMDb Intelligence JavaScript

$(document).ready(function() {
    // console.log('=== DOCUMENT READY EVENT TRIGGERED ===');
    // console.log('IMDb Intelligence JavaScript loading...');
    // console.log('Current URL:', window.location.href);
    // console.log('DOM ready state:', document.readyState);
    // console.log('Page load time:', new Date().toISOString());
    
    // Initialize enhanced DataTable
    if ($('#resultsTable').length) {
        // console.log('Results table found, initializing DataTable...');
        initializeDataTable();
    } else {
        // console.log('No results table found');
    }
    
    // Initialize search form enhancements
    // console.log('Initializing search form...');
    initializeSearchForm();
    
    // Initialize tooltips
    // console.log('Initializing tooltips...');
    initializeTooltips();
    
    // Initialize SQL query collapse functionality
    // console.log('Initializing SQL collapse...');
    initializeSQLCollapse();
    
    // Initialize AI summary functionality
    // console.log('Initializing AI Summary...');
    initializeAISummary();
    
    // Check for AI summary buttons on the page
    const aiButtons = $('.ai-summary-btn');
    // console.log(`Found ${aiButtons.length} AI summary buttons on the page`);
    aiButtons.each(function(index) {
        const $btn = $(this);
        // console.log(`AI Button ${index + 1}:`, {
        //     titleId: $btn.data('title-id'),
        //     titleName: $btn.data('title-name'),
        //     element: $btn[0]
        // });
    });
    
    // Initialize AI Chat Interface (only on chat page)
    // console.log('Calling initializeChatInterface...');
    // initializeChatInterface(); // This will be called from the chat.html page
    
    console.log('✅ IMDb Intelligence initialized successfully'); // Keep one summary log
    // console.log('=== DOCUMENT READY INITIALIZATION COMPLETED ===');
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
                        // Use data-sort attribute if available (this is the most reliable method)
                        const $cell = $(table.find('tbody tr').eq(meta.row).find('td').eq(meta.col));
                        const sortValue = $cell.attr('data-sort');
                        if (sortValue !== undefined && sortValue !== '') {
                            const numericValue = parseFloat(sortValue);
                            return isNaN(numericValue) ? 0 : numericValue;
                        }
                        
                        // Fallback: extract numeric value from formatted text
                        if (columnName === 'votes') {
                            if (typeof data === 'string') {
                                const numMatch = data.match(/[\d,]+/);
                                return numMatch ? parseInt(numMatch[0].replace(/,/g, '')) : 0;
                            }
                        } else if (columnName === 'rating') {
                            if (typeof data === 'string') {
                                // Remove HTML tags and extract numeric value
                                const cleanText = data.replace(/<[^>]*>/g, '');
                                const numMatch = cleanText.match(/[\d.]+/);
                                return numMatch ? parseFloat(numMatch[0]) : 0;
                            }
                        }
                        
                        // Final fallback
                        const numericValue = parseFloat(data);
                        return isNaN(numericValue) ? 0 : numericValue;
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
    
    // console.log('DataTable initialized with enhanced numeric sorting');
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
        
        // console.log('Search initiated:', query);
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

// Add smooth scrolling for anchor links (excluding navigation links)
$(document).on('click', 'a[href^="#"]:not([onclick])', function(e) {
    e.preventDefault();
    const href = this.getAttribute('href');
    
    // Skip if href is just "#" or empty
    if (!href || href === '#') {
        return;
    }
    
    const target = $(href);
    if (target.length) {
        $('html, body').animate({
            scrollTop: target.offset().top - 80
        }, 600);
    }
});

// Performance monitoring
$(window).on('load', function() {
    const loadTime = window.performance.timing.domContentLoadedEventEnd - window.performance.timing.navigationStart;
    // console.log(`Page loaded in ${loadTime}ms`);
    
    // Track user interactions
    // $('button').click(function() {
    //     const element = $(this).text().trim();
    //     console.log('User interaction:', element);
    // });
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
    // console.log('Initializing AI Summary functionality...');
    
    // Handle AI summary button clicks
    $(document).on('click', '.ai-summary-btn', function(e) {
        e.preventDefault();
        e.stopPropagation();
        
        // console.log('AI Summary button clicked');
        
        const $btn = $(this);
        const titleId = $btn.data('title-id');
        const titleName = $btn.data('title-name');
        
        // console.log('Title ID:', titleId);
        // console.log('Title Name:', titleName);
        // console.log('Button data attributes:', $btn.data());
        
        if (!titleId || !titleName) {
            console.error('Missing title information - titleId:', titleId, 'titleName:', titleName);
            showAlert('Missing title information', 'error');
            return;
        }
        
        // console.log('Showing AI Summary modal...');
        
        // Show modal and start loading - using simpler Bootstrap method
        const $modal = $('#aiSummaryModal');
        // console.log('Modal element found:', $modal.length > 0);
        
        if ($modal.length === 0) {
            console.error('AI Summary modal not found in DOM');
            showAlert('Modal not found. Please refresh the page.', 'error');
            return;
        }
        
        // Use Bootstrap modal show method
        try {
            $modal.modal('show');
            // console.log('Modal shown successfully');
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
        
        // console.log('Generating AI summary for:', titleName, 'with ID:', titleId);
        
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
    // console.log('Starting AJAX request for AI summary...');
    // console.log('Request URL: /api/generate_summary');
    // console.log('Request data:', {
    //     title_id: titleId,
    //     title_name: titleName
    // });
    
    $.ajax({
        url: '/api/generate_summary',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            title_id: titleId,
            title_name: titleName
        }),
        timeout: 30000, // 30 second timeout
        beforeSend: function(xhr) {
            // console.log('Sending AJAX request...');
        },
        success: function(response) {
            // console.log('AI Summary API response received:', response);
            
            if (response.success) {
                // console.log('Summary generation successful');
                displayAISummary(response.title_name, response.summary, titleId, titleName);
            } else {
                console.error('Summary generation failed:', response.error);
                showAISummaryError(response.error || 'Unknown error occurred', titleId, titleName);
            }
        },
        error: function(xhr, status, error) {
            // console.error('AJAX request failed');
            // console.error('Status:', status);
            // console.error('Error:', error);
            // console.error('Response Text:', xhr.responseText);
            // console.error('Response Status:', xhr.status);
            // console.error('XHR object:', xhr);
            
            let errorMessage = 'Failed to generate summary';
            
            if (status === 'timeout') {
                errorMessage = 'Request timed out. Please try again.';
                // console.error('Request timed out after 30 seconds');
            } else if (xhr.responseJSON && xhr.responseJSON.error) {
                errorMessage = xhr.responseJSON.error;
                // console.error('Server returned error:', xhr.responseJSON.error);
            } else if (error) {
                errorMessage = error;
                // console.error('JavaScript error:', error);
            }
            
            console.error('Final error message for AI Summary:', errorMessage); // Keep one error log
            showAISummaryError(errorMessage, titleId, titleName);
        }
    });
}

function displayAISummary(titleName, summary, titleId, originalTitleName) {
    // console.log('Displaying AI summary for:', titleName);
    // console.log('Summary length:', summary.length, 'characters');
    
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
    
    // console.log('AI summary displayed successfully');
}

function showAISummaryError(errorMessage, titleId, titleName) {
    // console.error('Showing AI summary error:', errorMessage);
    
    $('#aiSummaryLoading').addClass('d-none');
    $('#aiSummaryContent').addClass('d-none');
    
    $('#aiSummaryErrorMessage').text(errorMessage);
    $('#aiSummaryError').removeClass('d-none');
    
    // Setup regenerate button
    $('#regenerateSummary')
        .data('title-id', titleId)
        .data('title-name', titleName)
        .show();
    
    // console.log('Error display complete');
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

// Chat Interface and Function Calling Implementation

// Global variables for chat functionality
let currentChart = null;
let chatHistory = [];
let chatInitialized = false;

// Initialize chat functionality
function initializeChatInterface() {
    if (chatInitialized) {
        return;
    }
    // console.log('=== initializeChatInterface() called ===');
    // console.log('DOM ready state:', document.readyState);
    // console.log('Page URL:', window.location.href);
    // console.log('Current time:', new Date().toISOString());
    
    const chatInput = $('#chatInput');
    const sendButton = $('#sendChatBtn');
    const chatMessages = $('#chatMessages');
    // const statusPanel = $('#statusPanel'); // statusPanel not used, can be removed if not planned
    
    // console.log('jQuery elements search results:');
    // console.log('- chatInput length:', chatInput.length);
    // console.log('- sendButton length:', sendButton.length);
    // console.log('- chatMessages length:', chatMessages.length);
    // console.log('- statusPanel length:', statusPanel.length);
    
    // Also check with vanilla JavaScript
    // const chatInputVanilla = document.getElementById('chatInput');
    // const sendButtonVanilla = document.getElementById('sendChatBtn');
    // const chatMessagesVanilla = document.getElementById('chatMessages');
    
    // console.log('Vanilla JS elements search results:');
    // console.log('- chatInput found:', !!chatInputVanilla);
    // console.log('- sendButton found:', !!sendButtonVanilla);
    // console.log('- chatMessages found:', !!chatMessagesVanilla);
    
    // Check if aiChatSection exists and its state
    // const aiChatSection = document.getElementById('aiChatSection');
    // console.log('aiChatSection found:', !!aiChatSection);
    // if (aiChatSection) {
        // console.log('aiChatSection classes:', aiChatSection.className);
        // console.log('aiChatSection visible:', !aiChatSection.classList.contains('d-none'));
        // console.log('aiChatSection innerHTML length:', aiChatSection.innerHTML.length);
    // }
    
    // Check if chat elements exist
    if (!chatInput.length || !sendButton.length || !chatMessages.length) {
        console.error('❌ Chat elements not found, skipping chat initialization'); // Keep error log
        // console.log('Missing elements details:');
        // if (!chatInput.length) console.log('- chatInput missing');
        // if (!sendButton.length) console.log('- sendButton missing');
        // if (!chatMessages.length) console.log('- chatMessages missing');
        return;
    }
    
    // console.log('✅ All chat elements found, proceeding with initialization');
    
    // Send message on button click
    sendButton.on('click', function() {
        // console.log('Send button clicked via jQuery event');
        sendChatMessage();
    });
    
    // Send message on Enter key press
    chatInput.on('keypress', function(e) {
        if (e.which === 13) { // Enter key
            // console.log('Enter key pressed in chat input');
            sendChatMessage();
        }
    });
    
    // console.log('✅ Chat event listeners attached successfully');
    // console.log('=== initializeChatInterface() completed ===');
    chatInitialized = true;
}

function sendChatMessage() {
    // console.log('=== sendChatMessage() called ===');
    
    const chatInput = $('#chatInput');
    const message = chatInput.val().trim();
    
    // console.log('Message from input:', message);
    // console.log('Message length:', message.length);
    
    if (!message) {
        // console.log('❌ Empty message, returning early');
        return;
    }
    
    // console.log('✅ Valid message, proceeding with chat');
    
    // Clear input and disable send button
    chatInput.val('');
    $('#sendChatBtn').prop('disabled', true);
    // console.log('Input cleared and button disabled');
    
    // Add user message to chat
    // console.log('Adding user message to chat');
    addMessageToChat('user', message);
    
    // Show typing indicator
    // console.log('Showing typing indicator');
    showTypingIndicator();
    
    // Send request to API
    // console.log('Sending AJAX request to /api/chat');
    // console.log('Request payload:', { query: message });
    
    $.ajax({
        url: '/api/chat',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            query: message
        }),
        beforeSend: function(xhr) {
            // console.log('AJAX request starting...');
            // console.log('Request headers:', xhr.getAllResponseHeaders());
        },
        success: function(response) {
            // console.log('✅ AJAX request successful');
            // console.log('Response:', response);
            hideTypingIndicator();
            
            if (response.success) {
                // console.log('Response indicates success');
                // Format and add AI response to chat
                const formattedResponse = formatAIResponse(response.ai_response);
                addMessageToChat('ai', formattedResponse);
                
                // Handle search results if present
                if (response.search_results && response.search_results.success && response.search_results.results.length > 0) {
                    // console.log('Displaying search results:', response.search_results.results.length, 'items');
                    displaySearchResults(response.search_results);
                }
                
                // Handle chart data if present
                if (response.chart_data && response.chart_data.success) {
                    // console.log('Displaying chart data');
                    displayChart(response.chart_data);
                }
            } else {
                console.error('❌ Chat API Response indicates failure:', response.error); // Keep error log
                addMessageToChat('ai', 'Sorry, I encountered an error processing your request: ' + (response.error || 'Unknown error'));
            }
        },
        error: function(xhr, status, error) {
            console.error('❌ Chat AJAX request failed. Status:', status, 'Error:', error, 'Response:', xhr.responseText); // Keep error log
            
            hideTypingIndicator();
            addMessageToChat('ai', 'Sorry, I\'m having trouble connecting right now. Please try again.');
        },
        complete: function() {
            // console.log('AJAX request completed, re-enabling send button');
            // Re-enable send button
            $('#sendChatBtn').prop('disabled', false);
            chatInput.focus();
        }
    });
    
    // console.log('=== sendChatMessage() setup completed ===');
}

function addMessageToChat(sender, content) {
    const chatMessages = $('#chatMessages');
    const timestamp = new Date().toLocaleTimeString();
    
    let messageHtml;
    
    if (sender === 'user') {
        messageHtml = `
            <div class="message user-message">
                <div class="message-avatar">
                    <i class="fas fa-user"></i>
                </div>
                <div class="message-content">
                    <strong>You</strong>
                    <small class="text-muted ms-2">${timestamp}</small>
                    <p>${escapeHtml(content)}</p>
                </div>
            </div>
        `;
    } else {
        messageHtml = `
            <div class="message ai-message">
                <div class="message-avatar">
                    <i class="fas fa-robot"></i>
                </div>
                <div class="message-content">
                    <strong>IMDb AI Assistant</strong>
                    <small class="text-muted ms-2">${timestamp}</small>
                    <div>${content}</div>
                </div>
            </div>
        `;
    }
    
    chatMessages.append(messageHtml);
    
    // Scroll to bottom
    scrollChatToBottom();
}

function showTypingIndicator() {
    const chatMessages = $('#chatMessages');
    const typingHtml = `
        <div class="message ai-message typing-indicator" id="typingIndicator">
            <div class="message-avatar">
                <i class="fas fa-robot"></i>
            </div>
            <div class="message-content">
                <strong>IMDb AI Assistant</strong>
                <div class="typing-dots">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
            </div>
        </div>
    `;
    
    chatMessages.append(typingHtml);
    scrollChatToBottom();
}

function hideTypingIndicator() {
    $('#typingIndicator').remove();
}

function scrollChatToBottom() {
    const chatMessages = $('#chatMessages');
    chatMessages.scrollTop(chatMessages[0].scrollHeight);
}

function displaySearchResults(searchResults) {
    const results = searchResults.results;
    const rowCount = searchResults.row_count;
    
    if (!results || results.length === 0) {
        return;
    }

    // Determine the type of results for smarter presentation
    const firstResult = results[0];
    const hasMovieData = 'title' in firstResult || 'primary_title' in firstResult;
    const hasPersonData = 'person_name' in firstResult || 'name' in firstResult;
    const hasRatings = 'average_rating' in firstResult || 'rating' in firstResult;
    const hasYears = 'premiered' in firstResult || 'year' in firstResult || 'start_year' in firstResult;
    
    // Create contextual results display
    let resultsHtml = `
        <div class="search-results-container mt-3">
            <div class="results-header mb-3">
                <h6 class="mb-2">
                    <i class="fas fa-list-ul me-2 text-primary"></i>
                    <span class="results-count badge bg-primary me-2">${rowCount}</span>
                    ${rowCount === 1 ? 'Result' : 'Results'} Found
                </h6>
            </div>
    `;

    // For movie/show results, show as cards for better visual appeal
    if (hasMovieData && results.length <= 6) {
        resultsHtml += '<div class="row g-3">';
        
        results.slice(0, 6).forEach((result, index) => {
            const title = result.title || result.primary_title || result.original_title || 'Unknown Title';
            const year = result.premiered || result.start_year || result.year || '';
            const rating = result.average_rating || result.rating || result.imdb_rating || '';
            const genres = result.genres || '';
            const type = result.title_type || 'Movie';
            
            resultsHtml += `
                <div class="col-md-6 col-lg-4">
                    <div class="card h-100 shadow-sm hover-card">
                        <div class="card-body p-3">
                            <h6 class="card-title text-primary mb-2" title="${escapeHtml(title)}">
                                ${escapeHtml(title.length > 40 ? title.substring(0, 40) + '...' : title)}
                            </h6>
                            <div class="movie-details">
                                ${year ? `<small class="text-muted d-block"><i class="fas fa-calendar me-1"></i>${escapeHtml(year)}</small>` : ''}
                                ${rating ? `<small class="text-warning d-block"><i class="fas fa-star me-1"></i>${escapeHtml(rating)}</small>` : ''}
                                ${genres ? `<small class="text-info d-block"><i class="fas fa-tags me-1"></i>${escapeHtml(genres.length > 30 ? genres.substring(0, 30) + '...' : genres)}</small>` : ''}
                                ${type ? `<span class="badge bg-secondary mt-1">${escapeHtml(type)}</span>` : ''}
                            </div>
                        </div>
                    </div>
                </div>
            `;
        });
        
        resultsHtml += '</div>';
        
        if (results.length > 6) {
            resultsHtml += `
                <div class="text-center mt-3">
                    <small class="text-muted">
                        <i class="fas fa-info-circle me-1"></i>
                        Showing first 6 of ${rowCount} results
                    </small>
                </div>
            `;
        }
    } 
    // For large datasets or person data, use compact table
    else {
        resultsHtml += `
            <div class="table-responsive">
                <table class="table table-sm table-hover">
                    <thead class="table-dark">
                        <tr>
        `;
        
        // Add headers
        const columns = Object.keys(results[0]);
        columns.forEach(col => {
            const displayCol = col.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
            resultsHtml += `<th class="fw-semibold">${escapeHtml(displayCol)}</th>`;
        });
        resultsHtml += '</tr></thead><tbody>';
        
        // Add rows (limit to first 10 for chat display)
        const displayResults = results.slice(0, 10);
        displayResults.forEach((row, index) => {
            resultsHtml += `<tr class="table-row-hover">`;
            columns.forEach(col => {
                let value = row[col];
                if (value === null || value === undefined || value === '') {
                    value = '—';
                } else if (col.includes('rating') && !isNaN(value)) {
                    value = `⭐ ${value}`;
                } else if (col.includes('year') && !isNaN(value)) {
                    value = `📅 ${value}`;
                }
                resultsHtml += `<td>${escapeHtml(String(value))}</td>`;
            });
            resultsHtml += '</tr>';
        });
        
        resultsHtml += '</tbody></table>';
        
        if (results.length > 10) {
            resultsHtml += `
                <div class="text-center mt-2">
                    <small class="text-muted">
                        <i class="fas fa-ellipsis-h me-1"></i>
                        Showing first 10 of ${rowCount} results
                    </small>
                </div>
            `;
        }
        
        resultsHtml += '</div>';
    }
    
    resultsHtml += '</div>';
    
    // Add to the last AI message
    const lastAiMessage = $('.message.ai-message').last().find('.message-content');
    lastAiMessage.append(resultsHtml);
}

function displayChart(chartData) {
    if (!chartData.success || !chartData.chart_data) {
        return;
    }
    
    const chartId = 'chat-chart-' + Date.now();
    const chartTitle = chartData.chart_data.options?.plugins?.title?.text || 'Data Visualization';
    
    // Create more engaging chart presentation
    const chartHtml = `
        <div class="chat-chart-container mt-4">
            <div class="chart-header mb-3">
                <h6 class="mb-1">
                    <i class="fas fa-chart-line me-2 text-primary"></i>
                    <span class="chart-title">${escapeHtml(chartTitle)}</span>
                </h6>
                <small class="text-muted">
                    <i class="fas fa-magic me-1"></i>Here's the visual breakdown you requested!
                </small>
            </div>
            <div class="chart-wrapper bg-white p-3 rounded shadow-sm border">
                <canvas id="${chartId}" width="400" height="250"></canvas>
            </div>
            <div class="chart-footer mt-2">
                <small class="text-muted">
                    <i class="fas fa-lightbulb me-1"></i>
                    <em>What patterns do you notice? Feel free to ask for more analysis!</em>
                </small>
            </div>
        </div>
    `;
    
    // Add to the last AI message
    const lastAiMessage = $('.message.ai-message').last().find('.message-content');
    lastAiMessage.append(chartHtml);
    
    // Initialize the chart with enhanced styling
    setTimeout(() => {
        const ctx = document.getElementById(chartId);
        if (ctx) {
            // Enhance chart configuration for better visual appeal
            const chartConfig = chartData.chart_data;
            if (chartConfig.options) {
                chartConfig.options.responsive = true;
                chartConfig.options.maintainAspectRatio = false;
                
                // Add subtle animations
                chartConfig.options.animation = {
                    duration: 1500,
                    easing: 'easeInOutQuart'
                };
                
                // Enhance grid styling
                if (chartConfig.options.scales) {
                    if (chartConfig.options.scales.y) {
                        chartConfig.options.scales.y.grid = {
                            color: 'rgba(0,0,0,0.05)',
                            lineWidth: 1
                        };
                    }
                    if (chartConfig.options.scales.x) {
                        chartConfig.options.scales.x.grid = {
                            display: false
                        };
                    }
                }
            }
            
            new Chart(ctx, chartConfig);
        }
    }, 100);
}

function escapeHtml(unsafe) {
    if (typeof unsafe !== 'string') {
        return unsafe;
    }
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Add click handlers for example cards in welcome message
$(document).on('click', '.example-card', function() {
    const exampleText = $(this).find('small').text().replace(/['"]/g, '');
    const chatInput = $('#chatInput');
    
    if (chatInput.length && exampleText) {
        chatInput.val(exampleText);
        chatInput.focus();
        
        // Add a subtle animation to indicate the text was added
        chatInput.addClass('example-filled');
        setTimeout(() => {
            chatInput.removeClass('example-filled');
        }, 1000);
    }
});

// Helper function to make AI responses feel more natural
function formatAIResponse(response) {
    // Add some personality to responses if they seem too robotic
    if (response && typeof response === 'string') {
        // Add conversational touches to common patterns
        response = response.replace(/^Here are the results:?/i, 'Here\'s what I found for you:');
        response = response.replace(/^The search returned/i, 'I discovered');
        response = response.replace(/Found (\d+) results?/i, 'Great! I found $1 matches');
        response = response.replace(/No results found/i, 'Hmm, I couldn\'t find anything matching that. Want to try a different search?');
    }
    return response;
}