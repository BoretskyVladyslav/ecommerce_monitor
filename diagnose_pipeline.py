"""
=============================================================================
DIAGNOSTIC SCRIPT: End-to-End Scraping & DB Update Pipeline Verification
=============================================================================
Checks:
  1. DB connectivity & live table structure (SHOW COLUMNS for each table)
  2. Products in 'products' table - count, marketplace breakdown
  3. Variants in 'product_options' - count, columns present, sample rows
  4. 'monitored_product_options' - count, columns
  5. 'monitored_products_log' - last 5 log entries (proof of engine runs)
  6. Simulate update_product_option_status() call as engine would do
  7. Read session files from data/sessions/
  8. Cross-check: do product_options rows have option_name_1/option_name_2?
     (column names used in code vs schema.sql which only has option_name)
"""

import pymysql
import os
import sys
import glob
import json
import traceback
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from config.settings import settings

SEP  = "=" * 72
SEP2 = "-" * 72

def section(title):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)

def ok(msg):  print(f"  ✅  {msg}")
def warn(msg): print(f"  ⚠️  {msg}")
def fail(msg): print(f"  ❌  {msg}")
def info(msg): print(f"  ℹ️  {msg}")

def connect():
    return pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        db=settings.DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10
    )

def get_columns(cursor, table):
    try:
        cursor.execute(f"SHOW COLUMNS FROM `{table}`")
        return [r['Field'] for r in cursor.fetchall()]
    except Exception as e:
        return f"ERROR: {e}"

def table_exists(cursor, table):
    cursor.execute(
        "SELECT COUNT(*) as c FROM information_schema.tables "
        "WHERE table_schema=%s AND table_name=%s",
        (settings.DB_NAME, table)
    )
    return cursor.fetchone()['c'] > 0

print(f"\n{'#'*72}")
print(f"  PIPELINE DIAGNOSTIC — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'#'*72}")

# ─── 1. DB CONNECTIVITY ────────────────────────────────────────────────────
section("1. DATABASE CONNECTIVITY")
try:
    conn = connect()
    ok(f"Connected to MySQL @ {settings.DB_HOST}:{settings.DB_PORT} / {settings.DB_NAME}")
except Exception as e:
    fail(f"Cannot connect to DB: {e}")
    sys.exit(1)

cursor = conn.cursor()

# ─── 2. TABLE INVENTORY ───────────────────────────────────────────────────
section("2. TABLE INVENTORY (Tables the engine references)")

EXPECTED_TABLES = [
    "products",
    "product_options",
    "monitored_products",
    "monitored_product_options",
    "monitored_products_log",
    "sessions",
    "settings",
]

for t in EXPECTED_TABLES:
    if table_exists(cursor, t):
        cols = get_columns(cursor, t)
        ok(f"`{t}` EXISTS  — columns: {cols}")
    else:
        fail(f"`{t}` MISSING from database!")

# ─── 3. products TABLE ────────────────────────────────────────────────────
section("3. `products` TABLE — Content")

if table_exists(cursor, "products"):
    cursor.execute("SELECT COUNT(*) as c FROM products")
    total = cursor.fetchone()['c']
    info(f"Total rows: {total}")

    cursor.execute("SELECT COUNT(*) as c FROM products WHERE original_url IS NOT NULL")
    with_url = cursor.fetchone()['c']
    info(f"Rows with URL (processable): {with_url}")

    # Breakdown by platform
    for platform, pattern in [("Shein","shein"), ("AliExpress","aliexpress"), ("Temu","temu"), ("Amazon","amazon")]:
        cursor.execute(
            "SELECT COUNT(*) as c FROM products WHERE original_url LIKE %s",
            (f"%{pattern}%",)
        )
        c = cursor.fetchone()['c']
        if c: info(f"  {platform}: {c} products")

    # Sample 5 rows
    cursor.execute("SELECT id, original_title, original_url FROM products LIMIT 5")
    rows = cursor.fetchall()
    print(f"\n  Sample rows:")
    for r in rows:
        url_short = (r['original_url'] or '')[:60]
        title_short = (r['original_title'] or 'N/A')[:40]
        print(f"    ID={r['id']}  |  {title_short}  |  {url_short}")
