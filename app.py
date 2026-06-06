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
    # Fetch all PDFs and sub-folders recursively
    results = service.files().list(q=f"'{folder_id}' in parents and (mimeType='application/pdf' or mimeType='application/vnd.google-apps.folder') and trashed=false", fields="files(id, name, mimeType)").execute()
    for item in results.get('files', []):
        if item['mimeType'] == 'application/pdf':
            files.append(item)
        elif item['mimeType'] == 'application/vnd.google-apps.folder':
            files.extend(get_all_pdf_files_in_folder(service, item['id']))
    return files

@st.cache_data(ttl=3600, show_spinner=False)
def get_all_pdf_pages(active_folder_id):
    service = get_drive_service()
    files = get_all_pdf_files_in_folder(service, active_folder_id)
    all_pages = []
    for file in files:
        request = service.files().get_media(fileId=file['id'])
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.seek(0)
        reader = PyPDF2.PdfReader(fh)
        for page_num, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                # We store the File Name directly in the text so the AI can read it
                all_pages.append(f"--- Source: {file['name']} (Page {page_num + 1}) ---\n{text}")
    return all_pages

# --- UPGRADED SMART SCORING ---
def find_relevant_pages(query, all_pages, context_string):
    scored_pages = []
    # Remove common filler words to find the core subject
    stopwords = ['what', 'is', 'the', 'for', 'a', 'an', 'of', 'in', 'to', 'and', 'how', 'are', 'about', 'details', 'tell', 'me', 'can', 'you', 'find']
    query_words = [w.lower() for w in query.replace('?', '').split() if w.lower() not in stopwords]
    exact_query = query.lower().replace('?', '').strip()

    for page in all_pages:
        score = 0
        page_lower = page.lower()
        first_line = page_lower.split('\n')[0] # This contains the PDF file name
        
        # 1. FILENAME MATCH (The Silver Bullet)
        # If they ask for "personal loan" and the file is "CENT_PERSONAL.pdf", give it massive points!
        for qw in query_words:
            if qw in first_line:
                score += 2000 
                
        # 2. Exact phrase match in the document text
        if exact_query in page_lower:
            score += 1000

        # 3. Category Bias (If they selected Retail, boost retail documents)
        if context_string.lower() in page_lower or context_string.lower() in first_line:
            score += 300 
            
        # 4. General Keyword Matches
        for qw in query_words:
            score += (page_lower.count(qw) * 10)

        if score > 0:
            scored_pages.append({'score': score, 'text': page})
            
    scored_pages.sort(key=lambda x: x['score'], reverse=True)
    
    # PAID TIER UPGRADE: We are now passing the top 50 pages to the AI instead of 15!
    # This guarantees it reads Page 2 AND Page 3 of long circulars.
    return "\n".join([p['text'] for p in scored_pages[:50]])

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
        if st.button("Log Out"): st.session_state.clear(); st.rerun()

    st.title(f"Assistant: {dept}")
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])

    if query := st.chat_input("Ask a question..."):
        st.session_state.messages.append({"role": "user", "content": query})
        with st.chat_message("user"): st.markdown(query)
        
        with st.chat_message("assistant"):
            # Replaced the clickable status box with a temporary spinner
            with st.spinner("Reading branch circulars and finding the exact rule..."):
                pages = get_all_pdf_pages(FOLDER_MAP[dept])
                context = find_relevant_pages(query, pages, sub if sub != "General" else dept)
                
                # Humanized Prompt 
                prompt = f"""
                You are a highly intelligent, friendly colleague at the Central Bank of India, Silchar Branch. 
                You are helping {u['name']}. Speak to them naturally and warmly.
                
                CIRCULARS TO READ:
                {context}
                
                QUESTION: {query}
                
                RULES: 
                1. Base your answer strictly on the Circulars provided. 
                2. Be conversational but concise. 
                3. Always cite the Document Name and Page Number at the end of your answer.
                4. If the answer isn't in the circulars, politely say you can't find it.
                """
                
                resp = model.generate_content(prompt).text
                
            # The answer will immediately appear in the chat stream without needing to be clicked!
            st.markdown(resp)
            st.session_state.messages.append({"role": "assistant", "content": resp})
            all_chats = load_data(CHATS_FILE)
            all_chats[u['pf']] = st.session_state.messages
            save_data(CHATS_FILE, all_chats)
