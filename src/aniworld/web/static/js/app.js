// AniWorld Downloader Web Interface JavaScript

document.addEventListener('DOMContentLoaded', function () {
    // Security helper
    function sanitizeUrl(url) {
        if (!url) return '';
        const lower = url.toLowerCase();
        if (lower.startsWith('javascript:') || lower.startsWith('vbscript:') || lower.startsWith('data:')) {
            return '';
        }
        return url.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    console.log('AniWorld Downloader Web Interface loaded');

    // Get UI elements
    const versionDisplay = document.getElementById('version-display');
    const navTitle = document.getElementById('nav-title');
    const searchInput = document.getElementById('search-input');
    const searchBtn = document.getElementById('search-btn');
    const resultsSection = document.getElementById('results-section');
    const resultsContainer = document.getElementById('results-container');
    const loadingSection = document.getElementById('loading-section');
    const emptyState = document.getElementById('empty-state');
    const homeContent = document.getElementById('home-content');
    const homeLoading = document.getElementById('home-loading');
    const popularNewSections = document.getElementById('popular-new-sections');
    const popularAnimeGrid = document.getElementById('popular-anime-grid');
    const newAnimeGrid = document.getElementById('new-anime-grid');

    // Theme toggle elements
    const themeToggle = document.getElementById('theme-toggle');
    const themeIcon = document.getElementById('theme-icon');

    // Download modal elements
    const downloadModal = document.getElementById('download-modal');
    const closeDownloadModal = document.getElementById('close-download-modal');
    const cancelDownload = document.getElementById('cancel-download');
    const confirmDownload = document.getElementById('confirm-download');
    const selectAllBtn = document.getElementById('select-all');
    const deselectAllBtn = document.getElementById('deselect-all');
    const episodeTreeLoading = document.getElementById('episode-tree-loading');
    const episodeTree = document.getElementById('episode-tree');
    const selectedEpisodeCount = document.getElementById('selected-episode-count');
    const providerSelect = document.getElementById('provider-select');
    const languageSelect = document.getElementById('language-select');

    // Queue elements
    const queueSection = document.getElementById('queue-section');
    const activeDownloads = document.getElementById('active-downloads');
    const completedDownloads = document.getElementById('completed-downloads');
    const activeQueueList = document.getElementById('active-queue-list');
    const completedQueueList = document.getElementById('completed-queue-list');

    // Current download data
    let currentDownloadData = null;
    let availableEpisodes = {};
    let availableMovies = [];
    let selectedEpisodes = new Set();
    let progressInterval = null;
    let availableProviders = [];

    // Load version info and providers on page load
    loadVersionInfo();

    // Check for active downloads on page load
    checkQueueStatus();
    loadAvailableProviders();

    // Load popular and new anime on page load
    loadPopularAndNewAnime();

    // Initialize theme (default is dark mode)
    initializeTheme();

    // Search functionality
    if (searchBtn) {
        searchBtn.addEventListener('click', performSearch);
    }
    if (searchInput) {
        searchInput.addEventListener('keypress', function (e) {
            if (e.key === 'Enter') {
                performSearch();
            }
        });
    }

    // Download modal functionality
    if (closeDownloadModal) {
        closeDownloadModal.addEventListener('click', hideDownloadModal);
    }
    if (cancelDownload) {
        cancelDownload.addEventListener('click', hideDownloadModal);
    }
    if (confirmDownload) {
        confirmDownload.addEventListener('click', startDownload);
    }
    if (selectAllBtn) {
        selectAllBtn.addEventListener('click', selectAllEpisodes);
    }
    if (deselectAllBtn) {
        deselectAllBtn.addEventListener('click', deselectAllEpisodes);
    }

    // Keep Updated checkbox - auto-select all episodes and show interval
    const keepUpdatedCheckbox = document.getElementById('keep-updated-checkbox');
    const intervalGroup = document.getElementById('interval-group');
    if (keepUpdatedCheckbox) {
        keepUpdatedCheckbox.addEventListener('change', function () {
            if (intervalGroup) {
                intervalGroup.style.display = this.checked ? 'block' : 'none';
            }
            // Auto-select all episodes when Keep Updated is enabled (if episodes are loaded)
            if (this.checked && availableEpisodes && Object.keys(availableEpisodes).length > 0) {
                selectAllEpisodes();
            }
        });
    }

    // Custom path radio buttons
    const pathStandard = document.getElementById('path-standard');
    const pathCustom = document.getElementById('path-custom');
    const customPathGroup = document.getElementById('custom-path-group');

    if (pathStandard) {
        pathStandard.addEventListener('change', function () {
            if (customPathGroup && this.checked) {
                customPathGroup.style.display = 'none';
            }
        });
    }

    if (pathCustom) {
        pathCustom.addEventListener('change', function () {
            if (customPathGroup && this.checked) {
                customPathGroup.style.display = 'block';
            }
        });
    }

    // Browse button functionality
    const browseBtn = document.getElementById('browse-path-btn');
    if (browseBtn) {
        browseBtn.addEventListener('click', function () {
            const originalText = browseBtn.innerHTML;
            browseBtn.disabled = true;
            browseBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

            fetch('/api/browse-directory', {
                method: 'POST'
            })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        const customPathInput = document.getElementById('custom-path-input');
                        if (customPathInput) {
                            customPathInput.value = data.path;
                        }
                    } else if (data.message && data.message !== 'No directory selected') {
                        showNotification(data.message, 'info');
                    }
                })
                .catch(error => {
                    console.error('Error browsing directory:', error);
                    showNotification('Failed to open directory picker', 'error');
                })
                .finally(() => {
                    browseBtn.disabled = false;
                    browseBtn.innerHTML = originalText;
                });
        });
    }

    // Edit Sync Job Modal functionality
    const editSyncModal = document.getElementById('edit-sync-modal');
    const closeEditSyncBtn = document.getElementById('close-edit-sync-modal');
    const cancelEditSyncBtn = document.getElementById('cancel-edit-sync');
    const saveEditSyncBtn = document.getElementById('save-edit-sync');

    if (editSyncModal) {
        // Close handlers
        const closeEditModal = () => {
            editSyncModal.style.display = 'none';
            window.currentEditingJobId = null;
        };

        if (closeEditSyncBtn) closeEditSyncBtn.addEventListener('click', closeEditModal);
        if (cancelEditSyncBtn) cancelEditSyncBtn.addEventListener('click', closeEditModal);

        // Close on outside click
        editSyncModal.addEventListener('click', function (e) {
            if (e.target === editSyncModal) closeEditModal();
        });

        // Save handler
        if (saveEditSyncBtn) {
            saveEditSyncBtn.addEventListener('click', function () {
                if (!window.currentEditingJobId) return;

                const interval = document.getElementById('edit-interval-select').value;
                const path = document.getElementById('edit-custom-path-input').value;
                const enabled = document.getElementById('edit-enabled-checkbox').checked;

                saveEditSyncBtn.disabled = true;
                saveEditSyncBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';

                fetch(`/api/sync/${window.currentEditingJobId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        check_interval: parseFloat(interval),
                        custom_path: path.trim() || null,
                        enabled: enabled
                    })
                })
                    .then(r => r.json())
                    .then(data => {
                        if (data.success) {
                            showNotification('Sync job updated', 'success');
                            closeEditModal();
                            window.loadSyncJobs();
                        } else {
                            showNotification(data.error || 'Update failed', 'error');
                        }
                    })
                    .catch(err => {
                        console.error(err);
                        showNotification('Error updating job', 'error');
                    })
                    .finally(() => {
                        saveEditSyncBtn.disabled = false;
                        saveEditSyncBtn.innerHTML = 'Save Changes';
                    });
            });
        }
    }

    // Theme toggle functionality (only if element exists)
    if (themeToggle) {
        themeToggle.addEventListener('click', toggleTheme);
    }

    // Navbar title click functionality
    if (navTitle) {
        navTitle.addEventListener('click', function () {
            // Clear search input
            if (searchInput) {
                searchInput.value = '';
            }
            // Show home content (original state)
            showHomeContent();
            // Reload popular and new anime
            loadPopularAndNewAnime();
        });
    }

    // Close modal when clicking outside
    if (downloadModal) {
        downloadModal.addEventListener('click', function (e) {
            if (e.target === downloadModal) {
                hideDownloadModal();
            }
        });
    }

    function loadVersionInfo() {
        fetch('/api/info')
            .then(response => response.json())
            .then(data => {
                versionDisplay.textContent = `v${data.version}`;
            })
            .catch(error => {
                console.error('Failed to load version info:', error);
                versionDisplay.textContent = 'v?.?.?';
            });
    }

    function loadAvailableProviders() {
        // This will be called from showDownloadModal with site-specific logic
        // Default providers for initial load (aniworld.to)
        populateProviderDropdown('aniworld.to');
    }

    function populateProviderDropdown(site) {
        if (!providerSelect) {
            return;
        }

        // Define site-specific providers
        let siteProviders = [];
        if (site === 's.to') {
            siteProviders = ['VOE'];
        } else { // aniworld.to or default
            siteProviders = ['VOE', 'Filemoon', 'Vidmoly'];
        }

        providerSelect.innerHTML = '';

        siteProviders.forEach(provider => {
            const option = document.createElement('option');
            option.value = provider;
            option.textContent = provider;
            providerSelect.appendChild(option);
        });

        // Set default to VOE (should always be available)
        providerSelect.value = 'VOE';

        console.log(`Populated providers for ${site}:`, siteProviders);
    }

    function populateLanguageDropdown(site) {
        if (!languageSelect) {
            console.error('Language select element not found!');
            return;
        }

        console.log('Populating language dropdown for site:', site);
        languageSelect.innerHTML = '';

        // Define site-specific languages based on actual runtime availability
        let availableLanguages = [];
        if (site === 's.to') {
            // Based on runtime error: s.to only supports ['German Dub', 'English Dub']
            availableLanguages = ['German Dub', 'English Dub'];
        } else { // aniworld.to or default
            availableLanguages = ['German Dub', 'English Sub', 'German Sub'];
        }

        availableLanguages.forEach(language => {
            const option = document.createElement('option');
            option.value = language;
            option.textContent = language;
            languageSelect.appendChild(option);
        });

        // Set default based on site - use setTimeout to ensure DOM is updated
        setTimeout(() => {
            if (site === 's.to') {
                languageSelect.value = 'German Dub'; // s.to default
                console.log('Set default language for s.to to:', languageSelect.value);
                console.log('Verify s.to language value after setting:', languageSelect.value);
            } else {
                languageSelect.value = 'German Sub'; // aniworld default
                console.log('Set default language for aniworld to:', languageSelect.value);
                console.log('Verify aniworld language value after setting:', languageSelect.value);
            }
        }, 0);
    }

    function performSearch() {
        const query = searchInput.value.trim();
        if (!query) {
            // If search is empty, show home content again
            showHomeContent();
            return;
        }

        // Get selected site
        const selectedSite = document.querySelector('input[name="site"]:checked').value;

        // Show loading state
        showLoadingState();
        searchBtn.disabled = true;
        searchBtn.textContent = 'Searching...';

        fetch('/api/search', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                query: query,
                site: selectedSite
            })
        })
            .then(response => {
                if (response.status === 401) {
                    // Authentication required - redirect to login
                    window.location.href = '/login';
                    return;
                }
                return response.json();
            })
            .then(data => {
                if (!data) return; // Handle redirect case
                if (data.success) {
                    displaySearchResults(data.results);
                } else {
                    showNotification(data.error || 'Search failed', 'error');
                    showEmptyState();
                }
            })
            .catch(error => {
                console.error('Search error:', error);
                showNotification('Search failed. Please try again.', 'error');
                showEmptyState();
            })
            .finally(() => {
                searchBtn.disabled = false;
                searchBtn.textContent = 'Search';
                hideLoadingState();
            });
    }

    function displaySearchResults(results) {
        if (!results || results.length === 0) {
            showEmptyState();
            return;
        }

        resultsContainer.innerHTML = '';

        results.forEach(anime => {
            const animeCard = createAnimeCard(anime);
            resultsContainer.appendChild(animeCard);
        });

        showResultsSection();
    }

    function createAnimeCard(anime) {
        const card = document.createElement('div');
        card.className = 'anime-card';

        // Handle cover image
        let coverStyle = '';
        if (anime.cover) {
            let coverUrl = anime.cover;
            // Make URL absolute if it's relative
            if (!coverUrl.startsWith('http')) {
                if (coverUrl.startsWith('//')) {
                    coverUrl = 'https:' + coverUrl;
                } else if (coverUrl.startsWith('/')) {
                    // Determine base URL based on site
                    const baseUrl = anime.site === 's.to' ? 'https://s.to' : 'https://aniworld.to';
                    coverUrl = baseUrl + coverUrl;
                } else {
                    const baseUrl = anime.site === 's.to' ? 'https://s.to' : 'https://aniworld.to';
                    coverUrl = baseUrl + '/' + coverUrl;
                }
            }

            // Upgrade image resolution from 150x225 to 220x330 for better quality
            coverUrl = coverUrl.replace("150x225", "220x330");

            coverStyle = `style="background-image: url('${sanitizeUrl(coverUrl)}') "`;
        }

        card.innerHTML = `
            <div class="anime-card-background" ${coverStyle}></div>
            <div class="anime-card-content">
                <div class="anime-title">${escapeHtml(anime.title)}</div>
                <div class="anime-info">
                    <strong>Site:</strong> ${escapeHtml(anime.site || 'aniworld.to')}<br>
                    <strong>Slug:</strong> ${escapeHtml(anime.slug || 'Unknown')}<br>
                    ${anime.description ? `<strong>Description:</strong> ${escapeHtml(anime.description)}<br>` : ''}
                </div>
                <div class="anime-actions">
                    <button class="download-btn">
                        Download
                    </button>
                </div>
            </div>
        `;

        // Add event listener for the download button to avoid onclick string issues
        const downloadBtn = card.querySelector('.download-btn');
        downloadBtn.addEventListener('click', () => {
            showDownloadModal(anime.title, 'Series', anime.url);
        });

        return card;
    }

    function showDownloadModal(animeTitle, episodeTitle, episodeUrl) {
        // Reset Sync UI
        const existingWarning = document.getElementById('sync-warning-msg');
        if (existingWarning) existingWarning.remove();
        const keepUpdatedCheckbox = document.getElementById('keep-updated-checkbox');
        if (keepUpdatedCheckbox) {
            keepUpdatedCheckbox.disabled = false;
            keepUpdatedCheckbox.checked = false;
            keepUpdatedCheckbox.title = "";
        }
        const intervalSelect = document.getElementById('interval-select');
        if (intervalSelect) intervalSelect.disabled = false;

        // Detect site from URL
        let detectedSite = 'aniworld.to'; // default
        if (episodeUrl.includes('/serie/stream/') || episodeUrl.includes('186.2.175.5')) {
            detectedSite = 's.to';
        }

        currentDownloadData = {
            anime: animeTitle,
            episode: episodeTitle,
            url: episodeUrl,
            site: detectedSite,
            downloadPath: '/Downloads' // Default path - will be fetched from backend
        };

        // Reset selection state
        selectedEpisodes.clear();
        availableEpisodes = {};

        // Populate modal
        document.getElementById('download-anime-title').textContent = animeTitle;

        // Populate language dropdown based on site
        populateLanguageDropdown(detectedSite);

        // Populate provider dropdown based on site
        populateProviderDropdown(detectedSite);

        // Show loading state for episodes
        episodeTreeLoading.style.display = 'flex';
        episodeTree.style.display = 'none';
        updateSelectedCount();

        // Fetch download path from backend
        fetch('/api/download-path')
            .then(response => response.json())
            .then(data => {
                currentDownloadData.downloadPath = data.path;
                document.getElementById('download-path').textContent = data.path;

            })
            .catch(error => {
                console.error('Failed to fetch download path:', error);
                document.getElementById('download-path').textContent = 'Unknown';
            });

        // Fetch episodes for this series
        fetch('/api/episodes', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                series_url: episodeUrl
            })
        })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    availableEpisodes = data.episodes;
                    availableMovies = data.movies || [];
                    renderEpisodeTree();

                    // Auto-select all episodes if Keep Updated is already checked
                    const keepUpdatedCheckbox = document.getElementById('keep-updated-checkbox');
                    if (keepUpdatedCheckbox && keepUpdatedCheckbox.checked) {
                        selectAllEpisodes();
                    }
                } else {
                    showNotification(data.error || 'Failed to load episodes', 'error');
                }
            })
            .catch(error => {
                console.error('Failed to fetch episodes:', error);
                showNotification('Failed to load episodes', 'error');
            })
            .finally(() => {
                episodeTreeLoading.style.display = 'none';
                episodeTree.style.display = 'block';
            });

        // Check for existing sync job
        fetch('/api/sync')
            .then(r => r.json())
            .then(data => {
                if (data.success && data.sync_jobs) {
                    const match = data.sync_jobs.find(j =>
                        j.series_url === currentDownloadData.url ||
                        j.anime_title === currentDownloadData.anime
                    );

                    if (match) {
                        const cb = document.getElementById('keep-updated-checkbox');
                        if (cb) {
                            const container = document.querySelector('.download-settings');
                            let warning = document.getElementById('sync-warning-msg');
                            if (!warning && container) {
                                warning = document.createElement('div');
                                warning.id = 'sync-warning-msg';
                                warning.style.cssText = "padding: 10px; margin-bottom: 10px; border-radius: 4px; background: #ebf8ff; color: #2c5282; border-left: 4px solid #4299e1; font-size: 0.9em;";
                                warning.innerHTML = `<i class="fas fa-info-circle"></i> <strong>Already monitored:</strong> Interval ${match.check_interval}h`;
                                container.insertBefore(warning, container.firstChild);
                            }
                            cb.checked = true;
                            cb.disabled = true;
                            cb.title = "Manage this sync job in the Sync tab";

                            const intervalSelect = document.getElementById('interval-select');
                            if (intervalSelect) {
                                intervalSelect.value = match.check_interval;
                                intervalSelect.disabled = true;
                            }
                            const intervalGroup = document.getElementById('interval-group');
                            if (intervalGroup) intervalGroup.style.display = 'block';
                        }
                    }
                }
            });

        downloadModal.style.display = 'flex';
    }

    function hideDownloadModal() {
        downloadModal.style.display = 'none';
        currentDownloadData = null;
        selectedEpisodes.clear();
        availableEpisodes = {};
        availableMovies = [];
    }

    function renderEpisodeTree() {
        episodeTree.innerHTML = '';

        // Render seasons and episodes
        Object.keys(availableEpisodes).sort((a, b) => Number(a) - Number(b)).forEach(seasonNum => {
            const season = availableEpisodes[seasonNum];

            // Create season container
            const seasonContainer = document.createElement('div');
            seasonContainer.className = 'season-container';

            // Season header with checkbox
            const seasonHeader = document.createElement('div');
            seasonHeader.className = 'season-header';

            const seasonCheckbox = document.createElement('input');
            seasonCheckbox.type = 'checkbox';
            seasonCheckbox.className = 'season-checkbox';
            seasonCheckbox.id = `season-${seasonNum}`;
            seasonCheckbox.addEventListener('change', () => toggleSeason(seasonNum));

            const seasonLabel = document.createElement('label');
            seasonLabel.htmlFor = `season-${seasonNum}`;
            seasonLabel.textContent = `Season ${seasonNum} (${season.length} episodes)`;
            seasonLabel.className = 'season-label';

            seasonHeader.appendChild(seasonCheckbox);
            seasonHeader.appendChild(seasonLabel);

            // Episodes container
            const episodesContainer = document.createElement('div');
            episodesContainer.className = 'episodes-container';

            season.forEach(episode => {
                const episodeItem = document.createElement('div');
                episodeItem.className = 'episode-item-tree';

                const episodeCheckbox = document.createElement('input');
                episodeCheckbox.type = 'checkbox';
                episodeCheckbox.className = 'episode-checkbox';
                const episodeId = `${episode.season}-${episode.episode}`;
                episodeCheckbox.id = `episode-${episodeId}`;
                episodeCheckbox.addEventListener('change', () => toggleEpisode(episode, episodeCheckbox.checked));

                const episodeLabel = document.createElement('label');
                episodeLabel.htmlFor = `episode-${episodeId}`;
                episodeLabel.textContent = episode.title;
                episodeLabel.className = 'episode-label';

                episodeItem.appendChild(episodeCheckbox);
                episodeItem.appendChild(episodeLabel);
                episodesContainer.appendChild(episodeItem);
            });

            seasonContainer.appendChild(seasonHeader);
            seasonContainer.appendChild(episodesContainer);
            episodeTree.appendChild(seasonContainer);
        });

        // Render movies section if available
        if (availableMovies && availableMovies.length > 0) {
            const moviesContainer = document.createElement('div');
            moviesContainer.className = 'season-container';

            // Movies header with checkbox
            const moviesHeader = document.createElement('div');
            moviesHeader.className = 'season-header';

            const moviesCheckbox = document.createElement('input');
            moviesCheckbox.type = 'checkbox';
            moviesCheckbox.className = 'season-checkbox';
            moviesCheckbox.id = 'movies-section';
            moviesCheckbox.addEventListener('change', () => toggleMovies());

            const moviesLabel = document.createElement('label');
            moviesLabel.htmlFor = 'movies-section';
            moviesLabel.textContent = `Movies (${availableMovies.length} movies)`;
            moviesLabel.className = 'season-label';

            moviesHeader.appendChild(moviesCheckbox);
            moviesHeader.appendChild(moviesLabel);

            // Movies items container
            const moviesItemsContainer = document.createElement('div');
            moviesItemsContainer.className = 'episodes-container';

            availableMovies.forEach(movie => {
                const movieItem = document.createElement('div');
                movieItem.className = 'episode-item-tree';

                const movieCheckbox = document.createElement('input');
                movieCheckbox.type = 'checkbox';
                movieCheckbox.className = 'episode-checkbox';
                const movieId = `movie-${movie.movie}`;
                movieCheckbox.id = `movie-${movieId}`;
                movieCheckbox.addEventListener('change', () => toggleMovie(movie, movieCheckbox.checked));

                const movieLabel = document.createElement('label');
                movieLabel.htmlFor = `movie-${movieId}`;
                movieLabel.textContent = movie.title;
                movieLabel.className = 'episode-label';

                movieItem.appendChild(movieCheckbox);
                movieItem.appendChild(movieLabel);
                moviesItemsContainer.appendChild(movieItem);
            });

            moviesContainer.appendChild(moviesHeader);
            moviesContainer.appendChild(moviesItemsContainer);
            episodeTree.appendChild(moviesContainer);
        }

        updateSelectedCount();
    }

    function toggleSeason(seasonNum) {
        const season = availableEpisodes[seasonNum];
        const seasonCheckbox = document.getElementById(`season-${seasonNum}`);
        const isChecked = seasonCheckbox.checked;

        season.forEach(episode => {
            const episodeId = `${episode.season}-${episode.episode}`;
            const episodeCheckbox = document.getElementById(`episode-${episodeId}`);

            if (episodeCheckbox) {
                episodeCheckbox.checked = isChecked;
                toggleEpisode(episode, isChecked);
            }
        });
    }

    function toggleEpisode(episode, isSelected) {
        const episodeKey = `${episode.season}-${episode.episode}`;

        if (isSelected) {
            selectedEpisodes.add(episodeKey);
        } else {
            selectedEpisodes.delete(episodeKey);
        }

        // Update season checkbox state
        updateSeasonCheckboxState(episode.season);
        updateSelectedCount();
    }

    function updateSeasonCheckboxState(seasonNum) {
        const season = availableEpisodes[seasonNum];
        const seasonCheckbox = document.getElementById(`season-${seasonNum}`);

        if (!seasonCheckbox || !season) return;

        const seasonEpisodes = season.map(ep => `${ep.season}-${ep.episode}`);
        const selectedInSeason = seasonEpisodes.filter(key => selectedEpisodes.has(key));

        if (selectedInSeason.length === seasonEpisodes.length) {
            seasonCheckbox.checked = true;
            seasonCheckbox.indeterminate = false;
        } else if (selectedInSeason.length > 0) {
            seasonCheckbox.checked = false;
            seasonCheckbox.indeterminate = true;
        } else {
            seasonCheckbox.checked = false;
            seasonCheckbox.indeterminate = false;
        }
    }

    function toggleMovies() {
        const moviesCheckbox = document.getElementById('movies-section');
        const isChecked = moviesCheckbox.checked;

        availableMovies.forEach(movie => {
            const movieId = `movie-${movie.movie}`;
            const movieCheckbox = document.getElementById(`movie-${movieId}`);

            if (movieCheckbox) {
                movieCheckbox.checked = isChecked;
                toggleMovie(movie, isChecked);
            }
        });
    }

    function toggleMovie(movie, isSelected) {
        const movieKey = `movie-${movie.movie}`;

        if (isSelected) {
            selectedEpisodes.add(movieKey);
        } else {
            selectedEpisodes.delete(movieKey);
        }

        // Update movies section checkbox state
        updateMoviesCheckboxState();
        updateSelectedCount();
    }

    function updateMoviesCheckboxState() {
        const moviesCheckbox = document.getElementById('movies-section');

        if (!moviesCheckbox || !availableMovies || availableMovies.length === 0) return;

        const movieKeys = availableMovies.map(movie => `movie-${movie.movie}`);
        const selectedMovies = movieKeys.filter(key => selectedEpisodes.has(key));

        if (selectedMovies.length === movieKeys.length) {
            moviesCheckbox.checked = true;
            moviesCheckbox.indeterminate = false;
        } else if (selectedMovies.length > 0) {
            moviesCheckbox.checked = false;
            moviesCheckbox.indeterminate = true;
        } else {
            moviesCheckbox.checked = false;
            moviesCheckbox.indeterminate = false;
        }
    }

    function selectAllEpisodes() {
        // Select all episodes
        Object.values(availableEpisodes).flat().forEach(episode => {
            const episodeKey = `${episode.season}-${episode.episode}`;
            const episodeCheckbox = document.getElementById(`episode-${episodeKey}`);

            if (episodeCheckbox) {
                episodeCheckbox.checked = true;
                selectedEpisodes.add(episodeKey);
            }
        });

        // Select all movies
        availableMovies.forEach(movie => {
            const movieKey = `movie-${movie.movie}`;
            const movieCheckbox = document.getElementById(`movie-${movieKey}`);

            if (movieCheckbox) {
                movieCheckbox.checked = true;
                selectedEpisodes.add(movieKey);
            }
        });

        // Update all season checkboxes
        Object.keys(availableEpisodes).forEach(seasonNum => {
            updateSeasonCheckboxState(seasonNum);
        });

        // Update movies checkbox
        updateMoviesCheckboxState();

        updateSelectedCount();
    }

    function deselectAllEpisodes() {
        selectedEpisodes.clear();

        // Uncheck all checkboxes
        document.querySelectorAll('.episode-checkbox, .season-checkbox').forEach(checkbox => {
            checkbox.checked = false;
            checkbox.indeterminate = false;
        });

        updateSelectedCount();
    }

    function updateSelectedCount() {
        const count = selectedEpisodes.size;

        // Count episodes and movies separately for better display
        const episodeCount = Array.from(selectedEpisodes).filter(key => !key.startsWith('movie-')).length;
        const movieCount = Array.from(selectedEpisodes).filter(key => key.startsWith('movie-')).length;

        let countText = '';
        if (episodeCount > 0 && movieCount > 0) {
            countText = `${episodeCount} episode${episodeCount !== 1 ? 's' : ''} and ${movieCount} movie${movieCount !== 1 ? 's' : ''} selected`;
        } else if (episodeCount > 0) {
            countText = `${episodeCount} episode${episodeCount !== 1 ? 's' : ''} selected`;
        } else if (movieCount > 0) {
            countText = `${movieCount} movie${movieCount !== 1 ? 's' : ''} selected`;
        } else {
            countText = 'No items selected';
        }

        selectedEpisodeCount.textContent = countText;

        // Enable/disable download button based on selection
        confirmDownload.disabled = count === 0;
    }

    function startDownload() {
        if (!currentDownloadData || selectedEpisodes.size === 0) {
            showNotification('Please select at least one episode or movie to download', 'error');
            return;
        }

        // Show loading state
        confirmDownload.disabled = true;
        confirmDownload.textContent = 'Starting...';

        // Collect selected episode and movie URLs
        const selectedEpisodeUrls = [];
        selectedEpisodes.forEach(episodeKey => {
            if (episodeKey.startsWith('movie-')) {
                // Handle movie
                const movieNum = episodeKey.split('-')[1];
                const movieData = availableMovies.find(movie => movie.movie == movieNum);
                if (movieData) {
                    selectedEpisodeUrls.push(movieData.url);
                }
            } else {
                // Handle episode
                const [season, episode] = episodeKey.split('-').map(Number);
                const episodeData = availableEpisodes[season]?.find(ep => ep.season === season && ep.episode === episode);
                if (episodeData) {
                    selectedEpisodeUrls.push(episodeData.url);
                }
            }
        });

        // Get selected provider and language from dropdowns
        const selectedProvider = providerSelect.value || 'VOE';

        // Get language value without fallback first to see what's actually selected
        const rawLanguageValue = languageSelect.value;

        // Get language from dropdown - use site-appropriate fallback if empty
        const selectedLanguage = rawLanguageValue || (currentDownloadData.site === 's.to' ? 'German Dub' : 'German Sub');

        // Debug logging
        console.log('Raw language value:', rawLanguageValue);
        console.log('Selected language (final):', selectedLanguage);
        console.log('Selected provider:', selectedProvider);
        console.log('Site:', currentDownloadData.site);

        // Validate that we have a real selection
        if (!rawLanguageValue) {
            console.warn('Warning: No language selected from dropdown, using fallback');
        }

        // Get sync-related parameters
        const keepUpdated = keepUpdatedCheckbox ? keepUpdatedCheckbox.checked : false;
        const intervalSelect = document.getElementById('interval-select');
        const checkInterval = intervalSelect ? intervalSelect.value : 24;
        const useCustomPath = pathCustom ? pathCustom.checked : false;
        const customPathInput = document.getElementById('custom-path-input');
        const customPath = useCustomPath && customPathInput ? customPathInput.value.trim() : '';

        // Create request payload and log it
        const requestPayload = {
            episode_urls: selectedEpisodeUrls,
            language: selectedLanguage,
            provider: selectedProvider,
            anime_title: currentDownloadData.anime,
            keep_updated: keepUpdated,
            check_interval: parseFloat(checkInterval),
            custom_path: customPath || null,
            series_url: currentDownloadData.url || ''
        };

        console.log('Download payload:', requestPayload);

        fetch('/api/download', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestPayload)
        })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const count = selectedEpisodes.size;
                    let message = `Download started for ${count} episode${count !== 1 ? 's' : ''}`;
                    if (data.sync_job_id) {
                        message += ' (Auto-sync enabled)';
                    }
                    showNotification(message, 'success');
                    hideDownloadModal();
                    startQueueTracking();
                } else {
                    showNotification(data.error || 'Download failed to start', 'error');
                }
            })
            .catch(error => {
                console.error('Download error:', error);
                showNotification('Failed to start download', 'error');
            })
            .finally(() => {
                confirmDownload.disabled = false;
                confirmDownload.textContent = 'Start Download';
            });
    }

    function showLoadingState() {
        homeContent.style.display = 'none';
        emptyState.style.display = 'none';
        resultsSection.style.display = 'none';
        loadingSection.style.display = 'block';
    }

    function hideLoadingState() {
        loadingSection.style.display = 'none';
    }

    function showResultsSection() {
        homeContent.style.display = 'none';
        emptyState.style.display = 'none';
        loadingSection.style.display = 'none';
        resultsSection.style.display = 'block';
    }

    function showEmptyState() {
        homeContent.style.display = 'none';
        resultsSection.style.display = 'none';
        loadingSection.style.display = 'none';
        emptyState.style.display = 'block';
    }

    function showHomeContent() {
        resultsSection.style.display = 'none';
        loadingSection.style.display = 'none';
        emptyState.style.display = 'none';
        homeContent.style.display = 'block';
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function startQueueTracking() {
        // Start polling for queue status updates
        progressInterval = setInterval(updateQueueDisplay, 2000); // Poll every 2 seconds
        updateQueueDisplay(); // Initial update
    }

    function checkQueueStatus() {
        // Check queue status on page load to show any active downloads
        fetch('/api/queue-status')
            .then(response => response.json())
            .then(data => {
                if (data.success && data.queue) {
                    const activeItems = data.queue.active || [];
                    const completedItems = data.queue.completed || [];

                    if (activeItems.length > 0 || completedItems.length > 0) {
                        // There are downloads to show, start tracking
                        startQueueTracking();
                    }
                }
            })
            .catch(error => {
                console.error('Initial queue status check error:', error);
            });
    }

    function updateQueueDisplay() {
        fetch('/api/queue-status')
            .then(response => response.json())
            .then(data => {
                if (data.success && data.queue) {
                    const activeItems = data.queue.active || [];
                    const completedItems = data.queue.completed || [];

                    // Show/hide queue section based on content
                    if (activeItems.length > 0 || completedItems.length > 0) {
                        queueSection.style.display = 'block';

                        // Update active downloads
                        if (activeItems.length > 0) {
                            activeDownloads.style.display = 'block';
                            updateQueueList(activeQueueList, activeItems, 'active');
                        } else {
                            activeDownloads.style.display = 'none';
                        }

                        // Update completed downloads
                        if (completedItems.length > 0) {
                            completedDownloads.style.display = 'block';
                            updateQueueList(completedQueueList, completedItems, 'completed');
                        } else {
                            completedDownloads.style.display = 'none';
                        }
                    } else {
                        // No downloads to show
                        queueSection.style.display = 'none';
                        if (progressInterval) {
                            clearInterval(progressInterval);
                            progressInterval = null;
                        }
                    }
                }
            })
            .catch(error => {
                console.error('Queue status update error:', error);
            });
    }

    function cancelDownloadById(queueId) {
        if (!confirm('Are you sure you want to cancel this download?')) {
            return;
        }

        fetch(`/api/cancel-download/${queueId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showNotification('Download cancelled', 'success');
                    updateQueueDisplay(); // Refresh the queue
                } else {
                    showNotification(data.error || 'Failed to cancel download', 'error');
                }
            })
            .catch(error => {
                console.error('Cancel download error:', error);
                showNotification('Failed to cancel download', 'error');
            });
    }

    function updateQueueList(container, items, type) {
        container.innerHTML = '';

        items.forEach(item => {
            const queueItem = document.createElement('div');
            queueItem.className = 'queue-item';

            const overallProgress = item.progress_percentage || 0;
            const episodeProgress = item.current_episode_progress || 0;
            const showProgressBar = item.status === 'downloading' || item.status === 'queued';
            const isDownloading = item.status === 'downloading';


            // Create the HTML content
            const overallProgressClamped = Math.max(0, Math.min(100, overallProgress));
            const episodeProgressClamped = Math.max(0, Math.min(100, episodeProgress));

            // Show cancel button only for active downloads (queued or downloading)
            const showCancelButton = type === 'active' && (item.status === 'queued' || item.status === 'downloading');

            queueItem.innerHTML = `
                <div class="queue-item-header">
                    <div class="queue-item-title">${escapeHtml(item.anime_title)}</div>
                    <div class="queue-item-status-row">
                        <div class="queue-item-status ${item.status}">${item.status}</div>
                        ${showCancelButton ? `
                        <button class="cancel-download-btn" data-queue-id="${item.id}" title="Cancel Download">
                            <i class="fas fa-times"></i>
                        </button>
                        ` : ''}
                    </div>
                </div>
                ${showProgressBar ? `
                <div class="queue-item-progress">
                    <div class="queue-progress-bar">
                        <div class="queue-progress-fill" style="width: ${overallProgressClamped}%; transition: width 0.3s ease;"></div>
                    </div>
                    <div class="queue-progress-text">${overallProgressClamped.toFixed(1)}% | ${item.completed_episodes}/${item.total_episodes} episodes</div>
                </div>
                ${isDownloading ? `
                <div class="queue-item-progress episode-progress">
                    <div class="queue-progress-bar">
                        <div class="queue-progress-fill episode-progress-fill" style="width: ${episodeProgressClamped}%; transition: width 0.3s ease;"></div>
                    </div>
                    <div class="queue-progress-text episode-progress-text">Current Episode: ${episodeProgressClamped.toFixed(1)}%</div>
                </div>
                ` : ''}
                ` : `
                <div class="queue-item-progress">
                    <div class="queue-progress-text">${item.completed_episodes}/${item.total_episodes} episodes</div>
                </div>
                `}
                <div class="queue-item-details">
                    ${escapeHtml(item.current_episode || (item.status === 'completed' ? 'Download completed' : 'Waiting in queue'))}
                </div>
            `;

            // Add cancel button event listener
            if (showCancelButton) {
                const cancelBtn = queueItem.querySelector('.cancel-download-btn');
                if (cancelBtn) {
                    cancelBtn.addEventListener('click', function () {
                        const queueId = this.getAttribute('data-queue-id');
                        cancelDownloadById(queueId);
                    });
                }
            }

            container.appendChild(queueItem);
        });
    }

    function loadPopularAndNewAnime() {
        console.log('Loading popular and new anime...');

        // Show loading state for home content
        homeLoading.style.display = 'block';
        popularNewSections.style.display = 'none';

        fetch('/api/popular-new')
            .then(response => {
                if (response.status === 401) {
                    window.location.href = '/login';
                    return;
                }
                return response.json();
            })
            .then(data => {
                if (!data) return;

                if (data.success) {
                    displayPopularAndNewAnime(data.popular || [], data.new || []);
                } else {
                    console.error('Failed to load popular/new anime:', data.error);
                    showEmptyState();
                }
            })
            .catch(error => {
                console.error('Error loading popular/new anime:', error);
                showEmptyState();
            })
            .finally(() => {
                homeLoading.style.display = 'none';
            });
    }

    function displayPopularAndNewAnime(popularAnime, newAnime) {
        // Clear existing content
        popularAnimeGrid.innerHTML = '';
        newAnimeGrid.innerHTML = '';

        // Populate popular anime (limit to 8)
        popularAnime.slice(0, 8).forEach(anime => {
            const animeCard = createHomeAnimeCard(anime);
            popularAnimeGrid.appendChild(animeCard);
        });

        // Populate new anime (limit to 8)
        newAnime.slice(0, 8).forEach(anime => {
            const animeCard = createHomeAnimeCard(anime);
            newAnimeGrid.appendChild(animeCard);
        });

        // Show the sections
        popularNewSections.style.display = 'block';
        showHomeContent();
    }

    function createHomeAnimeCard(anime) {
        const card = document.createElement('div');
        card.className = 'home-anime-card';

        const defaultCover = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjMwMCIgdmlld0JveD0iMCAwIDIwMCAzMDAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxyZWN0IHdpZHRoPSIyMDAiIGhlaWdodD0iMzAwIiBmaWxsPSIjMzMzIi8+CjxwYXRoIGQ9Ik0xMDAgMTUwTDEyMCAxNzBMMTAwIDE5MFY3MGwyMCAyMEwxMDAgMTEwVjE1MFoiIGZpbGw9IiM2NjYiLz4KPC9zdmc+';

        // Replace image size from 150x225 to 220x330 for higher resolution
        let coverUrl = anime.cover || defaultCover;
        if (coverUrl.includes('_150x225.png')) {
            coverUrl = coverUrl.replace('_150x225.png', '_220x330.png');
        }

        // Truncate title at word boundaries to stay under 68 characters total
        let displayTitle = anime.name;
        if (displayTitle.length > 65) { // Leave room for "..." (3 chars)
            // Find the last space before character 65
            let truncateAt = displayTitle.lastIndexOf(' ', 65);
            if (truncateAt === -1 || truncateAt < 30) {
                // If no space found or space is too early, just cut at 65
                truncateAt = 65;
            }
            displayTitle = displayTitle.substring(0, truncateAt) + '...';
        }

        card.innerHTML = `
            <div class="home-anime-cover">
                <img src="${sanitizeUrl(coverUrl)}" alt="${escapeHtml(anime.name)}" loading="lazy"
                     onerror="this.src='${defaultCover}'">
            </div>
            <div class="home-anime-title" title="${escapeHtml(anime.name)}">
                ${escapeHtml(displayTitle)}
            </div>
        `;

        // Add click handler to search for this anime
        card.addEventListener('click', () => {
            searchInput.value = anime.name;
            performSearch();
        });

        return card;
    }


    // Theme functions
    function initializeTheme() {
        // Check if user has a saved theme preference, default to dark mode
        const savedTheme = localStorage.getItem('theme') || 'dark';
        setTheme(savedTheme);
    }

    function toggleTheme() {
        console.log('Toggle theme clicked'); // Debug log
        const currentTheme = document.body.getAttribute('data-theme') || 'light';
        console.log('Current theme:', currentTheme); // Debug log
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        console.log('New theme:', newTheme); // Debug log
        setTheme(newTheme);
    }

    function setTheme(theme) {
        console.log('Setting theme to:', theme); // Debug log
        if (theme === 'light') {
            document.body.removeAttribute('data-theme');
            if (themeIcon) {
                themeIcon.className = 'fas fa-moon';
            }
            console.log('Switched to light mode'); // Debug log
        } else {
            document.body.setAttribute('data-theme', 'dark');
            if (themeIcon) {
                themeIcon.className = 'fas fa-sun';
            }
            console.log('Switched to dark mode'); // Debug log
        }
        localStorage.setItem('theme', theme);
    }

    // Make showDownloadModal globally accessible
    window.showDownloadModal = showDownloadModal;

    // Tab switching functionality
    const tabButtons = document.querySelectorAll('.tab-nav-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const targetTab = button.getAttribute('data-tab');

            // Remove active class from all buttons and tabs
            tabButtons.forEach(btn => btn.classList.remove('active'));
            tabContents.forEach(content => content.classList.remove('active'));

            // Add active class to clicked button and corresponding tab
            button.classList.add('active');
            const targetContent = document.getElementById(targetTab);
            if (targetContent) {
                targetContent.classList.add('active');
            }

            // If switching to sync tab, load sync jobs
            if (targetTab === 'sync-tab') {
                loadSyncJobs();
            }
        });
    });

    // Sync tab functionality
    function loadSyncJobs() {
        const syncLoading = document.getElementById('sync-loading');
        const syncEmpty = document.getElementById('sync-empty');
        const syncTableContainer = document.getElementById('sync-table-container');
        const syncJobsTbody = document.getElementById('sync-jobs-tbody');

        // Show loading
        if (syncLoading) syncLoading.style.display = 'block';
        if (syncEmpty) syncEmpty.style.display = 'none';
        if (syncTableContainer) syncTableContainer.style.display = 'none';

        fetch('/api/sync')
            .then(response => response.json())
            .then(data => {
                if (data.success && data.sync_jobs && data.sync_jobs.length > 0) {
                    window.allSyncJobs = data.sync_jobs;
                    // Show table
                    if (syncTableContainer) syncTableContainer.style.display = 'block';
                    if (syncJobsTbody) {
                        syncJobsTbody.innerHTML = '';
                        data.sync_jobs.forEach(job => {
                            const row = createSyncJobRow(job);
                            syncJobsTbody.appendChild(row);
                        });
                    }
                } else {
                    // Show empty state
                    if (syncEmpty) syncEmpty.style.display = 'block';
                }
            })
            .catch(error => {
                console.error('Error loading sync jobs:', error);
                if (syncEmpty) syncEmpty.style.display = 'block';
            })
            .finally(() => {
                if (syncLoading) syncLoading.style.display = 'none';
            });
    }

    function createSyncJobRow(job) {
        const row = document.createElement('tr');

        const formatDate = (dateStr) => {
            if (!dateStr) return 'Never';
            const date = new Date(dateStr);
            return date.toLocaleString();
        };

        const statusClass = job.enabled ? 'enabled' : 'disabled';
        const statusText = job.enabled ? 'Enabled' : 'Disabled';

        row.innerHTML = `
            <td>${escapeHtml(job.anime_title)}</td>
            <td>Every ${job.check_interval}h</td>
            <td>${formatDate(job.last_checked)}</td>
            <td>${formatDate(job.last_found_new)}</td>
            <td>${job.last_episode_count || 0}</td>
            <td><span class="sync-status ${statusClass}">${statusText}</span></td>
            <td class="sync-actions">
                <button class="action-btn edit-btn" onclick="editSyncJob(${job.id})" title="Edit">
                    <i class="fas fa-edit"></i>
                </button>
                <button class="action-btn check-btn" onclick="forceCheckSyncJob(${job.id})" title="Check Now">
                    <i class="fas fa-sync"></i>
                </button>
                <button class="action-btn delete-btn" onclick="deleteSyncJob(${job.id})" title="Delete">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        `;

        return row;
    }

    // Make sync functions globally accessible
    window.loadSyncJobs = loadSyncJobs;
    window.editSyncJob = function (jobId) {
        if (!window.allSyncJobs) return;
        const job = window.allSyncJobs.find(j => j.id === jobId);
        if (!job) return;

        window.currentEditingJobId = jobId;

        const titleEl = document.getElementById('edit-sync-title');
        const intervalEl = document.getElementById('edit-interval-select');
        const pathEl = document.getElementById('edit-custom-path-input');
        const enabledEl = document.getElementById('edit-enabled-checkbox');
        const modal = document.getElementById('edit-sync-modal');

        if (titleEl) titleEl.textContent = job.anime_title;
        if (intervalEl) intervalEl.value = job.check_interval;
        if (pathEl) pathEl.value = job.custom_path || '';
        if (enabledEl) enabledEl.checked = job.enabled;

        if (modal) modal.style.display = 'flex';
    };
    window.forceCheckSyncJob = function (jobId) {
        fetch(`/api/sync/${jobId}/check`, { method: 'POST' })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showNotification('Sync check initiated', 'success');
                    setTimeout(loadSyncJobs, 2000);
                } else {
                    showNotification(data.error || 'Failed to check sync job', 'error');
                }
            })
            .catch(error => {
                console.error('Error checking sync job:', error);
                showNotification('Failed to check sync job', 'error');
            });
    };
    window.deleteSyncJob = function (jobId) {
        if (!confirm('Are you sure you want to delete this sync job?')) return;

        fetch(`/api/sync/${jobId}`, { method: 'DELETE' })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showNotification('Sync job deleted', 'success');
                    loadSyncJobs();
                } else {
                    showNotification(data.error || 'Failed to delete sync job', 'error');
                }
            })
            .catch(error => {
                console.error('Error deleting sync job:', error);
                showNotification('Failed to delete sync job', 'error');
            });
    };
});

