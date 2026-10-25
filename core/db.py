import sqlite3
from pathlib import Path
from datetime import date, timedelta, datetime
from contextlib import contextmanager
import os

DB_PATH = os.getenv("BLOOM_DB_PATH", str(Path(__file__).resolve().parent.parent / "bloom.db"))

def connect():
    """Create a raw connection with foreign keys, busy timeout, and WAL mode for concurrency."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except Exception:
        pass
    return conn

@contextmanager
def get_connection():
    """Managed connection context that guarantees commit/rollback and closure."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with get_connection() as c:
        # 1. Base table creation (using modern schema without UNIQUE(name, grade))
        c.executescript("""
        CREATE TABLE IF NOT EXISTS students (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          owner_id TEXT UNIQUE NOT NULL,
          username TEXT UNIQUE,
          password_hash TEXT DEFAULT '',
          name TEXT NOT NULL,
          email TEXT,
          grade TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS attempts (
          id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL, subject TEXT NOT NULL,
          topic TEXT NOT NULL, question TEXT NOT NULL, answer TEXT, expected TEXT, correct INTEGER NOT NULL,
          mistake_type TEXT NOT NULL DEFAULT 'conceptual', mode TEXT NOT NULL DEFAULT 'diagnostic',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(student_id) REFERENCES students(id)
        );
        CREATE TABLE IF NOT EXISTS mastery (
          id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL, subject TEXT NOT NULL,
          topic TEXT NOT NULL, mistake_type TEXT NOT NULL, error_count INTEGER NOT NULL DEFAULT 0,
          latest_score INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(student_id, subject, topic, mistake_type),
          FOREIGN KEY(student_id) REFERENCES students(id)
        );
        CREATE TABLE IF NOT EXISTS reviews (
          id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL, subject TEXT NOT NULL,
          topic TEXT NOT NULL, due_date TEXT NOT NULL, reason TEXT NOT NULL, completed INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(student_id) REFERENCES students(id)
        );
        CREATE TABLE IF NOT EXISTS test_sessions (
          id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL, subject TEXT NOT NULL,
          topic TEXT NOT NULL, scored REAL NOT NULL, total REAL NOT NULL, percentage INTEGER NOT NULL,
          mistake_types TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(student_id) REFERENCES students(id)
        );
        CREATE TABLE IF NOT EXISTS recall_sessions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          student_id INTEGER NOT NULL,
          review_id INTEGER,
          subject TEXT NOT NULL,
          topic TEXT NOT NULL,
          prompt TEXT NOT NULL,
          response TEXT NOT NULL,
          self_eval TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(student_id) REFERENCES students(id)
        );
        CREATE TABLE IF NOT EXISTS textbook_sessions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          student_id INTEGER NOT NULL,
          title TEXT NOT NULL,
          source_type TEXT NOT NULL DEFAULT 'pdf',
          source_name TEXT NOT NULL,
          file_path TEXT,
          file_hash TEXT,
          file_size INTEGER DEFAULT 0,
          extracted_text TEXT NOT NULL,
          page_count INTEGER DEFAULT 1,
          word_count INTEGER DEFAULT 0,
          is_truncated INTEGER DEFAULT 0,
          truncation_info TEXT DEFAULT '',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS textbook_qa (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id INTEGER NOT NULL,
          student_id INTEGER NOT NULL,
          question TEXT NOT NULL,
          answer TEXT NOT NULL,
          source_type TEXT NOT NULL DEFAULT 'ai',
          relevant_excerpt TEXT DEFAULT '',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(session_id) REFERENCES textbook_sessions(id) ON DELETE CASCADE,
          FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS saved_concepts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          student_id INTEGER NOT NULL,
          topic TEXT NOT NULL,
          concept_name TEXT NOT NULL,
          question TEXT NOT NULL,
          notes TEXT DEFAULT '',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_attempts_student ON attempts(student_id);
        CREATE INDEX IF NOT EXISTS idx_reviews_student ON reviews(student_id, completed, due_date);
        CREATE INDEX IF NOT EXISTS idx_tb_sessions_student ON textbook_sessions(student_id);
        CREATE INDEX IF NOT EXISTS idx_tb_qa_session ON textbook_qa(session_id, student_id);
        CREATE INDEX IF NOT EXISTS idx_saved_concepts_student ON saved_concepts(student_id);
        """)

        # 2. Check if students table requires migration to modern unique username and owner architecture
        cols = [r["name"] for r in c.execute("PRAGMA table_info(students)").fetchall()]
        table_sql_row = c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='students'").fetchone()
        table_sql = table_sql_row["sql"] if table_sql_row else ""

        needs_table_rebuild = (
            ("username" not in cols)
            or ("password_hash" not in cols)
            or ("UNIQUE(name, grade)" in table_sql)
            or ("UNIQUE (name, grade)" in table_sql)
        )

        # Backfill any legacy or raw-inserted rows lacking owner_id or username
        c.execute("UPDATE students SET owner_id = 'legacy_' || id WHERE owner_id IS NULL OR owner_id = ''")
        c.execute("UPDATE students SET username = 'legacy_' || id WHERE username IS NULL OR username = ''")

    if needs_table_rebuild:
        _migrate_students_table_schema()

