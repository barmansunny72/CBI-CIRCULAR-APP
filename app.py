import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import google.generativeai as genai
import io
import json
import os
import tempfile
import time

# --- UI THEME ---
st.set_page_config(page_title="CBI Branch Assistant", page_icon="🏦", layout="wide")

# --- 📁 THE 7-FOLDER SWITCHBOARD ---
FOLDER_MAP = {
    "Recovery": "1-ZNUfN6C63BDbciRxAXeK2BBU5_Apys7",
    "Operations": "11PIq4gs88DqcJ5dTpdKwMknZB5pB2jAr",
    "Miscellaneous": "11jvTnHhlisuG3gn4CgHzB58lMc0OtQyc",
    "IT/Digital Section": "1eKjscpA7I_-X0l86ApKqKdrPEr9SumjO",
    "Human Resource/Staff welfare": "1oDBeTtP9EKmOdqJ-OmbV4VwH6Cea1qcA",
    "Credit/Advance": "1EJKLgnEsnWZJ3jJDSEsiG9yseqKotkZG",
    "Credit Monitoring": "1h1ZIImScWAIycVeF_eLEdO95o7JhahQ4"
}

# --- 🗄️ DATABASE SETUP ---
USERS_FILE = "staff_users.json"
CHATS_FILE = "staff_chats.json"

def load_data(filepath):
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return json.load(f)
    return {}

def save_data(filepath, data):
    with open(filepath, "w") as f:
        json.dump(data, f)

# --- AI & DRIVE SETUP ---
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-2.5-flash')

@st.cache_resource
def get_drive_service():
    creds = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=['https://www.googleapis.com/auth/drive.readonly']
    )
    return build('drive', 'v3', credentials=creds)

def get_all_pdf_files_in_folder(service, folder_id):
    files = []
    try:
        # UPGRADED: Added Enterprise "Shared Drive" support to bypass workspace blocks
        results = service.files().list(
            q=f"'{folder_id}' in parents and (mimeType='application/pdf' or mimeType='application/vnd.google-apps.folder') and trashed=false", 
            fields="files(id, name, mimeType)",
            supportsAllDrives=True, 
            includeItemsFromAllDrives=True
        ).execute()
        
        for item in results.get('files', []):
            if item['mimeType'] == 'application/pdf':
                files.append(item)
            elif item['mimeType'] == 'application/vnd.google-apps.folder':
                files.extend(get_all_pdf_files_in_folder(service, item['id']))
        return files
    except Exception as e:
        # HUMAN READABLE ERROR CATCHER
        st.error(f"🚨 **Google Drive Connection Blocked!**\n\nThe app tried to open Folder ID: `{folder_id}`, but Google stopped it.\n\n**Please check:**\n1. Did you share this folder with the Robot Email?\n2. Did you accidentally paste the whole web link instead of just the ID?\n\n*(Technical detail: {e})*")
        st.stop()

# --- 🧠 THE GEMINI VISION ENGINE ---
@st.cache_resource(ttl=3600, show_spinner=False)
def load_folder_to_gemini(folder_id):
    service = get_drive_service()
    drive_files = get_all_pdf_files_in_folder(service, folder_id)
    
    gemini_uploaded_files = []
    
    for f in drive_files:
        request = service.files().get_media(fileId=f['id'])
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
            
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(fh.getvalue())
            tmp_path = tmp.name
            
        g_file = genai.upload_file(path=tmp_path, display_name=f['name'])
        
        while g_file.state.name == 'PROCESSING':
            time.sleep(2)
            g_file = genai.get_file(g_file.name)
            
        if g_file.state.name != 'FAILED':
            gemini_uploaded_files.append(g_file)
            
        os.remove(tmp_path)
        
    return gemini_uploaded_files

# --- UI ---
if "user_data" not in st.session_state:
    st.title("🏦 Central Bank of India - Silchar")
    tab1, tab2 = st.tabs(["🔒 Login", "📝 Register"])
    users_db = load_data(USERS_FILE)
    
    with tab1:
        login_pf = st.text_input("PF Number", key="login")
        if st.button("Log In"):
            if login_pf in users_db:
                st.session_state["user_data"] = {"name": users_db[login_pf], "pf": login_pf}
                st.session_state["messages"] = load_data(CHATS_FILE).get(login_pf, [])
                st.rerun()
            else:
                st.error("PF Number not found. Please register.")
                
    with tab2:
        name, pf = st.text_input("Name"), st.text_input("PF Number")
        if st.button("Register"):
            if pf in users_db:
                st.error("PF Number already registered.")
            elif len(pf) == 6 and name:
                users_db[pf] = name
                save_data(USERS_FILE, users_db)
                st.success("Registered! You can now log in.")
            else:
                st.error("Please enter a valid Name and 6-digit PF Number.")
else:
    u = st.session_state["user_data"]
    with st.sidebar:
        st.success(f"Logged in: {u['name']}")
        dept = st.selectbox("Department", list(FOLDER_MAP.keys()))
        sub = st.selectbox("Category", ["General"] + (["Retail", "MSME", "Agri", "Master Credit Policy"] if dept == "Credit/Advance" else []))
        
        if st.button("Log Out"): 
            st.session_state.clear()
            st.rerun()
            
        st.divider()
        if st.button("🔄 Sync New Circulars"):
            st.cache_resource.clear()
            st.cache_data.clear()
            st.success("Database synced! New circulars are now active.")

    st.title(f"Assistant: {dept}")
    
    # NEW SAFETY NET: Stops the app from crashing if you haven't put an ID in yet
    active_folder_id = FOLDER_MAP[dept]
    if "PASTE" in active_folder_id:
        st.warning(f"⚠️ **Stop!** You haven't linked the Google Drive folder for **{dept}** yet. Please paste the ID into your GitHub code.")
        st.stop()
        
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])

    if query := st.chat_input("Ask a question..."):
        st.session_state.messages.append({"role": "user", "content": query})
        with st.chat_message("user"): st.markdown(query)
        
        with st.chat_message("assistant"):
            with st.spinner("Analyzing physical and digital circulars..."):
                gemini_files = load_folder_to_gemini(active_folder_id)
                
                history_text = ""
                for msg in st.session_state.messages[-6:]: 
                    role_name = u['name'] if msg["role"] == "user" else "AI"
                    history_text += f"{role_name}: {msg['content']}\n"
                
                prompt_text = f"""
                You are Gemini, acting as a highly intelligent, friendly colleague at the Central Bank of India, Silchar Branch. 
                You are helping {u['name']}. Speak to them naturally and warmly.
                
                --- CHAT HISTORY ---
                {history_text}
                
                --- ATTACHED DOCUMENTS ---
                I have directly attached the official PDF circulars to this prompt. You can see their display names. 
                The user is specifically interested in the category: "{sub}". Pay extra attention to documents that match that topic, but search all attached files.
                
                USER'S QUESTION: {query}
                
                RULES: 
                1. Base your answer strictly on the attached documents. Read images, tables, and scanned text carefully.
                2. Be conversational but concise. 
                3. Always cite the Document display name so {u['name']} can verify it.
                4. If the answer isn't in the circulars, politely say you can't find it.
                """
                
                contents = [prompt_text] + gemini_files
                
                try:
                    resp = model.generate_content(contents).text
                    st.markdown(resp)
                    
                    st.session_state.messages.append({"role": "assistant", "content": resp})
                    all_chats = load_data(CHATS_FILE)
                    all_chats[u['pf']] = st.session_state.messages
                    save_data(CHATS_FILE, all_chats)
                except Exception as e:
                    st.error(f"An error occurred while reading the PDFs: {e}")
