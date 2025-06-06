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

# Globalni cache za uporabnike
# Struktura: {'username': {'user_data': {...}, 'timestamp': time.time()}}
USER_CACHE = {}
# Trajanje veljavnosti cache-a v sekundah (1 ura)
CACHE_EXPIRY = 3600  # 1 ura

app = Flask(__name__, static_folder="/app/static")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)  # Dodana definicija logger-ja

# Globalna spremenljivka za sledenje niti za posodobitve
update_thread = None
update_thread_stop_event = threading.Event()

# Funkcija za povezavo z bazo
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

# Funkcija za pridobivanje informacij o trenutnem uporabniku
def get_current_user():
    """Pridobi trenutnega uporabnika izključno iz glave zahtevka."""
    try:
        # Samo preverimo vrednost v X-Remote-User-Name ali X-Remote-User-Display-Name
        username = request.headers.get('X-Remote-User-Name')
        
        if username:
            logger.debug(f"User obtained from X-Remote-User-Name: {username}")
            return username
            
        # Poskusimo še z X-Remote-User-Display-Name, če X-Remote-User-Name ni na voljo
        username = request.headers.get('X-Remote-User-Display-Name')
        if username:
            logger.debug(f"User obtained from X-Remote-User-Display-Name: {username}")
            return username
            
        # Za diagnostične namene izpišimo vse glave samo pri prvem nedefiniranem uporabniku
        if 'auth_headers_logged' not in globals():
            globals()['auth_headers_logged'] = True
            logger.debug(f"All headers: {dict(request.headers)}")
        
        # Če uporabnika nismo pridobili iz glav, uporabimo 'admin' kot privzeto vrednost
        logger.debug("User not found in request headers, using 'admin'")
        return "admin"
        
    except Exception as e:
        logger.error(f"Error retrieving user: {e}")
        return "admin"  # Varnostno vračanje privzete vrednosti v primeru napake
    
# Funkcija za invalidacijo cache-a
def invalidate_user_cache(username=None):
    """
    Izbriše cache za določenega uporabnika ali za vse uporabnike.
    
    Args:
        username (str, optional): Uporabniško ime za katerega želite izbrisati cache.
                                  Če je None, se izbriše cache za vse uporabnike.
    """
    global USER_CACHE
    if username:
        if username in USER_CACHE:
            del USER_CACHE[username]
            logger.debug(f"Cache for user {username} has been cleared")
    else:
        USER_CACHE = {}
        logger.debug("Cache for all users has been cleared")

# API za upravljanje s cache-om
@app.route('/api/cache/status', methods=['GET'])
def cache_status():
    """Prikaže stanje cache-a uporabnikov"""
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
    """Izbriše cache za vse ali določene uporabnike"""
    data = request.json or {}
    username = data.get('username')
    
    invalidate_user_cache(username)
    
    return jsonify({
        'message': f"Cache {'za uporabnika ' + username if username else 'za vse uporabnike'} je bil uspešno izbrisan."
    })

# Funkcija za preverjanje in ustvarjanje uporabnika v bazi
def get_user_from_db(username):
    """Preveri, ali uporabnik obstaja, in ga ustvari, če ne obstaja"""
    if not username:
        logger.error("Empty username!")
        return None
    
    # Preveri cache
    if username in USER_CACHE:
        cache_entry = USER_CACHE[username]
        # Preveri, ali je cache še veljaven
        if time.time() - cache_entry['timestamp'] < CACHE_EXPIRY:
            return cache_entry['user_data']
    
    logger.debug(f"Checking user in database: {username}")
    
    try:
        conn = get_db_connection()
        
        # Najprej preverimo, ali tabela Users obstaja, če ne, jo ustvarimo
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
        
        # Preverimo, ali uporabnik že obstaja
        user = conn.execute(
            "SELECT * FROM Users WHERE username = ?", 
            (username,)
        ).fetchone()
        
        if user:
            logger.debug(f"User {username} already exists in database (ID: {user['id']})")
            user_dict = dict(user)
            # Shrani v cache
            USER_CACHE[username] = {
                'user_data': user_dict,
                'timestamp': time.time()
            }
            conn.close()
            return user_dict
        
        # Če uporabnik ne obstaja, ga ustvarimo
        display_name = username
        
        logger.info(f"Creating new user: {username}")
        
        # Nastavimo admin privilegije na 1, če je uporabnik "admin" ali "A" ali če je to prvi uporabnik
        is_admin = False
        if username.lower() == "admin" or username == "A":
            is_admin = True
            logger.info(f"Assigning admin privileges to user: {username}")
        else:
            # Preverimo, ali je to prvi uporabnik
            first_user = conn.execute("SELECT COUNT(*) as count FROM Users").fetchone()
            if first_user['count'] == 0:
                is_admin = True
                logger.info(f"Assigning admin privileges to first user: {username}")
        
        # POPRAVLJENO: pravilno število parametrov v SQL stavku
        conn.execute(
            """
            INSERT INTO Users (username, display_name, is_admin, is_tab_user, created_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            """,
            (username, display_name, 1 if is_admin else 0, 0)  # is_tab_user je vedno nastavljen na 0 za nove uporabnike
        )
        conn.commit()
        
        # Pridobimo ustvarjenega uporabnika
        user = conn.execute(
            "SELECT * FROM Users WHERE username = ?", 
            (username,)
        ).fetchone()
        conn.close()
        
        if user:
            logger.info(f"User successfully added to database: {username} (ID: {user['id']})")
            user_dict = dict(user)
            # Shrani v cache
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

