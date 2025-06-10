from flask import Flask, request, jsonify, send_from_directory
import sqlite3
from datetime import datetime, timedelta
import feedparser
import os
import requests
from bs4 import BeautifulSoup
import json
import websockets
import asyncio
from functools import wraps
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import logging

# Global cache for users
# Structure: {'username': {'user_data': {...}, 'timestamp': time.time()}}
USER_CACHE = {}
# Cache validity duration in seconds (1 hour)
CACHE_EXPIRY = 3600  # 1 hour

app = Flask(__name__, static_folder="/app/static")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)  # Added logger definition

# Global variable for tracking update threads
update_thread = None
update_thread_stop_event = threading.Event()

# Global variables for tracking playback sessions
tracking_thread = None
tracking_thread_stop_event = threading.Event()

# Function for database connection
def get_db_connection():
    conn = sqlite3.connect('/data/mypodcasts.db', isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# Function for Home Assistant WebSocket API
async def ha_websocket_call(command):
    """Execute Home Assistant WebSocket API call"""
    supervisor_token = os.environ.get('SUPERVISOR_TOKEN')
    if not supervisor_token:
        raise Exception("No Supervisor token available")
    uri = "ws://supervisor/core/websocket"
    async with websockets.connect(uri) as websocket:
        auth_message = {
            "type": "auth",
            "access_token": supervisor_token
        }
        await websocket.send(json.dumps(auth_message))
        response = await websocket.recv()
        
        await websocket.send(json.dumps(command))
        response = await websocket.recv()
        return json.loads(response)

# Function for getting current user
def get_current_user():
    """Get the current user exclusively from the request header."""
    try:
        # Just check the value in X-Remote-User-Name or X-Remote-User-Display-Name
        username = request.headers.get('X-Remote-User-Name')
        
        if username:
            logger.debug(f"User obtained from X-Remote-User-Name: {username}")
            return username
            
        # Try X-Remote-User-Display-Name if X-Remote-User-Name is not available
        username = request.headers.get('X-Remote-User-Display-Name')
        if username:
            logger.debug(f"User obtained from X-Remote-User-Display-Name: {username}")
            return username
            
        # For diagnostic purposes, print all headers only on the first undefined user
        if 'auth_headers_logged' not in globals():
            globals()['auth_headers_logged'] = True
            logger.debug(f"All headers: {dict(request.headers)}")
        
        # If we didn't get the user from headers, use 'admin' as default value
        logger.debug("User not found in request headers, using 'admin'")
        return "admin"
        
    except Exception as e:
        logger.error(f"Error retrieving user: {e}")
        return "admin"  # Safe return of default value in case of error
    
# Function for cache invalidation
def invalidate_user_cache(username=None):
    """
    Deletes cache for a specific user or for all users.
    
    Args:
        username (str, optional): Username for which to delete the cache.
                                  If None, cache is deleted for all users.
    """
    global USER_CACHE
    if username:
        if username in USER_CACHE:
            del USER_CACHE[username]
            logger.debug(f"Cache for user {username} has been cleared")
    else:
        USER_CACHE = {}
        logger.debug("Cache for all users has been cleared")

# API for cache management
@app.route('/api/cache/status', methods=['GET'])
def cache_status():
    """Shows the status of user cache"""
    result = {
        'user_count': len(USER_CACHE),
        'users': []
    }
    
    for username, cache_data in USER_CACHE.items():
        age = time.time() - cache_data['timestamp']
        expiry = CACHE_EXPIRY - age
        result['users'].append({
            'username': username,
            'cache_age_seconds': round(age, 2),
            'expires_in_seconds': round(expiry if expiry > 0 else 0, 2),
            'valid': expiry > 0
        })
    
    return jsonify(result)

@app.route('/api/cache/clear', methods=['POST'])
def clear_cache():
    """Deletes cache for all or specific users"""
    data = request.json or {}
    username = data.get('username')
    
    invalidate_user_cache(username)
    
    return jsonify({
        'message': f"Cache {'za uporabnika ' + username if username else 'za vse uporabnike'} je bil uspešno izbrisan."
    })

# Function for checking and creating user in database
def get_user_from_db(username):
    """Checks if user exists and creates them if they don't exist"""
    if not username:
        logger.error("Empty username!")
        return None
    
    # Check cache
    if username in USER_CACHE:
        cache_entry = USER_CACHE[username]
        # Check if cache is still valid
        if time.time() - cache_entry['timestamp'] < CACHE_EXPIRY:
            return cache_entry['user_data']
    
    logger.debug(f"Checking user in database: {username}")
    
    try:
        conn = get_db_connection()
        
        # First check if Users table exists, if not, create it
        conn.execute("""
        CREATE TABLE IF NOT EXISTS Users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            is_tab_user INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)
        conn.commit()
        
        # Check if user already exists
        user = conn.execute(
            "SELECT * FROM Users WHERE username = ?", 
            (username,)
        ).fetchone()
        
        if user:
            logger.debug(f"User {username} already exists in database (ID: {user['id']})")
            user_dict = dict(user)
            # Save to cache
            USER_CACHE[username] = {
                'user_data': user_dict,
                'timestamp': time.time()
            }
            conn.close()
            return user_dict
        
        # If user doesn't exist, create it
        display_name = username
        
        logger.info(f"Creating new user: {username}")
        
        # Set admin privileges to 1 if user is "admin" or "A" or if this is the first user
        is_admin = False
        if username.lower() == "admin" or username == "A":
            is_admin = True
            logger.info(f"Assigning admin privileges to user: {username}")
        else:
            # Check if this is the first user
            first_user = conn.execute("SELECT COUNT(*) as count FROM Users").fetchone()
            if first_user['count'] == 0:
                is_admin = True
                logger.info(f"Assigning admin privileges to first user: {username}")
        
        # FIXED: correct number of parameters in SQL statement
        conn.execute(
            """
            INSERT INTO Users (username, display_name, is_admin, is_tab_user, created_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            """,
            (username, display_name, 1 if is_admin else 0, 0)  # is_tab_user is always set to 0 for new users
        )
        conn.commit()
        
        # Get the created user
        user = conn.execute(
            "SELECT * FROM Users WHERE username = ?", 
            (username,)
        ).fetchone()
        conn.close()
        
        if user:
            logger.info(f"User successfully added to database: {username} (ID: {user['id']})")
            user_dict = dict(user)
            # Save to cache
            USER_CACHE[username] = {
                'user_data': user_dict,
                'timestamp': time.time()
            }
            return user_dict
        else:
            logger.error(f"Error: User {username} was not found after insertion")
            return None
    except Exception as e:
        logger.error(f"Error checking/creating user: {e}", exc_info=True)
        if 'conn' in locals() and conn:
            conn.close()
        return None

# API for adding or updating redirection to tablet.html
@app.route('/', methods=['GET'])
def serve_index():
    # Check if user is a tab user
    username = get_current_user()
    user = get_user_from_db(username)
    
    if not user:
        return send_from_directory('/app/static', 'index.html')
    
    # If user is a tab user, redirect to tablet.html
    if user['is_tab_user'] == 1:
        return send_from_directory('/app/static', 'tablet.html')
    
    # Otherwise show regular index.html
    return send_from_directory('/app/static', 'index.html')

# Serve podcast.html
@app.route('/podcast.html')
def serve_podcast():
    return send_from_directory('/app/static', 'podcast.html')

# Serve script.js
@app.route('/script.js')
def serve_script():
    return send_from_directory('/app/static', 'script.js')

# Serve settings.html
@app.route('/settings.html')
def serve_settings():
    return send_from_directory('/app/static', 'settings.html')

# Serve tablet.html
@app.route('/tablet.html')
def serve_tablet():
    return send_from_directory('/app/static', 'tablet.html')

# Static files
@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('/app/static', filename)

# API for retrieving all podcasts
@app.route('/api/podcasts', methods=['GET'])
def get_podcasts():
    username = get_current_user()
    user = get_user_from_db(username)

    if not user:
        return jsonify({"error": "User is not registered in the system."}), 401

    conn = get_db_connection()
    
    if user['is_admin'] == 1:
        logger.info(f"Retrieving all podcasts for admin user {user['username']}.")
        podcasts = conn.execute("""
            SELECT p.*, u.display_name as user_display_name 
            FROM Podcasts p
            LEFT JOIN Users u ON p.user_id = u.id
        """).fetchall()
    else:
        logger.info(f"Retrieving podcasts for user {user['username']} (ID: {user['id']}).")
        # Added consideration for hidden podcasts
        podcasts = conn.execute("""
            SELECT p.*, u.display_name as user_display_name
            FROM Podcasts p
            LEFT JOIN Users u ON p.user_id = u.id
            LEFT JOIN PodcastVisibilityPreferences pvp ON p.id = pvp.podcast_id AND pvp.user_id = ?
            WHERE (p.user_id = ? OR p.is_public = 1)
            AND (pvp.hidden IS NULL OR pvp.hidden = 0)
        """, (user['id'], user['id'])).fetchall()
    
    conn.close()
    logger.info(f"{len(podcasts)} podcasts found for user {user['username']}.")
    return jsonify([dict(podcast) for podcast in podcasts])

# Function for getting description from RSS feed
def get_podcast_description(rss_url):
    feed = feedparser.parse(rss_url)
    if feed.bozo:
        logger.info(f"Error reading RSS for description: {rss_url}")
        return None

    if 'description' in feed.feed:
        return feed.feed.description
    elif 'subtitle' in feed.feed:
        return feed.feed.subtitle
    return None

# Function for getting image from RSS feed
def get_podcast_image(rss_url):
    feed = feedparser.parse(rss_url)
    if feed.bozo:
        logger.info(f"Error reading RSS for image: {rss_url}")
        return None

    if 'image' in feed.feed and 'url' in feed.feed.image:
        return feed.feed.image.url
    elif hasattr(feed.feed, 'logo'):
        return feed.feed.logo
    return None

# API for adding podcast
@app.route('/api/podcasts', methods=['POST'])
def add_podcast():
    data = request.json
    naslov = data.get('naslov')
    rss_url = data.get('rss_url')
    is_public = data.get('is_public', 0)  # Default podcast is private (0)

    if not naslov or not rss_url:
        logger.error("Error: Title and RSS URL are required.")
        return jsonify({"error": "Naslov in RSS URL sta obvezna."}), 400

    # Get the current user
    username = get_current_user()
    user = get_user_from_db(username)

    if not user:
        logger.error("User is not registered in the system.")
        return jsonify({"error": "Uporabnik ni registriran v sistemu."}), 401

    conn = get_db_connection()
    obstojece = conn.execute("SELECT * FROM Podcasts WHERE rss_url = ? AND user_id = ?", 
                          (rss_url, user['id'])).fetchone()

    if obstojece:
        logger.info(f"Podcast already exists for user {user['username']} (RSS URL: {rss_url}).")
        return jsonify({"error": "Podcast že obstaja pri tem uporabniku."}), 400

    description = get_podcast_description(rss_url)
    image_url = get_podcast_image(rss_url)

    logger.info(f"Adding podcast: {naslov}, RSS URL: {rss_url}, is_public: {is_public}, user: {user['username']}")

    conn.execute(
        """
        INSERT INTO Podcasts (naslov, rss_url, datum_naročnine, image_url, description, user_id, is_public)
        VALUES (?, ?, datetime('now'), ?, ?, ?, ?)
        """,
        (naslov, rss_url, image_url, description, user['id'], is_public)
    )
    conn.commit()
    conn.close()
    logger.info(f"Podcast {naslov} successfully added for user {user['username']}.")
    return jsonify({"message": "Podcast dodan uspešno."}), 201

# API for checking podcast usage before deletion
@app.route('/api/podcasts/<int:podcast_id>/check_usage', methods=['GET'])
def check_podcast_usage(podcast_id):
    try:
        username = get_current_user()
        user = get_user_from_db(username)
        
        if not user:
            return jsonify({"error": "User is not registered in the system."}), 401
        
        with get_db_connection() as conn:
            # Check if podcast exists
            podcast = conn.execute("SELECT * FROM Podcasts WHERE id = ?", (podcast_id,)).fetchone()
            if not podcast:
                return jsonify({"error": "Podcast ne obstaja."}), 404
            
            # Check if user is owner or admin
            if podcast['user_id'] != user['id'] and not user['is_admin']:
                return jsonify({"error": "Nimate pravice za brisanje tega podcasta."}), 403
            
           # If not public, can be deleted directly
            if not podcast['is_public']:
                return jsonify({
                    "can_delete": True,
                    "reason": "private_podcast"
                })
            
            # If admin, can delete everything
            if user['is_admin']:
                return jsonify({
                    "can_delete": True,
                    "reason": "admin_user"
                })
            
            # Check usage of public podcast
            usage_check = conn.execute("""
                SELECT 
                    COUNT(DISTINCT CASE 
                        WHEN (pvp.podcast_id IS NULL OR pvp.hidden = 0) THEN u.id 
                        ELSE NULL 
                    END) as visible_users,
                    COUNT(DISTINCT CASE 
                        WHEN pvp.hidden = 1 AND els.episode_id IS NOT NULL THEN u.id 
                        ELSE NULL 
                    END) as hidden_with_history
                FROM Users u
                LEFT JOIN PodcastVisibilityPreferences pvp ON u.id = pvp.user_id AND pvp.podcast_id = ?
                LEFT JOIN Episodes e ON e.podcast_id = ?
                LEFT JOIN EpisodeListenStatus els ON els.episode_id = e.id AND els.user_id = u.id
                WHERE u.id != ?
            """, (podcast_id, podcast_id, user['id'])).fetchone()
            
            visible_users = usage_check['visible_users'] or 0
            hidden_with_history = usage_check['hidden_with_history'] or 0
            
            # Decision logic
            if hidden_with_history > 0:
                return jsonify({
                    "can_delete": False,
                    "reason": "hidden_with_history",
                    "message": f"Podcast ima {hidden_with_history} uporabnikov s skrito zgodovino poslušanja. Samo admin ga lahko izbriše."
                })
            elif visible_users > 0:
                return jsonify({
                    "can_delete": False,
                    "reason": "visible_users",
                    "visible_count": visible_users,
                    "message": f"Podcast uporabljajo še {visible_users} uporabnikov."
                })
            else:
                return jsonify({
                    "can_delete": True,
                    "reason": "no_active_users"
                })
                
    except Exception as e:
        logger.error(f"Error checking podcast usage: {e}")
        return jsonify({"error": str(e)}), 500

# API for deleting podcast
@app.route('/api/podcasts/<int:podcast_id>', methods=['DELETE'])
def delete_podcast(podcast_id):
    with get_db_connection() as conn:
        podcast = conn.execute("SELECT * FROM Podcasts WHERE id = ?", (podcast_id,)).fetchone()
        if not podcast:
            return jsonify({"error": "Podcast ne obstaja."}), 404

        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("DELETE FROM Episodes WHERE podcast_id = ?", (podcast_id,))
        conn.execute("DELETE FROM Podcasts WHERE id = ?", (podcast_id,))
        conn.commit()
    return jsonify({"message": "Podcast in njegove epizode so uspešno izbrisane."}), 200

# API for updating all podcasts
@app.route('/api/podcasts/update_all', methods=['POST'])
def update_all_podcasts():
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with get_db_connection() as conn:
        podcasts = conn.execute("SELECT * FROM Podcasts").fetchall()
        for podcast in podcasts:
            update_episodes(podcast['id'], podcast['rss_url'])
        conn.execute("UPDATE Podcasts SET datum_naročnine = ?", (now,))
        conn.commit()
    return jsonify({"message": "Vsi podcasti so bili posodobljeni."}), 200

# Add functionality for marking episodes as listened
@app.route('/api/episodes/mark_listened/<int:episode_id>', methods=['POST'])
def mark_episode_listened(episode_id):
    # Get current user
    username = get_current_user()
    user = get_user_from_db(username)
    
    if not user:
        return jsonify({"error": "User is not registered in the system."}), 401
    
    # Check request parameters
    data = request.json or {}
    as_user_id = data.get('as_user_id')
    
    # Check if current user is tab user and has permission to mark listening status
    with get_db_connection() as conn:
        # First check if episode exists
        episode = conn.execute("SELECT * FROM Episodes WHERE id = ?", (episode_id,)).fetchone()
        
        if not episode:
            return jsonify({"error": "Epizoda ne obstaja."}), 404
            
        # Determine the user for whom we record listening status
        target_user_id = None
        if as_user_id:
            # If current user is tab user, allow them to use as_user_id
            if user['is_tab_user'] == 1:
                target_user_id = as_user_id
            else:
                return jsonify({"error": "Nimate pravice označevati poslušanosti za druge uporabnike."}), 403
        else:
            target_user_id = user['id']
        
        # Check if listening record already exists for this user
        listen_status = conn.execute("""
            SELECT * FROM EpisodeListenStatus
            WHERE episode_id = ? AND user_id = ?
        """, (episode_id, target_user_id)).fetchone()
        
        if listen_status:
            # Update existing record
            conn.execute("""
                UPDATE EpisodeListenStatus
                SET poslušano = 1, timestamp = datetime('now')
                WHERE episode_id = ? AND user_id = ?
            """, (episode_id, target_user_id))
        else:
            # Create new record
            conn.execute("""
                INSERT INTO EpisodeListenStatus (episode_id, user_id, poslušano)
                VALUES (?, ?, 1)
            """, (episode_id, target_user_id))
        
        conn.commit()
        
        logger.info(f"User {username} marked episode {episode_id} as listened for user {target_user_id}")
    
    return jsonify({"message": "Epizoda označena kot poslušana."}), 200


# API for retrieving episodes
@app.route('/api/episodes/<int:podcast_id>', methods=['GET'])
def get_episodes(podcast_id):
    # Get current user
    username = get_current_user()
    user = get_user_from_db(username)
    
    if not user:
        return jsonify({"error": "User is not registered in the system."}), 401
    
    # Check request parameters (for case when viewing as another user)
    as_user_id = request.args.get('as_user', type=int)
    check_user_id = as_user_id if as_user_id else user['id']
    
    with get_db_connection() as conn:
        # Get episodes with listening status and playback position for the appropriate user
        episodes = conn.execute("""
            SELECT 
                e.*,
                COALESCE(els.poslušano, 0) as poslušano,
                COALESCE(epp.position, 0) as playback_position,
                epp.timestamp as playback_timestamp
            FROM Episodes e
            LEFT JOIN EpisodeListenStatus els ON e.id = els.episode_id AND els.user_id = ?
            LEFT JOIN EpisodePlaybackPosition epp ON e.id = epp.episode_id AND epp.user_id = ?
            WHERE e.podcast_id = ? AND e.izbrisano IS NOT 1
            ORDER BY datetime(e.datum_izdaje) DESC
        """, (check_user_id, check_user_id, podcast_id)).fetchall()
    
    if not episodes:
        return jsonify([])  # Return empty list instead of error
    
    # Convert results to list of dictionaries and add playback information
    result = []
    for episode in episodes:
        episode_dict = dict(episode)
        # Add formatted playback time (for easier display in user interface)
        if episode_dict['playback_position'] > 0:
            minutes = episode_dict['playback_position'] // 60
            seconds = episode_dict['playback_position'] % 60
            episode_dict['playback_time_formatted'] = f"{minutes}:{seconds:02d}"
        else:
            episode_dict['playback_time_formatted'] = "0:00"
        result.append(episode_dict)
    
    return jsonify(result)

# API for deleting a single episode
@app.route('/api/episodes/<int:episode_id>/delete', methods=['POST'])
def delete_episode(episode_id):
    """Izbriši posamezno epizodo"""
    try:
        # Get current user
        username = get_current_user()
        user = get_user_from_db(username)
        
        if not user:
            return jsonify({"error": "User is not registered in the system."}), 401
        
        with get_db_connection() as conn:
            # Check if episode exists and get podcast data
            episode = conn.execute("""
                SELECT e.*, p.user_id as podcast_owner_id
                FROM Episodes e
                JOIN Podcasts p ON e.podcast_id = p.id
                WHERE e.id = ?
            """, (episode_id,)).fetchone()
            
            if not episode:
                return jsonify({"error": "Epizoda ne obstaja."}), 404
            
            # Check if user has permission to delete episode
            # Podcast owner or admin has permission
            if episode['podcast_owner_id'] != user['id'] and not user['is_admin']:
                return jsonify({"error": "Nimate pravice brisati te epizode."}), 403
            
            # Mark episode as deleted (soft delete)
            conn.execute("""
                UPDATE Episodes 
                SET izbrisano = 1 
                WHERE id = ?
            """, (episode_id,))
            
            # Also delete related listening and playback position data
            conn.execute("DELETE FROM EpisodeListenStatus WHERE episode_id = ?", (episode_id,))
            conn.execute("DELETE FROM EpisodePlaybackPosition WHERE episode_id = ?", (episode_id,))
            
            conn.commit()
            
        logger.info(f"User {user['username']} deleted episode {episode_id}")
        return jsonify({"message": "Epizoda uspešno izbrisana."}), 200
        
    except Exception as e:
        logger.error(f"Error deleting episode: {e}")
        return jsonify({"error": str(e)}), 500

# Function for updating episodes from RSS feed
def update_episodes(podcast_id, rss_url):
    logger.info(f"Updating podcast ID {podcast_id} from source {rss_url}")
    feed = feedparser.parse(rss_url)
    if feed.bozo:
        logger.info(f"Error reading RSS: {rss_url}")
        return

    with get_db_connection() as conn:
        # Get podcast image URL and description and update
        image_url = get_podcast_image(rss_url)
        description = get_podcast_description(rss_url)
        if image_url or description:
            if image_url and description:
                conn.execute("UPDATE Podcasts SET image_url = ?, description = ? WHERE id = ?", (image_url, description, podcast_id))
            elif image_url:
                conn.execute("UPDATE Podcasts SET image_url = ? WHERE id = ?", (image_url, podcast_id))
            elif description:
                conn.execute("UPDATE Podcasts SET description = ? WHERE id = ?", (description, podcast_id))

        for entry in feed.entries:
            naslov = entry.title
            datum_izdaje = entry.published if hasattr(entry, 'published') else datetime.now().isoformat()
            # Date formatting
            try:
                parsed_date = datetime.strptime(datum_izdaje, "%a, %d %b %Y %H:%M:%S %z")
                datum_izdaje_iso = parsed_date.strftime("%Y-%m-%d %H:%M:%S")
            except Exception as e:
                logger.error(f"Error formatting date: {e}")
                datum_izdaje_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            url = entry.enclosures[0].href if hasattr(entry, 'enclosures') and entry.enclosures else entry.link
            if not url:
                logger.info(f"Missing URL for episode: {naslov}")
                continue

            # Add check for episode description
            opis = ""
            if hasattr(entry, 'summary'):
                opis = entry.summary
            elif hasattr(entry, 'description'):
                opis = entry.description

            # Check if episode already exists and get its ID and current description
            obstojece = conn.execute(
                "SELECT id, opis FROM Episodes WHERE podcast_id = ? AND naslov = ? AND datum_izdaje = ? AND izbrisano IS NOT 1",
                (podcast_id, naslov, datum_izdaje_iso)
            ).fetchone()

            if obstojece:
                # Get current description from database
                obstojeciOpis = obstojece['opis'] if obstojece['opis'] is not None else ""
                # If new description is different and not empty, update record
                if opis and opis != obstojeciOpis:
                    conn.execute(
                        "UPDATE Episodes SET opis = ? WHERE id = ?",
                        (opis, obstojece['id'])
                    )
                    logger.info(f"Updated description for episode: {naslov}")
                else:
                    logger.info(f"Episode '{naslov}' already exists, description unchanged or missing in RSS.")
                continue

            logger.info(f"Adding new episode: {naslov}")
            conn.execute(
                "INSERT INTO Episodes (podcast_id, naslov, datum_izdaje, url, opis) VALUES (?, ?, ?, ?, ?)",
                (podcast_id, naslov, datum_izdaje_iso, url, opis)
            )

        conn.commit()
    logger.info(f"Update for podcast ID {podcast_id} completed")

# Function for extracting all episodes from HTML archive of given URL
def scrape_all_episodes_from_html_url(html_url):
    r = requests.get(html_url)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')

    episodes_data = []
    # Adjust selectors according to actual HTML structure of the page
    epizode = soup.select('.podcast-episode')
    for ep in epizode:
        naslov_el = ep.find('h3')
        datum_el = ep.find('span', class_='date')
        link_el = ep.find('a', class_='download')

        if not naslov_el or not datum_el:
            continue

        naslov = naslov_el.get_text(strip=True)
        datum_raw = datum_el.get_text(strip=True)

        try:
            parsed_date = datetime.strptime(datum_raw, "%d.%m.%Y")
            datum_izdaje_iso = parsed_date.strftime("%Y-%m-%d 00:00:00")
        except:
            datum_izdaje_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not link_el:
            link_el = ep.find('a', href=True)
        url_mp3 = link_el['href'] if link_el else None

        if url_mp3:
            episodes_data.append((naslov, datum_izdaje_iso, url_mp3))

    return episodes_data

# Endpoint for one-time import of missing episodes from arbitrary HTML URL
@app.route('/api/podcasts/<int:podcast_id>/add_missing_from_html_url', methods=['POST'])
def add_missing_from_html_url(podcast_id):
    data = request.json
    html_url = data.get('html_url')
    if not html_url:
        return jsonify({"error": "html_url je obvezen parameter."}), 400

    episodes_data = scrape_all_episodes_from_html_url(html_url)

    with get_db_connection() as conn:
        dodano = 0
        for (naslov, datum_izdaje_iso, url) in episodes_data:
            obstojece = conn.execute(
                "SELECT 1 FROM Episodes WHERE podcast_id = ? AND naslov = ? AND datum_izdaje = ?",
                (podcast_id, naslov, datum_izdaje_iso)
            ).fetchone()
            if obstojece:
                continue

            conn.execute(
                "INSERT INTO Episodes (podcast_id, naslov, datum_izdaje, url) VALUES (?, ?, ?, ?)",
                (podcast_id, naslov, datum_izdaje_iso, url)
            )
            dodano += 1
        conn.commit()
    return jsonify({"message": f"Dodano {dodano} manjkajočih epizod iz HTML arhiva."}), 200

# New routes for media player support
@app.route('/api/media_players/all', methods=['GET'])
async def get_all_media_players():
    """Get list of all available media players"""
    try:
        supervisor_token = os.environ.get('SUPERVISOR_TOKEN')
        if not supervisor_token:
            return jsonify({"error": "No Supervisor token available"}), 500

        headers = {
            "Authorization": f"Bearer {supervisor_token}",
            "Content-Type": "application/json",
        }

        # Make request to Home Assistant API
        response = requests.get(
            "http://supervisor/core/api/states",
            headers=headers,
            timeout=10
        )

        if not response.ok:
            logger.error(f"Error fetching states: {response.status_code} - {response.text}")
            return jsonify({"error": "Failed to fetch media players"}), 500

        states = response.json()
        media_players = []
        for entity in states:
            if isinstance(entity, dict) and entity.get('entity_id', '').startswith('media_player.'):
                player = {
                    "entity_id": entity['entity_id'],
                    "state": entity.get('state', 'unknown'),
                    "attributes": entity.get('attributes', {})
                }
                if 'friendly_name' in entity.get('attributes', {}):
                    player["name"] = entity['attributes']['friendly_name']
                else:
                    player["name"] = entity['entity_id'].replace('media_player.', '')
                media_players.append(player)

        logger.info(f"Found {len(media_players)} media players")
        return jsonify({"players": media_players})
    except Exception as e:
        logger.error(f"Error in get_all_media_players: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/media_players', methods=['GET'])
async def get_media_players():
    """Get list of selected media players, or all if none are selected"""
    try:
        with get_db_connection() as conn:
            selected_players = conn.execute("SELECT * FROM SelectedPlayers").fetchall()

        # If no players are selected, return all players
        if not selected_players:
            return await get_all_media_players()
        
        # Return only selected players
        players = [{"entity_id": player["entity_id"], "name": player["display_name"]} for player in selected_players]
        return jsonify({"players": players})
    except Exception as e:
        logger.error(f"Error in get_media_players: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/media_players/selected', methods=['GET'])
def get_selected_media_players():
    """Get list of selected media players."""
    try:
        with get_db_connection() as conn:
            selected_players = conn.execute("SELECT * FROM SelectedPlayers").fetchall()
        return jsonify({"players": [dict(player) for player in selected_players]})
    except Exception as e:
        logger.error(f"Error in get_selected_media_players: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/media_players/selected', methods=['POST'])
def update_selected_media_players():
    """Update the list of selected media players."""
    try:
        data = request.json
        players = data.get('players', [])
        if not isinstance(players, list):
            return jsonify({"error": "Invalid data format. Expected a list of players."}), 400

        with get_db_connection() as conn:
            # Clear existing selections
            conn.execute("DELETE FROM SelectedPlayers")
            # Insert new selections
            for player in players:
                entity_id = player.get('entity_id')
                display_name = player.get('name', entity_id.replace('media_player.', '') if entity_id else "Unknown")
                if entity_id:
                    conn.execute(
                        "INSERT INTO SelectedPlayers (entity_id, display_name) VALUES (?, ?)",
                        (entity_id, display_name)
                    )
            conn.commit()
        return jsonify({"message": "Selected players updated successfully", "count": len(players)})
    except Exception as e:
        logger.error(f"Error in update_selected_media_players: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/play_episode', methods=['POST'])
async def play_episode():
    """Play episode on selected media player"""
    data = request.json
    player_entity_id = data.get('player_entity_id')
    episode_url = data.get('episode_url')
    episode_title = data.get('episode_title')
    start_position = data.get('start_position', 0)

    if not all([player_entity_id, episode_url, episode_title]):
        return jsonify({"error": "Missing required parameters"}), 400

    try:
        # Get current user for tracking
        username = get_current_user()
        user = get_user_from_db(username)
        if not user:
            return jsonify({"error": "User not found"}), 401

        # Get episode_id from URL and check for saved position
        episode_id = None
        saved_position = 0
        with get_db_connection() as conn:
            episode = conn.execute("SELECT id FROM Episodes WHERE url = ?", (episode_url,)).fetchone()
            if episode:
                episode_id = episode['id']
                
                # Check for saved position if start_position not provided
                if start_position == 0:
                    position_data = conn.execute("""
                        SELECT position FROM EpisodePlaybackPosition 
                        WHERE episode_id = ? AND user_id = ?
                    """, (episode_id, user['id'])).fetchone()
                    
                    if position_data and position_data['position'] > 0:
                        saved_position = position_data['position']
                        logger.info(f"Found saved position {saved_position} for episode {episode_id}")

        # Use saved position if no start_position was provided
        final_start_position = start_position if start_position > 0 else saved_position

        # First start playback
        play_command = {
            "type": "call_service",
            "domain": "media_player",
            "service": "play_media",
            "service_data": {
                "entity_id": player_entity_id,
                "media_content_id": episode_url,
                "media_content_type": "music",
                "extra": {
                    "title": episode_title
                }
            },
            "id": 2
        }
        await ha_websocket_call(play_command)

        # Start tracking session if we found episode_id
        if episode_id:
            start_tracking_session(episode_id, player_entity_id, episode_url, user['id'])

        # If we have a position to seek to, use improved seeking logic
        if final_start_position > 0:
            seek_success = await smart_seek_to_position(player_entity_id, final_start_position)
            
            if seek_success:
                minutes = final_start_position // 60
                seconds = final_start_position % 60
                return jsonify({"message": f"Predvajam epizodo od pozicije {minutes}:{seconds:02d}"})
            else:
                return jsonify({"message": "Predvajam epizodo (pozicija ni bila nastavljena)"})
        
        return jsonify({"message": "Predvajam epizodo"})
    except Exception as e:
        logger.error(f"Error in play_episode: {str(e)}")
        return jsonify({"error": str(e)}), 500

async def smart_seek_to_position(player_entity_id, seek_position, max_attempts=10):
    """
    Pametno iskanje pozicije - čaka da se media naloži pred seek operacijo
    """
    try:
        logger.info(f"Starting smart seek to position {seek_position} for player {player_entity_id}")
        
        # Počakaj da se predvajanje začne in media naloži
        for attempt in range(max_attempts):
            await asyncio.sleep(1)  # Počakaj 1 sekundo med poskusi
            
            # Preveri stanje predvajalnika
            player_state = await get_player_state_from_ha(player_entity_id)
            
            if not player_state:
                logger.warning(f"Could not get player state, attempt {attempt + 1}")
                continue
                
            state = player_state.get('state', 'unknown')
            duration = player_state.get('media_duration', 0)
            current_position = player_state.get('media_position', 0)
            
            logger.info(f"Attempt {attempt + 1}: state={state}, duration={duration}, position={current_position}")
            
            # Preverimo ali je media pripravljena
            if state in ['playing', 'paused'] and duration > 0:
                # Media je pripravljena, lahko izvršimo seek
                logger.info(f"Media ready after {attempt + 1} attempts, executing seek to {seek_position}")
                
                seek_command = {
                    "type": "call_service",
                    "domain": "media_player",
                    "service": "media_seek",
                    "service_data": {
                        "entity_id": player_entity_id,
                        "seek_position": seek_position
                    },
                    "id": 3
                }
                
                await ha_websocket_call(seek_command)
                
                # Počakaj malo in preveri ali je seek uspešen
                await asyncio.sleep(2)
                final_state = await get_player_state_from_ha(player_entity_id)
                if final_state:
                    final_position = final_state.get('media_position', 0)
                    logger.info(f"Seek completed, final position: {final_position}")
                
                return True
                
        logger.error(f"Failed to seek after {max_attempts} attempts")
        return False
        
    except Exception as e:
        logger.error(f"Error in smart_seek_to_position: {e}")
        return False

@app.route('/api/podcasts/<int:podcast_id>/add_missing_episodes', methods=['POST'])
def add_missing_episodes(podcast_id):
    """Add missing episodes from an XML file"""
    conn = None
    logger.info(f"Starting to process episodes for podcast {podcast_id}")
    
    try:
        with get_db_connection() as conn:
            podcast = conn.execute("SELECT * FROM Podcasts WHERE id = ?", (podcast_id,)).fetchone()
            if not podcast:
                return jsonify({"error": "Podcast not found"}), 404

            data = request.json
            if not data or 'episodes' not in data:
                return jsonify({"error": "No episode data provided"}), 400

            episodes = data['episodes']
            added_count = 0
            total_episodes = len(episodes)

            for episode in episodes:
                try:
                    # Convert publication date to ISO format
                    try:
                        parsed_date = datetime.strptime(episode['datum_izdaje'], "%a, %d %b %Y %H:%M:%S %z")
                        datum_izdaje_iso = parsed_date.strftime("%Y-%m-%d %H:%M:%S")
                    except Exception as e:
                        logger.error(f"Date parsing error: {e}")
                        datum_izdaje_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    # Check if episode already exists by title or URL
                    existing = conn.execute("""
                        SELECT 1 FROM Episodes 
                        WHERE podcast_id = ? 
                        AND (naslov = ? OR url = ?)
                        AND izbrisano = 0
                    """, (podcast_id, episode['naslov'], episode['url'])).fetchone()
                    
                    if existing:
                        logger.info(f"Skipping duplicate episode: {episode['naslov']}")
                        continue

                    conn.execute("""
                        INSERT INTO Episodes (podcast_id, naslov, datum_izdaje, url)
                        VALUES (?, ?, ?, ?)
                    """, (podcast_id, episode['naslov'], datum_izdaje_iso, episode['url']))
                    added_count += 1
                except Exception as e:
                    logger.error(f"Error processing episode {episode.get('naslov', 'unknown')}: {e}")
                    continue

            # Count total episodes processed
            skipped_count = total_episodes - added_count
            
            if added_count > 0:
                conn.commit()
                logger.info(f"Successfully added {added_count} episodes, skipped {skipped_count} duplicates")
            
            return jsonify({
                "message": f"Successfully added {added_count} new episodes, skipped {skipped_count} duplicates",
                "added_count": added_count,
                "skipped_count": skipped_count,
                "total_processed": total_episodes
            }), 201
    except Exception as e:
        logger.error(f"Error in add_missing_episodes: {e}")
        if conn:
            try:
                conn.rollback()
            except Exception as rollback_error:
                logger.error(f"Error during rollback: {rollback_error}")
        return jsonify({"error": str(e)}), 500

# API for user initialization on first application access
@app.route('/api/init_user', methods=['GET'])
def init_user():
    """API za preverjanje uporabnika ob prvem dostopu do aplikacije"""
    try:
        username = get_current_user()
        logger.info(f"Checking user: {username}")
        
        user = get_user_from_db(username)
        
        if not user:
            logger.error(f"User {username} is not registered in the system")
            return jsonify({"error": "Uporabnik ni registriran v sistemu"}), 401
        
        logger.info(f"User found: {username} (ID: {user['id']})")
        
        return jsonify({
            "username": username,
            "display_name": user['display_name'],
            "is_admin": bool(user['is_admin']),
            "is_tab_user": bool(user['is_tab_user'])
        })
    
    except Exception as e:
        logger.error(f"Napaka v init_user: {e}", exc_info=True)
        return jsonify({"error": f"Napaka: {str(e)}"}), 500

# API for getting settings
@app.route('/api/settings', methods=['GET'])
def get_settings():
    with get_db_connection() as conn:
        settings = conn.execute("SELECT * FROM Settings LIMIT 1").fetchone()
        if not settings:
            # If settings don't exist, create defaults
            current_time = datetime.now().strftime("%H:%M")
            conn.execute("""
                INSERT INTO Settings (avtomatsko, interval, cas_posodobitve, zadnja_posodobitev)
                VALUES (1, 24, ?, datetime('now'))
            """, (current_time,))
            conn.commit()
            settings = conn.execute("SELECT * FROM Settings LIMIT 1").fetchone()
    return jsonify(dict(settings))

# API for updating settings
@app.route('/api/settings', methods=['POST'])
def update_settings():
    data = request.json
    avtomatsko = data.get('avtomatsko', 1)
    interval = data.get('interval', 24)
    cas_posodobitve = data.get('cas_posodobitve', '03:00')

    with get_db_connection() as conn:
        # Check old settings for comparison
        old_settings = conn.execute("SELECT avtomatsko FROM Settings LIMIT 1").fetchone()
        old_avtomatsko = old_settings['avtomatsko'] if old_settings else 0

        # Check if settings exist
        settings = conn.execute("SELECT 1 FROM Settings LIMIT 1").fetchone()
        if settings:
            # Update existing settings
            conn.execute("""
                UPDATE Settings
                SET avtomatsko = ?, interval = ?, cas_posodobitve = ?
                WHERE id = 1
            """, (avtomatsko, interval, cas_posodobitve))
        else:
            # Create new settings
            conn.execute("""
                INSERT INTO Settings (avtomatsko, interval, cas_posodobitve, zadnja_posodobitev)
                VALUES (?, ?, ?, datetime('now'))
            """, (avtomatsko, interval, cas_posodobitve))
        conn.commit()
    
    logger.info(f"Settings updated: automatic={avtomatsko}, interval={interval}, update_time={cas_posodobitve}")
    
    # If we enabled automatic update or changed automatic update,
    # restart the update thread
    if avtomatsko == 1 or old_avtomatsko != avtomatsko:
        logger.info("Restarting update thread due to settings change")
        start_update_thread()
    
    return jsonify({"message": "Nastavitve uspešno posodobljene."})

# Function to calculate seconds until next update
def calculate_seconds_until_next_update():
    try:
        with get_db_connection() as conn:
            settings = conn.execute("SELECT * FROM Settings LIMIT 1").fetchone()
        
        if not settings or settings['avtomatsko'] != 1 or not settings['cas_posodobitve']:
            # If automatic update is not set, check again in one hour
            return 3600  
        
        # Get current time
        now = datetime.now()
        
        # Parse set update time
        hour, minute = map(int, settings['cas_posodobitve'].split(':'))
        
        # Create datetime object for next update time
        next_update = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # If set time is already past for today, add one day or one week
        if next_update <= now:
            if settings['interval'] <= 24:  # Daily update
                next_update += timedelta(days=1)
            else:  # Weekly update
                next_update += timedelta(days=7)
        # For weekly update, we can additionally check if we need to skip more days
        elif settings['interval'] > 24 and 'zadnja_posodobitev' in settings and settings['zadnja_posodobitev']:
            last_update = datetime.strptime(settings['zadnja_posodobitev'], "%Y-%m-%d %H:%M:%S")
            hours_since_last_update = (now - last_update).total_seconds() / 3600
            
            # If not enough time has passed since last update, skip to next week
            if hours_since_last_update < settings['interval'] and next_update > last_update:
                next_update += timedelta(days=7)
        
        # Calculate seconds until next update
        seconds_until_update = (next_update - now).total_seconds()
        
        logger.info(f"Next update at {next_update.strftime('%Y-%m-%d %H:%M:%S')} (over {seconds_until_update/3600:.2f} hours)")
        return max(seconds_until_update, 60)  # At least 1 minute
    except Exception as e:
        logger.error(f"Error calculating time for next update: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        # In case of error, check again in 1 hour
        return 3600
    
# API for saving playback position
@app.route('/api/episodes/<int:episode_id>/position', methods=['POST'])
def save_episode_position(episode_id):
    """Shrani trenutno pozicijo predvajanja za epizodo"""
    try:
        data = request.json
        position = data.get('position')
        
        if position is None:
            return jsonify({"error": "Manjka parameter 'position'"}), 400

        # Get current user
        username = get_current_user()
        current_user = get_user_from_db(username)
        
        if not current_user:
            return jsonify({"error": "Napaka pri preverjanju uporabnika."}), 500

        # Check as_user parameter
        as_user_id = data.get('as_user_id')
        target_user_id = None

        if as_user_id:
            if current_user['is_tab_user'] == 1:
                target_user_id = as_user_id
            else:
                return jsonify({"error": "Nimate pravice shranjevati pozicije za druge uporabnike."}), 403
        else:
            target_user_id = current_user['id']

        with get_db_connection() as conn:
            # Check if episode exists
            episode = conn.execute("SELECT * FROM Episodes WHERE id = ?", (episode_id,)).fetchone()
            if not episode:
                return jsonify({"error": "Epizoda ne obstaja."}), 404

            # Save or update position
            conn.execute("""
                INSERT INTO EpisodePlaybackPosition (episode_id, user_id, position, timestamp)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(episode_id, user_id) 
                DO UPDATE SET position = ?, timestamp = datetime('now')
            """, (episode_id, target_user_id, position, position))
            conn.commit()

        logger.info(f"Saved position {position} for episode {episode_id} and user {target_user_id}")
        return jsonify({"message": "Pozicija uspešno shranjena."}), 200

    except Exception as e:
        logger.error(f"Napaka pri shranjevanju pozicije: {e}")
        return jsonify({"error": str(e)}), 500

# API for getting playback position
@app.route('/api/episodes/<int:episode_id>/position', methods=['GET'])
def get_episode_position(episode_id):
    """Pridobi zadnjo shranjeno pozicijo predvajanja za epizodo"""
    try:
        # Get current user
        username = get_current_user()
        current_user = get_user_from_db(username)
        
        if not current_user:
            return jsonify({"error": "Napaka pri preverjanju uporabnika."}), 500

        # Check as_user parameter from URL
        as_user_id = request.args.get('as_user', type=int)
        target_user_id = None

        if as_user_id:
            if current_user['is_tab_user'] == 1:
                target_user_id = as_user_id
            else:
                return jsonify({"error": "Nimate pravice videti pozicije drugih uporabnikov."}), 403
        else:
            target_user_id = current_user['id']

        with get_db_connection() as conn:
            # Check if episode exists
            episode = conn.execute("SELECT * FROM Episodes WHERE id = ?", (episode_id,)).fetchone()
            if not episode:
                return jsonify({"error": "Epizoda ne obstaja."}), 404

            # Get last position
            position = conn.execute("""
                SELECT position, timestamp
                FROM EpisodePlaybackPosition
                WHERE episode_id = ? AND user_id = ?
            """, (episode_id, target_user_id)).fetchone()

            if position:
                return jsonify({
                    "position": position['position'],
                    "timestamp": position['timestamp']
                })
            else:
                return jsonify({
                    "position": 0,
                    "timestamp": None
                })

    except Exception as e:
        logger.error(f"Napaka pri pridobivanju pozicije: {e}")
        return jsonify({"error": str(e)}), 500

# Function for automatic update
def auto_update_podcasts():
    try:
        logger.info("Starting automatic podcast update...")
        # Update all podcasts
        with get_db_connection() as conn:
            podcasts = conn.execute("SELECT * FROM Podcasts").fetchall()
            updated = 0
            
            for podcast in podcasts:
                try:
                    update_episodes(podcast['id'], podcast['rss_url'])
                    updated += 1
                except Exception as e:
                    logger.error(f"Napaka pri posodabljanju podcasta {podcast['naslov']}: {e}")
            
            # Update last update time
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            conn.execute("UPDATE Settings SET zadnja_posodobitev = ? WHERE id = 1", (now,))
            conn.commit()
        logger.info(f"Automatic update completed. Updated {updated} podcasts.")
        return True
    except Exception as e:
        logger.error(f"Error while auto-updating podcasts: {e}")
        return False

# Function for automatic update
def auto_update_loop():
    logger.info("Automatic update initialized.")
    while not update_thread_stop_event.is_set():
        try:
            # Calculate time until next update
            sleep_duration = calculate_seconds_until_next_update()
            
            # Wait until next update
            logger.info(f"I'm sleeping {sleep_duration/3600:.2f} hours until the next update..")
            # Use wait with timeout instead of sleep to detect stop earlier
            if update_thread_stop_event.wait(timeout=sleep_duration):
                logger.info("Request received to stop update thread.")
                break
            
            # Check settings once more before update
            with get_db_connection() as conn:
                settings = conn.execute("SELECT * FROM Settings LIMIT 1").fetchone()
            
            if settings and settings['avtomatsko'] == 1:
                logger.info(f"Time for an update! ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
                auto_update_podcasts()
            else:
                logger.info("Automatic update is turned off.")
        except Exception as e:
            logger.error(f"Error in auto_update_loop: {e}")
            time.sleep(300)  # In case of error, wait 5 minutes

# Function for safe start/restart of thread
def start_update_thread():
    global update_thread, update_thread_stop_event
    
    # First stop existing thread if it exists
    if update_thread and update_thread.is_alive():
        logger.info("I'm stopping the existing update thread...")
        update_thread_stop_event.set()  # Send stop signal
        update_thread.join(timeout=5)   # Wait up to 5 seconds for thread to stop
        update_thread_stop_event.clear()  # Reset event
    
    # Start new thread
    logger.info("Starting new thread for automatic update...")
    update_thread = threading.Thread(target=auto_update_loop, daemon=True)
    update_thread.start()
    logger.info("New thread for automatic update started.")

# Tracking session functions
def start_tracking_session(episode_id, player_entity_id, episode_url, user_id):
    """Start tracking playback session"""
    try:
        with get_db_connection() as conn:
            # Delete any existing session for this episode/user
            conn.execute("""
                DELETE FROM ActiveTrackingSessions 
                WHERE episode_id = ? AND user_id = ?
            """, (episode_id, user_id))
            
            # Insert new session
            conn.execute("""
                INSERT INTO ActiveTrackingSessions 
                (episode_id, player_entity_id, episode_url, user_id, started_at)
                VALUES (?, ?, ?, ?, datetime('now'))
                """, (episode_id, player_entity_id, episode_url, user_id))
            
            conn.commit()
            logger.info(f"Started tracking session: episode {episode_id} on {player_entity_id}")
            
    except Exception as e:
        logger.error(f"Error starting tracking session: {e}")

def end_tracking_session(session_id):
    """End tracking session"""
    try:
        with get_db_connection() as conn:
            conn.execute("DELETE FROM ActiveTrackingSessions WHERE id = ?", (session_id,))
            conn.commit()
            logger.info(f"Ended tracking session: {session_id}")
    except Exception as e:
        logger.error(f"Error ending tracking session: {e}")

def get_active_sessions():
    """Get all active tracking sessions"""
    try:
        with get_db_connection() as conn:
            sessions = conn.execute("""
                SELECT * FROM ActiveTrackingSessions
            """).fetchall()
            return [dict(session) for session in sessions]
    except Exception as e:
        logger.error(f"Error getting active sessions: {e}")
        return []

async def get_player_state_from_ha(player_entity_id):
    """Get current state of media player from Home Assistant - improved version"""
    try:
        supervisor_token = os.environ.get('SUPERVISOR_TOKEN')
        if not supervisor_token:
            logger.error("No Supervisor token available")
            return None

        headers = {
            "Authorization": f"Bearer {supervisor_token}",
            "Content-Type": "application/json",
        }

        # Get player state from HA API
        response = requests.get(
            f"http://supervisor/core/api/states/{player_entity_id}",
            headers=headers,
            timeout=5
        )

        if not response.ok:
            logger.error(f"Error fetching player state: {response.status_code}")
            return None

        state_data = response.json()
        
        # Extract relevant attributes
        attributes = state_data.get('attributes', {})
        player_state = {
            'state': state_data.get('state', 'unknown'),
            'media_content_id': attributes.get('media_content_id', ''),
            'media_position': attributes.get('media_position', 0),
            'media_duration': attributes.get('media_duration', 0),
            'media_position_updated_at': attributes.get('media_position_updated_at', ''),
            'media_title': attributes.get('media_title', ''),
        }
        
        return player_state
        
    except Exception as e:
        logger.error(f"Error getting player state for {player_entity_id}: {e}")
        return None 

def update_session_position_tracking(session_id, position, count):
    """Update session position tracking data"""
    try:
        with get_db_connection() as conn:
            conn.execute("""
                UPDATE ActiveTrackingSessions 
                SET last_position = ?, same_position_count = ?
                WHERE id = ?
            """, (position, count, session_id))
            conn.commit()
    except Exception as e:
        logger.error(f"Error updating session position tracking: {e}")  

async def monitor_active_sessions():
    """Monitor all active tracking sessions"""
    logger.info("Starting playback tracking monitor...")
    
    while not tracking_thread_stop_event.is_set():
        try:
            sessions = get_active_sessions()
            
            for session in sessions:
                try:
                    # Get current player state from HA
                    player_state = await get_player_state_from_ha(session['player_entity_id'])
                    
                    if not player_state:
                        continue
                    
                    # Check if player is still playing our episode
                    playing_url = player_state['media_content_id'].replace("builtin://track/", "")
                    our_url = session['episode_url']
                    
                    if playing_url == our_url:
                        # This is our episode - handle tracking
                        position = player_state['media_position']
                        duration = player_state['media_duration']
                        state = player_state['state']
    
                        last_position = session.get('last_position', -1)
                        same_count = session.get('same_position_count', 0)
    
                        if state == "paused" and position > 0:
                            # PAUSE - save position
                            await save_playback_position(session['episode_id'], position, session['user_id'])
        
                            # Check if position is same as before
                            if position == last_position:
                                same_count += 1
                                logger.info(f"Saved position {position} for episode {session['episode_id']} (count: {same_count})")
            
                                if same_count >= 5:
                                    # Same position 5 times - stop tracking
                                    end_tracking_session(session['id'])
                                    logger.info(f"Stopped tracking session {session['id']} - paused for 5+ checks")
                                    continue
                            else:
                                # Position changed - reset counter
                                same_count = 0
                                logger.info(f"Saved position {position} for episode {session['episode_id']} (position changed)")
        
                            # Update session tracking data
                            update_session_position_tracking(session['id'], position, same_count)
        
                        elif position != last_position and state == "playing":
                            # Position changed during playing - reset counter and update
                            update_session_position_tracking(session['id'], position, 0)
        
                        elif position == 0 and duration > 0 and state != "playing":
                            # Only consider completed if session has been running for at least 15 seconds
                            from datetime import datetime
                            session_start = datetime.fromisoformat(session['started_at'])
                            session_age = (datetime.now() - session_start).total_seconds()

                            if session_age > 15:  # Only after 15 seconds
                                # EPISODE COMPLETED
                                pass

                    else:
                        # Not our episode anymore - stop tracking
                        end_tracking_session(session['id'])
                        logger.info(f"Stopped tracking session {session['id']} - different content playing")
                        
                except Exception as e:
                    logger.error(f"Error processing session {session.get('id', 'unknown')}: {e}")
            
            # Wait 1 second before next check
            if tracking_thread_stop_event.wait(timeout=1.0):
                break
                
        except Exception as e:
            logger.error(f"Error in monitor_active_sessions: {e}")
            # Wait before retrying
            if tracking_thread_stop_event.wait(timeout=5.0):
                break
    
    logger.info("Playback tracking monitor stopped.")
async def save_playback_position(episode_id, position, user_id):
    """Save playback position (async wrapper for existing function)"""
    try:
        with get_db_connection() as conn:
            conn.execute("""
                INSERT INTO EpisodePlaybackPosition (episode_id, user_id, position, timestamp)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(episode_id, user_id) 
                DO UPDATE SET position = ?, timestamp = datetime('now')
            """, (episode_id, user_id, position, position))
            conn.commit()
    except Exception as e:
        logger.error(f"Error saving playback position: {e}")

async def mark_episode_listened(episode_id, user_id):
    """Mark episode as listened (async wrapper for existing function)"""
    try:
        with get_db_connection() as conn:
            conn.execute("""
                INSERT INTO EpisodeListenStatus (episode_id, user_id, poslušano, timestamp)
                VALUES (?, ?, 1, datetime('now'))
                ON CONFLICT(episode_id, user_id) 
                DO UPDATE SET poslušano = 1, timestamp = datetime('now')
            """, (episode_id, user_id))
            conn.commit()
    except Exception as e:
        logger.error(f"Error marking episode as listened: {e}")

def tracking_loop():
    """Main tracking loop that runs in separate thread"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(monitor_active_sessions())
    finally:
        loop.close()

def start_tracking_thread():
    """Start tracking thread"""
    global tracking_thread, tracking_thread_stop_event
    
    # First stop existing thread if it exists
    if tracking_thread and tracking_thread.is_alive():
        logger.info("Stopping existing tracking thread...")
        tracking_thread_stop_event.set()
        tracking_thread.join(timeout=5)
        tracking_thread_stop_event.clear()
    
    # Start new thread
    logger.info("Starting new tracking thread...")
    tracking_thread = threading.Thread(target=tracking_loop, daemon=True)
    tracking_thread.start()
    logger.info("Tracking thread started.")

# Start automatic updates in separate thread
start_update_thread()

# Start tracking thread for playback monitoring
start_tracking_thread()

# API for getting latest added episodes from each podcast
@app.route('/api/latest_episodes', methods=['GET'])
def get_latest_episodes():
    limit = request.args.get('limit', 10, type=int)
    # Get user ID from query parameters
    as_user_id = request.args.get('as_user', type=int)
    
    # Get current user
    username = get_current_user()
    current_user = get_user_from_db(username)
    
    if not current_user:
        return jsonify({"error": "Napaka pri preverjanju uporabnika."}), 500

    # Determine for which user we're displaying episodes
    if as_user_id:
        # Check if current user has permission to see another user's episodes
        if not current_user['is_tab_user'] and not current_user['is_admin']:
            return jsonify({"error": "Nimate pravice videti epizod drugega uporabnika."}), 403
            
        # Get target user data
        with get_db_connection() as conn:
            target_user = conn.execute("SELECT * FROM Users WHERE id = ?", (as_user_id,)).fetchone()
            if not target_user:
                return jsonify({"error": "Uporabnik ne obstaja"}), 404
                
        check_user_id = as_user_id
        is_admin = target_user['is_admin'] == 1
    else:
        # Using current user
        check_user_id = current_user['id']
        is_admin = current_user['is_admin'] == 1

    with get_db_connection() as conn:
        # For each accessible podcast, get the latest unlistened episode
        if is_admin:
            # Admin uporabnik vidi vse epizode
            podcast_filter = ""
            params = (check_user_id, check_user_id, limit)
        else:
            # Regular users see episodes from their podcasts and public podcasts
            # Add filter for hidden podcasts as well
            podcast_filter = """
                AND (p.user_id = ? OR p.is_public = 1)
                AND (pvp.hidden IS NULL OR pvp.hidden = 0)
            """
            params = (check_user_id, check_user_id, check_user_id, limit)
            
        query = f"""
            WITH LatestEpisodes AS (
                SELECT 
                    e.*,
                    p.naslov as podcast_naslov,
                    p.image_url,
                    COALESCE(els.poslušano, 0) as uporabnik_poslušal,
                    ROW_NUMBER() OVER (PARTITION BY e.podcast_id ORDER BY datetime(e.datum_izdaje) DESC) as rn
                FROM Episodes e
                JOIN Podcasts p ON e.podcast_id = p.id
                LEFT JOIN EpisodeListenStatus els ON e.id = els.episode_id AND els.user_id = ?
                LEFT JOIN PodcastVisibilityPreferences pvp ON p.id = pvp.podcast_id AND pvp.user_id = ?
                WHERE e.izbrisano IS NOT 1 {podcast_filter}
            )
            SELECT * FROM LatestEpisodes
            WHERE rn = 1 AND uporabnik_poslušal = 0
            ORDER BY datetime(datum_izdaje) DESC
            LIMIT ?
        """
        episodes = conn.execute(query, params).fetchall()
        
        # If there aren't enough unlistened episodes, add listened ones too
        if len(episodes) < limit:
            remaining = limit - len(episodes)
            # Get podcasts for which we haven't found episodes yet
            existing_podcast_ids = [ep['podcast_id'] for ep in episodes]
            existing_ids_str = ','.join('?' for _ in existing_podcast_ids) if existing_podcast_ids else '0'
            
            if is_admin:
                # Admin user sees all episodes
                podcast_filter = ""
                # Here's the key fix - correct number of parameters
                if existing_podcast_ids:
                    params = [check_user_id] + existing_podcast_ids + [remaining]
                else:
                    params = [check_user_id, remaining]
            else:
                # Regular users see episodes from their podcasts and public podcasts
                # Add filter for hidden podcasts as well
                podcast_filter = """
                    AND (p.user_id = ? OR p.is_public = 1)
                    AND (pvp.hidden IS NULL OR pvp.hidden = 0)
                """
                # Here's the key fix - correct number of parameters
                if existing_podcast_ids:
                    params = [check_user_id, check_user_id] + existing_podcast_ids + [remaining]
                else:
                    params = [check_user_id, check_user_id, remaining]

            additional_query = f"""
                WITH LatestEpisodes AS (
                    SELECT 
                        e.*,
                        p.naslov as podcast_naslov,
                        p.image_url,
                        ROW_NUMBER() OVER (PARTITION BY e.podcast_id ORDER BY datetime(e.datum_izdaje) DESC) as rn
                    FROM Episodes e
                    JOIN Podcasts p ON e.podcast_id = p.id
                    LEFT JOIN PodcastVisibilityPreferences pvp ON p.id = pvp.podcast_id AND pvp.user_id = ?
                    WHERE e.izbrisano IS NOT 1 
                    AND (e.podcast_id NOT IN ({existing_ids_str}) OR 1=1) {podcast_filter}
                )
                SELECT * FROM LatestEpisodes
                WHERE rn = 1
                ORDER BY datetime(datum_izdaje) DESC
                LIMIT ?
            """
            additional_episodes = conn.execute(additional_query, params).fetchall()
            
            # Merge results
            for ep in additional_episodes:
                if ep['podcast_id'] not in existing_podcast_ids:
                    episodes.append(ep)
                    if len(episodes) >= limit:
                        break

    result = []
    for episode in episodes:
        ep_dict = dict(episode)
        # Remove helper columns
        for key in ['rn', 'uporabnik_poslušal']:
            if key in ep_dict:
                del ep_dict[key]
        result.append(ep_dict)
    return jsonify(result)

# API for getting paused episodes for current user
@app.route('/api/episodes/paused', methods=['GET'])
def get_paused_episodes():
    limit = request.args.get('limit', 3, type=int)
    # Get user ID from query parameters
    as_user_id = request.args.get('as_user', type=int)
    
    # Get current user
    username = get_current_user()
    current_user = get_user_from_db(username)
    
    if not current_user:
        return jsonify({"error": "Napaka pri preverjanju uporabnika."}), 500

    # Determine for which user we're displaying paused episodes
    if as_user_id:
        # Check if current user has permission to see another user's episodes
        if not current_user['is_tab_user'] and not current_user['is_admin']:
            return jsonify({"error": "Nimate pravice videti epizod drugega uporabnika."}), 403
            
        check_user_id = as_user_id
    else:
        # Using current user
        check_user_id = current_user['id']

    with get_db_connection() as conn:
        # Get target user data
        target_user = conn.execute("SELECT * FROM Users WHERE id = ?", (check_user_id,)).fetchone()
        
        if current_user['is_admin'] == 1 and not as_user_id:
            # Admin user without as_user parameter - show all paused episodes
            episodes = conn.execute("""
                SELECT 
                    e.id as episode_id,
                    e.podcast_id,
                    e.naslov as episode_naslov,
                    p.naslov as podcast_naslov,
                    p.image_url,
                    epp.position,
                    epp.timestamp,
                    u.display_name as user_display_name
                FROM EpisodePlaybackPosition epp
                JOIN Episodes e ON epp.episode_id = e.id
                JOIN Podcasts p ON e.podcast_id = p.id
                JOIN Users u ON epp.user_id = u.id
                WHERE epp.position > 0
                AND e.izbrisano != 1
                ORDER BY epp.timestamp DESC
                LIMIT ?
            """, (limit,)).fetchall()
        else:
            # Regular user, tab user or admin with as_user - show specific user's episodes
            episodes = conn.execute("""
                SELECT 
                    e.id as episode_id,
                    e.podcast_id,
                    e.naslov as episode_naslov,
                    p.naslov as podcast_naslov,
                    p.image_url,
                    epp.position,
                    epp.timestamp
                FROM EpisodePlaybackPosition epp
                JOIN Episodes e ON epp.episode_id = e.id
                JOIN Podcasts p ON e.podcast_id = p.id
                LEFT JOIN PodcastVisibilityPreferences pvp ON p.id = pvp.podcast_id AND pvp.user_id = ?
                WHERE epp.user_id = ? 
                AND epp.position > 0
                AND e.izbrisano != 1
                AND (pvp.hidden IS NULL OR pvp.hidden = 0)
                ORDER BY epp.timestamp DESC
                LIMIT ?
            """, (current_user['id'], check_user_id, limit)).fetchall()
        
    # Convert results and add formatted time
    result = []
    for episode in episodes:
        ep_dict = dict(episode)
        # Add formatted playback time
        minutes = ep_dict['position'] // 60
        seconds = ep_dict['position'] % 60
        ep_dict['playback_time_formatted'] = f"{minutes}:{seconds:02d}"
        result.append(ep_dict)
    
    logger.info(f"Found {len(result)} paused episodes for user {check_user_id}")
    return jsonify(result)


# Add new APIs for user management

# API for getting list of all users
@app.route('/api/users', methods=['GET'])
def get_users():
    try:
        with get_db_connection() as conn:
            users = conn.execute("""
                SELECT id, username, display_name, is_admin, is_tab_user, created_at 
                FROM Users
                ORDER BY display_name
            """).fetchall()
        
        return jsonify({'users': [dict(user) for user in users]})
    except Exception as e:
        logger.error(f"Error retrieving users: {e}")
        return jsonify({"error": str(e)}), 500

# API for getting users who have podcasts
@app.route('/api/users/with_podcasts', methods=['GET'])
def get_users_with_podcasts():
    try:
        with get_db_connection() as conn:
            users = conn.execute("""
                SELECT u.id, u.username, u.display_name, u.is_admin, u.is_tab_user, u.created_at,
                       COUNT(p.id) as podcast_count
                FROM Users u
                LEFT JOIN Podcasts p ON u.id = p.user_id
                GROUP BY u.id
                HAVING podcast_count > 0
                ORDER BY u.display_name
            """).fetchall()
        
        return jsonify({'users': [dict(user) for user in users]})
    except Exception as e:
        logger.error(f"Error retrieving users with podcasts: {e}")
        return jsonify({"error": str(e)}), 500

# API for getting current user
@app.route('/api/users/current', methods=['GET'])
def get_current_user_info():
    try:
        username = get_current_user()
        user = get_user_from_db(username)
        
        if not user:
            return jsonify({"error": "Uporabnik ni najden"}), 404
        
        # Check if user is tab user
        with get_db_connection() as conn:
            tab_user = conn.execute("""
                SELECT u.id, u.username, u.display_name
                FROM Users u
                WHERE u.is_tab_user = 1
                LIMIT 1
            """).fetchone()
        
        # If current user is tab user, return this information
        is_tab_user = user['is_tab_user'] == 1
        result = {
            'id': user['id'],
            'username': user['username'],
            'display_name': user['display_name'],
            'is_admin': user['is_admin'] == 1,
            'is_tab_user': is_tab_user,
        }
        
        # If this user is tab user, add information about it
        if is_tab_user and tab_user:
            result['is_central_user'] = True
        else:
            result['is_central_user'] = False
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error retrieving current user info: {e}")
        return jsonify({"error": str(e)}), 500

# API for setting tab user
@app.route('/api/users/settings', methods=['POST'])
def update_user_settings():
    try:
        data = request.json
        tab_user_id = data.get('tab_user_id')
        
        with get_db_connection() as conn:
            # First reset all existing tab users
            conn.execute("UPDATE Users SET is_tab_user = 0")
            
            # If ID was provided, set new tab user
            if tab_user_id:
                conn.execute("UPDATE Users SET is_tab_user = 1 WHERE id = ?", (tab_user_id,))
            
            conn.commit()
        
        # Invalidate cache for all users to ensure changes take effect immediately
        invalidate_user_cache()
        
        return jsonify({"message": "Nastavitve uporabnikov uspešno posodobljene"})
    except Exception as e:
        logger.error(f"Napaka pri posodabljanju uporabniških nastavitev: {e}")
        return jsonify({"error": str(e)}), 500

# API for getting specific user's podcasts
@app.route('/api/users/<int:user_id>/podcasts', methods=['GET'])
def get_user_podcasts(user_id):
    try:
        # First check if user exists
        with get_db_connection() as conn:
            user = conn.execute("SELECT * FROM Users WHERE id = ?", (user_id,)).fetchone()
            
            if not user:
                return jsonify({"error": "Uporabnik ne obstaja"}), 404
            
            # Get current user (the one who is logged in)
            current_username = get_current_user()
            current_user = get_user_from_db(current_username)
            
            if not current_user:
                return jsonify({"error": "Napaka pri preverjanju trenutnega uporabnika."}), 500
            
            # Different cases for different user types
            is_current_admin = current_user['is_admin'] == 1
            is_current_tab_user = current_user['is_tab_user'] == 1
            is_user_admin = user['is_admin'] == 1
            is_self_view = current_user['id'] == user_id
            
            logger.info(f"get_user_podcasts: current_user={current_user['username']}, is_admin={is_current_admin}, is_tab={is_current_tab_user}, viewing_user_id={user_id}, is_self={is_self_view}")
            
            # 1. If viewing admin user, return all podcasts
            if is_user_admin:
                podcasts = conn.execute("""
                    SELECT p.*, u.display_name as user_display_name 
                    FROM Podcasts p
                    LEFT JOIN Users u ON p.user_id = u.id
                    ORDER BY p.naslov
                """).fetchall()
                logger.info(f"I am returning all podcasts for the admin user. {user_id}")
                
            # 2. If current user is admin or viewing their own podcasts
            elif is_current_admin or is_self_view:
                podcasts = conn.execute("""
                    SELECT p.*, u.display_name as user_display_name 
                    FROM Podcasts p
                    LEFT JOIN Users u ON p.user_id = u.id
                    WHERE p.user_id = ?
                    ORDER BY p.naslov
                """, (user_id,)).fetchall()
                logger.info(f"User {current_user['id']} is watching podcasts from user {user_id}")
                
            # 3. If current user is tab user
            elif is_current_tab_user:
                # Tab user can see all podcasts of selected user + public podcasts
                podcasts = conn.execute("""
                    SELECT 
                        p.id,
                        p.naslov,
                        p.rss_url,
                        p.datum_naročnine,
                        p.image_url,
                        p.description,
                        p.user_id,
                        p.is_public,
                        u.display_name as user_display_name
                    FROM Podcasts p
                    LEFT JOIN Users u ON p.user_id = u.id
                    LEFT JOIN PodcastVisibilityPreferences pvp ON p.id = pvp.podcast_id AND pvp.user_id = ?
                    WHERE (p.user_id = ? OR p.is_public = 1)
                    AND (pvp.hidden IS NULL OR pvp.hidden = 0)
                    ORDER BY p.naslov
                """, (user_id, user_id)).fetchall()
                logger.info(f"Tab user {current_user['id']} is watching podcasts by user {user_id} (found: {len(podcasts)})")
                
            # 4. Other cases (regular users viewing other users)
            else:
                # Show only public podcasts of this user
                podcasts = conn.execute("""
                    SELECT p.*, u.display_name as user_display_name
                    FROM Podcasts p
                    LEFT JOIN Users u ON p.user_id = u.id
                    WHERE p.user_id = ? AND p.is_public = 1
                    ORDER BY p.naslov
               
                """, (user_id,)).fetchall()
                logger.info(f"User {current_user['id']} is watching public podcasts from user {user_id}")
            
            # Additional output for debugging
            logger.info(f"Found {len(podcasts)} podcasts")
        
        return jsonify({'podcasts': [dict(podcast) for podcast in podcasts]})
    except Exception as e:
        logger.error(f"Error retrieving user podcasts: {e}")
        return jsonify({"error": str(e)}), 500

# API for getting latest episodes of specific user
@app.route('/api/users/<int:user_id>/latest_episodes', methods=['GET'])
def get_user_latest_episodes(user_id):
    limit = request.args.get('limit', 10, type=int)
    
    try:
        with get_db_connection() as conn:
            # Check if user exists
            user = conn.execute("SELECT * FROM Users WHERE id = ?", (user_id,)).fetchone()
            
            if not user:
                return jsonify({"error": "Uporabnik ne obstaja"}), 404
            
            # Get current user (the one who is logged in)
            current_username = get_current_user()
            current_user = get_user_from_db(current_username)
            
            if not current_user:
                return jsonify({"error": "Napaka pri preverjanju trenutnega uporabnika."}), 500
            
            # Different cases for different user types
            is_current_admin = current_user['is_admin'] == 1
            is_current_tab_user = current_user['is_tab_user'] == 1
            is_user_admin = user['is_admin'] == 1
            is_self_view = current_user['id'] == user_id
            
            # Determine which podcasts the user can see
            if is_user_admin or is_current_admin or is_self_view or is_current_tab_user:
                # Can see all user's podcasts (considering hidden podcasts for current user)
                podcast_filter = "AND p.user_id = ?"
                if is_self_view or is_current_tab_user:
                    # For own podcasts or as tab user, consider hidden podcasts
                    podcast_filter += " AND (pvp.hidden IS NULL OR pvp.hidden = 0)"
                    params = (user_id, current_user['id'], user_id, limit)
                else:
                    # As admin, viewing all user's podcasts (without filtering hidden)
                    params = (user_id, user_id, limit)
            else:
                # Can see only public podcasts of the user (considering hidden podcasts)
                podcast_filter = """
                    AND p.user_id = ? AND p.is_public = 1
                    AND (pvp.hidden IS NULL OR pvp.hidden = 0)
                """
                params = (user_id, current_user['id'], user_id, limit)
            
            # For each podcast, get the latest unlistened episode
            query = f"""
                WITH LatestEpisodes AS (
                    SELECT 
                        e.*,
                        p.naslov as podcast_naslov,
                        p.image_url,
                        COALESCE(els.poslušano, 0) as uporabnik_poslušal,
                        ROW_NUMBER() OVER (PARTITION BY e.podcast_id ORDER BY datetime(e.datum_izdaje) DESC) as rn
                    FROM Episodes e
                    JOIN Podcasts p ON e.podcast_id = p.id
                    LEFT JOIN EpisodeListenStatus els ON e.id = els.episode_id AND els.user_id = ?
                    LEFT JOIN PodcastVisibilityPreferences pvp ON p.id = pvp.podcast_id AND pvp.user_id = ?
                    WHERE e.izbrisano IS NOT 1 {podcast_filter}
                )
                SELECT * FROM LatestEpisodes
                WHERE rn = 1
                ORDER BY datetime(datum_izdaje) DESC
                LIMIT ?
            """
            
            episodes = conn.execute(query, params).fetchall()
            logger.info(f"Found {len(episodes)} episodes for the user {user_id}")
            
        result = []
        for episode in episodes:
            ep_dict = dict(episode)
            # Remove helper columns
            for key in ['rn', 'uporabnik_poslušal']:
                if key in ep_dict:
                    del ep_dict[key]
            result.append(ep_dict)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Napaka pri pridobivanju zadnjih epizod uporabnika: {e}")
        return jsonify({"error": str(e)}), 500

# API for updating podcast visibility
@app.route('/api/podcasts/<int:podcast_id>/visibility', methods=['PATCH'])
def update_podcast_visibility(podcast_id):
    data = request.json
    is_public = data.get('is_public')

    if is_public is None:
        return jsonify({"error": "Manjka parameter 'is_public'."}), 400

    username = get_current_user()
    user = get_user_from_db(username) 

    if not user:
        return jsonify({"error": "Napaka pri preverjanju uporabnika."}), 500

    conn = get_db_connection()
    podcast = conn.execute("SELECT * FROM Podcasts WHERE id = ?", (podcast_id,)).fetchone()

    if not podcast:
        conn.close()
        return jsonify({"error": "Podcast ne obstaja."}), 404

    # Check if user has permission to edit podcast
    if podcast['user_id'] != user['id'] and not user['is_admin']:
        conn.close()
        return jsonify({"error": "Nimate dovoljenja za urejanje tega podcasta."}), 403

    conn.execute("UPDATE Podcasts SET is_public = ? WHERE id = ?", (is_public, podcast_id))
    conn.commit()
    conn.close()

    return jsonify({"message": "Vidnost podcasta uspešno posodobljena."}), 200

# API for hiding podcast for current user
@app.route('/api/podcasts/<int:podcast_id>/hide', methods=['POST'])
def hide_podcast(podcast_id):
    username = get_current_user()
    user = get_user_from_db(username)

    if not user:
        return jsonify({"error": "Uporabnik ni registriran v sistemu."}), 401

    conn = get_db_connection()
    
    # Check if podcast exists
    podcast = conn.execute("SELECT * FROM Podcasts WHERE id = ?", (podcast_id,)).fetchone()
    if not podcast:
        conn.close()
        return jsonify({"error": "Podcast ne obstaja."}), 404
    
        
    # Check if visibility record already exists
    visibility = conn.execute("""
        SELECT * FROM PodcastVisibilityPreferences 
        WHERE podcast_id = ? AND user_id = ?
    """, (podcast_id, user['id'])).fetchone()
    
    if visibility:
        # Update existing record
        conn.execute("""
            UPDATE PodcastVisibilityPreferences
            SET hidden = 1
            WHERE podcast_id = ? AND user_id = ?
        """, (podcast_id, user['id']))
    else:
        # Create new record
        conn.execute("""
            INSERT INTO PodcastVisibilityPreferences (podcast_id, user_id, hidden)
            VALUES (?, ?, 1)
        """, (podcast_id, user['id']))
    
    conn.commit()
    conn.close()
    
    logger.info(f"User {user['username']} hid the podcast {podcast_id}")
    return jsonify({"message": "Podcast successfully hidden."}), 200

# API for showing podcast for current user
@app.route('/api/podcasts/<int:podcast_id>/show', methods=['POST'])
def show_podcast(podcast_id):
    username = get_current_user()
    user = get_user_from_db(username)

    if not user:
        return jsonify({"error": "Uporabnik ni registriran v sistemu."}), 401

    conn = get_db_connection()
    
    # Check if podcast exists
    podcast = conn.execute("SELECT * FROM Podcasts WHERE id = ?", (podcast_id,)).fetchone()
    if not podcast:
        conn.close()
        return jsonify({"error": "Podcast ne obstaja."}), 404
    
    # Delete or update visibility record
    conn.execute("""
        DELETE FROM PodcastVisibilityPreferences
        WHERE podcast_id = ? AND user_id = ?
    """, (podcast_id, user['id']))
    
    conn.commit()
    conn.close()
    
    logger.info(f"User {user['username']} showed a podcast {podcast_id}")
    return jsonify({"message": "Podcast successfully displayed."}), 200

# API for getting hidden podcasts for current user
@app.route('/api/podcasts/hidden', methods=['GET'])
def get_hidden_podcasts():
    username = get_current_user()
    user = get_user_from_db(username)

    if not user:
        return jsonify({"error": "Uporabnik ni registriran v sistemu."}), 401

    conn = get_db_connection()
    
    # Get all hidden podcasts
    podcasts = conn.execute("""
        SELECT p.*, u.display_name as user_display_name 
        FROM Podcasts p
        LEFT JOIN Users u ON p.user_id = u.id
        JOIN PodcastVisibilityPreferences pvp ON p.id = pvp.podcast_id
        WHERE pvp.user_id = ? AND pvp.hidden = 1
    """, (user['id'],)).fetchall()
    
    conn.close()
    logger.info(f"Found {len(podcasts)} hidden podcasts for the user {user['username']}.")
    return jsonify([dict(podcast) for podcast in podcasts])

# add endpoint for managing admin status
@app.route('/api/users/admin_status', methods=['POST'])
def update_user_admin_status():
    try:
        data = request.json
        user_id = data.get('user_id')
        is_admin = data.get('is_admin', 0)

        if not user_id:
            return jsonify({"error": "Manjka user_id"}), 400

        # Check if current user exists and is admin
        current_username = get_current_user()
        current_user = get_user_from_db(current_username)
        
        if not current_user or not current_user['is_admin']:
            return jsonify({"error": "Nimate pravic za spreminjanje admin statusa."}), 403

        with get_db_connection() as conn:
            # Check if user exists
            user = conn.execute("SELECT * FROM Users WHERE id = ?", (user_id,)).fetchone()
            if not user:
                return jsonify({"error": "Uporabnik ne obstaja"}), 404

            conn.execute("""
                UPDATE Users 
                SET is_admin = ?
                WHERE id = ?
            """, (is_admin, user_id))
            conn.commit()

            logger.info(f"Updated admin status for user {user_id} on {is_admin}")
            
        return jsonify({
            "message": "Admin status successfully updated",
            "user_id": user_id,
            "is_admin": is_admin
        })

    except Exception as e:
        logger.error(f"Error updating admin status: {e}")
        return jsonify({"error": str(e)}), 500