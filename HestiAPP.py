import streamlit as st
import pandas as pd
import datetime
import easyocr
import numpy as np
from PIL import Image
import os
from fpdf import FPDF
from streamlit_gsheets import GSheetsConnection

# Nastavení stránky
st.set_page_config(page_title="Hesti Zbuzany", layout="wide")

# --- INICIALIZACE PŘIPOJENÍ ---
# Toto nahrazuje openpyxl a lokální Excel
conn = st.connection("gsheets", type=GSheetsConnection)

# --- INICIALIZACE AI (EasyOCR) ---
@st.cache_resource
def load_ocr():
    return easyocr.Reader(['en'], gpu=False)

reader = load_ocr()

# --- DATA PRO VÝBĚRY ---
DATA_VOZIDLA = {
    "MAN": ["TGX", "TGS", "TGM", "TGL"],
    "KRONE": ["Profi Liner", "Mega Liner", "Cool Liner", "Dry Liner", "Box Liner", "Box Carrier"],
    "D-TEC": [], "Langendorf": [], "Meiller": [], "Nooteboom": [], "O.ME.P.S": []
}

KAT_MAP = {
    "MAN nové": "MAN_nové",
    "Návěsy nové": "Návěsy_nové",
    "MAN TGE": "MAN_TGE",
    "Ojetá vozidla": "Ojetá_vozidla",
    "Noční stání": "Vlastní"
}

# --- FUNKCE: ZÁPIS PŘÍJEZDU (Google Sheets) ---
def zapsat_do_gsheets(list_name, vyrobce, druh, vin, kode, poznamka):
    try:
        df = conn.read(worksheet=list_name)
        new_row = pd.DataFrame([{
            "ID": len(df) + 1,
            "Výrobce": vyrobce,
            "Druh": druh if druh else "",
            "VIN/WERK": vin,
            "KÓDE": kode,
            "Poznámka": poznamka,
            "Čas příjezdu": datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
        }])
        updated_df = pd.concat([df, new_row], ignore_index=True)
        conn.update(worksheet=list_name, data=updated_df)
        return True
    except Exception as e:
        st.error(f"Chyba zápisu: {e}")
        return False

# --- FUNKCE: ZÁPIS ODJEZDU (Google Sheets) ---
def zapsat_odjezd_gsheets(list_z_kategorie, vin_kod, cil_odjezdu):
    try:
        df_source = conn.read(worksheet=list_z_kategorie)
        df_vydano = conn.read(worksheet="Vydáno")
        
        mask = df_source['VIN/WERK'].astype(str).str.strip().str.upper() == vin_kod.strip().upper()
        
        if mask.any():
            row_to_move = df_source[mask].copy()
            row_to_move['Cíl odjezdu'] = cil_odjezdu
            row_to_move['Čas odjezdu'] = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
            
            # Aktualizace ID pro historii
            row_to_move['ID'] = len(df_vydano) + 1
            
            df_vydano_new = pd.concat([df_vydano, row_to_move], ignore_index=True)
            df_source_new = df_source[~mask]
            
            conn.update(worksheet="Vydáno", data=df_vydano_new)
            conn.update(worksheet=list_z_kategorie, data=df_source_new)
            return True
        return False
    except Exception as e:
        st.error(f"Chyba při odjezdu: {e}")
        return False

# --- GLOBÁLNÍ DESIGN ---
st.markdown("""
    <style>
        /* Skrytí kotev u nadpisů */
        h1 a, h2 a, h3 a, h4 a { display: none !important; }
        .stButton > button { height: 3.5em; font-weight: bold !important; border-radius: 8px !important; }
    </style>
""", unsafe_allow_html=True)

if 'stranka' not in st.session_state: st.session_state.stranka = "prehled"
if 'nacteny_vin' not in st.session_state: st.session_state.nacteny_vin = ""

