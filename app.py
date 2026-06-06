import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import google.generativeai as genai
import io
import PyPDF2
import json
import os

# --- UI THEME UPGRADE ---
st.set_page_config(page_title="Central Bank of India Assistant", page_icon="🏦", layout="wide")

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
    query_pdfs = f"'{folder_id}' in parents and mimeType='application/pdf' and trashed=false"
    results = service.files().list(q=query_pdfs, fields="files(id, name)").execute()
    files.extend(results.get('files', []))
    
    query_folders = f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = service.files().list(q=query_folders, fields="files(id, name)").execute()
    subfolders = results.get('files', [])
    
    for sub in subfolders:
        files.extend(get_all_pdf_files_in_folder(service, sub['id']))
        
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
                all_pages.append(f"--- Document: {file['name']} (Page {page_num + 1}) ---\n{text}")
                
    return all_pages

def find_relevant_pages(query, all_pages, context_string):
    stopwords = ['what', 'is', 'the', 'for', 'a', 'an', 'of', 'in', 'to', 'and', 'how', 'are', 'about', 'details', 'policy', 'rules', 'guidelines', 'bank', 'branch', 'staff', 'central', 'maximum', 'minimum', 'amount']
    clean_words = [word.lower() for word in query.replace('?', '').split() if len(word) > 2]
    keywords = [w for w in clean_words if w not in stopwords]
    
    paired_words = []
    for i in range(len(clean_words) - 1):
        paired_words.append(f"{clean_words[i]} {clean_words[i+1]}")
        
    scored_pages = []
    for page in all_pages:
        score = 0
        page_lower = page.lower()
        first_line = page_lower.split('\n')[0] 
        
        matches = sum(1 for kw in keywords if kw in page_lower)
        if matches > 0:
            score += (matches * 10)
            for pair in paired_words:
                if pair in page_lower: score += 500 
                if pair in first_line: score += 2000 
            # Check if the context string (e.g., "Master Credit Policy") is in the page
            if context_string.lower() in first_line or context_string.lower() in page_lower:
                score += 300
            scored_pages.append({'score': score, 'text': page})
            
    scored_pages.sort(key=lambda x: x['score'], reverse=True)
    top_pages = [page['text'] for page in scored_pages[:20]]
    return "\n".join(top_pages)

# --- 1. THE AUTHENTICATION PORTAL ---
if "user_data" not in st.session_state:
    st.title("🏦 Central Bank of India - Silchar Branch")
    st.write("Welcome to the Smart Circular Assistant. Please log in or register.")
    
    users_db = load_data(USERS_FILE)
    
    tab1, tab2 = st.tabs(["🔒 Staff Login", "📝 Register New Staff"])
    
    with tab1:
        login_pf = st.text_input("PF Number (6 digits)", key="login_pf")
        if st.button("Log In", type="primary"):
            if login_pf in users_db:
                st.session_state["user_data"] = {"name": users_db[login_pf], "pf": login_pf}
                all_chats = load_data(CHATS_FILE)
                st.session_state["messages"] = all_chats.get(login_pf, [])
                st.rerun()
            else:
                st.error("⚠️ PF Number not found. Please register first.")
                
    with tab2:
        reg_name = st.text_input("Full Name")
        reg_pf = st.text_input("PF Number (6 digits)", key="reg_pf")
        if st.button("Register & Create Account"):
            if len(reg_pf) != 6 or not reg_pf.isdigit():
                st.error("⚠️ PF Number must be exactly 6 digits.")
            elif not reg_name:
                st.error("⚠️ Please enter your full name.")
            elif reg_pf in users_db:
                st.error("⚠️ This PF Number is already registered to another staff member.")
            else:
                users_db[reg_pf] = reg_name
                save_data(USERS_FILE, users_db)
                st.success(f"✅ Account created successfully for {reg_name}! You can now log in.")

