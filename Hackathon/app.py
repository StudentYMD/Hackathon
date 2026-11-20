import streamlit as st
import requests
from extractor import extract_tasks_from_transcript

# Page configuration
st.set_page_config(page_title="Meeting-to-Action Agent", page_icon="⚡", layout="wide")

# Initialize session state so tasks persist across button clicks
if "tasks" not in st.session_state:
    st.session_state.tasks = []
if "summary" not in st.session_state:
    st.session_state.summary = ""

# Helper to safely load keys from Streamlit Secrets if deployed, or leave blank locally
def get_secret(key_name: str) -> str:
    try:
        return st.secrets.get(key_name, "")
    except Exception:
        return ""

# --- HELPER FUNCTIONS FOR EXTERNAL ACTIONS ---
def push_to_trello(task: dict, api_key: str, token: str, list_id: str):
    url = "https://trello.com"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    desc = (
        f"**Owner:** {task['owner']}\n"
        f"**Deadline:** {task['deadline']}\n"
        f"**Priority:** {task['priority']}\n\n"
        f"**AI Reasoning:** {task['reasoning']}"
    )
    payload = {
        "key": api_key.strip(),
        "token": token.strip(),
        "idList": list_id.strip(),
        "name": f"[{task['priority']}] {task['task_title']}",
        "desc": desc,
    }
    res = requests.post(url, headers=headers, json=payload)
    return res.status_code == 200, res.status_code, res.text

def send_discord_reminder(task: dict, webhook_url: str) -> bool:
    message = {
        "content": (
            f"⏰ **Action Item Follow-Up Reminder!**\n"
            f"• **Task:** {task['task_title']}\n"
            f"• **Assigned To:** {task['owner'] or 'Unassigned'}\n"
            f"• **Deadline:** {task['deadline'] or 'Not Set'}\n"
            f"• **Status:** Pending completion — please update on Trello!"
        )
    }
    res = requests.post(webhook_url.strip(), json=message)
    return res.status_code in [200, 204]

# --- SIDEBAR: API CREDENTIALS ---
with st.sidebar:
    st.header("🔑 Agent Integrations")
    st.caption("Auto-filled from Streamlit Secrets if configured, or paste manually below.")
    gemini_key = st.text_input("Gemini API Key", value=get_secret("GEMINI_API_KEY"), type="password")
    
    st.divider()
    st.subheader("Trello Configuration")
    trello_key = st.text_input("Trello API Key", value=get_secret("TRELLO_API_KEY"), type="password")
    trello_token = st.text_input("Trello Token", value=get_secret("TRELLO_TOKEN"), type="password")
    trello_list_id = st.text_input("Trello 'To Do' List ID", value=get_secret("TRELLO_LIST_ID"))
    
    st.divider()
    st.subheader("Discord Follow-Up")
    discord_webhook = st.text_input("Discord Webhook URL", value=get_secret("DISCORD_WEBHOOK"), type="password")

# --- MAIN UI ---
st.title("⚡ Meeting-to-Action AI Agent")
st.markdown("Turn raw meeting discussions into verified Trello tasks and automated follow-ups.")

default_transcript = """Ananya: Hey everyone, hope you had a good weekend! Ready to get started?
Rahul: Yeah, let's dive in. First, the login page is crashing on mobile. I'll fix the CSS bug and push it to GitHub by tomorrow at 6 PM.
Ananya: Awesome, thanks Rahul. Also, we really need someone to write the pitch deck slides soon, maybe next week?
Vikram: Agreed. Oh, and I will set up the Supabase database tables tonight before 11 PM so the backend is ready.
Ananya: Sounds great! Let's wrap up here."""

transcript = st.text_area("1️⃣ Paste Meeting Transcript", value=default_transcript, height=180)

if st.button("🧠 Extract Commitments", type="primary"):
    if not gemini_key:
        st.error("Please enter your Gemini API Key in the left sidebar first!")
    else:
        with st.spinner("Agent is analyzing context, owners, and ambiguities..."):
            try:
                data = extract_tasks_from_transcript(transcript, gemini_key)
                st.session_state.summary = data.get("meeting_summary", "")
                st.session_state.tasks = data.get("action_items", [])
                for t in st.session_state.tasks:
                    t["synced"] = False
            except Exception as e:
                st.error(f"Extraction Error: {e}")

# --- DISPLAY RESULTS & HUMAN-IN-THE-LOOP ---
if st.session_state.summary:
    st.info(f"**Meeting Context Summary:** {st.session_state.summary}")

if st.session_state.tasks:
    st.subheader("2️⃣ Review & Human-in-the-Loop Verification")
    
    for idx, task in enumerate(st.session_state.tasks):
        with st.container(border=True):
            col1, col2 = st.columns([3, 1])
            
            with col1:
                if task["is_ambiguous"]:
                    st.warning(f"⚠️ **Clarification Needed:** {task.get('clarification_question') or 'Missing owner or deadline.'}")
                else:
                    st.success("✅ **Ready for Execution** (Clear Owner & Deadline)")
                
                task["task_title"] = st.text_input("Task Title", value=task["task_title"], key=f"title_{idx}")
                
                c_owner, c_date, c_prio = st.columns(3)
                task["owner"] = c_owner.text_input(
                    "Owner", 
                    value=task["owner"] or "", 
                    placeholder="Enter name...", 
                    key=f"owner_{idx}"
                )
                task["deadline"] = c_date.text_input(
                    "Deadline", 
                    value=task["deadline"] or "", 
                    placeholder="e.g. Friday 5 PM", 
                    key=f"date_{idx}"
                )
                task["priority"] = c_prio.selectbox(
                    "Priority", 
                    ["High", "Medium", "Low"], 
                    index=["High", "Medium", "Low"].index(task["priority"]) if task["priority"] in ["High", "Medium", "Low"] else 1,
                    key=f"prio_{idx}"
                )

                with st.expander("🔍 View Agent Reasoning"):
                    st.write(task["reasoning"])

            with col2:
                st.write("")
                st.write("")
                is_complete = bool(task["owner"].strip() and task["deadline"].strip())
                
                if task.get("synced"):
                    st.button("✔️ Synced to Trello", disabled=True, key=f"done_{idx}", use_container_width=True)
                else:
                    if st.button(
                        "🚀 Approve & Push to Trello", 
                        disabled=not is_complete, 
                        key=f"push_{idx}", 
                        use_container_width=True
                    ):
                        if not (trello_key and trello_token and trello_list_id):
                            st.error("Add Trello credentials in sidebar!")
                        else:
                            success, status_code, error_msg = push_to_trello(task, trello_key, trello_token, trello_list_id)
                            if success:
                                task["synced"] = True
                                task["is_ambiguous"] = False
                                st.rerun()
                            else:
                                st.error(f"Trello Error ({status_code}): {error_msg}")
                    
                    if not is_complete:
                        st.caption("🔒 Fill Owner & Deadline to unlock.")

                if st.button("🔔 Send Follow-Up Alert", key=f"remind_{idx}", use_container_width=True):
                    if not discord_webhook:
                        st.error("Add Discord Webhook in sidebar!")
                    else:
                        if send_discord_reminder(task, discord_webhook):
                            st.toast(f"Reminder sent to Discord for {task['owner'] or 'task'}!")
                        else:
                            st.error("Failed to send Discord alert.")

