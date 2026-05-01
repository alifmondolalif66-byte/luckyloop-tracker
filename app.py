"""
LuckyLoop - Job Tracker & License Management System
v2.0 - HyperLoop License System Integration
"""

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import sqlite3
from datetime import datetime
import os
import secrets
import string

app = Flask(__name__)
CORS(app)

DB = os.path.join(os.environ.get("DB_PATH", "."), "luckyloop.db")

# ── Admin password (change this!) ──────────────────────────
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "luckyloop_admin_2024")

def generate_random_key(length=12):
    """Generate a random license key"""
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))

def init_db():
    """Initialize LuckyLoop Database"""
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    
    # ── JOBS TABLE ──────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS luckyloop_jobs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            job_name   TEXT    UNIQUE NOT NULL,
            position   TEXT,
            available  TEXT,
            link       TEXT,
            updated_at TEXT
        )
    """)
    
    # ── SCRAPER STATUS TABLE ────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS luckyloop_scraper_status (
            id         INTEGER PRIMARY KEY,
            status     TEXT,
            message    TEXT,
            updated_at TEXT
        )
    """)
    
    # ── DEVICES TABLE (Legacy) ──────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS luckyloop_devices (
            device_id    TEXT PRIMARY KEY,
            device_name  TEXT,
            license_key  TEXT,
            license_type TEXT,
            ip_address   TEXT,
            first_seen   TEXT,
            last_seen    TEXT,
            is_blocked   INTEGER DEFAULT 0,
            block_reason TEXT
        )
    """)
    
    # ── PENDING LICENSES TABLE (HyperLoop) ──────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS luckyloop_pending_licenses (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id           TEXT UNIQUE NOT NULL,
            device_name         TEXT,
            device_ip           TEXT,
            temp_license_key    TEXT UNIQUE NOT NULL,
            requested_at        TEXT,
            status              TEXT DEFAULT 'pending',
            rejection_reason    TEXT,
            updated_at          TEXT
        )
    """)
    
    # ── APPROVED LICENSES TABLE (HyperLoop) ──────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS luckyloop_approved_licenses (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id           TEXT UNIQUE NOT NULL,
            device_name         TEXT,
            device_ip           TEXT,
            temp_license_key    TEXT,
            permanent_license_key TEXT UNIQUE NOT NULL,
            approved_at         TEXT,
            approved_by         TEXT DEFAULT 'admin',
            is_blocked          INTEGER DEFAULT 0,
            block_reason        TEXT,
            blocked_at          TEXT,
            status              TEXT DEFAULT 'approved',
            last_heartbeat      TEXT
        )
    """)
    
    # ── Migrate old jobs table ──────────────────────────────
    try:
        c.execute("SELECT * FROM jobs LIMIT 1")
        c.execute("""
            INSERT OR IGNORE INTO luckyloop_jobs 
            SELECT * FROM jobs
        """)
        c.execute("DROP TABLE IF EXISTS jobs")
    except:
        pass
    
    # ── Migrate old scraper_status table ────────────────────
    try:
        c.execute("SELECT * FROM scraper_status LIMIT 1")
        c.execute("""
            INSERT OR IGNORE INTO luckyloop_scraper_status 
            SELECT * FROM scraper_status
        """)
        c.execute("DROP TABLE IF EXISTS scraper_status")
    except:
        pass
    
    # ── Migrate old devices table ──────────────────────────
    try:
        c.execute("SELECT * FROM devices LIMIT 1")
        c.execute("""
            INSERT OR IGNORE INTO luckyloop_devices 
            SELECT * FROM devices
        """)
        c.execute("DROP TABLE IF EXISTS devices")
    except:
        pass
    
    conn.commit()
    conn.close()
    print("[LuckyLoop] Database initialized successfully ✅")

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def check_admin(req):
    """LuckyLoop Admin Authentication"""
    pw = req.headers.get("X-Admin-Password") or req.args.get("password") or ""
    return pw == ADMIN_PASSWORD

# ══════════════════════════════════════════════════════════════
#  EXISTING ROUTES (Job Tracker)
# ══════════════════════════════════════════════════════════════

@app.route("/")
def home():
    """LuckyLoop Home Page"""
    return render_template("index.html")

@app.route("/latest")
def latest():
    """LuckyLoop Latest Jobs"""
    return render_template("latest.html")

@app.route("/api/latest")
def api_latest():
    """LuckyLoop API - Get Latest Jobs"""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM luckyloop_jobs ORDER BY updated_at DESC"
    ).fetchall()
    status_row = conn.execute(
        "SELECT * FROM luckyloop_scraper_status WHERE id=1"
    ).fetchone()
    conn.close()
    
    scraper_ok = True
    scraper_msg = "LuckyLoop Scraper OK"
    if status_row:
        scraper_ok = status_row["status"] == "ok"
        scraper_msg = status_row["message"]
    
    return jsonify({
        "jobs": [dict(r) for r in rows],
        "scraper_ok": scraper_ok,
        "scraper_msg": scraper_msg
    })

@app.route("/api/scraper-status", methods=["POST"])
def update_scraper_status():
    """LuckyLoop - Update Scraper Status"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "no data"}), 400
    
    status  = data.get("status", "ok")
    message = data.get("message", "")
    now     = datetime.now().isoformat()
    
    conn = get_db()
    conn.execute("""
        INSERT INTO luckyloop_scraper_status (id, status, message, updated_at)
        VALUES (1, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            status     = excluded.status,
            message    = excluded.message,
            updated_at = excluded.updated_at
    """, (status, message, now))
    conn.commit()
    conn.close()
    print(f"[LuckyLoop Scraper] {status} | {message}")
    return jsonify({"ok": True})

