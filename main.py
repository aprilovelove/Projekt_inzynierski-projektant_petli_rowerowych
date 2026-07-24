import base64
import json
import math
from datetime import datetime
from io import BytesIO
from typing import List, Tuple

import folium
import networkx as nx
import osmnx as ox
import qrcode
import streamlit as st
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship
from streamlit_folium import st_folium
from streamlit_js_eval import get_geolocation

# Importy z plików lokalnych
from app.db.database import RouteReview, SavedRoute, SessionLocal, User, Base, engine
from app.services.auth import login_user, register_user
from app.services.email_service import send_custom_email
from app.services.manual_designer import show_manual_designer
from app.services.route_analysis_service import analyze_route_compatibility
from app.services.route_service import clean_line_coordinates, find_circular_route, get_graph
from app.utils.geo_utils import calculate_square_corners, create_gpx, format_surface_summary

# Automatyczne utworzenie tabeli w NeonDB przy starcie aplikacji
Base.metadata.create_all(bind=engine)

# --- APLIKACJA STREAMLIT ---
st.set_page_config(
    page_title="RoutePlanner",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': None
    }
)

import os

# --- AUTOMATYCZNA GENERACJA PLIKU KONFIGURACYJNEGO ---
# Ten kod sam utworzy niewidoczny folder .streamlit oraz plik config.toml z ciemnym motywem!
if not os.path.exists(".streamlit"):
    os.makedirs(".streamlit")

config_path = ".streamlit/config.toml"
# Zawsze upewniamy się, że plik ma właściwe ustawienia motywu dark
with open(config_path, "w", encoding="utf-8") as f:
    f.write("""[theme]
base = "dark"
primaryColor = "#EFCC76"
backgroundColor = "#152010"
secondaryBackgroundColor = "#2B4121"
textColor = "#FFFFFF"
""")

# 1. ŚCIEŻKI DO TWOICH OBRAZKÓW
MAIN_BG_PATH = "app/images/automatyczny.png"
SIDEBAR_BG_PATH = "app/images/sidebar.png"
LOGO_PATH = "app/images/logo.png"

# 2. AUTOMATYCZNA KONWERSJA OBRAZKA GŁÓWNEGO DO BASE64
try:
    with open(MAIN_BG_PATH, "rb") as image_file:
        encoded_main = base64.b64encode(image_file.read()).decode()
    main_bg_css = f"url(data:image/png;base64,{encoded_main})"
except FileNotFoundError:
    main_bg_css = "radial-gradient(circle at 10% 10%, #061f0b 0%, #0d130e 50%, #000000 100%)"

# 3. AUTOMATYCZNA KONWERSJA OBRAZKA SIDEBARA DO BASE64
try:
    with open(SIDEBAR_BG_PATH, "rb") as image_file:
        encoded_sidebar = base64.b64encode(image_file.read()).decode()
    sidebar_bg_css = f"url(data:image/png;base64,{encoded_sidebar})"
except FileNotFoundError:
    sidebar_bg_css = "none"

# 4. AUTOMATYCZNA KONWERSJA LOGO DO BASE64 (Przywrócona do CSS)
try:
    with open(LOGO_PATH, "rb") as image_file:
        encoded_logo = base64.b64encode(image_file.read()).decode()
    logo_css = f"data:image/png;base64,{encoded_logo}"
except FileNotFoundError:
    logo_css = ""

logo_background = f"url({logo_css})" if logo_css else "none"

st.markdown("""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Lexend:wght@300;400;500;600;700&display=swap" rel="stylesheet">
""", unsafe_allow_html=True)

