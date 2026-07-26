"""
AI STUDY PLANNER PRO — Streamlit Edition
==========================================
Converted from the original Tkinter desktop app into a single-file,
browser-based, mobile-compatible Streamlit application.

Preserves original functionality:
  - Splash Screen
  - Login
  - Subject Selection + Custom Subject Add
  - Difficulty Selection (Easy / Medium / Hard)
  - BFS demonstration (kept, and reused inside the scheduler)

New features added:
  - Chapter-based planning (user enters number of chapters + names per subject)
  - Exam date + daily study hours input
  - AI-style adaptive scheduler:
        * Weighted round-robin queue (BFS/deque based) that prioritizes
          harder subjects more frequently
        * Per-chapter time automatically scaled by difficulty
        * Automatic revision days inserted at regular intervals,
          focused on the hardest subjects first
        * Rule-based study tips generated per subject

Run locally:
    pip install streamlit
    streamlit run app.py

Deploy (free, public link, judges can just open a URL):
    1. Push this file + requirements.txt to a public GitHub repo.
    2. Go to https://share.streamlit.io -> "New app" -> pick the repo/file.
    3. Deploy. You get a public https://<name>.streamlit.app link.
"""

import streamlit as st
from collections import deque
from datetime import date, timedelta

# ----------------------------------------------------------------------
# THEME (kept from the original Tkinter app)
# ----------------------------------------------------------------------
NAVY_BLUE = "#0B0B1F"
BABY_PINK = "#E9CD53"
SILVER = "#C0C0C0"
LIGHT_BLUE = "#ADD8E6"
BLACK = "#000000"
WHITE = "#FFFFFF"

WEIGHTS = {"Easy": 1, "Medium": 2, "Hard": 3}

st.set_page_config(page_title="AI Study Planner Pro", page_icon="📘", layout="centered")

