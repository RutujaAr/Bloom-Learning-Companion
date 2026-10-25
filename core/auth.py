import streamlit as st
import hashlib
import bcrypt
from typing import Optional, Dict, Any
from core.db import (
    create_user_account, get_student_by_username, get_student_by_owner_id,
    get_student_by_id, get_or_create_account
)


def hash_password(password: str) -> str:
    """Securely hash a password using bcrypt with salt rounds (never plaintext)."""
    if not password:
        raise ValueError("Password cannot be empty.")
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash."""
    if not password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_account(username: str, password: str, display_name: str, grade: str, email: str = "") -> Dict[str, Any]:
    """
    Register a new student account with validated unique username, hashed password, display name, and stage.
    Enforces uniqueness of usernames and displays the standard taken message if duplicate.
    """
    clean_username = (username or "").strip().lower()
    if not clean_username:
        raise ValueError("Username is required.")
    if len(clean_username) < 3:
        raise ValueError("Username must be at least 3 characters long.")
    if not password:
        raise ValueError("Password is required.")
    if len(password) < 4:
        raise ValueError("Password must be at least 4 characters long.")

    clean_display = (display_name or "Learner").strip() or "Learner"
    clean_grade = (grade or "Class 10").strip()

    # Pre-lookup before attempting creation (Requirement 2)
    existing = get_student_by_username(clean_username)
    if existing:
        raise ValueError("This username is already taken. Please choose another.")

    hashed_pw = hash_password(password)
    student = create_user_account(
        username=clean_username,
        password_hash=hashed_pw,
        display_name=clean_display,
        grade=clean_grade,
        email=email
    )
    return student


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Authenticate student credentials.
    Returns student record on successful verification, or None on failure.
    """
    clean_username = (username or "").strip().lower()
    if not clean_username or not password:
        return None

    student = get_student_by_username(clean_username)
    if not student:
        return None

    stored_hash = student.get("password_hash")
    if not stored_hash or not verify_password(password, stored_hash):
        return None

    return student


def login_session(student: Dict[str, Any]) -> None:
    """Establish authenticated student session in Streamlit session state."""
    st.session_state["auth_user"] = {
        "authenticated": True,
        "owner_id": student["owner_id"],
        "username": student["username"],
        "name": student["name"],
        "grade": student["grade"],
        "email": student.get("email", ""),
        "auth_type": "account"
    }
    st.session_state["student_id"] = student["id"]
    st.session_state["student_name"] = student["name"]
    st.session_state["grade"] = student["grade"]
    st.session_state["owner_id"] = student["owner_id"]


def is_oidc_configured() -> bool:
    """
    Check if Streamlit OpenID Connect authentication is configured
    via secrets.toml [auth] block with required client credentials.
    """
    try:
        auth_conf = st.secrets.get("auth")
        if auth_conf and isinstance(auth_conf, dict):
            return bool(auth_conf.get("client_id") and auth_conf.get("client_secret"))
    except Exception:
        pass
    return False


def get_current_user() -> Dict[str, Any]:
    """
    Retrieve currently authenticated user identity.
    Prioritizes official Streamlit OIDC (st.user), with safe local session
    profile authentication for development and offline testing.
    """
    # 1. Check Streamlit OIDC user
    try:
        user_info = getattr(st, "user", None)
        if user_info and getattr(user_info, "is_logged_in", False):
            raw_sub = user_info.get("sub") or user_info.get("email") or "oidc_user"
            stable_owner_id = f"oidc_{hashlib.sha256(raw_sub.encode('utf-8')).hexdigest()[:16]}"
            return {
                "authenticated": True,
                "owner_id": stable_owner_id,
                "name": user_info.get("name") or user_info.get("email", "Learner"),
                "email": user_info.get("email", ""),
                "auth_type": "oidc"
            }
    except Exception:
        pass

    # 2. Check Session State
    local_user = st.session_state.get("auth_user")
    if local_user and isinstance(local_user, dict) and local_user.get("authenticated"):
        return local_user

    return {
        "authenticated": False,
        "owner_id": None,
        "name": None,
        "email": None,
        "auth_type": "unauthenticated"
    }


def login_local(display_name: str = "Learner", email: str = "", owner_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Authenticate a student profile in local development mode.
    Maintained for backwards-compatibility with previous development tests.
    """
    clean_name = (display_name or "Learner").strip() or "Learner"
    clean_email = (email or "").strip()
    clean_owner = (owner_id or "").strip()
    if not clean_owner:
        key_source = clean_email.lower() if clean_email else clean_name.lower()
        clean_owner = f"usr_{hashlib.sha256(key_source.encode('utf-8')).hexdigest()[:12]}"

    student = get_student_by_owner_id(clean_owner)
    if not student:
        student = get_or_create_account(owner_id=clean_owner, display_name=clean_name, email=clean_email)

    login_session(student)
    return st.session_state["auth_user"]


def logout_user() -> None:
    """Clear session state and trigger OIDC logout if available."""
    try:
        if getattr(st, "user", None) and getattr(st.user, "is_logged_in", False):
            st.logout()
    except Exception:
        pass

    # Clear all private learner-specific session state
    keys_to_clear = [
        "auth_user", "student_id", "student_name", "grade", "owner_id", "diagnostic", "diagnostic_result",
        "practice", "practice_score", "active_recall", "recall_input_text",
        "recall_flash_message", "tb_answer", "tb_kw_results", "active_tb_session_id"
    ]
    for k in keys_to_clear:
        st.session_state.pop(k, None)
