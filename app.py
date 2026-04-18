import streamlit as st
import pandas as pd
import os
import re
import pycountry
from datetime import datetime
import requests
import speech_recognition as sr
import firebase_admin
from firebase_admin import credentials, firestore

# ---------------- FIREBASE INIT ----------------
if not firebase_admin._apps:
    cred = credentials.Certificate(dict(st.secrets["firebase"]))
    firebase_admin.initialize_app(cred)

db = firestore.client()
GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
st.set_page_config(page_title="Health AI", layout="wide")




# ---------------- FUNCTIONS ----------------
def load_profiles():
    docs = db.collection("profiles").stream()

    rows = []
    for doc in docs:
        rows.append(doc.to_dict())

    if rows:
        return pd.DataFrame(rows)

    return pd.DataFrame(columns=[
        "user",
        "phone",
        "country",
        "state",
        "age",
        "gender",
        "patient_id"
    ])
    
def save_profile(username, phone, country, state, age, gender, p_id):
    db.collection("profiles").document(username).set({
        "user": username,
        "phone": phone,
        "country": country,
        "state": state,
        "age": age,
        "gender": gender,
        "patient_id": p_id
    })
    
def load_notes():
    docs = db.collection("notes").stream()

    rows = []
    for doc in docs:
        rows.append(doc.to_dict())

    if rows:
        return pd.DataFrame(rows)

    return pd.DataFrame(columns=[
        "user",
        "day",
        "note",
        "tag",
        "time"
    ])

def save_notes(df):
    current_user = st.session_state.username

    docs = db.collection("notes").where("user", "==", current_user).stream()

    for d in docs:
        d.reference.delete()

    user_df = df[df["user"] == current_user]

    for _, row in user_df.iterrows():
        db.collection("notes").add(row.to_dict())

def save_doctor(doc_id, password, name, hospital_code):
    db.collection("doctors").document(doc_id).set({
        "doc_id": doc_id,
        "password": password,
        "name": name,
        "h_code": hospital_code
    })




def check_doctor_login(doc_id, password):
    doc = db.collection("doctors").document(doc_id).get()

    if doc.exists:
        data = doc.to_dict()
        return data["password"] == password

    return False

def valid_username(username):
    return len(username) >= 4 and username.isalnum()

def valid_password(password):
    return (len(password) >= 6 and re.search("[A-Z]", password) and re.search("[0-9]", password))

def save_user(username, password):
    user_ref = db.collection("users").document(username)

    if user_ref.get().exists:
        return False

    user_ref.set({
        "username": username,
        "password": password
    })
    return True

def check_login(username, password):
    doc = db.collection("users").document(username).get()

    if doc.exists:
        data = doc.to_dict()
        return data["password"] == password

    return False

def load_meds():
    docs = db.collection("medications").stream()

    rows = []
    for doc in docs:
        rows.append(doc.to_dict())

    if rows:
        df = pd.DataFrame(rows)

        if "taken_log" not in df.columns:
            df["taken_log"] = ""

        if "dose" not in df.columns:
            df["dose"] = 0

        df["taken_log"] = df["taken_log"].astype(str)
        df["dose"] = pd.to_numeric(df["dose"], errors="coerce").fillna(0)

        return df

    return pd.DataFrame(columns=[
        "user",
        "name",
        "dose",
        "time",
        "food",
        "taken_log"
    ])


def save_meds(df):
    current_user = st.session_state.username

    docs = db.collection("medications").where("user", "==", current_user).stream()

    for d in docs:
        d.reference.delete()

    user_df = df[df["user"] == current_user]

    for _, row in user_df.iterrows():
        db.collection("medications").add(row.to_dict())

def ask_groq_health_bot(question):
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {
                    "role": "system",
                    "content": """
You are a professional medical assistant inside a healthcare app.
Give short clear answers.
Help with medicines, diet, symptoms, reminders, motivation.
Never diagnose dangerous disease with certainty.
If emergency symptoms say seek doctor immediately.
"""
                },
                {
                    "role": "user",
                    "content": question
                }
            ],
            "temperature": 0.4
        }

        r = requests.post(url, headers=headers, json=payload, timeout=20)
        data = r.json()

        if "choices" in data:
            return data["choices"][0]["message"]["content"]

        return "Sorry, I could not answer now."

    except:
        return "Connection issue while contacting AI."

# ---------------- SESSION ----------------
if "role" not in st.session_state:
    st.session_state.role = None  
    
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.page = "login"
    st.session_state.day = 1
    st.session_state.profile_complete = False

if "diet_log" not in st.session_state:
    st.session_state.diet_log = {}
    # --- ADD THESE TWO LINES HERE ---
if "user_diet_plans" not in st.session_state:
    st.session_state.user_diet_plans = {}

if "food_journal" not in st.session_state:
    st.session_state.food_journal = {}

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "voice_question" not in st.session_state:
    st.session_state.voice_question = ""

if "voice_answer" not in st.session_state:
    st.session_state.voice_answer = "Hello, I am your AI Health Assistant."

# ---------------- UI STYLING ----------------
# Default Background (Patient Portal - Blue)
bg_style = """
<style>
header {visibility:hidden;}
[data-testid="stAppViewContainer"] {
    background: radial-gradient(circle at 20% 20%, #1e3a8a, transparent 40%), 
                radial-gradient(circle at 80% 30%, #0ea5e9, transparent 40%), #020617 !important;
}
"""

# ROLE SELECTION PAGE: Now Indigo (Doctor's old style)
if st.session_state.role is None:
    bg_style = """
    <style>
    header {visibility:hidden;}
    [data-testid="stAppViewContainer"] {
        background: radial-gradient(circle at 10% 10%, #312e81, transparent 50%), 
                    radial-gradient(circle at 90% 90%, #1e1b4b, transparent 50%), #020617 !important;
    }
    """

# DOCTOR PORTAL: Now Emerald/Green (Role selection's old style)
elif st.session_state.role == "doctor":
    bg_style = """
    <style>
    header {visibility:hidden;}
    [data-testid="stAppViewContainer"] {
        background: radial-gradient(circle at 20% 20%, #064e3b, transparent 40%), 
                    radial-gradient(circle at 80% 30%, #134e4a, transparent 40%), #020617 !important;
    }
    """