@app.route("/save", methods=["POST", "OPTIONS"])
def save_job():
    """LuckyLoop - Save Job"""
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
        INSERT INTO luckyloop_jobs (job_name, position, available, link, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(job_name) DO UPDATE SET
            position   = excluded.position,
            available  = excluded.available,
            link       = excluded.link,
            updated_at = excluded.updated_at
    """, (job_name, position, available, link, now))
    conn.commit()
    conn.close()
    print(f"[LuckyLoop] Job saved: {job_name}")
    return jsonify({"status": "saved", "job_name": job_name})


# ══════════════════════════════════════════════════════════════
#  HYPERLOOP LICENSE SYSTEM - DEVICE REGISTRATION & VERIFICATION
# ══════════════════════════════════════════════════════════════

@app.route("/api/license/register", methods=["POST"])
def license_register():
    """LuckyLoop - Register new device & generate temporary license key"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ok": False, "error": "Invalid request"}), 400
    
    device_id   = str(data.get("device_id", "") or "").strip()
    device_name = str(data.get("device_name", "") or "Unknown Device").strip()
    device_ip   = request.headers.get("X-Forwarded-For", request.remote_addr or "")
    now         = datetime.now().isoformat()
    
    if not device_id:
        return jsonify({"ok": False, "error": "device_id required"}), 400
    
    conn = get_db()
    
    # Check if already approved
    existing_approved = conn.execute(
        "SELECT permanent_license_key FROM luckyloop_approved_licenses WHERE device_id=?",
        (device_id,)
    ).fetchone()
    
    if existing_approved:
        conn.close()
        return jsonify({
            "ok": True,
            "status": "approved",
            "license_key": existing_approved["permanent_license_key"],
            "message": "✅ Device already approved"
        })
    
    # Check if pending
    existing_pending = conn.execute(
        "SELECT temp_license_key, status FROM luckyloop_pending_licenses WHERE device_id=?",
        (device_id,)
    ).fetchone()
    
    if existing_pending:
        status = existing_pending["status"]
        if status == "rejected":
            # Regenerate new temp key for rejected device
            new_temp_key = f"LUCKYLOOP-TEMP-{generate_random_key(16)}"
            conn.execute("""
                UPDATE luckyloop_pending_licenses 
                SET temp_license_key=?, status='pending', updated_at=?, rejection_reason=NULL
                WHERE device_id=?
            """, (new_temp_key, now, device_id))
            conn.commit()
            conn.close()
            print(f"[LuckyLoop License] Device re-registered: {device_id} | New Temp Key: {new_temp_key}")
            return jsonify({
                "ok": True,
                "status": "pending",
                "license_key": new_temp_key,
                "message": "🔑 New temporary key generated"
            })
        else:
            conn.close()
            return jsonify({
                "ok": True,
                "status": status,
                "license_key": existing_pending["temp_license_key"],
                "message": f"⏳ Device is {status}"
            })
    
    # Generate new temporary key for new device
    temp_key = f"LUCKYLOOP-TEMP-{generate_random_key(16)}"
    
    try:
        conn.execute("""
            INSERT INTO luckyloop_pending_licenses 
            (device_id, device_name, device_ip, temp_license_key, requested_at, status, updated_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?)
        """, (device_id, device_name, device_ip, temp_key, now, now))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"ok": False, "error": "Device registration error"}), 400
    
    conn.close()
    print(f"[LuckyLoop License] New device registered: {device_name} ({device_id})")
    return jsonify({
        "ok": True,
        "status": "pending",
        "license_key": temp_key,
        "message": "🔑 Temporary license key generated. Awaiting admin approval."
    })


