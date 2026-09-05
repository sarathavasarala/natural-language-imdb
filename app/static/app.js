// ═══════════════════════════════════════════════════════════════════
// IMDb Intelligence — Digital Command Console Frontend Logic
// ═══════════════════════════════════════════════════════════════════

// ── Global AJAX Setup for Client-Side Azure OpenAI Credentials ────
$.ajaxSetup({
    beforeSend: function (xhr) {
        const customKey = localStorage.getItem('imdb_azure_api_key');
        const customEndpoint = localStorage.getItem('imdb_azure_endpoint');
        const customModel = localStorage.getItem('imdb_azure_model');
        const customVersion = localStorage.getItem('imdb_azure_api_version');

        if (customKey && customKey.trim()) {
            xhr.setRequestHeader('X-Azure-API-Key', customKey.trim());
        }
        if (customEndpoint && customEndpoint.trim()) {
            xhr.setRequestHeader('X-Azure-Endpoint', customEndpoint.trim());
        }
        if (customModel && customModel.trim()) {
            xhr.setRequestHeader('X-Azure-Model', customModel.trim());
        }
        if (customVersion && customVersion.trim()) {
            xhr.setRequestHeader('X-Azure-API-Version', customVersion.trim());
        }
    }
});

// ── Settings & Credentials Manager ────────────────────────────────
function initializeSettingsModal() {
    const $modal = $('#settingsModal');
    if (!$modal.length) return;

    // Populate inputs from LocalStorage
    $('#customApiKey').val(localStorage.getItem('imdb_azure_api_key') || '');
    $('#customEndpoint').val(localStorage.getItem('imdb_azure_endpoint') || '');
    $('#customModel').val(localStorage.getItem('imdb_azure_model') || '');
    $('#customApiVersion').val(localStorage.getItem('imdb_azure_api_version') || '');

    updateSettingsBadge();

    // Toggle API Key visibility
    $('#toggleApiKeyVisibility').on('click', function () {
        const $input = $('#customApiKey');
        const $icon = $('#toggleApiKeyIcon');
        if ($input.attr('type') === 'password') {
            $input.attr('type', 'text');
            $icon.removeClass('fa-eye').addClass('fa-eye-slash');
        } else {
            $input.attr('type', 'password');
            $icon.removeClass('fa-eye-slash').addClass('fa-eye');
        }
    });

    // Save Settings
    $('#saveSettingsBtn').on('click', function () {
        let key = $('#customApiKey').val().trim().replace(/^["']|["']$/g, '');
        let endpoint = $('#customEndpoint').val().trim().replace(/^["']|["']$/g, '').replace(/\/+$/, '');
        let model = $('#customModel').val().trim().replace(/^["']|["']$/g, '');
        let version = $('#customApiVersion').val().trim().replace(/^["']|["']$/g, '');

        if (key) localStorage.setItem('imdb_azure_api_key', key);
        else localStorage.removeItem('imdb_azure_api_key');

        if (endpoint) localStorage.setItem('imdb_azure_endpoint', endpoint);
        else localStorage.removeItem('imdb_azure_endpoint');

        if (model) localStorage.setItem('imdb_azure_model', model);
        else localStorage.removeItem('imdb_azure_model');

        if (version) localStorage.setItem('imdb_azure_api_version', version);
        else localStorage.removeItem('imdb_azure_api_version');

        console.log(`🔑 [IMDb Settings] Saved to LocalStorage:`, {
            endpoint: endpoint,
            model: model || '(default)',
            apiVersion: version || '(default)',
            keyLength: key ? key.length : 0,
            keyPreview: key && key.length > 8 ? `${key.substring(0, 4)}...${key.substring(key.length - 4)}` : '(none)'
        });

        updateSettingsBadge();
        showToast('Settings saved to browser LocalStorage!');
        bootstrap.Modal.getInstance($modal[0])?.hide();
    });

    // Clear Credentials
    $('#resetSettingsBtn').on('click', function () {
        localStorage.removeItem('imdb_azure_api_key');
        localStorage.removeItem('imdb_azure_endpoint');
        localStorage.removeItem('imdb_azure_model');
        localStorage.removeItem('imdb_azure_api_version');

        $('#customApiKey').val('');
        $('#customEndpoint').val('');
        $('#customModel').val('');
        $('#customApiVersion').val('');

        updateSettingsBadge();
        showToast('Cleared API credentials.');
        bootstrap.Modal.getInstance($modal[0])?.hide();
    });
}

function updateSettingsBadge() {
    const customKey = localStorage.getItem('imdb_azure_api_key');
    const $badge = $('#settingsStatusBadge');
    if (!$badge.length) return;

    if (customKey && customKey.trim()) {
        $badge.addClass('status-active').html('<i class="fa-solid fa-circle-check me-1"></i> Active');
    } else {
        $badge.removeClass('status-active').html('Set API Key');
    }
}

function ensureApiKeyConfigured() {
    const customKey = localStorage.getItem('imdb_azure_api_key');
    if (!customKey || !customKey.trim()) {
        const modalEl = document.getElementById('settingsModal');
        if (modalEl) {
            const modal = new bootstrap.Modal(modalEl);
            modal.show();
        }
        showToast('Please set your AI key in API Settings to search.');
        return false;
    }
    return true;
}

function showToast(message) {
    $('#toastMsg').text(message);
    const toastEl = document.getElementById('copyToast');
    if (toastEl) {
        const toast = new bootstrap.Toast(toastEl, { delay: 2800 });
        toast.show();
    }
}

// ── Main Search Application Controller ────────────────────────────
$(document).ready(function () {
    console.log('🎬 IMDb Intelligence Console Ready');

    let allResults = [];
    let allColumnNames = [];
    let activeGenreFilters = new Set();
    let dataTableInstance = null;
    let lastQuery = '';
    let activeAbortController = null;
    let agentTimerInterval = null;
    let searchStartTime = 0;
    let lastTimelineMessage = '';
    let chartInstance = null;
    let currentDrilldownTitles = [];
    let currentDrilldownCols = [];
    let currentDrilldownSql = null;
    let activeDrilldownYear = null;

    initializeSettingsModal();
    initializeSearchControls();
    initializePlaceholderRotator();
    initializeSuggestedChips();
    initializeFilters();
    initializeShareableURL();
    initializeAISummary();
    initializeSQLInspector();
    initializeViewSwitcher();

    // Auto-search if ?q= parameter is present in URL
    const urlParams = new URLSearchParams(window.location.search);
    const urlQuery = urlParams.get('q');
    if (urlQuery) {
        $('#query').val(urlQuery);
        toggleClearButton(true);
        executeSearch(urlQuery);
    }

    // ── Search Input & Keyboard Shortcuts ─────────────────────────
    function initializeSearchControls() {
        const $form = $('#searchForm');
        const $query = $('#query');
        const $clearBtn = $('#clearQueryBtn');
        const $abortBtn = $('#abortFromLoadingBtn');
        const $dismissCorrBtn = $('#dismissCorrectionBtn');

        $form.on('submit', function (e) {
            e.preventDefault();
            const query = $query.val().trim();
            if (!query) return;
            executeSearch(query);
        });

        $query.on('input', function () {
            toggleClearButton($(this).val().length > 0 && !activeAbortController);
        });

        $clearBtn.on('click', function () {
            $query.val('').focus();
            toggleClearButton(false);
            $('#heroCollapsible').removeClass('collapsed');
            $('#resultsContainer, #mobileResultsFeed, #resultsMeta, #noResultsState, #errorState, #loadingState, #correctionBanner, #disambiguationBanner, #analyticsSection, #viewModeTabs, #drilldownFilterNotice').addClass('d-none');
            $('#suggestedChipsSection').removeClass('d-none');
            history.pushState({}, '', window.location.pathname);
        });

        // Cancel / Abort buttons
        $abortBtn.on('click', cancelActiveSearch);

        // Dismiss correction & disambiguation banners
        $dismissCorrBtn.on('click', function () {
            $('#correctionBanner').addClass('d-none');
        });

        $('#dismissDisambiguationBtn').on('click', function () {
            $('#disambiguationBanner').addClass('d-none');
        });

        // Click handler for disambiguation suggestion chips
        $(document).on('click', '.disambig-chip', function (e) {
            e.preventDefault();
            const targetQuery = $(this).attr('data-query');
            if (targetQuery) {
                $query.val(targetQuery);
                $('#disambiguationBanner').addClass('d-none');
                $form.submit();
            }
        });

        // Global '/' shortcut to focus search input, 'Escape' to abort/clear
        $(document).on('keydown', function (e) {
            if (e.key === '/' && !$(e.target).is('input, textarea, select')) {
                e.preventDefault();
                $query.focus().select();
            } else if (e.key === 'Escape') {
                if (activeAbortController) {
                    cancelActiveSearch();
                } else if ($(e.target).is('#query')) {
                    $query.val('');
                    toggleClearButton(false);
                    $('#heroCollapsible').removeClass('collapsed');
                }
            }
        });
    }

    function cancelActiveSearch() {
        if (activeAbortController) {
            activeAbortController.abort();
            activeAbortController = null;
            stopAgentTimer();
            hideLoading();
            showToast('Search canceled.');
        }
    }

    function toggleClearButton(show) {
        if (show) $('#clearQueryBtn').removeClass('d-none');
        else $('#clearQueryBtn').addClass('d-none');
    }

    // ── Dynamic Rotating Placeholder (Mobile & Small Screen Safe) ──
    function initializePlaceholderRotator() {
        const $input = $('#query');
        if (!$input.length) return;

        // Curated concise query prompts guaranteed to fit on mobile without truncation
        const placeholders = [
            'Search movies, actors, genres...',
            'e.g., Tom Hanks movies',
            'e.g., Best 2010s sci-fi',
            'e.g., Christopher Nolan films',
            'e.g., DiCaprio & Winslet',
            'e.g., 90s crime thrillers'
        ];

        let currentIndex = 0;
        let rotateTimer = null;
        let isFocused = false;

        function cyclePlaceholder() {
            if (isFocused || $input.val().length > 0) return;
            currentIndex = (currentIndex + 1) % placeholders.length;
            $input.attr('placeholder', placeholders[currentIndex]);
        }

        function startRotation() {
            if (rotateTimer) clearInterval(rotateTimer);
            rotateTimer = setInterval(cyclePlaceholder, 3800);
        }

        function stopRotation() {
            if (rotateTimer) {
                clearInterval(rotateTimer);
                rotateTimer = null;
            }
        }

        $input.on('focus', function () {
            isFocused = true;
            stopRotation();
        });

        $input.on('blur', function () {
            isFocused = false;
            if (!$input.val().trim()) {
                startRotation();
            }
        });

        startRotation();
    }

    // ── Live Agent Timer & Activity Timeline (Connected Rail) ─────
    function startAgentTimer() {
        searchStartTime = Date.now();
        $('#agentLiveTimer').text('0.0s');
        if (agentTimerInterval) clearInterval(agentTimerInterval);
        agentTimerInterval = setInterval(function () {
            const elapsed = ((Date.now() - searchStartTime) / 1000).toFixed(1);
            $('#agentLiveTimer').text(`${elapsed}s`);
        }, 100);
    }

    function stopAgentTimer() {
        if (agentTimerInterval) {
            clearInterval(agentTimerInterval);
            agentTimerInterval = null;
        }
    }

    function addTimelineStep(msg, type = 'info', icon = 'fa-circle-notch fa-spin', title = '') {
        if (!msg || msg === lastTimelineMessage) return;
        lastTimelineMessage = msg;

        // Update card header status if a title is provided
        if (title) {
            $('#agentStatusTitle').text(title);
        }

        // Update active headline message
        $('#agentCurrentStepMsg').text(msg);

        // Transition previous timeline step icons to completed state
        const $timeline = $('#agentActivityTimeline');
        const $prevItems = $timeline.find('.agent-step-item');
        $prevItems.removeClass('active').addClass('completed');

        const elapsed = ((Date.now() - searchStartTime) / 1000).toFixed(1);
        const $item = $(`
            <div class="agent-step-item ${type} active fade-in">
                <div class="agent-step-node"></div>
                <div class="flex-grow-1 min-w-0">
                    <span>${escapeHtml(msg)}</span>
                </div>
                <span class="timeline-time-pill">${elapsed}s</span>
            </div>
        `);
        $timeline.append($item);
        $timeline.scrollTop($timeline[0].scrollHeight);
    }

    function getCustomAzureHeaders(extraHeaders = {}) {
        const headers = Object.assign({ 'Content-Type': 'application/json' }, extraHeaders);
        const customKey = localStorage.getItem('imdb_azure_api_key');
        const customEndpoint = localStorage.getItem('imdb_azure_endpoint');
        const customModel = localStorage.getItem('imdb_azure_model');
        const customVersion = localStorage.getItem('imdb_azure_api_version');

        if (customKey && customKey.trim()) headers['X-Azure-API-Key'] = customKey.trim();
        if (customEndpoint && customEndpoint.trim()) headers['X-Azure-Endpoint'] = customEndpoint.trim();
        if (customModel && customModel.trim()) headers['X-Azure-Model'] = customModel.trim();
        if (customVersion && customVersion.trim()) headers['X-Azure-API-Version'] = customVersion.trim();
        return headers;
    }

    // ── Search Execution with Streaming & Cancellation ───────────
    async function executeSearch(query) {
        if (!ensureApiKeyConfigured()) {
            return;
        }

        // Cancel previous search if running
        if (activeAbortController) {
            activeAbortController.abort();
        }
        activeAbortController = new AbortController();

        lastQuery = query;

        // Push state to browser URL
        const url = new URL(window.location);
        url.searchParams.set('q', query);
        history.pushState({ query: query }, '', url);

        showLoading();
        startAgentTimer();
        lastTimelineMessage = '';
        $('#agentActivityTimeline').empty();
        $('#correctionBanner').addClass('d-none');
        $('#noResultsDiagnosisBox').addClass('d-none');

        addTimelineStep('Understanding your query & movie criteria...', 'info', 'fa-satellite-dish', 'Searching Film Vault');

        const headers = getCustomAzureHeaders();
        const keyHdr = headers['X-Azure-API-Key'];
        const keyPreview = keyHdr ? `${keyHdr.substring(0, 4)}...${keyHdr.substring(keyHdr.length - 4)} (length: ${keyHdr.length})` : '(using server config.py)';
        
        console.group(`🎬 [IMDb Search] "${query}"`);
        console.log(`Endpoint:`, headers['X-Azure-Endpoint'] || '(using server config.py)');
        console.log(`Model:`, headers['X-Azure-Model'] || '(using server config.py)');
        console.log(`API Key:`, keyPreview);
        console.groupEnd();

        try {
            const response = await fetch('/api/search/stream', {
                method: 'POST',
                headers: headers,
                body: JSON.stringify({ query: query }),
                signal: activeAbortController.signal
            });

            if (!response.ok) {
                let errorMsg = 'Unable to complete search at this time.';
                let suggestions = [];
                try {
                    const errData = await response.json();
                    errorMsg = errData.error || errorMsg;
                    suggestions = errData.suggestions || [];
                } catch (_) {}
                stopAgentTimer();
                hideLoading();
                activeAbortController = null;
                showError(errorMsg, suggestions);
                return;
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');
                buffer = lines.pop(); // Keep incomplete chunk in buffer

                for (const block of lines) {
                    const trimmed = block.trim();
                    if (!trimmed.startsWith('data:')) continue;
                    const jsonStr = trimmed.replace(/^data:\s*/, '');
                    try {
                        const event = JSON.parse(jsonStr);
                        handleStreamEvent(event);
                    } catch (e) {
                        console.warn('Could not parse SSE chunk:', jsonStr, e);
                    }
                }
            }

            stopAgentTimer();
            hideLoading();
            activeAbortController = null;

        } catch (err) {
            stopAgentTimer();
            hideLoading();
            if (err.name === 'AbortError') {
                console.log('Search aborted by user');
            } else {
                console.error('Streaming search error:', err);
                showError(err.message || 'An unexpected error occurred during execution.');
            }
            activeAbortController = null;
        }
    }

    function handleStreamEvent(event) {
        console.log('⚡ [IMDb Stream]:', event.type, event.stage || '', event.message || event.sql || (event.results ? `${event.results.length} rows` : '') || '');
        if (event.type === 'status') {
            let icon = 'fa-circle-notch fa-spin';
            let stepType = 'info';
            let title = event.title || 'Searching Film Vault';

            if (event.stage === 'synthesizing' || event.stage === 'generating') {
                icon = 'fa-brain text-gold';
            } else if (event.stage === 'validating') {
                icon = 'fa-shield-halved text-cyan';
            } else if (event.stage === 'refining') {
                icon = 'fa-wand-magic-sparkles text-gold';
            } else if (event.stage === 'executing') {
                icon = 'fa-database text-gold';
            } else if (event.stage === 'compiling') {
                icon = 'fa-table-cells text-emerald';
            } else if (event.stage === 'probing' || event.stage === 'reflecting') {
                icon = 'fa-magnifying-glass text-cyan';
            }

            addTimelineStep(event.message, stepType, icon, title);

        } else if (event.type === 'sql') {
            $('#sqlDisplay').text(event.sql || '-- No SQL');

        } else if (event.type === 'retry') {
            let retryMsg = event.message || 'Searching with closest match...';
            if (event.corrected_entity) {
                retryMsg = `Searching for "${event.corrected_entity}" instead...`;
            }
            addTimelineStep(retryMsg, 'retry', 'fa-arrow-rotate-right text-gold', 'Smart Match');
            if (event.new_sql) {
                $('#sqlDisplay').text(event.new_sql);
            }

        } else if (event.type === 'result') {
            // Mark all items complete
            $('#agentActivityTimeline').find('.agent-step-item')
                .removeClass('active').addClass('completed');

            if (event.success && event.results && event.results.length > 0) {
                allResults = event.results;
                allColumnNames = event.column_names;

                showResultsMeta(event);
                
                if (event.is_aggregate) {
                    renderAnalyticsDashboard(event);
                } else {
                    renderTitleDiscoveryResults(event);
                }

                // Show Auto-Correction Banner if intent reflection was applied
                if (event.corrected_entity) {
                    $('#correctionMessage').html(`Showing results for <strong>${escapeHtml(event.corrected_entity)}</strong>`);
                    $('#correctionBanner').removeClass('d-none');
                } else if (event.correction_note) {
                    $('#correctionMessage').text(event.correction_note);
                    $('#correctionBanner').removeClass('d-none');
                } else {
                    $('#correctionBanner').addClass('d-none');
                }

                // Show Disambiguation Ribbon if alternative candidates exist
                if (event.disambiguation && event.disambiguation.alternatives && event.disambiguation.alternatives.length > 0) {
                    renderDisambiguation(event.disambiguation);
                } else {
                    $('#disambiguationBanner').addClass('d-none');
                }

            } else if (event.success && event.row_count === 0) {
                allResults = [];
                hideResultsMeta();
                showNoResults(event);
                if (event.disambiguation && event.disambiguation.alternatives && event.disambiguation.alternatives.length > 0) {
                    renderDisambiguation(event.disambiguation);
                } else {
                    $('#disambiguationBanner').addClass('d-none');
                }
            } else {
                showError(event.error || 'No matching movies found.', event.suggestions);
            }

        } else if (event.type === 'error') {
            console.error('❌ [IMDb Search Error]:', event);
            showError(event.error || 'Search could not be completed.', event.suggestions);
        }
    }

    function renderDisambiguation(disambigData) {
        if (!disambigData || !disambigData.alternatives || disambigData.alternatives.length === 0) {
            $('#disambiguationBanner').addClass('d-none');
            return;
        }

        const label = disambigData.primary_label || disambigData.primary_entity || disambigData.term;
        $('#disambigSelectedName').text(label);

        const $chips = $('#disambiguationChips');
        $chips.empty();

        disambigData.alternatives.forEach(alt => {
            let metaText = '';
            if (alt.credits) {
                metaText = `${alt.credits} titles`;
            } else if (alt.role) {
                metaText = alt.role;
            }

            const metaBadge = metaText ? `<span class="disambig-meta-badge ms-1">${escapeHtml(metaText)}</span>` : '';
            const queryTarget = alt.query || `${alt.name} movies`;
            const chipHtml = `
                <button type="button" class="disambig-chip" data-query="${escapeHtml(queryTarget)}" title="Search for ${escapeHtml(alt.name)}">
                    <i class="fa-solid fa-user-tag text-gold"></i>
                    <span class="disambig-name">${escapeHtml(alt.name)}</span>
                    ${metaBadge}
                </button>
            `;
            $chips.append(chipHtml);
        });

        $('#disambiguationBanner').removeClass('d-none');
    }

    function showLoading() {
        $('#heroCollapsible').addClass('collapsed');
        $('#loadingState').removeClass('d-none');
        $('#errorState, #noResultsState, #resultsContainer, #mobileResultsFeed, #resultsMeta, #suggestedChipsSection, #analyticsSection, #viewModeTabs, #drilldownFilterNotice, #disambiguationBanner').addClass('d-none');
        $('#searchBtn').prop('disabled', true).html('<i class="fa-solid fa-circle-notch fa-spin me-1"></i> <span>Searching...</span>');
        $('#clearQueryBtn').addClass('d-none');
    }

    function hideLoading() {
        $('#loadingState').addClass('d-none');
        $('#searchBtn').prop('disabled', false).html('<i class="fa-solid fa-magnifying-glass me-1"></i> <span>Search</span>');
        toggleClearButton($('#query').val().length > 0);
    }

    function showResultsMeta(response) {
        $('#resultsMeta').removeClass('d-none');
        if (response.is_aggregate) {
            $('#resultCount').text(`${response.results.length} data point${response.results.length !== 1 ? 's' : ''}`);
        } else if (response.row_count > response.results.length) {
            $('#resultCount').text(`${response.results.length.toLocaleString()} of ${response.row_count.toLocaleString()}`);
        } else {
            $('#resultCount').text(response.row_count.toLocaleString());
        }
        $('#executionTime').text(response.execution_time ? `${response.execution_time}s` : '0.2s');
        $('#sqlDisplay').text(response.sql_query || '-- No SQL query');
    }

    function hideResultsMeta() {
        $('#resultsMeta').addClass('d-none');
    }

    function showNoResults(eventData = null) {
        $('#noResultsState').removeClass('d-none');
        $('#resultsContainer, #mobileResultsFeed').addClass('d-none');

        if (eventData && (eventData.explanation || eventData.diagnosis)) {
            let diagText = eventData.explanation || '';
            if (eventData.diagnosis === 'GENUINE_EMPTY') {
                diagText += ' Entity was confirmed in IMDb catalog, but no titles matched the combined query filters.';
            }
            $('#noResultsDiagnosisText').text(diagText);
            $('#noResultsDiagnosisBox').removeClass('d-none');
        } else {
            $('#noResultsDiagnosisBox').addClass('d-none');
        }
    }

    function showError(message, suggestions) {
        $('#errorState').removeClass('d-none');
        $('#resultsContainer, #mobileResultsFeed, #noResultsState, #resultsMeta').addClass('d-none');
        $('#errorMessage').text(message);

        if (suggestions && suggestions.length > 0) {
            $('#errorSuggestions').removeClass('d-none');
            const $chips = $('#errorSuggestionChips').empty();
            suggestions.forEach(function (s) {
                $chips.append(
                    $('<button class="cinema-chip"></button>')
                        .text(s)
                        .on('click', function () {
                            $('#query').val(s);
                            toggleClearButton(true);
                            executeSearch(s);
                        })
                );
            });
        } else {
            $('#errorSuggestions').addClass('d-none');
        }
    }

    $('#dismissError').on('click', function () {
        $('#errorState').addClass('d-none');
    });

    $('#retryBtn').on('click', function () {
        if (lastQuery) executeSearch(lastQuery);
    });

    // ── Cinema Analytics & Drilldown Engine ───────────────────────
    function initializeViewSwitcher() {
        $('#tabAnalyticsBtn').on('click', function () {
            $(this).addClass('active');
            $('#tabTitlesBtn').removeClass('active');
            $('#analyticsSection').removeClass('d-none');
            $('#resultsContainer, #mobileResultsFeed').addClass('d-none');
        });

        $('#tabTitlesBtn').on('click', function () {
            $(this).addClass('active');
            $('#tabAnalyticsBtn').removeClass('active');
            $('#analyticsSection').addClass('d-none');
            $('#resultsContainer, #mobileResultsFeed').removeClass('d-none');
        });

        $('#clearDrilldownFilterBtn').on('click', function () {
            activeDrilldownYear = null;
            $('#drilldownFilterNotice').addClass('d-none');
            $('#titlesTabCountBadge').text(currentDrilldownTitles.length);
            applyTitlesDisplay(currentDrilldownTitles);
        });
    }

    function applyTitlesDisplay(titles) {
        if (!titles || titles.length === 0) return;
        allResults = titles;
        allColumnNames = currentDrilldownCols.length > 0 ? currentDrilldownCols : Object.keys(titles[0]);
        buildGenreFilters(allResults);
        renderResultsTable(allResults, allColumnNames);
        renderMobileCardsFeed(allResults);
        resetFilters();
    }

    function renderTitleDiscoveryResults(event) {
        $('#analyticsSection, #viewModeTabs, #drilldownFilterNotice').addClass('d-none');
        if (chartInstance) {
            chartInstance.destroy();
            chartInstance = null;
        }
        buildGenreFilters(allResults);
        renderResultsTable(allResults, allColumnNames);
        renderMobileCardsFeed(allResults);
        resetFilters();
    }

    function renderAnalyticsDashboard(event) {
        const rawRows = event.results || [];
        const cols = event.column_names || [];
        currentDrilldownTitles = event.drilldown_results || [];
        currentDrilldownCols = event.drilldown_columns || [];
        currentDrilldownSql = event.drilldown_sql || null;
        activeDrilldownYear = null;
        $('#drilldownFilterNotice').addClass('d-none');

        // Identify metric and group columns
        const groupCol = cols.find(c => ['year', 'premiered', 'genres', 'genre', 'name', 'country', 'language', 'category'].includes(c.toLowerCase())) || cols[0];
        const metricCol = cols.find(c => ['movie_count', 'count', 'total_movies', 'total_titles', 'avg_rating', 'votes'].includes(c.toLowerCase())) || (cols.length > 1 ? cols[1] : cols[0]);

        // Clean rows: remove rows with null or empty group values (e.g. unreleased/null year)
        const rows = rawRows.filter(r => {
            const val = r[groupCol];
            return val !== null && val !== undefined && String(val).toLowerCase() !== 'null' && String(val).trim() !== '';
        });

        // 1. Dynamic Context-Aware KPI Stat Ribbon (Clean 3-Card Cinema Layout)
        const $ribbon = $('#analyticsKpiRibbon').empty();
        
        let totalCount = 0;
        let peakVal = -Infinity;
        let peakLabel = '';
        let minVal = Infinity;
        let minLabel = '';

        rows.forEach(r => {
            const v = parseFloat(r[metricCol]) || 0;
            totalCount += v;
            if (v > peakVal) {
                peakVal = v;
                peakLabel = r[groupCol];
            }
            if (v < minVal) {
                minVal = v;
                minLabel = r[groupCol];
            }
        });

        if (event.query_type === 'AGGREGATION_SCALAR' || rows.length === 1) {
            const val = rows[0] ? (rows[0][metricCol] || rows[0][cols[0]]) : 0;
            const label = metricCol.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
            $ribbon.append(`
                <div class="kpi-stat-card">
                    <div class="kpi-stat-label"><i class="fa-solid fa-calculator text-gold"></i> ${escapeHtml(label)}</div>
                    <div class="kpi-stat-val">${Number(val).toLocaleString()}</div>
                    <div class="kpi-stat-sub">Direct aggregate metric</div>
                </div>
            `);
        } else if (rows.length > 0) {
            const isYear = (groupCol.toLowerCase() === 'year' || groupCol.toLowerCase() === 'premiered');
            const isGenre = groupCol.toLowerCase().includes('genre');
            const isRating = metricCol.toLowerCase().includes('rating') || metricCol.toLowerCase().includes('score');

            const peakPct = totalCount > 0 ? ((peakVal / totalCount) * 100).toFixed(1) : 0;

            if (isYear) {
                // Temporal trend analysis (3 cards: Total Films, Career Span, Peak Year)
                const validYearRows = rows.filter(r => {
                    const y = parseInt(r[groupCol]);
                    return !isNaN(y) && y > 1800 && y < 2100;
                });
                const minYear = validYearRows.length > 0 ? validYearRows[0][groupCol] : (rows[0] ? rows[0][groupCol] : 'N/A');
                const maxYear = validYearRows.length > 0 ? validYearRows[validYearRows.length - 1][groupCol] : (rows[rows.length - 1] ? rows[rows.length - 1][groupCol] : 'N/A');
                const yearSpan = (parseInt(maxYear) && parseInt(minYear)) ? (parseInt(maxYear) - parseInt(minYear) + 1) : validYearRows.length;

                $ribbon.append(`
                    <div class="kpi-stat-card">
                        <div class="kpi-stat-label"><i class="fa-solid fa-clapperboard text-gold"></i> Total Films</div>
                        <div class="kpi-stat-val">${Number(totalCount).toLocaleString()}</div>
                        <div class="kpi-stat-sub">Across ${validYearRows.length} active release years</div>
                    </div>
                    <div class="kpi-stat-card">
                        <div class="kpi-stat-label"><i class="fa-regular fa-calendar-days text-cyan"></i> Career Span</div>
                        <div class="kpi-stat-val" style="font-size: 1.45rem;">${escapeHtml(String(minYear))} – ${escapeHtml(String(maxYear))}</div>
                        <div class="kpi-stat-sub">${yearSpan}-year active creative window</div>
                    </div>
                    <div class="kpi-stat-card">
                        <div class="kpi-stat-label"><i class="fa-solid fa-trophy text-gold"></i> Peak Year</div>
                        <div class="kpi-stat-val" style="font-size: 1.45rem;">${escapeHtml(String(peakLabel))} (${peakVal.toLocaleString()} films)</div>
                        <div class="kpi-stat-sub">${peakPct}% of total career output</div>
                    </div>
                `);
            } else if (isGenre) {
                // Genre distribution analysis
                $ribbon.append(`
                    <div class="kpi-stat-card">
                        <div class="kpi-stat-label"><i class="fa-solid fa-film text-gold"></i> Total Classified</div>
                        <div class="kpi-stat-val">${Number(totalCount).toLocaleString()}</div>
                        <div class="kpi-stat-sub">Across ${rows.length} categories</div>
                    </div>
                    <div class="kpi-stat-card">
                        <div class="kpi-stat-label"><i class="fa-solid fa-star text-gold"></i> Dominant Genre</div>
                        <div class="kpi-stat-val" style="font-size: 1.45rem;">${escapeHtml(String(peakLabel))} (${peakVal.toLocaleString()})</div>
                        <div class="kpi-stat-sub">${peakPct}% share of filmography</div>
                    </div>
                    <div class="kpi-stat-card">
                        <div class="kpi-stat-label"><i class="fa-solid fa-shapes text-cyan"></i> Genre Breadth</div>
                        <div class="kpi-stat-val" style="font-size: 1.45rem;">${rows.length} Genres</div>
                        <div class="kpi-stat-sub">Distinct repertoire genres</div>
                    </div>
                `);
            } else if (isRating) {
                // Rating and reception analysis
                const meanRating = (totalCount / rows.length).toFixed(2);
                $ribbon.append(`
                    <div class="kpi-stat-card">
                        <div class="kpi-stat-label"><i class="fa-solid fa-star-half-stroke text-gold"></i> Mean Rating</div>
                        <div class="kpi-stat-val">${meanRating} ★</div>
                        <div class="kpi-stat-sub">Average across ${rows.length} entries</div>
                    </div>
                    <div class="kpi-stat-card">
                        <div class="kpi-stat-label"><i class="fa-solid fa-award text-gold"></i> Highest Rated</div>
                        <div class="kpi-stat-val" style="font-size: 1.45rem;">${escapeHtml(String(peakLabel))} (${peakVal.toFixed(1)} ★)</div>
                        <div class="kpi-stat-sub">Peak critical mark</div>
                    </div>
                    <div class="kpi-stat-card">
                        <div class="kpi-stat-label"><i class="fa-solid fa-arrow-down-short-wide text-cyan"></i> Lowest Mark</div>
                        <div class="kpi-stat-val" style="font-size: 1.45rem;">${escapeHtml(String(minLabel))} (${minVal.toFixed(1)} ★)</div>
                        <div class="kpi-stat-sub">Minimum score recorded</div>
                    </div>
                `);
            } else {
                // General aggregation (actors, directors, countries)
                $ribbon.append(`
                    <div class="kpi-stat-card">
                        <div class="kpi-stat-label"><i class="fa-solid fa-layer-group text-gold"></i> Total Output</div>
                        <div class="kpi-stat-val">${Number(totalCount).toLocaleString()}</div>
                        <div class="kpi-stat-sub">Total across all groups</div>
                    </div>
                    <div class="kpi-stat-card">
                        <div class="kpi-stat-label"><i class="fa-solid fa-trophy text-gold"></i> Leading Entry</div>
                        <div class="kpi-stat-val" style="font-size: 1.45rem;">${escapeHtml(String(peakLabel))} (${peakVal.toLocaleString()})</div>
                        <div class="kpi-stat-sub">${peakPct}% of overall volume</div>
                    </div>
                    <div class="kpi-stat-card">
                        <div class="kpi-stat-label"><i class="fa-solid fa-list-ol text-cyan"></i> Categories</div>
                        <div class="kpi-stat-val" style="font-size: 1.45rem;">${rows.length} Groups</div>
                        <div class="kpi-stat-sub">Unique classified entities</div>
                    </div>
                `);
            }
        }

        // 2. Render Interactive Chart.js
        if (event.query_type === 'AGGREGATION_SERIES' && rows.length > 1 && window.Chart) {
            $('#analyticsChartCard').removeClass('d-none');
            const labels = rows.map(r => String(r[groupCol]));
            const dataVals = rows.map(r => parseFloat(r[metricCol]) || 0);

            if (chartInstance) {
                chartInstance.destroy();
                chartInstance = null;
            }

            const canvasEl = document.getElementById('cinemaTrendCanvas');
            if (canvasEl) {
                const ctx = canvasEl.getContext('2d');
                const gradient = ctx.createLinearGradient(0, 0, 0, 300);
                gradient.addColorStop(0, 'rgba(245, 197, 24, 0.85)');
                gradient.addColorStop(1, 'rgba(245, 197, 24, 0.2)');

                chartInstance = new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: metricCol.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
                            data: dataVals,
                            backgroundColor: gradient,
                            borderColor: '#F5C518',
                            borderWidth: 1.5,
                            borderRadius: 6,
                            hoverBackgroundColor: '#FFD13B',
                            hoverBorderColor: '#FFFFFF'
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            x: {
                                grid: { display: false },
                                ticks: {
                                    color: '#9CA3AF',
                                    font: { family: "'JetBrains Mono', monospace", size: 12 }
                                }
                            },
                            y: {
                                grid: { color: 'rgba(255, 255, 255, 0.06)' },
                                ticks: {
                                    color: '#9CA3AF',
                                    font: { family: "'JetBrains Mono', monospace", size: 12 },
                                    beginAtZero: true,
                                    precision: 0
                                }
                            }
                        },
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                backgroundColor: '#12151E',
                                titleColor: '#F5C518',
                                bodyColor: '#E2E8F0',
                                borderColor: 'rgba(245, 197, 24, 0.4)',
                                borderWidth: 1,
                                padding: 10,
                                displayColors: false,
                                callbacks: {
                                    label: function (context) {
                                        const val = context.parsed.y;
                                        const pct = totalCount > 0 ? ((val / totalCount) * 100).toFixed(1) : 0;
                                        return `${val} films (${pct}% of period)`;
                                    }
                                }
                            }
                        },
                        onClick: function (evt, elements) {
                            if (elements && elements.length > 0) {
                                const index = elements[0].index;
                                const clickedLabel = labels[index];
                                drilldownByGroup(clickedLabel, groupCol);
                            }
                        }
                    }
                });
            }
        } else {
            $('#analyticsChartCard').addClass('d-none');
        }

        // 3. Render Aggregate Breakdown Table
        const $aggHead = $('#aggTableHead').empty();
        const $aggBody = $('#aggTableBody').empty();

        $aggHead.append(`
            <th>${escapeHtml(groupCol.replace(/_/g, ' ').toUpperCase())}</th>
            <th>${escapeHtml(metricCol.replace(/_/g, ' ').toUpperCase())}</th>
            <th>% SHARE</th>
            <th class="text-end">ACTION</th>
        `);

        rows.forEach(r => {
            const gVal = r[groupCol];
            const mVal = parseFloat(r[metricCol]) || 0;
            const pct = totalCount > 0 ? ((mVal / totalCount) * 100).toFixed(1) : '100';

            const actionHtml = `<td class="text-end"><button type="button" class="btn-agg-action" data-filter="${escapeHtml(String(gVal))}"><i class="fa-solid fa-eye me-1"></i> View ${mVal} Titles &rarr;</button></td>`;

            $aggBody.append(`
                <tr>
                    <td><span class="badge-year">${escapeHtml(String(gVal))}</span></td>
                    <td><span class="fw-bold text-white font-mono">${mVal.toLocaleString()}</span></td>
                    <td><span class="text-secondary font-mono small">${pct}%</span></td>
                    ${actionHtml}
                </tr>
            `);
        });

        // Event listener for action buttons
        $aggBody.find('.btn-agg-action').on('click', function () {
            const filterVal = $(this).attr('data-filter');
            drilldownByGroup(filterVal, groupCol);
        });

        // 4. Setup View Mode Switcher and Drilldown data
        if (currentDrilldownTitles.length > 0 || currentDrilldownSql) {
            $('#titlesTabCountBadge').text(currentDrilldownTitles.length || 'Explore');
            $('#viewModeTabs').removeClass('d-none');
            if (currentDrilldownTitles.length > 0) {
                applyTitlesDisplay(currentDrilldownTitles);
            }
        } else {
            $('#viewModeTabs').addClass('d-none');
        }

        // Switch to Analytics Tab
        $('#tabAnalyticsBtn').addClass('active');
        $('#tabTitlesBtn').removeClass('active');
        $('#analyticsSection').removeClass('d-none');
        $('#resultsContainer, #mobileResultsFeed').addClass('d-none');
    }

    async function drilldownByGroup(val, groupCol) {
        if (!val) return;
        activeDrilldownYear = val;

        // Visual loading state
        $('#drilldownFilterLabel').html(`<i class="fa-solid fa-circle-notch fa-spin me-1"></i> Loading ${escapeHtml(String(val))}...`);
        $('#drilldownFilterNotice').removeClass('d-none');

        // Immediately switch tab to 'Explore Titles' so user sees reaction
        $('#tabTitlesBtn').addClass('active');
        $('#tabAnalyticsBtn').removeClass('active');
        $('#analyticsSection').addClass('d-none');
        $('#resultsContainer, #mobileResultsFeed').removeClass('d-none');
        document.getElementById('viewModeTabs')?.scrollIntoView({ behavior: 'smooth', block: 'start' });

        // Targeted fetch via DuckDB backend drilldown
        if (currentDrilldownSql) {
            try {
                const resp = await fetch('/api/analytics/drilldown', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        drilldown_sql: currentDrilldownSql,
                        filter_col: groupCol,
                        filter_val: val
                    })
                });
                if (resp.ok) {
                    const data = await resp.json();
                    if (data.success && data.results && data.results.length > 0) {
                        $('#titlesTabCountBadge').text(data.results.length);
                        $('#drilldownFilterLabel').text(`Showing: ${val} (${data.results.length} titles)`);
                        applyTitlesDisplay(data.results);
                        return;
                    }
                }
            } catch (err) {
                console.warn('Backend drilldown fetch failed, falling back to client cache:', err);
            }
        }

        // Fallback: client-side cache filter
        const isYear = (groupCol.toLowerCase() === 'year' || groupCol.toLowerCase() === 'premiered');
        let filtered = currentDrilldownTitles;

        if (isYear) {
            filtered = currentDrilldownTitles.filter(t => String(t.premiered) === String(val));
        } else {
            filtered = currentDrilldownTitles.filter(t => String(t[groupCol] || t.genres || '').toLowerCase().includes(String(val).toLowerCase()));
        }

        $('#titlesTabCountBadge').text(filtered.length);
        $('#drilldownFilterLabel').text(`Showing: ${val} (${filtered.length} titles)`);
        applyTitlesDisplay(filtered);
    }

    // ── Table Rendering with DataTables (Desktop View) ───────────
    function renderResultsTable(results, columnNames) {
        if (dataTableInstance) {
            dataTableInstance.destroy();
            dataTableInstance = null;
        }

        const $head = $('#tableHead').empty();
        const $body = $('#tableBody').empty();

        const friendlyNames = {
            'title_id': 'IMDb ID',
            'primary_title': 'Title',
            'original_title': 'Original Title',
            'premiered': 'Year',
            'runtime_minutes': 'Runtime',
            'genres': 'Genres',
            'rating': 'IMDb Rating',
            'votes': 'Votes',
            'name': 'Name',
            'person_id': 'Person ID',
            'type': 'Format',
            'is_adult': 'Adult',
            'ended': 'Ended',
            'born': 'Born',
            'died': 'Died',
            'category': 'Role',
            'characters': 'Character',
            'season_number': 'Season',
            'episode_number': 'Episode'
        };

        const numericCols = ['votes', 'rating', 'premiered', 'runtime_minutes', 'season_number', 'episode_number', 'born', 'died', 'ended'];

        // Filter out raw poster_path column from table header if title column exists
        const visibleCols = columnNames.filter(c => c !== 'poster_path');

        // Build Table Header
        visibleCols.forEach(function (col) {
            const label = friendlyNames[col] || col.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
            const th = $('<th></th>').text(label);
            if (col === 'primary_title' || col === 'original_title' || col === 'title' || col === 'name') {
                th.addClass('col-title-header');
            } else if (col === 'title_id' || col === 'person_id') {
                th.addClass('col-id-header');
            } else if (col === 'premiered' || col === 'ended' || col === 'born' || col === 'died' || col === 'year') {
                th.addClass('col-year-header');
            } else if (col === 'rating' || col === 'average_rating') {
                th.addClass('col-rating-header');
            } else if (col === 'votes') {
                th.addClass('col-votes-header');
            } else if (col === 'genres') {
                th.addClass('col-genres-header');
            }
            if (numericCols.includes(col)) th.attr('data-type', 'numeric');
            $head.append(th);
        });

        if ($.fn.dataTable && $.fn.dataTable.ext && !$.fn.dataTable.ext.type.order['num-nulls-last-asc']) {
            const parseNum = function (val) {
                if (val === null || val === undefined || val === '' || val === '—') return null;
                if (typeof val === 'number') return isNaN(val) ? null : val;
                const n = parseFloat(String(val).replace(/[^0-9.-]/g, ''));
                return isNaN(n) ? null : n;
            };

            $.fn.dataTable.ext.type.order['num-nulls-last-pre'] = parseNum;

            $.fn.dataTable.ext.type.order['num-nulls-last-asc'] = function (a, b) {
                const x = parseNum(a);
                const y = parseNum(b);
                if (x === null && y === null) return 0;
                if (x === null) return 1;
                if (y === null) return -1;
                return x < y ? -1 : (x > y ? 1 : 0);
            };

            $.fn.dataTable.ext.type.order['num-nulls-last-desc'] = function (a, b) {
                const x = parseNum(a);
                const y = parseNum(b);
                if (x === null && y === null) return 0;
                if (x === null) return 1;
                if (y === null) return -1;
                return x < y ? 1 : (x > y ? -1 : 0);
            };
        }

        // Build Table Rows
        results.forEach(function (row) {
            const $tr = $('<tr></tr>');
            visibleCols.forEach(function (col) {
                const val = row[col];
                const $td = $('<td></td>');

                if (col === 'title_id' && val) {
                    $td.addClass('col-id-cell');
                    $td.html(`<a href="https://www.imdb.com/title/${escapeHtml(val)}/" target="_blank" rel="noopener noreferrer" class="imdb-link-badge"><i class="fa-solid fa-arrow-up-right-from-square"></i> ${escapeHtml(val)}</a>`);
                } else if ((col === 'primary_title' || col === 'original_title' || col === 'title' || col === 'name') && val) {
                    const titleId = row['title_id'] || '';
                    const posterPath = row['poster_path'] || '';
                    $td.addClass('col-title-cell');
                    
                    const posterImgHtml = posterPath 
                        ? `<img src="https://image.tmdb.org/t/p/w92${escapeHtml(posterPath)}" class="movie-poster-thumb" alt="Poster" loading="lazy" onerror="this.onerror=null; this.replaceWith(Object.assign(document.createElement('div'), {className: 'movie-poster-placeholder', innerHTML: '<i class=\\\'fa-solid fa-clapperboard\\\'></i>'}));">`
                        : `<div class="movie-poster-placeholder"><i class="fa-solid fa-clapperboard"></i></div>`;

                    $td.html(`
                        <div class="d-flex align-items-center justify-content-between gap-3">
                            <div class="d-flex align-items-center gap-2 min-w-0">
                                ${posterImgHtml}
                                <span class="title-text-cell">${escapeHtml(val)}</span>
                            </div>
                            ${titleId ? `<button class="btn-ai-synopsis flex-shrink-0" data-title-id="${escapeHtml(titleId)}" data-title-name="${escapeHtml(val)}" title="Generate AI Synopsis"><i class="fa-solid fa-wand-magic-sparkles"></i></button>` : ''}
                        </div>
                    `);
                } else if (col === 'rating' || col === 'average_rating') {
                    $td.addClass('col-rating-cell');
                    if (val != null && val !== '') {
                        $td.html(`<span class="badge-rating"><i class="fa-solid fa-star text-gold"></i> ${val}</span>`);
                        $td.attr('data-sort', val);
                        $td.attr('data-order', val);
                    } else {
                        $td.addClass('text-secondary').text('—');
                        $td.attr('data-sort', -1);
                        $td.attr('data-order', -1);
                    }
                } else if (col === 'votes') {
                    $td.addClass('col-votes-cell');
                    if (val != null && val !== '') {
                        $td.html(`<span class="votes-count-cell">${Number(val).toLocaleString()}</span>`);
                        $td.attr('data-sort', val);
                        $td.attr('data-order', val);
                    } else {
                        $td.addClass('text-secondary').text('—');
                        $td.attr('data-sort', -1);
                        $td.attr('data-order', -1);
                    }
                } else if ((col === 'original_language' || col === 'origin_country') && val) {
                    $td.html(`<span class="badge-country-lang">${escapeHtml(String(val).toUpperCase())}</span>`);
                } else if (col === 'premiered' || col === 'ended' || col === 'born' || col === 'died' || col === 'year') {
                    $td.addClass('col-year-cell');
                    if (val != null && val !== '') {
                        $td.html(`<span class="badge-year">${val}</span>`);
                        $td.attr('data-sort', val);
                        $td.attr('data-order', val);
                    } else {
                        $td.addClass('text-secondary').text('—');
                        $td.attr('data-sort', -1);
                        $td.attr('data-order', -1);
                    }
                } else if (col === 'genres' && val) {
                    $td.addClass('col-genres-cell');
                    const chips = val.split(',').map(g => `<span class="genre-chip-inline">${escapeHtml(g.trim())}</span>`).join(' ');
                    $td.html(chips);
                } else if (col === 'runtime_minutes') {
                    if (val != null && val !== '') {
                        $td.html(`<span class="font-mono text-secondary">${val} min</span>`);
                        $td.attr('data-sort', val);
                        $td.attr('data-order', val);
                    } else {
                        $td.addClass('text-secondary').text('—');
                        $td.attr('data-sort', -1);
                        $td.attr('data-order', -1);
                    }
                } else {
                    const textVal = (val != null && val !== '') ? val : '—';
                    $td.text(textVal);
                    if (numericCols.includes(col)) {
                        const numVal = (val != null && val !== '') ? Number(val) : -1;
                        $td.attr('data-sort', numVal);
                        $td.attr('data-order', numVal);
                    }
                }

                $tr.append($td);
            });
            $body.append($tr);
        });

        $('#resultsContainer').removeClass('d-none');
        $('#noResultsState').addClass('d-none');

        const columnDefs = [];
        let votesIdx = -1;
        visibleCols.forEach(function (col, idx) {
            if (col === 'votes') votesIdx = idx;
            if (numericCols.includes(col)) {
                columnDefs.push({
                    targets: idx,
                    type: 'num-nulls-last'
                });
            }
        });

        dataTableInstance = $('#resultsTable').DataTable({
            pageLength: 25,
            ordering: true,
            searching: true,
            autoWidth: false,
            responsive: false,
            language: {
                search: 'Filter results:',
                lengthMenu: 'Show _MENU_',
                info: 'Showing _START_ to _END_ of _TOTAL_',
                paginate: { first: '«', last: '»', next: '›', previous: '‹' },
                emptyTable: 'No matching movies found',
                zeroRecords: 'No matching records'
            },
            columnDefs: columnDefs,
            order: votesIdx >= 0 ? [[votesIdx, 'desc']] : [],
            dom: '<"table-controls-header d-flex align-items-center justify-content-between flex-wrap gap-2"<"d-flex align-items-center"l><"d-flex align-items-center"f>><"table-responsive"t><"table-controls-footer d-flex align-items-center justify-content-between flex-wrap gap-2"<"d-flex align-items-center"i><"d-flex align-items-center"p>>',
            drawCallback: function () {
                $(this.api().table().node()).find('tbody tr').addClass('fade-in');
            }
        });
    }

    // ── Mobile Cinema Cards Feed (Tactile Mobile View) ───────────
    function renderMobileCardsFeed(results) {
        const $feed = $('#mobileResultsFeed').empty();
        if (!results || results.length === 0) {
            $feed.addClass('d-none');
            return;
        }

        results.slice(0, 50).forEach(function (row) {
            const title = row.primary_title || row.title || row.name || row.original_title || 'Untitled';
            const titleId = row.title_id || row.person_id || '';
            const year = row.premiered || row.year || row.start_year || '';
            const rating = row.rating || row.average_rating || '';
            const votes = row.votes || '';
            const genres = row.genres || '';
            const posterPath = row.poster_path || '';
            const format = row.type ? (row.type === 'movie' ? 'Movie' : row.type === 'tvSeries' ? 'TV Series' : row.type) : '';
            const country = row.origin_country || row.original_language || '';

            const posterSrc = posterPath ? `https://image.tmdb.org/t/p/w185${escapeHtml(posterPath)}` : '';
            const posterHtml = posterSrc
                ? `<img src="${posterSrc}" class="movie-card-poster" alt="${escapeHtml(title)}" loading="lazy" onerror="this.onerror=null; this.parentElement.innerHTML='<i class=\\\'fa-solid fa-clapperboard poster-placeholder-icon\\\'></i>';">`
                : `<i class="fa-solid fa-clapperboard poster-placeholder-icon"></i>`;

            const genreChipsHtml = genres
                ? genres.split(',').slice(0, 3).map(g => `<span class="genre-chip-inline">${escapeHtml(g.trim())}</span>`).join('')
                : '';

            const $card = $(`
                <div class="movie-card-mobile fade-in">
                    <div class="movie-card-poster-box">
                        ${posterHtml}
                    </div>
                    <div class="movie-card-content">
                        <div>
                            <div class="movie-card-header-row">
                                <span class="movie-card-title">${escapeHtml(title)}</span>
                                ${rating ? `<span class="badge-rating flex-shrink-0"><i class="fa-solid fa-star text-gold"></i> ${rating}</span>` : ''}
                            </div>
                            <div class="movie-card-meta-row mt-1">
                                ${year ? `<span class="badge-year">${year}</span>` : ''}
                                ${format ? `<span class="text-secondary small fw-medium">${escapeHtml(format)}</span>` : ''}
                                ${country ? `<span class="badge-country-lang">${escapeHtml(String(country).toUpperCase())}</span>` : ''}
                                ${votes ? `<span class="votes-count-cell ms-auto">${Number(votes).toLocaleString()} votes</span>` : ''}
                            </div>
                            ${genreChipsHtml ? `<div class="movie-card-genres mt-1">${genreChipsHtml}</div>` : ''}
                        </div>
                        <div class="movie-card-actions">
                            ${titleId && !titleId.startsWith('nm') ? `
                                <button class="btn-card-synopsis" data-title-id="${escapeHtml(titleId)}" data-title-name="${escapeHtml(title)}">
                                    <i class="fa-solid fa-wand-magic-sparkles"></i> AI Synopsis
                                </button>
                            ` : '<span></span>'}
                            ${titleId ? `
                                <a href="https://www.imdb.com/${titleId.startsWith('nm') ? 'name' : 'title'}/${escapeHtml(titleId)}/" target="_blank" rel="noopener noreferrer" class="btn-card-imdb">
                                    <i class="fa-solid fa-arrow-up-right-from-square"></i> IMDb
                                </a>
                            ` : ''}
                        </div>
                    </div>
                </div>
            `);

            $feed.append($card);
        });

        $feed.removeClass('d-none');
    }

    // ── Interactive Filters ───────────────────────────────────────
    function initializeFilters() {
        $('#toggleFiltersBtn').on('click', function () {
            $('#filterPanel').toggleClass('d-none');
        });

        $('#applyFilters').on('click', applyClientFilters);
        $('#clearFilters').on('click', function () {
            resetFilters();
            applyClientFilters();
        });

        $('#yearMin, #yearMax, #ratingMin, #ratingMax').on('keydown', function (e) {
            if (e.key === 'Enter') applyClientFilters();
        });
    }

    function buildGenreFilters(results) {
        const genres = new Set();
        results.forEach(function (r) {
            if (r.genres) {
                r.genres.split(',').forEach(g => genres.add(g.trim()));
            }
        });

        const $container = $('#genreFilters').empty();
        activeGenreFilters.clear();

        if (genres.size === 0) {
            $container.html('<span class="text-muted small">No genre metadata available</span>');
            return;
        }

        Array.from(genres).sort().forEach(function (genre) {
            const $chip = $('<button class="chip-filter"></button>')
                .text(genre)
                .on('click', function () {
                    $(this).toggleClass('active');
                    if ($(this).hasClass('active')) {
                        activeGenreFilters.add(genre);
                    } else {
                        activeGenreFilters.delete(genre);
                    }
                });
            $container.append($chip);
        });
    }

    function applyClientFilters() {
        const yearMin = parseInt($('#yearMin').val()) || 0;
        const yearMax = parseInt($('#yearMax').val()) || 9999;
        const ratingMin = parseFloat($('#ratingMin').val()) || 0;
        const ratingMax = parseFloat($('#ratingMax').val()) || 10;
        const genresActive = activeGenreFilters.size > 0;

        const filtered = allResults.filter(function (row) {
            const year = row.premiered || row.year || row.start_year;
            if (year != null) {
                const y = parseInt(year);
                if (!isNaN(y) && (y < yearMin || y > yearMax)) return false;
            }

            const rating = row.rating || row.average_rating;
            if (rating != null) {
                const r = parseFloat(rating);
                if (!isNaN(r) && (r < ratingMin || r > ratingMax)) return false;
            }

            if (genresActive && row.genres) {
                const rowGenres = row.genres.split(',').map(g => g.trim());
                const hasMatch = rowGenres.some(g => activeGenreFilters.has(g));
                if (!hasMatch) return false;
            } else if (genresActive && !row.genres) {
                return false;
            }

            return true;
        });

        let count = 0;
        if (yearMin > 0 || yearMax < 9999) count++;
        if (ratingMin > 0 || ratingMax < 10) count++;
        if (genresActive) count++;

        const $badge = $('#activeFilterCount');
        if (count > 0) {
            $badge.text(count).removeClass('d-none');
        } else {
            $badge.addClass('d-none');
        }

        $('#resultCount').text(filtered.length.toLocaleString());
        renderResultsTable(filtered, allColumnNames);
        renderMobileCardsFeed(filtered);
    }

    function resetFilters() {
        activeGenreFilters.clear();
        $('#yearMin, #yearMax, #ratingMin, #ratingMax').val('');
        $('.chip-filter').removeClass('active');
        $('#activeFilterCount').addClass('d-none');
    }

    // ── URL Sharing & Popstate ────────────────────────────────────
    function initializeShareableURL() {
        window.addEventListener('popstate', function () {
            const params = new URLSearchParams(window.location.search);
            const q = params.get('q');
            if (q) {
                $('#query').val(q);
                toggleClearButton(true);
                executeSearch(q);
            }
        });

        $('#copyLinkBtn').on('click', function () {
            const url = window.location.href;
            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(url).then(function () {
                    showToast('Shareable query link copied!');
                }).catch(function () {
                    fallbackCopy(url);
                });
            } else {
                fallbackCopy(url);
            }
        });
    }

    function fallbackCopy(text) {
        const input = document.createElement('input');
        input.value = text;
        document.body.appendChild(input);
        input.select();
        document.execCommand('copy');
        document.body.removeChild(input);
        showToast('Link copied to clipboard!');
    }

    // ── Suggested Query Chips ─────────────────────────────────────
    function initializeSuggestedChips() {
        $(document).on('click', '.cinema-chip[data-query]', function () {
            const q = $(this).attr('data-query');
            $('#query').val(q);
            toggleClearButton(true);
            executeSearch(q);
        });
    }

    // ── SQL Terminal Copy ─────────────────────────────────────────
    function initializeSQLInspector() {
        $('#copySqlBtn').on('click', function () {
            const sqlText = $('#sqlDisplay').text();
            if (!sqlText) return;
            navigator.clipboard.writeText(sqlText).then(function () {
                showToast('SQL statement copied to clipboard!');
            }).catch(function () {
                fallbackCopy(sqlText);
            });
        });
    }

    // ── AI Synopsis Modal ─────────────────────────────────────────
    function initializeAISummary() {
        $(document).on('click', '.btn-ai-synopsis, .btn-card-synopsis', function () {
            if (!ensureApiKeyConfigured()) return;
            const titleId = $(this).data('title-id');
            const titleName = $(this).data('title-name');
            
            const modalEl = document.getElementById('aiSummaryModal');
            const modal = new bootstrap.Modal(modalEl);
            modal.show();

            $('#aiSummaryLoading').removeClass('d-none');
            $('#aiSummaryContent, #aiSummaryError').addClass('d-none');
            $('#aiSummaryTitle').text(titleName);
            
            generateAISummary(titleId, titleName);
        });

        $('#regenerateSummary').on('click', function () {
            const titleId = $(this).data('title-id');
            const titleName = $(this).data('title-name');
            if (titleId && titleName) {
                $('#aiSummaryLoading').removeClass('d-none');
                $('#aiSummaryContent, #aiSummaryError').addClass('d-none');
                generateAISummary(titleId, titleName);
            }
        });
    }

    function generateAISummary(titleId, titleName) {
        $.ajax({
            url: '/api/generate_summary',
            method: 'POST',
            contentType: 'application/json',
            headers: getCustomAzureHeaders(),
            data: JSON.stringify({ title_id: titleId, title_name: titleName }),
            timeout: 100000,
            success: function (response) {
                if (response.success) {
                    displayAISummary(response.title_name, response.summary, titleId, titleName);
                } else {
                    showAISummaryError(response.error || 'Unable to generate synopsis.', titleId, titleName);
                }
            },
            error: function (xhr, status) {
                let msg = 'Failed to generate synopsis.';
                if (status === 'timeout') msg = 'Synopsis generation took too long. Please try again.';
                else if (xhr.responseJSON && xhr.responseJSON.error) msg = xhr.responseJSON.error;
                showAISummaryError(msg, titleId, titleName);
            }
        });
    }

    function displayAISummary(titleName, summary, titleId, originalName) {
        $('#aiSummaryLoading, #aiSummaryError').addClass('d-none');
        $('#aiSummaryTitle').text(titleName);
        $('#aiSummaryText').html(formatSummaryText(summary));
        $('#aiSummaryContent').removeClass('d-none');
        $('#regenerateSummary').data('title-id', titleId).data('title-name', originalName).show();
    }

    function showAISummaryError(msg, titleId, titleName) {
        $('#aiSummaryLoading, #aiSummaryContent').addClass('d-none');
        $('#aiSummaryErrorMessage').text(msg);
        $('#aiSummaryError').removeClass('d-none');
        $('#regenerateSummary').data('title-id', titleId).data('title-name', titleName).show();
    }

    function formatSummaryText(summary) {
        let text = summary
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/#{1,6}\s(.+)/g, '<strong>$1</strong>')
            .trim();

        if (!text.includes('<p>')) {
            text = text.split(/\n\s*\n/)
                .map(s => s.trim()).filter(s => s.length > 0)
                .map(s => `<p>${s.replace(/\n/g, '<br>')}</p>`)
                .join('');
        }
        return text;
    }

    function escapeHtml(unsafe) {
        if (!unsafe || typeof unsafe !== 'string') return '';
        return unsafe
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }
});