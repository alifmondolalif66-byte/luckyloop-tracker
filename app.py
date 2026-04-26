from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import sqlite3
from datetime import datetime
import os

app = Flask(__name__)
CORS(app)  # Chrome Extension থেকে request allow করবে

DB = os.path.join(os.environ.get("DB_PATH", "."), "jobs.db")

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            job_name   TEXT    UNIQUE NOT NULL,
            position   TEXT,
            available  TEXT,
            link       TEXT,
            updated_at TEXT
        )
    """)
    cols = [row[1] for row in c.execute("PRAGMA table_info(jobs)")]
    if "updated_at" not in cols:
        c.execute("ALTER TABLE jobs ADD COLUMN updated_at TEXT")
    conn.commit()
    conn.close()
    print("[DB] Ready")

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/latest")
def latest():
    return render_template("latest.html")

@app.route("/api/latest")
def api_latest():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM jobs ORDER BY updated_at DESC"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/save", methods=["POST", "OPTIONS"])
def save_job():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "No JSON body received"}), 400

    job_name  = str(data.get("job_name",  "") or "").strip()
    position  = str(data.get("position",  "") or "").strip()
    available = str(data.get("available", "") or "").strip()
    link      = str(data.get("link",      "") or "").strip()
    now       = datetime.now().isoformat()

    if not job_name:
        return jsonify({"status": "error", "message": "job_name is required"}), 400

    conn = get_db()
    conn.execute("""
        INSERT INTO jobs (job_name, position, available, link, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(job_name) DO UPDATE SET
            position   = excluded.position,
            available  = excluded.available,
            link       = excluded.link,
            updated_at = excluded.updated_at
    """, (job_name, position, available, link, now))
    conn.commit()
    conn.close()

    print(f"[SAVED] {job_name}  |  pos={position}  |  avail={available}  |  {now}")
    return jsonify({"status": "saved", "job_name": job_name})

init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