def _migrate_students_table_schema():
    """Safely migrate students table removing UNIQUE(name, grade) and adding username and password_hash."""
    import bcrypt
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("DROP TABLE IF EXISTS students_migrated")
        conn.execute("""
        CREATE TABLE students_migrated (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          owner_id TEXT UNIQUE NOT NULL,
          username TEXT UNIQUE,
          password_hash TEXT DEFAULT '',
          name TEXT NOT NULL,
          email TEXT,
          grade TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)

        existing_rows = [dict(r) for r in conn.execute("SELECT * FROM students").fetchall()]

        rutuja_hash = bcrypt.hashpw(b"rutuja123", bcrypt.gensalt()).decode("utf-8")
        default_hash = bcrypt.hashpw(b"bloom123", bcrypt.gensalt()).decode("utf-8")

        used_usernames = set()
        used_owners = set()

        for row in existing_rows:
            rid = row["id"]
            rname = row.get("name") or "Learner"
            rgrade = row.get("grade") or "Class 10"
            remail = row.get("email") or None
            rcreated = row.get("created_at") or datetime.now().isoformat()
            row_owner = (row.get("owner_id") or "").strip()

            if not row_owner or row_owner in used_owners:
                row_owner = f"usr_legacy_{rid}"
            used_owners.add(row_owner)

            # Safe recovery of Rutuja College account
            if rid == 4 or (rname.lower() == "rutuja" and (row_owner == "usr_rutuja_test" or rgrade == "College")):
                username = "rutuja"
                pwd_hash = rutuja_hash
            elif rname.lower() == "rutuja" and rgrade == "Class 10":
                username = "rutuja_class10"
                pwd_hash = default_hash
            elif rid == 1:
                username = "learner"
                pwd_hash = default_hash
            elif rid == 2:
                username = "learner_class12"
                pwd_hash = default_hash
            else:
                base_u = rname.lower().replace(" ", "_")
                username = f"{base_u}_{rid}"
                pwd_hash = default_hash

            cand_u = username
            idx = 2
            while cand_u in used_usernames:
                cand_u = f"{username}_{idx}"
                idx += 1
            username = cand_u
            used_usernames.add(username)

            conn.execute(
                "INSERT INTO students_migrated(id, owner_id, username, password_hash, name, email, grade, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (rid, row_owner, username, pwd_hash, rname, remail, rgrade, rcreated)
            )

        conn.execute("DROP TABLE students")
        conn.execute("ALTER TABLE students_migrated RENAME TO students")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_students_owner ON students(owner_id)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_students_username ON students(username)")
        conn.commit()
    finally:
        conn.close()

migrate_db = init_db

def create_user_account(username, password_hash, display_name, grade="Class 10", email="", owner_id=None):
    """Create a new authenticated student record with a unique username, hashed password, and stable owner ID."""
    clean_username = (username or "").strip().lower()
    if not clean_username:
        raise ValueError("Username is required.")
    
    clean_name = (display_name or "Learner").strip() or "Learner"
    clean_grade = (grade or "Class 10").strip()
    clean_email = (email or "").strip() or None

    import hashlib
    clean_owner = (owner_id or "").strip()
    if not clean_owner:
        clean_owner = f"usr_{hashlib.sha256(clean_username.encode('utf-8')).hexdigest()[:16]}"

    with get_connection() as c:
        existing = c.execute("SELECT id FROM students WHERE LOWER(username)=?", (clean_username,)).fetchone()
        if existing:
            raise ValueError("This username is already taken. Please choose another.")

        try:
            cur = c.execute(
                "INSERT INTO students(owner_id, username, password_hash, name, email, grade) VALUES(?,?,?,?,?,?)",
                (clean_owner, clean_username, password_hash, clean_name, clean_email, clean_grade)
            )
            new_id = cur.lastrowid
            return dict(c.execute("SELECT * FROM students WHERE id=?", (new_id,)).fetchone())
        except sqlite3.IntegrityError as ie:
            if "username" in str(ie).lower():
                raise ValueError("This username is already taken. Please choose another.") from ie
            raise

def get_student_by_username(username: str):
    """Lookup student account by unique username (case-insensitive)."""
    clean_u = (username or "").strip().lower()
    if not clean_u:
        return None
    with get_connection() as c:
        row = c.execute("SELECT * FROM students WHERE LOWER(username)=?", (clean_u,)).fetchone()
        return dict(row) if row else None

def get_student_by_id(student_id: int):
    """Lookup student account by primary key ID."""
    with get_connection() as c:
        row = c.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone()
        return dict(row) if row else None

def get_student_by_owner_id(owner_id: str):
    """Lookup student account by internal stable owner ID."""
    clean_owner = (owner_id or "").strip()
    if not clean_owner:
        return None
    with get_connection() as c:
        row = c.execute("SELECT * FROM students WHERE owner_id=?", (clean_owner,)).fetchone()
        return dict(row) if row else None

def get_or_create_account(owner_id, display_name=None, email=None, grade="Class 10"):
    """
    Retrieve or create an account for an authenticated owner.
    Editing the display name or grade updates this student's profile without
    creating a new account or resetting learning progress.
    """
    clean_owner = (owner_id or "").strip()
    if not clean_owner:
        clean_owner = "local_dev_learner"
    clean_name = (display_name or "Learner").strip() or "Learner"
    clean_grade = (grade or "Class 10").strip()
    clean_email = (email or "").strip()

    with get_connection() as c:
        row = c.execute("SELECT * FROM students WHERE owner_id=?", (clean_owner,)).fetchone()
        if row:
            current = dict(row)
            upd_name = clean_name if (display_name and clean_name != current.get("name")) else current.get("name")
            upd_grade = clean_grade if (grade and clean_grade != current.get("grade")) else current.get("grade")
            upd_email = clean_email if (email and clean_email != current.get("email")) else current.get("email")

            if upd_name != current.get("name") or upd_grade != current.get("grade") or upd_email != current.get("email"):
                c.execute(
                    "UPDATE students SET name=?, grade=?, email=? WHERE id=?",
                    (upd_name, upd_grade, upd_email, current["id"])
                )
                return dict(c.execute("SELECT * FROM students WHERE id=?", (current["id"],)).fetchone())
            return current

        # Generate a candidate username and bcrypt password hash for this account
        base_u = clean_name.lower().replace(" ", "_")
        candidate_u = base_u
        idx = 1
        while c.execute("SELECT id FROM students WHERE LOWER(username)=?", (candidate_u,)).fetchone():
            candidate_u = f"{base_u}_{idx}"
            idx += 1

        import bcrypt
        default_hash = bcrypt.hashpw(b"bloom123", bcrypt.gensalt()).decode("utf-8")
        cur = c.execute(
            "INSERT INTO students(owner_id, username, password_hash, name, email, grade) VALUES(?,?,?,?,?,?)",
            (clean_owner, candidate_u, default_hash, clean_name, clean_email, clean_grade)
        )
        new_id = cur.lastrowid
        return dict(c.execute("SELECT * FROM students WHERE id=?", (new_id,)).fetchone())

def update_student_profile(student_id, owner_id, display_name=None, grade=None):
    """Update profile fields for an authenticated student record in place."""
    with get_connection() as c:
        row = c.execute("SELECT * FROM students WHERE id=? AND owner_id=?", (student_id, owner_id)).fetchone()
        if not row:
            return None
        new_name = (display_name or row["name"]).strip() or row["name"]
        new_grade = (grade or row["grade"]).strip() or row["grade"]
        c.execute("UPDATE students SET name=?, grade=? WHERE id=? AND owner_id=?", (new_name, new_grade, student_id, owner_id))
        return dict(c.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone())

def migrate_legacy_student(legacy_student_id: int, new_owner_id: str) -> bool:
    """Explicitly assign an unattached legacy student record to an authenticated account."""
    with get_connection() as c:
        row = c.execute("SELECT id FROM students WHERE id = ? AND (owner_id IS NULL OR owner_id = 'legacy:learner' OR owner_id LIKE 'legacy_%')", (legacy_student_id,)).fetchone()
        if not row:
            return False
        c.execute("UPDATE students SET owner_id = ? WHERE id = ?", (new_owner_id, legacy_student_id))
        return True

def get_or_create_student(name, grade):
    """Legacy helper maintained for backward compatibility. Uses stable id lookup without unique name/grade collisions."""
    clean_name = (name or "Learner").strip() or "Learner"
    clean_grade = (grade or "Class 10").strip()
    with get_connection() as c:
        row = c.execute("SELECT id FROM students WHERE name=? AND grade=?", (clean_name, clean_grade)).fetchone()
        if row:
            return row["id"]
        # If student exists under same name, update grade so learning history is preserved
        existing = c.execute("SELECT id FROM students WHERE name=?", (clean_name,)).fetchone()
        if existing:
            c.execute("UPDATE students SET grade=? WHERE id=?", (clean_grade, existing["id"]))
            return existing["id"]

        import uuid, bcrypt
        clean_owner = f"local_{uuid.uuid4().hex[:12]}"
        base_u = f"student_{clean_name.lower().replace(' ', '_')}"
        candidate_u = base_u
        idx = 1
        while c.execute("SELECT id FROM students WHERE LOWER(username)=?", (candidate_u,)).fetchone():
            candidate_u = f"{base_u}_{idx}"
            idx += 1
        default_hash = bcrypt.hashpw(b"bloom123", bcrypt.gensalt()).decode("utf-8")
        cur = c.execute(
            "INSERT INTO students(owner_id, username, password_hash, name, grade) VALUES(?,?,?,?,?)",
            (clean_owner, candidate_u, default_hash, clean_name, clean_grade)
        )
        return cur.lastrowid

def save_attempt(student_id, subject, topic, question, answer, expected, correct, mistake_type="conceptual", mode="diagnostic"):
    with get_connection() as c:
        c.execute("""INSERT INTO attempts(student_id,subject,topic,question,answer,expected,correct,mistake_type,mode)
                     VALUES(?,?,?,?,?,?,?,?,?)""",
                  (student_id, subject, topic, question, str(answer or ""), str(expected or ""), int(bool(correct)), mistake_type, mode))

def get_attempts(student_id, limit=200):
    with get_connection() as c:
        rows = c.execute("SELECT * FROM attempts WHERE student_id=? ORDER BY created_at DESC, id DESC LIMIT ?", (student_id, limit)).fetchall()
        return [dict(r) for r in rows]

def get_previous_questions(student_id, topic, limit=30):
    """Retrieve normalized question prompts previously seen by this learner for anti-repetition check."""
    with get_connection() as c:
        rows = c.execute("""SELECT DISTINCT question FROM attempts
                            WHERE student_id=? AND LOWER(topic)=LOWER(?)
                            ORDER BY id DESC LIMIT ?""", (student_id, (topic or "").strip(), limit)).fetchall()
        return [r["question"] for r in rows]

def get_dashboard_data(student_id):
    with get_connection() as c:
        attempts_row = c.execute("SELECT COUNT(*) n, COALESCE(AVG(correct),0) acc FROM attempts WHERE student_id=?", (student_id,)).fetchone()
        diag_sessions = c.execute("""
            SELECT COUNT(DISTINCT DATE(created_at) || ':' || LOWER(subject) || ':' || LOWER(topic)) n
            FROM attempts WHERE student_id=? AND mode='diagnostic'
        """, (student_id,)).fetchone()["n"]
        practice_count = c.execute("SELECT COUNT(*) n FROM attempts WHERE student_id=? AND mode='practice'", (student_id,)).fetchone()["n"]
        tests_row = c.execute("SELECT COUNT(*) n, COALESCE(AVG(percentage),0) avg_pct FROM test_sessions WHERE student_id=?", (student_id,)).fetchone()

        # Deduplicate topics by lowercase name across attempts and test sessions
        topics_row = c.execute("""
            SELECT COUNT(DISTINCT LOWER(topic)) n FROM (
                SELECT topic FROM attempts WHERE student_id=?
                UNION
                SELECT topic FROM test_sessions WHERE student_id=?
            )
        """, (student_id, student_id)).fetchone()["n"]

        today_str = date.today().isoformat()
        due_count = c.execute("SELECT COUNT(*) n FROM reviews WHERE student_id=? AND completed=0 AND due_date<=?", (student_id, today_str)).fetchone()["n"]
        upcoming_count = c.execute("SELECT COUNT(*) n FROM reviews WHERE student_id=? AND completed=0 AND due_date>?", (student_id, today_str)).fetchone()["n"]
        completed_reviews = c.execute("SELECT COUNT(*) n FROM reviews WHERE student_id=? AND completed=1", (student_id,)).fetchone()["n"]

        accuracy = round(attempts_row["acc"] * 100) if attempts_row["n"] > 0 else (round(tests_row["avg_pct"]) if tests_row["n"] > 0 else 0)
        return {
            "topics": topics_row,
            "attempts": attempts_row["n"],
            "diagnostic_sessions": diag_sessions,
            "practice_questions": practice_count,
            "tests": tests_row["n"],
            "accuracy": accuracy,
            "due": due_count,
            "upcoming": upcoming_count,
            "completed_reviews": completed_reviews
        }

def add_review(student_id, subject, topic, days=1, reason="Review suggested"):
    due = (date.today() + timedelta(days=max(0, int(days)))).isoformat()
    with get_connection() as c:
        existing = c.execute("SELECT id FROM reviews WHERE student_id=? AND LOWER(subject)=LOWER(?) AND LOWER(topic)=LOWER(?) AND completed=0", (student_id, subject, topic)).fetchone()
        if existing:
            c.execute("UPDATE reviews SET due_date=?, reason=? WHERE id=?", (due, reason, existing["id"]))
            return existing["id"]
        else:
            cur = c.execute("INSERT INTO reviews(student_id,subject,topic,due_date,reason) VALUES(?,?,?,?,?)", (student_id, subject, topic, due, reason))
            return cur.lastrowid

def get_due_reviews(student_id, limit=50):
    with get_connection() as c:
        rows = c.execute("""SELECT * FROM reviews WHERE student_id=? AND completed=0 AND due_date<=?
                            ORDER BY due_date ASC LIMIT ?""", (student_id, date.today().isoformat(), limit)).fetchall()
        return [dict(r) for r in rows]

def get_upcoming_reviews(student_id, limit=50):
    with get_connection() as c:
        rows = c.execute("""SELECT * FROM reviews WHERE student_id=? AND completed=0 AND due_date>?
                            ORDER BY due_date ASC LIMIT ?""", (student_id, date.today().isoformat(), limit)).fetchall()
        return [dict(r) for r in rows]

def get_completed_reviews(student_id, limit=50):
    with get_connection() as c:
        rows = c.execute("""SELECT * FROM reviews WHERE student_id=? AND completed=1
                            ORDER BY id DESC LIMIT ?""", (student_id, limit)).fetchall()
        return [dict(r) for r in rows]

def mark_review_done(student_id, review_id):
    with get_connection() as c:
        c.execute("UPDATE reviews SET completed=1 WHERE id=? AND student_id=?", (review_id, student_id))

def get_review_streak(student_id, subject, topic):
    with get_connection() as c:
        row = c.execute(
            "SELECT COUNT(*) as streak FROM reviews WHERE student_id=? AND LOWER(subject)=LOWER(?) AND LOWER(topic)=LOWER(?) AND completed=1",
            (student_id, subject, topic)
        ).fetchone()
        return row["streak"] if row else 0

def save_recall_session(student_id, review_id, subject, topic, prompt, response, self_eval):
    with get_connection() as c:
        cur = c.execute("""INSERT INTO recall_sessions(student_id, review_id, subject, topic, prompt, response, self_eval)
                           VALUES(?,?,?,?,?,?,?)""",
                        (student_id, review_id, subject, topic, str(prompt), str(response), str(self_eval)))
        return cur.lastrowid

def get_recall_sessions(student_id, limit=50):
    with get_connection() as c:
        rows = c.execute("""SELECT * FROM recall_sessions WHERE student_id=?
                            ORDER BY created_at DESC, id DESC LIMIT ?""", (student_id, limit)).fetchall()
        return [dict(r) for r in rows]

def update_mastery(student_id, subject, topic, mistake_type, error_count, score):
    with get_connection() as c:
        c.execute("""INSERT INTO mastery(student_id,subject,topic,mistake_type,error_count,latest_score)
                     VALUES(?,?,?,?,?,?)
                     ON CONFLICT(student_id,subject,topic,mistake_type) DO UPDATE SET
                     error_count=mastery.error_count+excluded.error_count,
                     latest_score=excluded.latest_score, updated_at=CURRENT_TIMESTAMP""",
                  (student_id, subject, topic, mistake_type, int(error_count), int(score)))

def get_all_mastery(student_id):
    with get_connection() as c:
        rows = c.execute("SELECT * FROM mastery WHERE student_id=? ORDER BY error_count DESC", (student_id,)).fetchall()
        return [dict(r) for r in rows]

def get_topics(student_id):
    with get_connection() as c:
        rows = c.execute("""
            SELECT DISTINCT subject, topic FROM (
                SELECT subject, topic FROM attempts WHERE student_id=?
                UNION
                SELECT subject, topic FROM test_sessions WHERE student_id=?
            ) ORDER BY topic
        """, (student_id, student_id)).fetchall()
        return [dict(r) for r in rows]

def mark_review_done_and_reschedule(student_id, review_id, subject, topic, days=3, reason="Follow-up spaced review"):
    mark_review_done(student_id, review_id)
    return add_review(student_id, subject, topic, days, reason)

def save_test_session(student_id, subject, topic, scored, total, percentage, mistake_types="", notes=""):
    with get_connection() as c:
        cur = c.execute("""INSERT INTO test_sessions(student_id,subject,topic,scored,total,percentage,mistake_types,notes)
                           VALUES(?,?,?,?,?,?,?,?)""",
                        (student_id, subject, topic, float(scored), float(total), int(percentage), str(mistake_types), str(notes)))
        return cur.lastrowid

def get_test_sessions(student_id, subject=None, topic=None, limit=100, order="ASC"):
    order_clause = "DESC" if str(order).upper() == "DESC" else "ASC"
    query = "SELECT * FROM test_sessions WHERE student_id=?"
    args = [student_id]
    if subject:
        query += " AND subject=?"
        args.append(subject)
    if topic:
        query += " AND topic=?"
        args.append(topic)
    query += f" ORDER BY created_at {order_clause}, id {order_clause} LIMIT ?"
    args.append(limit)
    with get_connection() as c:
        rows = c.execute(query, tuple(args)).fetchall()
        return [dict(r) for r in rows]

# ---------------------------------------------------------
# PERSISTENT TEXTBOOK SESSIONS & Q&A HISTORY
# ---------------------------------------------------------

def save_textbook_session(student_id, title, source_type, source_name, extracted_text="",
                          file_path=None, file_hash=None, file_size=0, page_count=1,
                          word_count=0, is_truncated=0, truncation_info="", **kwargs):
    """Persist a new textbook study session with extracted source text and document metadata."""
    path = file_path or kwargs.get("storage_path")
    text = extracted_text or kwargs.get("text", "")
    w_count = word_count or kwargs.get("accepted_words", 0) or kwargs.get("total_words", 0)
    trunc = is_truncated if is_truncated is not None else kwargs.get("is_truncated", 0)
    with get_connection() as c:
        cur = c.execute("""
            INSERT INTO textbook_sessions(
                student_id, title, source_type, source_name, file_path, file_hash,
                file_size, extracted_text, page_count, word_count, is_truncated, truncation_info
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            student_id, title, source_type, source_name, path, file_hash,
            int(file_size), text, int(page_count), int(w_count),
            int(bool(trunc)), str(truncation_info or "")
        ))
        return cur.lastrowid

