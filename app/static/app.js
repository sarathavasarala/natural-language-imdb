// IMDb Intelligence — Simple Search & AI Chat JavaScript
// Components: AJAX Search, Post-Search Filters, Shareable URLs, Suggested Chips, Azure Foundry / OpenAI Settings, AI Summary, AI Chat

// ════════════════════════════════════════════════════
//  GLOBAL AJAX SETUP FOR DYNAMIC AZURE CREDENTIALS
// ════════════════════════════════════════════════════
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

// ════════════════════════════════════════════════════
//  SETTINGS & AZURE FOUNDRY CREDENTIAL MANAGER
// ════════════════════════════════════════════════════
function initializeSettingsModal() {
    const $modal = $('#settingsModal');
    if (!$modal.length) return;

    // Load from LocalStorage into inputs
    const customKey = localStorage.getItem('imdb_azure_api_key') || '';
    const customEndpoint = localStorage.getItem('imdb_azure_endpoint') || '';
    const customModel = localStorage.getItem('imdb_azure_model') || '';
    const customVersion = localStorage.getItem('imdb_azure_api_version') || '';

    $('#customApiKey').val(customKey);
    $('#customEndpoint').val(customEndpoint);
    $('#customModel').val(customModel);
    $('#customApiVersion').val(customVersion);

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
        const key = $('#customApiKey').val().trim();
        const endpoint = $('#customEndpoint').val().trim();
        const model = $('#customModel').val().trim();
        const version = $('#customApiVersion').val().trim();

        if (key) {
            localStorage.setItem('imdb_azure_api_key', key);
        } else {
            localStorage.removeItem('imdb_azure_api_key');
        }

        if (endpoint) {
            localStorage.setItem('imdb_azure_endpoint', endpoint);
        } else {
            localStorage.removeItem('imdb_azure_endpoint');
        }

        if (model) {
            localStorage.setItem('imdb_azure_model', model);
        } else {
            localStorage.removeItem('imdb_azure_model');
        }

        if (version) {
            localStorage.setItem('imdb_azure_api_version', version);
        } else {
            localStorage.removeItem('imdb_azure_api_version');
        }

        updateSettingsBadge();
        showToast('Credentials saved to browser LocalStorage!');
        bootstrap.Modal.getInstance($modal[0])?.hide();
    });

    // Clear Key
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
        showToast('Cleared credentials from browser.');
        bootstrap.Modal.getInstance($modal[0])?.hide();
    });
}

function updateSettingsBadge() {
    const customKey = localStorage.getItem('imdb_azure_api_key');
    const $badge = $('#settingsStatusBadge');
    if (!$badge.length) return;

    if (customKey && customKey.trim()) {
        $badge.removeClass('bg-secondary bg-warning text-dark').addClass('bg-success text-white').html('<i class="fas fa-check-circle me-1"></i> API Key Active');
    } else {
        $badge.removeClass('bg-secondary bg-success text-white').addClass('bg-warning text-dark').html('<i class="fas fa-key me-1"></i> Set API Key');
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
        showToast('Please set your Azure AI Foundry / OpenAI key first.');
        return false;
    }
    return true;
}

function showToast(message) {
    $('#toastMsg').text(message);
    const toastEl = document.getElementById('copyToast');
    if (toastEl) {
        const toast = new bootstrap.Toast(toastEl, { delay: 2500 });
        toast.show();
    }
}

