from pathlib import Path

import streamlit as st

from src import auth, limits, store
from src.answer import answer_question
from seed_users import seed_demo_users

DOCS_FOLDER = Path("sample_policies")
DOCS_FOLDER.mkdir(exist_ok=True)

st.set_page_config(page_title="HR Policy Assistant")

quota_slot = None  # sidebar placeholder for "questions left today"


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


def show_quota():
    """Update the 'questions left today' line in the sidebar."""
    u = st.session_state.get("user")
    if quota_slot is None or not u:
        return
    if u["role"] == "admin":
        quota_slot.caption("Questions today: unlimited (admin)")
    else:
        left = limits.remaining(u["username"])
        quota_slot.caption(
            f"Questions left today: {left} of {limits.USER_DAILY_LIMIT}"
        )


def forgot_password_section():
    with st.expander("Forgot password?"):
        st.markdown("**Step 1. Ask your admin to verify you**")
        with st.form("reset_request", clear_on_submit=True):
            who = st.text_input("Your username")
            ask = st.form_submit_button("Send reset request")
        if ask:
            if who.strip():
                auth.request_reset(who)
            st.info(
                "If that username exists, your admin has been notified. Contact "
                "them directly (call or in person) so they can confirm it is you. "
                "They will give you a one-time code."
            )

        st.markdown("**Step 2. Enter the one-time code from your admin**")
        with st.form("reset_redeem", clear_on_submit=True):
            who2 = st.text_input("Username")
            code = st.text_input("One-time code")
            new = st.text_input("New password (6+ characters)", type="password")
            again = st.text_input("Repeat new password", type="password")
            go = st.form_submit_button("Set new password")
        if go:
            if new != again:
                st.error("The two passwords do not match.")
            else:
                try:
                    auth.redeem_reset_code(who2, code, new)
                    st.success("Password updated. You can now log in with it.")
                except ValueError as e:
                    st.error(str(e))


def login_screen():
    st.title("HR Policy Assistant")

    notice = st.session_state.pop("notice", None)
    if notice:
        st.warning(notice)

    st.subheader("Log in")
    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")
    if submitted:
        user = auth.verify_user(username, password)
        if user is None:
            # Same message for a wrong password, an unknown user and a locked account
            message = "Wrong username or password."
            max_fails = getattr(auth, "MAX_LOGIN_FAILS", None)
            if max_fails:
                message += (
                    f" After {max_fails} failed attempts an account is locked for "
                    f"{getattr(auth, 'LOCK_MINUTES', 15)} minutes."
                )
            st.error(message)
        elif not user["active"]:
            st.error("This account is blocked. Please contact your admin or HR.")
        else:
            st.session_state.user = user
            st.rerun()

    forgot_password_section()


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
        question = question.strip()

        # Too long: rejected, and it does not use up the daily allowance
        if len(question) > limits.MAX_QUESTION_CHARS:
            st.warning(
                f"Your question is {len(question)} characters. Please keep it "
                f"under {limits.MAX_QUESTION_CHARS}."
            )
            return

        username = st.session_state.user["username"]
        limited = not is_admin()  # the admin is exempt from the daily limits

        # Take one question from the allowance (checked and counted in one step)
        if limited:
            allowed, message = limits.reserve(username)
            if not allowed:
                st.warning(message)
                show_quota()
                return

        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            try:
                with st.spinner("Checking the policies..."):
                    result = answer_question(question)
            except Exception:
                if limited:
                    limits.refund(username)  # a failed call does not use a question
                show_quota()
                raise

            # Only answers that really called the model use up a question
            if limited and not result.get("used_llm"):
                limits.refund(username)

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
        show_quota()


def documents_screen():
    # Access is checked in code, not only by hiding the menu item
    if not is_admin():
        st.error("Access denied. Admins only.")
        return

    st.title("Document management")

    flash = st.session_state.pop("flash", None)
    if flash:
        st.success(flash)

    st.subheader("Upload or replace a document")
    st.warning(
        "Upload company HR policy documents only. Everything you upload can be "
        "read by every employee through the chat, and matching text is sent to "
        "the AI service. Never upload documents with personal data, such as CVs, "
        "payslips or ID numbers."
    )
    with st.expander("Document guidelines"):
        st.markdown(
            "- PDF, DOCX or TXT files with real text. Scanned images are rejected.\n"
            "- One topic per file, with a clear title on the first line.\n"
            "- Numbered sections with a blank line between them work best "
            "(for example `1. Fridays`).\n"
            "- Write tables as sentences. Tables inside Word files are skipped.\n"
            "- Uploading a file with the same name replaces the old version.\n"
            "- Do not upload the same policy twice under different names.\n"
            "- Write in English."
        )
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