# --- STRÁNKY ---
def stranka_seznam(nazev_kategorie, excel_list):
    st.header(f"📋 Seznam: {nazev_kategorie}")
    if st.button("⬅ ZPĚT"): st.session_state.stranka = "prehled"; st.rerun()
    try:
        data = conn.read(worksheet=excel_list)
        st.dataframe(data, use_container_width=True, hide_index=True)
    except:
        st.info("Seznam je momentálně prázdný.")

def stranka_report():
    c_nadpis, c_logo = st.columns([3, 1])
    with c_nadpis: st.title("🚛 HESTI ZBUZANY - PŘEHLED")
    with c_logo: st.image("HESTI GROUP.png", use_container_width=True)
    
    # Sumáře z Google Sheets
    celkem = 0
    col1, col2, col3 = st.columns(3)
    
    for idx, (app_name, sheet_name) in enumerate(KAT_MAP.items()):
        try:
            count = len(conn.read(worksheet=sheet_name))
            celkem += count
            with [col1, col2, col3][idx % 3]:
                st.metric(app_name.upper(), count)
        except: pass
    
    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🔎 Seznamy")
        for k, v in KAT_MAP.items():
            if st.button(f"📦 {k.upper()}", use_container_width=True):
                st.session_state.stranka = f"list_{v}"; st.rerun()
        if st.button("📜 HISTORIE VÝDEJŮ", use_container_width=True):
            st.session_state.stranka = "list_Vydáno"; st.rerun()
            
    with c2:
        st.subheader("⚙️ Pohyby")
        if st.button("🟢 ZAEVIDOVAT PŘÍJEZD", key="prijezd", use_container_width=True, type="primary"):
            st.session_state.stranka = "prijezd"; st.rerun()
        if st.button("🔴 EVIDOVAT ODJEZD", key="odjezd", use_container_width=True):
            st.session_state.stranka = "odjezd"; st.rerun()

def stranka_prijezd():
    st.header("🟢 Příjezd vozidla")
    foto = st.camera_input("📸 Vyfoťte štítek")
    if foto:
        img = Image.open(foto)
        res = reader.readtext(np.array(img))
        texts = [t[1] for t in res if len(t[1]) > 4]
        if texts:
            st.session_state.nacteny_vin = max(texts, key=len).upper().replace(" ", "")
            st.success(f"Přečteno: {st.session_state.nacteny_vin}")

    with st.container(border=True):
        kat = st.selectbox("Kategorie", list(KAT_MAP.keys()))
        vyr = st.selectbox("Výrobce", list(DATA_VOZIDLA.keys()))
        vin = st.text_input("VIN / WERK", value=st.session_state.nacteny_vin).upper()
        if st.button("💾 ULOŽIT", use_container_width=True, type="primary"):
            if vin and zapsat_do_gsheets(KAT_MAP[kat], vyr, "", vin, "", ""):
                st.success("Zapsáno!"); st.session_state.nacteny_vin = ""
        if st.button("⬅ ZPĚT", use_container_width=True):
            st.session_state.stranka = "prehled"; st.rerun()

def stranka_odjezd():
    st.header("🔴 Odjezd vozidla")
    with st.container(border=True):
        kat = st.selectbox("Z kategorie", list(KAT_MAP.keys()))
        vin = st.text_input("VIN pro výdej").upper()
        cil = st.text_input("Kam vozidlo odjíždí?")
        if st.button("❌ POTVRDIT VÝDEJ", use_container_width=True, type="primary"):
            if vin and cil and zapsat_odjezd_gsheets(KAT_MAP[kat], vin, cil):
                st.success("Vydáno!"); st.rerun()
        if st.button("⬅ ZPĚT", use_container_width=True):
            st.session_state.stranka = "prehled"; st.rerun()

# --- ROZCESTNÍK ---
if st.session_state.stranka == "prehled": stranka_report()
elif st.session_state.stranka == "prijezd": stranka_prijezd()
elif st.session_state.stranka == "odjezd": stranka_odjezd()
elif st.session_state.stranka.startswith("list_"):
    sheet = st.session_state.stranka.replace("list_", "")
    stranka_seznam(sheet, sheet)

