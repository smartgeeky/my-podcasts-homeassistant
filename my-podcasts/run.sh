#!/usr/bin/env bash

echo "Starting My Podcasts add-on..."

DB_PATH="/data/mypodcasts.db"

if [ ! -f "$DB_PATH" ]; then
    echo "Creating new SQLite database at $DB_PATH..."
    sqlite3 "$DB_PATH" <<EOF
CREATE TABLE IF NOT EXISTS Podcasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    naslov TEXT NOT NULL,
    rss_url TEXT NOT NULL,
    datum_naročnine TEXT NOT NULL,
    image_url TEXT,
    description TEXT,
    user_id INTEGER,
    is_public INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS Episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    podcast_id INTEGER NOT NULL,
    naslov TEXT NOT NULL,
    datum_izdaje TEXT NOT NULL,
    url TEXT NOT NULL,
    izbrisano INTEGER NOT NULL DEFAULT 0,
    opis TEXT,
    FOREIGN KEY (podcast_id) REFERENCES Podcasts (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS Settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    avtomatsko INTEGER NOT NULL DEFAULT 1,
    interval INTEGER NOT NULL DEFAULT 24,
    cas_posodobitve TEXT DEFAULT '03:00',
    zadnja_posodobitev TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS SelectedPlayers (
    entity_id TEXT PRIMARY KEY,
    display_name TEXT
);

CREATE TABLE IF NOT EXISTS Users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    is_tab_user INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS EpisodeListenStatus (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    poslušano INTEGER NOT NULL DEFAULT 0,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (episode_id) REFERENCES Episodes (id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES Users (id) ON DELETE CASCADE,
    UNIQUE(episode_id, user_id)
);

CREATE TABLE IF NOT EXISTS PodcastVisibilityPreferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    podcast_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    hidden INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (podcast_id) REFERENCES Podcasts (id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES Users (id) ON DELETE CASCADE,
    UNIQUE(podcast_id, user_id)
);

CREATE TABLE IF NOT EXISTS EpisodePlaybackPosition (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (episode_id) REFERENCES Episodes (id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES Users (id) ON DELETE CASCADE,
    UNIQUE(episode_id, user_id)
);

-- Vstavi privzete nastavitve, če še ne obstajajo
INSERT OR IGNORE INTO Settings (id, avtomatsko, interval, cas_posodobitve, zadnja_posodobitev)
VALUES (1, 1, 24, '03:00', datetime('now'));
EOF
    echo "Database structure created."
else
    echo "Database already exists, checking for structure updates..."
    
    # 1. Preveri, ali stolpec 'is_public' že obstaja v tabeli Podcasts
    HAS_IS_PUBLIC=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM pragma_table_info('Podcasts') WHERE name='is_public';")

    # Če stolpec ne obstaja, ga dodamo
    if [ "$HAS_IS_PUBLIC" -eq "0" ]; then
        echo "Adding column 'is_public' to Podcasts table..."
        sqlite3 "$DB_PATH" "ALTER TABLE Podcasts ADD COLUMN is_public INTEGER DEFAULT 0;"

        # Nastavi vse obstoječe podcaste od admin uporabnikov kot javne
        sqlite3 "$DB_PATH" "UPDATE Podcasts SET is_public = 1 WHERE user_id IN (SELECT id FROM Users WHERE is_admin = 1);"
        echo "Set all podcasts of admin users as public."
    else
        echo "Column 'is_public' already exists in Podcasts table."
    fi
    
    # Ostale posodobitve baze iz prejšnje verzije
    
    # Preveri, ali stolpec 'opis' že obstaja v tabeli Episodes
    HAS_OPIS=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM pragma_table_info('Episodes') WHERE name='opis';")
    
    # Če stolpec ne obstaja, ga dodamo
    if [ "$HAS_OPIS" -eq "0" ]; then
        echo "Adding column 'opis' to Episodes table..."
        sqlite3 "$DB_PATH" "ALTER TABLE Episodes ADD COLUMN opis TEXT DEFAULT NULL;"
    else
        echo "Column 'opis' already exists in Episodes table."
    fi
    
    # Preveri, ali stolpec 'description' obstaja v tabeli Podcasts
    HAS_DESCRIPTION=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM pragma_table_info('Podcasts') WHERE name='description';")
    
    # Če stolpec ne obstaja, ga dodamo
    if [ "$HAS_DESCRIPTION" -eq "0" ]; then
        echo "Adding column 'description' to Podcasts table..."
        sqlite3 "$DB_PATH" "ALTER TABLE Podcasts ADD COLUMN description TEXT DEFAULT NULL;"
    else
        echo "Column 'description' already exists in Podcasts table."
    fi
    
    # Preveri, ali tabela Settings obstaja
    HAS_SETTINGS=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='Settings';")
    
    # Obravnavamo tabelo Settings
    if [ "$HAS_SETTINGS" -eq "1" ]; then
        # Preveri, ali ima tabela Settings ustrezne stolpce
        HAS_CAS=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM pragma_table_info('Settings') WHERE name='cas_posodobitve';")
        HAS_ZADNJA=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM pragma_table_info('Settings') WHERE name='zadnja_posodobitev';")
        
        if [ "$HAS_CAS" -eq "0" ] || [ "$HAS_ZADNJA" -eq "0" ]; then
            echo "Updating Settings table with new columns..."
            
            sqlite3 "$DB_PATH" <<EOF
PRAGMA foreign_keys=off;
BEGIN TRANSACTION;

-- Varno ustvarimo začasno tabelo
CREATE TABLE Settings_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    avtomatsko INTEGER NOT NULL DEFAULT 1,
    interval INTEGER NOT NULL DEFAULT 24,
    cas_posodobitve TEXT DEFAULT '03:00',
    zadnja_posodobitev TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Kopiramo obstoječe podatke
INSERT INTO Settings_new(id, avtomatsko, interval)
SELECT id, avtomatsko, interval FROM Settings;

-- Varno izmenjamo tabeli
DROP TABLE Settings;
ALTER TABLE Settings_new RENAME TO Settings;

COMMIT;
PRAGMA foreign_keys=on;
EOF
        else
            echo "Settings table already has all required columns."
        fi
    else
        echo "Creating Settings table..."
        sqlite3 "$DB_PATH" <<EOF
CREATE TABLE IF NOT EXISTS Settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    avtomatsko INTEGER NOT NULL DEFAULT 1,
    interval INTEGER NOT NULL DEFAULT 24,
    cas_posodobitve TEXT DEFAULT '03:00',
    zadnja_posodobitev TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS SelectedPlayers (
    entity_id TEXT PRIMARY KEY,
    display_name TEXT
);

-- Vstavi privzete nastavitve, če še ne obstajajo
INSERT OR IGNORE INTO Settings (id, avtomatsko, interval, cas_posodobitve, zadnja_posodobitev)
VALUES (1, 1, 24, '03:00', datetime('now'));
EOF
    fi

    # Preveri, ali tabela SelectedPlayers obstaja
    HAS_SELECTED_PLAYERS=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='SelectedPlayers';")
    if [ "$HAS_SELECTED_PLAYERS" -eq "0" ]; then
        echo "Creating SelectedPlayers table..."
        sqlite3 "$DB_PATH" "CREATE TABLE IF NOT EXISTS SelectedPlayers (entity_id TEXT PRIMARY KEY, display_name TEXT);"
    fi

    # Preveri, ali tabela Users obstaja
    HAS_USERS=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='Users';")
    if [ "$HAS_USERS" -eq "0" ]; then
        echo "Creating Users table..."
        sqlite3 "$DB_PATH" "CREATE TABLE IF NOT EXISTS Users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            is_tab_user INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );"
    fi

    # Preveri, ali tabela PodcastVisibilityPreferences obstaja
    HAS_VISIBILITY_PREFS=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='PodcastVisibilityPreferences';")
    if [ "$HAS_VISIBILITY_PREFS" -eq "0" ]; then
        echo "Creating PodcastVisibilityPreferences table..."
        sqlite3 "$DB_PATH" "CREATE TABLE IF NOT EXISTS PodcastVisibilityPreferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            podcast_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            hidden INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (podcast_id) REFERENCES Podcasts (id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES Users (id) ON DELETE CASCADE,
            UNIQUE(podcast_id, user_id)
        );"
        echo "PodcastVisibilityPreferences table created successfully."
    fi

    # Preveri, ali tabela EpisodeListenStatus obstaja
    HAS_EPISODE_LISTEN=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='EpisodeListenStatus';")
    if [ "$HAS_EPISODE_LISTEN" -eq "0" ]; then
        echo "Creating EpisodeListenStatus table..."
        sqlite3 "$DB_PATH" "CREATE TABLE IF NOT EXISTS EpisodeListenStatus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            episode_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            poslušano INTEGER NOT NULL DEFAULT 0,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (episode_id) REFERENCES Episodes (id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES Users (id) ON DELETE CASCADE,
            UNIQUE(episode_id, user_id)
        );"
    fi

    # Preveri, ali tabela EpisodePlaybackPosition obstaja
    HAS_EPISODE_POSITION=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='EpisodePlaybackPosition';")
    if [ "$HAS_EPISODE_POSITION" -eq "0" ]; then
        echo "Creating EpisodePlaybackPosition table..."
        sqlite3 "$DB_PATH" "CREATE TABLE IF NOT EXISTS EpisodePlaybackPosition (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            episode_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (episode_id) REFERENCES Episodes (id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES Users (id) ON DELETE CASCADE,
            UNIQUE(episode_id, user_id)
        );"
        echo "EpisodePlaybackPosition table created successfully."
    fi

    # Preveri, ali obstaja stolpec user_id v tabeli Podcasts
    HAS_USER_ID=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM pragma_table_info('Podcasts') WHERE name='user_id';")
    if [ "$HAS_USER_ID" -eq "0" ]; then
        echo "Adding column user_id to Podcasts table..."
        sqlite3 "$DB_PATH" "ALTER TABLE Podcasts ADD COLUMN user_id INTEGER;"
    fi

    echo "Database structure updated."
fi

# Aktiviraj virtualno okolje
source /app/venv/bin/activate

# Launch with Gunicorn instead of Flask
echo "Starting Gunicorn server..."
gunicorn --bind 0.0.0.0:8099 --worker-class gthread --threads 4 main:app