# API za dodajanje ali posodabljanje redirekcije na tablet.html
@app.route('/', methods=['GET'])
def serve_index():
    # Preveri, ali je uporabnik tab uporabnik
    username = get_current_user()
    user = get_user_from_db(username)
    
    if not user:
        return send_from_directory('/app/static', 'index.html')
    
    # Če je uporabnik tab uporabnik, ga preusmeri na tablet.html
    if user['is_tab_user'] == 1:
        return send_from_directory('/app/static', 'tablet.html')
    
    # Sicer prikaži običajno index.html
    return send_from_directory('/app/static', 'index.html')

# Postrezi podcast.html
@app.route('/podcast.html')
def serve_podcast():
    return send_from_directory('/app/static', 'podcast.html')

# Postrezi script.js
@app.route('/script.js')
def serve_script():
    return send_from_directory('/app/static', 'script.js')

# Postrezi settings.html
@app.route('/settings.html')
def serve_settings():
    return send_from_directory('/app/static', 'settings.html')

# Postrezi tablet.html
@app.route('/tablet.html')
def serve_tablet():
    return send_from_directory('/app/static', 'tablet.html')

# Statične datoteke
@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('/app/static', filename)

# API za pridobivanje vseh podcastov
@app.route('/api/podcasts', methods=['GET'])
def get_podcasts():
    username = get_current_user()
    user = get_user_from_db(username)

    if not user:
        return jsonify({"error": "Uporabnik ni registriran v sistemu."}), 401

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
        # Dodano upoštevanje skritih podcastov
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

# Funkcija za pridobitev opisa iz RSS vira
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

# Funkcija za pridobitev slike iz RSS vira
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

# API za dodajanje podcasta
@app.route('/api/podcasts', methods=['POST'])
def add_podcast():
    data = request.json
    naslov = data.get('naslov')
    rss_url = data.get('rss_url')
    is_public = data.get('is_public', 0)  # Privzeto je podcast zaseben (0)

    if not naslov or not rss_url:
        logger.error("Error: Title and RSS URL are required.")
        return jsonify({"error": "Naslov in RSS URL sta obvezna."}), 400

    # Pridobimo trenutnega uporabnika
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

# API za preverjanje uporabe podcasta pred brisanjem
@app.route('/api/podcasts/<int:podcast_id>/check_usage', methods=['GET'])
def check_podcast_usage(podcast_id):
    try:
        username = get_current_user()
        user = get_user_from_db(username)
        
        if not user:
            return jsonify({"error": "Uporabnik ni registriran v sistemu."}), 401
        
        with get_db_connection() as conn:
            # Preveri, ali podcast obstaja
            podcast = conn.execute("SELECT * FROM Podcasts WHERE id = ?", (podcast_id,)).fetchone()
            if not podcast:
                return jsonify({"error": "Podcast ne obstaja."}), 404
            
            # Preveri, ali je uporabnik lastnik ali admin
            if podcast['user_id'] != user['id'] and not user['is_admin']:
                return jsonify({"error": "Nimate pravice za brisanje tega podcasta."}), 403
            
            # Če ni javen, lahko se direktno briše
            if not podcast['is_public']:
                return jsonify({
                    "can_delete": True,
                    "reason": "private_podcast"
                })
            
            # Če je admin, lahko briše vse
            if user['is_admin']:
                return jsonify({
                    "can_delete": True,
                    "reason": "admin_user"
                })
            
            # Preveri uporabo javnega podcasta
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
            
            # Logika odločanja
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

# API za brisanje podcasta
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

# API za posodobitev vseh podcastov
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

# Dodaj funkcionalnost za označevanje epizod kot poslušanih
@app.route('/api/episodes/mark_listened/<int:episode_id>', methods=['POST'])
def mark_episode_listened(episode_id):
    # Pridobi trenutnega uporabnika
    username = get_current_user()
    user = get_user_from_db(username)
    
    if not user:
        return jsonify({"error": "Uporabnik ni registriran v sistemu."}), 401
    
    # Preveri parametre zahtevka
    data = request.json or {}
    as_user_id = data.get('as_user_id')
    
    # Preveri, ali je trenutni uporabnik tab uporabnik in ali ima pravico označevati poslušanost
    with get_db_connection() as conn:
        # Najprej preverimo, ali epizoda obstaja
        episode = conn.execute("SELECT * FROM Episodes WHERE id = ?", (episode_id,)).fetchone()
        
        if not episode:
            return jsonify({"error": "Epizoda ne obstaja."}), 404
            
        # Določi uporabnika, za katerega beležimo poslušanost
        target_user_id = None
        if as_user_id:
            # Če je trenutni uporabnik tab uporabnik, mu dovolimo uporabo as_user_id
            if user['is_tab_user'] == 1:
                target_user_id = as_user_id
            else:
                return jsonify({"error": "Nimate pravice označevati poslušanosti za druge uporabnike."}), 403
        else:
            target_user_id = user['id']
        
        # Preverimo, ali že obstaja zapis o poslušanju za tega uporabnika
        listen_status = conn.execute("""
            SELECT * FROM EpisodeListenStatus
            WHERE episode_id = ? AND user_id = ?
        """, (episode_id, target_user_id)).fetchone()
        
        if listen_status:
            # Posodobi obstoječi zapis
            conn.execute("""
                UPDATE EpisodeListenStatus
                SET poslušano = 1, timestamp = datetime('now')
                WHERE episode_id = ? AND user_id = ?
            """, (episode_id, target_user_id))
        else:
            # Ustvari nov zapis
            conn.execute("""
                INSERT INTO EpisodeListenStatus (episode_id, user_id, poslušano)
                VALUES (?, ?, 1)
            """, (episode_id, target_user_id))
        
        conn.commit()
        
        logger.info(f"User {username} marked episode {episode_id} as listened for user {target_user_id}")
    
    return jsonify({"message": "Epizoda označena kot poslušana."}), 200


