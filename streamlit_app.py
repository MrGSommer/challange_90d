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
            auth_res = supabase.auth.sign_in_with_password({"email": email, "password": pwd})
            if getattr(auth_res, 'user', None):
                st.session_state.user = auth_res.user
                st.rerun()
            else:
                st.error("Login fehlgeschlagen")
    with col2:
        if st.button("Register"):
            reg_res = supabase.auth.sign_up({"email": email, "password": pwd})
            if getattr(reg_res, 'user', None):
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
                if getattr(resp, 'error', None) is None:
                    st.info("E-Mail zum Zurücksetzen versendet")
                else:
                    st.error("Fehler beim Anfordern des Resets")
    st.stop()

user = st.session_state.user
st.sidebar.write(f"Angemeldet als: {user.email}")

# --------------- Navigation ---------------
page = st.sidebar.radio("Menü", ["Dashboard", "Challenge", "History", "Logout"])
if page == "Logout":
    supabase.auth.sign_out()
    st.session_state.clear()
    st.rerun()

# --------------- Dashboard ---------------
if page == "Dashboard":
    st.title("Deine KPIs")
    sessions = supabase.table("user_sessions").select("recorded_at").eq("user_id", user.id).execute()
    data = sessions.data if hasattr(sessions, 'data') else sessions
    entries = data or []
    st.metric("Workouts gesamt", len(entries))
    dates = [s['recorded_at'][:10] for s in entries]
    if dates:
        counts = {d: dates.count(d) for d in sorted(set(dates))}
        st.bar_chart(counts)

# --------------- Challenge ---------------
elif page == "Challenge":
    st.title("90-Days Challenge")
    uc_res = supabase.table("user_challenges").select("id, current_day").eq("user_id", user.id).single().execute()
    uc = uc_res.data if hasattr(uc_res, 'data') else uc_res
    if not uc:
        if st.button("Challenge starten"):
            r = supabase.table("user_challenges").insert({"user_id": user.id}).execute()
            uc = r.data[0]
            st.rerun()
    if uc:
        current = uc['current_day'] if 'current_day' in uc else 1
        day = st.slider("Wähle Tag", 1, 90, current)
        prog_res = supabase.table("programs").select("id").eq("day", day).single().execute()
        prog = prog_res.data if hasattr(prog_res, 'data') else prog_res
        exercises_res = supabase.table("program_exercises").select("exercise_id, level, metric, sets, reps, rounds, duration_minutes").eq("program_id", prog['id']).order("level").execute()
        exercises = exercises_res.data if hasattr(exercises_res, 'data') else exercises_res
        # Warm-up Timer
        st.subheader(f"Tag {day} - Warm-up")
        if st.button("Start Warm-up (60s)"):
            placeholder = st.empty()
            for i in range(60, -1, -1):
                placeholder.write(f"Warm-up: {i//60:02d}:{i%60:02d}")
                time.sleep(1)
            st.audio('beep.mp3')
        # Übungsliste & Eingabe
        st.subheader("Übungen")
        reps_input = {}
        for idx, e in enumerate(exercises):
            name_res = supabase.table("exercises").select("name").eq("id", e['exercise_id']).single().execute()
            name = name_res.data['name']
            label = name
            if e['metric'] == 'time':
                secs = e['duration_minutes'] * 60
                if st.button(f"Timer: {label} ({e['duration_minutes']} min)", key=f"btn_{idx}"):
                    ph = st.empty()
                    for t in range(secs, -1, -1):
                        ph.write(f"{label}: {t//60:02d}:{t%60:02d}")
                        time.sleep(1)
                    st.audio('beep.mp3')
                reps_input[e['exercise_id']] = st.number_input(f"Reps {label}", min_value=0, step=1, key=f"in_{idx}")
            else:
                reps_input[e['exercise_id']] = st.number_input(f"Reps {label}", min_value=0, step=1, key=f"in_{idx}")
        if st.button("Speichern Ergebnisse"):
            for eid, val in reps_input.items():
                supabase.table("user_sessions").insert({"user_id": user.id, "program_id": prog['id'], "exercise_id": eid, "reps": val}).execute()
            supabase.table("user_challenges").update({"current_day": day + 1}).eq("id", uc['id']).execute()
            st.success("Ergebnisse gespeichert und Tag aktualisiert.")

# --------------- History ---------------
elif page == "History":
    st.title("Deine Versuche")
    hist_res = supabase.table("user_sessions").select("exercise_id, reps, recorded_at").eq("user_id", user.id).execute()
    hist = hist_res.data if hasattr(hist_res, 'data') else hist_res
    import pandas as pd
    df = pd.DataFrame(hist)
    if not df.empty:
        df['date'] = df['recorded_at'].str[:10]
        ex_res = supabase.table("exercises").select("id, name").execute()
        ex_df = pd.DataFrame(ex_res.data)
        df = df.merge(ex_df, left_on='exercise_id', right_on='id', how='left')
        stats = df.groupby('date')['reps'].sum().reset_index()
        st.line_chart(stats.rename(columns={'date':'index'}).set_index('index')['reps'])
    else:
        st.info("Noch keine Daten.")
