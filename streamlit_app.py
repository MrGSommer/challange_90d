import streamlit as st
from supabase import create_client
import time
from postgrest import APIError
import datetime
import pandas as pd

# --------------- Supabase-Client ---------------
URL = st.secrets.get("SUPABASE_URL")
KEY = st.secrets.get("SUPABASE_ANON_KEY")
if not URL or not KEY:
    st.error("Supabase-URL oder ANON-KEY fehlt in den Secrets.")
    st.stop()
supabase = create_client(URL, KEY)

def get_table(name: str):
    try:
        return supabase.table(name)
    except Exception as err:
        st.error(f"Fehler beim Zugriff auf Tabelle '{name}': {err}")
        st.stop()

# --------------- Page Config ---------------
st.set_page_config(page_title="90-Days Challenge MVP", layout="wide")

# --------------- Authentication ---------------
if "user" not in st.session_state:
    st.header("Login / Register")
    email = st.text_input("E-Mail")
    pwd = st.text_input("Passwort", type="password")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Login"):
            res = supabase.auth.sign_in_with_password({"email": email, "password": pwd})
            if getattr(res, 'user', None):
                st.session_state.user = res.user
                st.rerun()
            else:
                st.error("Login fehlgeschlagen.")
    with c2:
        if st.button("Register"):
            res = supabase.auth.sign_up({"email": email, "password": pwd})
            if getattr(res, 'user', None): st.success("Account erstellt.")
            else: st.error("Registrierung fehlgeschlagen.")
    if st.button("Passwort vergessen?"):
        res = supabase.auth.reset_password_for_email(
            email,
            {"redirect_to": "https://sog-challange90d-fitness.streamlit.app"}
        )
        if getattr(res, 'error', None) is None:
            st.info("Reset-E-Mail versendet.")
        else:
            st.error("Reset fehlgeschlagen.")
    st.stop()

user = st.session_state.user
# Sidebar: Navigation + Logout
st.sidebar.write(f"Angemeldet als: {user.email}")
pages = ["Dashboard", "Challenge", "Exercises", "History"]
page = st.sidebar.radio("Menü", pages)
if st.sidebar.button("Logout"):
    supabase.auth.sign_out()
    st.session_state.clear()
    st.rerun()

# --------------- Dashboard ---------------
if page == "Dashboard":
    st.title("Dashboard")
    # Load or start challenge
    uc = get_table("user_challenges").select("id, current_day, paused_until, started_at").eq("user_id", user.id).single().execute().data
    if not uc:
        if st.button("Challenge starten", key="start_chal"):
            new = get_table("user_challenges").insert({"user_id": user.id}).execute().data[0]
            st.success("Challenge gestartet!")
            st.rerun()
        st.stop()
    # Controls
    st.markdown("---")
    col_p, col_a = st.columns(2)
    today = datetime.date.today()
    # Pause
    if not uc['paused_until']:
        if col_p.button("Pause (max 7 Tage)", key="btn_pause"):
            pu = today + datetime.timedelta(days=7)
            get_table("user_challenges").update({"paused_until": pu.isoformat()}).eq("id", uc['id']).execute()
            st.success(f"Pause bis {pu}")
            st.rerun()
    else:
        pu = datetime.date.fromisoformat(uc['paused_until'][:10])
        if pu >= today:
            col_p.warning(f"Pausiert bis {pu}")
            if col_p.button("Fortsetzen", key="btn_resume"):
                get_table("user_challenges").update({"paused_until": None}).eq("id", uc['id']).execute()
                st.success("Challenge fortgesetzt.")
                st.rerun()
        else:
            col_p.error("Pause abgelaufen.")
    # Abort
    if col_a.button("Challenge abbrechen"):
        get_table("user_challenges").delete().eq("id", uc['id']).execute()
        st.info("Challenge abgebrochen.")
        st.rerun()
    # KPIs
    st.markdown("---")
    st.subheader("Kennzahlen")
    total = len(get_table("programs").select("day").execute().data)
    sessions = get_table("user_sessions").select("program_id").eq("user_id", user.id).execute().data or []
    prog_list = get_table("programs").select("id, day").execute().data
    day_map = {p['id']: p['day'] for p in prog_list}
    done = { day_map[s['program_id']] for s in sessions if s['program_id'] in day_map }
    st.metric("Abgeschlossen", len(done), delta=None)
    st.metric("Verbleibend", total - len(done))
    # Today
    start = datetime.date.fromisoformat(uc['started_at'][:10])
    curr = (today - start).days + 1
    st.markdown("---")
    st.subheader("Heute")
    if uc['paused_until'] and pu >= today:
        st.info("Heute pausiert.")
    elif curr in [p['day'] for p in prog_list]:
        st.write(f"Tag {curr}: Workout")
        if curr in done: st.success("Erledigt")
        else: st.warning("Ausstehend")
    else:
        st.info("Heute Ruhetag")

# --------------- Challenge ---------------
elif page == "Challenge":
    st.title(f"Challenge Tag {uc['current_day']}")
    # Implementation of workout execution similar to previous code
    st.write("Hier Workout durchführen und Ergebnisse speichern.")

# --------------- Exercises List ---------------
elif page == "Exercises":
    st.title("Alle Übungen")
    exs = get_table("exercises").select("id, name").execute().data or []
    df_ex = pd.DataFrame(exs)
    st.dataframe(df_ex)

# --------------- History ---------------
elif page == "History":
    st.title("History")
    hist = get_table("user_sessions").select("exercise_id, reps, recorded_at").eq("user_id", user.id).execute().data or []
    if hist:
        dfh = pd.DataFrame(hist)
        dfh['date'] = dfh['recorded_at'].str[:10]
        ex_df = pd.DataFrame(get_table("exercises").select("id, name").execute().data)
        dfh = dfh.merge(ex_df, left_on="exercise_id", right_on="id")
        chart = dfh.groupby('date')['reps'].sum().reset_index()
        st.line_chart(chart.rename(columns={'date':'index'}).set_index('index')['reps'])
    else:
        st.info("Noch keine Daten.")