st.markdown(bg_style + """
/* Forces all buttons to be equal width and centered */
.stButton button {
    width: 100% !important; 
    height: 50px !important;
    display: flex !important;
    justify-content: center !important;
    align-items: center !important;
    border-radius: 15px !important;
    background: rgba(255, 255, 255, 0.05) !important;
    color: white !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
    backdrop-filter: blur(10px) !important;
    transition: all 0.3s ease !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
}

.stButton button:hover {
    background: rgba(255, 255, 255, 0.15) !important;
    border-color: rgba(0, 163, 255, 0.5) !important;
    box-shadow: 0 0 20px rgba(0, 163, 255, 0.4) !important;
    transform: translateY(-2px) !important;
}

.card { padding: 20px; border-radius: 20px; background: rgba(255,255,255,0.05); color: white; margin-bottom: 10px; }
.glass { width: 400px; margin: auto; padding: 40px; border-radius: 30px; background: rgba(255,255,255,0.08); backdrop-filter: blur(25px); border: 1px solid rgba(255, 255, 255, 0.1); }
.landing-card { background: rgba(255, 255, 255, 0.02); backdrop-filter: blur(25px); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 40px; padding: 60px 40px; text-align: center; margin-top: 30px; }
.main-title { color: white; font-size: 50px; font-weight: 800; letter-spacing: -1px; margin-bottom: 5px; background: -webkit-linear-gradient(#fff, #94a3b8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.sub-title { color: #94a3b8; font-size: 18px; margin-bottom: 40px; }
</style>
""", unsafe_allow_html=True)

# ---------------- 1. INITIAL ROLE SELECTION ----------------
if st.session_state.role is None:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown('<div class="landing-card">', unsafe_allow_html=True)
        st.markdown('<h1 class="main-title">HEALTH AI</h1>', unsafe_allow_html=True)
        st.markdown('<p class="sub-title">Advanced Biomedical Monitoring System</p>', unsafe_allow_html=True)
        
        role_col1, role_col2 = st.columns(2)
        with role_col1:
            st.markdown("### 👨‍⚕️")
            if st.button("DOCTOR PORTAL"):
                st.session_state.role = "doctor"
                st.rerun()
            st.caption("Clinical Insights")
                
        with role_col2:
            st.markdown("### 👤")
            if st.button("PATIENT PORTAL"):
                st.session_state.role = "patient"
                st.rerun()
            st.caption("Personal Health Log")
        st.markdown('</div>', unsafe_allow_html=True)