# Następnie nakładamy zoptymalizowane style CSS
st.markdown(f"""
    <style>
        /* GLOBALNA CZCIONKA LEXEND Z NAJWYŻSZYM PRIORYTETEM */
        html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"],
        .stApp, div, span, p, label, button, input, select, textarea {{
            font-family: 'Lexend', sans-serif !important;
        }}

        /* WYJĄTEK: ikony Streamlita (strzałki, chevrony itp.) NIE mają dostać Lexend */
        [data-testid="stIconMaterial"],
        span[class*="material-icons"],
        span[class*="material-symbols"],
        [data-testid="stExpanderIcon"],
        [data-testid="stExpanderToggleIcon"],
        svg {{
            font-family: 'Material Symbols Rounded', 'Material Icons' !important;
        }}

        /* Globalne nadpisanie zmiennych kolorów */
        :root, [data-testid="stAppViewContainer"], [data-testid="stSidebar"] {{
            --primary-color: #EFCC76 !important;
            --primary: #EFCC76 !important;
            --state-selected-background: #2B4121 !important;
        }}

        /* UKRYWANIE ELEMENTÓW SYSTEMOWYCH */
        .stAppDeployButton {{ display:none !important; }}
        #MainMenu {{ visibility: hidden; }}
        footer {{ visibility: hidden; }}
        div[data-testid="stStatusWidget"] {{ visibility: hidden; }}
        div[data-testid="stToolbar"] {{ display: none !important; }}
        div[data-testid="stDecoration"] {{ display: none !important; }}

        /* CAŁKOWITE OCZYSZCZENIE GÓRNEGO NAGŁÓWKA */
        [data-testid="stHeader"] {{
            background: transparent !important;
            height: 0px !important;
            min-height: 0px !important;
        }}

        [data-testid="stAppViewBlockContainer"] {{
            padding-top: 0rem !important;
        }}

        /* Rezerwowe/starsze selektory na wypadek innej wersji Streamlit */
        .block-container {{
            padding-top: 1rem !important;
        }}

        [data-testid="stAppViewContainer"] > .main {{
            padding-top: 0rem !important;
        }}

        section.main > div {{
            padding-top: 0rem !important;
        }}

        /* STYLIZACJA SIDEBARU */
        [data-testid="stSidebar"] {{ 
            background: linear-gradient(180deg, rgba(43, 65, 33, 0.92) 0%, rgba(21, 33, 16, 0.98) 100%), {sidebar_bg_css} !important;
            background-size: cover !important;
            background-position: center !important;
            border-right: 3px solid #EFCC76 !important;
            border-radius: 0px 20px 20px 0px;
        }}

        .sidebar-logo-container {{
            width: 100% !important;
            height: 110px !important;
            background-image: {logo_background} !important;
            background-repeat: no-repeat !important;
            background-size: contain !important;
            background-position: center center !important;
            margin-bottom: 5px !important;
        }}

        [data-testid="stSidebar"] .stMarkdown p, 
        [data-testid="stSidebar"] label {{
            color: #ffffff !important;
            font-weight: 500 !important;
            text-shadow: 1px 1px 3px rgba(0, 0, 0, 0.8);
        }}

        /* TŁO APLIKACJI */
        .stApp {{ 
            background: linear-gradient(rgba(0, 0, 0, 0.65), rgba(0, 0, 0, 0.85)), {main_bg_css} !important;
            background-size: cover !important;
            background-position: center !important;
            background-attachment: fixed !important;
        }}

        h1, h2, h3 {{
            color: #EFCC76 !important;                  
            font-family: 'Lexend', sans-serif !important;
            font-weight: 700 !important;
            padding-bottom: 8px;
            text-shadow: 1px 1px 4px rgba(0, 0, 0, 0.8); 
        }}

        .stMarkdown p {{
            color: #e2e8f0 !important;                   
            font-size: 15px !important;
            text-shadow: 1px 1px 3px rgba(0, 0, 0, 0.9);
        }}

        /* STYLIZACJA PRZYCISKÓW */
        div.stButton > button {{
            background-color: #2B4121 !important;        
            color: #ffffff !important;                   
            border: 1px solid #EFCC76 !important;        
            border-radius: 8px !important;               
            padding: 8px 16px !important;
            font-weight: 600 !important;
            transition: all 0.3s ease !important;        
        }}

        div.stButton > button:hover {{
            background-color: #EFCC76 !important;        
            color: #152010 !important;                   
            border-color: #ffffff !important;
            box-shadow: 0px 4px 12px rgba(239, 204, 118, 0.3) !important;
        }}

        /* ======================================================= */
        /* POWIĘKSZONE ZAKŁADKI (st.segmented_control / st.tabs)   */
        /* ======================================================= */

        div[data-testid="stSegmentedControl"],
        div[data-testid="stSegmentedControl"] > div {{
            width: 100% !important;
            display: flex !important;
            background-color: rgba(21, 32, 16, 0.85) !important;
            border: 1.5px solid rgba(239, 204, 118, 0.5) !important;
            border-radius: 12px !important;
            padding: 6px !important;
            gap: 6px !important;
        }}

        div[data-testid="stSegmentedControl"] button,
        div[data-testid="stSegmentedControl"] [role="option"] {{
            flex: 1 1 0% !important;
            min-height: 48px !important;
            font-size: 16px !important;
            font-weight: 600 !important;
            padding: 10px 16px !important;
            background-color: transparent !important;
            color: #e2e8f0 !important;
            border: none !important;
            border-radius: 8px !important;
            transition: all 0.2s ease-in-out !important;
        }}

        div[data-testid="stSegmentedControl"] button[aria-checked="true"],
        div[data-testid="stSegmentedControl"] [aria-selected="true"] {{
            background-color: #2B4121 !important;
            color: #EFCC76 !important;
            border: 1.5px solid #EFCC76 !important;
            box-shadow: 0px 4px 12px rgba(0, 0, 0, 0.5) !important;
        }}

        div[data-testid="stTabs"] [data-baseweb="tab-list"] {{
            width: 100% !important;
            gap: 8px !important;
        }}
        div[data-testid="stTabs"] button[data-baseweb="tab"] {{
            flex: 1 !important;
            height: 50px !important;
            font-size: 16px !important;
            font-weight: 600 !important;
            background-color: rgba(21, 32, 16, 0.85) !important;
            color: #ffffff !important;
            border-radius: 8px 8px 0 0 !important;
        }}

        /* ======================================================= */
        /* RADIO BUTTONY I OBSŁUGA INPUTÓW                         */
        /* ======================================================= */

        div[data-testid="stRadio"] *:focus,
        div[data-testid="stRadio"] *:focus-visible {{
            outline: none !important;
            box-shadow: none !important;
        }}

        div[data-testid="stRadio"] [data-checked="true"] > div {{
            background-color: #EFCC76 !important;
        }}

        div[data-testid="stRadio"] label p {{
            color: #ffffff !important;
            font-size: 15px !important;
        }}

        div[data-testid="stTextInput"] input, 
        div[data-testid="stNumberInput"] input,
        div[data-testid="stSelectbox"] div[data-baseweb="select"] {{
            background-color: #152010 !important;        
            color: #ffffff !important;                   
            border: 1px solid rgba(239, 204, 118, 0.3) !important;        
            border-radius: 8px !important;
        }}

        div[data-testid="stExpander"] {{ 
            border: 1px solid #EFCC76 !important; 
            background-color: rgba(21, 32, 16, 0.9) !important; 
        }}

    </style>
""", unsafe_allow_html=True)




