from pathlib import Path

import streamlit as st

from src import auth, store
from src.answer import answer_question
from seed_users import seed_demo_users

DOCS_FOLDER = Path("sample_policies")
DOCS_FOLDER.mkdir(exist_ok=True)

st.set_page_config(page_title="HR Policy Assistant")


@st.cache_resource
def seed_on_startup():
    """Runs once per server start. Does nothing if the data already exists."""
    # 1) Demo users (existing usernames are skipped)
    seed_demo_users()
    # 2) Sample documents, only if the search index is empty
    if not store.list_sources():
        for f in sorted(DOCS_FOLDER.iterdir()):
            if f.suffix.lower() in {".txt", ".pdf", ".docx"}:
                store.ingest_file(f)


with st.spinner("Setting up demo data (first start only)..."):
    seed_on_startup()


def is_admin():
    user = st.session_state.get("user")
    return bool(user) and user["role"] == "admin"


def login_screen():
    st.title("HR Policy Assistant")
    st.subheader("Log in")
    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")
    if submitted:
        user = auth.verify_user(username, password)
        if user:
            st.session_state.user = user
            st.rerun()
        else:
            st.error("Wrong username or password.")

    with st.expander("Forgot password?"):
        st.write(
            "Please contact your admin or HR. They can set a new temporary "
            "password for you. You can then log in with it."
        )


def chat_screen():
    st.title("HR Policy Assistant")
    st.caption("Answers come only from company policy documents.")

    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "Hi! Ask me about leave, notice period, working hours, "
                "reimbursement and other company policies.",
            }
        ]

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            if m.get("sources"):
                st.caption("Sources: " + "; ".join(m["sources"]))

    question = st.chat_input("Ask a policy question")
    if question and question.strip():
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.spinner("Checking the policies..."):
                result = answer_question(question)
            st.markdown(result["answer"])
            if result["sources"]:
                st.caption("Sources: " + "; ".join(result["sources"]))

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": result["answer"],
                "sources": result["sources"],
            }
        )


def users_section():
    """Admin-only tools: add a user and reset a password."""
    st.subheader("Add a user")
    with st.form("add_user", clear_on_submit=True):
        new_name = st.text_input("Username")
        new_pass = st.text_input("Temporary password (6+ characters)", type="password")
        new_role = st.selectbox("Role", ["employee", "admin"])
        add = st.form_submit_button("Create user")
    if add:
        try:
            auth.create_user(new_name, new_pass, new_role)
            st.success(f"Created {new_role}: {new_name.strip().lower()}")
        except ValueError as e:
            st.error(str(e))

    st.subheader("Reset a password")
    names = auth.list_usernames()
    with st.form("reset_password", clear_on_submit=True):
        target_user = st.selectbox("User", names)
        temp_pass = st.text_input("New temporary password (6+ characters)", type="password")
        reset = st.form_submit_button("Reset password")
    if reset:
        try:
            auth.reset_password(target_user, temp_pass)
            st.success(f"Password reset for {target_user}. Share the new password with them.")
        except ValueError as e:
            st.error(str(e))


def admin_screen():
    # Access is checked in code, not only by hiding the menu item
    if not is_admin():
        st.error("Access denied. Admins only.")
        return

    st.title("Document management")

    flash = st.session_state.pop("flash", None)
    if flash:
        st.success(flash)

    st.subheader("Upload or replace a document")
    st.caption("Uploading a file with the same name replaces the old version.")
    uploaded = st.file_uploader("Choose a PDF, DOCX or TXT file", type=["pdf", "docx", "txt"])

    if uploaded and st.button("Save document"):
        name = Path(uploaded.name).name  # strip any folder part
        target = DOCS_FOLDER / name
        existed = target.exists()
        backup = target.read_bytes() if existed else None
        target.write_bytes(uploaded.getvalue())
        try:
            with st.spinner("Reading and storing the document..."):
                n = store.ingest_file(target)
            verb = "Replaced" if existed else "Added"
            st.session_state.flash = f"{verb} {name} ({n} sections stored)."
            st.rerun()
        except Exception as e:
            # undo the file change so the folder and the search stay consistent
            if existed:
                target.write_bytes(backup)
            else:
                target.unlink(missing_ok=True)
            st.error(f"Could not add '{name}': {e}")

    st.subheader("Current documents")
    sources = store.list_sources()
    if sources:
        for source, count in sources.items():
            st.write(f"- {source} ({count} sections)")

        st.subheader("Delete a document")
        choice = st.selectbox("Choose a document", list(sources))
        confirm = st.checkbox(f"Yes, delete {choice}")
        if st.button("Delete", disabled=not confirm):
            store.delete_source(choice)
            (DOCS_FOLDER / choice).unlink(missing_ok=True)
            st.session_state.flash = f"Deleted {choice}."
            st.rerun()
    else:
        st.info("No documents yet.")

    st.divider()
    users_section()


# ---- Main ----
user = st.session_state.get("user")
if not user:
    login_screen()
    st.stop()

with st.sidebar:
    st.write(f"Logged in as **{user['username']}** ({user['role']})")
    pages = ["Chat"] + (["Admin: documents"] if user["role"] == "admin" else [])
    page = st.radio("Go to", pages)
    if st.button("Log out"):
        st.session_state.clear()
        st.rerun()

if page == "Chat":
    chat_screen()
else:
    admin_screen()