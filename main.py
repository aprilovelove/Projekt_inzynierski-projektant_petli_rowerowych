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
from app.db.database import engine, Base, User, SavedRoute

# Ta linia to "magiczny przycisk", który tworzy tabele
try:
    Base.metadata.create_all(bind=engine)
    st.sidebar.success("Połączono z bazą danych!")
except Exception as e:
    st.sidebar.error(f"Błąd tworzenia tabel: {e}")
# Importy z plików lokalnych
from app.services.auth import login_user, register_user
from app.db.database import SessionLocal, SavedRoute

# NOWE IMPORTY (KROK 2)
from app.utils.geo_utils import calculate_square_corners, create_gpx, generate_qr_image
from app.services.route_service import find_circular_route, clean_line_coordinates
from app.services.auth import login_user, register_user
from app.db.database import SessionLocal, SavedRoute, User
from app.services.route_service import get_graph

from app.db.database import engine, Base
Base.metadata.create_all(bind=engine)
# --- KONFIGURACJA I SŁOWNIKI ---

BIKE_PROFILES = {
    "Szosowy/miejski": {
        "good": ["asphalt", "concrete", "paved"],
        "neutral": ["sett", "unpaved"],
        "bad": ["gravel", "cobblestone", "dirt", "sand", "grass", "ground"]
    },
    "Gravel(hybrydowy)": {
        "good": ["asphalt", "gravel", "unpaved", "dirt", "compacted"],
        "neutral": ["concrete", "sett", "cobblestone"],
        "bad": ["sand", "grass"]
    },
    "MTB(terenowy)": {
        "good": ["gravel", "dirt", "sand", "grass", "ground", "cobblestone", "unpaved"],
        "neutral": ["asphalt", "concrete", "sett"],
        "bad": []
    }
}


# --- LOGIKA ANALITYCZNA I POMOCNICZA ---

def analyze_route_compatibility(G, route_nodes, bike_type):
    if not bike_type or bike_type == "Brak":
        return None, None
    edges = ox.routing.route_to_gdf(G, route_nodes)
    if 'surface' not in edges.columns:
        return "Brak danych o nawierzchni w OpenStreetMaps", "gray"
    surfaces = edges['surface'].dropna().tolist()
    if not surfaces:
        return "Brak danych o nawierzchni w OpenStreetMaps", "gray"
    score = 0
    profile = BIKE_PROFILES[bike_type]
    for s in surfaces:
        s_val = s[0] if isinstance(s, list) else s
        if s_val in profile["good"]:
            score += 1
        elif s_val in profile["neutral"]:
            score += 0.5
    ratio = score / len(surfaces)
    if ratio > 0.8:
        return "🟢 Trasa idealnie dopasowana", "green"
    elif ratio > 0.4:
        return "🟡 Trasa średnio dopasowana", "orange"
    else:
        return "🔴 Trasa niedopasowana", "red"


# --- APLIKACJA STREAMLIT ---
st.set_page_config(page_title="RoutePlanner", layout="wide")

st.markdown("""
    <style>
        /* 1. Kolor tła Sidebara */
        [data-testid="stSidebar"] {
            background-color:#006600;
            border-right: 2px solid  #cccc99 ; /* Zielone obramowanie z prawej */
        }

        /* 2. Główny kolor tła aplikacji */
        .stApp {
            background-color: #000000;
        }

        /* 3. Stylizacja kontenerów (obramowania Twoich tras) */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid #e0e0e0;
            border-radius: 10px;
            padding: 10px;
            background-color: #ffffff;
        }

        /* 4. Stylizacja kart w zakładkach (Community/Saved) */
        .stElementContainer div[data-testid="stExpander"] {
            border: 1px solid #ffcc00;
        }
    </style>
""", unsafe_allow_html=True)

# INICJALIZACJA STANU SESJI
if 'user' not in st.session_state: st.session_state.user = None
if 'generated_geojson' not in st.session_state: st.session_state.generated_geojson = None
if 'map_center' not in st.session_state: st.session_state.map_center = [50.2859, 18.9549]
if 'load_info' not in st.session_state: st.session_state.load_info = None
if 'route_score' not in st.session_state: st.session_state.route_score = (None, None)
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


