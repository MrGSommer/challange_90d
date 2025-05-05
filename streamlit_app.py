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
    uc_res = get_table("user_challenges").select("id, current_day, paused_until, started_at").eq("user_id", user.id).execute()
    uc = uc_res.data if hasattr(uc_res, 'data') else uc_res
    if not uc:
        if st.button("Challenge starten", key="start_chal"):
            new = get_table("user_challenges").insert({"user_id": user.id}).execute().data[0]
            st.success("Challenge gestartet!")
            st.rerun()
        st.stop()
    # If challenge active, allow jump-in
    st.markdown("---")
    st.subheader("Challenge Einstellungen")
    col_start, col_actions = st.columns([2,1])
    # Jump to specific day
    with col_start:
        new_day = st.number_input(
            "Einsteigen ab Tag", min_value=1, max_value=90, value=uc['current_day'], step=1, key='jump_day'
        )
        if st.button("Tag setzen", key="set_day"):
            get_table("user_challenges").update({"current_day": new_day}).eq("id", uc['id']).execute()
            st.success(f"Challenge-Pointer gesetzt auf Tag {new_day}")
            st.rerun()
    # Pause/Abort actions
    today = datetime.date.today()
    with col_actions:
        if not uc['paused_until']:
            if st.button("Pause (max 7 Tage)", key="btn_pause"):
                pu = today + datetime.timedelta(days=7)
                get_table("user_challenges").update({"paused_until": pu.isoformat()}).eq("id", uc['id']).execute()
                st.success(f"Pause bis {pu}")
                st.rerun()
        else:
            pu = datetime.date.fromisoformat(uc['paused_until'][:10])
            if pu >= today:
                st.warning(f"Pausiert bis {pu}")
                if st.button("Fortsetzen", key="btn_resume"):
                    get_table("user_challenges").update({"paused_until": None}).eq("id", uc['id']).execute()
                    st.success("Challenge fortgesetzt.")
                    st.rerun()
            else:
                st.error("Pause abgelaufen.")
        if st.button("Challenge abbrechen", key="btn_abort"):
            get_table("user_challenges").delete().eq("id", uc['id']).execute()
            st.info("Challenge abgebrochen.")
            st.rerun()
    # KPIs based on challenge pointer
    st.markdown("---")
    st.subheader("Kennzahlen")
    total = len(get_table("programs").select("day").execute().data)
    completed = uc['current_day'] - 1
    remaining = total - completed
    st.metric("Abgeschlossen", completed)
    st.metric("Verbleibend", remaining)
    # Today's status
    st.markdown("---")
    st.subheader("Heute")
    if uc['paused_until'] and datetime.date.fromisoformat(uc['paused_until'][:10]) >= today:
        st.info("Heute pausiert.")
    else:
        curr = uc['current_day']
        prog_days = [p['day'] for p in get_table("programs").select("day").execute().data]
        if curr in prog_days:
            st.write(f"Tag {curr}: Workout")
            # check if user_sessions entry exists for this day
            # map program_id to day
            prog_map = {p['id']: p['day'] for p in get_table("programs").select("id, day").execute().data}
            sess = get_table("user_sessions").select("program_id").eq("user_id", user.id).execute().data or []
            done = {prog_map[s['program_id']] for s in sess if s['program_id'] in prog_map}
            if curr in done:
                st.success("Erledigt")
            else:
                st.warning("Ausstehend")
                if st.button("Jetzt durchführen", key="goto_challenge"):
                    st.experimental_set_query_params(page="Challenge")
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
