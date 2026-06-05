import streamlit as st

# Configure the app for mobile screens
st.set_page_config(page_title="CBI Silchar - Circular Assistant", page_icon="🏦", layout="centered")

# --- SECURITY: Simple Login Screen ---
def check_password():
    """Returns True if the user has entered the correct password."""
    def password_entered():
        if st.session_state["password"] == "Silchar123": # You can change this password
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Don't store password
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("Enter Branch Password", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Enter Branch Password", type="password", on_change=password_entered, key="password")
        st.error("Incorrect Password. Please try again.")
        return False
    return True

# --- MAIN APP UI ---
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

    # Dropdowns for mobile-friendly filtering
    col1, col2 = st.columns(2)
    with col1:
        selected_dept = st.selectbox("Select Department", list(departments.keys()))
    with col2:
        selected_sub = st.selectbox("Select Sub-Department", departments[selected_dept])

    st.divider()

    # The Search Interface
    query = st.text_area("🔍 Ask your doubt:", placeholder="e.g., What is the maximum quantum of staff housing loan?")
    
    if st.button("Search Circulars", use_container_width=True):
        if query:
            with st.spinner("Scanning circulars..."):
                # NOTE: This is where we will integrate the Google Drive PDF reader logic
                st.success("Draft Answer Example:")
                st.write(f"**Based on {selected_dept} > {selected_sub} circulars:**")
                st.info("The maximum quantum of staff housing loan is up to 75 Lakhs, subject to 60 months' gross salary. \n\n*Source: Circular 2026/14 (Paragraph 3.2)*")
        else:
            st.warning("Please type a question first.")