import streamlit as st
import pandas as pd
import time
import os
import io
import re
import csv as csv_module
import base64
from datetime import datetime

# --- 1. PAGE CONFIG & STYLING ---
st.set_page_config(page_title="Sahayaks Academy Quiz", layout="wide")

st.markdown("""
    <style>
    .stApp {
        background-color: #0F1937;
        color: #FFFFFF;
    }
    .stTextInput label,
    .stTextInput > label,
    div[data-testid="stTextInput"] label {
        color: #FFFFFF !important;
        font-weight: bold !important;
        font-size: 1.2rem !important;
    }
    .stTextInput > div > div > input {
        background-color: #FFFFFF !important;
        color: #0F1937 !important;
        border: 2px solid #FFD700 !important;
        font-weight: bold;
    }
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
    /* Certificate open-button */
    .cert-btn-wrap a {
        display: block;
        background-color: #FFD700;
        color: #0F1937 !important;
        text-align: center;
        font-weight: bold;
        font-size: 1.1rem;
        padding: 16px;
        border-radius: 8px;
        border: 2px solid #0F1937;
        text-decoration: none;
        margin-top: 12px;
    }
    .cert-btn-wrap a:hover {
        background-color: #e6c200;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. SESSION STATE ---
if 'step'               not in st.session_state: st.session_state.step               = "login"
if 'user_name'          not in st.session_state: st.session_state.user_name          = ""
if 'selected_chapter'   not in st.session_state: st.session_state.selected_chapter   = None
if 'quiz_state'         not in st.session_state: st.session_state.quiz_state         = {'idx': 0, 'answers': {}, 'end_time': None}
if 'just_answered_idx'  not in st.session_state: st.session_state.just_answered_idx  = None


# --- 3. MATH SYMBOL REPAIR ---
def repair_math_symbols(text):
    if not isinstance(text, str):
        return text
    text = text.replace('\x92', "'").replace('\x93', '"').replace('\x94', '"')
    text = text.replace('\x96', '–').replace('\x97', '—')
    text = text.replace('? ? 3.14', 'π ≈ 3.14').replace('value of ?', 'value of π')
    text = re.sub(r'\?(\d)', r'√\1', text)
    if text.strip() == '?':
        return 'π'
    return text


# --- 4. CSV LOADER (robust: handles commas inside every field) ---
@st.cache_data
def load_data():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path  = os.path.join(script_dir, "MCQ for test.csv")

    if not os.path.exists(file_path):
        st.warning(f"⚠️ Data file not found at: {file_path}")
        return pd.DataFrame()

    EXPECTED = 10   # Board, Class, Chapter, Question, Opt1-4, Correct Answer, Explanation

    def parse_line(raw):
        """
        The CSV format wraps every row in a single outer pair of "…" quotes,
        and each individual field is further wrapped in ""…"" double-quote pairs.

        Steps:
          1. Strip the single outer wrapping quote from the whole row.
          2. Replace every "" (escaped-quote pair) with a single " so that
             csv.reader now sees properly quoted fields — commas INSIDE a
             question or explanation are protected and won't be mis-split.
          3. If the explanation still got split (e.g. it contained a literal
             quote), merge columns 10 onwards back into col 9.
        """
        line = raw.strip().strip('\r')
        if not line:
            return None
        # Step 1 – remove single outer wrapper
        if line.startswith('"') and line.endswith('"'):
            line = line[1:-1]
        # Step 2 – convert ""field"" → "field"
        line = line.replace('""', '"')
        # Step 3 – parse as standard CSV
        parsed = next(csv_module.reader([line], quotechar='"'))
        parsed = [f.strip() for f in parsed]
        # Step 4 – merge any explanation overflow back into col 9
        if len(parsed) > EXPECTED:
            parsed = parsed[:9] + [', '.join(parsed[9:])]
        return parsed if len(parsed) == EXPECTED else None

    try:
        header = None
        rows   = []
        with open(file_path, 'r', encoding='latin1') as f:
            for raw_line in f:
                result = parse_line(raw_line)
                if result is None:
                    continue
                if header is None:
                    header = result
                    continue
                rows.append(result)

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
        st.error(f"❌ 'Question' column not found. Headers: {list(df.columns)}")
        return pd.DataFrame()


df_all = load_data()


# --- 5. LIVE TIMER (fragment so it doesn't rerun the whole page) ---
@st.fragment(run_every=1.0)
def isolated_timer_component():
    if st.session_state.step == "quiz" and st.session_state.quiz_state.get('end_time'):
        remaining = max(int(st.session_state.quiz_state['end_time'] - time.time()), 0)
        mins, secs = divmod(remaining, 60)
        label     = f"⏳ {mins:02d}:{secs:02d}"
        css_class = "timer-card-urgent" if remaining <= 60 else "timer-card"
        st.markdown(f'<div class="{css_class}">{label}</div>', unsafe_allow_html=True)
        if remaining <= 0:
            st.session_state.step = "results"
            st.rerun()


# --- 6. CERTIFICATE — HTML rendered in browser (works on ALL mobile devices) ---
def generate_certificate_html(user_name, chapter, score_pct, date_str):
    """
    Returns a base64-encoded data-URI of a self-contained HTML certificate.
    Opening this URI in a new tab works on every mobile browser without any
    file-download permission — the student can then use the browser's built-in
    Share / Print / Save-as-PDF to keep it.
    """
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Certificate – {user_name}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@700&family=Open+Sans:wght@400;600&display=swap');
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: #0F1937;
    display: flex; align-items: center; justify-content: center;
    min-height: 100vh; padding: 20px;
    font-family: 'Open Sans', sans-serif;
  }}
  .cert {{
    background: #0F1937;
    border: 6px solid #FFD700;
    border-radius: 18px;
    padding: 60px 70px;
    max-width: 860px;
    width: 100%;
    text-align: center;
    box-shadow: 0 0 60px rgba(255,215,0,0.25);
    position: relative;
  }}
  .cert::before {{
    content: '';
    position: absolute; inset: 10px;
    border: 2px solid rgba(255,215,0,0.35);
    border-radius: 12px;
    pointer-events: none;
  }}
  .logo {{
    font-family: 'Cinzel', serif;
    font-size: 2.4rem;
    color: #FFD700;
    letter-spacing: 2px;
    margin-bottom: 6px;
  }}
  .subtitle {{
    font-size: 1.1rem;
    color: #CCCCCC;
    letter-spacing: 3px;
    text-transform: uppercase;
    margin-bottom: 30px;
  }}
  .divider {{
    border: none;
    border-top: 1px solid #FFD700;
    opacity: 0.5;
    margin: 20px auto;
    width: 80%;
  }}
  .certify-text {{
    color: #CCCCCC;
    font-size: 1rem;
    margin: 24px 0 10px;
  }}
  .student-name {{
    font-family: 'Cinzel', serif;
    font-size: 2.6rem;
    color: #FFD700;
    margin: 10px 0 16px;
    word-break: break-word;
  }}
  .completed-text {{
    color: #CCCCCC;
    font-size: 1rem;
    margin-bottom: 10px;
  }}
  .chapter-name {{
    font-size: 1.5rem;
    font-weight: 600;
    color: #FFFFFF;
    margin: 8px 0 20px;
    word-break: break-word;
  }}
  .score-badge {{
    display: inline-block;
    background: #FFD700;
    color: #0F1937;
    font-size: 1.6rem;
    font-weight: 700;
    padding: 10px 36px;
    border-radius: 50px;
    margin: 10px 0 28px;
  }}
  .date-text {{
    color: #AAAAAA;
    font-size: 0.9rem;
    margin-top: 24px;
  }}
  .footer {{
    color: #555E7A;
    font-size: 0.8rem;
    font-style: italic;
    margin-top: 12px;
  }}
  @media print {{
    body {{ background: white; padding: 0; }}
    .cert {{ border-color: #FFD700; box-shadow: none; max-width: 100%; }}
  }}
  @media (max-width: 600px) {{
    .cert {{ padding: 36px 24px; }}
    .logo {{ font-size: 1.6rem; }}
    .student-name {{ font-size: 1.8rem; }}
    .chapter-name {{ font-size: 1.1rem; }}
    .score-badge {{ font-size: 1.2rem; padding: 8px 24px; }}
  }}
</style>
</head>
<body>
  <div class="cert">
    <div class="logo">Sahayaks Education</div>
    <div class="subtitle">Certificate of Achievement</div>
    <hr class="divider"/>
    <p class="certify-text">This is to certify that</p>
    <div class="student-name">{user_name}</div>
    <p class="completed-text">has successfully completed the assessment for</p>
    <div class="chapter-name">{chapter}</div>
    <div class="score-badge">Score: {score_pct:.1f}%</div>
    <hr class="divider"/>
    <p class="date-text">Awarded on: {date_str}</p>
    <p class="footer">Sahayaks Education — Empowering Every Learner</p>
  </div>
</body>
</html>"""
    # Encode as base64 data-URI so it opens as a standalone page in any browser
    b64 = base64.b64encode(html.encode('utf-8')).decode('utf-8')
    return f"data:text/html;base64,{b64}"


# ─────────────────────────────────────────────────────────────────────────────
# --- 7. PAGES ---
# ─────────────────────────────────────────────────────────────────────────────

# ── LOGIN ─────────────────────────────────────────────────────────────────────
if st.session_state.step == "login":
    st.markdown("<h1 style='text-align:center;color:#FFD700;'>Sahayaks Education</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.markdown("<p style='color:#FFFFFF;font-weight:bold;font-size:1.1rem;'>Student Entrance</p>",
                    unsafe_allow_html=True)
        u_name = st.text_input("Full Name for Certificate",
                               value=st.session_state.user_name,
                               placeholder="Enter your full name...",
                               key="cert_name_input")
        if st.button("Start Assessment"):
            if u_name.strip():
                st.session_state.user_name = u_name.strip()
                st.session_state.step = "instructions"
                st.rerun()
            else:
                st.error("Please enter your name to proceed.")


# ── INSTRUCTIONS ──────────────────────────────────────────────────────────────
elif st.session_state.step == "instructions":
    st.markdown("<h2 style='text-align:center;color:#FFD700;'>Instructions</h2>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([0.1, 0.8, 0.1])
    with col2:
        st.markdown(f"""
        <div style="background-color:#1b2641;padding:25px;border-radius:15px;border:1px solid #FFD700;">
            <p style="color:#FFFFFF;">Welcome, <b>{st.session_state.user_name}</b>.</p>
            <ul style="color:#FFFFFF;line-height:2rem;">
                <li><b>Timer:</b> 1 minute per question (pooled). A 10-question chapter gives 10 minutes total.</li>
                <li><b>Feedback:</b> After each answer you will see if you were right or wrong, the correct answer, and a brief explanation.</li>
                <li><b>Navigation:</b> Use the sidebar to jump between questions.</li>
                <li><b>Results:</b> Only your final score is shown at the end — no full answer breakdown.</li>
                <li><b>Certificate:</b> Awarded automatically if you score above 90%. Opens in your browser — use Share / Print to save it.</li>
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


# ── CHAPTER SELECT ────────────────────────────────────────────────────────────
elif st.session_state.step == "chapter_select":
    st.markdown("<h2 style='text-align:center;color:#FFD700;'>Select a Chapter</h2>", unsafe_allow_html=True)
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
                    'end_time': time.time() + (len(chapter_qs) * 60)   # 1 min / question
                }
                st.session_state.step = "quiz"
                st.rerun()


# ── QUIZ ──────────────────────────────────────────────────────────────────────
elif st.session_state.step == "quiz":
    chapter_qs = df_all[df_all['Chapter'] == st.session_state.selected_chapter].to_dict('records')
    qs  = st.session_state.quiz_state
    idx = qs['idx']

    if idx >= len(chapter_qs):
        idx = len(chapter_qs) - 1
        qs['idx'] = idx

    q_data    = chapter_qs[idx]
    remaining = int(qs['end_time'] - time.time())

    if remaining <= 0 and len(qs['answers']) < len(chapter_qs):
        st.session_state.step = "results"
        st.rerun()

    # Sidebar
    with st.sidebar:
        st.markdown("<b style='color:#FFD700;'>⏳ Time Remaining</b>", unsafe_allow_html=True)
        isolated_timer_component()
        st.markdown("---")
        st.title("Questions")
        nav_cols = st.columns(4)
        for i in range(len(chapter_qs)):
            lbl = "✅" if i in qs['answers'] else ("▶" if i == idx else str(i + 1))
            if nav_cols[i % 4].button(lbl, key=f"nav_{i}"):
                st.session_state.just_answered_idx = None
                qs['idx'] = i
                st.rerun()
        st.markdown("---")
        if st.button("🚪 Quit Test", key="quit_sidebar"):
            st.session_state.step = "confirm_quit"
            st.rerun()

    # Question
    t1, t2 = st.columns([3, 1])
    t1.subheader(f"Question {idx + 1} of {len(chapter_qs)}")
    with t2:
        isolated_timer_component()

    st.markdown(f"<h3 style='text-align:center;color:#FFD700;'>{q_data['Question']}</h3>",
                unsafe_allow_html=True)

    just_answered = (st.session_state.just_answered_idx == idx)

    if idx not in qs['answers']:
        opts = [q_data.get(k) for k in ['Option1', 'Option2', 'Option3', 'Option4']]
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
            st.markdown(f"""
                <div class="explanation-box">
                    <b style="color:#FFD700;">💡 Explanation:</b><br><br>
                    <span style="color:#FFFFFF;">{explanation}</span>
                </div>""", unsafe_allow_html=True)

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
        ans  = qs['answers'][idx]
        icon = "✅" if ans['correct'] else "❌"
        st.markdown(f"<p style='text-align:center;color:#AAAAAA;font-style:italic;'>"
                    f"{icon} You already answered this question.</p>", unsafe_allow_html=True)
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


# ── CONFIRM QUIT ──────────────────────────────────────────────────────────────
elif st.session_state.step == "confirm_quit":
    st.markdown("<h2 style='text-align:center;color:#FFD700;'>⚠️ Quit Test?</h2>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        qs       = st.session_state.quiz_state
        answered = len(qs['answers'])
        total    = len(df_all[df_all['Chapter'] == st.session_state.selected_chapter])
        st.markdown(f"""
        <div style="background-color:#1b2641;padding:25px;border-radius:15px;border:1px solid #FFD700;text-align:center;">
            <p style="color:#FFFFFF;font-size:1.1rem;">
                You have answered <b style="color:#FFD700;">{answered} of {total}</b> questions.<br><br>
                Are you sure you want to quit? Your progress will be lost.
            </p>
        </div>""", unsafe_allow_html=True)
        st.write("")
        c1, c2 = st.columns(2)
        if c1.button("✅ Yes, Quit"):
            st.session_state.clear(); st.rerun()
        if c2.button("↩️ Resume Test"):
            st.session_state.step = "quiz"; st.rerun()


# ── RESULTS ───────────────────────────────────────────────────────────────────
elif st.session_state.step == "results":
    qs         = st.session_state.quiz_state
    chapter_qs = df_all[df_all['Chapter'] == st.session_state.selected_chapter].to_dict('records')
    total         = len(chapter_qs)
    correct_count = sum(1 for a in qs['answers'].values() if a.get('correct', False))
    attempted     = len(qs['answers'])
    score_pct     = (correct_count / total * 100) if total > 0 else 0
    passed        = score_pct > 90

    if passed:
        st.balloons()

    st.markdown("<h1 style='text-align:center;color:#FFD700;'>Assessment Complete!</h1>",
                unsafe_allow_html=True)

    color = "#28a745" if passed else "#dc3545"
    badge = "🏆 PASSED" if passed else "📚 Keep Practising"
    st.markdown(f"""
        <div class="result-card">
            <h2 style="color:#FFFFFF;">{st.session_state.user_name}</h2>
            <h3 style="color:#FFD700;">{st.session_state.selected_chapter}</h3>
            <p style="color:#CCCCCC;font-size:1.1rem;">
                Questions Attempted: <b>{attempted} / {total}</b><br>
                Correct Answers: <b>{correct_count}</b>
            </p>
            <h1 style="color:{color};font-size:3rem;">{score_pct:.1f}%</h1>
            <h2 style="color:{color};">{badge}</h2>
        </div>""", unsafe_allow_html=True)

    if passed:
        st.markdown("<h3 style='text-align:center;color:#FFD700;'>🎓 You qualify for a certificate!</h3>",
                    unsafe_allow_html=True)
        date_str  = datetime.now().strftime("%d %B %Y, %I:%M %p")
        cert_uri  = generate_certificate_html(
                        st.session_state.user_name,
                        st.session_state.selected_chapter,
                        score_pct, date_str)

        # ── Mobile-safe certificate button ──────────────────────────────────
        # Opens the certificate as a full HTML page in a new browser tab.
        # Works on iPhone, Android, and desktop — no file download needed.
        # Students can then use browser Share → Save as PDF / Screenshot to keep it.
        _, mid, _ = st.columns([1, 2, 1])
        with mid:
            st.markdown(f"""
                <div class="cert-btn-wrap">
                    <a href="{cert_uri}" target="_blank">
                        🎓 Open My Certificate
                    </a>
                </div>
                <p style="color:#AAAAAA;font-size:0.85rem;text-align:center;margin-top:8px;">
                    Opens in a new tab — use your browser's Share or Print option to save it as a PDF.
                </p>""", unsafe_allow_html=True)
    else:
        needed = 90 - score_pct
        st.markdown(f"<p style='text-align:center;color:#CCCCCC;'>Score above 90% to earn a certificate. "
                    f"You need <b style='color:#FFD700;'>{needed:.1f}% more</b> to qualify.</p>",
                    unsafe_allow_html=True)

    st.write("")
    col1, col2 = st.columns(2)
    if col1.button("🔄 Try Another Chapter"):
        st.session_state.selected_chapter = None
        st.session_state.quiz_state       = {'idx': 0, 'answers': {}, 'end_time': None}
        st.session_state.step             = "chapter_select"
        st.rerun()
    if col2.button("🏠 Start Over"):
        st.session_state.clear()
        st.rerun()