# API za pridobivanje epizod
@app.route('/api/episodes/<int:podcast_id>', methods=['GET'])
def get_episodes(podcast_id):
    # Pridobi trenutnega uporabnika
    username = get_current_user()
    user = get_user_from_db(username)
    
    if not user:
        return jsonify({"error": "Uporabnik ni registriran v sistemu."}), 401
    
    # Preveri parametre zahtevka (za primer, ko se gleda kot drug uporabnik)
    as_user_id = request.args.get('as_user', type=int)
    check_user_id = as_user_id if as_user_id else user['id']
    
    with get_db_connection() as conn:
        # Pridobi epizode s stanjem poslušanja in pozicijo predvajanja za ustreznega uporabnika
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
        return jsonify([])  # Vrnemo prazen seznam namesto napake
    
    # Pretvorimo rezultate v seznam slovarjev in dodamo informacije o predvajanju
    result = []
    for episode in episodes:
        episode_dict = dict(episode)
        # Dodamo formatiran čas predvajanja (za lažji prikaz v uporabniškem vmesniku)
        if episode_dict['playback_position'] > 0:
            minutes = episode_dict['playback_position'] // 60
            seconds = episode_dict['playback_position'] % 60
            episode_dict['playback_time_formatted'] = f"{minutes}:{seconds:02d}"
        else:
            episode_dict['playback_time_formatted'] = "0:00"
        result.append(episode_dict)
    
    return jsonify(result)

# API za brisanje posamezne epizode
@app.route('/api/episodes/<int:episode_id>/delete', methods=['POST'])
def delete_episode(episode_id):
    """Izbriši posamezno epizodo"""
    try:
        # Pridobi trenutnega uporabnika
        username = get_current_user()
        user = get_user_from_db(username)
        
        if not user:
            return jsonify({"error": "Uporabnik ni registriran v sistemu."}), 401
        
        with get_db_connection() as conn:
            # Preveri, ali epizoda obstaja in pridobi podatke o podcasu
            episode = conn.execute("""
                SELECT e.*, p.user_id as podcast_owner_id
                FROM Episodes e
                JOIN Podcasts p ON e.podcast_id = p.id
                WHERE e.id = ?
            """, (episode_id,)).fetchone()
            
            if not episode:
                return jsonify({"error": "Epizoda ne obstaja."}), 404
            
            # Preveri, ali ima uporabnik pravico brisati epizodo
            # Pravico ima lastnik podcasta ali admin
            if episode['podcast_owner_id'] != user['id'] and not user['is_admin']:
                return jsonify({"error": "Nimate pravice brisati te epizode."}), 403
            
            # Označi epizodo kot izbrisano (soft delete)
            conn.execute("""
                UPDATE Episodes 
                SET izbrisano = 1 
                WHERE id = ?
            """, (episode_id,))
            
            # Izbriši tudi povezane podatke o poslušanju in poziciji predvajanja
            conn.execute("DELETE FROM EpisodeListenStatus WHERE episode_id = ?", (episode_id,))
            conn.execute("DELETE FROM EpisodePlaybackPosition WHERE episode_id = ?", (episode_id,))
            
            conn.commit()
            
        logger.info(f"User {user['username']} deleted episode {episode_id}")
        return jsonify({"message": "Epizoda uspešno izbrisana."}), 200
        
    except Exception as e:
        logger.error(f"Error deleting episode: {e}")
        return jsonify({"error": str(e)}), 500

# Funkcija za posodobitev epizod iz RSS vira
def update_episodes(podcast_id, rss_url):
    logger.info(f"Updating podcast ID {podcast_id} from source {rss_url}")
    feed = feedparser.parse(rss_url)
    if feed.bozo:
        logger.info(f"Error reading RSS: {rss_url}")
        return

    with get_db_connection() as conn:
        # Pridobi URL slike in opis podcasta ter posodobi
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
            # Formatiranje datuma
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

            # Dodamo preverjanje za opis epizode
            opis = ""
            if hasattr(entry, 'summary'):
                opis = entry.summary
            elif hasattr(entry, 'description'):
                opis = entry.description

            # Preveri, ali epizoda že obstaja in pridobi njen ID in trenutni opis
            obstojece = conn.execute(
                "SELECT id, opis FROM Episodes WHERE podcast_id = ? AND naslov = ? AND datum_izdaje = ? AND izbrisano IS NOT 1",
                (podcast_id, naslov, datum_izdaje_iso)
            ).fetchone()

            if obstojece:
                # Pridobi trenutni opis iz baze
                obstojeciOpis = obstojece['opis'] if obstojece['opis'] is not None else ""
                # Če je nov opis drugačen in ni prazen, posodobi zapis
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

# Funkcija za izluščenje vseh epizod iz HTML arhiva podanega URL-ja
def scrape_all_episodes_from_html_url(html_url):
    r = requests.get(html_url)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')

    episodes_data = []
    # Prilagodite selektorje glede na dejansko HTML strukturo strani
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

# Endpoint za enkraten uvoz manjkajočih epizod iz poljubnega HTML URL
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
        # Najprej začnemo predvajanje
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

        # Če imamo začetno pozicijo, počakamo daljši čas in pošljemo seek ukaz
        if start_position > 0:
            # Počakamo 5 sekund, da se medij popolnoma naloži
            await asyncio.sleep(5)
            
            seek_command = {
                "type": "call_service",
                "domain": "media_player",
                "service": "media_seek",
                "service_data": {
                    "entity_id": player_entity_id,
                    "seek_position": start_position
                },
                "id": 3
            }
            
            try:
                await ha_websocket_call(seek_command)
                minutes = start_position // 60
                seconds = start_position % 60
                return jsonify({"message": f"Predvajam epizodo od pozicije {minutes}:{seconds:02d}"})
            except Exception as seek_error:
                logger.error(f"Error seeking to position {start_position}: {str(seek_error)}")
                return jsonify({"message": "Predvajam epizodo (pozicija ni bila nastavljena)"})
        
        return jsonify({"message": "Predvajam epizodo"})
    except Exception as e:
        logger.error(f"Error in play_episode: {str(e)}")
        return jsonify({"error": str(e)}), 500

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