# ---------------- 2. DOCTOR PORTAL (LOGIN & REGISTER) ----------------
elif st.session_state.role == "doctor":
    # Doctor Mesh Background
    st.markdown("""<style>[data-testid="stAppViewContainer"] { background: radial-gradient(circle at 10% 10%, #312e81, transparent 50%), radial-gradient(circle at 90% 90%, #1e1b4b, transparent 50%), #020617; }</style>""", unsafe_allow_html=True)
    
    if not st.session_state.logged_in:
        col1, col2, col3 = st.columns([1, 1.2, 1])
        with col2:
            st.markdown('<div class="glass" style="border-color: #6366f1; width: 100%;">', unsafe_allow_html=True)
            
            # --- DOCTOR LOGIN ---
            if st.session_state.page == "login":
                st.subheader("👨‍⚕️ Doctor Login")
                doc_id_in = st.text_input("License ID (4-Digits)", key="doc_login_id")
                doc_pass_in = st.text_input("Password", type="password", key="doc_login_pass")
                
                b_col1, b_col2 = st.columns(2)
                with b_col1:
                    # Added unique key to avoid StreamlitDuplicateElementId
                    if st.button("Login", key="doc_login_btn"):
                        if check_doctor_login(doc_id_in, doc_pass_in):
                            st.session_state.logged_in = True
                            st.session_state.username = doc_id_in  
                            st.success("Access Granted.")
                            st.rerun()
                        else:
                            st.error("❌ Invalid ID or Password. Please ensure you have registered.")
                
                with b_col2:
                    # Added unique key to avoid StreamlitDuplicateElementId
                    if st.button("Register", key="doc_goto_reg"):
                        st.session_state.page = "create"
                        st.rerun()
                
                st.write("---")
                if st.button("↩️ Switch Role", key="doc_switch_role_login"):
                    st.session_state.role = None
                    st.rerun()
                    
            # --- DOCTOR REGISTER ---
            else:
                st.subheader("🆕 Doctor Registration")
                doc_name = st.text_input("Full Name", key="doc_reg_name")
                h_code = st.text_input("Hospital Code (4 Digits)", key="doc_reg_hcode")
                new_pass = st.text_input("Set Password", type="password", help="6+ chars, 1 Uppercase, 1 Number", key="doc_reg_pass")
                
                b_col1, b_col2 = st.columns(2)
                with b_col1:
                    # Added unique key to avoid StreamlitDuplicateElementId
                    if st.button("Register", key="doc_final_reg_btn"):
                        if len(h_code) != 4 or not h_code.isdigit():
                            st.error("❌ Enter a valid 4-digit Hospital Code")
                        elif not valid_password(new_pass):
                            st.error("⚠️ Weak Password!")
                        else:
                            import random
                            generated_id = str(random.randint(1000, 9999))
                            
                            # Save to doctors.csv permanently
                            save_doctor(generated_id, new_pass, doc_name, h_code)
                            
                            st.success("✅ Registration Successful!")
                            st.markdown(f"""
                                <div style="background:rgba(99, 102, 241, 0.2); padding:15px; border-radius:10px; border:1px solid #6366f1; text-align:center;">
                                    <p style="margin:0; color:#c7d2fe;">Your PERMANENT License ID:</p>
                                    <h2 style="margin:0; color:white; letter-spacing:5px;">{generated_id}</h2>
                                </div>
                                """, unsafe_allow_html=True)
                            st.info("Use this ID to Login.")
                
                with b_col2:
                    # Added unique key to avoid StreamlitDuplicateElementId
                    if st.button("Back", key="doc_reg_back"):
                        st.session_state.page = "login"
                        st.rerun()

                st.write("---")
                if st.button("↩️ Switch Role Selection", key="doc_switch_role_reg"):
                    st.session_state.role = None
                    st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
    
    else:
        # ---------------- DOCTOR DASHBOARD (HOSPITAL MGMT) ----------------
        st.title("🏥 Hospital Management Dashboard")
        if st.button("Logout", key="doc_logout_btn"):
            st.session_state.logged_in = False
            st.rerun()
            
        search_id = st.text_input("🔍 Enter Patient 4-Digit ID to Manage", placeholder="e.g. 5421", key="patient_search_input")
        
        if search_id:
            all_profs = load_profiles()
            # Search for the patient by ID
            all_profs['patient_id'] = all_profs['patient_id'].astype(str).str.replace('.0', '', regex=False).str.strip()

            # Second, perform an EXACT match check
            target_patient = all_profs[all_profs["patient_id"] == search_id.strip()]
            if not target_patient.empty:
                p_user = target_patient.iloc[0]["user"]
                st.success(f"Connected to Patient: **{p_user}**")
                
                # Management Tabs
                tab1, tab2, tab3 = st.tabs(["💊 Meds", "🥗 Diet", "📝 History"])
                
                with tab1:
                    st.subheader("Prescribe Medication")
                    m_name = st.text_input("Medicine Name", key="presc_med_name")
                    m_dose = st.number_input("Dose (mg)", min_value=0, key="presc_med_dose")
                    
                    if st.button("Confirm Prescription", key="doc_confirm_presc"):
                        df_m = load_meds()
                        # Calculate current total dose for this specific patient
                        current_patient_dose = df_m[df_m["user"] == p_user]["dose"].sum()
                        
                        if current_patient_dose + m_dose > 1000:
                            st.error(f"⚠️ Limit Reached! Total dosage cannot exceed 1000mg per day. (Current: {current_patient_dose}mg)")
                        elif m_name.strip() == "":
                            st.warning("Please enter a medicine name.")
                        else:
                            new_med = pd.DataFrame([[p_user, m_name, m_dose, "Morning", "After Food", ""]], 
                                                 columns=["user","name","dose","time","food","taken_log"])
                            save_meds(pd.concat([df_m, new_med], ignore_index=True))
                            st.success(f"✅ Prescribed {m_name} ({m_dose}mg). Total: {current_patient_dose + m_dose}mg")

                with tab2:
                    st.subheader("Assign Diet Plan")
                    diet_content = st.text_area("Write/Paste Diet Plan", key="doc_diet_text")
                    if st.button("Sync Diet to Patient Portal", key="doc_sync_diet"):
                        if "user_diet_plans" not in st.session_state:
                            st.session_state.user_diet_plans = {}
                        st.session_state.user_diet_plans[p_user] = diet_content
                        st.success("Diet plan updated for patient.")

                with tab3:
                    st.subheader("📊 Comprehensive Patient History")
                    
                    # --- A. MEDICATION ADHERENCE ---
                    st.markdown("#### 💊 Medication Adherence & Dosage")
                    df_meds = load_meds()
                    p_meds = df_meds[df_meds["user"] == p_user]
                    if not p_meds.empty:
                        # Display what meds they have and which days they were taken
                        st.dataframe(p_meds[["name", "dose", "time", "taken_log"]], use_container_width=True)
                    else:
                        st.info("No medications prescribed.")

                    # --- B. DIET & CALORIES ---
                    st.markdown("#### 🥗 Diet & Nutrition Logs")
                    # Retrieve the global diet and journal from session state
                    # (In a real app, these would be in a CSV, but for now we pull from the linked session)
                    log_id = f"{p_user}_{st.session_state.day}"
                    p_diet = st.session_state.user_diet_plans.get(p_user, "No plan assigned.")
                    p_journal = st.session_state.food_journal.get(log_id, "No intake logged today.")
                    p_cals = st.session_state.diet_log.get(st.session_state.day, 0)

                    col_h1, col_h2 = st.columns(2)
                    col_h1.metric("Today's Intake", f"{p_cals} kcal")
                    col_h2.write(f"**Patient Journal:** {p_journal}")
                    
                    with st.expander("View Assigned Diet Plan"):
                        st.markdown(p_diet)

                    # --- C. SYMPTOMS & NOTES ---
                    st.markdown("#### 📝 Patient Notes & Symptoms")
                    try:
                        notes_df = load_notes() 
                        p_notes = notes_df[notes_df["user"] == p_user]
                        if not p_notes.empty:
                            st.table(p_notes[["day", "tag", "note", "time"]])
                        else:
                            st.info("No patient notes found.")
                    except Exception as e:
                        st.error("Error loading notes.")
            else:
                st.error("Patient ID not found.")
                
        