def get_textbook_sessions(student_id, limit=50):
    """Retrieve all study sessions owned by the authenticated student."""
    with get_connection() as c:
        rows = c.execute("""
            SELECT id, student_id, title, source_type, source_name, file_path, file_hash,
                   file_size, page_count, word_count, is_truncated, truncation_info,
                   created_at, updated_at
            FROM textbook_sessions
            WHERE student_id=?
            ORDER BY updated_at DESC, id DESC LIMIT ?
        """, (student_id, limit)).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["storage_path"] = d.get("file_path")
            d["accepted_words"] = d.get("word_count", 0)
            result.append(d)
        return result

def get_textbook_session(student_id_or_session_id, session_id=None):
    """Retrieve a specific study session owned by the authenticated student."""
    with get_connection() as c:
        if session_id is not None:
            student_id, sid = student_id_or_session_id, session_id
        else:
            sid, student_id = student_id_or_session_id, None

        if student_id is not None:
            row = c.execute("SELECT * FROM textbook_sessions WHERE id=? AND student_id=?", (sid, student_id)).fetchone()
        else:
            row = c.execute("SELECT * FROM textbook_sessions WHERE id=?", (sid,)).fetchone()
        
        if not row:
            return None
        d = dict(row)
        d["storage_path"] = d.get("file_path")
        d["accepted_words"] = d.get("word_count", 0)
        return d

