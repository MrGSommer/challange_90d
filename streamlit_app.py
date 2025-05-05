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
# Sidebar: User info + navigation + logout
st.sidebar.write(f"Angemeldet als: {user.email}")
page = st.sidebar.radio("Menü", ["Dashboard", "Challenge", "History"])
if st.sidebar.button("Logout", key="logout_btn"):
    supabase.auth.sign_out()
    st.session_state.clear()
    st.rerun()

# --------------- Dashboard ---------------
if page == "Dashboard":
    st.title("Challenge Dashboard")
    # Load user_challenge
    uc_list = get_table("user_challenges").select("id, current_day, paused_until, started_at").eq("user_id", user.id).execute().data
    uc = uc_list[0] if uc_list else None
    if not uc:
        st.info("Du hast noch keine Challenge gestartet.")
    else:
        # Pause logic
        paused_until = uc.get('paused_until')
        today = datetime.date.today()
        if paused_until:
            pu = datetime.date.fromisoformat(paused_until[:10])
            days_left = (pu - today).days
            if days_left >= 0:
                st.warning(f"Challenge pausiert, bis {pu} ({days_left} Tage übrig)")
                if st.button("Fortsetzen" , key="resume_btn"):
                    get_table("user_challenges").update({"paused_until": None}).eq("id", uc['id']).execute()
                    st.success("Challenge fortgesetzt.")
                    st.rerun()
            else:
                st.error("Pause abgelaufen. Bitte starte die Challenge neu.")
        else:
            if st.button("Pause Challenge (bis zu 7 Tage)" , key="pause_btn"):
                pu = today + datetime.timedelta(days=7)
                get_table("user_challenges").update({"paused_until": pu.isoformat()}).eq("id", uc['id']).execute()
                st.success(f"Challenge pausiert bis {pu}")
                st.rerun()
        # Key indicators
        st.subheader("Kennzahlen")
        # total workout days (programmed)
        prog = get_table("programs").select("day").execute().data or []
        total_days = len(prog)
        # completed days
        sessions = get_table("user_sessions").select("program_id").eq("user_id", user.id).execute().data or []
        done_days = set()
        for s in sessions:
            day_list = [p['day'] for p in prog if p.get('id') == s['program_id']]
            if day_list:
                done_days.add(day_list[0])
        completed = len(done_days)
        remaining = total_days - completed
        st.metric("Tage abgeschlossen", completed)
        st.metric("Tage offen", remaining)
        # today's workout
        today_offset = (today - datetime.date.fromisoformat(uc['started_at'][:10])).days + 1
        st.markdown("---")
        st.subheader("Status für heute")
        if paused_until and days_left >=0:
            st.info("Heute keine Aktivität, da pausiere Challenge.")
        else:
            if today_offset in [p['day'] for p in prog]:
                if today_offset in done_days:
                    st.success("Workout für heute bereits erledigt ✅")
                else:
                    st.warning("Workout für heute steht aus ⚠️")
                    if st.button("Jetzt durchführen", key="goto_challenge"):
                        st.experimental_set_query_params(page="Challenge")
            else:
                st.info("Heute ist Ruhetag 🌴")
        # Buchführung: Übersicht
        st.markdown("---")
        st.subheader("Buchführung: Verlauf")
        # build table of days
        df_days = pd.DataFrame({'day': range(1,91)})
        prog_df = pd.DataFrame(get_table("programs").select("day, workout_name").execute().data)
        df = df_days.merge(prog_df, on='day', how='left')
        df['type'] = df['workout_name'].fillna('Ruhetag')
        df['status'] = df['day'].apply(lambda d: 'Erledigt' if d in done_days else ('Offen' if df.loc[df.day==d,'type'].iloc[0] != 'Ruhetag' else 'Ruhe'))
        df = df[['day','type','status']]
        st.dataframe(df)

# --------------- Challenge (Durchführung) ---------------
elif page == "Challenge":
    st.title("90-Days Challenge: Durchführung")
    # existing logic for challenge page...
    st.write("Hier geht es weiter zur Durchführung der einzelnen Tage.")

# --------------- History ---------------
elif page == "History":
    st.title("Deine Versuche")
    hist = get_table("user_sessions").select("exercise_id, reps, recorded_at").eq("user_id", user.id).execute().data or []
    if hist:
        dfh = pd.DataFrame(hist)
        dfh['date'] = dfh['recorded_at'].str[:10]
        ex_df = pd.DataFrame(get_table("exercises").select("id, name").execute().data)
        dfh = dfh.merge(ex_df, left_on="exercise_id", right_on="id", how="left")
        stats = dfh.groupby("date")["reps"].sum().reset_index()
        st.line_chart(stats.rename(columns={"date":"index"}).set_index("index")["reps"])
    else:
        st.info("Noch keine Daten vorhanden.")
