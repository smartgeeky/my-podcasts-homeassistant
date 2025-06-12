// We define these functions outside the DOMContentLoaded event to make them globally accessible
// Function to display all episodes in a modal window
window.showAllEpisodes = async function() {
    // If the modal window is not already in the DOM, add it
    if (!document.getElementById('episodesModal')) {
        const modalHTML = `
            <div id="episodesModal" class="modal-overlay">
                <div class="modal-container">
                    <div class="modal-header">
                        <h2 class="modal-title" data-i18n="episodes.all_latest_episodes">All Latest Episodes</h2>
                        <button class="close-modal" onclick="closeModal()">&times;</button>
                    </div>
                    <div class="modal-content">
                        <div id="modalEpisodesList" class="modal-episodes-list">
                            <div class="loading">
                                <p data-i18n="states.loading_episodes">Loading episodes...</p>
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button onclick="closeModal()" data-i18n="episodes.close">Close</button>
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHTML);
        
        // Translation application for the newly added modal window
        if (window.i18n) {
            window.i18n.applyTranslations();
        }
    }
    
    // Show modal window
    const modal = document.getElementById('episodesModal');
    modal.style.display = 'flex';
    
    // Load all recently added episodes
    await loadAllLatestEpisodes();
};

// Function to close a modal window
window.closeModal = function() {
    const modal = document.getElementById('episodesModal');
    if (modal) {
        modal.style.display = 'none';
    }
};

// Feature to download all the latest added episodes
async function loadAllLatestEpisodes() {
    const ingressBase = window.location.pathname.replace(/\/$/, '');
    const modalEpisodesList = document.getElementById('modalEpisodesList');
    
    try {
        // Show loading status
        modalEpisodesList.innerHTML = `
            <div class="loading">
                throw new Error(window.i18n.t('states.error_loading'));
            </div>
        `;
        
        // Gets the as_user parameter from the URL if it exists
        const urlParams = new URLSearchParams(window.location.search);
        const asUserId = urlParams.get('as_user');
        
        // Constructs the URL for the API call, taking into account the as_user parameter
        let apiUrl = `${ingressBase}/api/latest_episodes?limit=100`;
        if (asUserId) {
            apiUrl += `&as_user=${asUserId}`;
        }
        
        // Get all recently added unlistened episodes (no limit)
        const response = await fetch(apiUrl);
        
        if (!response.ok) {
            throw new Error(window.i18n.t('states.error_loading'));
        }
        
        const episodes = await response.json();
        
        if (episodes.length === 0) {
            modalEpisodesList.innerHTML = `
                <div class="empty-state">
                    <p data-i18n="episodes.no_episodes">No episodes to display.</p>
                </div>
            `;
            return;
        }
        
        // Show episode list
        modalEpisodesList.innerHTML = episodes.map(episode => {
            // Format date to a more readable format
            const date = new Date(episode.datum_izdaje);
            const formattedDate = `${date.getDate()}. ${date.getMonth() + 1}. ${date.getFullYear()}`;
            
            // Use a placeholder image if podcast image is not available
                const imageUrl = episode.image_url || 'https://via.placeholder.com/60';
                const userInfo = episode.user_display_name ? ` (${episode.user_display_name})` : '';
                
                return `
                    <div class="episode-item" onclick="goToPodcastEpisode(${episode.podcast_id}, ${episode.id}, ${asUserId ? asUserId : 'null'})">
                        <img class="episode-thumbnail" 
                            src="${imageUrl}"
                            alt="${episode.podcast_naslov}"
                            onerror="this.src='https://via.placeholder.com/60'">
                        <div class="episode-details">
                            <div class="episode-title">${episode.naslov}${userInfo}</div>
                            <div class="episode-podcast-name">${episode.podcast_naslov}</div>
                            <div class="episode-date">${formattedDate}</div>
                        </div>
                    </div>
                `;
            }).join('');
    } catch (error) {
        console.error('Error loading all latest episodes:', error);
        modalEpisodesList.innerHTML = `
            <div class="error-state">
                <p>Error loading episodes: ${error.message}</p>
            </div>
        `;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const ingressBase = window.location.pathname.replace(/\/$/, '');
    const podcastForm = document.getElementById('podcastForm');
    const podcastList = document.getElementById('podcastList');
    const toast = document.getElementById('toast');
    const latestEpisodesList = document.getElementById('latestEpisodesList');

    // Initialize user on page load
    fetch(`${ingressBase}/api/init_user`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Error initializing user');
            }
            return response.json();
        })
        .then(userData => {
            
        })
        .catch(error => {
            console.error('Error initializing user:', error);
        });

    // Show toast message function
    function showToast(message, type = 'info') {
        toast.textContent = message;
        toast.style.display = 'block';
        toast.style.backgroundColor = type === 'error' ? '#dc3545' : '#28a745';
        
        setTimeout(() => {
            toast.style.display = 'none';
        }, 3000);
    }

    // Show loading state
    function showLoading() {
        podcastList.innerHTML = `
            <div class="loading">
                <p data-i18n="states.loading_podcasts">Loading podcasts...</p>
            </div>
        `;
    }

    // Load all podcasts on page load
    loadPodcasts();
    
    // Load latest episodes on page load
    if (latestEpisodesList) {
        loadLatestEpisodes();
    }

    // Load paused episodes on page load
    loadPausedEpisodes();


    // Add new podcast event listener
    if (podcastForm) {
        podcastForm.addEventListener('submit', async (event) => {
            event.preventDefault();
            const naslov = document.getElementById('naslov').value.trim();
            const rssUrl = document.getElementById('rssUrl').value.trim();
            // Added support for isPublic checkbox
            const isPublic = document.getElementById('isPublic').checked ? 1 : 0;

            if (!naslov || !rssUrl) {
                showToast(window.i18n.t('messages.fill_all_fields'), 'error');
                return;
            }

            try {
                const submitButton = podcastForm.querySelector('button[type="submit"]');
                submitButton.disabled = true;
                submitButton.textContent = window.i18n.t('forms.submit_adding');

                const response = await fetch(`${ingressBase}/api/podcasts`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        naslov, 
                        rss_url: rssUrl,
                        is_public: isPublic 
                    }),
                });

                if (response.ok) {
                    showToast(window.i18n.t('messages.podcast_added'));
                    loadPodcasts();
                    podcastForm.reset();
                    // Also re-download the latest episodes as a new podcast may be added
                    if (latestEpisodesList) {
                        loadLatestEpisodes();
                    }
                    // Reloads paused episodes as well
                    loadPausedEpisodes();
                } else {
                    const error = await response.json();
                    throw new Error(error.error || 'Error adding podcast.');
                }
            } catch (error) {
                showToast(error.message, 'error');
            } finally {
                const submitButton = podcastForm.querySelector('button[type="submit"]');
                submitButton.disabled = false;
                submitButton.textContent = window.i18n.t('forms.submit_add');
            }
        });
    }

    // Load all podcasts
    async function loadPodcasts() {
        try {
            if (!podcastList) return; // Check if an element exists
        
            showLoading();
            const response = await fetch(`${ingressBase}/api/podcasts`);
        
            if (!response.ok) {
                throw new Error('Error loading podcasts.');
            }

            const podcasts = await response.json();

            if (podcasts.length === 0) {
                podcastList.innerHTML = `
                    <div class="empty-state">
                        <p>No podcasts added yet. Add your first one!</p>
                    </div>
                `;
                return;
            }

            // First, we get information about the current user
            const userResponse = await fetch(`${ingressBase}/api/users/current`);
            if (!userResponse.ok) {
                throw new Error('Error fetching user data.');
            }
            const currentUser = await userResponse.json();

            podcastList.innerHTML = podcasts.map(podcast => {
                // Determine if the user owns the podcast
                const isOwner = podcast.user_id === currentUser.id;
                // Determine whether to show the hide button (only for other users' public podcasts)
                const showHideButton = podcast.is_public && !isOwner;
                
                    return `
                        <div class="podcast-card">
                            <img src="${podcast.image_url || 'https://via.placeholder.com/150'}" 
                                alt="${podcast.naslov}"
                                onerror="this.src='https://via.placeholder.com/150'">
                            <h3>${podcast.naslov}</h3>
        
                            <div class="podcast-status-row">
                                ${podcast.is_public ? `<span class="public-badge">${window.i18n.t('forms.public_podcast_short') || 'Public'}</span>` : ''}
                                ${showHideButton ? `
                                    <button onclick="hidePodcast(${podcast.id}, this)" class="hide-btn" title="${window.i18n.t('navigation.hide')}">
                                        <span class="hide-icon">🚫</span>
                                    </button>
                                ` : ''}
                            </div>
        
                            <div class="card-buttons">
                                <button onclick="goToPodcast(${podcast.id})">
                                    ${window.i18n.t('navigation.open_podcast')}
                                </button>
                                ${(isOwner || currentUser.is_admin) ? `
                                    <button onclick="deletePodcast(${podcast.id})" class="delete-btn">
                                        ${window.i18n.t('navigation.delete')}
                                    </button>
                                ` : ''}
                            </div>
                        </div>
                    `;
            }).join('');
        } catch (error) {
            if (podcastList) {
                podcastList.innerHTML = `
                    <div class="error-state">
                        <p>Error loading podcasts: ${error.message}</p>
                    </div>
                `;
            }
        }
    }

    // Load latest episodes
    async function loadLatestEpisodes() {
    try {
        if (!latestEpisodesList) return; // Check if an element exists
        
        latestEpisodesList.innerHTML = `
            <div class="loading">
                <p data-i18n="states.loading_episodes">Loading episodes...</p>
            </div>
        `;

        // Gets the as_user parameter from the URL if it exists
        const urlParams = new URLSearchParams(window.location.search);
        const asUserId = urlParams.get('as_user');

        // Compose URL for API call
        let apiUrl = `${ingressBase}/api/latest_episodes?limit=8`;
        if (asUserId) {
            apiUrl += `&as_user=${asUserId}`;
        }

        const response = await fetch(apiUrl);
        
        if (!response.ok) {
            throw new Error('Error loading latest episodes.');
        }

        const episodes = await response.json();

        if (episodes.length === 0) {
            latestEpisodesList.innerHTML = `
                <div class="empty-state">
                    <p data-i18n="episodes.no_episodes">No episodes to display.</p>
                </div>
            `;
            return;
        }

        latestEpisodesList.innerHTML =
            episodes.map(episode => {
                // Format date to a more readable format
                const date = new Date(episode.datum_izdaje);
                const formattedDate = `${date.getDate()}. ${date.getMonth() + 1}. ${date.getFullYear()}`;
                
                // Use a placeholder image if podcast image is not available
                const imageUrl = episode.image_url || 'https://via.placeholder.com/60';
                
                // Add listening status
                const listenedIcon = episode.poslušano ? '✅ ' : '';
                
                return `
                    <div class="episode-item" onclick="goToPodcastEpisode(${episode.podcast_id}, ${episode.id}, ${asUserId ? asUserId : 'null'})">
                        <img class="episode-thumbnail" 
                             src="${imageUrl}"
                             alt="${episode.podcast_naslov}"
                             onerror="this.src='https://via.placeholder.com/60'">
                        <div class="episode-details">
                            <div class="episode-title">${listenedIcon}${episode.naslov}</div>
                            <div class="episode-podcast-name">${episode.podcast_naslov}</div>
                            <div class="episode-date">${formattedDate}</div>
                        </div>
                    </div>
                `;
            }).join('') +
            `<div class="view-all-button" onclick="showAllEpisodes()">
                ${window.i18n.t('episodes.show_all_episodes')}
            </div>`;
    } catch (error) {
        if (latestEpisodesList) {
            latestEpisodesList.innerHTML = `
                <div class="error-state">
                    <p>Error loading latest episodes: ${error.message}</p>
                </div>
            `;
        }
    }
}

    // Load paused episodes
    async function loadPausedEpisodes() {
        const pausedEpisodesList = document.getElementById('pausedEpisodesList');
        const pausedEpisodesContainer = document.getElementById('pausedEpisodesContainer');
        
        if (!pausedEpisodesList || !pausedEpisodesContainer) return;
        
        try {
            // Gets the as_user parameter from the URL if it exists
            const urlParams = new URLSearchParams(window.location.search);
            const asUserId = urlParams.get('as_user');

            // Compose URL for API call
            let apiUrl = `${ingressBase}/api/episodes/paused?limit=3`;
            if (asUserId) {
                apiUrl += `&as_user=${asUserId}`;
            }

            const response = await fetch(apiUrl);
            
            if (!response.ok) {
                throw new Error('Error loading paused episodes.');
            }

            const episodes = await response.json();

            if (episodes.length === 0) {
                // Hide section if no episodes are paused
                pausedEpisodesContainer.style.display = 'none';
                return;
            }

            // Show section
            pausedEpisodesContainer.style.display = 'block';

            pausedEpisodesList.innerHTML = episodes.map(episode => {
                // Use a placeholder image if podcast image is not available
                const imageUrl = episode.image_url || 'https://via.placeholder.com/60';
                
                return `
                    <div class="episode-item paused-episode" onclick="goToPodcastEpisode(${episode.podcast_id}, ${episode.episode_id}, ${asUserId ? asUserId : 'null'})">
                        <img class="episode-thumbnail" 
                             src="${imageUrl}"
                             alt="${episode.podcast_naslov}"
                             onerror="this.src='https://via.placeholder.com/60'">
                        <div class="episode-details">
                            <div class="episode-title">${episode.episode_naslov}</div>
                            <div class="episode-podcast-name">${episode.podcast_naslov}</div>
                            <div class="episode-playback-time">⏸️ ${window.i18n.t('episodes.position')} ${episode.playback_time_formatted}</div>
                        </div>
                    </div>
                `;
            }).join('');
        } catch (error) {
            console.error('Error loading paused episodes:', error);
            // In case of error, hide section
            pausedEpisodesContainer.style.display = 'none';
        }
    }

    // Event listeners for pagination
    const pageInput = document.getElementById('pageInput');
    if (pageInput) {
        pageInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                goToPage();
            }
        });
    }

    // Update all podcasts
    window.updateAllPodcasts = async function() {
        try {
            const updateButton = document.querySelector('.divider-button');
            if (!updateButton) return;
            
            updateButton.disabled = true;
            updateButton.textContent = 'Updating...';

            const response = await fetch(`${ingressBase}/api/podcasts/update_all`, {
                method: 'POST'
            });

            if (response.ok) {
                showToast(window.i18n.t('messages.all_podcasts_updated'));
                await loadPodcasts();
                // Reload the latest episodes too
                if (latestEpisodesList) {
                    loadLatestEpisodes();
                }
                // Reloads paused episodes as well
                loadPausedEpisodes();
            } else {
                throw new Error('Error updating podcasts.');
            }
            } catch (error) {
                showToast(error.message, 'error');
            } finally {
            const updateButton = document.querySelector('.divider-button');
            if (updateButton) {
                    updateButton.disabled = false;
                    updateButton.textContent = window.i18n.t('navigation.update_all');
                }
            }
    };

    // Navigate to settings page
    window.goToSettings = function() {
        window.location.href = `${ingressBase}/settings.html`;
    };

    // Delete podcast
    window.deletePodcast = async function(podcastId) {
        try {
            // Check podcast usage first
            const checkResponse = await fetch(`${ingressBase}/api/podcasts/${podcastId}/check_usage`);
            
            if (!checkResponse.ok) {
                const errorData = await checkResponse.json();
                throw new Error(errorData.error || 'Error checking podcast.');
            }
            
            const usageData = await checkResponse.json();
            
            // Depending on the result of the check, choose an action.
            if (usageData.can_delete) {
                // Can be deleted directly
                let confirmMessage = window.i18n.t('messages.confirm_delete_podcast');
                if (usageData.reason === 'admin_user') {
                    confirmMessage = window.i18n.t('messages.confirm_delete_podcast_admin');
                } else if (usageData.reason === 'hidden_with_history') {
                    // ... nothing extra ...
                }
                if (!confirm(confirmMessage)) return;
                // Direct deletion
                await performPodcastDeletion(podcastId);
            } else {
                // Cannot be deleted directly
                if (usageData.reason === 'hidden_with_history') {
                    // Only admin can delete
                    showToast(usageData.message, 'error');
                    return;
                } else if (usageData.reason === 'visible_users') {
                    // Offer a hiding option
                    const userChoice = confirm(
                        `${usageData.message}\n\n` +
                        'Choose action:\n' +
                        'OK = Hide podcast for me\n' +
                        'Cancel = Keep podcast'
                    );
                    if (userChoice) {
                        // Hide a podcast instead of deleting it
                        await hidePodcast(podcastId, document.querySelector(`[onclick*="deletePodcast(${podcastId})"]`));
                    }
                    return;
                }
            }
            
        } catch (error) {
            showToast(error.message, 'error');
        }
    };

    // Auxiliary function for actual deletion
    async function performPodcastDeletion(podcastId) {
        try {
            const response = await fetch(`${ingressBase}/api/podcasts/${podcastId}`, {
                method: 'DELETE',
            });

            if (response.ok) {
                showToast(window.i18n.t('messages.podcast_deleted'));
                await loadPodcasts();
                // Reload the latest episodes too
                if (latestEpisodesList) {
                    loadLatestEpisodes();
                }
                // Reloads paused episodes as well
                loadPausedEpisodes();
            } else {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Error deleting podcast.');
            }
        } catch (error) {
            showToast(error.message, 'error');
        }
    }

    // Navigate to podcast
    window.goToPodcast = function(podcastId) {
        window.location.href = `${ingressBase}/podcast.html?id=${podcastId}`;
    };

    // We add functionality to read the as_user parameter from the URL
    function getAsUserIdFromUrl() {
        const params = new URLSearchParams(window.location.search);
        return params.get('as_user');
    }

    // Let's update the navigation function on podcast.html
    window.goToPodcastEpisode = function(podcastId, episodeId, asUserId) {
        if (!asUserId || asUserId === 'null') {
            asUserId = getAsUserIdFromUrl();
        }
        const url = `${ingressBase}/podcast.html?id=${podcastId}&episode=${episodeId}${asUserId ? `&as_user=${asUserId}` : ''}`;
        window.location.href = url;
    };

    // We're updating the feature for marking episodes as listened to
    window.playEpisode = async function(url, episodeId) {
        const audioPlayer = document.getElementById('audioPlayer');
        audioPlayer.src = url;
        audioPlayer.play();
    
        // Mark episode as listened
        try {
            // Get as_user_id from URL if it exists
            const urlParams = new URLSearchParams(window.location.search);
            const asUserId = urlParams.get('as_user');
        
            // We prepare the data for the claim
            const requestData = asUserId ? { as_user_id: parseInt(asUserId) } : {};
        
            const response = await fetch(`${ingressBase}/api/episodes/mark_listened/${episodeId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestData)
            });
        
            if (response.ok) {
                // Reload episodes to update UI
                await loadEpisodes();
            } else {
                console.error('Failed to mark episode as listened:', await response.text());
            }
        } catch (error) {
            console.error('Error marking episode as listened:', error);
        }
    }

    // Feature to hide podcast
    window.hidePodcast = async function(podcastId, buttonElement) {
        if (!confirm(window.i18n.t('messages.confirm_hide_podcast'))) return;
        
        try {
            const response = await fetch(`${ingressBase}/api/podcasts/${podcastId}/hide`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
        
            if (!response.ok) {
                throw new Error('Error hiding podcast.');
            }
        
            showToast(window.i18n.t('messages.podcast_hidden'));
        
            // Let's remove the entire podcast-card element
            if (buttonElement) {
                const podcastCard = buttonElement.closest('.podcast-card');
                if (podcastCard) {
                    podcastCard.style.transition = 'all 0.3s ease';
                    podcastCard.style.opacity = '0';
                    setTimeout(() => {
                        podcastCard.remove();
                    }, 300);
                } else {
                    // If we don't find the item, we reload all podcasts.
                    await loadPodcasts();
                }
            } else {
                // If buttonElement is not specified, reload all podcasts
                await loadPodcasts();
            }
        
            // We're also re-uploading the latest episodes, as we've hidden the podcast
            if (latestEpisodesList) {
                loadLatestEpisodes();
            }
            // Reloads paused episodes as well
            loadPausedEpisodes();
        } catch (error) {
            showToast(error.message, 'error');
        }
    };

    // Let's update the playback feature on your device
    window.playOnDevice = async function(episodeUrl, episodeTitle, playerEntityId, episodeId) {
        if (!playerEntityId) return;
    
        try {
            const response = await fetch(`${ingressBase}/api/play_episode`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    player_entity_id: playerEntityId,
                    episode_url: episodeUrl,
                    episode_title: episodeTitle
                })
            });
        
            if (!response.ok) throw new Error('Error playing episode');
        
            // Mark episode as listened (taking into account the as_user parameter)
            const asUserId = getAsUserIdFromUrl();
            const requestData = asUserId ? { as_user_id: parseInt(asUserId) } : {};
        
            const listenResponse = await fetch(`${ingressBase}/api/episodes/mark_listened/${episodeId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestData)
            });
        
            if (!listenResponse.ok) {
                console.error('Failed to mark episode as listened:', await listenResponse.text());
            }
        
            // Reload episodes to update UI
            await loadEpisodes();
        
            const result = await response.json();
            alert(result.message);
        } catch (error) {
            alert(window.i18n.t('messages.device_playback_error', {error: error.message}));
        }
    };

    // Copy playlist URL
    window.copyPlaylistUrl = function() {
        const playlistInput = document.getElementById('playlistUrl');
        if (!playlistInput) return;
        
        playlistInput.select();
        navigator.clipboard.writeText(playlistInput.value)
            .then(() => showToast(window.i18n.t('messages.url_copied')))
            .catch(() => showToast(window.i18n.t('messages.copy_error'), 'error'));
    };
});

// The following functions are available globally
// for use within podcast.html

// Pagination variables
let currentPage = 1;
let pageSize = 5;
let totalEpisodes = 0;

// Episode download feature
async function loadEpisodes() {
    if (typeof podcastId === 'undefined' || !document.getElementById('episodes')) return;
    
    const episodesDiv = document.getElementById('episodes');
    try {
        const response = await fetch(`${ingressBase}/api/episodes/${podcastId}`);
        if (!response.ok) throw new Error(window.i18n.t('states.error_loading'));

        const episodes = await response.json();
        totalEpisodes = episodes.length;

        const start = (currentPage - 1) * pageSize;
        const end = start + pageSize;
        const pageEpisodes = episodes.slice(start, end);

        episodesDiv.innerHTML = pageEpisodes.map(episode => {
            // Escape special characters in title
            const safeTitle = episode.naslov.replace(/['"\\]/g, char => '\\' + char);
            
            return `
                <div class="episode">
                    <strong>${episode.naslov} ${episode.poslušano ? '✅' : ''}</strong>
                    <p>Datum izdaje: ${episode.datum_izdaje}</p>
                    <div class="episode-controls">
                        <button onclick="playEpisode('${episode.url}', ${episode.id})" class="play-button">
                            ${episode.poslušano ? 'Ponovno predvajaj' : 'Predvajaj'} v brskalniku
                        </button>
                        <select 
                            class="player-select" 
                            onchange="playOnDevice('${episode.url}', '${safeTitle}', this.value, ${episode.id})"
                            aria-label="${window.i18n.t('forms.select_player')} ${safeTitle}"
                        >
                           <option value="">${window.i18n.t('forms.select_player')}</option>
                        </select>
                        <button onclick="deleteEpisode(${episode.id})" class="delete-button" style="background-color: #dc3545;">
                            ${window.i18n.t('episodes.delete_episode')}
                        </button>
                    </div>
                </div>
            `;
        }).join('');

        updatePagination();
        // Load media players after episodes are rendered
        if (typeof loadMediaPlayers === 'function') {
            await loadMediaPlayers();
        }
    } catch (error) {
        console.error('Error loading episodes:', error);
        episodesDiv.innerHTML = `<div class="error">${error.message}</div>`;
    }
}

function changePage(offset) {
    currentPage += offset;
    loadEpisodes();
}

function updatePagination() {
    const totalPages = Math.ceil(totalEpisodes / pageSize);
    const firstPageBtn = document.getElementById('firstPage');
    const prevPageBtn = document.getElementById('prevPage');
    const nextPageBtn = document.getElementById('nextPage');
    const lastPageBtn = document.getElementById('lastPage');
    const pageInfo = document.getElementById('pageInfo');
    
    if (firstPageBtn) firstPageBtn.disabled = currentPage === 1;
    if (prevPageBtn) prevPageBtn.disabled = currentPage === 1;
    if (nextPageBtn) nextPageBtn.disabled = currentPage === totalPages;
    if (lastPageBtn) lastPageBtn.disabled = currentPage === totalPages;
    if (pageInfo) pageInfo.textContent = window.i18n.t('pagination.page_of', {current: currentPage, total: totalPages});
    
    // Update page input max value
    const pageInput = document.getElementById('pageInput');
    if (pageInput) {
        pageInput.max = totalPages;
        pageInput.placeholder = `1-${totalPages}`;
    }
}

function goToFirstPage() {
    currentPage = 1;
    loadEpisodes();
}

function goToLastPage() {
    const totalPages = Math.ceil(totalEpisodes / pageSize);
    currentPage = totalPages;
    loadEpisodes();
}

function goToPage() {
    const pageInput = document.getElementById('pageInput');
    if (!pageInput) return;
    
    const totalPages = Math.ceil(totalEpisodes / pageSize);
    let targetPage = parseInt(pageInput.value);

    if (isNaN(targetPage)) {
        alert(window.i18n.t('pagination.invalid_page'));
        return;
    }

    // Ensure page number is within valid range
    targetPage = Math.max(1, Math.min(targetPage, totalPages));
    
    if (targetPage !== currentPage) {
        currentPage = targetPage;
        loadEpisodes();
    }

    // Clear input after navigation
    pageInput.value = '';
}