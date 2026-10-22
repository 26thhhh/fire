#!/usr/bin/env python3
import hashlib
import json
import sqlite3
import time
import urllib.parse
import urllib.request
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
import sys

from location import ensure_location, handle_location_command

DATA_DIR = Path.home() / ".local/share/kanslor-fire"
DATABASE_PATH = DATA_DIR / "history.sqlite3"
SOURCES = {
    "FIRE": "https://webapp3.sanantonio.gov/activefire/Fire.aspx",
    "EMS": "https://webapp3.sanantonio.gov/activefire/EMS.aspx",
}


class IncidentTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_table = self.in_row = self.in_cell = False
        self.cells, self.rows, self.parts = [], [], []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "table" and attributes.get("id") == "GridView2":
            self.in_table = True
        elif self.in_table and tag == "tr":
            self.in_row, self.cells = True, []
        elif self.in_row and tag == "td":
            self.in_cell, self.parts = True, []

    def handle_data(self, data):
        if self.in_cell:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self.in_cell:
            self.cells.append(" ".join("".join(self.parts).split()))
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if len(self.cells) == 8:
                self.rows.append(self.cells)
            self.in_row = False
        elif tag == "table" and self.in_table:
            self.in_table = False


def initialize_database(connection):
    connection.execute("""
        CREATE TABLE IF NOT EXISTS incidents (
            incident_id TEXT PRIMARY KEY, kind TEXT NOT NULL, response_at TEXT NOT NULL,
            problem_type TEXT, address TEXT, cross_street TEXT, location_type TEXT,
            postal_code TEXT, tac TEXT, units TEXT, first_seen INTEGER NOT NULL,
            last_seen INTEGER NOT NULL
        )
    """)
    connection.execute("CREATE INDEX IF NOT EXISTS incidents_last_seen ON incidents(last_seen DESC)")
    connection.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.execute("""
        CREATE TABLE IF NOT EXISTS geocodes (
            address TEXT NOT NULL, postal_code TEXT NOT NULL, latitude REAL, longitude REAL,
            fetched_at INTEGER NOT NULL, PRIMARY KEY(address, postal_code)
        )
    """)


def fetch_rows(url):
    request = urllib.request.Request(url, headers={"User-Agent": "kanslor-fire-watch/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        page = response.read().decode("utf-8", errors="replace")
    parser = IncidentTableParser()
    parser.feed(page)
    return parser.rows


def geocode(connection, address, postal_code):
    cached = connection.execute("SELECT latitude, longitude FROM geocodes WHERE address = ? AND postal_code = ?", (address, postal_code)).fetchone()
    if cached:
        return cached
    query = urllib.parse.urlencode({"q": f"{address}, San Antonio, TX {postal_code}", "format": "json", "limit": 1})
    request = urllib.request.Request(f"https://nominatim.openstreetmap.org/search?{query}", headers={"User-Agent": "kanslor-vigilante/1.0 (personal homelab)"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.load(response)
        latitude, longitude = (float(result[0]["lat"]), float(result[0]["lon"])) if result else (None, None)
    except (OSError, KeyError, IndexError, ValueError, json.JSONDecodeError):
        latitude = longitude = None
    connection.execute("INSERT INTO geocodes VALUES (?, ?, ?, ?, ?) ON CONFLICT(address, postal_code) DO UPDATE SET latitude = excluded.latitude, longitude = excluded.longitude, fetched_at = excluded.fetched_at", (address, postal_code, latitude, longitude, int(time.time())))
    return latitude, longitude


def main():
    if handle_location_command(sys.argv[1:]):
        return
    ensure_location(interactive=sys.stdin.isatty())
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    now = int(time.time())
    with sqlite3.connect(DATABASE_PATH) as connection:
        initialize_database(connection)
        pending_geocodes = []
        for kind, url in SOURCES.items():
            for units, response_at, problem_type, address, cross_street, location_type, postal_code, tac in fetch_rows(url):
                try:
                    response_time = datetime.strptime(response_at, "%m/%d/%Y %I:%M:%S %p")
                except ValueError:
                    continue
                # The public page occasionally retains years-old test records.
                if abs((datetime.now() - response_time).total_seconds()) > 86400:
                    continue
                incident_id = hashlib.sha256("\x1f".join((kind, response_at, problem_type, address)).encode()).hexdigest()
                connection.execute("""
                    INSERT INTO incidents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(incident_id) DO UPDATE SET
                        units = excluded.units, cross_street = excluded.cross_street,
                        location_type = excluded.location_type, tac = excluded.tac,
                        last_seen = excluded.last_seen
                """, (incident_id, kind, response_at, problem_type, address, cross_street,
                      location_type, postal_code, tac, units, now, now))
                if address and postal_code:
                    pending_geocodes.append((address, postal_code))
        # Nominatim requests are deliberately limited to respect its public-service rate policy.
        for address, postal_code in dict.fromkeys(pending_geocodes):
            if connection.execute("SELECT 1 FROM geocodes WHERE address = ? AND postal_code = ?", (address, postal_code)).fetchone():
                continue
            geocode(connection, address, postal_code)
            time.sleep(1)
        connection.execute("INSERT INTO metadata VALUES ('last_success', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (str(now),))
    (DATA_DIR / "last_success").write_text(str(now), encoding="utf-8")


if __name__ == "__main__":
    main()
