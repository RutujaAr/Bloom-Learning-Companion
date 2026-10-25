import streamlit as st
import pandas as pd
import plotly.express as px
import hashlib
from datetime import date

from core.db import (
    init_db, get_or_create_student, get_dashboard_data, get_due_reviews,
    get_upcoming_reviews, get_completed_reviews, get_recall_sessions,
    get_previous_questions, get_attempts, save_attempt, update_mastery,
    add_review, save_test_session, get_test_sessions,
    get_or_create_account, update_student_profile, get_db_health,
    save_textbook_session, get_textbook_sessions, get_textbook_session,
    delete_textbook_session, save_textbook_qa, get_textbook_qa,
    migrate_legacy_student, connect,
    create_user_account, get_student_by_username, get_student_by_id, get_student_by_owner_id,
    save_important_concept, get_saved_concepts, get_saved_concept_count, delete_saved_concept
)
from core.auth import (
    get_current_user, login_local, logout_user, is_oidc_configured,
    create_account, authenticate_user, login_session
)
from services.storage_service import (
    save_uploaded_pdf, delete_stored_pdf, validate_pdf_bytes
)
from agents.gap_finder import run_diagnostic
from agents.paper_pattern import analyze_test
from agents.recall_loop import (
    complete_review, get_recommendations,
    generate_recall_prompt, complete_recall_session
)
from services.gemini_service import GeminiService
from services.pdf_service import (
    extract_pdf_text, find_relevant_context,
    MAX_TEXTBOOK_WORDS, count_words, enforce_word_limit, search_text_by_keywords
)
from core.learning import build_practice_set, calculate_score
from core.syllabus import get_supported_curricula, get_syllabus_context

# ---------------------------------------------------------
# PAGE SETUP & BRAND IDENTITY
# ---------------------------------------------------------