st.markdown(
    f"""
    <style>
    .stApp {{
        background-color: {NAVY_BLUE};
        color: {WHITE};
    }}
    h1, h2, h3, .title-text {{
        color: {BABY_PINK} !important;
        font-weight: 800 !important;
    }}
    .subtitle-text {{
        color: {LIGHT_BLUE} !important;
        font-weight: 700 !important;
    }}
    div.stButton > button {{
        background-color: {BABY_PINK};
        color: {BLACK};
        font-weight: 700;
        border-radius: 8px;
        border: none;
        padding: 0.6em 1em;
    }}
    div.stButton > button:hover {{
        background-color: {LIGHT_BLUE};
        color: {BLACK};
    }}
    .card {{
        background-color: {SILVER};
        color: {BLACK};
        border-radius: 10px;
        padding: 14px 18px;
        margin-bottom: 10px;
    }}
    .revision-card {{
        background-color: {LIGHT_BLUE};
        color: {BLACK};
        border-radius: 10px;
        padding: 14px 18px;
        margin-bottom: 10px;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------
# SESSION STATE
# ----------------------------------------------------------------------
_defaults = {
    "stage": "splash",
    "user_name": "",
    "subjects_list": ["Physics", "Maths", "Computer", "English", "Urdu", "Chemistry"],
    "selected_subjects": [],
    "difficulty": {},
    "num_chapters": {},
    "chapters": {},
    "daily_hours": 2.0,
    "exam_date": date.today() + timedelta(days=14),
    "plan": None,
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


def goto(stage: str):
    st.session_state.stage = stage
    st.rerun()


# ----------------------------------------------------------------------
# BFS DEMONSTRATION (kept from the original app)
# ----------------------------------------------------------------------
def bfs_screen_demo():
    """BFS traversal over the app's screen graph — same idea as the
    original Tkinter version's bfs_demo(), now also shown to the user."""
    screens = ["Splash", "Login", "Selection", "Difficulty", "Chapters", "Schedule Setup", "Planner"]
    queue = deque(screens)
    visited = []
    while queue:
        visited.append(queue.popleft())
    return visited


# ----------------------------------------------------------------------
# AI-STYLE ADAPTIVE SCHEDULER
# ----------------------------------------------------------------------
def build_weighted_queue(selected_subjects, chapters, difficulty):
    """
    Weighted round-robin queue built with collections.deque (BFS style).
    Harder subjects appear more often per rotation cycle, so their
    chapters get pulled into the schedule earlier and more frequently.
    Returns a deque of (subject, chapter_name, minutes_for_chapter).
    """
    total_minutes_per_subject = {}
    total_weight = sum(WEIGHTS[difficulty[s]] for s in selected_subjects)

    # Rough per-subject time share (used to size each chapter's duration)
    for s in selected_subjects:
        n_chapters = max(1, len(chapters[s]))
        # Base per-chapter minutes scaled by difficulty weight
        base = 25  # baseline minutes per chapter
        scaled = base * WEIGHTS[difficulty[s]]
        total_minutes_per_subject[s] = scaled

    subject_queues = {
        s: deque([(s, ch, total_minutes_per_subject[s]) for ch in chapters[s]])
        for s in selected_subjects
    }

    # Build rotation order: harder subjects repeat more times per cycle
    rotation = []
    for s in selected_subjects:
        rotation.extend([s] * WEIGHTS[difficulty[s]])

    master_queue = deque()
    remaining = sum(len(q) for q in subject_queues.values())
    idx = 0
    while remaining > 0:
        s = rotation[idx % len(rotation)]
        if subject_queues[s]:
            master_queue.append(subject_queues[s].popleft())
            remaining -= 1
        idx += 1
        if idx > 100000:  # safety valve
            break

    return master_queue


def generate_plan(selected_subjects, difficulty, chapters, daily_hours, exam_date):
    days_left = (exam_date - date.today()).days
    if days_left < 1:
        return None, "Exam date must be at least 1 day from today."

    daily_minutes = int(daily_hours * 60)
    if daily_minutes <= 0:
        return None, "Daily study hours must be greater than 0."

    # Insert a revision day every 4th study day
    REVISION_EVERY = 4

    master_queue = build_weighted_queue(selected_subjects, chapters, difficulty)

    plan = []
    covered_subjects_order = []  # tracks subjects studied so far, in order, for revision focus
    day_number = 0
    study_day_counter = 0

    while master_queue and day_number < 90:  # 90-day safety cap
        day_number += 1
        study_day_counter += 1

        # Revision day
        if study_day_counter % REVISION_EVERY == 0 and covered_subjects_order:
            # Prioritize hardest subjects covered so far for revision
            unique_covered = list(dict.fromkeys(covered_subjects_order))
            unique_covered.sort(key=lambda s: WEIGHTS[difficulty[s]], reverse=True)
            focus = unique_covered[:3] if len(unique_covered) > 3 else unique_covered
            plan.append({
                "day": day_number,
                "type": "revision",
                "focus_subjects": focus,
            })
            continue

        # Normal study day — fill with chapter tasks up to daily_minutes
        minutes_left = daily_minutes
        tasks_today = []
        while master_queue and minutes_left > 0:
            subj, chap, mins = master_queue[0]
            if mins <= minutes_left or not tasks_today:
                master_queue.popleft()
                tasks_today.append((subj, chap, mins))
                covered_subjects_order.append(subj)
                minutes_left -= mins
            else:
                break

        if not tasks_today:
            break

        plan.append({
            "day": day_number,
            "type": "study",
            "tasks": tasks_today,
        })

        if day_number >= days_left and master_queue:
            # Ran out of calendar days before finishing chapters — keep going,
            # but this signals the plan is tight.
            pass

    return plan, None


def format_minutes(mins):
    mins = round(mins)
    h = mins // 60
    m = mins % 60
    if h > 0 and m > 0:
        return f"{h}h {m}m"
    if h > 0:
        return f"{h}h"
    return f"{m}m"


def study_tip(subject, level):
    tips = {
        "Hard": f"🧠 AI Tip: {subject} is Hard — tackle it earlier in the day when focus is highest, and revise it most often.",
        "Medium": f"🧠 AI Tip: {subject} is Medium — a steady daily dose works better than cramming.",
        "Easy": f"🧠 AI Tip: {subject} is Easy — light, quick sessions are enough; don't over-allocate time here.",
    }
    return tips[level]


# ----------------------------------------------------------------------
# SCREENS
# ----------------------------------------------------------------------
def render_splash():
    st.markdown(
        f"""
        <div style='text-align:center; padding-top:80px;'>
            <div style='width:200px;height:200px;border:5px solid {LIGHT_BLUE};
                        border-radius:50%; margin:0 auto; display:flex;
                        align-items:center; justify-content:center;'>
                <span style='font-size:60px;font-weight:bold;color:{BABY_PINK};'>SP</span>
            </div>
            <h2 style='color:{SILVER}; margin-top:30px;'>STUDY PLANNER</h2>
            <p style='color:{LIGHT_BLUE};'>AI-Powered Study Planner Pro</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write("")
    if st.button("▶  START", use_container_width=True):
        goto("login")


def render_login():
    st.markdown("<h2>USER ACCESS</h2>", unsafe_allow_html=True)
    name = st.text_input("NAME", value=st.session_state.user_name)
    if st.button("LOGIN", use_container_width=True):
        if not name.strip():
            st.error("Please enter your name!")
        else:
            st.session_state.user_name = name.strip()
            goto("selection")


def render_selection():
    st.markdown("<h2>SELECT SUBJECTS</h2>", unsafe_allow_html=True)

    current_selection = []
    for sub in st.session_state.subjects_list:
        checked = st.checkbox(
            sub,
            value=(sub in st.session_state.selected_subjects),
            key=f"chk_{sub}",
        )
        if checked:
            current_selection.append(sub)

    st.write("---")
    col1, col2 = st.columns([3, 1])
    with col1:
        new_sub = st.text_input("Add a custom subject", key="new_sub_input", label_visibility="collapsed", placeholder="Add a custom subject")
    with col2:
        if st.button("+ ADD"):
            val = new_sub.strip()
            if val and val not in st.session_state.subjects_list:
                st.session_state.subjects_list.append(val)
                st.session_state.selected_subjects = current_selection
                goto("selection")

    st.write("")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("← BACK", use_container_width=True):
            st.session_state.selected_subjects = current_selection
            goto("login")
    with c2:
        if st.button("NEXT →", use_container_width=True):
            if not current_selection:
                st.warning("Select at least one subject!")
            else:
                st.session_state.selected_subjects = current_selection
                goto("difficulty")


def render_difficulty():
    st.markdown("<h2>LEVEL CONFIG</h2>", unsafe_allow_html=True)

    new_diff = {}
    for sub in st.session_state.selected_subjects:
        current = st.session_state.difficulty.get(sub, "Medium")
        st.markdown(f"<div class='card'><b>{sub}</b></div>", unsafe_allow_html=True)
        level = st.selectbox(
            f"Difficulty for {sub}",
            ["Easy", "Medium", "Hard"],
            index=["Easy", "Medium", "Hard"].index(current),
            key=f"diff_{sub}",
            label_visibility="collapsed",
        )
        new_diff[sub] = level

    st.write("")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("← BACK", use_container_width=True):
            st.session_state.difficulty = new_diff
            goto("selection")
    with c2:
        if st.button("NEXT →", use_container_width=True):
            st.session_state.difficulty = new_diff
            goto("chapters")


def render_chapters():
    st.markdown("<h2>CHAPTERS</h2>", unsafe_allow_html=True)
    st.caption("Tell the planner how many chapters each subject has, and name them.")

    for sub in st.session_state.selected_subjects:
        st.markdown(f"<div class='card'><b>{sub}</b></div>", unsafe_allow_html=True)
        default_n = st.session_state.num_chapters.get(sub, 5)
        n = st.number_input(
            f"Number of chapters — {sub}",
            min_value=1, max_value=50, value=default_n, step=1,
            key=f"nchap_{sub}",
        )
        st.session_state.num_chapters[sub] = n

        existing = st.session_state.chapters.get(sub, [])
        chapter_names = []
        cols = st.columns(2)
        for i in range(n):
            default_name = existing[i] if i < len(existing) else f"Chapter {i+1}"
            col = cols[i % 2]
            with col:
                name = st.text_input(
                    f"{sub} — Ch. {i+1}",
                    value=default_name,
                    key=f"chap_{sub}_{i}",
                )
            chapter_names.append(name.strip() or f"Chapter {i+1}")
        st.session_state.chapters[sub] = chapter_names
        st.write("")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("← BACK", use_container_width=True):
            goto("difficulty")
    with c2:
        if st.button("NEXT →", use_container_width=True):
            goto("schedule_setup")


def render_schedule_setup():
    st.markdown("<h2>DAILY HOURS & EXAM DATE</h2>", unsafe_allow_html=True)

    hours = st.number_input(
        "How many hours can you study per day?",
        min_value=0.5, max_value=16.0, value=float(st.session_state.daily_hours), step=0.5,
    )
    exam_date = st.date_input(
        "Exam date",
        value=st.session_state.exam_date,
        min_value=date.today() + timedelta(days=1),
    )

    st.session_state.daily_hours = hours
    st.session_state.exam_date = exam_date

    c1, c2 = st.columns(2)
    with c1:
        if st.button("← BACK", use_container_width=True):
            goto("chapters")
    with c2:
        if st.button("GENERATE PLAN →", use_container_width=True):
            plan, err = generate_plan(
                st.session_state.selected_subjects,
                st.session_state.difficulty,
                st.session_state.chapters,
                st.session_state.daily_hours,
                st.session_state.exam_date,
            )
            if err:
                st.error(err)
            else:
                st.session_state.plan = plan
                goto("planner")


def render_planner():
    st.markdown("<h2>OPTIMIZED PLAN</h2>", unsafe_allow_html=True)
    st.markdown(f"<p class='subtitle-text'>STUDENT: {st.session_state.user_name.upper()}</p>", unsafe_allow_html=True)

    days_left = (st.session_state.exam_date - date.today()).days
    plan = st.session_state.plan or []
    if plan and plan[-1]["day"] > days_left:
        st.warning(
            f"Your chapters need about {plan[-1]['day']} study days, but only {days_left} "
            f"days remain before the exam. Consider increasing daily study hours."
        )

    for entry in plan:
        if entry["type"] == "revision":
            focus = ", ".join(entry["focus_subjects"])
            st.markdown(
                f"""<div class='revision-card'>
                <b>Day {entry['day']} — 🔁 REVISION DAY</b><br>
                Focus: {focus}
                </div>""",
                unsafe_allow_html=True,
            )
        else:
            rows = "".join(
                f"<div>📘 <b>{subj}</b> — {chap} <i>({format_minutes(mins)})</i></div>"
                for subj, chap, mins in entry["tasks"]
            )
            st.markdown(
                f"<div class='card'><b>Day {entry['day']}</b><br>{rows}</div>",
                unsafe_allow_html=True,
            )

    st.write("---")
    st.markdown("<h3>AI Study Tips</h3>", unsafe_allow_html=True)
    for sub in st.session_state.selected_subjects:
        st.write(study_tip(sub, st.session_state.difficulty[sub]))

    with st.expander("⚙️ How the scheduler works (BFS / queue demonstration)"):
        st.write(
            "Screen navigation follows a BFS traversal, and the study plan itself "
            "is built with a weighted round-robin queue (Python's collections.deque): "
            "harder subjects are placed into the rotation more times per cycle, so "
            "their chapters are pulled and scheduled earlier and more frequently."
        )
        visited = bfs_screen_demo()
        st.code(" → ".join(visited), language="text")

    st.write("")
    if st.button("↺ NEW SESSION", use_container_width=True):
        st.session_state.plan = None
        goto("selection")


# ----------------------------------------------------------------------
# ROUTER
# ----------------------------------------------------------------------
STAGES = {
    "splash": render_splash,
    "login": render_login,
    "selection": render_selection,
    "difficulty": render_difficulty,
    "chapters": render_chapters,
    "schedule_setup": render_schedule_setup,
    "planner": render_planner,
}

STAGES[st.session_state.stage]()