# INICJALIZACJA STANU SESJI
if 'user' not in st.session_state: st.session_state.user = None
if 'generated_geojson' not in st.session_state: st.session_state.generated_geojson = None
if 'map_center' not in st.session_state: st.session_state.map_center = [50.2859, 18.9549]
if 'load_info' not in st.session_state: st.session_state.load_info = None
if 'route_score' not in st.session_state: st.session_state.route_score = (None, None, None)
if 'loc_requested' not in st.session_state: st.session_state.loc_requested = False
if 'show_load_toast' not in st.session_state: st.session_state.show_load_toast = False

# WYŚWIETLENIE POP-UPA (TOAST) JEŚLI FLAGA JEST AKTYWNA
if st.session_state.show_load_toast:
    st.toast("Trasa została wczytana na projektant automatyczny", icon="✅")
    st.session_state.show_load_toast = False

# --- SYSTEM TRWAŁEGO ZAPISU WSPÓŁRZĘDNYCH ---
if 'permanent_lat' not in st.session_state: st.session_state.permanent_lat = st.session_state.map_center[0]
if 'permanent_lon' not in st.session_state: st.session_state.permanent_lon = st.session_state.map_center[1]

# Reakcja na przesunięcie mapy/wczytanie z bazy
if 'new_coords' in st.session_state:
    st.session_state.map_center = st.session_state.new_coords
    st.session_state.permanent_lat = st.session_state.new_coords[0]
    st.session_state.permanent_lon = st.session_state.new_coords[1]
    st.session_state["lat_input_field"] = st.session_state.new_coords[0]
    st.session_state["lon_input_field"] = st.session_state.new_coords[1]
    del st.session_state.new_coords

# --- OBSŁUGA GPS W TLE ---
if st.session_state.loc_requested:
    loc_data = get_geolocation()
    if loc_data:
        lat = loc_data['coords']['latitude']
        lon = loc_data['coords']['longitude']
        st.session_state.map_center = [lat, lon]
        st.session_state.permanent_lat = lat
        st.session_state.permanent_lon = lon
        st.session_state["lat_input_field"] = lat
        st.session_state["lon_input_field"] = lon
        st.session_state.loc_requested = False
        st.rerun()


def load_route_action(geojson_data, name):
    data = json.loads(geojson_data)
    st.session_state.generated_geojson = data
    st.session_state.load_info = name
    first_coord = data['features'][0]['geometry']['coordinates'][0]
    st.session_state.map_center = [first_coord[1], first_coord[0]]
    st.session_state.permanent_lat = first_coord[1]
    st.session_state.permanent_lon = first_coord[0]
    st.session_state["lat_input_field"] = first_coord[1]
    st.session_state["lon_input_field"] = first_coord[0]
    st.session_state.show_load_toast = True
    surf_stats = data['features'][0]['properties'].get('surface_stats')
    st.session_state.route_score = (None, None, surf_stats)