st.set_page_config(
    page_title="Bloom • AI Learning Companion",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Polished calm forest & mint theme with clear typography and spacing
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&family=Manrope:wght@500;600;700;800&display=swap');

:root {
    color-scheme: dark;
    --bg: #0f1612;
    --surface: #16221b;
    --surface2: #1e2d24;
    --border: #283a2f;
    --border-light: #364d3f;
    --border-focus: #3ca373;
    --ink: #eaf3ed;
    --label: #d2e4d8;
    --muted: #9ab1a3;
    --placeholder: #7d9687;
    --mint: #a3e7b7;
    --mint-glow: rgba(163, 231, 183, 0.15);
    --green: #257a53;
    --green-hover: #2f9466;
}

html, body, [class*="css"] {
    font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif;
}

.stApp, [data-testid="stAppViewContainer"] {
    background: var(--bg) !important;
    color: var(--ink) !important;
}

[data-testid="stHeader"] {
    background: rgba(15, 22, 18, 0.85) !important;
    backdrop-filter: blur(10px);
    border-bottom: 1px solid var(--border);
}

/* Hide Streamlit Deploy button cleanly without hiding toolbar or sidebar toggle */
[data-testid="stAppDeployButton"],
.stAppDeployButton,
button[title="Deploy this app"] {
    display: none !important;
}

.block-container {
    padding-top: 4.2rem !important;
    padding-bottom: 2.5rem !important;
    max-width: 1240px;
}

h1, h2, h3, h4 {
    font-family: 'Manrope', sans-serif !important;
    letter-spacing: -0.02em;
    color: var(--ink) !important;
}

h1 { font-size: 1.85rem !important; }
h2 { font-size: 1.4rem !important; }
h3 { font-size: 1.15rem !important; }

/* Accessible Labels & Helper Text */
label,
[data-testid="stWidgetLabel"] p,
.stWidgetLabel label,
.stSelectbox label,
.stTextInput label,
.stNumberInput label,
.stTextArea label,
.stMultiSelect label,
.stSlider label,
.stFileUploader label {
    color: var(--label) !important;
    font-size: 0.91rem !important;
    font-weight: 600 !important;
    margin-bottom: 0.25rem !important;
}

/* Sidebar styling */
[data-testid="stSidebar"],
[data-testid="stSidebar"] > div:first-child {
    background: #121c16 !important;
    border-right: 1px solid var(--border);
}

[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label {
    color: var(--muted) !important;
}

/* Polished Hero Card (never clipped) */
.hero {
    background: linear-gradient(135deg, #172a1f 0%, #1c3527 100%);
    border: 1px solid #2d4837;
    padding: 1.4rem 1.6rem;
    border-radius: 16px;
    margin-top: 0.35rem;
    margin-bottom: 1.2rem;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
}

.hero h1 {
    color: #f2f8f4 !important;
    font-size: 1.75rem !important;
    line-height: 1.25;
    margin: 0.2rem 0 0.35rem 0;
}

.hero p {
    color: #b5cbbb;
    margin: 0;
    font-size: 0.95rem;
    line-height: 1.5;
}

.eyebrow {
    text-transform: uppercase;
    letter-spacing: 0.14em;
    font-size: 0.72rem;
    font-weight: 700;
    color: var(--mint);
    margin-bottom: 0.3rem;
    display: inline-block;
}

/* Metrics and Panels */
.panel {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 1rem 1.15rem;
    margin-bottom: 0.75rem;
}

.metric-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 0.9rem 1.05rem;
    min-height: 90px;
}

.metric-label {
    color: var(--muted);
    font-size: 0.8rem;
    font-weight: 600;
    margin-bottom: 0.2rem;
}

.metric-value {
    color: var(--mint);
    font-size: 1.65rem;
    font-weight: 800;
    font-family: 'Manrope', sans-serif;
    line-height: 1.15;
}

.metric-note {
    color: #8fa697;
    font-size: 0.74rem;
    margin-top: 0.25rem;
}

/* Interactive components & buttons */
div.stButton > button {
    border-radius: 10px;
    border: 1px solid #364d3f;
    background: #1c2a21;
    color: #eaf3ed;
    font-weight: 600;
    transition: all 0.15s ease-in-out;
}

div.stButton > button:hover {
    background: #23352a;
    border-color: #496855;
    color: #ffffff;
}

div.stButton > button[kind="primary"],
div[data-testid="stFormSubmitButton"] button[kind="primary"] {
    background: var(--green) !important;
    border-color: var(--green) !important;
    color: #ffffff !important;
    box-shadow: 0 2px 8px rgba(37, 122, 83, 0.3);
}

div.stButton > button[kind="primary"]:hover,
div[data-testid="stFormSubmitButton"] button[kind="primary"]:hover {
    background: var(--green-hover) !important;
    border-color: var(--green-hover) !important;
}

/* Form Inputs, Text Areas, Number Inputs */
.stTextInput input,
.stTextArea textarea,
.stNumberInput input,
div[data-baseweb="input"],
div[data-baseweb="base-input"] {
    background: #16221b !important;
    color: #eaf3ed !important;
    border-color: #283a2f !important;
    border-radius: 10px !important;
}

.stTextInput input:focus,
.stTextArea textarea:focus,
.stNumberInput input:focus,
div[data-baseweb="input"]:focus-within {
    border-color: #3ca373 !important;
    box-shadow: 0 0 0 1px #3ca373 !important;
}

/* Number input stepper controls (+ and -) */
div[data-testid="stNumberInput"] button {
    background: #1c2a21 !important;
    border: 1px solid #283a2f !important;
    color: #a3e7b7 !important;
}

div[data-testid="stNumberInput"] button:hover {
    background: #25392d !important;
    border-color: #3ca373 !important;
    color: #ffffff !important;
}

div[data-testid="stNumberInput"] button svg {
    fill: #a3e7b7 !important;
}

/* Readable Placeholders */
input::placeholder,
textarea::placeholder {
    color: #7d9687 !important;
    opacity: 1 !important;
}

/* Selectbox Closed State */
div[data-baseweb="select"],
div[data-baseweb="select"] > div {
    background: #16221b !important;
    color: #eaf3ed !important;
    border-color: #283a2f !important;
    border-radius: 10px !important;
}

div[data-baseweb="select"] span,
div[data-baseweb="select"] div {
    color: #eaf3ed !important;
}

div[data-baseweb="select"] svg {
    fill: #a3e7b7 !important;
}

div[data-baseweb="select"]:focus-within > div {
    border-color: #3ca373 !important;
    box-shadow: 0 0 0 1px #3ca373 !important;
}

/* Dropdown Menu Portal Popover (Open State) */
div[data-baseweb="popover"],
div[data-baseweb="popover"] > div,
div[data-baseweb="menu"],
ul[role="listbox"] {
    background: #16221b !important;
    color: #eaf3ed !important;
    border: 1px solid #2f4537 !important;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5) !important;
    border-radius: 10px !important;
}

li[role="option"],
div[data-baseweb="option"] {
    background: #16221b !important;
    color: #eaf3ed !important;
    padding: 8px 12px !important;
}

li[role="option"]:hover,
div[data-baseweb="option"]:hover,
li[aria-selected="true"],
div[data-baseweb="option"][aria-selected="true"] {
    background: #22372a !important;
    color: #a3e7b7 !important;
    font-weight: 600 !important;
}

/* Multiselect Chips / Tags (No bright red!) */
[data-baseweb="tag"] {
    background: #1c3829 !important;
    border: 1px solid #365e44 !important;
    border-radius: 8px !important;
    padding: 2px 8px !important;
}

[data-baseweb="tag"] span {
    color: #a3e7b7 !important;
    font-weight: 600 !important;
}

[data-baseweb="tag"] svg,
[data-baseweb="tag"] [role="presentation"] {
    fill: #a3e7b7 !important;
    stroke: #a3e7b7 !important;
    cursor: pointer;
}

[data-baseweb="tag"]:hover {
    background: #234734 !important;
    border-color: #437354 !important;
}

/* High-Contrast Alert Banners */
div[data-testid="stAlert"] {
    border-radius: 12px !important;
    padding: 0.9rem 1.15rem !important;
}

div[data-testid="stAlert"] p,
div[data-testid="stAlert"] span,
div[data-testid="stAlert"] div {
    font-size: 0.93rem !important;
    line-height: 1.5 !important;
}

/* INFO Banner (e.g. Spaced Reviews notice) */
div[data-testid="stAlert"]:has([data-testid="stNotificationContentInfo"]),
div[data-testid="stAlert"]:has(svg[data-testid="stIconInfo"]) {
    background: #14251b !important;
    border: 1px solid #285438 !important;
    color: #eaf3ed !important;
}

div[data-testid="stAlert"]:has([data-testid="stNotificationContentInfo"]) p,
div[data-testid="stAlert"]:has(svg[data-testid="stIconInfo"]) p {
    color: #eaf3ed !important;
}

div[data-testid="stAlert"]:has([data-testid="stNotificationContentInfo"]) svg,
div[data-testid="stAlert"]:has(svg[data-testid="stIconInfo"]) svg {
    fill: #a3e7b7 !important;
}

/* SUCCESS Banner */
div[data-testid="stAlert"]:has([data-testid="stNotificationContentSuccess"]),
div[data-testid="stAlert"]:has(svg[data-testid="stIconSuccess"]) {
    background: #14281c !important;
    border: 1px solid #2f7a4a !important;
    color: #eaf3ed !important;
}

div[data-testid="stAlert"]:has([data-testid="stNotificationContentSuccess"]) p,
div[data-testid="stAlert"]:has(svg[data-testid="stIconSuccess"]) p {
    color: #eaf3ed !important;
}

div[data-testid="stAlert"]:has([data-testid="stNotificationContentSuccess"]) svg,
div[data-testid="stAlert"]:has(svg[data-testid="stIconSuccess"]) svg {
    fill: #6ae49c !important;
}

/* WARNING Banner (Subtle amber) */
div[data-testid="stAlert"]:has([data-testid="stNotificationContentWarning"]),
div[data-testid="stAlert"]:has(svg[data-testid="stIconWarning"]) {
    background: #251e12 !important;
    border: 1px solid #5e461f !important;
    color: #f7dfa5 !important;
}

div[data-testid="stAlert"]:has([data-testid="stNotificationContentWarning"]) p,
div[data-testid="stAlert"]:has(svg[data-testid="stIconWarning"]) p {
    color: #f7dfa5 !important;
}

div[data-testid="stAlert"]:has([data-testid="stNotificationContentWarning"]) svg,
div[data-testid="stAlert"]:has(svg[data-testid="stIconWarning"]) svg {
    fill: #f5c869 !important;
}

/* ERROR Banner (Muted coral) */
div[data-testid="stAlert"]:has([data-testid="stNotificationContentError"]),
div[data-testid="stAlert"]:has(svg[data-testid="stIconError"]) {
    background: #2a1515 !important;
    border: 1px solid #6b2d2d !important;
    color: #f7baba !important;
}

div[data-testid="stAlert"]:has([data-testid="stNotificationContentError"]) p,
div[data-testid="stAlert"]:has(svg[data-testid="stIconError"]) p {
    color: #f7baba !important;
}

div[data-testid="stAlert"]:has([data-testid="stNotificationContentError"]) svg,
div[data-testid="stAlert"]:has(svg[data-testid="stIconError"]) svg {
    fill: #e87a7a !important;
}

/* Radio buttons & Checkboxes */
.stRadio label,
.stCheckbox label {
    color: #eaf3ed !important;
    font-size: 0.92rem !important;
}

/* Expanders */
[data-testid="stExpander"] {
    background: #142018 !important;
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
}

[data-testid="stExpander"] summary {
    color: var(--label) !important;
    font-weight: 600 !important;
}

[data-testid="stExpander"] summary:hover {
    color: var(--mint) !important;
}

/* File Uploader */
[data-testid="stFileUploader"] section {
    background: #142018 !important;
    border: 1px dashed #36503e !important;
    border-radius: 12px !important;
}

[data-testid="stFileUploader"] section:hover {
    border-color: #3ca373 !important;
}

[data-testid="stFileUploader"] button {
    background: #1e3025 !important;
    border: 1px solid #36503e !important;
    color: #eaf3ed !important;
}

/* Dataframe and Tables */
[data-testid="stDataFrame"],
div[data-testid="stTable"] {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
}

.small-muted {
    color: var(--muted) !important;
    font-size: 0.86rem;
}

/* Captions and Small explanatory text - high contrast WCAG AA compliant */
[data-testid="stCaptionContainer"],
.stCaption,
[data-testid="stCaptionContainer"] p,
small,
.caption-text {
    color: #b5cbbb !important;
    font-size: 0.87rem !important;
    line-height: 1.45 !important;
}

/* Spinner and loading text */
[data-testid="stSpinner"],
[data-testid="stSpinner"] > div,
.stSpinner > div > div {
    color: #eaf3ed !important;
}

/* Tooltip and help popover text */
[data-testid="stTooltipContent"],
div[role="tooltip"] {
    background: #1c2a21 !important;
    color: #eaf3ed !important;
    border: 1px solid #364d3f !important;
    border-radius: 8px !important;
}

/* Disabled controls */
button:disabled,
input:disabled,
textarea:disabled {
    background: #152019 !important;
    color: #6d8274 !important;
    border-color: #233428 !important;
    cursor: not-allowed !important;
}

hr { border-color: var(--border) !important; margin: 1.25rem 0; }
footer { visibility: hidden; }

@media (max-width: 800px) {
    .block-container { padding-top: 3.5rem !important; }
    .hero { padding: 1.1rem; }
    .hero h1 { font-size: 1.45rem !important; }
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# INITIALIZATION & PERSISTENCE
# ---------------------------------------------------------

init_db()

# Navigation pages list
NAV_PAGES = [
    "Overview",
    "Find my gaps",
    "Marks analysis",
    "Recall & revision",
    "Textbook helper",
    "My progress"
]

if "nav_page" not in st.session_state:
    st.session_state["nav_page"] = "Overview"

if "sidebar_radio" not in st.session_state:
    st.session_state["sidebar_radio"] = st.session_state["nav_page"]

def set_nav_page(target):
    """Reliably navigate to a page by setting the radio widget key before rendering."""
    st.session_state["sidebar_radio"] = target
    st.session_state["nav_page"] = target

def on_sidebar_nav():
    st.session_state["nav_page"] = st.session_state["sidebar_radio"]

# ---------------------------------------------------------
# AUTHENTICATION & ACCESS CONTROL
# ---------------------------------------------------------

auth_user = get_current_user()

if not auth_user.get("authenticated"):
    st.markdown("""
    <div class="hero" style="margin-top:0.8rem">
        <span class="eyebrow">WELCOME TO BLOOM 🌱</span>
        <h1>Your Personalised AI Learning Companion</h1>
        <p>Master complex topics, diagnose reasoning misconceptions, and retain knowledge with spaced revision.</p>
    </div>
    """, unsafe_allow_html=True)

    sign_col1, sign_col2 = st.columns([1.2, 1])

    with sign_col1:
        st.markdown("### Access Your Learning Space")

        if is_oidc_configured():
            st.markdown("""
            <div class="panel" style="margin-bottom:12px">
                <div style="font-weight:600;color:#eaf3ed;margin-bottom:4px">Institutional / Google Sign-In</div>
                <div class="small-muted">Log in using your verified OpenID Connect account.</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Sign in with Google / OIDC 🔑", type="primary", use_container_width=True):
                st.login("google")
            st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

        tab_login, tab_register = st.tabs(["🔑 Log In", "✨ Create Account"])

        with tab_login:
            with st.form("student_login_form"):
                st.markdown("#### Log In to Existing Account")
                l_user = st.text_input("Username", placeholder="e.g. rutuja", max_chars=40, key="login_username_input")
                l_pass = st.text_input("Password", type="password", placeholder="Enter your password", key="login_password_input")
                submit_login = st.form_submit_button("Log In 🔑", type="primary", use_container_width=True)

                if submit_login:
                    clean_u = l_user.strip()
                    if not clean_u or not l_pass:
                        st.warning("Please enter both username and password.")
                    else:
                        try:
                            student = authenticate_user(clean_u, l_pass)
                            if student:
                                login_session(student)
                                st.success(f"Welcome back, {student['name']}!")
                                st.rerun()
                            else:
                                st.error("Invalid username or password. Please try again.")
                        except Exception as exc:
                            import logging
                            logging.error(f"Login failure: {exc}")
                            st.error("Unable to log in at this time. Please try again.")

        with tab_register:
            with st.form("student_register_form"):
                st.markdown("#### Create New Student Account")
                r_user = st.text_input("Username", placeholder="Choose a unique username (e.g. rutuja_2)", max_chars=40, key="reg_username_input")
                r_pass = st.text_input("Password", type="password", placeholder="Choose a secure password (min 4 characters)", key="reg_password_input")
                r_name = st.text_input("Display Name", placeholder="e.g. Rutuja", max_chars=40, key="reg_display_input")
                r_stage = st.selectbox("Stage / Grade", ["Class 10", "Class 12", "College", "Research / PhD"], index=2, key="reg_stage_input")
                r_email = st.text_input("Email (Optional)", placeholder="e.g. rutuja@example.edu", max_chars=80, key="reg_email_input")
                submit_reg = st.form_submit_button("Create Account ✨", type="primary", use_container_width=True)

                if submit_reg:
                    clean_ru = r_user.strip()
                    clean_rn = r_name.strip()
                    if not clean_ru:
                        st.warning("Please choose a unique username.")
                    elif not r_pass:
                        st.warning("Please choose a password.")
                    elif not clean_rn:
                        st.warning("Please enter your display name.")
                    else:
                        try:
                            new_student = create_account(
                                username=clean_ru,
                                password=r_pass,
                                display_name=clean_rn,
                                grade=r_stage,
                                email=r_email.strip()
                            )
                            login_session(new_student)
                            st.success(f"Account created! Welcome to Bloom, {new_student['name']}!")
                            st.rerun()
                        except ValueError as ve:
                            st.error(str(ve))
                        except Exception as exc:
                            import logging
                            logging.error(f"Account creation failure: {exc}")
                            st.error("Unable to create account at this time. Please try again.")

    with sign_col2:
        st.markdown("### 🔒 Student Data Privacy & Isolation")
        st.markdown("""
        <div class="panel">
            <h4 style="margin:0 0 0.4rem 0;color:#eaf3ed">Private & Isolated Learning Records</h4>
            <p class="small-muted" style="margin-bottom:0.6rem">
                Every learning record in Bloom is strictly isolated to your authenticated account ID:
            </p>
            <ul class="small-muted" style="padding-left:1.2rem;margin:0 0 0.8rem 0">
                <li><b>Grounded Mastery:</b> Diagnostic results and mistake patterns are private to your account.</li>
                <li><b>Textbook Sessions:</b> Uploaded PDFs, Q&A history, and My 4 Important Concepts are private to you.</li>
                <li><b>Spaced Revision:</b> Recall intervals adapt exclusively to your personal memory decay.</li>
            </ul>
            <p class="small-muted" style="margin:0">
                Multiple students can share the same display name. Accounts are securely isolated by unique username and stable internal account ID.
            </p>
        </div>
        """, unsafe_allow_html=True)

    st.stop()

# Authenticated student account retrieval
student_rec = None
if st.session_state.get("student_id"):
    student_rec = get_student_by_id(st.session_state["student_id"])
if not student_rec and auth_user.get("owner_id"):
    student_rec = get_student_by_owner_id(auth_user["owner_id"])
if not student_rec and auth_user.get("username"):
    student_rec = get_student_by_username(auth_user["username"])
if not student_rec:
    student_rec = get_or_create_account(
        owner_id=auth_user.get("owner_id") or "local_dev_learner",
        display_name=auth_user.get("name", "Learner"),
        email=auth_user.get("email"),
        grade=st.session_state.get("grade", "College")
    )

student_id = student_rec["id"]
st.session_state["student_id"] = student_id
st.session_state["student_name"] = student_rec["name"]
st.session_state["owner_id"] = student_rec["owner_id"]
current_grade = student_rec["grade"]

with st.sidebar:
    # Original Bloom Identity: Abstract Blooming Leaf & Book SVG Logo
    st.markdown("""
    <div style="display:flex;align-items:center;gap:12px;margin:0.2rem 0 0.4rem 0">
        <svg width="40" height="40" viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect width="36" height="36" rx="10" fill="#18261e" stroke="#2a4032" stroke-width="1.2"/>
            <path d="M18 12C14.5 12 11.5 14 10 17V27C11.5 25 14.5 24 18 24C21.5 24 24.5 25 26 27V17C24.5 14 21.5 12 18 12Z" fill="#224c36" stroke="#489167" stroke-width="1.4" stroke-linejoin="round"/>
            <path d="M18 24V12" stroke="#a3e7b7" stroke-width="1.4" stroke-linecap="round"/>
            <path d="M18 12C18 8.5 21 6.5 24.5 6.5C24.5 9.5 22 12 18 12Z" fill="#a3e7b7"/>
            <path d="M18 12C18 8.5 15 6.5 11.5 6.5C11.5 9.5 14 12 18 12Z" fill="#58a679"/>
        </svg>
        <div>
            <div style="font-family:'Manrope',sans-serif;font-weight:800;font-size:1.4rem;color:#eaf3ed;line-height:1.15">Bloom</div>
            <div style="font-size:0.75rem;color:#9ab1a3;font-weight:500">AI Learning Companion</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    st.markdown(f"""
    <div class="panel" style="padding:0.7rem 0.9rem;margin-bottom:0.5rem">
        <div style="display:flex;align-items:center;justify-content:space-between">
            <span style="font-weight:700;color:#eaf3ed;font-size:0.95rem">👤 {student_rec['name']}</span>
            <span style="font-size:0.75rem;color:#a3e7b7;background:#182e22;padding:2px 6px;border-radius:4px">{student_rec['grade']}</span>
        </div>
        <div style="font-size:0.76rem;color:#a3e7b7;margin-top:3px">@{student_rec.get('username', 'learner')}</div>
        <div style="font-size:0.72rem;color:#8fa697;margin-top:2px;word-break:break-all">ID: {student_rec['owner_id'][:20]}...</div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("✏️ Edit Profile", expanded=False):
        new_name = st.text_input("Display Name", value=student_rec["name"], max_chars=40, key="edit_profile_name")
        grade_options = ["Class 10", "Class 12", "College", "Research / PhD"]
        new_grade = st.selectbox(
            "Stage",
            grade_options,
            index=grade_options.index(student_rec["grade"]) if student_rec["grade"] in grade_options else 2,
            key="edit_profile_grade"
        )
        if st.button("Save Profile Changes", key="save_profile_btn", use_container_width=True):
            if new_name.strip():
                update_student_profile(student_id, auth_user["owner_id"], display_name=new_name.strip(), grade=new_grade)
                st.session_state["student_name"] = new_name.strip()
                st.session_state["grade"] = new_grade
                st.success("Profile updated.")
                st.rerun()

        # Check if legacy learner record exists to optionally claim
        try:
            with connect() as conn:
                legacy = conn.execute(
                    "SELECT id FROM students WHERE (owner_id IS NULL OR owner_id = 'legacy:learner') AND id != ?",
                    (student_id,)
                ).fetchone()
                if legacy:
                    st.divider()
                    st.caption("Found previous unattached Learner data.")
                    if st.button("Claim Legacy Learner Data", key="claim_legacy_btn"):
                        migrate_legacy_student(legacy["id"], auth_user["owner_id"])
                        st.success("Legacy data claimed!")
                        st.rerun()
        except Exception:
            pass

    curricula_list = get_supported_curricula()
    current_curriculum = st.selectbox(
        "Curriculum / Board",
        curricula_list,
        index=st.session_state.get("curriculum_index", 0),
        help="Select your educational board to ground question generation in verified syllabi."
    )
    st.session_state["curriculum_index"] = curricula_list.index(current_curriculum)
    st.session_state["curriculum"] = current_curriculum

    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    # Sidebar Navigation synchronized with programmatic jumps
    page = st.radio(
        "EXPLORE",
        NAV_PAGES,
        key="sidebar_radio",
        on_change=on_sidebar_nav
    )
    st.session_state["nav_page"] = page

    st.divider()

    if st.button("Sign Out 🚪", use_container_width=True):
        logout_user()
        st.rerun()

    if st.button("Refresh Workspace", use_container_width=True):
        st.rerun()

gemini = GeminiService()

# ---------------------------------------------------------
# REUSABLE UI HELPERS
# ---------------------------------------------------------

def render_hero(title, subtitle, eyebrow="YOUR LEARNING SPACE"):
    st.markdown(
        f"""
        <div class="hero">
            <span class="eyebrow">{eyebrow}</span>
            <h1>{title}</h1>
            <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True
    )

def render_metric(label, value, note=""):
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-note">{note}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

# ---------------------------------------------------------
# SECTION 1: OVERVIEW
# ---------------------------------------------------------

if page == "Overview":
    data = get_dashboard_data(student_id)
    has_activity = bool(data.get("attempts", 0) or data.get("topics", 0) or data.get("tests", 0))

    greeting = f"Welcome back, {st.session_state['student_name']}" if has_activity else f"Welcome to Bloom, {st.session_state['student_name']}"

    render_hero(
        greeting,
        "Find what you missed. Practise what matters. Remember it longer.",
        "YOUR NEXT SMALL WIN"
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_metric("Topics Explored", data["topics"], "Across tests & diagnostics")
    with c2:
        render_metric("Questions Solved", data["attempts"], "Recorded practice attempts")
    with c3:
        render_metric("Reviews Due", data["due"], "Spaced revision items")
    with c4:
        render_metric("Average Accuracy", f"{data['accuracy']}%", "Overall recorded score")

    st.write("")

    left, right = st.columns([1.2, 1])

    with left:
        st.markdown("### Next Steps")
        st.markdown("""
        <div class="panel">
            <h4 style="margin:0 0 0.35rem 0;color:#eaf3ed">Start a 5-minute Diagnostic</h4>
            <p class="small-muted" style="margin:0">
                Answer a few targeted questions to pinpoint where understanding breaks down,
                then practise only the missing concepts.
            </p>
        </div>
        """, unsafe_allow_html=True)

        st.button(
            "Start Diagnostic Assessment",
            type="primary",
            use_container_width=True,
            on_click=set_nav_page,
            args=("Find my gaps",)
        )

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        st.markdown("### 🗓️ Upcoming Spaced Reviews")

        due = get_due_reviews(student_id, limit=4)
        if due:
            for rev in due:
                st.markdown(
                    f"""
                    <div class="panel" style="padding:0.75rem 1rem;margin-bottom:0.5rem">
                        <div style="font-weight:600;color:#eaf3ed">{rev['topic']}</div>
                        <div class="small-muted">{rev['subject']} · Due: <b>{rev['due_date']}</b> · {rev['reason']}</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
        else:
            if data.get("upcoming", 0) > 0:
                st.info(f"✨ No reviews due today! You have {data['upcoming']} upcoming review(s) scheduled for future dates.")
            else:
                st.info("No reviews due today! You're caught up. Complete a diagnostic to schedule your next revision.")

    with right:
        st.markdown("### Recent Activity")
        attempts = get_attempts(student_id, limit=60)

        if attempts:
            df = pd.DataFrame(attempts)
            df["parsed_dt"] = pd.to_datetime(df["created_at"], errors="coerce")
            df_valid = df.dropna(subset=["parsed_dt"])

            if not df_valid.empty:
                df_valid["date_str"] = df_valid["parsed_dt"].dt.strftime("%Y-%m-%d")
                df_valid["display_date"] = df_valid["parsed_dt"].dt.strftime("%b %d")
                daily = df_valid.groupby(["date_str", "display_date"], as_index=False).agg(Questions=("id", "count"))
                daily = daily.sort_values("date_str")

                fig = px.bar(
                    daily,
                    x="display_date",
                    y="Questions",
                    color_discrete_sequence=["#3ca373"]
                )
                fig.update_layout(
                    title=dict(
                        text="Daily Learning Activity",
                        font=dict(family="Manrope", size=14, color="#eaf3ed")
                    ),
                    margin=dict(l=10, r=10, t=35, b=10),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font_color="#b5cbbb",
                    xaxis_title="",
                    yaxis_title="Questions Attempted",
                    xaxis=dict(
                        type="category",
                        gridcolor="#283a2f",
                        tickfont=dict(color="#b5cbbb", size=11)
                    ),
                    yaxis=dict(
                        gridcolor="#283a2f",
                        dtick=1,
                        rangemode="tozero",
                        tickfont=dict(color="#b5cbbb", size=11)
                    )
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.markdown("""
                <div class="panel">
                    <h4 style="margin:0 0 0.3rem 0;color:#eaf3ed">Daily Learning Activity</h4>
                    <p class="small-muted" style="margin:0">
                        No attempts recorded yet. Your learning activity will appear here after your first practice or diagnostic.
                    </p>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="panel">
                <h4 style="margin:0 0 0.3rem 0;color:#eaf3ed">Daily Learning Activity</h4>
                <p class="small-muted" style="margin:0">
                    No attempts recorded yet. Your learning activity will appear here after your first practice or diagnostic.
                </p>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    with st.expander("ℹ️ About Bloom & Educational Disclaimer", expanded=False):
        st.markdown("""
        **Bloom** is a learning-support tool designed to help you practise, identify misconceptions, and organise spaced revision.
        - **Learning Improvement:** Improvement is not guaranteed or instantaneous; learning outcomes depend on individual effort, consistency, and active engagement with concepts.
        - **Answer Verification:** AI-generated and algorithmic questions, answers, and explanations can occasionally contain errors or misinterpretations. Always check and verify important answers against your textbooks, teachers, or trusted educational sources.
        - **Syllabus Alignment:** Syllabus grounding depends on the board curriculum information and official source versions currently available in Bloom's knowledge base or provided by the learner.
        - **Learner Responsibility:** The learner remains responsible for verifying important facts, mastering the material, and preparing for official examinations. Bloom is an assistive companion, not a substitute for accredited teaching or assessment bodies.
        """)

# ---------------------------------------------------------
# SECTION 2: FIND MY GAPS (GAPFINDER)
# ---------------------------------------------------------

elif page == "Find my gaps":
    render_hero(
        "Find the gap, not just the answer.",
        "A short diagnostic isolates the exact reasoning step that needs attention.",
        "GAPFINDER"
    )

    col1, col2 = st.columns([1, 1])

    with col1:
        subject = st.selectbox(
            "Subject",
            ["Mathematics", "Science", "Physics", "Chemistry", "Biology", "English", "Computer Science", "Other"],
            key="gap_subject"
        )
        topic = st.text_input(
            "Topic you want to diagnose",
            placeholder="e.g. Linear equations, Photosynthesis, Organic reactions",
            key="gap_topic"
        )
        level = st.selectbox(
            "Difficulty Level",
            ["Foundation", "Standard", "Challenge"],
            index=1,
            key="gap_level"
        )
        count = st.slider("Number of Questions", min_value=3, max_value=10, value=5, step=1, key="gap_count")

        clean_topic = topic.strip()
        syl_ctx = get_syllabus_context(current_grade, current_curriculum, subject, clean_topic) if clean_topic else {"verified": False}
        if clean_topic:
            if syl_ctx.get("verified"):
                st.markdown(f"""
                <div style="background:#132219;border:1px solid #285438;border-radius:8px;padding:6px 10px;margin-bottom:8px">
                    <span style="color:#a3e7b7;font-weight:600;font-size:0.8rem">📘 VERIFIED SYLLABUS:</span>
                    <span style="color:#eaf3ed;font-size:0.8rem">Questions are grounded in official verified syllabus: {syl_ctx['curriculum']} · Unit: {syl_ctx.get('chapters') or syl_ctx.get('unit')}</span>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div style="background:#1c241e;border:1px solid #2f3e34;border-radius:8px;padding:6px 10px;margin-bottom:8px">
                    <span style="color:#9ab1a3;font-weight:600;font-size:0.8rem">ℹ️ TOPIC SCOPE:</span>
                    <span style="color:#d2e4d8;font-size:0.8rem">Questions are generated from the selected topic and are not verified against a specific syllabus.</span>
                </div>
                """, unsafe_allow_html=True)

        if st.button("Generate Diagnostic Assessment", type="primary", use_container_width=True):
            if not clean_topic:
                st.warning("Please enter a topic name before starting.")
            else:
                with st.spinner("Preparing your diagnostic questions…"):
                    prev_qs = get_previous_questions(student_id, clean_topic, limit=50)
                    questions, source = run_diagnostic(
                        gemini,
                        subject,
                        clean_topic,
                        level=level,
                        count=count,
                        stage=current_grade,
                        curriculum=current_curriculum,
                        previous_questions=prev_qs
                    )

                st.session_state["diagnostic"] = {
                    "stage": current_grade,
                    "curriculum": current_curriculum,
                    "subject": subject,
                    "topic": clean_topic,
                    "level": level,
                    "count": count,
                    "questions": questions,
                    "source": source
                }
                st.session_state.pop("diagnostic_submitted", None)
                st.session_state.pop("diagnostic_result", None)
                st.session_state.pop("practice", None)
                st.session_state.pop("practice_score", None)
                st.rerun()

        if clean_topic and syl_ctx.get("verified"):
            scope_caption = "Questions are grounded in official verified syllabus learning outcomes."
        else:
            scope_caption = "Questions are generated from the selected topic and are not verified against a specific syllabus."

        st.markdown(
            f"<p class='caption-text' style='color:#b5cbbb;font-size:0.87rem;margin-top:8px;line-height:1.45;'>{scope_caption}</p>",
            unsafe_allow_html=True
        )

    with col2:
        st.markdown("""
        <div class="panel">
            <h4 style="margin:0 0 0.35rem 0;color:#eaf3ed">Diagnostic Protocol</h4>
            <p class="small-muted" style="margin-bottom:0.4rem">1. Answer questions without consulting external notes.</p>
            <p class="small-muted" style="margin-bottom:0.4rem">2. Bloom classifies incorrect reasoning into specific patterns (conceptual, misread, calculation, recall).</p>
            <p class="small-muted" style="margin:0">3. Get a customized targeted practice set and scheduled spaced revision.</p>
        </div>
        """, unsafe_allow_html=True)

    diagnostic = st.session_state.get("diagnostic")

    # If the student changed the topic in the input field, bypass and invalidate incompatible cached diagnostic
    if diagnostic and clean_topic and diagnostic.get("topic", "").strip().lower() != clean_topic.lower():
        diagnostic = None
        st.session_state.pop("diagnostic", None)
        st.session_state.pop("diagnostic_submitted", None)
        st.session_state.pop("diagnostic_result", None)

    if diagnostic:
        st.divider()
        if not diagnostic.get("questions"):
            friendly_err = diagnostic.get("source") or "We couldn't prepare verified questions for this topic right now. Please try again."
            st.warning(f"⚠️ {friendly_err}")
            if st.button("🔄 Try Again", key="retry_diag_btn"):
                st.session_state.pop("diagnostic", None)
                st.rerun()
        else:
            st.markdown(f"### Diagnostic: {diagnostic['topic']}")
            st.caption(f"Subject: {diagnostic['subject']} · Status: {diagnostic['source']}")

            with st.form("diagnostic_quiz_form"):
                answers = {}
                for i, q in enumerate(diagnostic["questions"], 1):
                    st.markdown(f"**{i}. {q['prompt']}**")
                    # Use index=None so answers are not pre-selected
                    answers[q["id"]] = st.radio(
                        f"Choose an option for question {i}:",
                        q["options"],
                        index=None,
                        key=f"diag_{q['id']}",
                        label_visibility="collapsed"
                    )
                    if q.get("hint"):
                        with st.expander("Need a hint?"):
                            st.write(q["hint"])
                    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

                submitted = st.form_submit_button("Submit Diagnostic", type="primary", use_container_width=True)

            if submitted:
                if st.session_state.get("diagnostic_submitted"):
                    st.info("This diagnostic assessment has already been submitted and recorded.")
                else:
                    # Check for unselected questions
                    unanswered = [i for i, q in enumerate(diagnostic["questions"], 1) if answers.get(q["id"]) is None]
                    if unanswered:
                        st.warning(f"Please answer all questions before submitting. Unanswered: {', '.join(map(str, unanswered))}")
                    else:
                        st.session_state["diagnostic_submitted"] = True
                        results = []
                for q in diagnostic["questions"]:
                    ans = answers.get(q["id"], "")
                    is_correct = (str(ans).strip().lower() == str(q["answer"]).strip().lower())
                    results.append({
                        "question": q,
                        "answer": ans,
                        "correct": is_correct
                    })
                    save_attempt(
                        student_id,
                        diagnostic["subject"],
                        diagnostic["topic"],
                        q["prompt"],
                        ans,
                        q["answer"],
                        is_correct,
                        q.get("mistake_type", "conceptual"),
                        mode="diagnostic"
                    )

                score = calculate_score(results)
                analysis = analyze_test(gemini, results, diagnostic["subject"], diagnostic["topic"])

                # Update mastery for each mistake pattern
                for mistake in analysis.get("mistakes", []):
                    update_mastery(
                        student_id,
                        diagnostic["subject"],
                        diagnostic["topic"],
                        mistake["type"],
                        mistake["count"],
                        score
                    )

                # Schedule spaced revision (1 day if score < 60, otherwise 3 days)
                review_days = 1 if score < 60 else 3
                add_review(
                    student_id,
                    diagnostic["subject"],
                    diagnostic["topic"],
                    days=review_days,
                    reason=f"Diagnostic result: {score}%"
                )

                st.session_state["diagnostic_result"] = {
                    "results": results,
                    "score": score,
                    "analysis": analysis
                }
                st.rerun()

    result = st.session_state.get("diagnostic_result")

    if result:
        st.divider()
        st.markdown("### Diagnostic Evaluation")

        r1, r2 = st.columns([1, 2])
        with r1:
            render_metric("Diagnostic Score", f"{result['score']}%", "Assessment accuracy")
            st.progress(result["score"] / 100)
        with r2:
            st.markdown("**Identified Gaps & Next Steps**")
            st.write(result["analysis"]["summary"])
            for m in result["analysis"]["mistakes"]:
                st.markdown(f"- **{m['label']}** ({m['count']} error{'s' if m['count'] > 1 else ''}): {m['recommendation']}")

        with st.expander("Detailed Answer Explanations", expanded=False):
            for item in result["results"]:
                icon = "✅" if item["correct"] else "❌"
                st.markdown(f"**{icon} {item['question']['prompt']}**")
                st.caption(f"Your answer: **{item['answer']}** | Expected: **{item['question']['answer']}**")
                st.write(item["question"].get("explanation", "Review core definitions for this topic."))
                st.markdown("---")

        if st.button("Generate Targeted Practice", type="primary"):
            with st.spinner("Generating targeted practice questions for your weak areas..."):
                st.session_state["practice"] = build_practice_set(
                    diagnostic["subject"],
                    diagnostic["topic"],
                    result["analysis"],
                    gemini=gemini
                )
            st.session_state["practice_meta"] = {
                "subject": diagnostic["subject"],
                "topic": diagnostic["topic"]
            }
            st.session_state.pop("practice_score", None)
            st.rerun()

    practice = st.session_state.get("practice")

    if practice:
        st.divider()
        st.markdown("### 🎯 Targeted Practice")
        st.caption("Practice questions specifically focus on the mistake patterns detected above.")

        # If practice has already been submitted, show score and clear button
        if "practice_score" in st.session_state:
            st.success(f"Practice Completed! Score: **{st.session_state['practice_score']}%**. Results saved to your progress history.")
            if st.button("Clear Practice Session"):
                st.session_state.pop("practice", None)
                st.session_state.pop("practice_score", None)
                st.rerun()
        else:
            with st.form("practice_quiz_form"):
                prac_answers = {}
                for i, pq in enumerate(practice, 1):
                    st.markdown(f"**{i}. {pq['prompt']}**")
                    prac_answers[pq["id"]] = st.radio(
                        f"Practice choice {i}:",
                        pq["options"],
                        index=None,
                        key=f"prac_{pq['id']}",
                        label_visibility="collapsed"
                    )
                p_submit = st.form_submit_button("Check Practice Answers", type="primary")

            if p_submit:
                p_unanswered = [i for i, pq in enumerate(practice, 1) if prac_answers.get(pq["id"]) is None]
                if p_unanswered:
                    st.warning(f"Please answer all practice questions. Unanswered: {', '.join(map(str, p_unanswered))}")
                else:
                    correct_count = 0
                    meta = st.session_state["practice_meta"]
                    for pq in practice:
                        correct = (str(prac_answers[pq["id"]]).strip() == str(pq["answer"]).strip())
                        correct_count += int(correct)
                        save_attempt(
                            student_id,
                            meta["subject"],
                            meta["topic"],
                            pq["prompt"],
                            prac_answers[pq["id"]],
                            pq["answer"],
                            correct,
                            pq.get("mistake_type", "conceptual"),
                            mode="practice"
                        )
                    st.session_state["practice_score"] = round(correct_count / len(practice) * 100)
                    st.rerun()

# ---------------------------------------------------------
# SECTION 3: MARKS ANALYSIS (PAPERPATTERN)
# ---------------------------------------------------------

elif page == "Marks analysis":
    render_hero(
        "Understand where marks go.",
        "Turn raw test marks into an actionable plan for your next attempt.",
        "PAPERPATTERN"
    )

    with st.form("marks_analysis_form"):
        subject = st.selectbox(
            "Subject",
            ["Mathematics", "Science", "Physics", "Chemistry", "Biology", "English", "Other"],
            key="marks_sub"
        )
        topic = st.text_input("Chapter or Test Name", placeholder="e.g. Chemical Bonding, Integral Calculus", key="marks_top")

        c_a, c_b = st.columns(2)
        with c_a:
            total_marks = st.number_input("Maximum Marks", min_value=1.0, max_value=1000.0, value=20.0, step=1.0)
        with c_b:
            scored_marks = st.number_input("Marks Obtained", min_value=0.0, max_value=1000.0, value=12.0, step=0.5)

        st.markdown("**What kinds of mistakes occurred?**")
        all_mistake_types = [
            "Conceptual misunderstanding",
            "Calculation / careless error",
            "Misread the question",
            "Incomplete explanation / steps",
            "Time management",
            "Forgot formula or fact"
        ]
        selected_types = st.multiselect("Select all that apply:", all_mistake_types, default=["Conceptual misunderstanding"])
        notes = st.text_area("Optional: Describe an example question where you lost marks", placeholder="e.g. Formula was correct but applied incorrect boundary condition.")

        submitted = st.form_submit_button("Analyze Test Marks", type="primary", use_container_width=True)

    if submitted:
        if scored_marks > total_marks:
            st.error("Marks obtained cannot exceed maximum marks.")
        else:
            percentage = round(scored_marks / total_marks * 100)
            final_topic = topic.strip() or "General Assessment"

            with st.spinner("Analyzing test patterns..."):
                analysis = analyze_test(
                    gemini,
                    [],
                    subject,
                    final_topic,
                    manual_types=selected_types,
                    notes=notes,
                    score=percentage
                )

            save_test_session(
                student_id,
                subject,
                final_topic,
                scored_marks,
                total_marks,
                percentage,
                ", ".join(selected_types),
                notes
            )

            # Record mastery updates for identified patterns
            for m in analysis.get("mistakes", []):
                update_mastery(
                    student_id,
                    subject,
                    final_topic,
                    m.get("type", "conceptual"),
                    error_count=1,
                    score=percentage
                )

            # Add follow-up review
            add_review(
                student_id,
                subject,
                final_topic,
                days=1 if percentage < 60 else 3,
                reason="Review mistakes from test"
            )

            st.session_state["marks_result"] = {
                "pct": percentage,
                "scored": scored_marks,
                "total": total_marks,
                "subject": subject,
                "topic": final_topic,
                "analysis": analysis
            }
            st.rerun()

    m_res = st.session_state.get("marks_result")

    if m_res:
        st.divider()
        st.markdown(f"### Performance Report: {m_res['topic']}")

        c1, c2, c3 = st.columns(3)
        with c1:
            render_metric("Test Score", f"{m_res['pct']}%", f"{m_res['scored']:g} out of {m_res['total']:g}")
        with c2:
            render_metric("Patterns Identified", len(m_res["analysis"]["mistakes"]), "Actionable categories")
        with c3:
            render_metric("Priority", "Targeted Review", "Added to revision loop")

        st.markdown("### Action Plan")
        st.write(m_res["analysis"]["summary"])

        for mistake in m_res["analysis"]["mistakes"]:
            st.markdown(f"- **{mistake['label']}**: {mistake['recommendation']}")

        # Compare with previous test attempts on the same topic
        history = get_test_sessions(student_id, m_res["subject"], m_res["topic"], order="ASC")
        if len(history) >= 2:
            st.markdown("### 📈 Historical Progression on this Topic")
            prev = history[-2]
            curr = history[-1]
            delta = curr["percentage"] - prev["percentage"]

            k1, k2, k3 = st.columns(3)
            with k1:
                render_metric("Previous Score", f"{prev['percentage']}%", f"{prev['scored']:g}/{prev['total']:g}")
            with k2:
                render_metric("Latest Score", f"{curr['percentage']}%", f"{curr['scored']:g}/{curr['total']:g}")
            with k3:
                sign = "+" if delta > 0 else ""
                render_metric("Score Delta", f"{sign}{delta}%", "Net change in mastery")

# ---------------------------------------------------------
# SECTION 4: RECALL & REVISION (RECALLLOOP)
# ---------------------------------------------------------

elif page == "Recall & revision":
    render_hero(
        "Active recall builds lasting memory.",
        "Retrieve knowledge from memory first, verify against model explanations, and let spaced repetition lock it in.",
        "RECALLLOOP"
    )

    due = get_due_reviews(student_id, limit=50)
    upcoming = get_upcoming_reviews(student_id, limit=50)
    completed = get_completed_reviews(student_id, limit=50)

    # 3 Distinct Tabs separating Due Today, Upcoming Schedule, and Completed / Log
    tab_due, tab_upcoming, tab_completed = st.tabs([
        f"⏰ Due Today ({len(due)})",
        f"🗓️ Upcoming ({len(upcoming)})",
        f"✅ Completed ({len(completed)})"
    ])

    with tab_due:
        # Check if an active recall session is in progress
        active_session = st.session_state.get("active_recall")

        if active_session:
            rev_data = active_session["review"]
            chal = active_session["challenge"]
            step = active_session.get("step", "prompt")

            st.markdown(f"### 🧠 Active Retrieval Session: **{rev_data['topic']}**")
            st.caption(f"Subject: {rev_data['subject']} · Challenge Source: {chal.get('source', 'Active Recall Challenge')}")

            if step == "prompt":
                st.markdown(f"""
                <div class="panel" style="border-left: 4px solid #a3e7b7;padding:1.1rem 1.3rem;">
                    <div style="font-weight:700;color:#a3e7b7;margin-bottom:8px;font-size:0.85rem">RETRIEVAL CHALLENGE (NO LOOKING AT NOTES!)</div>
                    <div style="font-size:0.95rem;color:#eaf3ed;line-height:1.6;white-space:pre-wrap;">{chal['challenge']}</div>
                </div>
                """, unsafe_allow_html=True)

                st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
                student_recall_input = st.text_area(
                    "Write your explanation or solution from memory (avoid checking notes!):",
                    value=st.session_state.get("recall_input_text", ""),
                    height=160,
                    placeholder="Type what you remember: core definition, key equations, steps, and edge cases...",
                    key="recall_textarea"
                )

                col_sub, col_cancel = st.columns([1, 4])
                with col_sub:
                    if st.button("Submit Retrieval", type="primary", use_container_width=True):
                        if not student_recall_input.strip():
                            st.warning("Please type your response from memory before submitting.")
                        else:
                            active_session["student_response"] = student_recall_input.strip()
                            active_session["step"] = "evaluate"
                            st.session_state["active_recall"] = active_session
                            st.rerun()
                with col_cancel:
                    if st.button("Cancel Session"):
                        st.session_state.pop("active_recall", None)
                        st.session_state.pop("recall_input_text", None)
                        st.rerun()

            elif step == "evaluate":
                st.markdown("#### 1. What You Recalled from Memory:")
                st.markdown(f"""
                <div class="panel" style="background:#14221a;border:1px solid #284433;">
                    <p style="margin:0;color:#eaf3ed;white-space:pre-wrap;">{active_session['student_response']}</p>
                </div>
                """, unsafe_allow_html=True)

                st.markdown("#### 2. Model Reference & Key Criteria:")
                st.markdown(f"""
                <div class="panel" style="background:#13261b;border:1px solid #366548;">
                    <div style="font-weight:700;color:#a3e7b7;margin-bottom:6px">MODEL EXPLANATION</div>
                    <p style="color:#eaf3ed;margin-bottom:10px;white-space:pre-wrap;">{chal['model_answer']}</p>
                </div>
                """, unsafe_allow_html=True)

                if chal.get("key_points"):
                    st.markdown("**Key Checklist for Recall:**")
                    for kp in chal["key_points"]:
                        st.markdown(f"- {kp}")

                st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
                st.markdown("#### 3. Self-Assess Your Recall:")

                eval_choice = st.radio(
                    "How accurately did you retrieve the concepts?",
                    [
                        "🌟 Mastered (Recalled accurately, completely, and effortlessly)",
                        "👍 Recalled (Recalled the core ideas with minor gaps)",
                        "⚠️ Struggled (Forgot critical concepts or formulas; need review tomorrow)"
                    ],
                    index=1,
                    key="eval_radio"
                )

                if st.button("Save & Reschedule Review", type="primary", use_container_width=True):
                    res = complete_recall_session(
                        student_id=student_id,
                        review_id=rev_data.get("id"),
                        subject=rev_data.get("subject", "General"),
                        topic=rev_data.get("topic", "General"),
                        prompt=chal["challenge"],
                        response=active_session["student_response"],
                        self_eval=eval_choice
                    )
                    st.session_state.pop("active_recall", None)
                    st.session_state.pop("recall_input_text", None)
                    st.session_state["recall_flash_message"] = res["message"]
                    st.rerun()

        else:
            flash = st.session_state.pop("recall_flash_message", None)
            if flash:
                st.success(flash)

            if due:
                st.markdown(f"### Reviews Due for Revision · **{len(due)}**")
                st.caption("Select a topic to begin an active retrieval test without checking notes first.")

                for rev in due:
                    with st.container():
                        c1, c2, c3 = st.columns([3, 1.4, 1.1])
                        with c1:
                            st.markdown(f"**{rev['topic']}**")
                            st.caption(f"{rev['subject']} · Due: **{rev['due_date']}** · {rev['reason']}")
                        with c2:
                            if st.button("Start Active Recall 🧠", key=f"start_recall_{rev['id']}", use_container_width=True, type="primary"):
                                with st.spinner("Preparing active recall challenge..."):
                                    challenge = generate_recall_prompt(gemini, rev["subject"], rev["topic"], stage=current_grade)
                                st.session_state["active_recall"] = {
                                    "review": rev,
                                    "challenge": challenge,
                                    "step": "prompt"
                                }
                                st.rerun()
                        with c3:
                            if st.button("Mark Mastered", key=f"mast_{rev['id']}", use_container_width=True):
                                res = complete_review(student_id, rev["id"], rev["subject"], rev["topic"], mastered=True)
                                st.success(res["message"])
                                st.rerun()
                    st.markdown("---")
            else:
                if upcoming:
                    st.info(f"✨ You're all caught up for today! You have {len(upcoming)} upcoming review(s) scheduled. Click the 'Upcoming' tab to see when they are due.")
                elif completed:
                    st.success("All scheduled reviews have been completed! Add new topics below or take a diagnostic to keep your revision active.")
                else:
                    st.info("No revision items scheduled yet. Complete a diagnostic or add a topic below to start your spaced repetition plan.")

    with tab_upcoming:
        if upcoming:
            st.markdown(f"### Scheduled Upcoming Reviews · **{len(upcoming)}**")
            st.caption("These topics are scheduled according to your spaced repetition learning intervals.")
            today_date = date.today()
            for rev in upcoming:
                try:
                    rev_d = date.fromisoformat(rev["due_date"])
                    diff = (rev_d - today_date).days
                    days_text = f"in {diff} day{'s' if diff > 1 else ''}" if diff > 0 else "tomorrow"
                except Exception:
                    days_text = f"on {rev['due_date']}"

                st.markdown(f"""
                <div class="panel" style="padding:0.8rem 1.1rem;margin-bottom:0.5rem">
                    <div style="display:flex;justify-content:space-between;align-items:center">
                        <span style="font-weight:600;font-size:1rem;color:#eaf3ed">{rev['topic']}</span>
                        <span style="font-weight:700;color:#a3e7b7;font-size:0.85rem">{days_text} ({rev['due_date']})</span>
                    </div>
                    <div class="small-muted" style="margin-top:2px">{rev['subject']} · Reason: {rev['reason']}</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No upcoming reviews scheduled for future dates. Complete a diagnostic or add topics below to schedule reviews.")

    with tab_completed:
        recent_sessions = get_recall_sessions(student_id, limit=20)
        if recent_sessions:
            st.markdown("### Active Recall Session Log")
            st.caption("Record of concepts you retrieved from memory and your self-assessment ratings.")
            for s in recent_sessions:
                eval_tag = s.get("self_eval", "")
                st.markdown(f"""
                <div class="panel" style="padding:0.8rem 1.1rem;margin-bottom:0.6rem">
                    <div style="display:flex;justify-content:space-between">
                        <span style="font-weight:600;color:#eaf3ed">{s['topic']} ({s['subject']})</span>
                        <span style="color:#a3e7b7;font-size:0.82rem">{s['created_at']}</span>
                    </div>
                    <div style="margin:4px 0;font-size:0.88rem;color:#d2e4d8"><b>Self-Assessment:</b> {eval_tag}</div>
                    <div style="font-size:0.83rem;color:#9ab1a3;white-space:pre-wrap;background:#131c16;padding:6px 10px;border-radius:6px;margin-top:4px">{s.get('response', '')[:250]}{'...' if len(s.get('response', '')) > 250 else ''}</div>
                </div>
                """, unsafe_allow_html=True)
        elif completed:
            st.markdown(f"### Completed Topics Archive · **{len(completed)}**")
            for c in completed:
                st.markdown(f"- **{c['topic']}** ({c['subject']}) · Completed")
        else:
            st.info("No completed review history recorded yet.")

    st.markdown("### Add a Topic to Your Revision Schedule")

    with st.form("manual_review_form"):
        r_sub = st.selectbox(
            "Subject",
            ["Mathematics", "Science", "Physics", "Chemistry", "Biology", "English", "Computer Science", "Other"],
            key="man_sub"
        )
        r_top = st.text_input("Topic Name", placeholder="e.g. Thermodynamics, Coordinate Geometry")
        r_interval = st.selectbox("First Review Interval", ["Tomorrow (1 day)", "In 3 days", "In 7 days", "In 14 days"])
        r_submit = st.form_submit_button("Add to Revision Plan", type="primary")

    if r_submit:
        if not r_top.strip():
            st.warning("Please provide a topic name.")
        else:
            days_map = {
                "Tomorrow (1 day)": 1,
                "In 3 days": 3,
                "In 7 days": 7,
                "In 14 days": 14
            }
            add_review(student_id, r_sub, r_top.strip(), days=days_map[r_interval], reason="Self-scheduled review")
            st.success(f"Added '{r_top.strip()}' to your revision plan.")
            st.rerun()

    st.markdown("### High-Priority Topics to Revisit")
    recs = get_recommendations(student_id)

    if recs:
        for r in recs[:5]:
            st.markdown(f"- **{r['topic']}** ({r['subject']}): {r['reason']}")
    else:
        st.caption("Recommendations automatically surface here after you complete diagnostics or mark exam mistakes.")

# ---------------------------------------------------------
# SECTION 5: TEXTBOOK HELPER
# ---------------------------------------------------------

elif page == "Textbook helper":
    render_hero(
        "Make dense textbook pages simple.",
        "Upload a PDF chapter or paste lesson text to build a persistent study session with source-grounded Q&A.",
        "TEXTBOOK HELPER"
    )

    # ---------------------------------------------------------
    # MY 4 IMPORTANT CONCEPTS
    # ---------------------------------------------------------
    st.markdown("### ⭐ My 4 Important Concepts")
    saved_concepts = get_saved_concepts(student_id)
    c_count = len(saved_concepts)
    st.caption(f"📌 **{c_count} of 4 saved** — Keep up to four core concepts handy for rapid review and reflection.")

    if c_count >= 4:
        st.info("You have saved four important concepts. Delete one to add a new concept.")

    if saved_concepts:
        concept_cols = st.columns(min(c_count, 2))
        for idx_c, sc in enumerate(saved_concepts):
            with concept_cols[idx_c % len(concept_cols)]:
                st.markdown(f"""
                <div class="panel" style="padding:0.9rem 1.1rem;margin-bottom:0.6rem">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
                        <span style="font-weight:700;color:#a3e7b7;font-size:0.98rem">⭐ {sc['concept_name']}</span>
                        <span style="font-size:0.75rem;color:#8fa697;background:#182e22;padding:2px 8px;border-radius:4px">{sc['topic']}</span>
                    </div>
                    <div style="color:#eaf3ed;font-size:0.92rem;margin-bottom:6px"><b>Question:</b> {sc['question']}</div>
                    {f'<div style="color:#9ab1a3;font-size:0.83rem;font-style:italic">Note: {sc["notes"]}</div>' if sc.get('notes') else ''}
                </div>
                """, unsafe_allow_html=True)
                if st.button("Delete Concept 🗑️", key=f"del_concept_btn_{sc['id']}", use_container_width=True):
                    delete_saved_concept(student_id, sc["id"])
                    st.success(f"Deleted '{sc['concept_name']}'. You can now save a replacement concept.")
                    st.rerun()

    if c_count < 4:
        with st.expander(f"➕ Add Important Concept ({4 - c_count} of 4 available)", expanded=(c_count == 0)):
            with st.form("manual_save_concept_form"):
                m_topic = st.text_input("Topic", placeholder="e.g. Cellular Respiration or Machine Learning", max_chars=60)
                m_concept = st.text_input("Concept Name", placeholder="e.g. Gradient Descent Convergence", max_chars=80)
                m_question = st.text_area("Question to Revisit", placeholder="e.g. How does learning rate affect convergence?", max_chars=300)
                m_note = st.text_input("Personal Note (Optional)", placeholder="e.g. Review formula before exam", max_chars=120)
                submit_m_concept = st.form_submit_button("Save to My 4 Concepts ⭐", type="primary")

                if submit_m_concept:
                    if not m_concept.strip() or not m_question.strip():
                        st.warning("Please provide both a Concept Name and a Question to revisit.")
                    else:
                        try:
                            save_important_concept(
                                student_id=student_id,
                                topic=m_topic.strip() or "General",
                                concept_name=m_concept.strip(),
                                question=m_question.strip(),
                                notes=m_note.strip()
                            )
                            st.success(f"Saved '{m_concept.strip()}' to your 4 Important Concepts!")
                            st.rerun()
                        except ValueError as ve:
                            st.error(str(ve))
                        except Exception as exc:
                            import logging
                            logging.error(f"Save concept error: {exc}")
                            st.error("Unable to save concept at this time. Please try again.")

    st.markdown("---")

    # 1. Study Sessions Management
    saved_sessions = get_textbook_sessions(student_id)
    session_options = ["➕ Create New Study Session"] + [f"{s['title']} ({s['created_at'][:10]} · #{s['id']})" for s in saved_sessions]
    session_map = {f"{s['title']} ({s['created_at'][:10]} · #{s['id']})": s for s in saved_sessions}

    # Determine default selected session
    selected_idx = 0
    active_sid = st.session_state.get("active_tb_session_id")
    if active_sid:
        for idx, s in enumerate(saved_sessions, 1):
            if s["id"] == active_sid:
                selected_idx = idx
                break

    selected_session_label = st.selectbox(
        "Study Session",
        session_options,
        index=selected_idx,
        help="Switch between existing saved textbook sessions or create a new one."
    )

    if selected_session_label == "➕ Create New Study Session":
        st.markdown("### ➕ Create a New Study Session")
        session_title = st.text_input(
            "Session Title",
            placeholder="e.g. Chapter 4: ATP & Cellular Respiration",
            max_chars=80,
            help="Give this study session a recognizable name so you can reopen it anytime."
        )

        input_mode = st.radio(
            "Choose Source Material",
            ["📄 Upload PDF Document", "✍️ Paste Text / Notes"],
            horizontal=True,
            key="tb_create_mode"
        )

        if input_mode == "📄 Upload PDF Document":
            uploaded = st.file_uploader(
                "Upload Textbook or Study Notes (PDF)",
                type=["pdf"],
                help=f"Upload text-based PDF documents up to 15 MB. First {MAX_TEXTBOOK_WORDS:,} words will be analyzed."
            )

            if uploaded:
                is_valid, v_msg = validate_pdf_bytes(uploaded.getvalue(), uploaded.name)
                if not is_valid:
                    st.error(f"Upload rejected: {v_msg}")
                else:
                    file_bytes = uploaded.getvalue()
                    with st.spinner("Extracting and verifying textbook content..."):
                        extracted, info = extract_pdf_text(file_bytes)

                    if not extracted.strip():
                        st.warning(f"⚠️ {info}")
                    else:
                        accepted_text, total_words, is_truncated = enforce_word_limit(extracted, MAX_TEXTBOOK_WORDS)
                        accepted_words = count_words(accepted_text)

                        st.success(f"Extracted {accepted_words:,} words from **{uploaded.name}** ({info}).")
                        if is_truncated:
                            st.warning(f"⚠️ Truncation Notice: Accepting the first {MAX_TEXTBOOK_WORDS:,} words out of {total_words:,} total extracted words.")

                        if st.button("Save & Start Study Session", type="primary", use_container_width=True):
                            title_to_save = session_title.strip() or uploaded.name
                            # Save PDF to private persistent directory
                            rel_storage_path = save_uploaded_pdf(student_id, uploaded.name, file_bytes)
                            new_id = save_textbook_session(
                                student_id=student_id,
                                title=title_to_save,
                                source_type="pdf",
                                source_name=uploaded.name,
                                storage_path=rel_storage_path,
                                extracted_text=accepted_text,
                                total_words=total_words,
                                accepted_words=accepted_words,
                                is_truncated=is_truncated,
                                metadata={"doc_info": info, "byte_size": len(file_bytes)}
                            )
                            st.session_state["active_tb_session_id"] = new_id
                            st.success(f"Study session '{title_to_save}' created successfully!")
                            st.rerun()

        else:
            # Pasted text
            pasted_text = st.text_area(
                "Paste Lesson or Textbook Text",
                height=220,
                placeholder="Paste your lesson notes, textbook excerpts, or study material here...",
                key="tb_pasted_create"
            )
            p_words = count_words(pasted_text)
            if pasted_text.strip():
                accepted_text, total_words, is_truncated = enforce_word_limit(pasted_text, MAX_TEXTBOOK_WORDS)
                accepted_words = count_words(accepted_text)
                st.caption(f"📊 Word Count: **{p_words:,}** / {MAX_TEXTBOOK_WORDS:,} word limit")

                if is_truncated:
                    st.warning(f"⚠️ Content Truncated: Accepting the first {MAX_TEXTBOOK_WORDS:,} words out of {total_words:,} pasted words.")

                if st.button("Save & Start Study Session", type="primary", use_container_width=True):
                    title_to_save = session_title.strip() or (pasted_text.strip().splitlines()[0][:40] if pasted_text.strip() else "Lesson Notes")
                    new_id = save_textbook_session(
                        student_id=student_id,
                        title=title_to_save,
                        source_type="pasted",
                        source_name="Pasted Lesson Notes",
                        storage_path=None,
                        extracted_text=accepted_text,
                        total_words=total_words,
                        accepted_words=accepted_words,
                        is_truncated=is_truncated,
                        metadata={"original_word_count": p_words}
                    )
                    st.session_state["active_tb_session_id"] = new_id
                    st.success(f"Study session '{title_to_save}' created successfully!")
                    st.rerun()
            else:
                st.caption(f"📊 Content Limit: Up to {MAX_TEXTBOOK_WORDS:,} words allowed.")

    else:
        # Existing Session is Selected
        cur_session = session_map[selected_session_label]
        st.session_state["active_tb_session_id"] = cur_session["id"]

        # Session Header & Metadata
        c_meta1, c_meta2 = st.columns([3, 1])
        with c_meta1:
            st.markdown(f"### 📖 {cur_session['title']}")
            st.caption(
                f"Source: **{cur_session['source_name']}** ({cur_session['source_type'].upper()}) · "
                f"Words: **{cur_session['accepted_words']:,}** · "
                f"Created: {cur_session['created_at'][:16]}"
            )
            if cur_session.get("is_truncated"):
                st.warning(f"⚠️ Truncation Notice: Bloom accepted the first {cur_session['accepted_words']:,} words of this document.")
            if cur_session.get("source_type") == "pdf" and cur_session.get("storage_path"):
                from pathlib import Path
                if not Path(cur_session["storage_path"]).exists():
                    st.info("ℹ️ Note: Original PDF file is not present on disk, but extracted study text and Q&A history are preserved.")

        with c_meta2:
            with st.expander("Session Options"):
                del_confirm = st.checkbox("Confirm permanent deletion", key=f"del_chk_{cur_session['id']}")
                if st.button("Delete Session 🗑️", key=f"del_btn_{cur_session['id']}", type="primary"):
                    if del_confirm:
                        if cur_session.get("storage_path"):
                            delete_stored_pdf(student_id, cur_session["storage_path"])
                        delete_textbook_session(cur_session["id"], student_id)
                        st.session_state.pop("active_tb_session_id", None)
                        st.success("Study session deleted.")
                        st.rerun()
                    else:
                        st.warning("Please tick the confirmation checkbox to delete.")

        st.divider()

        # Display Existing Q&A History
        qa_history = get_textbook_qa(cur_session["id"], student_id)
        if qa_history:
            st.markdown(f"### 💬 Question & Answer History ({len(qa_history)})")
            for idx, qa in enumerate(qa_history, 1):
                mode_label = "AI-generated" if qa.get("mode") == "ai" else "Keyword Excerpt Match"
                st.markdown(f"""
                <div class="panel" style="padding:1rem 1.2rem;margin-bottom:0.9rem">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
                        <span style="font-weight:700;color:#eaf3ed;font-size:1.02rem">Q{idx}: {qa['question']}</span>
                        <span style="font-size:0.75rem;color:#a3e7b7;background:#182e22;padding:2px 8px;border-radius:4px">{mode_label} · {qa['created_at'][:16]}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                st.markdown(qa["answer"])
                if qa.get("source_excerpt"):
                    with st.expander("View Cited Source Excerpt", expanded=False):
                        st.markdown(f"```\n{qa['source_excerpt']}\n```")

                col_save_btn, _ = st.columns([1, 3])
                with col_save_btn:
                    if st.button("⭐ Save to My 4 Concepts", key=f"save_qa_concept_{qa['id']}"):
                        if get_saved_concept_count(student_id) >= 4:
                            st.warning("You have saved four important concepts. Delete one to add a new concept.")
                        else:
                            try:
                                save_important_concept(
                                    student_id=student_id,
                                    topic=cur_session["title"],
                                    concept_name=qa["question"][:60] + ("..." if len(qa["question"]) > 60 else ""),
                                    question=qa["question"],
                                    notes=f"Saved from study session: {cur_session['source_name']}"
                                )
                                st.success("Saved to My 4 Important Concepts!")
                                st.rerun()
                            except ValueError as ve:
                                st.info(str(ve))
                st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            st.divider()

        # Ask a new Question
        st.markdown("### ❓ Ask a Question on This Study Material")
        question_input = st.text_area(
            "Enter your question:",
            placeholder="e.g. Explain how ATP synthase produces energy based on this text...",
            key=f"tb_q_input_{cur_session['id']}"
        )

        col_ai, col_kw = st.columns([1, 1])
        ai_available = gemini.available()

        with col_ai:
            if st.button("Explain with AI 🤖", type="primary", use_container_width=True, key=f"btn_ai_{cur_session['id']}"):
                clean_q = question_input.strip()
                placeholder_guidance = "e.g. explain how atp synthase produces energy based on this text..."
                if not clean_q or clean_q.lower() == placeholder_guidance:
                    st.warning("Please enter your own question. The placeholder example is guidance only.")
                elif not ai_available:
                    st.info("AI assistance is temporarily unavailable. You can continue using keyword search below or try again in a few moments.")
                else:
                    relevant_section = find_relevant_context(cur_session["extracted_text"], clean_q, max_chars=18000)
                    with st.spinner("Analyzing source material with Bloom AI..."):
                        ans, status = gemini.explain_from_document(clean_q, relevant_section)

                    # Save only successful responses
                    if ans and "Bloom couldn't generate" not in ans:
                        save_textbook_qa(
                            session_id=cur_session["id"],
                            student_id=student_id,
                            question=clean_q,
                            answer=ans,
                            mode="ai",
                            source_excerpt=relevant_section[:500],
                            is_fallback=False
                        )
                        st.success("Explanation generated and saved to session history.")
                        st.rerun()
                    else:
                        st.info("AI assistance is temporarily unavailable. You can continue using keyword search or try again in a few moments.")

        with col_kw:
            if st.button("Search by Keywords (Non-AI Mode) 🔍", use_container_width=True, key=f"btn_kw_{cur_session['id']}"):
                clean_q = question_input.strip()
                placeholder_guidance = "e.g. explain how atp synthase produces energy based on this text..."
                if not clean_q or clean_q.lower() == placeholder_guidance:
                    st.warning("Please enter search keywords or a question. The placeholder example is guidance only.")
                else:
                    results = search_text_by_keywords(cur_session["extracted_text"], clean_q, max_results=5)
                    if results:
                        st.markdown("### 🔍 Relevant Excerpts (Non-AI Keyword Match)")
                        for i, r in enumerate(results, 1):
                            matched_str = ", ".join(r["matches"])
                            st.markdown(f"""
                            <div class="panel" style="padding:0.9rem 1.1rem;margin-bottom:0.6rem">
                                <div style="font-weight:600;color:#a3e7b7;font-size:0.85rem;margin-bottom:4px">
                                    EXCERPT {i} · Matched terms: <i>{matched_str}</i> (Relevance Score: {r['score']})
                                </div>
                                <div style="color:#eaf3ed;font-size:0.92rem;line-height:1.55;white-space:pre-wrap;">{r['excerpt']}</div>
                            </div>
                            """, unsafe_allow_html=True)
                    else:
                        st.info("No direct keyword matches found in this document. Try using alternative terms or broader concepts.")

        if not ai_available:
            st.info("💡 **AI Explanations Offline:** AI assistance is currently unavailable. You can review saved Q&A above, search by keywords, or read the source material.")

        with st.expander("Preview Accepted Source Material", expanded=False):
            st.text(cur_session["extracted_text"][:6000] + ("..." if len(cur_session["extracted_text"]) > 6000 else ""))

# ---------------------------------------------------------
# SECTION 6: MY PROGRESS
# ---------------------------------------------------------

elif page == "My progress":
    render_hero(
        "Look how far you've come.",
        "Inspect your accuracy progression, mistake patterns, and recorded test milestones.",
        "YOUR PROGRESS"
    )

    attempts = get_attempts(student_id, limit=500)
    tests = get_test_sessions(student_id, limit=100, order="DESC")

    data = get_dashboard_data(student_id)
    attempts = get_attempts(student_id, limit=500)
    tests = get_test_sessions(student_id, limit=100, order="DESC")
    recall_logs = get_recall_sessions(student_id, limit=50)

    has_data = bool(attempts or tests or recall_logs)

    if has_data:
        # Clarified Overview Metrics
        m1, m2, m3, m4, m5 = st.columns(5)
        with m1:
            render_metric("Questions Solved", data["attempts"], "Diagnostic & practice attempts")
        with m2:
            render_metric("Diagnostics", data["diagnostic_sessions"], "Unique topic assessments")
        with m3:
            render_metric("Practice Solved", data["practice_questions"], "Targeted gap questions")
        with m4:
            render_metric("Tests Recorded", data["tests"], "Formal test milestones")
        with m5:
            render_metric("Topics Explored", data["topics"], "Deduplicated curriculum scope")

        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

        if attempts:
            df = pd.DataFrame(attempts)
            df["created_at"] = pd.to_datetime(df["created_at"])
            df["date"] = df["created_at"].dt.date
            df["correct_num"] = df["correct"].astype(int)

            c_left, c_right = st.columns(2)

            with c_left:
                st.markdown("### Accuracy Trend Over Time")
                trend = df.groupby("date", as_index=False).agg(
                    Accuracy=("correct_num", "mean"),
                    Attempts=("id", "count")
                )
                trend["Accuracy"] = (trend["Accuracy"] * 100).round()
                trend["Formatted Date"] = pd.to_datetime(trend["date"]).dt.strftime("%b %d, %Y")

                # Only draw a trendline when >= 2 distinct dates exist to avoid misleading single-point trend
                if len(trend) >= 2:
                    fig1 = px.line(
                        trend,
                        x="Formatted Date",
                        y="Accuracy",
                        markers=True,
                        range_y=[0, 105],
                        color_discrete_sequence=["#3ca373"],
                        labels={"Formatted Date": "Assessment Date", "Accuracy": "Accuracy (%)"}
                    )
                    fig1.update_layout(
                        margin=dict(l=10, r=10, t=10, b=10),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font_color="#b5cbbb",
                        xaxis_title="Assessment Date",
                        yaxis_title="Accuracy (%)",
                        xaxis=dict(gridcolor="#283a2f"),
                        yaxis=dict(gridcolor="#283a2f")
                    )
                    st.plotly_chart(fig1, use_container_width=True)
                else:
                    curr_acc = trend["Accuracy"].iloc[0] if not trend.empty else 0
                    st.markdown(f"""
                    <div class="panel" style="padding:1.4rem;min-height:180px;display:flex;flex-direction:column;justify-content:center">
                        <div style="font-weight:700;color:#eaf3ed;font-size:1.05rem;margin-bottom:6px">Session Accuracy: {curr_acc}% ({trend['Attempts'].iloc[0]} questions)</div>
                        <p class="small-muted" style="margin:0;line-height:1.5">
                            A longitudinal trendline requires assessments across at least 2 distinct dates.
                            Complete another session on a different date to track your accuracy trajectory over time.
                        </p>
                    </div>
                    """, unsafe_allow_html=True)

            with c_right:
                st.markdown("### Daily Question Volume")
                df["parsed_dt"] = pd.to_datetime(df["created_at"], errors="coerce")
                df_valid = df.dropna(subset=["parsed_dt"])
                if not df_valid.empty:
                    df_valid["date_str"] = df_valid["parsed_dt"].dt.strftime("%Y-%m-%d")
                    df_valid["display_date"] = df_valid["parsed_dt"].dt.strftime("%b %d")
                    daily = df_valid.groupby(["date_str", "display_date"], as_index=False).agg(Questions=("id", "count"))
                    daily = daily.sort_values("date_str")

                    fig_daily = px.bar(
                        daily,
                        x="display_date",
                        y="Questions",
                        color_discrete_sequence=["#3ca373"]
                    )
                    fig_daily.update_layout(
                        title=dict(text="Daily Learning Activity", font=dict(family="Manrope", size=14, color="#eaf3ed")),
                        margin=dict(l=10, r=10, t=35, b=10),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font_color="#b5cbbb",
                        xaxis_title="",
                        yaxis_title="Questions Attempted",
                        xaxis=dict(type="category", gridcolor="#283a2f", tickfont=dict(color="#b5cbbb", size=11)),
                        yaxis=dict(gridcolor="#283a2f", dtick=1, rangemode="tozero", tickfont=dict(color="#b5cbbb", size=11))
                    )
                    st.plotly_chart(fig_daily, use_container_width=True)

            # Mistake Pattern Distribution
            st.markdown("### Mistake Pattern Breakdown")
            mistakes = df[df["correct_num"] == 0].groupby("mistake_type", as_index=False).size()

            if not mistakes.empty:
                fig2 = px.bar(
                    mistakes,
                    x="size",
                    y="mistake_type",
                    orientation="h",
                    color_discrete_sequence=["#d89a57"],
                    labels={"size": "Recorded Errors", "mistake_type": "Mistake Pattern"}
                )
                fig2.update_layout(
                    margin=dict(l=10, r=10, t=10, b=10),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font_color="#b5cbbb",
                    xaxis=dict(gridcolor="#283a2f"),
                    yaxis=dict(gridcolor="#283a2f")
                )
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("No incorrect answers recorded yet! Keep up the great work.")

            st.markdown("### Recent Question Attempts")
            show_df = df[["created_at", "subject", "topic", "correct", "mistake_type", "mode"]].copy()
            show_df["Result"] = show_df["correct"].map({1: "✅ Correct", 0: "❌ Review", True: "✅ Correct", False: "❌ Review"})
            show_df = show_df[["created_at", "subject", "topic", "Result", "mistake_type", "mode"]].rename(columns={
                "created_at": "Timestamp",
                "subject": "Subject",
                "topic": "Topic",
                "mistake_type": "Pattern",
                "mode": "Mode"
            })
            st.dataframe(show_df.head(30), use_container_width=True, hide_index=True)

            csv_data = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Export Learning History (CSV)",
                csv_data,
                file_name="bloom_learning_data.csv",
                mime="text/csv"
            )

        if tests:
            st.markdown("### Test Score Milestones")
            tdf = pd.DataFrame(tests)
            tdf["Test Date"] = pd.to_datetime(tdf["created_at"]).dt.strftime("%Y-%m-%d")
            display_tests = tdf[["Test Date", "subject", "topic", "scored", "total", "percentage", "mistake_types"]].rename(columns={
                "subject": "Subject",
                "topic": "Topic",
                "scored": "Score",
                "total": "Max Marks",
                "percentage": "Percentage",
                "mistake_types": "Noted Mistakes"
            })
            st.dataframe(display_tests, use_container_width=True, hide_index=True)

        if recall_logs:
            st.markdown("### Active Recall History")
            rdf = pd.DataFrame(recall_logs)
            rdf["Date"] = pd.to_datetime(rdf["created_at"]).dt.strftime("%Y-%m-%d %H:%M")
            display_recall = rdf[["Date", "subject", "topic", "self_eval", "response"]].rename(columns={
                "subject": "Subject",
                "topic": "Topic",
                "self_eval": "Self-Assessment",
                "response": "Learner Response"
            })
            st.dataframe(display_recall.head(25), use_container_width=True, hide_index=True)

    else:
        st.markdown("""
        <div class="panel">
            <h4 style="margin:0 0 0.35rem 0;color:#eaf3ed">No learning data recorded yet</h4>
            <p class="small-muted" style="margin:0">
                Complete a diagnostic assessment in <b>Find my gaps</b> or record a test in <b>Marks analysis</b> to start tracking your learning progress.
            </p>
        </div>
        """, unsafe_allow_html=True)