# API za inicializacijo uporabnika ob prvem dostopu do aplikacije
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

# API za pridobivanje nastavitev
@app.route('/api/settings', methods=['GET'])
def get_settings():
    with get_db_connection() as conn:
        settings = conn.execute("SELECT * FROM Settings LIMIT 1").fetchone()
        if not settings:
            # Če nastavitve ne obstajajo, ustvari privzete
            current_time = datetime.now().strftime("%H:%M")
            conn.execute("""
                INSERT INTO Settings (avtomatsko, interval, cas_posodobitve, zadnja_posodobitev)
                VALUES (1, 24, ?, datetime('now'))
            """, (current_time,))
            conn.commit()
            settings = conn.execute("SELECT * FROM Settings LIMIT 1").fetchone()
    return jsonify(dict(settings))

# API za posodabljanje nastavitev
@app.route('/api/settings', methods=['POST'])
def update_settings():
    data = request.json
    avtomatsko = data.get('avtomatsko', 1)
    interval = data.get('interval', 24)
    cas_posodobitve = data.get('cas_posodobitve', '03:00')

    with get_db_connection() as conn:
        # Preveri stare nastavitve za primerjavo
        old_settings = conn.execute("SELECT avtomatsko FROM Settings LIMIT 1").fetchone()
        old_avtomatsko = old_settings['avtomatsko'] if old_settings else 0

        # Preveri, če nastavitve obstajajo
        settings = conn.execute("SELECT 1 FROM Settings LIMIT 1").fetchone()
        if settings:
            # Posodobi obstoječe nastavitve
            conn.execute("""
                UPDATE Settings
                SET avtomatsko = ?, interval = ?, cas_posodobitve = ?
                WHERE id = 1
            """, (avtomatsko, interval, cas_posodobitve))
        else:
            # Ustvari nove nastavitve
            conn.execute("""
                INSERT INTO Settings (avtomatsko, interval, cas_posodobitve, zadnja_posodobitev)
                VALUES (?, ?, ?, datetime('now'))
            """, (avtomatsko, interval, cas_posodobitve))
        conn.commit()
    
    logger.info(f"Settings updated: automatic={avtomatsko}, interval={interval}, update_time={cas_posodobitve}")
    
    # Če smo vklopili avtomatsko posodobitev ali spremenili avtomatsko posodobitev,
    # ponovno zaženemo nit za posodobitve
    if avtomatsko == 1 or old_avtomatsko != avtomatsko:
        logger.info("Restarting update thread due to settings change")
        start_update_thread()
    
    return jsonify({"message": "Nastavitve uspešno posodobljene."})