// ════════════════════════════════════════════════════
//  MAIN SEARCH PAGE LOGIC
// ════════════════════════════════════════════════════
$(document).ready(function () {
    console.log('✅ IMDb Intelligence initialized');

    // ── State ──────────────────────────────────────────
    let allResults = [];
    let allColumnNames = [];
    let activeGenreFilters = new Set();
    let dataTableInstance = null;
    let lastQuery = '';

    // ── Init ──────────────────────────────────────────
    initializeSettingsModal();
    initializeSearchForm();
    initializeSuggestedChips();
    initializeFilters();
    initializeShareableURL();
    initializeAISummary();
    initializeTooltips();

    // Check for ?q= in URL and auto-search
    const urlParams = new URLSearchParams(window.location.search);
    const urlQuery = urlParams.get('q');
    if (urlQuery) {
        $('#query').val(urlQuery);
        executeSearch(urlQuery);
    }

    function initializeSearchForm() {
        const $form = $('#searchForm');
        $form.on('submit', function (e) {
            e.preventDefault();
            const query = $('#query').val().trim();
            if (!query) return;
            executeSearch(query);
        });

        $('#query').on('keydown', function (e) {
            if (e.key === 'Escape') {
                $(this).val('').focus();
            }
        });
    }

    function executeSearch(query) {
        if (!ensureApiKeyConfigured()) {
            return;
        }

        lastQuery = query;

        const url = new URL(window.location);
        url.searchParams.set('q', query);
        history.pushState({ query: query }, '', url);

        addToQueryHistory(query);
        showLoading();

        $.ajax({
            url: '/api/search',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ query: query }),
            timeout: 60000,
            success: function (response) {
                hideLoading();

                if (response.success && response.results && response.results.length > 0) {
                    allResults = response.results;
                    allColumnNames = response.column_names;

                    showResultsMeta(response);
                    buildGenreFilters(allResults);
                    renderResultsTable(allResults, allColumnNames);
                    resetFilters();
                } else if (response.success && response.row_count === 0) {
                    allResults = [];
                    hideResultsMeta();
                    showNoResults();
                } else {
                    showError(response.error || 'Unknown error', response.suggestions);
                }
            },
            error: function (xhr) {
                hideLoading();
                let msg = 'Something went wrong. Please try again.';
                let suggestions = [];
                try {
                    const resp = JSON.parse(xhr.responseText);
                    msg = resp.error || msg;
                    suggestions = resp.suggestions || [];
                } catch (_) {}
                showError(msg, suggestions);
            }
        });
    }

    function showLoading() {
        $('#loadingState').removeClass('d-none');
        $('#errorState, #noResultsState, #resultsContainer, #resultsMeta').addClass('d-none');
        $('#searchBtn').prop('disabled', true).html('<i class="fas fa-spinner fa-spin me-1"></i>Searching...');
    }

    function hideLoading() {
        $('#loadingState').addClass('d-none');
        $('#searchBtn').prop('disabled', false).html('<i class="fas fa-bolt me-1"></i>Search');
    }

    function showResultsMeta(response) {
        $('#resultsMeta').removeClass('d-none');
        if (response.row_count > response.results.length) {
            $('#resultCount').text(`${response.results.length.toLocaleString()} (of ${response.row_count.toLocaleString()} total)`);
        } else {
            $('#resultCount').text(response.row_count.toLocaleString());
        }
        $('#executionTime').text(response.execution_time ? `in ${response.execution_time}s` : '');
        $('#sqlDisplay').text(response.sql_query || '');
    }

    function hideResultsMeta() {
        $('#resultsMeta').addClass('d-none');
    }

    function showNoResults() {
        $('#noResultsState').removeClass('d-none');
        $('#resultsContainer').addClass('d-none');
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
                    $('<button class="chip chip-suggestion"></button>')
                        .text(s)
                        .on('click', function () {
                            $('#query').val(s);
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
            'rating': 'Rating',
            'votes': 'Votes',
            'name': 'Name',
            'person_id': 'Person ID',
            'type': 'Type',
            'is_adult': 'Adult',
            'ended': 'Ended',
            'born': 'Born',
            'died': 'Died',
            'category': 'Role',
            'characters': 'Characters',
            'season_number': 'Season',
            'episode_number': 'Episode'
        };

        const numericCols = ['votes', 'rating', 'premiered', 'runtime_minutes', 'season_number', 'episode_number', 'born', 'died', 'ended'];

        columnNames.forEach(function (col) {
            const label = friendlyNames[col] || col.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
            const th = $('<th class="fw-semibold"></th>').text(label);
            if (numericCols.includes(col)) th.attr('data-type', 'numeric');
            $head.append(th);
        });

        results.forEach(function (row) {
            const $tr = $('<tr></tr>');
            columnNames.forEach(function (col) {
                const val = row[col];
                const $td = $('<td></td>');

                if (col === 'title_id' && val) {
                    $td.html(`<a href="https://www.imdb.com/title/${escapeHtml(val)}/" target="_blank" class="text-decoration-none"><i class="fas fa-external-link-alt me-1"></i>${escapeHtml(val)}</a>`);
                } else if (col === 'primary_title' && val) {
                    const titleId = row['title_id'] || '';
                    $td.html(`<div class="d-flex align-items-center"><span class="me-2">${escapeHtml(val)}</span>${titleId ? `<button class="btn btn-sm btn-outline-primary ai-summary-btn" data-title-id="${escapeHtml(titleId)}" data-title-name="${escapeHtml(val)}" title="AI Summary"><i class="fa-solid fa-wand-magic-sparkles"></i></button>` : ''}</div>`);
                } else if (col === 'rating' && val != null) {
                    $td.html(`<span class="badge bg-warning text-dark"><i class="fas fa-star"></i> ${val}</span>`);
                    $td.attr('data-sort', val);
                } else if (col === 'votes' && val != null) {
                    $td.html(`<span class="text-muted">${Number(val).toLocaleString()} votes</span>`);
                    $td.attr('data-sort', val);
                } else if (col === 'premiered' && val) {
                    $td.html(`<span class="badge bg-secondary">${val}</span>`);
                    $td.attr('data-sort', val);
                } else if (col === 'genres' && val) {
                    const chips = val.split(',').map(g => `<span class="genre-chip-inline">${escapeHtml(g.trim())}</span>`).join(' ');
                    $td.html(chips);
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
                lengthMenu: 'Show _MENU_ per page',
                info: 'Showing _START_–_END_ of _TOTAL_',
                paginate: { first: 'First', last: 'Last', next: '→', previous: '←' },
                emptyTable: 'No matching results',
                zeroRecords: 'No matching results'
            },
            columnDefs: columnDefs,
            order: votesIdx >= 0 ? [[votesIdx, 'desc']] : [],
            dom: '<"row"<"col-sm-12 col-md-6"l><"col-sm-12 col-md-6"f>><"row"<"col-sm-12"tr>><"row"<"col-sm-12 col-md-5"i><"col-sm-12 col-md-7"p>>',
            drawCallback: function () {
                $(this.api().table().node()).find('tbody tr').addClass('fade-in');
            }
        });

        $('html, body').animate({ scrollTop: $('#resultsMeta').offset().top - 80 }, 400);
    }

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
            $container.html('<span class="text-muted small">No genre data in these results</span>');
            return;
        }

        Array.from(genres).sort().forEach(function (genre) {
            const $chip = $('<button class="chip chip-filter"></button>')
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

    function initializeShareableURL() {
        window.addEventListener('popstate', function (e) {
            const params = new URLSearchParams(window.location.search);
            const q = params.get('q');
            if (q) {
                $('#query').val(q);
                executeSearch(q);
            }
        });

        $('#copyLinkBtn').on('click', function () {
            const url = window.location.href;
            navigator.clipboard.writeText(url).then(function () {
                showToast('Search link copied!');
            }).catch(function () {
                const input = document.createElement('input');
                input.value = url;
                document.body.appendChild(input);
                input.select();
                document.execCommand('copy');
                document.body.removeChild(input);
                showToast('Search link copied!');
            });
        });
    }

    function initializeSuggestedChips() {
        $(document).on('click', '.chip[data-query]', function () {
            const q = $(this).attr('data-query');
            $('#query').val(q);
            executeSearch(q);
        });
    }

    function initializeAISummary() {
        $(document).on('click', '.ai-summary-btn', function () {
            if (!ensureApiKeyConfigured()) return;
            const titleId = $(this).data('title-id');
            const titleName = $(this).data('title-name');
            $('#aiSummaryModal').modal('show');
            $('#aiSummaryLoading').removeClass('d-none');
            $('#aiSummaryContent').addClass('d-none');
            $('#aiSummaryError').addClass('d-none');
            $('#aiSummaryTitle').text(titleName);
            generateAISummary(titleId, titleName);
        });

        $('#regenerateSummary').on('click', function () {
            const titleId = $(this).data('title-id');
            const titleName = $(this).data('title-name');
            if (titleId && titleName) {
                $('#aiSummaryLoading').removeClass('d-none');
                $('#aiSummaryContent').addClass('d-none');
                $('#aiSummaryError').addClass('d-none');
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
            timeout: 30000,
            success: function (response) {
                if (response.success) {
                    displayAISummary(response.title_name, response.summary, titleId, titleName);
                } else {
                    showAISummaryError(response.error || 'Unknown error', titleId, titleName);
                }
            },
            error: function (xhr, status) {
                let msg = 'Failed to generate summary';
                if (status === 'timeout') msg = 'Request timed out. Try again.';
                else if (xhr.responseJSON && xhr.responseJSON.error) msg = xhr.responseJSON.error;
                showAISummaryError(msg, titleId, titleName);
            }
        });
    }

    function displayAISummary(titleName, summary, titleId, originalName) {
        $('#aiSummaryLoading').addClass('d-none');
        $('#aiSummaryError').addClass('d-none');
        $('#aiSummaryTitle').text(titleName);
        $('#aiSummaryText').html(formatSummaryText(summary));
        $('#aiSummaryContent').removeClass('d-none');
        $('#regenerateSummary').data('title-id', titleId).data('title-name', originalName).show();
    }

    function showAISummaryError(msg, titleId, titleName) {
        $('#aiSummaryLoading').addClass('d-none');
        $('#aiSummaryContent').addClass('d-none');
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

    function initializeTooltips() {
        [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]')).forEach(function (el) {
            new bootstrap.Tooltip(el);
        });
    }

    function addToQueryHistory(query) {
        let history = JSON.parse(localStorage.getItem('queryHistory') || '[]');
        history = history.filter(item => item.query !== query);
        history.unshift({ query: query, timestamp: Date.now() });
        history = history.slice(0, 10);
        localStorage.setItem('queryHistory', JSON.stringify(history));
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