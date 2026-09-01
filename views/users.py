import streamlit as st
from src.auth import require_roles, create_user, reset_password, ROLE_LABELS
from src.styles import page_header
from src.db import fetchall, execute, log_action


def page():
    user=require_roles("admin")
    page_header("SECURITY PROTOTYPE", "Users & Access", "Role-based access with hashed passwords and an auditable user list.")

    users=fetchall("SELECT id,username,display_name,role,active,created_at FROM users ORDER BY id")
    st.dataframe(users,use_container_width=True,hide_index=True)

    st.subheader("Create user")
    with st.form("create_user"):
        c1,c2=st.columns(2)
        username=c1.text_input("Username")
        display=c2.text_input("Display name")
        role=st.selectbox("Role",list(ROLE_LABELS.keys()),format_func=lambda x:ROLE_LABELS[x])
        password=st.text_input("Temporary password",type="password")
        create=st.form_submit_button("Create user",type="primary")
    if create:
        if len(username.strip())<3 or len(password)<8:
            st.error("Use a username of at least 3 characters and password of at least 8 characters.")
        else:
            try:
                uid=create_user(username,display or username,role,password)
                log_action(user["id"],"CREATE_USER",f"{username} ({role})")
                st.success(f"User created with ID {uid}.")
            except Exception as e:
                st.error(f"Could not create user: {e}")

    st.subheader("Reset password / enable-disable")
    if users:
        selected=st.selectbox("User",[f"{u['username']} · {u['display_name']}" for u in users])
        target=users[[f"{u['username']} · {u['display_name']}" for u in users].index(selected)]
        new_pass=st.text_input("New password",type="password")
        c1,c2=st.columns(2)
        if c1.button("Reset password",disabled=len(new_pass)<8):
            reset_password(target["id"],new_pass)
            log_action(user["id"],"RESET_PASSWORD",target["username"])
            st.success("Password reset.")
        desired=0 if target["active"] else 1
        if c2.button("Disable user" if target["active"] else "Enable user",disabled=(target["id"]==user["id"])):
            execute("UPDATE users SET active=? WHERE id=?",(desired,target["id"]))
            log_action(user["id"],"TOGGLE_USER",f"{target['username']} -> active={desired}")
            st.success("User status updated.")