# --- SIDEBAR ---
with st.sidebar:
    if st.session_state.user is None:
        st.header("🔑 Logowanie")
        choice = st.radio("Akcja", ["Logowanie", "Rejestracja"])
        u = st.text_input("Użytkownik")
        p = st.text_input("Hasło", type="password")
        if choice == "Logowanie":
            if st.button("Zaloguj"):
                user = login_user(u, p)
                if user:
                    st.session_state.user = {"id": user.id, "name": user.username}
                    st.rerun()
                else:
                    st.error("Błędne dane")
        else:
            if st.button("Zarejestruj"):
                if register_user(u, p):
                    st.success("Konto utworzone!")
                else:
                    st.error("Użytkownik już istnieje.")
    else:
        st.success(f"Zalogowany jako: {st.session_state.user['name']}")
        if st.button("Wyloguj"):
            st.session_state.user = None
            st.rerun()

    st.divider()
    st.header("🪧 Parametry Trasy")
    if st.button("Użyj mojej lokalizacji"):
        st.session_state.loc_requested = True
        st.rerun()

    st.number_input("Szerokość (Lat)", format="%.6f", key="lat_widget", on_change=update_center)
    st.number_input("Długość (Lon)", format="%.6f", key="lon_widget", on_change=update_center)

    dist_km = st.slider("Dystans (km)", 5, 30, 15)
    bike_type = st.selectbox("Typ roweru(opcjonalne)",
                             ["Brak", "Szosowy/miejski", "Gravel(hybrydowy)", "MTB(terenowy)"])
    clean_option = st.checkbox("Wyczyść backtracking", value=True)
    generate_btn = st.button("🚴‍♂️ Wygeneruj Trasę", type="primary")

# --- INTERFEJS GŁÓWNY ---
tab1, tab2, tab3 = st.tabs(["🚲 Projektant", "🌍 Społeczność", "📒 Zapisane Trasy"])

