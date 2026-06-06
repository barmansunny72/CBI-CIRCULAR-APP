import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import google.generativeai as genai
import io
import PyPDF2
import re

# --- UI THEME UPGRADE ---
st.set_page_config(page_title="CBI Circular Assistant", page_icon="🏦", layout="wide")

# --- PUT YOUR FOLDER ID HERE ---
FOLDER_ID = "1gyuybMhyMQp3N-N2cmSrOgKBUf6iQ85y"
# -------------------------------

# --- SECURITY ---
def check_password():
    def password_entered():
        if st.session_state["password"] == "cbi@123":
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state or not st.session_state["password_correct"]:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.title("🔒 Branch Login")
            st.write("Please enter the branch password to access internal circulars.")
            st.text_input("Password", type="password", on_change=password_entered, key="password")
            if "password_correct" in st.session_state and not st.session_state["password_correct"]:
                st.error("Incorrect Password.")
        return False
    return True

# --- AI & DRIVE SETUP (UPGRADED TO PRO MODEL) ---
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
# Using the PRO model because you are on the paid tier for maximum intelligence
model = genai.GenerativeModel('gemini-1.5-pro-latest')

@st.cache_resource
def get_drive_service():
    creds = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=['https://www.googleapis.com/auth/drive.readonly']
    )
    return build('drive', 'v3', credentials=creds)

@st.cache_data(ttl=3600, show_spinner=False)
def get_all_pdf_pages():
    service = get_drive_service()
    results = service.files().list(q=f"'{FOLDER_ID}' in parents and mimeType='application/pdf'", fields="files(id, name)").execute()
    files = results.get('files', [])
    
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
                # Store the Document Name, Page Number, and Text
                all_pages.append(f"--- Document: {file['name']} (Page {page_num + 1}) ---\n{text}")
                
    return all_pages

# --- NEW: THE UNLOCKED SMART LIBRARIAN ---
def find_relevant_pages(query, all_pages):
    # Remove common filler words so we only search for the core subject
    stopwords = ['what', 'is', 'the', 'for', 'a', 'an', 'of', 'in', 'to', 'and', 'how', 'are', 'about', 'details', 'my', 'i', 'need', 'tell', 'me', 'can', 'you', 'find']
    keywords = [word.lower() for word in query.replace('?', '').split() if word.lower() not in stopwords and len(word) > 2]
    
    scored_pages = []
    
    for page in all_pages:
        score = 0
        page_lower = page.lower()
        
        # Give massive bonus points if the keywords appear right next to each other
        for kw in keywords:
            score += page_lower.count(kw)
        
        # Exact phrase matching bonus (e.g. "staff transfer policy")
        phrase = " ".join(keywords)
        if phrase in page_lower:
            score += 50 
            
        if score > 0:
            scored_pages.append({'score': score, 'text': page})
            
    # Sort the pages so the highest scores are at the top
    scored_pages.sort(key=lambda x: x['score'], reverse=True)
    
    # PAID TIER UPGRADE: Grab the top 25 pages of data to give the AI massive context
    top_pages = [page['text'] for page in scored_pages[:25]]
    
    return "\n".join(top_pages)

# --- APP INTERFACE ---
if check_password():
    
    with st.sidebar:
        st.title("🏦 CBI Silchar")
        st.caption("Internal Branch Tool")
        st.divider()
        
        st.subheader("📁 Filter Context")
        departments = {
            "Operations": ["Account Opening", "KYC Norms", "Cash Handling", "Clearing"],
            "Credit": ["Retail Loans / Housing", "Agriculture / KCC", "MSME", "Recovery"],
            "HR or Staff Benefits": ["Leave Policy", "LFC / Travel", "Medical Benefits"],
            "Audit": ["Concurrent Audit", "Compliance Reports", "Risk Management"],
            "Miscellaneous": ["General Admin", "IT Security", "Premises", "Deceased Settlement"]
        }
        selected_dept = st.selectbox("Main Department", list(departments.keys()))
        selected_sub = st.selectbox("Sub-Department", departments[selected_dept])
        
        st.divider()
        st.success("🟢 System Online (Pro Tier)")

    st.title("Smart Circular Assistant ✨")
    st.markdown("*Your AI-powered guide for internal banking policies and operational guidelines.*")
    
    with st.expander("📖 How to use this tool"):
        st.write("1. **Filter** your department on the left sidebar so the AI knows the context.\n2. **Type** your query in plain English below.\n3. The AI will read the latest branch PDFs and summarize the rules for you.")

    st.divider()

    st.subheader(f"Ask a question regarding: **{selected_sub}**")
    query = st.text_input("🔍 Question:", placeholder="e.g., What are the required annexes for settling a deceased claim without a nominee?")
    
    if st.button("Ask the AI 🤖", type="primary", use_container_width=True):
        if query:
            with st.status("Analyzing bank policies...", expanded=True) as status:
                st.write("📥 Loading PDFs from Google Drive...")
                all_pages = get_all_pdf_pages()
                
                st.write("🔍 Gathering comprehensive context...")
                document_text = find_relevant_pages(query, all_pages)
                
                if not document_text.strip():
                    status.update(label="⚠️ No matches found", state="error", expanded=False)
                    st.warning("I couldn't find any circulars mentioning those exact keywords. Try simplifying your search words.")
                else:
                    st.write("🧠 Pro AI reading policies and connecting data...")
                    prompt = f"""
                    You are a professional banking assistant for the Central Bank of India. 
                    Read the following official bank circular pages carefully.
                    
                    BANK CIRCULARS:
                    {document_text}
                    
                    USER QUESTION: {query}
                    
                    INSTRUCTIONS:
                    1. Answer the user's question comprehensively based ONLY on the provided circular text.
                    2. Connect information across different documents if necessary.
                    3. If the answer is not contained in the text, you MUST say "I cannot find the exact answer to this in the uploaded circulars." Do not guess.
                    4. Always cite the Document Name(s) and Page Number(s) you used to formulate the answer.
                    """
                    
                    try:
                        response = model.generate_content(prompt)
                        status.update(label="✅ Answer Generated!", state="complete", expanded=False)
                        st.markdown("### 📋 Official Policy Breakdown:")
                        st.info(response.text)
                        st.caption("⚠️ Note: Always verify critical data with the original physical circular.")
                    except Exception as e:
                        status.update(label="⚠️ Error", state="error", expanded=False)
                        st.error(f"An error occurred: {e}")
        else:
            st.warning("Please type a question first.")