@app.route("/api/license/verify/<device_id>", methods=["GET"])
def license_verify(device_id):
    """LuckyLoop - Verify device license status"""
    device_id = str(device_id or "").strip()
    
    conn = get_db()
    
    # Check approved
    approved = conn.execute(
        "SELECT permanent_license_key, is_blocked, block_reason FROM luckyloop_approved_licenses WHERE device_id=?",
        (device_id,)
    ).fetchone()
    
    if approved:
        if approved["is_blocked"]:
            conn.close()
            return jsonify({
                "ok": False,
                "status": "blocked",
                "reason": approved["block_reason"] or "🚫 Device is blocked by LuckyLoop Admin",
                "license_key": ""
            })
        conn.close()
        return jsonify({
            "ok": True,
            "status": "approved",
            "license_key": approved["permanent_license_key"],
            "reason": "✅ Device approved"
        })
    
    # Check pending
    pending = conn.execute(
        "SELECT temp_license_key, status, rejection_reason FROM luckyloop_pending_licenses WHERE device_id=?",
        (device_id,)
    ).fetchone()
    
    if pending:
        if pending["status"] == "rejected":
            conn.close()
            return jsonify({
                "ok": False,
                "status": "rejected",
                "reason": pending["rejection_reason"] or "❌ Your license request was rejected",
                "license_key": ""
            })
        conn.close()
        return jsonify({
            "ok": True,
            "status": "pending",
            "license_key": pending["temp_license_key"],
            "reason": "⏳ Awaiting admin approval"
        })
    
    conn.close()
    return jsonify({
        "ok": False,
        "status": "unknown",
        "reason": "Device not found",
        "license_key": ""
    })


# ══════════════════════════════════════════════════════════════
#  ADMIN PANEL - LICENSE MANAGEMENT
# ══════════════════════════════════════════════════════════════

@app.route("/admin")
def admin_panel():
    """LuckyLoop - Legacy Admin Panel"""
    return render_template("admin.html")

@app.route("/admin-hyperloop")
def admin_hyperloop():
    """LuckyLoop - HyperLoop Admin Panel"""
    return render_template("admin-hyperloop.html")

@app.route("/api/admin/hyperloop/pending", methods=["GET"])
def admin_pending_licenses():
    """LuckyLoop Admin - Get pending license requests"""
    if not check_admin(request):
        return jsonify({"error": "Unauthorized"}), 401
    
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM luckyloop_pending_licenses 
        WHERE status='pending'
        ORDER BY requested_at DESC
    """).fetchall()
    conn.close()
    
    return jsonify({
        "ok": True,
        "data": [dict(r) for r in rows],
        "count": len(rows)
    })


@app.route("/api/admin/hyperloop/approved", methods=["GET"])
def admin_approved_licenses():
    """LuckyLoop Admin - Get approved licenses"""
    if not check_admin(request):
        return jsonify({"error": "Unauthorized"}), 401
    
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM luckyloop_approved_licenses 
        ORDER BY approved_at DESC
    """).fetchall()
    conn.close()
    
    return jsonify({
        "ok": True,
        "data": [dict(r) for r in rows],
        "count": len(rows)
    })