# --- FUNKCJE SYNCHRONIZACJI DLA WIDGETÓW NUMERYCZNYCH ---
def on_lat_change():
    st.session_state.permanent_lat = st.session_state["lat_input_field"]
    st.session_state.map_center[0] = st.session_state["lat_input_field"]


def on_lon_change():
    st.session_state.permanent_lon = st.session_state["lon_input_field"]
    st.session_state.map_center[1] = st.session_state["lon_input_field"]


# --- OKNO MODALNE (DIALOGOWE) DO DODAWANIA OPINII ---
@st.dialog("💬 Dodaj opinię o trasie")
def review_dialog(route_id, route_name):
    st.write(f"Oceniasz trasę: **{route_name}**")

    add_rating = st.checkbox("Chcę dodać ocenę punktową trasy.", value=True)
    rating_val = None
    if add_rating:
        rating_val = st.slider("Ocena trasy w skali od 1 do 5.", 1, 5, 5)

    add_comment = st.checkbox("Chcę dodać opinię o trasie.", value=True)
    comment_val = None
    if add_comment:
        comment_val = st.text_area("Wpisz swoją opinię o trasie:",
                                   placeholder="np. Świetne widoki, ale na 5 kilometrze sporo piasku...")

    st.divider()
    if st.button("Zapisz opinię", use_container_width=True, type="primary"):
        if not add_rating and not add_comment:
            st.error("Musisz wybrać przynajmniej jedną opcję (ocenę lub komentarz)!")
            return

        if add_comment and not comment_val.strip():
            st.error("Komentarz nie może być pusty, jeśli nie chcesz dodać komenatrza odznacz opcję 'Chcę dodać opinię o trasie'.")
            return

        db = SessionLocal()
        try:
            new_review = RouteReview(
                route_id=route_id,
                user_id=st.session_state.user['id'],
                rating=rating_val if add_rating else None,
                comment=comment_val if add_comment else None
            )
            db.add(new_review)
            db.commit()
            st.toast("Dziękujemy za dodanie opinii!", icon="🎉")
            st.rerun()
        except Exception as e:
            st.error(f"Błąd zapisu opinii: {e}")
        finally:
            db.close()


# =========================================================================
# =========================================================================
# KROK 1: WYBÓR TRYBU ORAZ LOGO (W JEDNYM WIERSZU)
# =========================================================================
import streamlit as st

# ============================================
# 2 WIERSZE, 2 KOLUMNY — LOGO W 2 WIERSZACH
# ============================================

import base64

def load_logo_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

logo_base64 = load_logo_base64("app/images/logo.png")


top_col1, top_col2 = st.columns([1, 2.5], vertical_alignment="center")

with top_col1:
    st.markdown(
        f"""
        <div style="
            background-image: url('data:image/png;base64,{logo_base64}');
            background-size: contain;
            background-repeat: no-repeat;
            background-position: center left;
            width: 100%;
            height: 170px;   /* zwiększone z 70px */
        ">
        </div>
        """,
        unsafe_allow_html=True
    )

# --- ZAKŁADKI ---
with top_col2:
    active_tab = st.segmented_control(
        "Wybierz tryb projektowania:",
        options=["Projektant automatyczny", "Projektant manualny", "🌍 Społeczność", "📒 Zapisane Trasy"],
        default="Projektant automatyczny",
        label_visibility="collapsed"
    )



# Zmienne globalne dla sidebaru
generate_btn = False
dist_km = 15
bike_type = "Brak"

