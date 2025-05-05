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

# --------------- Table Helper ---------------
def get_table(name: str):
    try:
        return supabase.table(name)
    except APIError as err:
        st.error(f"Fehler beim Zugriff auf Tabelle '{name}': {err.message}")
        st.stop()

# --------------- Authentication ---------------
if "user" not in st.session_state:
    st.header("Login / Register")
    email = st.text_input("E-Mail")
    pwd = st.text_input("Passwort", type="password")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Login"):
            res = supabase.auth.sign_in_with_password({"email": email, "password": pwd})
            if getattr(res, 'user', None):
                st.session_state.user = res.user
                st.rerun()
            else:
                st.error("Login fehlgeschlagen. E-Mail oder Passwort falsch.")
    with col2:
        if st.button("Register"):
            res = supabase.auth.sign_up({"email": email, "password": pwd})
            if getattr(res, 'user', None):
                st.success("Account erstellt. Bitte bestätige Deine E-Mail.")
            else:
                st.error("Registrierung fehlgeschlagen.")
    if st.button("Passwort vergessen?"):
        res = supabase.auth.reset_password_for_email(
            email,
            {"redirect_to": "https://sog-challange90d-fitness.streamlit.app"}
        )
        if getattr(res, 'error', None) is None:
            st.info("E-Mail mit Reset-Link wurde versendet.")
        else:
            st.error("Fehler beim Anfordern des Resets.")
    st.stop()

user = st.session_state.user
st.sidebar.write(f"Angemeldet als: {user.email}")

# --------------- Navigation ---------------
page = st.sidebar.radio("Menü", ["Dashboard", "Challenge", "History"] )
if st.sidebar.button("Logout", key="logout_btn"):
    supabase.auth.sign_out()
    st.session_state.clear()
    st.rerun()

# --------------- Dashboard ---------------
if page == "Dashboard":
    st.title("Deine KPIs")
    # Workouts zählen
    res = get_table("user_sessions").select("recorded_at").eq("user_id", user.id).execute()
    entries = res.data or []
    st.metric("Workouts gesamt", len(entries))
    if entries:
        dates = [e["recorded_at"][:10] for e in entries]
        counts = {d: dates.count(d) for d in sorted(set(dates))}
        st.bar_chart(counts)

# --------------- Challenge ---------------
elif page == "Challenge":
    st.title("90-Days Challenge")
    # Lade oder starte Challenge
    res = get_table("user_challenges").select("id, current_day").eq("user_id", user.id).execute()
    uc = res.data[0] if res.data else None
    if not uc:
        if st.button("Challenge starten"):
            r = get_table("user_challenges").insert({"user_id": user.id}).execute()
            uc = r.data[0]
            st.rerun()
    if uc:
        current = uc.get("current_day", 1)
        day = st.slider("Wähle Tag", 1, 90, current)
        p = get_table("programs").select("id, warmup_page, cooldown_page").eq("day", day).execute().data[0]
        exercises = get_table("program_exercises").select(
            "exercise_id, metric, sets, reps, rounds, duration_minutes"
        ).eq("program_id", p["id"]).order("level").execute().data or []
        # Warm-up
        st.subheader(f"Warm-up (60s)")
        if st.button("Start Warm-up"):
            ph = st.empty()
            for i in range(60, -1, -1):
                ph.write(f"{i//60:02d}:{i%60:02d}")
                time.sleep(1)
            st.audio("beep.mp3")
        # Übungen
        st.subheader("Übungen")
        inputs = {}
        for idx, ex in enumerate(exercises):
            name = get_table("exercises").select("name").eq("id", ex["exercise_id"]).execute().data[0]["name"]
            label = name
            if ex["metric"] == "time":
                secs = ex["duration_minutes"] * 60
                if st.button(f"Timer: {label} ({ex['duration_minutes']}min)", key=f"timer_{idx}"):
                    ph2 = st.empty()
                    for t in range(secs, -1, -1):
                        ph2.write(f"{t//60:02d}:{t%60:02d}")
                        time.sleep(1)
                    st.audio("beep.mp3")
                inputs[ex["exercise_id"]] = st.number_input(f"Reps {label}", min_value=0, step=1, key=f"input_{idx}")
            else:
                inputs[ex["exercise_id"]] = st.number_input(f"Reps {label} ({ex['metric']})", min_value=0, step=1, key=f"input_{idx}")
        if st.button("Speichern Ergebnisse"):
            for eid, val in inputs.items():
                get_table("user_sessions").insert({
                    "user_id": user.id,
                    "program_id": p["id"],
                    "exercise_id": eid,
                    "reps": val
                }).execute()
            get_table("user_challenges").update({"current_day": day+1}).eq("id", uc["id"]).execute()
            st.success("Ergebnisse gespeichert und Tag aktualisiert.")

# --------------- History ---------------
elif page == "History":
    st.title("Deine Versuche")
    hist = get_table("user_sessions").select("exercise_id, reps, recorded_at").eq("user_id", user.id).execute().data or []
    import pandas as pd
    if hist:
        df = pd.DataFrame(hist)
        df["date"] = df["recorded_at"].str[:10]
        ex_df = pd.DataFrame(get_table("exercises").select("id, name").execute().data)
        df = df.merge(ex_df, left_on="exercise_id", right_on="id", how="left")
        stats = df.groupby("date")["reps"].sum().reset_index()
        st.line_chart(stats.rename(columns={"date":"index"}).set_index("index")["reps"])
    else:
        st.info("Noch keine Daten vorhanden.")