@app.route("/api/admin/hyperloop/stats", methods=["GET"])
def admin_license_stats():
    """LuckyLoop Admin - Get license statistics"""
    if not check_admin(request):
        return jsonify({"error": "Unauthorized"}), 401
    
    conn = get_db()
    
    total_pending = conn.execute(
        "SELECT COUNT(*) as count FROM luckyloop_pending_licenses WHERE status='pending'"
    ).fetchone()["count"]
    
    total_approved = conn.execute(
        "SELECT COUNT(*) as count FROM luckyloop_approved_licenses WHERE is_blocked=0"
    ).fetchone()["count"]
    
    total_blocked = conn.execute(
        "SELECT COUNT(*) as count FROM luckyloop_approved_licenses WHERE is_blocked=1"
    ).fetchone()["count"]
    
    total_rejected = conn.execute(
        "SELECT COUNT(*) as count FROM luckyloop_pending_licenses WHERE status='rejected'"
    ).fetchone()["count"]
    
    conn.close()
    
    return jsonify({
        "ok": True,
        "stats": {
            "pending": total_pending,
            "approved": total_approved,
            "blocked": total_blocked,
            "rejected": total_rejected,
            "total": total_pending + total_approved + total_blocked + total_rejected
        }
    })


@app.route("/api/admin/hyperloop/approve", methods=["POST"])
def admin_approve_license():
    """LuckyLoop Admin - Approve device license"""
    if not check_admin(request):
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json(silent=True) or {}
    device_id = str(data.get("device_id", "") or "").strip()
    
    if not device_id:
        return jsonify({"ok": False, "error": "device_id required"}), 400
    
    conn = get_db()
    
    # Get pending record
    pending = conn.execute(
        "SELECT * FROM luckyloop_pending_licenses WHERE device_id=?",
        (device_id,)
    ).fetchone()
    
    if not pending:
        conn.close()
        return jsonify({"ok": False, "error": "Device not found in pending"}), 404
    
    # Generate permanent key
    perm_key = f"LUCKYLOOP-PERM-{generate_random_key(16)}"
    now = datetime.now().isoformat()
    
    try:
        # Insert into approved
        conn.execute("""
            INSERT INTO luckyloop_approved_licenses 
            (device_id, device_name, device_ip, temp_license_key, permanent_license_key, 
             approved_at, is_blocked, status)
            VALUES (?, ?, ?, ?, ?, ?, 0, 'approved')
        """, (device_id, pending["device_name"], pending["device_ip"], 
              pending["temp_license_key"], perm_key, now))
        
        # Update pending to approved
        conn.execute(
            "UPDATE luckyloop_pending_licenses SET status='approved' WHERE device_id=?",
            (device_id,)
        )
        
        conn.commit()
    except sqlite3.IntegrityError as e:
        conn.close()
        return jsonify({"ok": False, "error": str(e)}), 400
    
    conn.close()
    print(f"[LuckyLoop License] Device APPROVED: {device_id} | Permanent Key: {perm_key}")
    
    return jsonify({
        "ok": True,
        "message": f"✅ Device {device_id} approved!",
        "permanent_license_key": perm_key
    })


@app.route("/api/admin/hyperloop/reject", methods=["POST"])
def admin_reject_license():
    """LuckyLoop Admin - Reject device license"""
    if not check_admin(request):
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json(silent=True) or {}
    device_id = str(data.get("device_id", "") or "").strip()
    reason = str(data.get("reason", "Request rejected by admin") or "").strip()
    
    if not device_id:
        return jsonify({"ok": False, "error": "device_id required"}), 400
    
    conn = get_db()
    conn.execute(
        "UPDATE luckyloop_pending_licenses SET status='rejected', rejection_reason=?, updated_at=? WHERE device_id=?",
        (reason, datetime.now().isoformat(), device_id)
    )
    conn.commit()
    conn.close()
    
    print(f"[LuckyLoop License] Device REJECTED: {device_id} | Reason: {reason}")
    return jsonify({"ok": True, "message": f"❌ Device {device_id} rejected"})