# =========================================================================
# KROK 2: SIDEBAR (BEZ LOGO)
# =========================================================================
with st.sidebar:
    # Kontener HTML na logo został stąd usunięty

    if st.session_state.user is None:
        st.header("Panel Użytkownika")
        choice = st.radio("Akccjaa", ["Logowanie", "Rejestracja"], label_visibility="collapsed")

        if choice == "Logowanie":
            e = st.text_input("E-mail/Nick")
            p = st.text_input("Hasło", type="password")
            if st.button("Zaloguj"):
                user = login_user(e, p)
                if user:
                    st.session_state.user = {"id": user.id, "name": user.username}
                    st.rerun()
                else:
                    st.error("Błędny e-mail/nick lub hasło")
        else:
            new_u = st.text_input("Twoje Imię lub nick")
            new_e = st.text_input("E-mail")
            new_p = st.text_input("Hasło", type="password")
            if st.button("Zarejestruj"):
                res = register_user(new_u, new_e, new_p)
                if res == "success":
                    st.success("Konto utworzone! Możesz się zalogować.")
                elif res == "invalid_email":
                    st.error("Niepoprawny format e-maila!")
                elif res == "exists":
                    st.error("Użytkownik lub e-mail już istnieje.")
    else:
        st.header("👤 Twój Profil")
        st.success(f"Zalogowany jako: **{st.session_state.user['name']}**")
        if st.button("🚪 Wyloguj się", use_container_width=True):
            st.session_state.user = None
            st.rerun()

    st.divider()
    st.header("🎴 Parametry Trasy")

    if active_tab == "Projektant automatyczny":
        st.subheader("🔍 Wyszukaj miejsce startowe")
        search_query = st.text_input("Tutaj wpisz skąd chcesz zacząć i naciśnij przycisk 'Znajdź punkt na mapie'", key="search_query_input")

        if st.button("🔎 Znajdź punkt na mapie", use_container_width=True):
            if search_query:
                with st.spinner("Szukanie..."):
                    try:
                        from geopy.geocoders import Nominatim

                        geolocator = Nominatim(user_agent="bike_route_planner_2026")
                        location = geolocator.geocode(search_query)
                        if location:
                            st.session_state.permanent_lat = location.latitude
                            st.session_state.permanent_lon = location.longitude
                            st.session_state.map_center = [location.latitude, location.longitude]
                            st.session_state["lat_input_field"] = location.latitude
                            st.session_state["lon_input_field"] = location.longitude
                            st.session_state.search_address = location.address
                            st.toast(f"Znaleziono: {location.address[:45]}...", icon="📍")
                            st.rerun()
                        else:
                            st.session_state.search_address = None
                            st.error("Nie znaleziono takiego miejsca.")
                    except Exception as e:
                        st.error(f"Błąd wyszukiwania: {e}")

        if 'search_address' in st.session_state and st.session_state.search_address:
            st.markdown(
                f"""
                    <div style="background-color: rgba(204, 204, 153, 0.15); padding: 10px; border-radius: 8px; border: 1px solid #cccc99; margin-top: -10px; margin-bottom: 15px;">
                        <span style="color: #cccc99; font-size: 13px; font-weight: bold;">📍 Aktywny punkt startowy:</span><br>
                        <span style="color: #ffffff; font-size: 13px;">{st.session_state.search_address}</span>
                    </div>
                    """,
                unsafe_allow_html=True
            )

        if st.button("Użyj mojej lokalizacji", use_container_width=True):
            st.session_state.loc_requested = True
            st.session_state.search_address = "📍 Twoja bieżąca lokalizacja (GPS)"
            st.rerun()

        st.write("Za pomocą +/- możesz dostosować swoją dokładną lokalizację.")
        input_lat = st.number_input("Szerokość geograficzna", value=st.session_state.permanent_lat, format="%.6f",
                                    step=0.0001, key="lat_input_field", on_change=on_lat_change)
        input_lon = st.number_input("Długość geograficzna", value=st.session_state.permanent_lon, format="%.6f",
                                    step=0.0001, key="lon_input_field", on_change=on_lon_change)

        dist_km = st.slider("Dystans w kilometrach", 5, 30, 15)
        bike_type = st.selectbox("Typ roweru (wybór opcjonalny)",
                                 ["Brak", "Szosowy/miejski", "Gravel (hybrydowy)", "MTB (terenowy)"])
        generate_btn = st.button("🚴‍♂️ Wygeneruj Trasę", type="primary", use_container_width=True)

    elif active_tab == "Projektant manualny":
        bike_type = st.selectbox("Typ roweru (wybór opcjonalny)",
                                 ["Brak", "Szosowy/miejski", "Gravel (hybrydowy)", "MTB (terenowy)"])
    else:
        st.caption("Przełącz na projektant automatyczny lub manualny, aby dostosowywać trasę.")
# =========================================================================
# KROK 3: TREŚĆ OKNA GŁÓWNEGO
# =========================================================================
st.divider()

