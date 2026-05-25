import streamlit as st
import pandas as pd
import time
import os
import io
import re
import csv as csv_module
from datetime import datetime

# --- 1. PAGE CONFIG & STYLING ---
st.set_page_config(page_title="Sahayaks Academy Quiz", layout="wide")

st.markdown("""
    <style>
    .stApp {
        background-color: #0F1937;
        color: #FFFFFF;
    }

    /* Text input labels */
    .stTextInput label,
    .stTextInput > label,
    div[data-testid="stTextInput"] label {
        color: #FFFFFF !important;
        font-weight: bold !important;
        font-size: 1.2rem !important;
    }

    /* Input field */
    .stTextInput > div > div > input {
        background-color: #FFFFFF !important;
        color: #0F1937 !important;
        border: 2px solid #FFD700 !important;
        font-weight: bold;
    }

    /* ALL regular buttons: white bg, dark text */
    .stButton > button {
        background-color: #FFFFFF !important;
        color: #0F1937 !important;
        border: 1px solid #FFD700 !important;
        font-weight: bold !important;
        width: 100%;
        height: 48px;
    }
    .stButton > button:hover {
        background-color: #f0f0f0 !important;
        border: 2px solid #0F1937 !important;
    }

    /* Targeted Streamlit Download button styling */
    div[data-testid="stDownloadButton"] > button {
        background-color: #FFD700 !important;
        color: #0F1937 !important;
        border: 2px solid #0F1937 !important;
        font-weight: bold !important;
        font-size: 1.1rem !important;
        width: 100% !important;
        height: 56px !important;
        border-radius: 8px !important;
    }
    div[data-testid="stDownloadButton"] > button:hover {
        background-color: #e6c200 !important;
        color: #0F1937 !important;
    }

    .explanation-box {
        background-color: #1b2641;
        padding: 20px;
        border-left: 5px solid #FFD700;
        border-radius: 8px;
        margin-top: 20px;
    }

    .timer-card {
        background-color: #FFD700;
        color: #0F1937;
        padding: 10px;
        border-radius: 8px;
        text-align: center;
        font-weight: bold;
        font-size: 1.4rem;
    }

    .timer-card-urgent {
        background-color: #dc3545;
        color: #FFFFFF;
        padding: 10px;
        border-radius: 8px;
        text-align: center;
        font-weight: bold;
        font-size: 1.4rem;
        animation: pulse 1s infinite;
    }

    @keyframes pulse {
        0%   { opacity: 1; }
        50%  { opacity: 0.6; }
        100% { opacity: 1; }
    }

    .result-card {
        background-color: #1b2641;
        padding: 30px;
        border-radius: 15px;
        border: 2px solid #FFD700;
        text-align: center;
        margin-bottom: 20px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. SESSION STATE MANAGEMENT ---
if 'step' not in st.session_state:
    st.session_state.step = "login"
if 'user_name' not in st.session_state:
    st.session_state.user_name = ""
if 'selected_chapter' not in st.session_state:
    st.session_state.selected_chapter = None
if 'quiz_state' not in st.session_state:
    st.session_state.quiz_state = {'idx': 0, 'answers': {}, 'end_time': None}
if 'just_answered_idx' not in st.session_state:
    st.session_state.just_answered_idx = None


# --- 3. DYNAMIC MATHEMATICAL SYMBOL REPAIR LAYER ---
def repair_math_symbols(text):
    if not isinstance(text, str):
        return text

    # Fix mojibake for Windows-1252 special chars
    text = text.replace('\x92', "'")
    text = text.replace('\x93', '"')
    text = text.replace('\x94', '"')
    text = text.replace('\x96', '–')
    text = text.replace('\x97', '—')

    # Fix compound corrupted expressions
    text = text.replace('? ? 3.14', 'π ≈ 3.14')
    text = text.replace('value of ?', 'value of π')

    # Turn '?' into square root '√' when immediately followed by a number (e.g. ?2 -> √2)
    text = re.sub(r'\?(\d)', r'√\1', text)

    # Turn standalone '?' into 'π'
    if text.strip() == '?':
        return 'π'

    return text


# --- 4. DATA LOADING ---
@st.cache_data
def load_data():
    # ── Path is relative to this script's folder so it works regardless of
    #    where you launch Streamlit from. ──
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_dir, "MCQ for test.csv")

    if not os.path.exists(file_path):
        st.warning(f"⚠️ Data file not found at: {file_path}")
        return pd.DataFrame()

    EXPECTED_COLS = 10  # Board, Class, Chapter, Question, Opt1-4, Correct Answer, Explanation

    def clean_field(s):
        """Strip the trailing/leading double-quote artifacts left by the
        double-layer quoting in this CSV format."""
        s = s.strip()
        while s.endswith('""'):
            s = s[:-2].rstrip()
        while s.startswith('""'):
            s = s[2:].lstrip()
        return s

    try:
        header = None
        rows = []

        with open(file_path, 'r', encoding='latin1') as f:
            for raw_line in f:
                line = raw_line.strip().strip('\r')
                if not line:
                    continue

                # Each row is wrapped in an extra pair of outer double-quotes — remove them.
                if line.startswith('"') and line.endswith('"'):
                    line = line[1:-1]

                # Parse with csv.reader to handle quoted fields correctly.
                parsed = next(csv_module.reader([line]))
                parsed = [clean_field(field) for field in parsed]

                if header is None:
                    header = parsed[:EXPECTED_COLS]
                    continue

                # The Explanation field often contains commas, causing extra columns.
                # Fix: merge all overflow columns back into the last (Explanation) column.
                if len(parsed) > EXPECTED_COLS:
                    explanation_merged = ', '.join(parsed[EXPECTED_COLS - 1:])
                    parsed = parsed[:EXPECTED_COLS - 1] + [explanation_merged]

                # Skip any rows that are still malformed after merging
                if len(parsed) == EXPECTED_COLS:
                    rows.append(parsed)

        if not rows:
            st.error("❌ CSV file appears to be empty or could not be parsed.")
            return pd.DataFrame()

        df = pd.DataFrame(rows, columns=header)
        df.columns = df.columns.str.strip()

    except Exception as e:
        st.error(f"❌ Error processing CSV: {e}")
        return pd.DataFrame()

    if not df.empty:
        for col in df.columns:
            df[col] = df[col].apply(repair_math_symbols)

    if 'Question' in df.columns:
        return df.dropna(subset=['Question'])
    else:
        st.error(f"❌ Could not find 'Question' column. Found headers: {list(df.columns)}")
        return pd.DataFrame()


df_all = load_data()


# --- 5. NATIVE ISOLATED LIVE TIMER ---
@st.fragment(run_every=1.0)
def isolated_timer_component():
    if st.session_state.step == "quiz" and st.session_state.quiz_state.get('end_time'):
        remaining = int(st.session_state.quiz_state['end_time'] - time.time())
        remaining = max(remaining, 0)

        mins, secs = divmod(remaining, 60)
        label = f"⏳ {mins:02d}:{secs:02d}"
        css_class = "timer-card-urgent" if remaining <= 60 else "timer-card"

        st.markdown(f'<div class="{css_class}">{label}</div>', unsafe_allow_html=True)

        if remaining <= 0:
            st.session_state.step = "results"
            st.rerun()


# --- 6. CERTIFICATE GENERATION ---
def generate_certificate(user_name, chapter, score_pct, date_str):
    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.pdfgen import canvas

        buffer = io.BytesIO()
        w, h = landscape(A4)
        c = canvas.Canvas(buffer, pagesize=landscape(A4))

        c.setFillColor(colors.HexColor("#0F1937"))
        c.rect(0, 0, w, h, fill=1, stroke=0)

        c.setStrokeColor(colors.HexColor("#FFD700"))
        c.setLineWidth(6)
        c.rect(20, 20, w - 40, h - 40, fill=0, stroke=1)
        c.setLineWidth(2)
        c.rect(30, 30, w - 60, h - 60, fill=0, stroke=1)

        c.setFillColor(colors.HexColor("#FFD700"))
        c.setFont("Helvetica-Bold", 42)
        c.drawCentredString(w / 2, h - 110, "Sahayaks Education")

        c.setFillColor(colors.white)
        c.setFont("Helvetica", 22)
        c.drawCentredString(w / 2, h - 150, "Certificate of Achievement")

        c.setStrokeColor(colors.HexColor("#FFD700"))
        c.setLineWidth(1.5)
        c.line(80, h - 170, w - 80, h - 170)

        c.setFillColor(colors.white)
        c.setFont("Helvetica", 18)
        c.drawCentredString(w / 2, h - 215, "This is to certify that")

        c.setFillColor(colors.HexColor("#FFD700"))
        c.setFont("Helvetica-Bold", 34)
        c.drawCentredString(w / 2, h - 265, user_name)

        c.setFillColor(colors.white)
        c.setFont("Helvetica", 18)
        c.drawCentredString(w / 2, h - 310, "has successfully completed the assessment for")

        c.setFillColor(colors.HexColor("#FFD700"))
        c.setFont("Helvetica-Bold", 26)
        c.drawCentredString(w / 2, h - 355, chapter)

        c.setFillColor(colors.white)
        c.setFont("Helvetica", 18)
        c.drawCentredString(w / 2, h - 400, f"with a score of {score_pct:.1f}%")

        c.setStrokeColor(colors.HexColor("#FFD700"))
        c.line(80, h - 430, w - 80, h - 430)

        c.setFillColor(colors.HexColor("#CCCCCC"))
        c.setFont("Helvetica", 14)
        c.drawCentredString(w / 2, h - 460, f"Awarded on: {date_str}")

        c.setFont("Helvetica-Oblique", 12)
        c.drawCentredString(w / 2, h - 490, "Sahayaks Education — Empowering Every Learner")

        c.save()
        buffer.seek(0)
        return buffer
    except ImportError:
        return None


# --- 7. NAVIGATION & PAGES ---

# ── LOGIN ──────────────────────────────────────────────────────────────────────
if st.session_state.step == "login":
    st.markdown("<h1 style='text-align: center; color: #FFD700;'>Sahayaks Education</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.markdown("<p style='color:#FFFFFF; font-weight:bold; font-size:1.1rem;'>Student Entrance</p>",
                    unsafe_allow_html=True)

        u_name = st.text_input(
            "Full Name for Certificate",
            value=st.session_state.user_name,
            placeholder="Enter your full name...",
            key="cert_name_input"
        )
        if st.button("Start Assessment"):
            if u_name.strip():
                st.session_state.user_name = u_name.strip()
                st.session_state.step = "instructions"
                st.rerun()
            else:
                st.error("Please enter your name to proceed.")


# ── INSTRUCTIONS ───────────────────────────────────────────────────────────────
elif st.session_state.step == "instructions":
    st.markdown("<h2 style='text-align: center; color: #FFD700;'>Instructions</h2>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([0.1, 0.8, 0.1])
    with col2:
        st.markdown(f"""
        <div style="background-color: #1b2641; padding: 25px; border-radius: 15px; border: 1px solid #FFD700;">
            <p style="color:#FFFFFF;">Welcome, <b>{st.session_state.user_name}</b>.</p>
            <ul style="color:#FFFFFF;">
                <li><b>Timer:</b> 1 minute per question (pooled across the chapter). For example, a 10-question chapter gives you 10 minutes total.</li>
                <li><b>Feedback:</b> After each answer you will immediately see whether you got it right or wrong, the correct answer, and a brief explanation.</li>
                <li><b>Navigation:</b> Use the sidebar to jump between questions.</li>
                <li><b>Results:</b> Only your final score is shown at the end — no answers or breakdowns are revealed.</li>
                <li><b>Certificate:</b> Awarded automatically if you score above 90%.</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        st.write("")
        c1, c2 = st.columns(2)
        if c1.button("✅ I Agree"):
            st.session_state.step = "chapter_select"
            st.rerun()
        if c2.button("❌ Quit"):
            st.session_state.step = "login"
            st.rerun()


# ── CHAPTER SELECT ─────────────────────────────────────────────────────────────
elif st.session_state.step == "chapter_select":
    st.markdown("<h2 style='text-align: center; color: #FFD700;'>Select a Chapter</h2>", unsafe_allow_html=True)

    if df_all.empty:
        st.error("No data loaded. Please verify your CSV file path and structure.")
    else:
        chapters = sorted(df_all['Chapter'].unique())
        cols = st.columns(3)
        for i, ch in enumerate(chapters):
            if cols[i % 3].button(f"📘 {ch}", key=f"ch_{i}"):
                chapter_qs = df_all[df_all['Chapter'] == ch]
                st.session_state.selected_chapter = ch
                st.session_state.quiz_state = {
                    'idx': 0,
                    'answers': {},
                    # ── 60 seconds per question ──
                    'end_time': time.time() + (len(chapter_qs) * 60)
                }
                st.session_state.step = "quiz"
                st.rerun()


# ── QUIZ ───────────────────────────────────────────────────────────────────────
elif st.session_state.step == "quiz":
    chapter_qs = df_all[df_all['Chapter'] == st.session_state.selected_chapter].to_dict('records')
    qs = st.session_state.quiz_state
    idx = qs['idx']

    if idx >= len(chapter_qs):
        idx = len(chapter_qs) - 1
        qs['idx'] = idx

    q_data = chapter_qs[idx]
    remaining = int(qs['end_time'] - time.time())
    all_answered = len(qs['answers']) == len(chapter_qs)

    if remaining <= 0 and not all_answered:
        st.session_state.step = "results"
        st.rerun()

    # ── Sidebar ────────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("<b style='color:#FFD700;'>⏳ Time Remaining</b>", unsafe_allow_html=True)
        isolated_timer_component()
        st.markdown("---")
        st.title("Questions")
        nav_cols = st.columns(4)
        for i in range(len(chapter_qs)):
            if i in qs['answers']:
                lbl = "✅"
            elif i == idx:
                lbl = "▶"
            else:
                lbl = str(i + 1)
            if nav_cols[i % 4].button(lbl, key=f"nav_{i}"):
                st.session_state.just_answered_idx = None
                qs['idx'] = i
                st.rerun()
        st.markdown("---")
        if st.button("🚪 Quit Test", key="quit_sidebar"):
            st.session_state.step = "confirm_quit"
            st.rerun()

    # ── Question header ────────────────────────────────────────────────────────
    t1, t2 = st.columns([3, 1])
    t1.subheader(f"Question {idx + 1} of {len(chapter_qs)}")
    with t2:
        isolated_timer_component()

    st.markdown(f"<h3 style='text-align: center; color: #FFD700;'>{q_data['Question']}</h3>", unsafe_allow_html=True)

    just_answered = (st.session_state.just_answered_idx == idx)

    if idx not in qs['answers']:
        opts = [q_data.get('Option1'), q_data.get('Option2'), q_data.get('Option3'), q_data.get('Option4')]
        opts = [o for o in opts if pd.notna(o) and str(o).strip()]
        c1, c2 = st.columns(2)
        for i, opt in enumerate(opts):
            col = c1 if i < 2 else c2
            if col.button(str(opt), key=f"q_{idx}_{i}"):
                is_correct = str(opt).strip() == str(q_data['Correct Answer']).strip()
                qs['answers'][idx] = {"correct": is_correct, "chosen": str(opt).strip()}
                st.session_state.just_answered_idx = idx
                st.rerun()

    elif just_answered:
        ans = qs['answers'][idx]
        if ans['correct']:
            st.success(f"✅ Correct! The answer is: **{q_data['Correct Answer']}**")
        else:
            st.error(f"❌ Incorrect. You chose: **{ans['chosen']}** | Correct answer: **{q_data['Correct Answer']}**")

        explanation = q_data.get('Explanation of Correct Answer', '')
        if explanation and str(explanation).strip():
            st.markdown(f'''
                <div class="explanation-box">
                    <b style="color:#FFD700;">💡 Explanation:</b><br><br>
                    <span style="color:#FFFFFF;">{explanation}</span>
                </div>
            ''', unsafe_allow_html=True)

        st.write("")
        if idx + 1 < len(chapter_qs):
            if st.button("Next Question ➡️"):
                st.session_state.just_answered_idx = None
                qs['idx'] += 1
                st.rerun()
        else:
            if st.button("🏁 Submit Final Answers"):
                st.session_state.just_answered_idx = None
                st.session_state.step = "results"
                st.rerun()

    else:
        ans = qs['answers'][idx]
        icon = "✅" if ans['correct'] else "❌"
        st.markdown(
            f"<p style='text-align:center; color:#AAAAAA; font-style:italic;'>{icon} You already answered this question.</p>",
            unsafe_allow_html=True)
        if idx + 1 < len(chapter_qs):
            if st.button("Next Question ➡️"):
                st.session_state.just_answered_idx = None
                qs['idx'] += 1
                st.rerun()
        else:
            if st.button("🏁 Submit Final Answers"):
                st.session_state.just_answered_idx = None
                st.session_state.step = "results"
                st.rerun()


# --- CONFIRM QUIT ---
elif st.session_state.step == "confirm_quit":
    st.markdown("<h2 style='text-align:center; color:#FFD700;'>⚠️ Quit Test?</h2>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        qs = st.session_state.quiz_state
        answered = len(qs['answers'])
        chapter_qs = df_all[df_all['Chapter'] == st.session_state.selected_chapter]
        total = len(chapter_qs)
        st.markdown(f"""
        <div style="background-color:#1b2641; padding:25px; border-radius:15px; border:1px solid #FFD700; text-align:center;">
            <p style="color:#FFFFFF; font-size:1.1rem;">
                You have answered <b style="color:#FFD700;">{answered} of {total}</b> questions.<br><br>
                Are you sure you want to quit? Your progress will be lost.
            </p>
        </div>
        """, unsafe_allow_html=True)
        st.write("")
        c1, c2 = st.columns(2)
        if c1.button("✅ Yes, Quit"):
            st.session_state.clear()
            st.rerun()
        if c2.button("↩️ Resume Test"):
            st.session_state.step = "quiz"
            st.rerun()


# --- RESULTS ---
elif st.session_state.step == "results":
    qs = st.session_state.quiz_state
    chapter_qs = df_all[df_all['Chapter'] == st.session_state.selected_chapter].to_dict('records')

    total = len(chapter_qs)
    correct_count = sum(1 for ans in qs['answers'].values() if ans.get('correct', False))
    attempted = len(qs['answers'])
    score_pct = (correct_count / total) * 100 if total > 0 else 0
    passed = score_pct > 90

    if passed:
        st.balloons()

    st.markdown("<h1 style='text-align:center; color:#FFD700;'>Assessment Complete!</h1>", unsafe_allow_html=True)

    color = "#28a745" if passed else "#dc3545"
    badge = "🏆 PASSED" if passed else "📚 Keep Practising"
    st.markdown(f"""
        <div class="result-card">
            <h2 style="color:#FFFFFF;">{st.session_state.user_name}</h2>
            <h3 style="color:#FFD700;">{st.session_state.selected_chapter}</h3>
            <p style="color:#CCCCCC; font-size:1.1rem;">
                Questions Attempted: <b>{attempted} / {total}</b><br>
                Correct Answers: <b>{correct_count}</b><br>
            </p>
            <h1 style="color:{color}; font-size:3rem;">{score_pct:.1f}%</h1>
            <h2 style="color:{color};">{badge}</h2>
        </div>
    """, unsafe_allow_html=True)

    if passed:
        st.markdown("<h3 style='text-align:center; color:#FFD700;'>🎓 You qualify for a certificate!</h3>",
                    unsafe_allow_html=True)
        date_str = datetime.now().strftime("%d %B %Y, %I:%M %p")
        cert_buffer = generate_certificate(st.session_state.user_name, st.session_state.selected_chapter, score_pct,
                                           date_str)
        if cert_buffer:
            _, mid, _ = st.columns([1, 2, 1])
            with mid:
                st.download_button(
                    label="📥 Download Your Certificate (PDF)",
                    data=cert_buffer,
                    file_name=f"Certificate_{st.session_state.user_name.replace(' ', '_')}.pdf",
                    mime="application/pdf"
                )
        else:
            st.info("Certificate generation requires `reportlab`. Run `pip install reportlab` to enable this feature.")
    else:
        st.markdown(
            f"<p style='text-align:center; color:#CCCCCC;'>Score above 90% to earn a certificate. You need <b style='color:#FFD700;'>{90 - score_pct:.1f}% more</b> to qualify.</p>",
            unsafe_allow_html=True)

    st.write("")
    col1, col2 = st.columns(2)
    if col1.button("🔄 Try Another Chapter"):
        st.session_state.selected_chapter = None
        st.session_state.quiz_state = {'idx': 0, 'answers': {}, 'end_time': None}
        st.session_state.step = "chapter_select"
        st.rerun()
    if col2.button("🏠 Start Over"):
        st.session_state.clear()
        st.rerun()