# ---------------- 3. LOGIN / CREATE (PATIENT) ----------------
elif st.session_state.role == "patient" and not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1,1,1])
    with col2:
        st.markdown('<div class="glass">', unsafe_allow_html=True)
        if st.session_state.page == "login":
            st.subheader("🔐 Patient Login")
            u_input = st.text_input("Username")
            p_input = st.text_input("Password", type="password")
            
            if st.button("Login"):
                if check_login(u_input, p_input):
                    st.session_state.logged_in = True
                    st.session_state.username = u_input
                    profiles = load_profiles()
                    user_profile = profiles[profiles["user"] == u_input]
                    if not user_profile.empty:
                        p_data = user_profile.iloc[0]
                    # --- INSIDE YOUR PATIENT LOGIN BUTTON LOGIC ---
                    
                        # Check if they already have an ID in the CSV
                        raw_val = str(p_data.get("patient_id", ""))
                        
                        if raw_val == "" or raw_val == "nan" or raw_val == "None":
                            # PERMANENT FIX: Generate it ONCE and save it to the CSV immediately
                            import random
                            new_permanent_id = str(random.randint(1000, 9999))
                            st.session_state.patient_id = new_permanent_id
                            
                            # Save this new ID back to the CSV file so it's permanent
                            save_profile(
                                u_input, 
                                str(p_data["phone"]), 
                                p_data["country"], 
                                p_data["state"], 
                                p_data["age"], 
                                p_data["gender"], 
                                new_permanent_id
                            )
                        else:
                            # User already has an ID, just load it
                            st.session_state.patient_id = str(int(float(raw_val)))

                        
                        st.session_state.update({
                            "profile_complete": True, "phone": str(p_data["phone"]),
                            "country": p_data["country"], "state": p_data["state"],
                            "age": p_data["age"], "gender": p_data["gender"], "page": "Dashboard"
                        })
                    else:
                        st.session_state.profile_complete = False
                        st.session_state.page = "Profile"
                    st.rerun()
                else:
                    st.error("Invalid login")
            
            if st.button("Create Account"):
                st.session_state.page = "create"
                st.rerun()
                
            # Role Selection Redirect Button
            st.write("---")
            if st.button("↩️ Switch to Role Selection"):
                st.session_state.role = None
                st.rerun()
                
        else:
            st.subheader("🆕 Create Account")
            new_u = st.text_input("New Username")
            new_p = st.text_input("New Password", type="password")
            if st.button("Create"):
                if not valid_username(new_u): st.error("Username: 4+ chars, alphanumeric")
                elif not valid_password(new_p): st.error("Password: 6+ chars, 1 uppercase, 1 number")
                elif not save_user(new_u, new_p): st.error("Username already exists")
                else: st.success("Created! Please login")
            
            if st.button("Back"):
                st.session_state.page = "login"
                st.rerun()

            # Role Selection Redirect Button
            st.write("---")
            if st.button("↩️ Switch to Role Selection"):
                st.session_state.role = None
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
# ---------------- MAIN APP ----------------
else:
    # Navigation (Single Row)
    c1, c2, c3, c4, c5, c6, c7 = st.columns(7)

    if st.session_state.profile_complete:
        if c1.button("Dashboard"):
            st.session_state.page = "Dashboard"

        if c2.button("Medications"):
            st.session_state.page = "Medications"

        if c3.button("Diet"):
            st.session_state.page = "Diet"

        if c4.button("Notes"):
            st.session_state.page = "Notes"

        if c5.button("Records"):
            st.session_state.page = "Records"

        if c6.button("Profile"):
            st.session_state.page = "Profile"

    else:
        st.warning("⚠️ Complete your profile first")
        st.session_state.page = "Profile"

        if c6.button("Profile"):
            st.session_state.page = "Profile"

    # Logout
    if c7.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.profile_complete = False
        st.rerun()

    st.markdown(f"### 👋 {st.session_state.username}")

    # =====================================================
    # AI BUTTON + PATIENT ID
    # =====================================================

    if "chat_open" not in st.session_state:
        st.session_state.chat_open = False

    if "voice_question" not in st.session_state:
        st.session_state.voice_question = ""

    if "voice_answer" not in st.session_state:
        st.session_state.voice_answer = "Hello, ask me anything about health."

    top1, top2 = st.columns(2)

    # LEFT = AI BUTTON
    with top1:
        if st.button("🤖 AI CHATBOT", use_container_width=True):
            st.session_state.chat_open = not st.session_state.chat_open
            st.rerun()

    # RIGHT = PATIENT ID
    with top2:
        p_id_raw = st.session_state.get("patient_id", "0000")

        try:
            clean_id = str(int(float(p_id_raw)))
        except:
            clean_id = str(p_id_raw)

        st.markdown(
            f"""
            <div style="text-align:right;">
                <span style="
                    background:#020617;
                    padding:12px 24px;
                    border-radius:12px;
                    border:2px solid white;
                    color:white;
                    font-family:Courier New;
                    font-size:22px;
                    font-weight:900;">
                    🆔 ID: {clean_id}
                </span>
            </div>
            """,
            unsafe_allow_html=True
        )

    # =====================================================
    # CHATBOT POPUP ONLY WHEN CLICKED
    # =====================================================

    if st.session_state.chat_open:

        st.markdown("""
        <style>
        .chatbox{
            position:fixed;
            bottom:20px;
            right:20px;
            width:360px;
            z-index:9999;
            background:rgba(15,23,42,0.95);
            border:1px solid rgba(255,255,255,0.12);
            border-radius:18px;
            padding:15px;
            box-shadow:0 10px 30px rgba(0,0,0,0.4);
            backdrop-filter:blur(14px);
        }

        .chat-title{
            color:white;
            font-size:20px;
            font-weight:700;
            margin-bottom:10px;
            text-align:center;
        }

        .smalltxt{
            font-size:13px;
            color:#cbd5e1;
        }
        </style>
        """, unsafe_allow_html=True)

        st.markdown('<div class="chatbox">', unsafe_allow_html=True)

        st.markdown(
            '<div class="chat-title">🎙 AI Health Chatbot</div>',
            unsafe_allow_html=True
        )

        st.caption("Ask by text or voice")

        user_msg = st.text_input(
            "Message",
            placeholder="Ask symptoms, diet, medicine...",
            key="global_ai_text"
        )

        colv1, colv2 = st.columns(2)

        # VOICE
        with colv1:
            if st.button("🎤 Speak", use_container_width=True):

                try:
                    recog = sr.Recognizer()

                    with sr.Microphone() as source:
                        st.info("Listening...")
                        audio = recog.listen(
                            source,
                            timeout=5,
                            phrase_time_limit=7
                        )

                    spoken = recog.recognize_google(audio)

                    st.session_state.voice_question = spoken
                    st.session_state.voice_answer = ask_groq_health_bot(spoken)

                except:
                    st.session_state.voice_answer = "Could not understand voice."

                st.rerun()

        # SEND
        with colv2:
            if st.button("Send", use_container_width=True):

                q = user_msg.strip()

                if q != "":
                    st.session_state.voice_question = q
                    st.session_state.voice_answer = ask_groq_health_bot(q)

                st.rerun()

        if st.session_state.voice_question:
            st.markdown(
                f"""
                <div class='smalltxt'>
                <b>You:</b> {st.session_state.voice_question}
                </div>
                """,
                unsafe_allow_html=True
            )

        st.markdown(
            f"""
            <div style="
                margin-top:8px;
                color:white;
                background:rgba(255,255,255,0.05);
                padding:10px;
                border-radius:12px;
                min-height:80px;">
                🤖 {st.session_state.voice_answer}
            </div>
            """,
            unsafe_allow_html=True
        )

        st.markdown("</div>", unsafe_allow_html=True)
        


