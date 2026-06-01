import streamlit as st
import pandas as pd
import time
import os
import io
import re
import csv as csv_module
import base64
from datetime import datetime, timezone, timedelta

# ─────────────────────────────────────────────────────────────────────────────
# 1. PAGE CONFIG & GLOBAL CSS
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Sahayaks Academy Quiz", layout="wide")

st.markdown("""
<style>
.stApp { background-color: #0F1937; color: #FFFFFF; }

/* Input label */
.stTextInput label, div[data-testid="stTextInput"] label {
    color: #FFFFFF !important; font-weight: bold !important; font-size: 1.2rem !important;
}
/* Input box */
.stTextInput > div > div > input {
    background-color: #FFFFFF !important; color: #0F1937 !important;
    border: 2px solid #FFD700 !important; font-weight: bold;
}
/* Regular buttons */
.stButton > button {
    background-color: #FFFFFF !important; color: #0F1937 !important;
    border: 1px solid #FFD700 !important; font-weight: bold !important;
    width: 100%; height: 48px;
}
.stButton > button:hover { background-color: #f0f0f0 !important; }

/* Explanation box */
.explanation-box {
    background-color: #1b2641; padding: 20px;
    border-left: 5px solid #FFD700; border-radius: 8px; margin-top: 20px;
}
/* Timer */
.timer-card {
    background-color: #FFD700; color: #0F1937; padding: 10px;
    border-radius: 8px; text-align: center; font-weight: bold; font-size: 1.4rem;
}
.timer-card-urgent {
    background-color: #dc3545; color: #FFFFFF; padding: 10px;
    border-radius: 8px; text-align: center; font-weight: bold; font-size: 1.4rem;
    animation: pulse 1s infinite;
}
@keyframes pulse { 0%{opacity:1} 50%{opacity:0.6} 100%{opacity:1} }

/* Result card */
.result-card {
    background-color: #1b2641; padding: 30px; border-radius: 15px;
    border: 2px solid #FFD700; text-align: center; margin-bottom: 20px;
}

/* ── Certificate download button ─────────────────────────────────────────
   Styled as a big gold anchor tag — works on every device because it is
   just a plain HTML link, not a JS-triggered download.               */
.cert-download-wrap {
    text-align: center; margin: 18px 0 6px;
}
.cert-download-wrap a {
    display: inline-block;
    background-color: #FFD700; color: #0F1937 !important;
    font-weight: bold; font-size: 1.15rem;
    padding: 15px 0; width: 100%; max-width: 480px;
    border-radius: 8px; border: 2px solid #0F1937;
    text-decoration: none; letter-spacing: 0.3px;
}
.cert-download-wrap a:hover { background-color: #e6c200; }
.cert-hint {
    color: #AAAAAA; font-size: 0.82rem; text-align: center; margin-top: 6px;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# 2. SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────
defaults = {
    'step': 'login',
    'user_name': '',
    'selected_chapter': None,
    'quiz_state': {'idx': 0, 'answers': {}, 'end_time': None},
    'just_answered_idx': None,
    'cert_b64': None,   # base64 PDF string — generated once, survives reruns
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ─────────────────────────────────────────────────────────────────────────────
# 3. MATH SYMBOL REPAIR
# ─────────────────────────────────────────────────────────────────────────────
def repair_math_symbols(text):
    if not isinstance(text, str):
        return text
    text = text.replace('\x92',"'").replace('\x93','"').replace('\x94','"')
    text = text.replace('\x96','–').replace('\x97','—')
    text = text.replace('? ? 3.14','π ≈ 3.14').replace('value of ?','value of π')
    text = re.sub(r'\?(\d)', r'√\1', text)
    return 'π' if text.strip() == '?' else text


# ─────────────────────────────────────────────────────────────────────────────
# 4. CSV LOADER
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data
def load_data():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path  = os.path.join(script_dir, "MCQ for test.csv")
    if not os.path.exists(file_path):
        st.warning(f"⚠️ Data file not found at: {file_path}")
        return pd.DataFrame()

    EXPECTED = 10

    def parse_line(raw):
        line = raw.strip().strip('\r')
        if not line:
            return None
        if line.startswith('"') and line.endswith('"'):
            line = line[1:-1]
        line = line.replace('""', '"')
        parsed = next(csv_module.reader([line], quotechar='"'))
        parsed = [f.strip() for f in parsed]
        if len(parsed) > EXPECTED:
            parsed = parsed[:9] + [', '.join(parsed[9:])]
        return parsed if len(parsed) == EXPECTED else None

    try:
        header, rows = None, []
        with open(file_path, 'r', encoding='latin1') as f:
            for raw_line in f:
                result = parse_line(raw_line)
                if result is None:
                    continue
                if header is None:
                    header = result
                else:
                    rows.append(result)
        if not rows:
            st.error("❌ CSV file appears to be empty.")
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=header)
        df.columns = df.columns.str.strip()
    except Exception as e:
        st.error(f"❌ Error processing CSV: {e}")
        return pd.DataFrame()

    for col in df.columns:
        df[col] = df[col].apply(repair_math_symbols)

    if 'Question' not in df.columns:
        st.error(f"❌ 'Question' column not found. Headers: {list(df.columns)}")
        return pd.DataFrame()
    return df.dropna(subset=['Question'])


df_all = load_data()


# ─────────────────────────────────────────────────────────────────────────────
# 5. LIVE TIMER
# ─────────────────────────────────────────────────────────────────────────────
@st.fragment(run_every=1.0)
def isolated_timer_component():
    if st.session_state.step == "quiz" and st.session_state.quiz_state.get('end_time'):
        remaining = max(int(st.session_state.quiz_state['end_time'] - time.time()), 0)
        mins, secs = divmod(remaining, 60)
        css = "timer-card-urgent" if remaining <= 60 else "timer-card"
        st.markdown(f'<div class="{css}">⏳ {mins:02d}:{secs:02d}</div>', unsafe_allow_html=True)
        if remaining <= 0:
            st.session_state.step = "results"
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# 6. IST TIMESTAMP
# ─────────────────────────────────────────────────────────────────────────────
def get_ist_timestamp():
    IST = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(IST).strftime("%d %B %Y, %I:%M %p IST")


# ─────────────────────────────────────────────────────────────────────────────
# 7. PDF CERTIFICATE  (reportlab — server-side, no browser quirks)
# ─────────────────────────────────────────────────────────────────────────────
def build_certificate_pdf(user_name, chapter, score_pct, date_str) -> bytes:
    """Renders a landscape-A4 PDF and returns raw bytes."""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas as rl_canvas

    buf   = io.BytesIO()
    w, h  = landscape(A4)
    c     = rl_canvas.Canvas(buf, pagesize=landscape(A4))

    # Background
    c.setFillColor(colors.HexColor("#0F1937"))
    c.rect(0, 0, w, h, fill=1, stroke=0)

    # Borders
    c.setStrokeColor(colors.HexColor("#FFD700"))
    c.setLineWidth(7);  c.roundRect(18, 18, w-36, h-36, 12, fill=0, stroke=1)
    c.setLineWidth(2);  c.roundRect(30, 30, w-60, h-60,  8, fill=0, stroke=1)

    # Org name
    c.setFillColor(colors.HexColor("#FFD700"))
    c.setFont("Helvetica-Bold", 40)
    c.drawCentredString(w/2, h-100, "Sahayaks Education")

    # Subtitle
    c.setFillColor(colors.white)
    c.setFont("Helvetica", 20)
    c.drawCentredString(w/2, h-135, "Certificate of Achievement")

    # Divider
    c.setStrokeColor(colors.HexColor("#FFD700")); c.setLineWidth(1)
    c.line(80, h-155, w-80, h-155)

    # "This is to certify that"
    c.setFillColor(colors.HexColor("#CCCCCC"))
    c.setFont("Helvetica", 15)
    c.drawCentredString(w/2, h-192, "This is to certify that")

    # Student name — shrink to fit
    ns = 36
    while c.stringWidth(user_name, "Helvetica-Bold", ns) > (w-160) and ns > 18:
        ns -= 1
    c.setFillColor(colors.HexColor("#FFD700"))
    c.setFont("Helvetica-Bold", ns)
    c.drawCentredString(w/2, h-238, user_name)

    # "has successfully completed…"
    c.setFillColor(colors.HexColor("#CCCCCC"))
    c.setFont("Helvetica", 15)
    c.drawCentredString(w/2, h-275, "has successfully completed the assessment for")

    # Chapter — shrink to fit
    cs = 22
    while c.stringWidth(chapter, "Helvetica-Bold", cs) > (w-160) and cs > 12:
        cs -= 1
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", cs)
    c.drawCentredString(w/2, h-312, chapter)

    # Score badge
    bw, bh = 210, 42
    c.setFillColor(colors.HexColor("#FFD700"))
    c.roundRect(w/2-bw/2, h-378, bw, bh, 21, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#0F1937"))
    c.setFont("Helvetica-Bold", 21)
    c.drawCentredString(w/2, h-378+12, f"Score:  {score_pct:.1f}%")

    # Divider
    c.setStrokeColor(colors.HexColor("#FFD700")); c.setLineWidth(1)
    c.line(80, h-402, w-80, h-402)

    # Date
    c.setFillColor(colors.HexColor("#AAAAAA"))
    c.setFont("Helvetica", 12)
    c.drawCentredString(w/2, h-428, f"Awarded on:  {date_str}")

    # Footer
    c.setFillColor(colors.HexColor("#555E7A"))
    c.setFont("Helvetica-Oblique", 11)
    c.drawCentredString(w/2, h-450, "Sahayaks Education — Empowering Every Learner")

    c.save()
    buf.seek(0)
    return buf.read()


def cert_download_html(b64_str: str, filename: str) -> str:
    """
    Returns an HTML anchor with the PDF embedded as a base64 data-URI.
    Using `download` attribute + `data:application/pdf` is the most
    universally compatible approach:
      • Desktop (Chrome / Firefox / Edge / Safari) → direct download
      • Android Chrome → download to Downloads folder
      • iPhone Safari → opens PDF viewer; user taps Share → Save to Files
    No JavaScript, no Streamlit download-button quirks involved.
    """
    href = f"data:application/pdf;base64,{b64_str}"
    return f"""
<div class="cert-download-wrap">
  <a href="{href}" download="{filename}">📥 Download Certificate (PDF)</a>
</div>
<p class="cert-hint">
  Desktop / Android: file saves automatically to your Downloads folder.<br>
  iPhone: PDF opens in a viewer — tap <b>Share → Save to Files</b> to keep it.
</p>"""


# ─────────────────────────────────────────────────────────────────────────────
# PAGES
# ─────────────────────────────────────────────────────────────────────────────

# ── LOGIN ─────────────────────────────────────────────────────────────────────
if st.session_state.step == "login":
    st.markdown("<h1 style='text-align:center;color:#FFD700;'>Sahayaks Education</h1>",
                unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1.5, 1])
    with mid:
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
    st.markdown("<h2 style='text-align:center;color:#FFD700;'>Instructions</h2>",
                unsafe_allow_html=True)
    _, mid, _ = st.columns([0.1, 0.8, 0.1])
    with mid:
        st.markdown(f"""
        <div style="background-color:#1b2641;padding:25px;border-radius:15px;border:1px solid #FFD700;">
          <p style="color:#FFFFFF;">Welcome, <b>{st.session_state.user_name}</b>.</p>
          <ul style="color:#FFFFFF;line-height:2.2rem;">
            <li><b>Timer:</b> 1 minute per question (pooled). A 10-question chapter gives 10 minutes total.</li>
            <li><b>Feedback:</b> After each answer you will see the correct answer and a brief explanation.</li>
            <li><b>Navigation:</b> Use the sidebar to jump between questions.</li>
            <li><b>Results:</b> Only your final score is shown at the end.</li>
            <li><b>Certificate:</b> Awarded automatically if you score above 90%. Downloads as a PDF on all devices.</li>
          </ul>
        </div>""", unsafe_allow_html=True)
        st.write("")
        c1, c2 = st.columns(2)
        if c1.button("✅ I Agree"):
            st.session_state.step = "chapter_select"; st.rerun()
        if c2.button("❌ Quit"):
            st.session_state.step = "login"; st.rerun()


# ── CHAPTER SELECT ────────────────────────────────────────────────────────────
elif st.session_state.step == "chapter_select":
    st.markdown("<h2 style='text-align:center;color:#FFD700;'>Select a Chapter</h2>",
                unsafe_allow_html=True)
    if df_all.empty:
        st.error("No data loaded. Please verify your CSV file path and structure.")
    else:
        chapters = sorted(df_all['Chapter'].unique())
        cols = st.columns(3)
        for i, ch in enumerate(chapters):
            if cols[i % 3].button(f"📘 {ch}", key=f"ch_{i}"):
                chapter_qs = df_all[df_all['Chapter'] == ch]
                st.session_state.selected_chapter = ch
                st.session_state.cert_b64         = None   # reset for new attempt
                st.session_state.quiz_state = {
                    'idx': 0, 'answers': {},
                    'end_time': time.time() + len(chapter_qs) * 60
                }
                st.session_state.step = "quiz"
                st.rerun()


# ── QUIZ ──────────────────────────────────────────────────────────────────────
elif st.session_state.step == "quiz":
    chapter_qs = df_all[df_all['Chapter'] == st.session_state.selected_chapter].to_dict('records')
    qs  = st.session_state.quiz_state
    idx = min(qs['idx'], len(chapter_qs) - 1)
    qs['idx'] = idx
    q_data = chapter_qs[idx]

    if int(qs['end_time'] - time.time()) <= 0 and len(qs['answers']) < len(chapter_qs):
        st.session_state.step = "results"; st.rerun()

    # Sidebar
    with st.sidebar:
        st.markdown("<b style='color:#FFD700;'>⏳ Time Remaining</b>", unsafe_allow_html=True)
        isolated_timer_component()
        st.markdown("---")
        st.title("Questions")
        nav_cols = st.columns(4)
        for i in range(len(chapter_qs)):
            lbl = "✅" if i in qs['answers'] else ("▶" if i == idx else str(i+1))
            if nav_cols[i % 4].button(lbl, key=f"nav_{i}"):
                st.session_state.just_answered_idx = None
                qs['idx'] = i; st.rerun()
        st.markdown("---")
        if st.button("🚪 Quit Test", key="quit_sidebar"):
            st.session_state.step = "confirm_quit"; st.rerun()

    # Question header
    t1, t2 = st.columns([3, 1])
    t1.subheader(f"Question {idx+1} of {len(chapter_qs)}")
    with t2: isolated_timer_component()

    st.markdown(f"<h3 style='text-align:center;color:#FFD700;'>{q_data['Question']}</h3>",
                unsafe_allow_html=True)

    just_answered = (st.session_state.just_answered_idx == idx)

    if idx not in qs['answers']:
        opts = [q_data.get(k) for k in ['Option1','Option2','Option3','Option4']]
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
            st.error(f"❌ Incorrect. You chose: **{ans['chosen']}** | Correct: **{q_data['Correct Answer']}**")
        expl = q_data.get('Explanation of Correct Answer', '')
        if expl and str(expl).strip():
            st.markdown(f"""<div class="explanation-box">
                <b style="color:#FFD700;">💡 Explanation:</b><br><br>
                <span style="color:#FFFFFF;">{expl}</span></div>""",
                unsafe_allow_html=True)
        st.write("")
        if idx + 1 < len(chapter_qs):
            if st.button("Next Question ➡️"):
                st.session_state.just_answered_idx = None; qs['idx'] += 1; st.rerun()
        else:
            if st.button("🏁 Submit Final Answers"):
                st.session_state.just_answered_idx = None
                st.session_state.step = "results"; st.rerun()

    else:
        icon = "✅" if qs['answers'][idx]['correct'] else "❌"
        st.markdown(f"<p style='text-align:center;color:#AAAAAA;font-style:italic;'>"
                    f"{icon} You already answered this question.</p>", unsafe_allow_html=True)
        if idx + 1 < len(chapter_qs):
            if st.button("Next Question ➡️"):
                st.session_state.just_answered_idx = None; qs['idx'] += 1; st.rerun()
        else:
            if st.button("🏁 Submit Final Answers"):
                st.session_state.just_answered_idx = None
                st.session_state.step = "results"; st.rerun()


# ── CONFIRM QUIT ──────────────────────────────────────────────────────────────
elif st.session_state.step == "confirm_quit":
    st.markdown("<h2 style='text-align:center;color:#FFD700;'>⚠️ Quit Test?</h2>",
                unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1.5, 1])
    with mid:
        answered = len(st.session_state.quiz_state['answers'])
        total    = len(df_all[df_all['Chapter'] == st.session_state.selected_chapter])
        st.markdown(f"""
        <div style="background-color:#1b2641;padding:25px;border-radius:15px;
                    border:1px solid #FFD700;text-align:center;">
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

    # ── Build the PDF certificate BEFORE st.balloons() ──────────────────────
    # Stored in session_state so it survives every rerun (including the one
    # that balloons() triggers internally).
    if passed and st.session_state.cert_b64 is None:
        try:
            pdf_bytes = build_certificate_pdf(
                st.session_state.user_name,
                st.session_state.selected_chapter,
                score_pct,
                get_ist_timestamp()
            )
            st.session_state.cert_b64 = base64.b64encode(pdf_bytes).decode('utf-8')
        except Exception as e:
            st.session_state.cert_b64 = ""   # empty string = generation failed
            st.error(f"Certificate generation error: {e}. "
                     "Ensure reportlab is installed: pip install reportlab")

    if passed:
        st.balloons()

    # Score card
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

    # Certificate section
    if passed and st.session_state.cert_b64:
        st.markdown("<h3 style='text-align:center;color:#FFD700;'>🎓 You qualify for a certificate!</h3>",
                    unsafe_allow_html=True)
        _, mid, _ = st.columns([1, 2, 1])
        with mid:
            safe = re.sub(r'[^\w\s-]', '', st.session_state.user_name).strip().replace(' ', '_')
            filename = f"Certificate_{safe}.pdf"
            st.markdown(cert_download_html(st.session_state.cert_b64, filename),
                        unsafe_allow_html=True)
    elif not passed:
        needed = 90 - score_pct
        st.markdown(
            f"<p style='text-align:center;color:#CCCCCC;'>Score above 90% to earn a certificate. "
            f"You need <b style='color:#FFD700;'>{needed:.1f}% more</b> to qualify.</p>",
            unsafe_allow_html=True)

    st.write("")
    c1, c2 = st.columns(2)
    if c1.button("🔄 Try Another Chapter"):
        st.session_state.selected_chapter = None
        st.session_state.cert_b64         = None
        st.session_state.quiz_state       = {'idx': 0, 'answers': {}, 'end_time': None}
        st.session_state.step             = "chapter_select"; st.rerun()
    if c2.button("🏠 Start Over"):
        st.session_state.clear(); st.rerun()
