import streamlit as st
import osmnx as ox
import networkx as nx
import folium
from streamlit_folium import st_folium
import json
import math
from typing import List, Tuple
from streamlit_js_eval import get_geolocation
from datetime import datetime
import qrcode
from io import BytesIO
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship

# Importy z plików lokalnych
from app.db.database import engine, Base, User, SavedRoute, RouteReview
from app.db.database import SessionLocal
from app.utils.geo_utils import calculate_square_corners, create_gpx
from app.services.route_service import find_circular_route, clean_line_coordinates
from app.services.route_service import get_graph
from app.services.route_analysis_service import analyze_route_compatibility
from app.services.manual_designer import show_manual_designer
from app.services.auth import login_user, register_user
from app.services.email_service import send_custom_email

# Automatyczne utworzenie tabeli w NeonDB przy starcie aplikacji
Base.metadata.create_all(bind=engine)

# --- APLIKACJA STREAMLIT ---
st.set_page_config(
    page_title="RoutePlanner",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={'Get Help': None, 'Report a bug': None, 'About': None}
)

st.markdown("""
    <style>
        .stAppDeployButton {display:none !important;}
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        div[data-testid="stStatusWidget"] {visibility: hidden;}
        [data-testid="stSidebar"] { background-color:#006600; border-right: 2px solid #cccc99; }
        .stApp { background-color: #000000; }
        div[data-testid="stVerticalBlockBorderWrapper"] { border: 1px solid #e0e0e0; border-radius: 10px; padding: 10px; background-color: #ffffff; }
        .stElementContainer div[data-testid="stExpander"] { border: 1px solid #ffcc00; }
    </style>
""", unsafe_allow_html=True)

# INICJALIZACJA STANU SESJI
if 'user' not in st.session_state: st.session_state.user = None
if 'generated_geojson' not in st.session_state: st.session_state.generated_geojson = None
if 'map_center' not in st.session_state: st.session_state.map_center = [50.2859, 18.9549]
if 'load_info' not in st.session_state: st.session_state.load_info = None
if 'route_score' not in st.session_state: st.session_state.route_score = (None, None, None)
if 'loc_requested' not in st.session_state: st.session_state.loc_requested = False

# --- MECHANIZM AKTUALIZACJI WSPÓŁRZĘDNYCH ---
if 'new_coords' in st.session_state:
    st.session_state.lat_widget = st.session_state.new_coords[0]
    st.session_state.lon_widget = st.session_state.new_coords[1]
    st.session_state.map_center = st.session_state.new_coords
    del st.session_state.new_coords

if 'lat_widget' not in st.session_state: st.session_state.lat_widget = st.session_state.map_center[0]
if 'lon_widget' not in st.session_state: st.session_state.lon_widget = st.session_state.map_center[1]

# --- OBSŁUGA GPS W TLE ---
if st.session_state.loc_requested:
    loc_data = get_geolocation()
    if loc_data:
        st.session_state.new_coords = [loc_data['coords']['latitude'], loc_data['coords']['longitude']]
        st.session_state.loc_requested = False
        st.rerun()


def load_route_action(geojson_data, name):
    data = json.loads(geojson_data)
    st.session_state.generated_geojson = data
    st.session_state.load_info = name
    first_coord = data['features'][0]['geometry']['coordinates'][0]
    st.session_state.new_coords = [first_coord[1], first_coord[0]]


def update_center():
    st.session_state.map_center = [st.session_state.lat_widget, st.session_state.lon_widget]


@st.dialog("💬 Dodaj opinię o trasie")
def review_dialog(route_id, route_name):
    st.write(f"Oceniasz trasę: **{route_name}**")
    add_rating = st.checkbox("Chcę dodać ocenę punktową", value=True)
    rating_val = st.slider("Ocena trasy (1 - słaba, 5 - genialna)", 1, 5, 5) if add_rating else None
    add_comment = st.checkbox("Chcę dodać komentarz tekstowy", value=True)
    comment_val = st.text_area("Wpisz swoją opinię o warunkach na trasie:") if add_comment else None

    st.divider()
    if st.button("Zapisz opinię", use_container_width=True, type="primary"):
        db = SessionLocal()
        try:
            new_review = RouteReview(route_id=route_id, user_id=st.session_state.user['id'], rating=rating_val,
                                     comment=comment_val)
            db.add(new_review)
            db.commit()
            st.toast("Dziękujemy za dodanie opinii!", icon="🎉")
            st.rerun()
        except Exception as e:
            st.error(f"Błąd: {e}")
        finally:
            db.close()


# =========================================================================
# KROK 1: WYBÓR TRYBU (Zamiast st.tabs używamy stabilnego przełącznika segmentowego)
# =========================================================================
active_tab = st.segmented_control(
    "Wybierz tryb projektowania:",
    options=["🚲 Projektant automatyczny", "Projektant ręczny", "🌍 Społeczność", "📒 Zapisane Trasy"],
    default="🚲 Projektant automatyczny",
    label_visibility="collapsed"
)

# Zmienne pomocnicze
generate_btn = False
dist_km = 15
bike_type = "Brak"