# ---------------- PAGE: PROFILE (PATIENT SIDE) ----------------
    if st.session_state.page == "Profile":
        st.subheader("👤 Profile Settings")
        countries = sorted([c.name for c in pycountry.countries])
        
        # Default values from session state
        curr_country = st.session_state.get("country", "India")
        curr_state = st.session_state.get("state", "")
        curr_phone = st.session_state.get("phone", "")
        curr_age = st.session_state.get("age", 25)
        curr_gender = st.session_state.get("gender", "Male")

        country = st.selectbox("🌍 Country", countries, index=countries.index(curr_country) if curr_country in countries else 0)
        state = st.text_input("📍 State / Region", value=curr_state)
        phone = st.text_input("📞 Phone Number", value=curr_phone)
        age = st.number_input("🎂 Age", 1, 120, value=int(curr_age))
        gender = st.selectbox("⚧ Gender", ["Male","Female","Other"], index=["Male","Female","Other"].index(curr_gender))

        if st.button("Update Profile"):
            if state.strip() == "" or not phone.isdigit():
                st.error("Please provide valid state and phone number")
            else:
                # 1. Handle Patient ID Generation
                import random
                # We check if they already have an ID in the session, otherwise create one
                if "patient_id" not in st.session_state or not st.session_state.patient_id:
                    st.session_state.patient_id = str(random.randint(1000, 9999))
                
                # 2. Save to CSV - CRITICAL: Passing all 7 arguments now
                save_profile(
                    st.session_state.username, 
                    phone, 
                    country, 
                    state, 
                    age, 
                    gender, 
                    st.session_state.patient_id
                )
                
                # 3. Update Session State
                st.session_state.profile_complete = True
                st.session_state.phone = phone
                st.session_state.country = country
                st.session_state.state = state
                st.session_state.age = age
                st.session_state.gender = gender
                
                # 4. Success and Redirect
                st.session_state.page = "Dashboard"
                st.success(f"✅ Profile Updated! Your Unique Patient ID is: {st.session_state.patient_id}")
                st.rerun()
                
                
    # ---------------- DASHBOARD (GLASS UI) ----------------
    elif st.session_state.page == "Dashboard":
        df = load_meds()
        user_df = df[df["user"] == st.session_state.username]
        NOTE_FILE = "notes.csv"
        
        # ---------------- CALCULATIONS ----------------
        total_meds = len(user_df)
        total_dose = user_df["dose"].sum()
        today_taken = 0
        total_today = 0
        
        for _, row in user_df.iterrows():
            total_today += row["dose"]
            taken_days = str(row["taken_log"]).split(",")
            if str(st.session_state.day) in taken_days:
                today_taken += row["dose"]
                
        # NOTES INSIGHT
        insight_msg = "No data"
        insight_color = "#38bdf8"
        if os.path.exists(NOTE_FILE):
            notes_df = pd.read_csv(NOTE_FILE)
            user_notes = notes_df[notes_df["user"] == st.session_state.username]
            if not user_notes.empty:
                text = " ".join(user_notes["note"].astype(str)).lower()
                bad = ["pain","fever","headache","vomit","weak"]
                good = ["good","better","fine","ok","improved"]
                
                bad_score = sum(word in text for word in bad)
                good_score = sum(word in text for word in good)
                
                if bad_score > good_score:
                    insight_msg = "⚠ Symptoms detected"
                    insight_color = "#ef4444"
                elif good_score > bad_score:
                    insight_msg = "✅ Improving"
                    insight_color = "#22c55e"
                    
        # CALORIES
        calories = st.session_state.diet_log.get(st.session_state.day, 0)
        
        # ---------------- UI GRID ----------------
        st.markdown("## 📊 Dashboard Overview")
        col1, col2, col3 = st.columns(3)
        
        # CARD 1
        col1.markdown(f"""
        <div class="card">
            <h3>💊 Medicines</h3>
            <h2>{total_meds}</h2>
            <p>Total Dose: {total_dose} mg</p>
        </div>
        """, unsafe_allow_html=True)
        
        # CARD 2
        col2.markdown(f"""
        <div class="card">
            <h3>📅 Today</h3>
            <h2>{today_taken} / {total_today} mg</h2>
            <p>Progress Tracking</p>
        </div>
        """, unsafe_allow_html=True)
        
        # CARD 3
        col3.markdown(f"""
        <div class="card">
            <h3>🔥 Calories</h3>
            <h2>{calories}</h2>
            <p>Daily Intake</p>
        </div>
        """, unsafe_allow_html=True)
        
        # ---------------- SECOND ROW ----------------
        col4, col5 = st.columns(2)
        
        # HEALTH INSIGHT CARD
        col4.markdown(f"""
        <div class="card">
            <h3>🧠 Health Insight</h3>
            <h2 style="color:{insight_color};">{insight_msg}</h2>
            <p>Based on notes</p>
        </div>
        """, unsafe_allow_html=True)
        
        # STATUS CARD
        status_msg = "Stable"
        status_color = "#22c55e"
        if total_dose > 1000 or today_taken < total_today * 0.5:
            status_msg = "Attention Needed"
            status_color = "#ef4444"
            
        col5.markdown(f"""
        <div class="card">
            <h3>⚡ Overall Status</h3>
            <h2 style="color:{status_color};">{status_msg}</h2>
            <p>System Health</p>
        </div>
        """, unsafe_allow_html=True)
        
        # ---------------- TODAY'S ADHERENCE ----------------
        st.markdown("### 📈 Today's Adherence")
        total_meds_today = len(user_df)
        taken_meds_today = 0
        
        for _, row in user_df.iterrows():
            taken_days = str(row["taken_log"]).split(",")
            if str(st.session_state.day) in taken_days:
                taken_meds_today += 1
                
        progress = 0
        if total_meds_today > 0:
            progress = taken_meds_today / total_meds_today
            
        st.progress(progress)
        st.write(f"💊 {taken_meds_today} / {total_meds_today} medicines taken")
        
        # ---------------- ADHERENCE HISTORY ----------------
        st.markdown("### 📊 Adherence History")
        adherence_map = {}
        for _, row in user_df.iterrows():
            if row["taken_log"]:
                taken_days = [d for d in str(row["taken_log"]).split(",") if d.strip() != ""]
                for d in taken_days:
                    try:
                        day_val = int(float(d))
                        if day_val not in adherence_map:
                            adherence_map[day_val] = {"taken": 0, "total": total_meds_today}
                        adherence_map[day_val]["taken"] += 1
                    except:
                        pass
        
        history_data = []
        for day, values in adherence_map.items():
            total = values["total"]
            taken = values["taken"]
            percent = (taken / total) * 100 if total > 0 else 0
            history_data.append((day, percent))
            
        if history_data:
            hist_df = pd.DataFrame(history_data, columns=["day", "adherence"])
            hist_df = hist_df.sort_values("day")
            st.line_chart(hist_df.set_index("day"))
            
            avg = hist_df["adherence"].mean()
            st.write(f"📊 Average adherence: {avg:.1f}%")
        else:
            st.info("No adherence data yet")
            
 # ---------------- MEDICATIONS PAGE (WITH 1000mg LIMIT) ----------------
    if st.session_state.page == "Medications":
        st.subheader("💊 Medication Manager")
        df = load_meds()
        user_df = df[df["user"] == st.session_state.username]
        
        # Calculate current total dosage for the user
        current_daily_total = user_df["dose"].sum()

        with st.expander("➕ Add New Medicine"):
            st.markdown(f"**Current Daily Total:** `{current_daily_total}mg / 1000mg`")
            
            name = st.text_input("Medicine Name")
            dose = st.number_input("Dose (mg)", min_value=0, step=10)
            time = st.selectbox("Time", ["Morning","Afternoon","Night"])
            food = st.selectbox("Food", ["Before Food","After Food"])
            
            if st.button("Add Medicine"):
                if name.strip() == "":
                    st.error("Please enter a medicine name.")
                # SAFETY CHECK: 1000mg Limit
                elif current_daily_total + dose > 1000:
                    st.error(f"⚠️ Limit Reached! Adding this would bring your total to {current_daily_total + dose}mg. Daily maximum is 1000mg.")
                else:
                    new = pd.DataFrame([[st.session_state.username, name, dose, time, food, ""]], 
                                     columns=["user","name","dose","time","food","taken_log"])
                    df = pd.concat([df, new], ignore_index=True)
                    save_meds(df)
                    st.success(f"Added {name} successfully!")
                    st.rerun()
        
        st.markdown("---")
        
        # Day Navigation
        colA, colB = st.columns(2)
        with colA:
            if st.button("⬅ Previous Day", key="med_prev"):
                if st.session_state.day > 1:
                    st.session_state.day -= 1
                    st.rerun()
        with colB:
            if st.button("Next Day ➡", key="med_next"):
                st.session_state.day += 1
                st.rerun()
            
        st.subheader(f"📅 Day {st.session_state.day} Log")
        
        # Filter again to ensure we have fresh data after additions
        user_df = df[df["user"] == st.session_state.username]

        if user_df.empty:
            st.info("No medicines added yet. Use the expander above to start.")
        else:
            st.markdown("### 🟢 Today's Schedule")
            for i, row in user_df.iterrows():
                taken_days = str(row["taken_log"]).split(",")
                is_taken_today = str(st.session_state.day) in taken_days
                
                col1, col2 = st.columns([6,1])
                status = "✅ Taken" if is_taken_today else "⏳ Pending"
                
                col1.markdown(f"""
                <div class="card">
                    💊 <b>{row['name']}</b> — {row['dose']}mg<br>
                    🕒 {row['time']} | 🍽 {row['food']}<br>
                    📌 Status: {status}
                </div>
                """, unsafe_allow_html=True)
                
                if not is_taken_today:
                    if col2.button("✔️", key=f"take_{i}"):
                        new_log = str(row["taken_log"])
                        if new_log in ["", "nan", "None"]:
                            new_log = str(st.session_state.day)
                        else:
                            new_log = f"{new_log},{st.session_state.day}"
                        
                        df.at[i, "taken_log"] = new_log
                        save_meds(df)
                        st.rerun()

            st.markdown("---")
            st.markdown("### 📋 Management (All Prescriptions)")
            for i, row in user_df.iterrows():
                col1, col2 = st.columns([6,1])
                col1.markdown(f"""
                <div class="card" style="border-left: 5px solid #38bdf8;">
                    <b>{row['name']}</b> ({row['dose']}mg)<br>
                    <small>Logged on days: {row['taken_log'] if row['taken_log'] else 'None'}</small>
                </div>
                """, unsafe_allow_html=True)
                
                if col2.button("❌", key=f"del_{i}"):
                    df = df.drop(i)
                    save_meds(df)
                    st.rerun()

            st.markdown("### 📊 Adherence & Dosage Trend")
            graph_data = []
            for _, row in user_df.iterrows():
                if row["taken_log"]:
                    for d in str(row["taken_log"]).split(","):
                        try:
                            day_val = int(float(d))
                            graph_data.append({"day": day_val, "dose": row["dose"]})
                        except:
                            pass
            
            if graph_data:
                graph_df = pd.DataFrame(graph_data)
                chart_pivot = graph_df.groupby("day")["dose"].sum()
                st.line_chart(chart_pivot)
            else:
                st.caption("Complete your daily intake to see trends.")        