# --- 2. THE MAIN APP ---
else:
    user_name = st.session_state["user_data"]["name"]
    pf_num = st.session_state["user_data"]["pf"]
    
    with st.sidebar:
        st.title("🏦 Central Bank of India")
        st.caption("Silchar Branch Assistant")
        st.success(f"👤 Logged in as:\n**{user_name}** (PF: {pf_num})")
        if st.button("Log Out"):
            del st.session_state["user_data"]
            del st.session_state["messages"]
            st.rerun()
            
        st.divider()
        
        st.subheader("📁 Step 1: Select Context")
        
        departments = {
            "Recovery": [],
            "Operations": [],
            "Miscellaneous": [],
            "IT/Digital Section": [],
            "Human Resource/Staff welfare": [],
            "Credit/Advance": ["Retail", "MSME", "Agri", "Master Credit Policy"],
            "Credit Monitoring": []
        }
        
        selected_dept = st.selectbox("Main Department", list(departments.keys()))
        
        if departments[selected_dept]:
            # Updated UI text to make more sense to staff
            selected_sub = st.selectbox("Category / Specific Policy", departments[selected_dept])
            context_string = selected_sub
        else:
            selected_sub = None
            context_string = selected_dept
            
        active_folder_id = FOLDER_MAP[selected_dept]

    # --- 3. THE CHATBOT UI ---
    st.title(f"Assistant: {selected_dept}")
    if selected_sub:
        st.markdown(f"*Searching within: **{selected_sub}***")
    st.divider()
    
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    search_label = selected_sub if selected_sub else selected_dept
    query = st.chat_input(f"Ask a question regarding {search_label}...")

    if query:
        st.session_state.messages.append({"role": "user", "content": query})
        with st.chat_message("user"):
            st.markdown(query)
            
        with st.chat_message("assistant"):
            with st.status(f"Searching {selected_dept} archives...", expanded=True) as status:
                st.write("📥 Reading policies (including sub-folders)...")
                all_pages = get_all_pdf_pages(active_folder_id)
                
                st.write("🔍 Finding relevant rules...")
                document_text = find_relevant_pages(query, all_pages, context_string)
                
                history_text = ""
                for msg in st.session_state.messages[-6:]: 
                    role_name = user_name if msg["role"] == "user" else "AI"
                    history_text += f"{role_name}: {msg['content']}\n"
                
                if not document_text.strip():
                    status.update(label="⚠️ No matches found", state="error", expanded=False)
                    st.warning("I couldn't find any circulars mentioning those exact keywords.")
                else:
                    st.write("🧠 Reading chat history and formulating response...")
                    
                    prompt = f"""
                    You are Gemini, acting as a highly intelligent, friendly, and conversational banking assistant for the Central Bank of India, Silchar Branch.
                    You are speaking directly with staff member: {user_name} (PF: {pf_num}). Talk to them naturally, like a helpful colleague.
                    
                    --- RECENT CONVERSATION MEMORY ---
                    {history_text}
                    
                    --- BANK CIRCULARS (Context for current question) ---
                    {document_text}
                    
                    USER'S NEW QUESTION: {query}
                    
                    INSTRUCTIONS:
                    1. Maintain your natural, conversational Gemini personality, but when it comes to facts and bank rules, you MUST base your answer strictly on the provided Bank Circulars. 
                    2. Read the Recent Conversation Memory to understand the context of follow-up questions.
                    3. Always cite the Document Name(s) and Page Number(s) so {user_name} can verify the information.
                    4. If the answer is not in the circulars, politely say that you cannot find the exact answer in the current documents.
                    """
                    
                    try:
                        response = model.generate_content(prompt)
                        status.update(label="✅ Answer Generated!", state="complete", expanded=False)
                        st.markdown(response.text)
                        
                        st.session_state.messages.append({"role": "assistant", "content": response.text})
                        
                        all_chats = load_data(CHATS_FILE)
                        all_chats[pf_num] = st.session_state.messages
                        save_data(CHATS_FILE, all_chats)
                        
                    except Exception as e:
                        status.update(label="⚠️ Error", state="error", expanded=False)
                        st.error(f"An error occurred: {e}")
