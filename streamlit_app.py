import streamlit as st
from supabase import create_client
import time
from postgrest import APIError

# --------------- Supabase-Client ---------------
URL = st.secrets.get("SUPABASE_URL")
KEY = st.secrets.get("SUPABASE_ANON_KEY")
if not URL or not KEY:
    st.error("Supabase-URL oder ANON-KEY fehlt in den Secrets.")
    st.stop()
supabase = create_client(URL, KEY)

# --------------- Page Config ---------------
st.set_page_config(page_title="90-Days Challenge MVP", layout="wide")

# --------------- Error-Handler ---------------
def safe_query(table_name, *query_args, **query_kwargs):
    try:
        result = getattr(supabase.table(table_name), *query_args)(**query_kwargs).execute()
        return result.data if hasattr(result, 'data') else result
    except APIError as err:
        st.error(f"Datenbankfehler bei '{table_name}': {err.message}. Bitte initialisiere das Schema.")
        st.stop()

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
                st.error("Login fehlgeschlagen. Überprüfe E-Mail/Passwort.")
    with col2:
        if st.button("Register"):
            reg_res = supabase.auth.sign_up({"email": email, "password": pwd})
            if getattr(reg_res, 'user', None):
                st.success("Account erstellt. Bitte E-Mail bestätigen.")
            else:
                st.error("Registrierung fehlgeschlagen.")
    # Passwort-Reset
    if st.button("Passwort vergessen?"):
        resp = supabase.auth.reset_password_for_email(
            email,
            {"redirect_to": "https://sog-challange90d-fitness.streamlit.app"}
        )
        if getattr(resp, 'error', None) is None:
            st.info("E-Mail mit Reset-Link versendet.")
        else:
            st.error("Fehler beim Anfordern des Resets.")
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
    entries = safe_query("user_sessions").select("recorded_at").eq("user_id", user.id)
    st.metric("Workouts gesamt", len(entries))
    if entries:
        dates = [e['recorded_at'][:10] for e in entries]
        counts = {d: dates.count(d) for d in sorted(set(dates))}
        st.bar_chart(counts)

# --------------- Challenge ---------------
elif page == "Challenge":
    st.title("90-Days Challenge")
    uc_list = safe_query("user_challenges").select("id, current_day").eq("user_id", user.id)
    uc = uc_list[0] if uc_list else None
    if not uc:
        if st.button("Challenge starten"):
            new_uc = safe_query("user_challenges").insert({"user_id": user.id})
            uc = new_uc[0]
            st.rerun()
    if uc:
        current_day = uc.get('current_day', 1)
        day = st.slider("Wähle Tag", 1, 90, current_day)
        prog = safe_query("programs").select("id, warmup_page, cooldown_page").eq("day", day)[0]
        exercises = safe_query("program_exercises").select(
            "exercise_id, level, metric, sets, reps, rounds, duration_minutes"
        ).eq("program_id", prog['id']).order("level")
        # Warm-up Timer
        st.subheader(f"Tag {day} - Warm-up")
        if st.button("Start Warm-up (60s)"):
            ph = st.empty()
            for i in range(60, -1, -1):
                ph.write(f"Warm-up: {i//60:02d}:{i%60:02d}")
                time.sleep(1)
            st.audio('beep.mp3')
        # Übungen und Eingabe
        st.subheader("Übungen")
        reps_input = {}
        for idx, e in enumerate(exercises):
            name = safe_query("exercises").select("name").eq("id", e['exercise_id'])[0]['name']
            label = f"{name}"
            if e['metric'] == 'time':
                secs = e['duration_minutes'] * 60
                if st.button(f"Timer: {label} ({e['duration_minutes']}min)", key=f"btn_{idx}"):
                    ph2 = st.empty()
                    for t in range(secs, -1, -1):
                        ph2.write(f"{label}: {t//60:02d}:{t%60:02d}")
                        time.sleep(1)
                    st.audio('beep.mp3')
                reps_input[e['exercise_id']] = st.number_input(
                    f"Reps {label}", min_value=0, step=1, key=f"in_{idx}"
                )
            else:
                reps_input[e['exercise_id']] = st.number_input(
                    f"Reps {label} ({e['metric']})",
                    min_value=0, step=1, key=f"in_{idx}"
                )
        if st.button("Speichern Ergebnisse"):
            for eid, val in reps_input.items():
                safe_query("user_sessions").insert({
                    "user_id": user.id,
                    "program_id": prog['id'],
                    "exercise_id": eid,
                    "reps": val
                })
            safe_query("user_challenges").update({"current_day": day + 1}).eq("id", uc['id'])
            st.success("Ergebnisse gespeichert und Tag aktualisiert.")

# --------------- History ---------------
elif page == "History":
    st.title("Deine Versuche")
    hist = safe_query("user_sessions").select("exercise_id, reps, recorded_at").eq("user_id", user.id)
    import pandas as pd
    if hist:
        df = pd.DataFrame(hist)
        df['date'] = df['recorded_at'].str[:10]
        ex_df = pd.DataFrame(safe_query("exercises").select("id, name"))
        df = df.merge(ex_df, left_on='exercise_id', right_on='id', how='left')
        stats = df.groupby('date')['reps'].sum().reset_index()
        st.line_chart(stats.rename(columns={'date':'index'}).set_index('index')['reps'])
    else:
        st.info("Noch keine Daten vorhanden.")