if active_tab == "Projektant automatyczny":
    if st.session_state.load_info:
        st.warning(f"📍 **Aktywna trasa:** {st.session_state.load_info}")
        if st.button("Wyczyść i zacznij od nowa"):
            st.session_state.generated_geojson = None
            st.session_state.load_info = None
            st.session_state.auto_coords = None
            st.session_state.search_address = None
            st.session_state.route_score = (None, None, None)
            st.rerun()

    if generate_btn:
        with st.spinner("Trwa przygotowywanie trasy..."):
            try:
                curr_lat = st.session_state.permanent_lat
                curr_lon = st.session_state.permanent_lon
                side_m = (dist_km * 1000 * 0.65) / 4
                corners = calculate_square_corners(curr_lon, curr_lat, side_m)
                G = get_graph(curr_lat, curr_lon, dist=side_m * 1.5, network_type="bike")
                st.session_state.G = G

                route_nodes = find_circular_route(G, corners)
                if route_nodes:
                    nodes_df, _ = ox.graph_to_gdfs(G)
                    raw_coords = [[nodes_df.loc[n].y, nodes_df.loc[n].x] for n in route_nodes]
                    clean_input = [[c[1], c[0]] for c in raw_coords]
                    cleaned = clean_line_coordinates(clean_input)
                    display_coords = [[c[1], c[0]] for c in cleaned]

                    st.session_state.auto_coords = display_coords
                    dist = ox.routing.route_to_gdf(G, route_nodes)['length'].sum() / 1000

                    status, color, surf_stats = analyze_route_compatibility(G, route_nodes, bike_type)
                    st.session_state.route_score = (status, color, surf_stats)

                    st.session_state.load_info = f"Nowa trasa {round(dist, 1)} km"
                    st.session_state.generated_geojson = {
                        "type": "FeatureCollection",
                        "features": [{
                            "type": "Feature",
                            "geometry": {"type": "LineString", "coordinates": [[c[1], c[0]] for c in display_coords]},
                            "properties": {"length_km": round(dist, 2)}
                        }]
                    }
                    st.session_state.map_center = [curr_lat, curr_lon]
                    st.rerun()
                else:
                    st.error("Nie znaleziono pętli.")
            except Exception as e:
                st.error(f"Błąd: {e}")

    if st.session_state.generated_geojson:
        data = st.session_state.generated_geojson
        dist = data['features'][0]['properties']['length_km']
        start_point = [data['features'][0]['geometry']['coordinates'][0][1],
                       data['features'][0]['geometry']['coordinates'][0][0]]

        c1, c2, c3 = st.columns([1, 2, 0.4])
        c1.metric("Długość całkowita", f"{dist} km")

        status, color, surf_stats = st.session_state.route_score

        with c2:
            if bike_type != "Brak" and status:
                st.markdown(f"**Status dopasowania do roweru:** \n**{status}**")
                st.markdown("---")

            if surf_stats:
                st.markdown("**Struktura nawierzchni trasy:**")
                st.markdown(
                    f"🟦 **Utwardzona (Asfalt/Beton):** `{surf_stats.get('paved_pct', 0)}%` ({surf_stats.get('paved_km', 0)} km)")
                st.markdown(
                    f"🟫 **Nieutwardzona (Szuter/Grunt):** `{surf_stats.get('unpaved_pct', 0)}%` ({surf_stats.get('unpaved_km', 0)} km)")
                if surf_stats.get('unknown_pct', 0) > 0:
                    st.markdown(
                        f"⬜ **Nieokreślona (Brak danych):** `{surf_stats.get('unknown_pct', 0)}%` ({surf_stats.get('unknown_km', 0)} km)")

        with c3:
            with st.popover("❓", help="Dowiedz się, jak analizujemy trasy"):
                st.markdown("### 🧭 Jak analizujemy Twoją trasę?")

                st.markdown("**1️⃣ Analiza nawierzchni**")
                st.markdown("""
                    Niezależnie od wybranego roweru, zawsze sprawdzamy z czego zbudowana jest trasa - 
                    każdy odcinek klasyfikujemy jako **utwardzony** (asfalt, beton, kostka), 
                    **nieutwardzony** (szuter, grunt, piach) lub **nieokreślony** (brak danych w mapie), 
                    a wynik pokazujemy jako procentowy skład całej trasy.
                """)

                st.divider()

                st.markdown("**2️⃣ Indeks dopasowania do roweru**")
                st.markdown("""
                    Jeśli wybierzesz typ roweru, dodatkowo liczymy **indeks trudności w skali od 0 (idealnie) do 5 (nieprzejezdne)**, 
                    dopasowany właśnie do niego. System uwzględnia nie tylko nawierzchnię, ale też klasę drogi 
                    (np. droga główna vs leśna ścieżka) oraz jej jakość:
                """)

                st.warning("""
                    - **🚴 Szosowy/miejski:** priorytet dla asfaltu i dróg utwardzonych - nawierzchnie gruntowe drastycznie podnoszą trudność.
                    - **🌲 Gravel (hybrydowy):** szuter i ubita ziemia to środowisko idealne - asfalt nie jest karany, ale nie jest też premiowany.
                    - **⛰️ MTB (terenowy):** piach i leśne ścieżki dają indeks optymalny (0), a asfalt traktowany jest jako lekko nieefektywny.
                """)

                st.caption("💡 Ostateczny indeks to średnia ważona długością odcinków całej trasy.")

        m = folium.Map(location=st.session_state.map_center, zoom_start=13)
        folium.GeoJson(data, style_function=lambda x: {'color': '#2ecc71', 'weight': 5}).add_to(m)
        folium.Marker(start_point, popup="Start/Meta", icon=folium.Icon(color='red')).add_to(m)

        st_folium(m, use_container_width=True, height=550, key="active_gen_map")

        st.divider()
        st.subheader("📲 Wyślij trasę na telefon")
        col_down1, col_down2, col_down3 = st.columns([1, 1, 1])
        active_geojson = st.session_state.generated_geojson
        current_gpx = create_gpx(active_geojson)
        ts = datetime.now().strftime("%H%M%S")

        with col_down1:
            st.download_button(label="🗺️ POBIERZ PLIK GPX", data=current_gpx, file_name=f"trasa_{ts}.gpx",
                               mime="application/gpx+xml", use_container_width=True, key=f"dl_btn_{ts}")
            if st.button("📧 WYŚLIJ NA MÓJ E-MAIL", use_container_width=True):
                if st.session_state.user:
                    db = SessionLocal()
                    try:
                        curr_user = db.get(User, st.session_state.user['id'])
                        target_email = curr_user.email if curr_user else None
                    except Exception as e:
                        st.error(f"Błąd bazy danych: {e}")
                        target_email = None
                    finally:
                        db.close()

                    if target_email:
                        with st.spinner("Wysyłanie..."):
                            if send_custom_email(target_email.strip(), "Plik twojej trasy RoutePlanner",
                                                 "Cześć! W załączniku przesyłamy plik wygenerowanej przez ciebie trasy. Pobierz ją na telefon i otwórz za pomocą ulubionej aplikacji i ruszaj w drogę! Rekomendujemy aplikację Samsung Health na systemy Android oraz aplikację Zdrowie na systemy IOS. ", current_gpx,
                                                 f"trasa_{ts}.gpx"):
                                st.toast("E-mail został wysłany!")
                            else:
                                r = st.error("Błąd serwera e-mail.")
                else:
                    st.error("Nie znaleziono adresu e-mail lub nie jesteś zalogowany.")

        with col_down3:
            if st.session_state.user:
                with st.popover("💾 Zapisz w profilu", use_container_width=True):
                    r_name = st.text_input("Nazwa trasy", "Moja Trasa")
                    r_vis = st.selectbox("Widoczność", ["publiczna", "prywatna"])
                    if st.button("Potwierdź Zapis"):
                        db = SessionLocal()
                        save_data = json.loads(json.dumps(data))  # kopia, żeby nie ruszać oryginału w sesji
                        if surf_stats:
                            save_data['features'][0]['properties']['surface_stats'] = surf_stats
                        new_r = SavedRoute(user_id=st.session_state.user['id'], name=r_name,
                                           geojson_data=json.dumps(save_data), visibility=r_vis)
                        db.add(new_r)
                        db.commit()
                        db.close()
                        st.success("Zapisano!")
            else:
                st.button("💾 Zaloguj się by zapisać", disabled=True, use_container_width=True)
    else:
        st.warning("Ustaw parametry i naciśnij 'Wygeneruj Trasę' w panelu bocznym po lewej, by zobaczyć ją na mapie.")
        m_preview = folium.Map(location=st.session_state.map_center, zoom_start=13)
        folium.Marker(st.session_state.map_center, popup="Twoja lokalizacja",
                      icon=folium.Icon(color='blue', icon='info-sign')).add_to(m_preview)
        st_folium(m_preview, use_container_width=True, height=550, key="preview_map")