# Funkcija za izračun sekund do naslednje posodobitve
def calculate_seconds_until_next_update():
    try:
        with get_db_connection() as conn:
            settings = conn.execute("SELECT * FROM Settings LIMIT 1").fetchone()
        
        if not settings or settings['avtomatsko'] != 1 or not settings['cas_posodobitve']:
            # Če avtomatska posodobitev ni nastavljena, preveri spet čez eno uro
            return 3600  
        
        # Pridobi trenutni čas
        now = datetime.now()
        
        # Razčleni nastavljen čas posodobitve
        hour, minute = map(int, settings['cas_posodobitve'].split(':'))
        
        # Ustvari datetime objekt za naslednji čas posodobitve
        next_update = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # Če je nastavljen čas že mimo za danes, dodaj en dan ali en teden
        if next_update <= now:
            if settings['interval'] <= 24:  # Dnevna posodobitev
                next_update += timedelta(days=1)
            else:  # Tedenska posodobitev
                next_update += timedelta(days=7)
        # Pri tedenski posodobitvi lahko dodatno preverimo, ali moramo preskočiti več dni
        elif settings['interval'] > 24 and 'zadnja_posodobitev' in settings and settings['zadnja_posodobitev']:
            last_update = datetime.strptime(settings['zadnja_posodobitev'], "%Y-%m-%d %H:%M:%S")
            hours_since_last_update = (now - last_update).total_seconds() / 3600
            
            # Če ni minilo dovolj časa od zadnje posodobitve, preskočimo na naslednji teden
            if hours_since_last_update < settings['interval'] and next_update > last_update:
                next_update += timedelta(days=7)
        
        # Izračunaj sekunde do naslednje posodobitve
        seconds_until_update = (next_update - now).total_seconds()
        
        logger.info(f"Next update at {next_update.strftime('%Y-%m-%d %H:%M:%S')} (over {seconds_until_update/3600:.2f} hours)")
        return max(seconds_until_update, 60)  # Najmanj 1 minuta
    except Exception as e:
        logger.error(f"Error calculating time for next update: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        # V primeru napake preveri ponovno čez 1 uro
        return 3600
    
# API za shranjevanje pozicije predvajanja
@app.route('/api/episodes/<int:episode_id>/position', methods=['POST'])
def save_episode_position(episode_id):
    """Shrani trenutno pozicijo predvajanja za epizodo"""
    try:
        data = request.json
        position = data.get('position')
        
        if position is None:
            return jsonify({"error": "Manjka parameter 'position'"}), 400

        # Pridobi trenutnega uporabnika
        username = get_current_user()
        current_user = get_user_from_db(username)
        
        if not current_user:
            return jsonify({"error": "Napaka pri preverjanju uporabnika."}), 500

        # Preveri as_user parameter
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
            # Preveri ali epizoda obstaja
            episode = conn.execute("SELECT * FROM Episodes WHERE id = ?", (episode_id,)).fetchone()
            if not episode:
                return jsonify({"error": "Epizoda ne obstaja."}), 404

            # Shrani ali posodobi pozicijo
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

# API za pridobivanje pozicije predvajanja
@app.route('/api/episodes/<int:episode_id>/position', methods=['GET'])
def get_episode_position(episode_id):
    """Pridobi zadnjo shranjeno pozicijo predvajanja za epizodo"""
    try:
        # Pridobi trenutnega uporabnika
        username = get_current_user()
        current_user = get_user_from_db(username)
        
        if not current_user:
            return jsonify({"error": "Napaka pri preverjanju uporabnika."}), 500

        # Preveri as_user parameter iz URL
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
            # Preveri ali epizoda obstaja
            episode = conn.execute("SELECT * FROM Episodes WHERE id = ?", (episode_id,)).fetchone()
            if not episode:
                return jsonify({"error": "Epizoda ne obstaja."}), 404

            # Pridobi zadnjo pozicijo
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

# Funkcija za posodobitev avtomatsko
def auto_update_podcasts():
    try:
        logger.info("Starting automatic podcast update...")
        # Posodobi vse podcaste
        with get_db_connection() as conn:
            podcasts = conn.execute("SELECT * FROM Podcasts").fetchall()
            updated = 0
            
            for podcast in podcasts:
                try:
                    update_episodes(podcast['id'], podcast['rss_url'])
                    updated += 1
                except Exception as e:
                    logger.error(f"Napaka pri posodabljanju podcasta {podcast['naslov']}: {e}")
            
            # Posodobi čas zadnje posodobitve
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            conn.execute("UPDATE Settings SET zadnja_posodobitev = ? WHERE id = 1", (now,))
            conn.commit()
        logger.info(f"Automatic update completed. Updated {updated} podcasts.")
        return True
    except Exception as e:
        logger.error(f"Error while auto-updating podcasts: {e}")
        return False

# Funkcija za avtomatsko posodobitev
def auto_update_loop():
    logger.info("Automatic update initialized.")
    while not update_thread_stop_event.is_set():
        try:
            # Izračunaj čas do naslednje posodobitve
            sleep_duration = calculate_seconds_until_next_update()
            
            # Počakaj do naslednje posodobitve
            logger.info(f"I'm sleeping {sleep_duration/3600:.2f} hours until the next update..")
            # Uporabimo wait s časovno omejitvijo namesto sleep, da lahko prej zaznamo zaustavitev
            if update_thread_stop_event.wait(timeout=sleep_duration):
                logger.info("Request received to stop update thread.")
                break
            
            # Preveri še enkrat nastavitve pred posodobitvijo
            with get_db_connection() as conn:
                settings = conn.execute("SELECT * FROM Settings LIMIT 1").fetchone()
            
            if settings and settings['avtomatsko'] == 1:
                logger.info(f"Time for an update! ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
                auto_update_podcasts()
            else:
                logger.info("Automatic update is turned off.")
        except Exception as e:
            logger.error(f"Error in auto_update_loop: {e}")
            time.sleep(300)  # V primeru napake počakaj 5 minut

# Funkcija za varen zagon/ponoven zagon niti
def start_update_thread():
    global update_thread, update_thread_stop_event
    
    # Najprej ustavi obstoječo nit, če obstaja
    if update_thread and update_thread.is_alive():
        logger.info("I'm stopping the existing update thread...")
        update_thread_stop_event.set()  # Pošlji signal za zaustavitev
        update_thread.join(timeout=5)   # Počakaj do 5 sekund, da se nit zaustavi
        update_thread_stop_event.clear()  # Ponastavi dogodek
    
    # Zaženi novo nit
    logger.info("Starting new thread for automatic update...")
    update_thread = threading.Thread(target=auto_update_loop, daemon=True)
    update_thread.start()
    logger.info("New thread for automatic update started.")

# Zagon avtomatskih posodobitev v ločeni niti
start_update_thread()

# API za pridobivanje zadnjih dodanih epizod iz vsakega podcasta
@app.route('/api/latest_episodes', methods=['GET'])
def get_latest_episodes():
    limit = request.args.get('limit', 10, type=int)
    # Pridobimo ID uporabnika iz query parametrov
    as_user_id = request.args.get('as_user', type=int)
    
    # Pridobi trenutnega uporabnika
    username = get_current_user()
    current_user = get_user_from_db(username)
    
    if not current_user:
        return jsonify({"error": "Napaka pri preverjanju uporabnika."}), 500

    # Določi za katerega uporabnika prikazujemo epizode
    if as_user_id:
        # Preveri ali ima trenutni uporabnik pravico videti epizode drugega uporabnika
        if not current_user['is_tab_user'] and not current_user['is_admin']:
            return jsonify({"error": "Nimate pravice videti epizod drugega uporabnika."}), 403
            
        # Pridobi podatke o ciljnem uporabniku
        with get_db_connection() as conn:
            target_user = conn.execute("SELECT * FROM Users WHERE id = ?", (as_user_id,)).fetchone()
            if not target_user:
                return jsonify({"error": "Uporabnik ne obstaja"}), 404
                
        check_user_id = as_user_id
        is_admin = target_user['is_admin'] == 1
    else:
        # Uporabljamo trenutnega uporabnika
        check_user_id = current_user['id']
        is_admin = current_user['is_admin'] == 1

    with get_db_connection() as conn:
        # Za vsakega dostopnega podcasta pridobi zadnjo neposlušano epizodo
        if is_admin:
            # Admin uporabnik vidi vse epizode
            podcast_filter = ""
            params = (check_user_id, check_user_id, limit)
        else:
            # Običajni uporabniki vidijo epizode svojih podcastov in javnih podcastov
            # Dodamo tudi filter za skrite podcaste
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
        
        # Če ni dovolj neposlušanih epizod, dodamo tudi poslušane
        if len(episodes) < limit:
            remaining = limit - len(episodes)
            # Pridobimo podcaste, za katere še nismo našli epizod
            existing_podcast_ids = [ep['podcast_id'] for ep in episodes]
            existing_ids_str = ','.join('?' for _ in existing_podcast_ids) if existing_podcast_ids else '0'
            
            if is_admin:
                # Admin uporabnik vidi vse epizode
                podcast_filter = ""
                # Tukaj je ključni popravek - pravilno število parametrov
                if existing_podcast_ids:
                    params = [check_user_id] + existing_podcast_ids + [remaining]
                else:
                    params = [check_user_id, remaining]
            else:
                # Običajni uporabniki vidijo epizode svojih podcastov in javnih podcastov
                # Dodamo tudi filter za skrite podcaste
                podcast_filter = """
                    AND (p.user_id = ? OR p.is_public = 1)
                    AND (pvp.hidden IS NULL OR pvp.hidden = 0)
                """
                # Tukaj je ključni popravek - pravilno število parametrov
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
            
            # Združimo rezultate
            for ep in additional_episodes:
                if ep['podcast_id'] not in existing_podcast_ids:
                    episodes.append(ep)
                    if len(episodes) >= limit:
                        break

    result = []
    for episode in episodes:
        ep_dict = dict(episode)
        # Odstranimo pomožne stolpce
        for key in ['rn', 'uporabnik_poslušal']:
            if key in ep_dict:
                del ep_dict[key]
        result.append(ep_dict)
    return jsonify(result)

# API za pridobivanje epizod na pavzi za trenutnega uporabnika
@app.route('/api/episodes/paused', methods=['GET'])
def get_paused_episodes():
    limit = request.args.get('limit', 3, type=int)
    # Pridobimo ID uporabnika iz query parametrov
    as_user_id = request.args.get('as_user', type=int)
    
    # Pridobi trenutnega uporabnika
    username = get_current_user()
    current_user = get_user_from_db(username)
    
    if not current_user:
        return jsonify({"error": "Napaka pri preverjanju uporabnika."}), 500

    # Določi za katerega uporabnika prikazujemo epizode na pavzi
    if as_user_id:
        # Preveri ali ima trenutni uporabnik pravico videti epizode drugega uporabnika
        if not current_user['is_tab_user'] and not current_user['is_admin']:
            return jsonify({"error": "Nimate pravice videti epizod drugega uporabnika."}), 403
            
        check_user_id = as_user_id
    else:
        # Uporabljamo trenutnega uporabnika
        check_user_id = current_user['id']

    with get_db_connection() as conn:
        # Pridobi podatke o ciljnem uporabniku
        target_user = conn.execute("SELECT * FROM Users WHERE id = ?", (check_user_id,)).fetchone()
        
        if current_user['is_admin'] == 1 and not as_user_id:
            # Admin uporabnik brez as_user parametra - prikaži vse epizode na pavzi
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
            # Običajni uporabnik, tab uporabnik ali admin z as_user - prikaži epizode specifičnega uporabnika
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
        
    # Pretvori rezultate in dodaj formatiran čas
    result = []
    for episode in episodes:
        ep_dict = dict(episode)
        # Dodamo formatiran čas predvajanja
        minutes = ep_dict['position'] // 60
        seconds = ep_dict['position'] % 60
        ep_dict['playback_time_formatted'] = f"{minutes}:{seconds:02d}"
        result.append(ep_dict)
    
    logger.info(f"Found {len(result)} paused episodes for user {check_user_id}")
    return jsonify(result)


# Dodamo nove API-je za upravljanje z uporabniki

# API za pridobivanje seznama vseh uporabnikov
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

# API za pridobivanje uporabnikov, ki imajo podcaste
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

# API za pridobivanje trenutnega uporabnika
@app.route('/api/users/current', methods=['GET'])
def get_current_user_info():
    try:
        username = get_current_user()
        user = get_user_from_db(username)
        
        if not user:
            return jsonify({"error": "Uporabnik ni najden"}), 404
        
        # Preverimo, če je uporabnik tab user
        with get_db_connection() as conn:
            tab_user = conn.execute("""
                SELECT u.id, u.username, u.display_name
                FROM Users u
                WHERE u.is_tab_user = 1
                LIMIT 1
            """).fetchone()
        
        # Če je trenutni uporabnik tab user, vrnemo te informacije
        is_tab_user = user['is_tab_user'] == 1
        result = {
            'id': user['id'],
            'username': user['username'],
            'display_name': user['display_name'],
            'is_admin': user['is_admin'] == 1,
            'is_tab_user': is_tab_user,
        }
        
        # Če je ta uporabnik tab user, dodamo še podatke o tem
        if is_tab_user and tab_user:
            result['is_central_user'] = True
        else:
            result['is_central_user'] = False
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error retrieving current user info: {e}")
        return jsonify({"error": str(e)}), 500

# API za nastavitev tab uporabnika
@app.route('/api/users/settings', methods=['POST'])
def update_user_settings():
    try:
        data = request.json
        tab_user_id = data.get('tab_user_id')
        
        with get_db_connection() as conn:
            # Najprej resetiramo vse obstoječe tab uporabnike
            conn.execute("UPDATE Users SET is_tab_user = 0")
            
            # Če je bil podan ID, nastavimo novega tab uporabnika
            if tab_user_id:
                conn.execute("UPDATE Users SET is_tab_user = 1 WHERE id = ?", (tab_user_id,))
            
            conn.commit()
        
        # Invalidate cache for all users to ensure changes take effect immediately
        invalidate_user_cache()
        
        return jsonify({"message": "Nastavitve uporabnikov uspešno posodobljene"})
    except Exception as e:
        logger.error(f"Napaka pri posodabljanju uporabniških nastavitev: {e}")
        return jsonify({"error": str(e)}), 500

# API za pridobivanje podcastov določenega uporabnika
@app.route('/api/users/<int:user_id>/podcasts', methods=['GET'])
def get_user_podcasts(user_id):
    try:
        # Najprej preverimo, ali uporabnik obstaja
        with get_db_connection() as conn:
            user = conn.execute("SELECT * FROM Users WHERE id = ?", (user_id,)).fetchone()
            
            if not user:
                return jsonify({"error": "Uporabnik ne obstaja"}), 404
            
            # Pridobi trenutnega uporabnika (tistega, ki je prijavljen)
            current_username = get_current_user()
            current_user = get_user_from_db(current_username)
            
            if not current_user:
                return jsonify({"error": "Napaka pri preverjanju trenutnega uporabnika."}), 500
            
            # Različni primeri za različne tipe uporabnikov
            is_current_admin = current_user['is_admin'] == 1
            is_current_tab_user = current_user['is_tab_user'] == 1
            is_user_admin = user['is_admin'] == 1
            is_self_view = current_user['id'] == user_id
            
            logger.info(f"get_user_podcasts: current_user={current_user['username']}, is_admin={is_current_admin}, is_tab={is_current_tab_user}, viewing_user_id={user_id}, is_self={is_self_view}")
            
            # 1. Če gledamo admin uporabnika, vrnemo vse podcaste
            if is_user_admin:
                podcasts = conn.execute("""
                    SELECT p.*, u.display_name as user_display_name 
                    FROM Podcasts p
                    LEFT JOIN Users u ON p.user_id = u.id
                    ORDER BY p.naslov
                """).fetchall()
                logger.info(f"I am returning all podcasts for the admin user. {user_id}")
                
            # 2. Če je trenutni uporabnik admin ali gleda svoje podcaste
            elif is_current_admin or is_self_view:
                podcasts = conn.execute("""
                    SELECT p.*, u.display_name as user_display_name 
                    FROM Podcasts p
                    LEFT JOIN Users u ON p.user_id = u.id
                    WHERE p.user_id = ?
                    ORDER BY p.naslov
                """, (user_id,)).fetchall()
                logger.info(f"User {current_user['id']} is watching podcasts from user {user_id}")
                
            # 3. Če je trenutni uporabnik tab uporabnik
            elif is_current_tab_user:
                # Tab uporabnik lahko vidi vse podcaste izbranega uporabnika + javne podcaste
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
                
            # 4. Ostali primeri (običajni uporabniki gledajo druge uporabnike)
            else:
                # Prikaži samo javne podcaste tega uporabnika
                podcasts = conn.execute("""
                    SELECT p.*, u.display_name as user_display_name
                    FROM Podcasts p
                    LEFT JOIN Users u ON p.user_id = u.id
                    WHERE p.user_id = ? AND p.is_public = 1
                    ORDER BY p.naslov
               
                """, (user_id,)).fetchall()
                logger.info(f"User {current_user['id']} is watching public podcasts from user {user_id}")
            
            # Dodaten izpis za debugging
            logger.info(f"Found {len(podcasts)} podcasts")
        
        return jsonify({'podcasts': [dict(podcast) for podcast in podcasts]})
    except Exception as e:
        logger.error(f"Error retrieving user podcasts: {e}")
        return jsonify({"error": str(e)}), 500

# API za pridobivanje zadnjih epizod določenega uporabnika
@app.route('/api/users/<int:user_id>/latest_episodes', methods=['GET'])
def get_user_latest_episodes(user_id):
    limit = request.args.get('limit', 10, type=int)
    
    try:
        with get_db_connection() as conn:
            # Preverimo, ali uporabnik obstaja
            user = conn.execute("SELECT * FROM Users WHERE id = ?", (user_id,)).fetchone()
            
            if not user:
                return jsonify({"error": "Uporabnik ne obstaja"}), 404
            
            # Pridobi trenutnega uporabnika (tistega, ki je prijavljen)
            current_username = get_current_user()
            current_user = get_user_from_db(current_username)
            
            if not current_user:
                return jsonify({"error": "Napaka pri preverjanju trenutnega uporabnika."}), 500
            
            # Različni primeri za različne tipe uporabnikov
            is_current_admin = current_user['is_admin'] == 1
            is_current_tab_user = current_user['is_tab_user'] == 1
            is_user_admin = user['is_admin'] == 1
            is_self_view = current_user['id'] == user_id
            
            # Določimo, katere podcaste lahko uporabnik vidi
            if is_user_admin or is_current_admin or is_self_view or is_current_tab_user:
                # Lahko vidi vse podcaste uporabnika (z upoštevanjem skritih podcastov za trenutnega uporabnika)
                podcast_filter = "AND p.user_id = ?"
                if is_self_view or is_current_tab_user:
                    # Za lastne podcaste ali kot tab uporabnik upoštevamo skrite podcaste
                    podcast_filter += " AND (pvp.hidden IS NULL OR pvp.hidden = 0)"
                    params = (user_id, current_user['id'], user_id, limit)
                else:
                    # Kot admin gledamo vse podcaste uporabnika (brez filtriranja skritih)
                    params = (user_id, user_id, limit)
            else:
                # Lahko vidi samo javne podcaste uporabnika (z upoštevanjem skritih podcastov)
                podcast_filter = """
                    AND p.user_id = ? AND p.is_public = 1
                    AND (pvp.hidden IS NULL OR pvp.hidden = 0)
                """
                params = (user_id, current_user['id'], user_id, limit)
            
            # Za vsak podcast pridobi zadnjo neposlušano epizodo
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
            # Odstranimo pomožne stolpce
            for key in ['rn', 'uporabnik_poslušal']:
                if key in ep_dict:
                    del ep_dict[key]
            result.append(ep_dict)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Napaka pri pridobivanju zadnjih epizod uporabnika: {e}")
        return jsonify({"error": str(e)}), 500

# API za posodobitev vidnosti podcasta
@app.route('/api/podcasts/<int:podcast_id>/visibility', methods=['PATCH'])
def update_podcast_visibility(podcast_id):
    data = request.json
    is_public = data.get('is_public')

    if is_public is None:
        return jsonify({"error": "Manjka parameter 'is_public'."}), 400

    username = get_current_user()
    user = get_user_from_db(username)  # <- POPRAVLJENA VRSTICA

    if not user:
        return jsonify({"error": "Napaka pri preverjanju uporabnika."}), 500

    conn = get_db_connection()
    podcast = conn.execute("SELECT * FROM Podcasts WHERE id = ?", (podcast_id,)).fetchone()

    if not podcast:
        conn.close()
        return jsonify({"error": "Podcast ne obstaja."}), 404

    # Preveri, ali ima uporabnik pravico urejati podcast
    if podcast['user_id'] != user['id'] and not user['is_admin']:
        conn.close()
        return jsonify({"error": "Nimate dovoljenja za urejanje tega podcasta."}), 403

    conn.execute("UPDATE Podcasts SET is_public = ? WHERE id = ?", (is_public, podcast_id))
    conn.commit()
    conn.close()

    return jsonify({"message": "Vidnost podcasta uspešno posodobljena."}), 200

# API za skrivanje podcasta za trenutnega uporabnika
@app.route('/api/podcasts/<int:podcast_id>/hide', methods=['POST'])
def hide_podcast(podcast_id):
    username = get_current_user()
    user = get_user_from_db(username)

    if not user:
        return jsonify({"error": "Uporabnik ni registriran v sistemu."}), 401

    conn = get_db_connection()
    
    # Preveri, ali podcast obstaja
    podcast = conn.execute("SELECT * FROM Podcasts WHERE id = ?", (podcast_id,)).fetchone()
    if not podcast:
        conn.close()
        return jsonify({"error": "Podcast ne obstaja."}), 404
    
        
    # Preveri, ali že obstaja zapis za vidnost
    visibility = conn.execute("""
        SELECT * FROM PodcastVisibilityPreferences 
        WHERE podcast_id = ? AND user_id = ?
    """, (podcast_id, user['id'])).fetchone()
    
    if visibility:
        # Posodobi obstoječi zapis
        conn.execute("""
            UPDATE PodcastVisibilityPreferences
            SET hidden = 1
            WHERE podcast_id = ? AND user_id = ?
        """, (podcast_id, user['id']))
    else:
        # Ustvari nov zapis
        conn.execute("""
            INSERT INTO PodcastVisibilityPreferences (podcast_id, user_id, hidden)
            VALUES (?, ?, 1)
        """, (podcast_id, user['id']))
    
    conn.commit()
    conn.close()
    
    logger.info(f"User {user['username']} hid the podcast {podcast_id}")
    return jsonify({"message": "Podcast successfully hidden."}), 200

# API za prikazovanje podcasta za trenutnega uporabnika
@app.route('/api/podcasts/<int:podcast_id>/show', methods=['POST'])
def show_podcast(podcast_id):
    username = get_current_user()
    user = get_user_from_db(username)

    if not user:
        return jsonify({"error": "Uporabnik ni registriran v sistemu."}), 401

    conn = get_db_connection()
    
    # Preveri, ali podcast obstaja
    podcast = conn.execute("SELECT * FROM Podcasts WHERE id = ?", (podcast_id,)).fetchone()
    if not podcast:
        conn.close()
        return jsonify({"error": "Podcast ne obstaja."}), 404
    
    # Izbriši ali posodobi zapis za vidnost
    conn.execute("""
        DELETE FROM PodcastVisibilityPreferences
        WHERE podcast_id = ? AND user_id = ?
    """, (podcast_id, user['id']))
    
    conn.commit()
    conn.close()
    
    logger.info(f"User {user['username']} showed a podcast {podcast_id}")
    return jsonify({"message": "Podcast successfully displayed."}), 200

# API za pridobivanje skritih podcastov za trenutnega uporabnika
@app.route('/api/podcasts/hidden', methods=['GET'])
def get_hidden_podcasts():
    username = get_current_user()
    user = get_user_from_db(username)

    if not user:
        return jsonify({"error": "Uporabnik ni registriran v sistemu."}), 401

    conn = get_db_connection()
    
    # Pridobi vse skrite podcaste
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

# dodamo endpoint za upravljanje admin statusa
@app.route('/api/users/admin_status', methods=['POST'])
def update_user_admin_status():
    try:
        data = request.json
        user_id = data.get('user_id')
        is_admin = data.get('is_admin', 0)

        if not user_id:
            return jsonify({"error": "Manjka user_id"}), 400

        # Preveri ali trenutni uporabnik obstaja in je admin
        current_username = get_current_user()
        current_user = get_user_from_db(current_username)
        
        if not current_user or not current_user['is_admin']:
            return jsonify({"error": "Nimate pravic za spreminjanje admin statusa."}), 403

        with get_db_connection() as conn:
            # Preverimo ali uporabnik obstaja
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