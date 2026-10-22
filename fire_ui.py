#!/usr/bin/env python3
import curses
import sqlite3
import time
import sys
from datetime import datetime
from pathlib import Path

from location import ensure_location, handle_location_command

DATABASE_PATH = Path.home() / ".local/share/kanslor-fire/history.sqlite3"


def draw_line(screen, row, text, selected=False, color=0):
    height, width = screen.getmaxyx()
    if row < height:
        try:
            screen.addnstr(row, 0, text.ljust(max(width - 1, 1)), max(width - 1, 1), curses.A_REVERSE if selected else color)
        except curses.error:
            pass


def incidents(connection, mode, kind_filter):
    clauses, params = [], []
    if mode == "ACTIVE":
        clauses.append("last_seen >= ?")
        params.append(int(time.time()) - 180)
    if kind_filter:
        clauses.append("kind = ?")
        params.append(kind_filter)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return connection.execute(f"SELECT incident_id, kind, response_at, problem_type, address, cross_street, location_type, postal_code, tac, units, first_seen, last_seen FROM incidents {where} ORDER BY response_at DESC", params).fetchall()


def detail_view(screen, incident):
    labels = (("TYPE", incident[1]), ("RESPONSE", incident[2]), ("PROBLEM", incident[3] or "--"),
              ("ADDRESS", incident[4] or "--"), ("CROSS STREET", incident[5] or "--"),
              ("LOCATION", incident[6] or "--"), ("ZIP", incident[7] or "--"),
              ("TAC", incident[8] or "--"), ("UNITS", incident[9] or "--"),
              ("FIRST OBSERVED", datetime.fromtimestamp(incident[10]).strftime("%Y-%m-%d %H:%M:%S")),
              ("LAST OBSERVED", datetime.fromtimestamp(incident[11]).strftime("%Y-%m-%d %H:%M:%S")))
    while True:
        screen.erase()
        draw_line(screen, 0, "S A F D  //  PUBLIC INCIDENT DETAIL", color=curses.color_pair(1))
        draw_line(screen, 1, "ESC return to incident list")
        for row, (label, value) in enumerate(labels, 3):
            draw_line(screen, row, f"{label:<16} {value}")
        draw_line(screen, 16, "SOURCE: City of San Antonio Active SAFD Calls. Data is public and may be delayed.", color=curses.color_pair(2))
        screen.refresh()
        if screen.getch() in (27, ord("q"), ord("Q")):
            return


def app(screen):
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_RED, -1)
    curses.init_pair(2, curses.COLOR_CYAN, -1)
    selected, mode, kind_filter = 0, "ACTIVE", None
    while True:
        screen.erase()
        if not DATABASE_PATH.exists():
            draw_line(screen, 0, "S A F D  //  FIRE + EMS WATCH", color=curses.color_pair(1))
            draw_line(screen, 2, "No local history yet. The collector runs once per minute.")
            draw_line(screen, 4, "ESC exit")
            screen.refresh()
            if screen.getch() == 27:
                return
            continue
        with sqlite3.connect(DATABASE_PATH) as connection:
            rows = incidents(connection, mode, kind_filter)
            last_success = connection.execute("SELECT value FROM metadata WHERE key = 'last_success'").fetchone()
            updated = datetime.fromtimestamp(int(last_success[0])).strftime("%H:%M:%S") if last_success else "unavailable"
            label = kind_filter or "FIRE + EMS"
            draw_line(screen, 0, f"S A F D  //  FIRE + EMS WATCH   [{mode} | {label}]", color=curses.color_pair(1))
            draw_line(screen, 1, "UP/DOWN select  ENTER detail  A active  H history  F fire  M EMS  C clear  ESC exit")
            draw_line(screen, 2, f"LAST POLL: {updated}   Source refreshes approximately every 40 seconds.", color=curses.color_pair(2))
            draw_line(screen, 4, "TYPE  RESPONSE          PROBLEM                  ADDRESS                 ZIP    TAC  UNITS", color=curses.color_pair(2))
            height, _ = screen.getmaxyx()
            visible, start = max(height - 6, 1), max(0, selected - max(height - 6, 1) + 1)
            for index, incident in enumerate(rows[start:start + visible], start):
                text = f"{incident[1]:<5} {incident[2]:<17} {(incident[3] or '--'):<24.24} {(incident[4] or '--'):<23.23} {(incident[7] or '--'):<6.6} {(incident[8] or '--'):<4.4} {incident[9] or '--'}"
                draw_line(screen, index - start + 5, text, index == selected)
            if not rows:
                draw_line(screen, 6, "No incidents match this view.")
            screen.refresh()
            key = screen.getch()
            if key in (27, ord("q"), ord("Q")):
                return
            if key in (curses.KEY_DOWN, ord("j")) and selected < len(rows) - 1:
                selected += 1
            elif key in (curses.KEY_UP, ord("k")) and selected > 0:
                selected -= 1
            elif key in (10, 13, curses.KEY_ENTER) and rows:
                detail_view(screen, rows[selected])
            elif key in (ord("a"), ord("A")):
                mode, selected = "ACTIVE", 0
            elif key in (ord("h"), ord("H")):
                mode, selected = "HISTORY", 0
            elif key in (ord("f"), ord("F")):
                kind_filter, selected = "FIRE", 0
            elif key in (ord("m"), ord("M")):
                kind_filter, selected = "EMS", 0
            elif key in (ord("c"), ord("C")):
                kind_filter, selected = None, 0


if __name__ == "__main__":
    if not handle_location_command(sys.argv[1:]):
        ensure_location(interactive=True)
        curses.wrapper(app)
