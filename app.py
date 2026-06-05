import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import google.generativeai as genai
import io
import PyPDF2

st.set_page_config(page_title="CBI Silchar - Circular Assistant", page_icon="🏦", layout="centered")

# --- PUT YOUR FOLDER ID HERE ---
FOLDER_ID = "1gyuybMhyMQp3N-N2cmSrOgKBUf6iQ85y"
# -------------------------------

# --- SECURITY ---
def check_password():
    def password_entered():
        if st.session_state["password"] == "Silchar123":
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("Enter Branch Password", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Enter Branch Password", type="password", on_change=password_entered, key="password")
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

# This reads all your PDFs once and saves the text in memory so it's fast!
@st.cache_data(ttl=3600, show_spinner=False)
def get_all_circular_text():
    service = get_drive_service()
    results = service.files().list(q=f"'{FOLDER_ID}' in parents and mimeType='application/pdf'", fields="files(id, name)").execute()
    files = results.get('files', [])
    
    all_text = ""
    for file in files:
        request = service.files().get_media(fileId=file['id'])
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            
        fh.seek(0)
        reader = PyPDF2.PdfReader(fh)
        file_text = ""
        for page in reader.pages:
            text = page.extract_text()
            if text: file_text += text + "\n"
        
        all_text += f"\n--- Document: {file['name']} ---\n{file_text}\n"
    
    return all_text

# --- APP INTERFACE ---
if check_password():
    st.title("🏦 Smart Circular Assistant")
    st.write("Ask natural questions about the bank's policies.")

    # Department Menus
    departments = {
        "Operations": ["Account Opening", "KYC Norms", "Cash Handling", "Clearing"],
        "Credit": ["Retail Loans / Housing", "Agriculture / KCC", "MSME", "Recovery"],
        "HR or Staff Benefits": ["Leave Policy", "LFC / Travel", "Medical Benefits"],
        "Audit": ["Concurrent Audit", "Compliance Reports", "Risk Management"],
        "Miscellaneous": ["General Admin", "IT Security", "Premises", "Deceased Settlement"]
    }

    col1, col2 = st.columns(2)
    with col1:
        selected_dept = st.selectbox("Select Department", list(departments.keys()))
    with col2:
        selected_sub = st.selectbox("Select Sub-Department", departments[selected_dept])

    st.divider()

    # The AI Chat Interface
    query = st.text_area(f"🔍 Ask your question regarding {selected_sub}:", placeholder="e.g., What are the rules for settling a deceased account without a legal heir certificate?")
    
    if st.button("Ask AI", use_container_width=True):
        if query:
            with st.spinner("The AI is reading the circulars and typing an answer..."):
                try:
                    # 1. Grab all the text from the PDFs
                    document_text = get_all_circular_text()
                    
                    # 2. Give the AI strict instructions
                    prompt = f"""
                    You are a professional banking assistant for the Central Bank of India. 
                    Read the following official bank circulars carefully.
                    
                    BANK CIRCULARS:
                    {document_text}
                    
                    USER QUESTION: {query}
                    
                    INSTRUCTIONS:
                    1. Answer the user's question clearly and professionally based ONLY on the provided circular text.
                    2. If the answer is not contained in the text, you MUST say "I cannot find the answer to this in the uploaded circulars." Do not guess or make up bank policies.
                    3. Mention the name of the document you found the answer in.
                    """
                    
                    # 3. Get the answer
                    response = model.generate_content(prompt)
                    st.success("Answer Generated:")
                    st.write(response.text)
                    
                except Exception as e:
                    st.error(f"An error occurred: {e}")
        else:
            st.warning("Please type a question first.")
