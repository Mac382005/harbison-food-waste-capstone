from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime

import streamlit as st

from .db import execute, fetchone, fetchall, log_action


ROLE_LABELS = {
    "admin": "System Administrator",
    "manager": "Foodservice Manager",
    "kitchen": "Kitchen Staff",
    "dietitian": "Dietitian / Analyst",
}


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def seed_demo_users():
    demo = [
        ("admin", "System Administrator", "admin", "Admin123!"),
        ("manager", "Foodservice Manager", "manager", "Manager123!"),
        ("kitchen", "Kitchen Staff", "kitchen", "Kitchen123!"),
        ("dietitian", "Dietitian / Analyst", "dietitian", "Dietitian123!"),
    ]
    for username, name, role, password in demo:
        if not fetchone("SELECT id FROM users WHERE username=?", (username,)):
            execute(
                "INSERT INTO users(username,display_name,role,password_hash,active,created_at) VALUES(?,?,?,?,1,?)",
                (username, name, role, hash_password(password), datetime.now().isoformat(timespec="seconds")),
            )


def authenticate(username: str, password: str):
    user = fetchone("SELECT * FROM users WHERE username=? AND active=1", (username.strip(),))
    if user and verify_password(password, user["password_hash"]):
        return user
    return None


def current_user():
    return st.session_state.get("user")


def login_screen():
    st.markdown(
        """
        <div class="hero">
          <div class="hero-kicker">HARBISON CARE · CAPSTONE PROTOTYPE</div>
          <div class="hero-title">Food Waste Intelligence</div>
          <div class="hero-sub">Secure prototype for kitchen data collection, costing, reporting and forecasting.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    left, mid, right = st.columns([1, 1.2, 1])
    with mid:
        with st.form("login_form"):
            st.subheader("Sign in")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)
        if submitted:
            user = authenticate(username, password)
            if user:
                st.session_state.user = user
                log_action(user["id"], "LOGIN", "Successful prototype login")
                st.rerun()
            st.error("Invalid username or password.")
        with st.expander("Prototype demo accounts"):
            st.code(
                "admin / Admin123!\n"
                "manager / Manager123!\n"
                "kitchen / Kitchen123!\n"
                "dietitian / Dietitian123!"
            )
            st.caption("Demo credentials only. Replace before any real deployment.")


def logout():
    user = current_user()
    if user:
        log_action(user["id"], "LOGOUT", "User logged out")
    st.session_state.pop("user", None)
    st.rerun()


def require_roles(*roles):
    user = current_user()
    if not user or user["role"] not in roles:
        st.error("You do not have permission to view this page.")
        st.stop()
    return user


def create_user(username, display_name, role, password):
    return execute(
        "INSERT INTO users(username,display_name,role,password_hash,active,created_at) VALUES(?,?,?,?,1,?)",
        (username.strip(), display_name.strip(), role, hash_password(password), datetime.now().isoformat(timespec="seconds")),
    )


def reset_password(user_id: int, password: str):
    execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(password), user_id))
