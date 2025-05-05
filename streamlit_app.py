import streamlit as st
from supabase import create_client
from postgrest import APIError
import datetime
import pandas as pd

# ---------------- Supabase-Client ----------------
URL = st.secrets.get("SUPABASE_URL")
KEY = st.secrets.get("SUPABASE_ANON_KEY")
if not URL or not KEY:
    st.error("Supabase-URL oder ANON-KEY fehlt in den Secrets.")
    st.stop()

supabase = create_client(URL, KEY)
token = st.session_state.get("auth_token")
if token:
    supabase.postgrest.auth(token)

# ---------------- Page Config ----------------
st.set_page_config(page_title="90-Days Challenge MVP", layout="wide")

# ---------------- Authentication ----------------
if "user" not in st.session_state:
    st.header("Login / Register")
    email = st.text_input("E-Mail")
    pwd = st.text_input("Passwort", type="password")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Login"):
            auth = supabase.auth.sign_in_with_password({"email": email, "password": pwd})
            session = getattr(auth, 'session', None)
            user = getattr(auth, 'user', None)
            if session and user:
                st.session_state.user = user
                st.session_state.auth_token = session.access_token
                supabase.postgrest.auth(session.access_token)
                st.experimental_rerun()
            else:
                st.error("Login fehlgeschlagen.")
    with col2:
        if st.button("Register"):
            reg = supabase.auth.sign_up({"email": email, "password": pwd})
            if getattr(reg, 'user', None):
                st.success("Account erstellt. Bitte E-Mail prüfen.")
            else:
                st.error("Registrierung fehlgeschlagen.")
    if st.button("Passwort vergessen?"):
        res = supabase.auth.reset_password_for_email(
            email,
            {"redirect_to": st.secrets.get("APP_URL")}  # anpassen
        )
        if not getattr(res, 'error', None):
            st.info("Reset-E-Mail gesendet.")
        else:
            st.error("Fehler beim Passwort-Reset.")
    st.stop()

# eingeloggter User
user = st.session_state.user

# Helper zum Tabellenzugriff
def get_table(name: str):
    return supabase.table(name)

# Challenge-State laden
uc_data = get_table("user_challenges").select("id, current_day, paused_until").eq("user_id", user.id).execute().data or []
uc = uc_data[0] if uc_data else None

# Exercise Metadata laden
ed = get_table("exercise_details").select("exercise_id, level, description, focus").execute().data or []
exercise_info = {x['exercise_id']: x for x in ed}

# Sidebar mit Level-Auswahl
st.sidebar.write(f"Angemeldet: {user.email}")
st.sidebar.subheader("Training-Level")
levels = [1,2,3]
def_lvl = st.session_state.get("level",1)
sel = st.sidebar.selectbox("Level", levels, index=levels.index(def_lvl))
st.session_state.level = sel
page = st.sidebar.radio("Menü", ["Dashboard","Challenge","Exercises","History"])
if st.sidebar.button("Logout"):
    supabase.auth.sign_out()
    st.session_state.clear()
    st.experimental_rerun()

# Dashboard
if page == "Dashboard":
    st.title("Dashboard")
    if not uc:
        if st.button("Challenge starten"):
            get_table("user_challenges").insert({"user_id": user.id}).execute()
            st.experimental_rerun()
        st.stop()
    st.markdown("---")
    st.subheader("Challenge-Steuerung")
    c1, c2 = st.columns([3,1])
    today = datetime.date.today()
    with c1:
        nd = st.number_input("Tag setzen",1,90,value=uc['current_day'])
        if st.button("Setzen"):
            get_table("user_challenges").update({"current_day": nd}).eq("id", uc['id']).execute()
            st.experimental_rerun()
    with c2:
        pu = uc.get('paused_until')
        if not pu:
            if st.button("Pause 7 Tage"):
                dt = today + datetime.timedelta(days=7)
                get_table("user_challenges").update({"paused_until": dt.isoformat()}).eq("id", uc['id']).execute()
                st.experimental_rerun()
        else:
            dd = datetime.date.fromisoformat(pu[:10])
            st.info(f"Pausiert bis {dd}")
    st.markdown("---")
    st.metric("Aktueller Tag", uc['current_day'])

# Challenge Page
elif page == "Challenge":
    if not uc:
        st.info("Keine Challenge aktiv.")
        st.stop()
    day = uc['current_day']
    prog = get_table("programs").select("id, workout_name").eq("day", day).execute().data
    if not prog:
        st.warning("Kein Workout für diesen Tag.")
        st.stop()
    pid, title = prog[0]['id'], prog[0]['workout_name']
    st.title(f"Tag {day}: {title}")

    # Übungen abrufen\    
pes = get_table("program_exercises").select(
        "exercise_id, level, sets, reps, rounds, duration_minutes, metric"
    ).eq("program_id", pid).execute().data or []
    names = {e['id']: e['name'] for e in get_table("exercises").select("id, name").execute().data}

    # Auswahl pro Übung basierend auf Level mit Fallback\    
pick = []
    for eid in {p['exercise_id'] for p in pes}:
        group = [p for p in pes if p['exercise_id']==eid]
        exact = [p for p in group if p['level']==sel]
        if exact:
            ch = exact[0]
        else:
            higher = sorted([p for p in group if p['level']>sel], key=lambda x: x['level'])
            ch = higher[0] if higher else min(group, key=lambda x: x['level'])
        pick.append(ch)

    # Exakte Reihenfolge festlegen per exercise_id
    exercise_order = {104: 0, 107: 1, 89: 2, 95: 3}
    pick = sorted(pick, key=lambda p: exercise_order.get(p['exercise_id'], 99))

    # Darstellung\    
    for p in pick:
        nm = names.get(p['exercise_id'], "Unbekannt")
        st.subheader(f"{nm} (Level {p['level']})")
        parts = []
        if p.get('sets') is not None: parts.append(f"Sätze: {p['sets']}")
        if p.get('reps') is not None: parts.append(f"Reps: {p['reps']}")
        if p.get('rounds') is not None: parts.append(f"Runden: {p['rounds']}")
        if p.get('duration_minutes') is not None: parts.append(f"Dauer: {p['duration_minutes']} min")
        if p.get('metric'): parts.append(f"Metrik: {p['metric']}")
        if parts:
            st.write(", ".join(parts))
        det = exercise_info.get(p['exercise_id'], {})
        if det.get('description'): st.write(det['description'])
        if det.get('focus'): st.write(f"**Fokus:** {det['focus']}")

# Exercises Page
elif page == "Exercises":
    st.title("Alle Übungen")
    exs = get_table("exercises").select("id, name").execute().data or []
    for ex in exs:
        info = exercise_info.get(ex['id'], {})
        st.subheader(f"{ex['name']} (Level {info.get('level','?')})")
        if info.get('description'): st.write(info['description'])
        if info.get('focus'): st.write(f"**Fokus:** {info['focus']}")
        st.markdown("---")

# History Page
elif page == "History":
    st.title("History")
    his = get_table("user_sessions").select("exercise_id, reps, recorded_at").eq("user_id", user.id).execute().data or []
    if his:
        df = pd.DataFrame(his)
        df['date'] = df['recorded_at'].str[:10]
        names = pd.DataFrame(get_table("exercises").select("id, name").execute().data)
        df = df.merge(names, left_on="exercise_id", right_on="id")
        chart = df.groupby('date')['reps'].sum().reset_index()
        st.line_chart(chart.rename(columns={'date':'index'}).set_index('index')['reps'])
    else:
        st.info("Noch keine Daten.")