def issue_code_for(username):
    try:
        code = auth.issue_reset_code(username)
        st.session_state.issued_code = (username, code)
        st.rerun()
    except ValueError as e:
        st.error(str(e))


def users_screen():
    # Access is checked in code, not only by hiding the menu item
    if not is_admin():
        st.error("Access denied. Admins only.")
        return

    st.title("User management")

    flash = st.session_state.pop("flash", None)
    if flash:
        st.success(flash)

    issued = st.session_state.pop("issued_code", None)
    if issued:
        st.success(
            f"One-time code for {issued[0]}. It is shown only now, works once "
            f"and expires in {auth.CODE_MINUTES} minutes:"
        )
        st.code(issued[1])

    me = st.session_state.user["username"]
    users = auth.list_users()

    st.subheader("Users")
    st.caption(
        "Passwords are stored hashed and can never be displayed. "
        "To help someone who forgot theirs, generate a one-time code below. "
        "Block then Activate also removes a login lockout."
    )
    header = st.columns([3, 2, 3, 2])
    header[0].markdown("**Username**")
    header[1].markdown("**Role**")
    header[2].markdown("**Status**")
    header[3].markdown("**Action**")

    for u in users:
        c1, c2, c3, c4 = st.columns([3, 2, 3, 2])
        c1.write(u["username"])
        c2.write(u["role"])
        status = "Active" if u["active"] else "Blocked"
        if u.get("locked"):
            status += " (locked)"
        if u["reset_requested"]:
            status += " (reset requested)"
        c3.write(status)
        if u["username"] == me:
            c4.caption("(you)")
        elif u["active"]:
            if c4.button("Block", key=f"block_{u['username']}"):
                try:
                    auth.set_active(u["username"], False)
                    st.session_state.flash = f"Blocked {u['username']}."
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
        else:
            if c4.button("Activate", key=f"activate_{u['username']}"):
                auth.set_active(u["username"], True)
                st.session_state.flash = f"Activated {u['username']}."
                st.rerun()

    st.divider()
    st.subheader("Password reset requests")
    st.caption(
        "Verify the person first (call them on a number you already have, or ask in "
        "person). Then generate a code and share it privately. Never share it in a "
        "group chat."
    )
    pending = [u for u in users if u["reset_requested"] and u["active"]]
    if not pending:
        st.caption("No pending requests.")
    for u in pending:
        r1, r2 = st.columns([4, 2])
        r1.write(f"{u['username']} asked for a password reset")
        if r2.button("Generate code", key=f"code_{u['username']}"):
            issue_code_for(u["username"])

    st.subheader("Generate a reset code for any user")
    active_names = [u["username"] for u in users if u["active"]]
    with st.form("manual_code"):
        target = st.selectbox("User", active_names)
        make = st.form_submit_button("Generate one-time code")
    if make:
        issue_code_for(target)

    st.divider()
    st.subheader("Add a user")
    with st.form("add_user", clear_on_submit=True):
        new_name = st.text_input("Username")
        new_pass = st.text_input("Initial password (6+ characters)", type="password")
        new_role = st.selectbox("Role", ["employee", "admin"])
        add = st.form_submit_button("Create user")
    if add:
        try:
            auth.create_user(new_name, new_pass, new_role)
            st.session_state.flash = f"Created {new_role}: {new_name.strip().lower()}"
            st.rerun()
        except ValueError as e:
            st.error(str(e))


# ---- Main ----
user = st.session_state.get("user")
if user:
    # Re-check on every click: a user blocked while logged in is logged out
    current = auth.get_user(user["username"])
    if current is None or not current["active"]:
        st.session_state.clear()
        st.session_state.notice = "Your account is blocked or no longer exists. Please contact HR."
        st.rerun()
    user = current

if not user:
    login_screen()
    st.stop()

with st.sidebar:
    st.write(f"Logged in as **{user['username']}** ({user['role']})")
    quota_slot = st.empty()
    show_quota()
    pages = ["Chat"]
    if user["role"] == "admin":
        pages += ["Admin: documents", "Admin: users"]
    page = st.radio("Go to", pages)
    if st.button("Log out"):
        st.session_state.clear()
        st.rerun()

if page == "Chat":
    chat_screen()
elif page == "Admin: documents":
    documents_screen()
else:
    users_screen()