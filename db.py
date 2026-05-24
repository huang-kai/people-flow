import sqlite3
import os
import yaml

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    _cfg = yaml.safe_load(f)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), _cfg["database"]["path"])


def _init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        '''CREATE TABLE IF NOT EXISTS people_count
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         direction TEXT,
         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)'''
    )
    conn.commit()
    conn.close()


def record_direction(direction):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO people_count (direction) VALUES (?)", (direction,))
    conn.commit()
    conn.close()


_init_db()
