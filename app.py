import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io
import PyPDF2

st.set_page_config(page_title="CBI Silchar - Circular Assistant", page_icon="🏦", layout="centered")

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

    if "password_correct" not in st.session_state:
        st.text_input("Enter Branch Password", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Enter Branch Password", type="password", on_change=password_entered, key="password")
        st.error("Incorrect Password.")
        return False
    return True

# --- GOOGLE DRIVE CONNECTION ---
@st.cache_resource
def get_drive_service():
    creds = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=['https://www.googleapis.com/auth/drive.readonly']
    )
    return build('drive', 'v3', credentials=creds)

def search_pdfs(query):
    service = get_drive_service()
    results = service.files().list(q=f"'{FOLDER_ID}' in parents and mimeType='application/pdf'", fields="files(id, name)").execute()
    files = results.get('files', [])
    
    found_snippets = []
    for file in files:
        request = service.files().get_media(fileId=file['id'])
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            
        fh.seek(0)
        reader = PyPDF2.PdfReader(fh)
        for page_num, page in enumerate(reader.pages):
            text = page.extract_text()
            if text and query.lower() in text.lower():
                found_snippets.append(f"**Found in: {file['name']} (Page {page_num + 1})**\n\n... {text[:400]} ...")
    
    return found_snippets

# --- APP INTERFACE ---
if check_password():
    st.title("🏦 Circular Assistant")
    st.write("Search the latest guidelines and circulars.")

    # Department Selection Structure
    departments = {
        "Operations": ["Account Opening", "KYC Norms", "Cash Handling", "Clearing"],
        "Credit": ["Retail Loans / Housing", "Agriculture / KCC", "MSME", "Recovery"],
        "HR or Staff Benefits": ["Leave Policy", "LFC / Travel", "Medical Benefits"],
        "Audit": ["Concurrent Audit", "Compliance Reports", "Risk Management"],
        "Miscellaneous": ["General Admin", "IT Security", "Premises"]
    }

    col1, col2 = st.columns(2)
    with col1:
        selected_dept = st.selectbox("Select Department", list(departments.keys()))
    with col2:
        selected_sub = st.selectbox("Select Sub-Department", departments[selected_dept])

    st.divider()

    st.info("💡 Tip: Type a single keyword (like 'audit' or 'leave') rather than a full sentence.")
    query = st.text_input(f"🔍 Search within {selected_sub}:")
    
    if st.button("Search Circulars", use_container_width=True):
        if query:
            with st.spinner("Scanning Google Drive PDFs..."):
                results = search_pdfs(query)
                if results:
                    st.success(f"Found {len(results)} matching sections!")
                    for res in results:
                        st.write(res)
                        st.divider()
                else:
                    st.warning("No matches found. Try a different keyword.")
        else:
            st.warning("Please type a search word first.")
