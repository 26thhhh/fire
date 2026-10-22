# SAFD Fire + EMS Watch

Terminal viewer and collector for San Antonio Fire Department public active incidents. ZIP configuration establishes the shared local profile for the app suite; this public source remains San Antonio-specific.

Run `python3 fire_ui.py`. The first interactive launch asks for a five-digit United States ZIP code. Change it later with `python3 fire_ui.py --set-zip [ZIP_CODE]`.

Run `python3 collect.py` to fetch public incidents. This project uses only the Python standard library.

Generated SQLite history, logs, and local location settings are excluded from source control.
