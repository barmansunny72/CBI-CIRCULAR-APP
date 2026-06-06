import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import google.generativeai as genai
import io
import PyPDF2
import json
import os

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
# Using 1.5-flash because it natively supports reading raw PDF bytes
model = genai.GenerativeModel('gemini-1.5-flash')

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
        st.error(f"🚨 Google Drive Connection Error on Folder ID: `{folder_id}`.\n\nDetails: {e}")
        st.stop()

# --- ⚡ THE INLINE BYTES ENGINE (NO UPLOADING NEEDED) ---
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_and_prepare_documents(folder_id):
    service = get_drive_service()
    files = get_all_pdf_files_in_folder(service, folder_id)
    
    database = []
    for f in files:
        # Download the raw file bytes securely
        request = service.files().get_media(fileId=f['id'])
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
            
        pdf_bytes = fh.getvalue()
        
        # Try to extract text just for our local search algorithm to use
        extracted_text = ""
        try:
            fh.seek(0)
            reader = PyPDF2.PdfReader(fh)
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    extracted_text += text + "\n"
        except:
            pass # If it's a pure scanned image, text remains empty, but we still have the raw bytes!
            
        database.append({
            'name': f['name'],
            'text': extracted_text.lower(),
            'bytes': pdf_bytes
        })
        
    return database

def get_top_documents(query, database, context_string):
    stopwords = ['what', 'is', 'the', 'for', 'a', 'an', 'of', 'in', 'to', 'and', 'how', 'are', 'about', 'details', 'tell', 'me', 'can', 'you', 'find']
    query_words = [w.lower() for w in query.replace('?', '').split() if w.lower() not in stopwords]
    exact_query = query.lower().replace('?', '').strip()

    scored_docs = []
    for doc in database:
        score = 0
        name_lower = doc['name'].lower()
        text_lower = doc['text']
        
        # 1. FILENAME BOOST: Crucial for finding scanned PDFs!
        for qw in query_words:
            if qw in name_lower:
                score += 2000
                
        # 2. Exact phrase in text
        if exact_query in text_lower:
            score += 1000
            
        # 3. Context/Category boost
        if context_string.lower() in name_lower or context_string.lower() in text_lower:
            score += 300
            
        # 4. Keyword frequency
        for qw in query_words:
            score += (text_lower.count(qw) * 10)
            
        if score > 0:
            scored_docs.append({'score': score, 'doc': doc})
            
    scored_docs.sort(key=lambda x: x['score'], reverse=True)
    # We return the Top 2 most relevant PDFs to send to the AI
    return [item['doc'] for item in scored_docs[:2]]

# --- UI ---
if "user_data" not in st.session_state:
    st.title("🏦 Central Bank of India - Silchar")
    tab1, tab2 = st.tabs(["🔒 Login", "📝 Register"])
    users_db = load_data(USERS_FILE)
    
    with tab1:
        login_pf = st.text_input("PF Number", key="login")
        if st.button("Log In", type="primary"):
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
            st.cache_data.clear()
            st.success("Database synced! New circulars are now active.")

    st.title(f"Assistant: {dept}")
    
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
            with st.spinner("Scanning files and reading selected PDFs..."):
                # Fetch all documents in memory
                database = fetch_and_prepare_documents(active_folder_id)
                
                # Find the top 2 documents based on name and text
                top_docs = get_top_documents(query, database, sub if sub != "General" else dept)
                
                if not top_docs:
                    st.markdown("I couldn't find any circulars matching those keywords. Try different search terms.")
                    st.session_state.messages.append({"role": "assistant", "content": "I couldn't find any circulars matching those keywords. Try different search terms."})
                else:
                    doc_names = [d['name'] for d in top_docs]
                    st.write(f"🧠 *Running Native OCR on:* **{', '.join(doc_names)}**")
                    
                    history_text = ""
                    for msg in st.session_state.messages[-6:]: 
                        role_name = u['name'] if msg["role"] == "user" else "AI"
                        history_text += f"{role_name}: {msg['content']}\n"
                    
                    prompt_text = f"""
                    You are Gemini, a highly intelligent, friendly colleague at the Central Bank of India, Silchar Branch. 
                    You are helping {u['name']}. Speak to them naturally and warmly.
                    
                    --- CHAT HISTORY ---
                    {history_text}
                    
                    --- INSTRUCTIONS ---
                    I have attached the raw PDF files directly to this prompt. 
                    1. Run your native OCR to read the tables, text, and scanned images in these attached files.
                    2. Answer the user's question ({query}) based ONLY on these files.
                    3. Be conversational but concise. 
                    4. Always cite the Document Name at the end of your answer.
                    """
                    
                    # We pass the prompt AND the raw bytes directly to Gemini!
                    contents = [prompt_text]
                    for doc in top_docs:
                        contents.append({
                            "mime_type": "application/pdf",
                            "data": doc['bytes']
                        })
                    
                    try:
                        resp = model.generate_content(contents).text
                        st.markdown(resp)
                        
                        st.session_state.messages.append({"role": "assistant", "content": resp})
                        all_chats = load_data(CHATS_FILE)
                        all_chats[u['pf']] = st.session_state.messages
                        save_data(CHATS_FILE, all_chats)
                    except Exception as e:
                        st.error(f"An error occurred while generating the answer: {e}")
