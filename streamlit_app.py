import streamlit as st
from supabase_client import supabase
import time

st.set_page_config(page_title="90-Days Challenge", layout="wide")
# —————————————————————————————————
# 1) Auth
if "user" not in st.session_state:
    st.header("Login / Register")
    email = st.text_input("E-Mail")
    pwd   = st.text_input("Passwort", type="password")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Login"):
            res = supabase.auth.sign_in_with_password({"email":email,"password":pwd})
            if res.user: st.session_state.user = res.user
            else: st.error("Login fehlgeschlagen")
    with col2:
        if st.button("Register"):
            res = supabase.auth.sign_up({"email":email,"password":pwd})
            if res.user: st.success("Account erstellt") 
            else: st.error("Registrierung fehlgeschlagen")
    st.stop()

user = st.session_state.user
st.sidebar.write(f"Angemeldet als: {user.email}")

# —————————————————————————————————
# 2) Navigation
page = st.sidebar.radio("Menü", ["Dashboard","Challenge","History","Logout"])
if page=="Logout":
    supabase.auth.sign_out()
    st.session_state.clear()
    st.rerun()

# —————————————————————————————————
# 3) Dashboard
if page=="Dashboard":
    st.title("Deine KPIs")
    # Lädt alle Sessions des Users
    sessions = supabase.table("user_sessions")\
        .select("id, session_id, recorded_at")\
        .eq("user_id", user.id).execute().data or []
    st.metric("Workouts gesamt", len(sessions))
    # Beispiel-Chart: tägliche Workouts
    dates = [s["recorded_at"][:10] for s in sessions]
    st.bar_chart({d: dates.count(d) for d in set(dates)})

# —————————————————————————————————
# 4) Challenge
elif page=="Challenge":
    st.title("90-Days Challenge")
    # 4.1 Starten / Fortsetzen
    uc = supabase.table("user_challenges")\
        .select("*").eq("user_id", user.id).single().execute().data
    if not uc:
        if st.button("Challenge starten"):
            res = supabase.table("user_challenges")\
                .insert({"user_id":user.id,"started_at":"now()"}).execute()
            uc = res.data[0]
    if uc:
        day = st.slider("Tag wählen", 1, 90, uc.get("current_day",1))
        # Übungen laden
        prog = supabase.table("programs")\
            .select("id").eq("day", day).single().execute().data
        exs = supabase.table("program_exercises")\
            .select("exercise_id, metric, sets, reps, rounds, duration_minutes")\
            .eq("program_id", prog["id"]).order("level").execute().data or []
        # 4.2 Anzeige & Eingabe
        st.subheader(f"Tag {day}")
        inputs = {}
        for e in exs:
            name = supabase.table("exercises")\
                .select("name").eq("id",e["exercise_id"]).single().execute().data["name"]
            label = f"{name} ({e['metric']})"
            inputs[e["exercise_id"]] = st.number_input(label, min_value=0, step=1)
        if st.button("Speichern"):
            for eid, val in inputs.items():
                supabase.table("user_sessions")\
                    .insert({
                      "user_id": user.id,
                      "program_id": prog["id"],
                      "exercise_id": eid,
                      "reps": val
                    }).execute()
            supabase.table("user_challenges")\
                .update({"current_day": day})\
                .eq("id", uc["id"]).execute()
            st.success("Gespeichert")
        # 4.3 Timer
        if st.button("Start Warm-up (60 s)"):
            placeholder = st.empty()
            for i in range(60, -1, -1):
                placeholder.write(f"Warm-up: {i//60:02d}:{i%60:02d}")
                time.sleep(1)
            st.markdown(
              "<audio autoplay src='beep.mp3'></audio>",
              unsafe_allow_html=True
            )

# —————————————————————————————————
# 5) History
elif page=="History":
    st.title("Deine Versuche")
    rows = supabase.table("user_sessions")\
        .select("exercise_id, reps, recorded_at")\
        .eq("user_id", user.id).execute().data or []
    # DataFrame & Chart
    import pandas as pd
    df = pd.DataFrame(rows)
    df["date"] = df["recorded_at"].str[:10]
    stats = df.groupby("date")["reps"].sum().reset_index()
    st.line_chart(stats.rename(columns={"date":"index"}).set_index("index")["reps"])