// Show notification function
function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;

    // Style the notification
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 12px 20px;
        border-radius: 6px;
        color: white;
        font-weight: 500;
        z-index: 1000;
        animation: slideIn 0.3s ease-out;
        max-width: 300px;
        word-wrap: break-word;
    `;

    // Set background color based on type
    switch (type) {
        case 'success':
            notification.style.background = '#48bb78';
            break;
        case 'error':
            notification.style.background = '#f56565';
            break;
        default:
            notification.style.background = '#4299e1';
    }

    // Add to page
    document.body.appendChild(notification);

    // Remove after 3 seconds
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease-in';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, 3000);
}

// Show info modal function
function showInfoModal(data) {
    // Create modal overlay
    const overlay = document.createElement('div');
    overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.5);
        z-index: 1001;
        display: flex;
        justify-content: center;
        align-items: center;
        animation: fadeIn 0.3s ease-out;
    `;

    // Create modal content
    const modal = document.createElement('div');
    modal.style.cssText = `
        background: white;
        border-radius: 12px;
        padding: 2rem;
        max-width: 500px;
        width: 90%;
        max-height: 80vh;
        overflow-y: auto;
        box-shadow: 0 20px 40px rgba(0, 0, 0, 0.2);
        animation: scaleIn 0.3s ease-out;
    `;

    modal.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
            <h2 style="color: #4a5568; margin: 0;">Application Info</h2>
            <button id="close-modal" style="background: none; border: none; font-size: 1.5rem; cursor: pointer; color: #718096;">&times;</button>
        </div>
        <div style="color: #718096;">
            <p><strong>Version:</strong> ${data.version || 'N/A'}</p>
            <p><strong>Status:</strong> ${data.status || 'Running'}</p>
            <p><strong>Uptime:</strong> ${data.uptime || 'N/A'}</p>
            <p><strong>Mode:</strong> Web Interface</p>
        </div>
    `;

    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    // Close modal functionality
    const closeBtn = modal.querySelector('#close-modal');
    const closeModal = () => {
        overlay.style.animation = 'fadeOut 0.3s ease-in';
        setTimeout(() => {
            if (overlay.parentNode) {
                overlay.parentNode.removeChild(overlay);
            }
        }, 300);
    };

    closeBtn.addEventListener('click', closeModal);
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            closeModal();
        }
    });
}

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }

    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }

    @keyframes fadeIn {
        from {
            opacity: 0;
        }
        to {
            opacity: 1;
        }
    }

    @keyframes fadeOut {
        from {
            opacity: 1;
        }
        to {
            opacity: 0;
        }
    }

    @keyframes scaleIn {
        from {
            transform: scale(0.8);
            opacity: 0;
        }
        to {
            transform: scale(1);
            opacity: 1;
        }
    }
`;
document.head.appendChild(style);