else:
    fail("`products` table does not exist — engine will return 0 tasks!")

# ─── 4. product_options TABLE ─────────────────────────────────────────────
section("4. `product_options` TABLE — CRITICAL COLUMN CHECK")

if table_exists(cursor, "product_options"):
    cols = get_columns(cursor, "product_options")
    ok(f"Table exists. Columns: {cols}")

    # CRITICAL: engine code reads option_name_1 and option_name_2
    for needed_col in ["option_name_1", "option_name_2", "url", "status", "updated_at"]:
        if needed_col in cols:
            ok(f"  Column `{needed_col}` PRESENT")
        else:
            fail(f"  Column `{needed_col}` MISSING — engine code references this!")

    cursor.execute("SELECT COUNT(*) as c FROM product_options")
    count = cursor.fetchone()['c']
    info(f"Total variant rows: {count}")

    # Sample
    cursor.execute("SELECT * FROM product_options LIMIT 5")
    rows = cursor.fetchall()
    if rows:
        print(f"\n  Sample product_options rows:")
        for r in rows:
            print(f"    {r}")
    else:
        warn("product_options is EMPTY — no variants defined for any product")
else:
    fail("`product_options` table does not exist!")

# ─── 5. monitored_product_options TABLE ───────────────────────────────────
section("5. `monitored_product_options` TABLE (Legacy fallback)")

if table_exists(cursor, "monitored_product_options"):
    cols = get_columns(cursor, "monitored_product_options")
    ok(f"Table exists. Columns: {cols}")
    cursor.execute("SELECT COUNT(*) as c FROM monitored_product_options")
    count = cursor.fetchone()['c']
    info(f"Total rows: {count}")

    # Check if updated_at exists (needed for legacy update query)
    if "updated_at" in cols:
        ok("  `updated_at` column present — legacy UPDATE query will work")
    else:
        fail("  `updated_at` MISSING — legacy UPDATE query will fail!")

    cursor.execute("SELECT * FROM monitored_product_options ORDER BY id DESC LIMIT 5")
    rows = cursor.fetchall()
    if rows:
        print("\n  Last 5 legacy options:")
        for r in rows: print(f"    {r}")
else:
    fail("`monitored_product_options` table missing!")

# ─── 6. monitored_products_log TABLE ─────────────────────────────────────
section("6. `monitored_products_log` TABLE — Proof of Engine Runs")

if table_exists(cursor, "monitored_products_log"):
    cols = get_columns(cursor, "monitored_products_log")
    ok(f"Table exists. Columns: {cols}")

    cursor.execute("SELECT COUNT(*) as c FROM monitored_products_log")
    count = cursor.fetchone()['c']
    info(f"Total log entries: {count}")

    cursor.execute(
        "SELECT * FROM monitored_products_log ORDER BY created_at DESC LIMIT 10"
    )
    rows = cursor.fetchall()
    if rows:
        ok(f"Last {len(rows)} log entries (most recent first):")
        for r in rows:
            print(f"    {r}")
    else:
        warn("Log table is empty — engine has NEVER written a successful check")
else:
    fail("`monitored_products_log` table missing!")

# ─── 7. SIMULATE update_product_option_status ────────────────────────────
section("7. SIMULATE `update_product_option_status()` — Dry Run")

# Try the exact query the engine uses for product_options
if table_exists(cursor, "product_options"):
    cursor.execute("SELECT id, status FROM product_options LIMIT 1")
    row = cursor.fetchone()
    if row:
        opt_id = row['id']
        old_status = row['status']
        new_status = 1 if old_status != 1 else 0
        try:
            cursor.execute(
                "UPDATE product_options SET status = %s WHERE id = %s",
                (new_status, opt_id)
            )
            conn.commit()
            ok(f"product_options UPDATE succeeded: id={opt_id}  {old_status} → {new_status}")
            # Restore
            cursor.execute(
                "UPDATE product_options SET status = %s WHERE id = %s",
                (old_status, opt_id)
            )
            conn.commit()
            ok("  Restored original status.")
        except Exception as e:
            fail(f"product_options UPDATE failed: {e}")
    else:
        warn("No rows in product_options to test UPDATE against.")