def delete_textbook_session(arg1, arg2=None):
    """
    Delete a study session and all associated Q&A records.
    Supports delete_textbook_session(session_id, student_id) or (student_id, session_id).
    Returns (success: bool, file_path_to_clean: str or None).
    """
    with get_connection() as c:
        if arg2 is not None:
            row = c.execute("SELECT file_path, id, student_id FROM textbook_sessions WHERE id=? AND student_id=?", (arg1, arg2)).fetchone()
            if not row:
                row = c.execute("SELECT file_path, id, student_id FROM textbook_sessions WHERE id=? AND student_id=?", (arg2, arg1)).fetchone()
        else:
            row = c.execute("SELECT file_path, id, student_id FROM textbook_sessions WHERE id=?", (arg1,)).fetchone()

        if not row:
            return False, None

        session_id = row["id"]
        student_id = row["student_id"]
        file_to_clean = row["file_path"]
        c.execute("DELETE FROM textbook_qa WHERE session_id=? AND student_id=?", (session_id, student_id))
        c.execute("DELETE FROM textbook_sessions WHERE id=? AND student_id=?", (session_id, student_id))
        return True, file_to_clean

def save_textbook_qa(session_id, student_id, question, answer, source_type="ai", relevant_excerpt="", **kwargs):
    """Persist a question and successful answer within an owned study session."""
    stype = kwargs.get("mode", source_type)
    excerpt = kwargs.get("source_excerpt", relevant_excerpt)
    with get_connection() as c:
        cur = c.execute("""
            INSERT INTO textbook_qa(session_id, student_id, question, answer, source_type, relevant_excerpt)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session_id, student_id, question, answer, stype, excerpt or ""))
        c.execute("UPDATE textbook_sessions SET updated_at=CURRENT_TIMESTAMP WHERE id=? AND student_id=?", (session_id, student_id))
        return cur.lastrowid

def get_textbook_qa(session_id, student_id):
    """Retrieve full chronological Q&A history for a specific owned study session."""
    with get_connection() as c:
        rows = c.execute("""
            SELECT id, session_id, student_id, question, answer, source_type as mode, relevant_excerpt as source_excerpt, created_at
            FROM textbook_qa
            WHERE session_id=? AND student_id=?
            ORDER BY created_at ASC, id ASC
        """, (session_id, student_id)).fetchall()
        return [dict(r) for r in rows]

def get_db_health():
    """Non-revealing database connectivity and integrity health check."""
    import time
    start = time.time()
    try:
        with get_connection() as c:
            tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            students_count = c.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        elapsed = round((time.time() - start) * 1000, 2)
        return {
            "status": "healthy",
            "engine": "sqlite",
            "tables": len(tables),
            "students": students_count,
            "latency_ms": elapsed
        }
    except Exception as exc:
        return {
            "status": "unhealthy",
            "engine": "sqlite",
            "error": type(exc).__name__
        }

# ---------------------------------------------------------
# MY 4 IMPORTANT CONCEPTS
# ---------------------------------------------------------

MAX_IMPORTANT_CONCEPTS = 4

def get_saved_concept_count(student_id: int) -> int:
    """Return the total number of important concepts saved for the authenticated student."""
    with get_connection() as c:
        row = c.execute("SELECT COUNT(*) FROM saved_concepts WHERE student_id=?", (student_id,)).fetchone()
        return row[0] if row else 0

def get_saved_concepts(student_id: int) -> list:
    """Retrieve all saved important concepts owned by the student (up to 4 items)."""
    with get_connection() as c:
        rows = c.execute("""
            SELECT id, student_id, topic, concept_name, question, notes, created_at
            FROM saved_concepts
            WHERE student_id=?
            ORDER BY created_at ASC, id ASC
        """, (student_id,)).fetchall()
        return [dict(r) for r in rows]

def save_important_concept(student_id: int, topic: str, concept_name: str, question: str, notes: str = "") -> dict:
    """
    Save an important concept for the student.
    Enforces the maximum of 4 items and prevents duplicates.
    """
    clean_topic = (topic or "").strip() or "General"
    clean_name = (concept_name or "").strip()
    clean_question = (question or "").strip()
    clean_notes = (notes or "").strip()

    if not clean_name:
        raise ValueError("Concept name is required.")
    if not clean_question:
        raise ValueError("Question is required.")

    with get_connection() as c:
        # Duplicate check first: prevent saving duplicate items with same concept name and question
        dup = c.execute(
            "SELECT id FROM saved_concepts WHERE student_id=? AND LOWER(concept_name)=LOWER(?) AND LOWER(question)=LOWER(?)",
            (student_id, clean_name, clean_question)
        ).fetchone()
        if dup:
            raise ValueError("This concept is already saved in your Important Concepts list.")

        count = c.execute("SELECT COUNT(*) FROM saved_concepts WHERE student_id=?", (student_id,)).fetchone()[0]
        if count >= MAX_IMPORTANT_CONCEPTS:
            raise ValueError("You have saved four important concepts. Delete one to add a new concept.")

        cur = c.execute(
            "INSERT INTO saved_concepts(student_id, topic, concept_name, question, notes) VALUES (?, ?, ?, ?, ?)",
            (student_id, clean_topic, clean_name, clean_question, clean_notes)
        )
        new_id = cur.lastrowid
        return dict(c.execute("SELECT * FROM saved_concepts WHERE id=?", (new_id,)).fetchone())

def delete_saved_concept(student_id: int, concept_id: int) -> bool:
    """
    Delete a specific saved concept owned by the authenticated student.
    Guarantees isolation: student A cannot delete student B's concept.
    Does NOT affect textbook sessions, Q&A records, or documents.
    """
    with get_connection() as c:
        cur = c.execute("DELETE FROM saved_concepts WHERE id=? AND student_id=?", (concept_id, student_id))
        return cur.rowcount > 0