@app.route("/api/admin/hyperloop/block", methods=["POST"])
def admin_block_device():
    """LuckyLoop Admin - Block approved device"""
    if not check_admin(request):
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json(silent=True) or {}
    device_id = str(data.get("device_id", "") or "").strip()
    reason = str(data.get("reason", "🚫 Device blocked by LuckyLoop Admin") or "").strip()
    
    if not device_id:
        return jsonify({"ok": False, "error": "device_id required"}), 400
    
    conn = get_db()
    now = datetime.now().isoformat()
    conn.execute(
        "UPDATE luckyloop_approved_licenses SET is_blocked=1, block_reason=?, blocked_at=? WHERE device_id=?",
        (reason, now, device_id)
    )
    conn.commit()
    conn.close()
    
    print(f"[LuckyLoop License] Device BLOCKED: {device_id} | Reason: {reason}")
    return jsonify({"ok": True, "message": f"🚫 Device {device_id} blocked"})


@app.route("/api/admin/hyperloop/unblock", methods=["POST"])
def admin_unblock_device():
    """LuckyLoop Admin - Unblock device"""
    if not check_admin(request):
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json(silent=True) or {}
    device_id = str(data.get("device_id", "") or "").strip()
    
    if not device_id:
        return jsonify({"ok": False, "error": "device_id required"}), 400
    
    conn = get_db()
    conn.execute(
        "UPDATE luckyloop_approved_licenses SET is_blocked=0, block_reason=NULL, blocked_at=NULL WHERE device_id=?",
        (device_id,)
    )
    conn.commit()
    conn.close()
    
    print(f"[LuckyLoop License] Device UNBLOCKED: {device_id}")
    return jsonify({"ok": True, "message": f"✅ Device {device_id} unblocked"})


@app.route("/api/admin/hyperloop/delete", methods=["POST"])
def admin_delete_license():
    """LuckyLoop Admin - Delete license record"""
    if not check_admin(request):
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json(silent=True) or {}
    device_id = str(data.get("device_id", "") or "").strip()
    license_type = str(data.get("license_type", "pending") or "").strip()  # pending or approved
    
    if not device_id:
        return jsonify({"ok": False, "error": "device_id required"}), 400
    
    conn = get_db()
    
    if license_type == "approved":
        conn.execute("DELETE FROM luckyloop_approved_licenses WHERE device_id=?", (device_id,))
    else:
        conn.execute("DELETE FROM luckyloop_pending_licenses WHERE device_id=?", (device_id,))
    
    conn.commit()
    conn.close()
    
    print(f"[LuckyLoop License] License record DELETED: {device_id}")
    return jsonify({"ok": True, "message": f"🗑️ License record deleted"})


# ══════════════════════════════════════════════════════════════
#  LEGACY DEVICE ROUTES (Backward compatibility)
# ══════════════════════════════════════════════════════════════