# ---------------- DIET PANEL (STABLE GROQ VERSION) ----------------
    elif st.session_state.page == "Diet":
        st.subheader("🥗 Smart AI Diet & Nutrition")
        
        # --- SHARED DAY CONTROLS ---
        col_day1, col_day2 = st.columns([2, 1])

        with col_day1:
            st.markdown(f"#### 📅 Log for Day {st.session_state.day}")

        with col_day2:
            if st.button("Next Day ➡️"):
                st.session_state.day += 1
                st.rerun()

        if "user_diet_plans" not in st.session_state:
            st.session_state.user_diet_plans = {}

        if "food_journal" not in st.session_state:
            st.session_state.food_journal = {}

        if "diet_log" not in st.session_state:
            st.session_state.diet_log = {}

        # PROFILE INFO
        u_country = st.session_state.get("country", "India")
        u_state = st.session_state.get("state", "Tamil Nadu")
        u_age = st.session_state.get("age", 21)
        u_gender = st.session_state.get("gender", "User")
        current_user = st.session_state.username

        df = load_meds()
        user_meds = df[df["user"] == current_user]["name"].unique().tolist()

        st.info(
            f"📍 {u_state} | 👤 {u_age}yo {u_gender} | 💊 Meds: {', '.join(user_meds) if user_meds else 'None'}"
        )

        # ===================================
        # AI DIET PLAN
        # ===================================
        if st.button("✨ Generate AI Diet Plan"):

            with st.spinner("Analyzing medication safety and regional cuisine..."):

                import requests

                url = "https://api.groq.com/openai/v1/chat/completions"

                headers = {
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                }

                payload = {
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {
                            "role": "system",
                            "content":
                            "You are a clinical nutritionist. Priority #1 medication safety. Priority #2 regional Indian foods."
                        },
                        {
                            "role": "user",
                            "content": f"""
    Create a 1-day {u_state} meal plan for a {u_age}yo {u_gender}.
    Current Medications: {user_meds}.
    Include Breakfast, Lunch, Snack, Dinner with calories.
    """
                        }
                    ]
                }

                try:
                    response = requests.post(
                        url,
                        headers=headers,
                        json=payload,
                        timeout=15
                    )

                    result = response.json()

                    if "choices" in result:
                        st.session_state.user_diet_plans[current_user] = \
                            result["choices"][0]["message"]["content"]

                        st.rerun()

                except Exception as e:
                    st.error(f"Error: {e}")

        if current_user in st.session_state.user_diet_plans:
            st.markdown(
                f'<div class="card">{st.session_state.user_diet_plans[current_user]}</div>',
                unsafe_allow_html=True
            )

        st.markdown("---")

        # ===================================
        # FOOD JOURNAL
        # ===================================
        st.markdown(f"### 📝 Day {st.session_state.day} Food Journal")

        log_id = f"{current_user}_{st.session_state.day}"

        existing_journal = st.session_state.food_journal.get(log_id, "")
        existing_cals = st.session_state.diet_log.get(
            st.session_state.day, 0
        )

        col_j1, col_j2 = st.columns([2, 1])

        with col_j1:
            user_meals = st.text_area(
                "What did you eat today?",
                value=existing_journal,
                placeholder="e.g. Idli, Rice, Milk..."
            )

        with col_j2:
            calories = st.number_input(
                "Total Calories (kcal)",
                min_value=0,
                value=int(existing_cals)
            )

        if st.button("💾 Save Journal & Calories"):

            st.session_state.food_journal[log_id] = user_meals
            st.session_state.diet_log[st.session_state.day] = calories

            st.success(
                f"✅ Day {st.session_state.day} journal saved!"
            )

            st.rerun()

        # ===================================
        # FEEDBACK
        # ===================================
        if calories > 0:

            if calories > 2500:
                st.error(
                    f"⚠️ High intake ({calories} kcal)"
                )

            elif calories < 1200:
                st.warning(
                    f"⚠️ Low intake ({calories} kcal)"
                )

            else:
                st.success(
                    f"✅ Healthy intake ({calories} kcal)"
                )

        # ===================================
        # HISTORY DISPLAY
        # ===================================
        st.markdown("---")
        st.subheader("📜 Food Journal History")

        found = False

        for key in sorted(
            st.session_state.food_journal.keys(),
            reverse=True
        ):

            if key.startswith(current_user + "_"):

                try:
                    day_num = int(key.split("_")[1])
                except:
                    day_num = 0

                meal_text = st.session_state.food_journal[key]

                cal_val = st.session_state.diet_log.get(
                    day_num, 0
                )

                st.markdown(
                    f"""
    <div class="card">
    <h4>📅 Day {day_num}</h4>
    <p><b>🍽 Meals:</b><br>{meal_text}</p>
    <p><b>🔥 Calories:</b> {cal_val} kcal</p>
    </div>
    """,
                    unsafe_allow_html=True
                )

                found = True

        if not found:
            st.info("No food history available yet.")
