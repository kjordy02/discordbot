from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from config import DB_CONFIG

class Database:
    def __init__(self):
        self.db_name = "botdata"
        self.db_user = "discordbot"
        self.db_password = os.getenv("DB_PASSWORD")
        self.db_host = "localhost"

    def get_connection(self):
        return psycopg2.connect(
            **DB_CONFIG
        )


    def setup_tables(self):
        """Create the necessary tables in the database if they don't exist."""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    discord_id BIGINT UNIQUE NOT NULL
                );""")
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS servers (
                    id SERIAL PRIMARY KEY,
                    server_id BIGINT UNIQUE NOT NULL
                );""")
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS game_sessions (
                    id SERIAL PRIMARY KEY,
                    server_id INTEGER REFERENCES servers(id),
                    game_name TEXT NOT NULL,              -- 'busdriver_main', 'busdriver_endgame', 'horserace'
                    played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );""")
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS busdriver_main_stats (
                    id SERIAL PRIMARY KEY,
                    session_id INTEGER REFERENCES game_sessions(id),
                    user_id INTEGER REFERENCES users(id),
                    sips_given INTEGER DEFAULT 0,
                    sips_drunk INTEGER DEFAULT 0
                );""")
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS busdriver_endgame_stats (
                    id SERIAL PRIMARY KEY,
                    session_id INTEGER REFERENCES game_sessions(id),
                    user_id INTEGER REFERENCES users(id),
                    sips_drunk INTEGER DEFAULT 0,
                    tries INTEGER DEFAULT 0
                );""")
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS horserace_stats (
                    id SERIAL PRIMARY KEY,
                    session_id INTEGER REFERENCES game_sessions(id),
                    user_id INTEGER REFERENCES users(id),
                    sips_given INTEGER DEFAULT 0,
                    sips_drunk INTEGER DEFAULT 0
                );""")
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS color_effects (
                    id SERIAL PRIMARY KEY,
                    server_id INTEGER REFERENCES servers(id) ON DELETE CASCADE,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE (server_id, user_id)
                );""")


    def get_or_create_user(self, discord_id):
        """Get or create a user in the database."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT id FROM users WHERE discord_id = %s", (discord_id,))
                user = cursor.fetchone()
                if user:
                    return user['id']
                cursor.execute("INSERT INTO users (discord_id) VALUES (%s) RETURNING id", (discord_id,))
                return cursor.fetchone()['id']

    def get_or_create_server(self, server_id):
        """Get or create a server in the database."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT id FROM servers WHERE server_id = %s", (server_id,))
                server = cursor.fetchone()
                if server:
                    return server['id']
                cursor.execute("INSERT INTO servers (server_id) VALUES (%s) RETURNING id", (server_id,))
                return cursor.fetchone()['id']
    
    def create_game_session(self, server_id, game_name):
        """Create a new game session in the database."""
        server_pk = self.get_or_create_server(server_id)
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    INSERT INTO game_sessions (server_id, game_name)
                    VALUES (%s, %s)
                    RETURNING id;
                """, (server_pk, game_name))
                return cursor.fetchone()['id']
    
    def add_busdriver_main_stat(self, discord_id, server_id, session_id, sips_given, sips_drunk):
        """Add a bus driver main stat to the database."""
        user_pk = self.get_or_create_user(discord_id)
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO busdriver_main_stats (session_id, user_id, sips_given, sips_drunk)
                    VALUES (%s, %s, %s, %s);
                """, (session_id, user_pk, sips_given, sips_drunk))
    
    def add_busdriver_endgame_stat(self, discord_id, server_id, session_id, sips_drunk, tries):
        """Add a bus driver endgame stat to the database."""
        user_pk = self.get_or_create_user(discord_id)
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO busdriver_endgame_stats (session_id, user_id, sips_drunk, tries)
                    VALUES (%s, %s, %s, %s);
                """, (session_id, user_pk, sips_drunk, tries))
    
    def add_horserace_stat(self, discord_id, server_id, session_id, sips_given, sips_drunk):
        """Add a horserace stat to the database."""
        user_pk = self.get_or_create_user(discord_id)
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO horserace_stats (session_id, user_id, sips_given, sips_drunk)
                    VALUES (%s, %s, %s, %s);
                """, (session_id, user_pk, sips_given, sips_drunk))
    
    def get_busdriver_main_ranking(self, metric="sips_drunk", scope="global", server_id=None, today=False, limit=3):
        assert metric in ["sips_drunk", "sips_given"], "Invalid metric"

        filters = []
        params = []

        if scope == "server":
            filters.append("s.server_id = %s")
            params.append(server_id)
        if today:
            from datetime import datetime, timedelta, time
            now = datetime.now()
            midday = datetime.combine(now.date(), time(12))
            cutoff = midday if now >= midday else midday - timedelta(days=1)
            filters.append("gs.played_at >= %s")
            params.append(cutoff)

        where = "WHERE " + " AND ".join(filters) if filters else ""

        query = f"""
            SELECT u.discord_id, SUM(bms.{metric}) AS value
            FROM busdriver_main_stats bms
            JOIN users u ON u.id = bms.user_id
            JOIN game_sessions gs ON gs.id = bms.session_id
            JOIN servers s ON s.id = gs.server_id
            {where}
            GROUP BY u.discord_id
            ORDER BY value DESC
            LIMIT %s;
        """
        params.append(limit)

        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                return [(row["discord_id"], row["value"]) for row in cursor.fetchall()]
            
    def get_busdriver_endgame_ranking(self, sort_by="sips", scope="global", server_id=None, today=False, limit=3):
        assert sort_by in ["sips", "tries"], "Invalid sort column"

        filters = []
        params = []

        if scope == "server":
            filters.append("s.server_id = %s")
            params.append(server_id)
        if today:
            from datetime import datetime, timedelta, time
            now = datetime.now()
            midday = datetime.combine(now.date(), time(12))
            cutoff = midday if now >= midday else midday - timedelta(days=1)
            filters.append("gs.played_at >= %s")
            params.append(cutoff)

        where = "WHERE " + " AND ".join(filters) if filters else ""

        query = f"""
            SELECT u.discord_id, SUM(bes.sips_drunk) AS sips, SUM(bes.tries) AS tries
            FROM busdriver_endgame_stats bes
            JOIN users u ON u.id = bes.user_id
            JOIN game_sessions gs ON gs.id = bes.session_id
            JOIN servers s ON s.id = gs.server_id
            {where}
            GROUP BY u.discord_id
            ORDER BY {sort_by} DESC
            LIMIT %s;
        """
        params.append(limit)

        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                return [(row["discord_id"], row["sips"], row["tries"]) for row in cursor.fetchall()]

    def insert_horserace_stat(self, session_id, user_id, sips_drunk=0, sips_given=0):
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO horserace_stats (session_id, user_id, sips_drunk, sips_given)
                    VALUES (%s, %s, %s, %s)
                """, (session_id, user_id, sips_drunk, sips_given))

    def update_horserace_given(self, session_id, user_id, sips):
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE horserace_stats
                    SET sips_given = sips_given + %s
                    WHERE session_id = %s AND user_id = %s
                """, (sips, session_id, user_id))

    def get_horserace_main_ranking(self, metric="sips_drunk", scope="global", server_id=None, today=False, limit=3):
        assert metric in ["sips_drunk", "sips_given"]

        filters = []
        params = []

        if scope == "server" and server_id:
            filters.append("s.server_id = %s")
            params.append(server_id)

        if today:
            from datetime import datetime, timedelta, time
            now = datetime.now()
            midday = datetime.combine(now.date(), time(12))
            cutoff = midday if now >= midday else midday - timedelta(days=1)
            filters.append("gs.played_at >= %s")
            params.append(cutoff)

        where_clause = "WHERE " + " AND ".join(filters) if filters else ""

        query = f"""
            SELECT u.discord_id, SUM(hs.{metric}) AS value
            FROM horserace_stats hs
            JOIN users u ON u.id = hs.user_id
            JOIN game_sessions gs ON gs.id = hs.session_id
            JOIN servers s ON s.id = gs.server_id
            {where_clause}
            GROUP BY u.discord_id
            ORDER BY value DESC
            LIMIT %s;
        """
        params.append(limit)

        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                return [(row["discord_id"], row["value"]) for row in cursor.fetchall()]

    # COLOR SYSTEM
    def add_color_effect(self, server_id, user_id):
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO color_effects (server_id, user_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING;
                """, (server_id, user_id))

    def remove_color_effect(self, server_id, user_id):
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM color_effects
                    WHERE server_id = %s AND user_id = %s;
                """, (server_id, user_id))

    def has_color_effect(self, server_id, user_id):
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT 1 FROM color_effects
                    WHERE server_id = %s AND user_id = %s;
                """, (server_id, user_id))
                return cursor.fetchone() is not None

    def get_color_effect_users(self, server_id):
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT u.discord_id FROM color_effects ce
                    JOIN users u ON u.id = ce.user_id
                    WHERE ce.server_id = %s;
                """, (server_id,))
                return [int(row["discord_id"]) for row in cursor.fetchall()]