@app.route("/api/heartbeat", methods=["POST"])
def heartbeat():
    """LuckyLoop - Device Heartbeat (Legacy)"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ok": False, "blocked": False}), 400

    device_id   = str(data.get("device_id",   "") or "").strip()
    device_name = str(data.get("device_name", "") or "Unknown").strip()
    license_key = str(data.get("license_key", "") or "").strip()
    license_type = str(data.get("license_type", "") or "").strip()
    ip_address  = request.headers.get("X-Forwarded-For", request.remote_addr or "")
    now         = datetime.now().isoformat()

    if not device_id:
        return jsonify({"ok": False, "blocked": False, "reason": "no device_id"}), 400

    conn = get_db()
    existing = conn.execute(
        "SELECT * FROM luckyloop_devices WHERE device_id=?", (device_id,)
    ).fetchone()

    if existing:
        conn.execute("""
            UPDATE luckyloop_devices SET
                device_name  = ?,
                license_key  = ?,
                license_type = ?,
                ip_address   = ?,
                last_seen    = ?
            WHERE device_id = ?
        """, (device_name, license_key, license_type, ip_address, now, device_id))
        is_blocked = bool(existing["is_blocked"])
        block_reason = existing["block_reason"] or ""
    else:
        conn.execute("""
            INSERT INTO luckyloop_devices
                (device_id, device_name, license_key, license_type, ip_address, first_seen, last_seen, is_blocked)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
        """, (device_id, device_name, license_key, license_type, ip_address, now, now))
        is_blocked   = False
        block_reason = ""

    conn.commit()
    conn.close()

    if is_blocked:
        print(f"[LuckyLoop] BLOCKED device tried to connect: {device_name} ({device_id})")
        return jsonify({"ok": False, "blocked": True, "reason": block_reason or "আপনার device block করা হয়েছে।"})

    print(f"[LuckyLoop] Heartbeat from: {device_name} ({device_id})")
    return jsonify({"ok": True, "blocked": False})


@app.route("/api/check/<device_id>", methods=["GET"])
def check_device(device_id):
    """LuckyLoop - Check device status (Legacy)"""
    conn = get_db()
    row = conn.execute(
        "SELECT is_blocked, block_reason FROM luckyloop_devices WHERE device_id=?", (device_id,)
    ).fetchone()
    conn.close()

    if not row:
        return jsonify({"ok": True, "blocked": False})

    if row["is_blocked"]:
        return jsonify({
            "ok": False,
            "blocked": True,
            "reason": row["block_reason"] or "আপনার device block করা হয়েছে।"
        })

    return jsonify({"ok": True, "blocked": False})


@app.route("/api/admin/devices", methods=["GET"])
def admin_get_devices():
    """LuckyLoop Admin - Get all devices (Legacy)"""
    if not check_admin(request):
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM luckyloop_devices ORDER BY last_seen DESC"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/admin/block", methods=["POST"])
def admin_block():
    """LuckyLoop Admin - Block device (Legacy)"""
    if not check_admin(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    device_id = str(data.get("device_id", "") or "").strip()
    reason    = str(data.get("reason", "Admin কর্তৃক block করা হয়েছে") or "").strip()
    if not device_id:
        return jsonify({"error": "device_id required"}), 400
    conn = get_db()
    conn.execute(
        "UPDATE luckyloop_devices SET is_blocked=1, block_reason=? WHERE device_id=?",
        (reason, device_id)
    )
    conn.commit()
    conn.close()
    print(f"[LuckyLoop] Device BLOCKED: {device_id}")
    return jsonify({"ok": True, "blocked": True})


@app.route("/api/admin/unblock", methods=["POST"])
def admin_unblock():
    """LuckyLoop Admin - Unblock device (Legacy)"""
    if not check_admin(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    device_id = str(data.get("device_id", "") or "").strip()
    if not device_id:
        return jsonify({"error": "device_id required"}), 400
    conn = get_db()
    conn.execute(
        "UPDATE luckyloop_devices SET is_blocked=0, block_reason='' WHERE device_id=?",
        (device_id,)
    )
    conn.commit()
    conn.close()
    print(f"[LuckyLoop] Device UNBLOCKED: {device_id}")
    return jsonify({"ok": True, "blocked": False})


@app.route("/api/admin/delete", methods=["POST"])
def admin_delete():
    """LuckyLoop Admin - Delete device (Legacy)"""
    if not check_admin(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    device_id = str(data.get("device_id", "") or "").strip()
    if not device_id:
        return jsonify({"error": "device_id required"}), 400
    conn = get_db()
    conn.execute("DELETE FROM luckyloop_devices WHERE device_id=?", (device_id,))
    conn.commit()
    conn.close()
    print(f"[LuckyLoop] Device DELETED: {device_id}")
    return jsonify({"ok": True})


# ══════════════════════════════════════════════════════════════
#  INITIALIZATION & STARTUP
# ═══════════════��══════════════════════════════════════════════

init_db()

try:
    from scraper import start_scraper
    start_scraper()
except Exception as e:
    print(f"[LuckyLoop] Scraper warning: {e}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"""
    ╔══════════════════════════════════════════════════════════╗
    ║  🚀 LuckyLoop Server v2.0 - HyperLoop License System    ║
    ║  🔗 Running on: http://0.0.0.0:{port}                    ║
    ║  📊 Admin Panel: /admin-hyperloop                        ║
    ║  🔐 License API: /api/license/*                          ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    app.run(host="0.0.0.0", port=port, debug=False)