# Try the exact query for monitored_product_options
if table_exists(cursor, "monitored_product_options"):
    cursor.execute("SELECT id, status FROM monitored_product_options LIMIT 1")
    row = cursor.fetchone()
    if row:
        opt_id = row['id']
        old_status = row['status']
        new_status = 1 if old_status != 1 else 0
        try:
            cols = get_columns(cursor, "monitored_product_options")
            if "updated_at" in cols:
                cursor.execute(
                    "UPDATE monitored_product_options SET status=%s, updated_at=NOW() WHERE id=%s",
                    (new_status, opt_id)
                )
            else:
                cursor.execute(
                    "UPDATE monitored_product_options SET status=%s WHERE id=%s",
                    (new_status, opt_id)
                )
            conn.commit()
            ok(f"monitored_product_options UPDATE succeeded: id={opt_id}  {old_status} → {new_status}")
            cursor.execute(
                "UPDATE monitored_product_options SET status=%s WHERE id=%s",
                (old_status, opt_id)
            )
            conn.commit()
            ok("  Restored original status.")
        except Exception as e:
            fail(f"monitored_product_options UPDATE failed: {e}")
    else:
        warn("No rows in monitored_product_options to test UPDATE against.")

# ─── 8. GOLDEN SESSION FILES ──────────────────────────────────────────────
section("8. GOLDEN SESSION FILES — data/sessions/")

sessions_dir = os.path.join("data", "sessions")
if os.path.exists(sessions_dir):
    files = glob.glob(os.path.join(sessions_dir, "*.json"))
    if files:
        ok(f"Found {len(files)} session file(s):")
        for f in files:
            size_kb = os.path.getsize(f) / 1024
            try:
                with open(f) as fh:
                    data = json.load(fh)
                cookies = len(data.get('cookies', []))
                origins = len(data.get('origins', []))
                ok(f"  {os.path.basename(f)} ({size_kb:.1f} KB)  cookies={cookies}  origins={origins}")
            except Exception as e:
                warn(f"  {os.path.basename(f)} — could not parse: {e}")
    else:
        fail("No session files in data/sessions/ — engine will run as guest!")
else:
    fail("data/sessions/ directory does not exist!")

# ─── 9. DATA-FLOW CROSS-CHECK ────────────────────────────────────────────
section("9. CODE vs SCHEMA CONSISTENCY CHECK")

info("Checking alignment between db_manager.py queries and actual DB columns...")

# fetch_active_products uses: products(id, original_url, original_title)
# product_options(id, option_name_1, option_name_2, url)
# monitored_product_options(id, product_id, option_name, status)

checks = {
    "products.id":              ("products", "id"),
    "products.original_url":    ("products", "original_url"),
    "products.original_title":  ("products", "original_title"),
    "product_options.option_name_1": ("product_options", "option_name_1"),
    "product_options.option_name_2": ("product_options", "option_name_2"),
    "product_options.url":      ("product_options", "url"),
    "product_options.status":   ("product_options", "status"),
    "monitored_product_options.product_id": ("monitored_product_options", "product_id"),
    "monitored_product_options.option_name": ("monitored_product_options", "option_name"),
    "monitored_product_options.updated_at":  ("monitored_product_options", "updated_at"),
    "monitored_products_log.option_id":  ("monitored_products_log", "option_id"),
    "monitored_products_log.note":       ("monitored_products_log", "note"),
}

all_ok = True
for label, (table, column) in checks.items():
    if not table_exists(cursor, table):
        fail(f"{label} — table `{table}` MISSING")
        all_ok = False
        continue
    cols = get_columns(cursor, table)
    if isinstance(cols, list) and column in cols:
        ok(f"{label}")
    else:
        fail(f"{label} — column MISSING from `{table}`  (actual cols: {cols})")
        all_ok = False

if all_ok:
    ok("ALL referenced columns exist in database — code/schema in sync")

# ─── SUMMARY ──────────────────────────────────────────────────────────────
section("DIAGNOSTIC COMPLETE")
conn.close()
print(f"  Finished at {datetime.now().strftime('%H:%M:%S')}\n")
