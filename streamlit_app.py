import streamlit as st
from supabase import create_client
import time

# --------------- Supabase-Client ---------------
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_ANON_KEY"]
supabase = create_client(URL, KEY)

# --------------- Page Config ---------------
st.set_page_config(page_title="90-Days Challenge MVP", layout="wide")

# --------------- Authentication ---------------
if "user" not in st.session_state:
    st.header("Login / Register")
    email = st.text_input("E-Mail")
    pwd = st.text_input("Passwort", type="password")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Login"):
            res = supabase.auth.sign_in_with_password({"email": email, "password": pwd})
            if res.data and res.data.get("session"):
                st.session_state.user = res.data["user"]
                st.experimental_rerun()
            else:
                st.error("Login fehlgeschlagen")
    with col2:
        if st.button("Register"):
            res = supabase.auth.sign_up({"email": email, "password": pwd})
            if res.data and res.data.get("user"):
                st.success("Account erstellt. Bitte E-Mail bestätigen.")
            else:
                st.error("Registrierung fehlgeschlagen")
    # Passwort-Reset
    reset = st.checkbox("Passwort vergessen?")
    if reset:
        with st.form("reset_form"):
            reset_email = st.text_input("E-Mail zum Zurücksetzen", value=email)
            reset_btn = st.form_submit_button("Reset-Link senden")
            if reset_btn:
                resp = supabase.auth.reset_password_for_email(
                    reset_email,
                    {"redirect_to": "https://sog-challange90d-fitness.streamlit.app"}
                )
                if resp.data:
                    st.info("E-Mail zum Zurücksetzen versendet")
                else:
                    st.error("Fehler beim Anfordern des Resets")
    st.stop()

user = st.session_state.user
st.sidebar.write(f"Angemeldet als: {user['email']}")

# --------------- Navigation ---------------
page = st.sidebar.radio("Menü", ["Dashboard", "Challenge", "History", "Logout"])
if page == "Logout":
    supabase.auth.sign_out()
    st.session_state.clear()
    st.experimental_rerun()

# --------------- Dashboard ---------------
if page == "Dashboard":
    st.title("Deine KPIs")
    # Gesamt Workouts
    sessions = supabase.table("user_sessions").select("recorded_at").eq("user_id", user['id']).execute().data or []
    st.metric("Workouts gesamt", len(sessions))
    # Tägliche Workouts Chart
    dates = [s['recorded_at'][:10] for s in sessions]
    if dates:
        counts = {d: dates.count(d) for d in sorted(set(dates))}
        st.bar_chart(counts)

# --------------- Challenge ---------------
elif page == "Challenge":
    st.title("90-Days Challenge")
    # Lade oder erstelle User-Challenge
    uc = supabase.table("user_challenges").select("id, current_day").eq("user_id", user['id']).single().execute().data
    if not uc:
        if st.button("Challenge starten"):
            r = supabase.table("user_challenges").insert({"user_id": user['id']}).execute()
            uc = r.data[0]
            st.experimental_rerun()
    if uc:
        day = st.slider("Wähle Tag", 1, 90, uc['current_day'])
        # Lese Programm-Details
        prog = supabase.table("programs").select("id, warmup_page, cooldown_page").eq("day", day).single().execute().data
        exercises = supabase.table("program_exercises").select("exercise_id, level, metric, sets, reps, rounds, duration_minutes").eq("program_id", prog['id']).order("level").execute().data or []
        # Warmup & Timer
        st.subheader(f"Tag {day} - Warm-up")
        if st.button("Start Warm-up (60s)"):
            placeholder = st.empty()
            for i in range(60, -1, -1):
                placeholder.write(f"Warm-up: {i//60:02d}:{i%60:02d}")
                time.sleep(1)
            st.audio('beep.mp3')
        # Übungen anzeigen
        st.subheader("Übungen")
        reps_input = {}
        for idx, e in enumerate(exercises):
            # Name abrufen
            name = supabase.table("exercises").select("name").eq("id", e['exercise_id']).single().execute().data['name']
            if e['metric'] == 'time':
                secs = e['duration_minutes'] * 60
                if st.button(f"Timer: {name} ({e['duration_minutes']} min)", key=f"btn_{idx}"):
                    ph = st.empty()
                    for t in range(secs, -1, -1):
                        ph.write(f"{name}: {t//60:02d}:{t%60:02d}")
                        time.sleep(1)
                    st.audio('beep.mp3')
                reps_input[e['exercise_id']] = st.number_input(f"Reps {name}", min_value=0, step=1, key=f"in_{idx}")
            else:
                reps_input[e['exercise_id']] = st.number_input(f"Reps {name}", min_value=0, step=1, key=f"in_{idx}")
        if st.button("Speichern Ergebnisse"):
            for eid, val in reps_input.items():
                supabase.table("user_sessions").insert({"user_id": user['id'], "program_id": prog['id'], "exercise_id": eid, "reps": val}).execute()
            supabase.table("user_challenges").update({"current_day": day + 1}).eq("id", uc['id']).execute()
            st.success("Ergebnisse gespeichert und Tag aktualisiert.")

# --------------- History ---------------
elif page == "History":
    st.title("Deine Versuche")
    data = supabase.table("user_sessions").select("exercise_id, reps, recorded_at").eq("user_id", user['id']).execute().data or []
    import pandas as pd
    df = pd.DataFrame(data)
    if not df.empty:
        df['date'] = df['recorded_at'].str[:10]
        df = df.merge(
            pd.DataFrame(supabase.table("exercises").select("id, name").execute().data),
            left_on='exercise_id', right_on='id', how='left'
        )
        stats = df.groupby('date')['reps'].sum().reset_index()
        st.line_chart(stats.rename(columns={'date':'index'}).set_index('index')['reps'])
    else:
        st.info("Noch keine Daten.")
