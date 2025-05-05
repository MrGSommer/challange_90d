from supabase import create_client
import streamlit as st

URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_ANON_KEY"]
supabase = create_client(URL, KEY)