# =========================================================================
# KROK 2: SIDEBAR (Budowany OD RAZU na podstawie wybranej karty, brak lagów)
# =========================================================================
with st.sidebar:
    if st.session_state.user is None:
        st.header("🔑 Panel Użytkownika")
        choice = st.radio("Akcja", ["Logowanie", "Rejestracja"])
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
            new_u = st.text_input("Twoje Imię/Nick")
            new_e = st.text_input("E-mail")
            new_p = st.text_input("Hasło", type="password")
            if st.button("Zarejestruj"):
                res = register_user(new_u, new_e, new_p)
                if res == "success":
                    st.success("Konto utworzone!")
                else:
                    st.error("Błąd rejestracji.")
    else:
        st.header("👤 Twój Profil")
        st.success(f"Zalogowany jako: **{st.session_state.user['name']}**")
        if st.button("🚪 Wyloguj się", use_container_width=True):
            st.session_state.user = None
            st.rerun()

    st.divider()
    st.header("🎴 Parametry Trasy")

    # Warunkowa zawartość parametrów trasy
    if active_tab == "🚲 Projektant automatyczny":
        st.subheader("🔍 Wyszukaj adres/miejsce")
        search_query = st.text_input("Wpisz np. miasto, ulicę:", key="search_query_input")
        if st.button("🔎 Znajdź na mapie", use_container_width=True):
            if search_query:
                try:
                    from geopy.geocoders import Nominatim

                    geolocator = Nominatim(user_agent="bike_route_planner_2026")
                    location = geolocator.geocode(search_query)
                    if location:
                        st.session_state.new_coords = [location.latitude, location.longitude]
                        st.rerun()
                except Exception as e:
                    st.error(f"Błąd: {e}")

        if st.button("Użyj mojej lokalizacji", use_container_width=True):
            st.session_state.loc_requested = True
            st.rerun()

        st.number_input("Szerokość (Lat)", format="%.6f", key="lat_widget", on_change=update_center)
        st.number_input("Długość (Lon)", format="%.6f", key="lon_widget", on_change=update_center)
        dist_km = st.slider("Dystans (km)", 5, 30, 15)
        bike_type = st.selectbox("Typ roweru(opcjonalne)",
                                 ["Brak", "Szosowy/miejski", "Gravel(hybrydowy)", "MTB(terenowy)"])
        generate_btn = st.button("🚴‍♂️ Wygeneruj Trasę", type="primary", use_container_width=True)

    elif active_tab == "Projektant ręczny":
        bike_type = st.selectbox("Typ roweru(opcjonalne)",
                                 ["Brak", "Szosowy/miejski", "Gravel(hybrydowy)", "MTB(terenowy)"])
    else:
        st.caption("Przełącz na projektant automatyczny lub ręczny.")

# =========================================================================
# KROK 3: GŁÓWNE OKNO APLIKACJI
# =========================================================================
st.divider()

if active_tab == "🚲 Projektant automatyczny":
    if st.session_state.load_info:
        st.info(f"📍 **Aktywna trasa:** {st.session_state.load_info}")
        if st.button("Wyczyść i zacznij od nowa"):
            st.session_state.generated_geojson = None
            st.session_state.load_info = None
            st.session_state.auto_coords = None
            st.rerun()

    if generate_btn:
        with st.spinner("Trwa przygotowywanie trasy..."):
            try:
                curr_lat = st.session_state.lat_widget
                curr_lon = st.session_state.lon_widget
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
                        "features": [{"type": "Feature", "geometry": {"type": "LineString",
                                                                      "coordinates": [[c[1], c[0]] for c in
                                                                                      display_coords]},
                                      "properties": {"length_km": round(dist, 2)}}]
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
        if status:
            c2.markdown(f"**Status dopasowania do roweru:** \n**{status}**")
            if surf_stats:
                c2.markdown(
                    f"🟦 **Utwardzona:** `{surf_stats['paved_pct']}%` | 🟫 **Nieutwardzona:** `{surf_stats['unpaved_pct']}%`")

        m = folium.Map(location=st.session_state.map_center, zoom_start=13)
        folium.GeoJson(data, style_function=lambda x: {'color': '#2ecc71', 'weight': 5}).add_to(m)
        folium.Marker(start_point, icon=folium.Icon(color='red')).add_to(m)
        st_folium(m, use_container_width=True, height=550, key="active_gen_map")
    else:
        m_preview = folium.Map(location=st.session_state.map_center, zoom_start=13)
        folium.Marker(st.session_state.map_center, icon=folium.Icon(color='blue')).add_to(m_preview)
        st_folium(m_preview, use_container_width=True, height=550, key="preview_map")

elif active_tab == "Projektant ręczny":
    show_manual_designer()

elif active_tab == "🌍 Społeczność":
    st.header("🌍 Trasy dodane przez społeczność")
    db = SessionLocal()
    routes = db.query(SavedRoute).filter_by(visibility='public').all()
    for r in routes:
        with st.container(border=True):
            st.write(f"**{r.name}** | Autor: `{r.owner.username}`")
            if st.button("↗️ Wczytaj", key=f"pub_{r.id}"):
                load_route_action(r.geojson_data, r.name)
                st.rerun()
    db.close()

elif active_tab == "📒 Zapisane Trasy":
    if st.session_state.user:
        st.header("🎴 Twoje Trasy")
        db = SessionLocal()
        my_routes = db.query(SavedRoute).filter_by(user_id=st.session_state.user['id']).all()
        for r in my_routes:
            with st.container(border=True):
                st.write(f"**{r.name}**")
                if st.button("↗️ Wczytaj", key=f"my_{r.id}"):
                    load_route_action(r.geojson_data, r.name)
                    st.rerun()
        db.close()
    else:
        st.warning("Zaloguj się, by uzyskać podgląd.")