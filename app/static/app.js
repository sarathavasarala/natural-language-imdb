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

    initializeSettingsModal();
    initializeSearchControls();
    initializeSuggestedChips();
    initializeFilters();
    initializeShareableURL();
    initializeAISummary();
    initializeSQLInspector();

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
        const $cancelBtn = $('#cancelSearchBtn');
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
        });

        // Cancel / Abort buttons
        $cancelBtn.on('click', cancelActiveSearch);
        $abortBtn.on('click', cancelActiveSearch);

        // Dismiss correction banner
        $dismissCorrBtn.on('click', function () {
            $('#correctionBanner').addClass('d-none');
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

    // ── Live Agent Timer & Activity Timeline ──────────────────────
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

    let lastTimelineMessage = '';

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
        $prevItems.find('.agent-step-icon')
            .removeClass('fa-circle-notch fa-spin fa-satellite-dish fa-brain fa-microchip fa-database fa-magnifying-glass fa-shield-halved fa-wand-magic-sparkles fa-stethoscope fa-arrow-rotate-right')
            .addClass('fa-circle-check text-emerald');
        $prevItems.removeClass('active').addClass('completed');

        const elapsed = ((Date.now() - searchStartTime) / 1000).toFixed(1);
        const $item = $(`
            <div class="agent-step-item ${type} active fade-in">
                <i class="fa-solid ${icon} agent-step-icon"></i>
                <div class="flex-grow-1 min-w-0">
                    <span>${escapeHtml(msg)}</span>
                </div>
                <span class="font-mono text-muted small flex-shrink-0">${elapsed}s</span>
            </div>
        `);
        $timeline.prepend($item);
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

        addTimelineStep('Connecting to Azure AI and preparing prompt...', 'info', 'fa-satellite-dish', 'Initiating Search');

        const headers = { 'Content-Type': 'application/json' };
        const customKey = localStorage.getItem('imdb_azure_api_key');
        const customEndpoint = localStorage.getItem('imdb_azure_endpoint');
        const customModel = localStorage.getItem('imdb_azure_model');
        const customVersion = localStorage.getItem('imdb_azure_api_version');

        if (customKey && customKey.trim()) headers['X-Azure-API-Key'] = customKey.trim();
        if (customEndpoint && customEndpoint.trim()) headers['X-Azure-Endpoint'] = customEndpoint.trim();
        if (customModel && customModel.trim()) headers['X-Azure-Model'] = customModel.trim();
        if (customVersion && customVersion.trim()) headers['X-Azure-API-Version'] = customVersion.trim();

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
        if (event.type === 'status') {
            let icon = 'fa-circle-notch fa-spin';
            let stepType = 'info';
            let title = event.title || 'Processing Query';

            if (event.stage === 'synthesizing' || event.stage === 'generating') {
                icon = 'fa-brain text-gold';
                if (!title) title = 'AI Query Synthesis';
            } else if (event.stage === 'validating') {
                icon = 'fa-shield-halved text-cyan';
                if (!title) title = 'Query Validation';
            } else if (event.stage === 'refining') {
                icon = 'fa-wand-magic-sparkles text-gold';
                if (!title) title = 'Query Optimization';
            } else if (event.stage === 'executing') {
                icon = 'fa-database text-gold';
                if (!title) title = 'Database Execution';
            } else if (event.stage === 'compiling') {
                icon = 'fa-table-cells text-emerald';
                if (!title) title = 'Preparing Results';
            } else if (event.stage === 'probing') {
                icon = 'fa-magnifying-glass text-cyan';
                if (!title) title = 'Zero-Result Diagnostics';
            } else if (event.stage === 'reflecting') {
                icon = 'fa-stethoscope text-gold';
                if (!title) title = 'Intent Diagnostics';
            }

            addTimelineStep(event.message, stepType, icon, title);

        } else if (event.type === 'sql') {
            $('#sqlDisplay').text(event.sql || '-- No SQL');

        } else if (event.type === 'retry') {
            let retryMsg = event.message || 'Searching with closest match...';
            if (event.corrected_entity) {
                retryMsg = `Auto-correcting to "${event.corrected_entity}" & re-querying...`;
            }
            addTimelineStep(retryMsg, 'retry', 'fa-arrow-rotate-right text-gold', 'Auto-Correction');
            if (event.new_sql) {
                $('#sqlDisplay').text(event.new_sql);
            }

        } else if (event.type === 'result') {
            // Mark all items complete
            $('#agentActivityTimeline').find('.agent-step-icon')
                .removeClass('fa-circle-notch fa-spin fa-arrow-rotate-right fa-database fa-brain fa-microchip')
                .addClass('fa-circle-check text-emerald');
            if (event.success && event.results && event.results.length > 0) {
                allResults = event.results;
                allColumnNames = event.column_names;

                showResultsMeta(event);
                buildGenreFilters(allResults);
                renderResultsTable(allResults, allColumnNames);
                resetFilters();

                // Show Auto-Correction Banner if intent reflection was applied
                if (event.correction_note || event.corrected_entity) {
                    const entityLabel = event.corrected_entity ? `<strong>${escapeHtml(event.corrected_entity)}</strong>` : 'closest match';
                    const noteText = event.correction_note ? ` &bull; ${escapeHtml(event.correction_note)}` : '';
                    $('#correctionMessage').html(`Showing results for ${entityLabel} (searched for "<em>${escapeHtml(event.query)}</em>")${noteText}`);
                    $('#correctionBanner').removeClass('d-none');
                } else {
                    $('#correctionBanner').addClass('d-none');
                }

            } else if (event.success && event.row_count === 0) {
                allResults = [];
                hideResultsMeta();
                showNoResults(event);
            } else {
                showError(event.error || 'No matching movies or shows found.', event.suggestions);
            }

        } else if (event.type === 'error') {
            showError(event.error || 'Search could not be completed.', event.suggestions);
        }
    }

    function showLoading() {
        $('#loadingState').removeClass('d-none');
        $('#errorState, #noResultsState, #resultsContainer, #resultsMeta').addClass('d-none');
        $('#searchBtn').addClass('d-none');
        $('#cancelSearchBtn').removeClass('d-none');
        $('#clearQueryBtn').addClass('d-none');
    }

    function hideLoading() {
        $('#loadingState').addClass('d-none');
        $('#searchBtn').removeClass('d-none').prop('disabled', false).html('<i class="fa-solid fa-magnifying-glass me-1"></i> <span>Search</span>');
        $('#cancelSearchBtn').addClass('d-none');
        toggleClearButton($('#query').val().length > 0);
    }

    function showResultsMeta(response) {
        $('#resultsMeta').removeClass('d-none');
        if (response.row_count > response.results.length) {
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
        $('#resultsContainer').addClass('d-none');

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
        $('#resultsContainer, #noResultsState, #resultsMeta').addClass('d-none');
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

    // ── Table Rendering with DataTables ───────────────────────────
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

        // Build Table Header
        columnNames.forEach(function (col) {
            const label = friendlyNames[col] || col.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
            const th = $('<th></th>').text(label);
            if (numericCols.includes(col)) th.attr('data-type', 'numeric');
            $head.append(th);
        });

        // Build Table Rows
        results.forEach(function (row) {
            const $tr = $('<tr></tr>');
            columnNames.forEach(function (col) {
                const val = row[col];
                const $td = $('<td></td>');

                if (col === 'title_id' && val) {
                    $td.html(`<a href="https://www.imdb.com/title/${escapeHtml(val)}/" target="_blank" rel="noopener noreferrer" class="imdb-link-badge"><i class="fa-solid fa-arrow-up-right-from-square"></i> ${escapeHtml(val)}</a>`);
                } else if (col === 'primary_title' && val) {
                    const titleId = row['title_id'] || '';
                    $td.html(`
                        <div class="d-flex align-items-center justify-content-between gap-2">
                            <span class="fw-semibold text-white" style="word-break: break-word; min-width: 0;">${escapeHtml(val)}</span>
                            ${titleId ? `<button class="btn-ai-synopsis flex-shrink-0" data-title-id="${escapeHtml(titleId)}" data-title-name="${escapeHtml(val)}" title="Generate AI Synopsis"><i class="fa-solid fa-wand-magic-sparkles"></i></button>` : ''}
                        </div>
                    `);
                } else if (col === 'rating' && val != null) {
                    $td.html(`<span class="badge-rating"><i class="fa-solid fa-star text-gold"></i> ${val}</span>`);
                    $td.attr('data-sort', val);
                } else if (col === 'votes' && val != null) {
                    $td.html(`<span class="votes-count-cell">${Number(val).toLocaleString()}</span>`);
                    $td.attr('data-sort', val);
                } else if (col === 'premiered' && val) {
                    $td.html(`<span class="badge-year">${val}</span>`);
                    $td.attr('data-sort', val);
                } else if (col === 'genres' && val) {
                    const chips = val.split(',').map(g => `<span class="genre-chip-inline">${escapeHtml(g.trim())}</span>`).join(' ');
                    $td.html(chips);
                } else if (col === 'runtime_minutes' && val) {
                    $td.html(`<span class="font-mono text-secondary">${val} min</span>`);
                    $td.attr('data-sort', val);
                } else {
                    $td.text(val != null ? val : '—');
                    if (numericCols.includes(col) && val != null) $td.attr('data-sort', val);
                }

                $tr.append($td);
            });
            $body.append($tr);
        });

        $('#resultsContainer').removeClass('d-none');
        $('#noResultsState').addClass('d-none');

        const columnDefs = [];
        let votesIdx = -1;
        columnNames.forEach(function (col, idx) {
            if (col === 'votes') votesIdx = idx;
            if (numericCols.includes(col)) {
                columnDefs.push({
                    targets: idx,
                    type: 'num',
                    render: function (data, type, row, meta) {
                        if (type === 'sort' || type === 'type') {
                            const $cell = $($('#resultsTable tbody tr').eq(meta.row).find('td').eq(meta.col));
                            const sv = $cell.attr('data-sort');
                            if (sv !== undefined && sv !== '') return parseFloat(sv) || 0;
                            const n = parseFloat(String(data).replace(/[^0-9.]/g, ''));
                            return isNaN(n) ? 0 : n;
                        }
                        return data;
                    }
                });
            }
        });

        dataTableInstance = $('#resultsTable').DataTable({
            pageLength: 25,
            ordering: true,
            searching: true,
            responsive: true,
            language: {
                search: 'Filter results:',
                lengthMenu: 'Show _MENU_',
                info: 'Showing _START_ to _END_ of _TOTAL_',
                paginate: { first: '«', last: '»', next: '›', previous: '‹' },
                emptyTable: 'No matching movies or shows found',
                zeroRecords: 'No matching records'
            },
            columnDefs: columnDefs,
            order: votesIdx >= 0 ? [[votesIdx, 'desc']] : [],
            dom: '<"row align-items-center mb-3"<"col-sm-6"l><"col-sm-6 d-flex justify-content-sm-end"f>><"table-responsive"t><"row align-items-center mt-3"<"col-sm-6"i><"col-sm-6 d-flex justify-content-sm-end"p>>',
            drawCallback: function () {
                $(this.api().table().node()).find('tbody tr').addClass('fade-in');
            }
        });

        // Smooth scroll towards results
        $('html, body').animate({ scrollTop: $('#resultsMeta').offset().top - 90 }, 350);
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
        $(document).on('click', '.btn-ai-synopsis', function () {
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