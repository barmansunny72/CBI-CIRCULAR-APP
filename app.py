import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import google.generativeai as genai
import io
import PyPDF2

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

# NEW: Reads PDFs and separates them page-by-page so we don't overload the AI
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
                all_pages.append(f"--- Document: {file['name']} (Page {page_num + 1}) ---\n{text}")
                
    return all_pages

# NEW: Acts like a librarian, picking only the relevant pages to send to the AI
def find_relevant_pages(query, all_pages):
    # Remove common words to find the real keywords
    stopwords = ['what', 'is', 'the', 'for', 'a', 'an', 'of', 'in', 'to', 'and', 'how', 'are', 'rules', 'policy', 'about', 'details']
    keywords = [word.lower() for word in query.replace('?', '').split() if word.lower() not in stopwords and len(word) > 2]
    
    relevant_pages = []
    for page in all_pages:
        # If the page contains any of our question's keywords, grab it
        if any(kw in page.lower() for kw in keywords):
            relevant_pages.append(page)
            
   # Only return the top 3 most relevant pages so we don't crash the free AI limit
return "\n".join(relevant_pages[:3])

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
        st.success("🟢 System Online")

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
                
                st.write("🔍 Scanning for relevant paragraphs...")
                document_text = find_relevant_pages(query, all_pages)
                
                if not document_text.strip():
                    status.update(label="⚠️ No matches found", state="error", expanded=False)
                    st.warning("I couldn't find any circulars mentioning those exact keywords. Try simplifying your search words.")
                else:
                    st.write("🧠 Reading policies and generating response...")
                prompt = f"""
                You are a professional banking assistant for the Central Bank of India. 
                Read the following official bank circular pages carefully.
                
                BANK CIRCULARS:
                {document_text}
                
                USER QUESTION: {query}
                
                INSTRUCTIONS:
                1. Answer the user's question clearly, professionally, and step-by-step based ONLY on the provided circular text.
                2. If the answer is not contained in the text, you MUST say "I cannot find the exact answer to this in the uploaded circulars." Do not guess.
                3. Always mention the Document Name and Page Number you got the answer from.
                """
                
                try:
                    response = model.generate_content(prompt)
                    status.update(label="✅ Answer Generated!", state="complete", expanded=False)
                    st.markdown("### 📋 Official Policy Breakdown:")
                    st.info(response.text)
                    st.caption("⚠️ Note: Always verify critical data with the original physical circular.")
                    
                except Exception as e:
                    status.update(label="⚠️ Network Busy", state="error", expanded=False)
                    if "429" in str(e) or "ResourceExhausted" in str(e):
                        st.error("⏳ The AI servers are currently busy (Free Tier Limit). Please wait 60 seconds and try your question again.")
                    else:
                        st.error(f"An unexpected error occurred: {e}")