elif active_tab == "Projektant manualny":
    show_manual_designer(bike_type)

    if st.session_state.generated_geojson and 'route_score' in st.session_state:
        status, color, surf_stats = st.session_state.route_score
        if surf_stats:
            st.markdown("---")
            c1, c2 = st.columns([1, 3])
            with c1:
                if bike_type != "Brak" and status:
                    st.markdown(f"**Dopasowanie:**\n{status}")
            with c2:
                st.markdown("**Struktura nawierzchni trasy:**")
                cols = st.columns(3)
                cols[0].markdown(
                    f"🟦 **Utwardzona:** `{surf_stats.get('paved_pct', 0)}%` ({surf_stats.get('paved_km', 0)} km)")
                cols[1].markdown(
                    f"🟫 **Nieutwardzona:** `{surf_stats.get('unpaved_pct', 0)}%` ({surf_stats.get('unpaved_km', 0)} km)")
                if surf_stats.get('unknown_pct', 0) > 0:
                    cols[2].markdown(
                        f"⬜ **Nieokreślona:** `{surf_stats.get('unknown_pct', 0)}%` ({surf_stats.get('unknown_km', 0)} km)")

elif active_tab == "🌍 Społeczność":
    st.header("🌍 Trasy dodane przez społeczność")
    db = SessionLocal()
    routes = db.query(SavedRoute).filter_by(visibility='publiczna').all()  # <-- naprawiony filtr

    for r in routes:
        avg_rating_query = db.query(func.avg(RouteReview.rating)).filter(RouteReview.route_id == r.id).scalar()
        avg_text = f"⭐ {round(avg_rating_query, 1)}/5" if avg_rating_query else "🔹 Brak ocen"

        with st.container(border=True):
            c1, c2, c3 = st.columns([2.5, 1, 1])
            try:
                r_data = json.loads(r.geojson_data)
                r_props = r_data['features'][0]['properties']
                r_dist = r_props.get('length_km', '??')
                surface_summary = format_surface_summary(r_props.get('surface_stats'))
            except:
                r_dist = "??"
                surface_summary = None

            c1.write(f"**{r.name}** ({r_dist} km) | Autor: `{r.owner.username}` | **{avg_text}**")
            if surface_summary:
                c1.caption(f"Nawierzchnia: {surface_summary}")

            if c2.button("↗️ Wczytaj", key=f"pub_{r.id}", use_container_width=True):
                load_route_action(r.geojson_data, r.name)
                st.session_state.auto_coords = [[c[1], c[0]] for c in r_data['features'][0]['geometry']['coordinates']]
                st.rerun()

            if st.session_state.user:
                if c3.button("💬 Dodaj opinię", key=f"rev_btn_{r.id}", use_container_width=True):
                    review_dialog(r.id, r.name)
            else:
                c3.button("💬 Zaloguj się", key=f"rev_dis_{r.id}", disabled=True, use_container_width=True,
                          help="Musisz być zalogowany, by oceniać.")

            reviews = db.query(RouteReview).filter(RouteReview.route_id == r.id).order_by(
                RouteReview.created_at.desc()).all()
            if reviews:
                with st.expander(f"👁️ Zobacz opinie użytkowników ({len(reviews)})"):
                    for rev in reviews:
                        stars = f" {'⭐' * rev.rating}" if rev.rating else ""
                        author = rev.user.username if rev.user else "Anonim"
                        comment_text = f'"{rev.comment}"' if rev.comment else "_Brak komentarza tekstowego_"
                        st.markdown(f"**{author}**{stars} \n{comment_text}")
                        st.caption(f"Dodano: {rev.created_at.strftime('%Y-%m-%d %H:%M')}")
                        st.divider()
    db.close()

