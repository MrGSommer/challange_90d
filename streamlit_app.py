import streamlit as st
from supabase import create_client
from postgrest import APIError
import datetime
import pandas as pd

# --------------- Supabase-Client ---------------
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_ANON_KEY"]  # Nur ANON-KEY nutzen
supabase = create_client(url, key)

def get_table(name: str):
    return supabase.table(name)

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
           # supabase-auth liefert hier ein Session-Objekt mit access_token
           if getattr(res, "session", None) and getattr(res, "user", None):
               # JWT in die Header übernehmen, damit RLS auth.uid() stimmt
               token = res.session.access_token
               supabase.client._client.headers.update({"Authorization": f"Bearer {token}"})
               st.session_state.user = res.user
               st.rerun()
            else:
                st.error("Login fehlgeschlagen.")
                
    with c2:
        if st.button("Register"):
            res = supabase.auth.sign_up({"email": email, "password": pwd})
            if getattr(res, "user", None):
                st.success("Account erstellt.")
            else:
                st.error("Registrierung fehlgeschlagen.")
    if st.button("Passwort vergessen?"):
        res = supabase.auth.reset_password_for_email(
            email,
            {"redirect_to": "https://sog-challange90d-fitness.streamlit.app"}
        )
        if getattr(res, "error", None) is None:
            st.info("Reset-E-Mail versendet.")
        else:
            st.error("Reset fehlgeschlagen.")
    st.stop()

user = st.session_state.user

# --------------- Load Challenge State ---------------
uc_resp = get_table("user_challenges") \
    .select("id, current_day, paused_until, started_at") \
    .eq("user_id", user.id) \
    .execute()
uc = uc_resp.data[0] if uc_resp.data else None

# --------------- Load Exercise Metadata ---------------
ed_resp = get_table("exercise_details") \
    .select("exercise_id, level, description, focus") \
    .execute()
exercise_info = {
    item["exercise_id"]: {
        "level": item["level"],
        "description": item["description"],
        "focus": item["focus"]
    }
    for item in (ed_resp.data or [])
}

# --------------- Sidebar ---------------
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

    if not uc:
        if st.button("Challenge starten"):
            try:
                new = get_table("user_challenges") \
                    .insert({"user_id": user.id}).execute().data[0]
                st.success("Challenge gestartet.")
                st.rerun()
            except APIError as e:
                st.error(f"RLS-Fehler: {e.message}")
        st.stop()

    # Challenge Controls
    st.subheader("Challenge Steuerung")
    col1, col2 = st.columns([3, 1])
    with col1:
        new_day = st.number_input(
            "Einsteigen ab Tag",
            min_value=1, max_value=90,
            value=uc["current_day"]
        )
        if st.button("Setze Tag"):
            get_table("user_challenges") \
                .update({"current_day": new_day}) \
                .eq("id", uc["id"]).execute()
            st.success(f"Aktueller Tag gesetzt auf {new_day}.")
            st.rerun()
    with col2:
        pu_iso = uc.get("paused_until")
        if not pu_iso:
            if st.button("Pause (7 Tage)"):
                pu = datetime.date.today() + datetime.timedelta(days=7)
                get_table("user_challenges") \
                    .update({"paused_until": pu.isoformat()}) \
                    .eq("id", uc["id"]).execute()
                st.success(f"Pause bis {pu}.")
                st.rerun()
        else:
            pu = datetime.date.fromisoformat(pu_iso[:10])
            if pu >= datetime.date.today():
                st.warning(f"Pausiert bis {pu}.")
                if st.button("Fortsetzen"):
                    get_table("user_challenges") \
                        .update({"paused_until": None}) \
                        .eq("id", uc["id"]).execute()
                    st.success("Challenge fortgesetzt.")
                    st.rerun()
            else:
                st.error("Pause abgelaufen.")
        if st.button("Abbrechen"):
            get_table("user_challenges") \
                .delete().eq("id", uc["id"]).execute()
            st.info("Challenge abgebrochen.")
            st.rerun()

    # KPIs
    st.markdown("---")
    st.subheader("Kennzahlen")
    total = len(get_table("programs").select("day").execute().data or [])
    completed = uc["current_day"] - 1
    st.metric("Abgeschlossen", completed)
    st.metric("Verbleibend", total - completed)

    # Status heute
    st.markdown("---")
    st.subheader("Status heute")
    today = datetime.date.today()
    if uc.get("paused_until"):
        pu = datetime.date.fromisoformat(uc["paused_until"][:10])
        if pu >= today:
            st.info("Heute pausiert.")
        else:
            st.info("Pause abgelaufen. Fortsetzen möglich im Panel oben.")
    else:
        curr = uc["current_day"]
        days = [p["day"] for p in get_table("programs").select("day").execute().data]
        if curr in days:
            st.write(f"Tag {curr}: Workout")
            prog_map = {
                p["id"]: p["day"]
                for p in get_table("programs").select("id, day").execute().data
            }
            sess = get_table("user_sessions") \
                .select("program_id").eq("user_id", user.id) \
                .execute().data or []
            done = {prog_map[s["program_id"]] for s in sess if s["program_id"] in prog_map}
            if curr in done:
                st.success("Erledigt")
            else:
                st.warning("Ausstehend")
                if st.button("Jetzt durchführen"):
                    st.experimental_set_query_params(page="Challenge")
        else:
            st.info("Heute Ruhetag")

# --------------- Challenge Page ---------------
elif page == "Challenge":
    if not uc:
        st.info("Keine aktive Challenge. Starte eine im Dashboard.")
    else:
        st.title(f"Challenge Tag {uc['current_day']}")
        st.write("Hier Workout durchführen und Ergebnisse speichern.")

# --------------- Exercises Page ---------------
elif page == "Exercises":
    st.title("Alle Übungen")
    exs = get_table("exercises").select("id, name").execute().data or []
    for ex in exs:
        ex_id = ex["id"]
        name = ex["name"]
        info = exercise_info.get(ex_id, {})
        st.header(f"{name} (Level {info.get('level', '?')})")
        st.write(info.get("description", "Keine Beschreibung verfügbar."))
        st.write("**Fokus:**", info.get("focus", ""))
        st.markdown("---")

# --------------- History ---------------
elif page == "History":
    st.title("Deine bisherigen Sessions")
    hist = get_table("user_sessions") \
        .select("exercise_id, reps, recorded_at") \
        .eq("user_id", user.id) \
        .execute().data or []
    if hist:
        df = pd.DataFrame(hist)
        df["date"] = df["recorded_at"].str[:10]
        ex_df = pd.DataFrame(
            get_table("exercises").select("id, name").execute().data
        )
        df = df.merge(ex_df, left_on="exercise_id", right_on="id")
        chart = df.groupby("date")["reps"].sum().reset_index()
        st.line_chart(chart.rename(columns={"date": "index"}).set_index("index")["reps"])
    else:
        st.info("Noch keine Daten vorhanden.")