# ---------------- NOTES PANEL (AI UPGRADED) ----------------
    elif st.session_state.page == "Notes":
        st.subheader("🧠 Smart Health Notes")
        NOTES_FILE = "notes.csv"
        
        # ---------------- LOAD / SAVE ----------------
        def load_notes():
            if os.path.exists(NOTES_FILE):
                return pd.read_csv(NOTES_FILE)
            return pd.DataFrame(columns=["user","day","note","tag","time"])
            
        def save_notes(df):
            df.to_csv(NOTES_FILE, index=False)
            
        notes_df = load_notes()
        user_notes = notes_df[notes_df["user"] == st.session_state.username]
        
        # ---------------- ADD NOTE ----------------
        st.markdown("### ✍️ Add Note")
        note_text = st.text_area("Write your note")
        tag = st.selectbox("Tag", ["Symptom","Side Effect","Mood","Diet","Other"])
        if st.button("Save Note"):
            if note_text.strip() != "":
                from datetime import datetime
                new_note = pd.DataFrame([[
                    st.session_state.username,
                    st.session_state.day,
                    note_text,
                    tag,
                    datetime.now().strftime("%Y-%m-%d %H:%M")
                ]], columns=["user","day","note","tag","time"])
                notes_df = pd.concat([notes_df, new_note], ignore_index=True)
                save_notes(notes_df)
                st.success("✅ Note saved")
                st.rerun()
                
        # ---------------- SEARCH ----------------
        st.markdown("### 🔍 Search Notes")
        search = st.text_input("Search by keyword")
        if search:
            user_notes = user_notes[user_notes["note"].str.contains(search, case=False)]
            
        # ---------------- AI ANALYSIS ----------------
        st.markdown("### 🤖 Health Insights")
        all_text = " ".join(user_notes["note"].astype(str)).lower()
        
        warning_words = ["pain","fever","headache","vomit","weak","dizzy"]
        good_words = ["good","better","improved","fine","ok"]
        
        warning_count = sum(word in all_text for word in warning_words)
        good_count = sum(word in all_text for word in good_words)
        
        if warning_count > good_count:
            st.error("⚠️ Frequent symptoms detected. Consider consulting a doctor.")
        elif good_count > warning_count:
            st.success("✅ Health seems to be improving based on your notes.")
        else:
            st.info("ℹ️ Not enough data for insights yet.")
            
        # ---------------- DISPLAY NOTES ----------------
        st.markdown("### 📋 Your Notes")
        for i, row in user_notes.iterrows():
            st.markdown(f"""
            <div class="card">
                📅 Day {row['day']} <br>
                🏷 {row['tag']} <br>
                🕒 {row['time']} <br><br>
                📝 {row['note']}
            </div>
            """, unsafe_allow_html=True)
            if st.button("❌ Delete", key=f"note_del_{i}"):
                notes_df = notes_df.drop(i)
                save_notes(notes_df)
                st.rerun()
                
        # ---------------- DOWNLOAD ----------------
        st.markdown("### 📥 Export Notes")
        if not user_notes.empty:
            st.download_button(
                "Download Notes",
                user_notes.to_csv(index=False),
                "my_health_notes.csv"
            )
    # ---------------- PAGE: MEDICAL RECORDS ----------------
    elif st.session_state.page == "Records":
        st.subheader("📂 Medical Records Vault")

        RECORD_DIR = "medical_records"
        user_folder = os.path.join(RECORD_DIR, st.session_state.username)
        if not os.path.exists(user_folder):
            os.makedirs(user_folder)

        # --- UPLOAD SECTION ---
        # We use st.expander. To "close" it, we rely on the rerun which resets the UI state
        with st.expander("📤 Upload New Record", expanded=False):
            # We assign 'key' to inputs so we can clear them later
            up_file = st.file_uploader("Upload Report", type=["pdf", "png", "jpg", "jpeg"], key="file_up")
            up_date = st.date_input("Record Date", datetime.now(), key="date_up")
            up_desc = st.text_input("Description", placeholder="e.g. MRI Scan", key="desc_up")
            
            if st.button("Securely Save to Server"):
                if up_file is not None:
                    # File Naming Logic
                    date_str = up_date.strftime("%Y-%m-%d")
                    clean_name = f"{date_str}_{up_file.name}"
                    file_path = os.path.join(user_folder, clean_name)
                    
                    with open(file_path, "wb") as f:
                        f.write(up_file.getbuffer())
                    
                    # SUCCESS: Clear the inputs by deleting their keys from session state
                    st.success(f"✅ Saved: {clean_name}")
                    
                    # Reset logic: This empties the blanks for the next use
                    for key in ["file_up", "desc_up"]:
                        if key in st.session_state:
                            del st.session_state[key]
                    
                    # Rerunning closes the expander and refreshes the list
                    st.rerun()
                else:
                    st.error("Please select a file first.")

        st.markdown("---")

        # --- VIEW, PREVIEW & DOWNLOAD SECTION ---
        st.markdown("### 📋 Your Stored Documents")
        files = sorted(os.listdir(user_folder), reverse=True)
        
        if not files:
            st.info("No records found.")
        else:
            for file_name in files:
                display_date = file_name[:10] if "_" in file_name else "Date Unknown"
                actual_name = file_name[11:] if "_" in file_name else file_name
                full_path = os.path.join(user_folder, file_name)
                
                with st.container():
                    # Grid for File Info and 3 Actions (View, Download, Delete)
                    col_f1, col_f2, col_v, col_d, col_x = st.columns([2, 3, 1, 1, 1])
                    
                    col_f1.write(f"📅 `{display_date}`")
                    col_f2.write(actual_name)
                    
                    # 1. VIEW (Preview)
                    if col_v.button("👁️", key=f"pre_{file_name}", help="Preview"):
                        st.session_state.preview_file = full_path
                    
                    # 2. DOWNLOAD (Direct Option)
                    with open(full_path, "rb") as f:
                        col_d.download_button(
                            label="📥",
                            data=f,
                            file_name=file_name,
                            mime="application/octet-stream",
                            key=f"down_{file_name}",
                            help="Download to device"
                        )
                    
                    # 3. DELETE
                    if col_x.button("🗑️", key=f"del_{file_name}", help="Delete permanently"):
                        os.remove(full_path)
                        st.rerun()

            # --- PREVIEW RENDERER ---
            if "preview_file" in st.session_state and st.session_state.preview_file:
                st.markdown("---")
                path = st.session_state.preview_file
                
                # Header with close button
                p_col1, p_col2 = st.columns([9, 1])
                p_col1.markdown(f"#### 🔍 Viewing: {os.path.basename(path)}")
                if p_col2.button("✖️"):
                    st.session_state.preview_file = None
                    st.rerun()

                if path.lower().endswith(".pdf"):
                    with open(path, "rb") as f:
                        base64_pdf = __import__("base64").b64encode(f.read()).decode('utf-8')
                    pdf_display = f'<embed src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800" type="application/pdf">'
                    st.markdown(pdf_display, unsafe_allow_html=True)
                elif path.lower().endswith((".png", ".jpg", ".jpeg")):
                    st.image(path, use_container_width=True)