with tab1:
    if st.session_state.load_info:
        st.info(f"📍 **Aktywna trasa:** {st.session_state.load_info}")
        if st.button("Wyczyść i zacznij od nowa"):
            st.session_state.generated_geojson = None
            st.session_state.load_info = None
            st.rerun()

    if generate_btn:
        with st.spinner("Trwa przygotowywanie trasy..."):
            try:
                curr_lat = st.session_state.lat_widget
                curr_lon = st.session_state.lon_widget

                side_m = (dist_km * 1000 * 0.65) / 4
                corners = calculate_square_corners(curr_lon, curr_lat, side_m)

                # ZMIANA KROK 3.1: Użycie get_graph z buforowaniem lokalnym
                G = get_graph(curr_lat, curr_lon, dist=side_m * 1.5, network_type="bike")

                route_nodes = find_circular_route(G, corners)
                if route_nodes:
                    nodes_df, _ = ox.graph_to_gdfs(G)
                    raw_coords = [[nodes_df.loc[n].y, nodes_df.loc[n].x] for n in route_nodes]
                    if clean_option:
                        clean_input = [[c[1], c[0]] for c in raw_coords]
                        cleaned = clean_line_coordinates(clean_input)
                        display_coords = [[c[1], c[0]] for c in cleaned]
                    else:
                        display_coords = raw_coords
                    dist = ox.routing.route_to_gdf(G, route_nodes)['length'].sum() / 1000
                    st.session_state.route_score = analyze_route_compatibility(G, route_nodes, bike_type)
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

        c1, c2 = st.columns([1, 2])
        c1.metric("Długość", f"{dist} km")
        status, color = st.session_state.route_score
        if status: c2.markdown(f"**Status dopasowania do roweru:** :{color}[{status}]")

        m = folium.Map(location=st.session_state.map_center, zoom_start=13)
        folium.GeoJson(data, style_function=lambda x: {'color': '#2ecc71', 'weight': 5}).add_to(m)
        folium.Marker(start_point, popup="Start/Meta", icon=folium.Icon(color='red')).add_to(m)
        st_folium(m, width=1200, height=550, key="active_gen_map")

        # --- SEKCJA EKSPORTU ---
        st.divider()
        st.subheader("📲 Wyślij trasę na telefon")
        col_down1, col_down2, col_down3 = st.columns([1, 1, 1])

        active_geojson = st.session_state.generated_geojson
        current_gpx = create_gpx(active_geojson)

        current_start_lon = active_geojson['features'][0]['geometry']['coordinates'][0][0]
        current_start_lat = active_geojson['features'][0]['geometry']['coordinates'][0][1]
        current_qr_img = generate_qr_image(current_start_lat, current_start_lon)

        ts = datetime.now().strftime("%H%M%S")

        with col_down1:
            st.download_button(
                label="🗺️ POBIERZ PLIK GPX",
                data=current_gpx,
                file_name=f"trasa_{ts}.gpx",
                mime="application/gpx+xml",
                use_container_width=True,
                key=f"dl_btn_{ts}"
            )
            st.caption("Pobierz i otwórz w OsmAnd")

        with col_down2:
            st.image(current_qr_img, width=150)
            st.caption("Skanuj kod, by ustawić punkt startowy w OsmAnd.")

        with col_down3:
            if st.session_state.user:
                with st.popover("💾 Zapisz w profilu", use_container_width=True):
                    r_name = st.text_input("Nazwa trasy", "Moja Trasa")
                    r_vis = st.selectbox("Widoczność", ["public", "private"])
                    if st.button("Potwierdź Zapis"):
                        db = SessionLocal()
                        new_r = SavedRoute(user_id=st.session_state.user['id'], name=r_name,
                                           geojson_data=json.dumps(data), visibility=r_vis)
                        db.add(new_r)
                        db.commit()
                        db.close()
                        st.success("Zapisano!")
            else:
                st.button("💾 Zaloguj się by zapisać", disabled=True, use_container_width=True)

    else:
        st.info("Ustaw parametry i naciśnij 'Wygeneruj Trasę', by uzyskać podgląd w projektancie...")
        m_preview = folium.Map(location=st.session_state.map_center, zoom_start=13)
        folium.Marker(st.session_state.map_center, icon=folium.Icon(color='blue')).add_to(m_preview)
        st_folium(m_preview, width=1200, height=550, key="preview_map")

# --- POZOSTAŁE ZAKŁADKI ---
with tab2:
    st.header("🌍 Trasy dodane przez społeczność")
    db = SessionLocal()
    routes = db.query(SavedRoute).filter_by(visibility='public').all()
    for r in routes:
        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            try:
                r_data = json.loads(r.geojson_data)
                r_dist = r_data['features'][0]['properties'].get('length_km', '??')
            except:
                r_dist = "??"
            c1.write(f"**{r.name}** ({r_dist} km) | Autor: {r.owner.username}")
            if c2.button("↗️ Wczytaj", key=f"pub_{r.id}"):
                load_route_action(r.geojson_data, r.name)
                st.rerun()
    db.close()

with tab3:
    if st.session_state.user:
        st.header("🎴 Twoje Trasy")
        db = SessionLocal()
        my_routes = db.query(SavedRoute).filter_by(user_id=st.session_state.user['id']).all()
        for r in my_routes:
            with st.container(border=True):
                c1, c2, c3 = st.columns([2, 1, 1])
                try:
                    r_data = json.loads(r.geojson_data)
                    r_dist = r_data['features'][0]['properties'].get('length_km', '??')
                except:
                    r_dist = "??"
                c1.write(f"**{r.name}** ({r_dist} km) [{r.visibility}]")
                if c2.button("↗️ Wczytaj", key=f"my_{r.id}"):
                    load_route_action(r.geojson_data, r.name)
                    st.rerun()
                if c3.button("🗑️ Usuń", key=f"del_{r.id}"):
                    db.delete(r)
                    db.commit()
                    st.rerun()
        db.close()
    else:
        st.warning("Zaloguj się, by uzyskać podgląd.")