elif active_tab == "📒 Zapisane Trasy":
    if st.session_state.user:
        st.header("🎴 Twoje Trasy")
        db = SessionLocal()
        my_routes = db.query(SavedRoute).filter_by(user_id=st.session_state.user['id']).all()

        for r in my_routes:
            with st.container(border=True):
                c1, c2, c3 = st.columns([2, 1, 1])
                try:
                    r_data = json.loads(r.geojson_data)
                    r_props = r_data['features'][0]['properties']
                    r_dist = r_props.get('length_km', '??')
                    surface_summary = format_surface_summary(r_props.get('surface_stats'))
                except:
                    r_dist = "??"
                    surface_summary = None

                c1.write(f"**{r.name}** ({r_dist} km) [{r.visibility}]")
                if surface_summary:
                    c1.caption(f"Nawierzchnia: {surface_summary}")

                if c2.button("↗️ Wczytaj", key=f"my_{r.id}"):
                    load_route_action(r.geojson_data, r.name)
                    st.session_state.auto_coords = [[c[1], c[0]] for c in
                                                    r_data['features'][0]['geometry']['coordinates']]
                    st.rerun()

                if c3.button("🗑️ Usuń", key=f"del_{r.id}"):
                    db.delete(r)
                    db.commit()
                    st.rerun()
        db.close()
    else:
        st.warning("Zaloguj się, by uzyskać podgląd.")