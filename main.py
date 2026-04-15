import streamlit as st
import osmnx as ox
import folium
from streamlit_folium import st_folium
import json
from streamlit_js_eval import get_geolocation
from datetime import datetime

# --- IMPORTY Z TWOJEJ STRUKTURY (KROK 1 & 2) ---
from app.services.auth import login_user, register_user
from app.db.database import SessionLocal, SavedRoute, User
from app.utils.geo_utils import calculate_square_corners, create_gpx, generate_qr_image
from app.services.route_service import (
    find_circular_route,
    clean_line_coordinates,
    get_graph  # <--- Nasza nowa funkcja z Kroku 3
)

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


# --- LOGIKA ANALITYCZNA ---
def analyze_route_compatibility(G, route_nodes, bike_type):
    if not bike_type or bike_type == "Brak":
        return None, None
    edges = ox.routing.route_to_gdf(G, route_nodes)
    if 'surface' not in edges.columns:
        return "Brak danych o nawierzchni w OSM", "gray"
    surfaces = edges['surface'].dropna().tolist()
    if not surfaces:
        return "Brak danych o nawierzchni w OSM", "gray"
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
st.set_page_config(page_title="RoutePlanner Pro", layout="wide")

# CSS - Stylizacja inżynierska
st.markdown("""
    <style>
        [data-testid="stSidebar"] { background-color:#004d00; border-right: 2px solid #cccc99; }
        .stApp { background-color: #0e1117; }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid #444; border-radius: 10px; padding: 15px; background-color: #1e2129;
        }
    </style>
""", unsafe_allow_html=True)

# INICJALIZACJA STANU SESJI
for key, default in [
    ('user', None), ('generated_geojson', None), ('map_center', [50.2859, 18.9549]),
    ('load_info', None), ('route_score', (None, None)), ('loc_requested', False)
]:
    if key not in st.session_state: st.session_state[key] = default

# OBSŁUGA GPS
if st.session_state.loc_requested:
    loc_data = get_geolocation()
    if loc_data:
        st.session_state.map_center = [loc_data['coords']['latitude'], loc_data['coords']['longitude']]
        st.session_state.loc_requested = False
        st.rerun()


def load_route_action(geojson_data, name):
    data = json.loads(geojson_data)
    st.session_state.generated_geojson = data
    st.session_state.load_info = name
    first = data['features'][0]['geometry']['coordinates'][0]
    st.session_state.map_center = [first[1], first[0]]


# --- SIDEBAR ---
with st.sidebar:
    if st.session_state.user is None:
        st.header("🔑 Panel Dostępu")
        choice = st.radio("Akcja", ["Logowanie", "Rejestracja"])
        u = st.text_input("Użytkownik")
        p = st.text_input("Hasło", type="password")
        if choice == "Logowanie" and st.button("Zaloguj"):
            user = login_user(u, p)
            if user:
                st.session_state.user = {"id": user.id, "name": user.username}
                st.rerun()
            else:
                st.error("Błąd logowania")
        elif choice == "Rejestracja" and st.button("Zarejestruj"):
            if register_user(u, p):
                st.success("Konto utworzone!")
            else:
                st.error("Użytkownik istnieje.")
    else:
        st.success(f"Witaj, {st.session_state.user['name']}")
        if st.button("Wyloguj"):
            st.session_state.user = None
            st.rerun()

    st.divider()
    st.header("🪧 Parametry Trasy")
    if st.button("📍 Pobierz moją lokalizację"):
        st.session_state.loc_requested = True
        st.rerun()

    lat = st.number_input("Szerokość (Lat)", value=st.session_state.map_center[0], format="%.6f")
    lon = st.number_input("Długość (Lon)", value=st.session_state.map_center[1], format="%.6f")
    dist_km = st.slider("Dystans pętli (km)", 5, 50, 15)
    bike_type = st.selectbox("Typ roweru", ["Brak", "Szosowy/miejski", "Gravel(hybrydowy)", "MTB(terenowy)"])
    clean_option = st.checkbox("Optymalizacja geometrii (Backtracking)", value=True)
    generate_btn = st.button("🚴‍♂️ GENERUJ TRASĘ", type="primary")

# --- INTERFEJS GŁÓWNY ---
tab1, tab2, tab3 = st.tabs(["🚲 Projektant", "🌍 Społeczność", "📒 Twoje Archiwum"])

with tab1:
    if generate_btn:
        with st.spinner("KROK 3: Optymalizacja i pobieranie danych grafowych..."):
            try:
                # 1. Obliczanie narożników kwadratu
                side_m = (dist_km * 1000 * 0.65) / 4
                corners = calculate_square_corners(lon, lat, side_m)

                # 2. KROK 3.1: Pobieranie grafu z CACHE (graphml) zamiast każdorazowego API
                G = get_graph(lat, lon, dist=side_m * 1.5)

                # 3. Szukanie trasy
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
                    st.session_state.load_info = f"Trasa {round(dist, 1)} km"
                    st.session_state.generated_geojson = {
                        "type": "FeatureCollection",
                        "features": [{
                            "type": "Feature",
                            "geometry": {"type": "LineString", "coordinates": [[c[1], c[0]] for c in display_coords]},
                            "properties": {"length_km": round(dist, 2)}
                        }]
                    }
                    st.session_state.map_center = [lat, lon]
                    st.rerun()
                else:
                    st.error("Nie znaleziono bezpiecznej pętli w tym rejonie.")
            except Exception as e:
                st.error(f"Błąd silnika trasowania: {e}")

    if st.session_state.generated_geojson:
        data = st.session_state.generated_geojson
        dist = data['features'][0]['properties']['length_km']

        c1, c2 = st.columns([1, 2])
        c1.metric("Szacowany dystans", f"{dist} km")
        status, color = st.session_state.route_score
        if status: c2.markdown(f"**Nawierzchnia:** :{color}[{status}]")

        m = folium.Map(location=st.session_state.map_center, zoom_start=13)
        folium.GeoJson(data, style_function=lambda x: {'color': '#2ecc71', 'weight': 5}).add_to(m)
        folium.Marker([data['features'][0]['geometry']['coordinates'][0][1],
                       data['features'][0]['geometry']['coordinates'][0][0]],
                      popup="Start/Meta", icon=folium.Icon(color='red')).add_to(m)
        st_folium(m, width=1200, height=500, key="active_map")

        # EKSPORT
        st.divider()
        col_ex1, col_ex2, col_ex3 = st.columns([1, 1, 1])
        with col_ex1:
            st.download_button("💾 Pobierz GPX", create_gpx(data), f"trasa_{dist}km.gpx", "application/gpx+xml")
        with col_ex2:
            st.image(generate_qr_image(st.session_state.map_center[0], st.session_state.map_center[1]), width=120)
            st.caption("QR Start (OsmAnd)")
        with col_ex3:
            if st.session_state.user:
                r_name = st.text_input("Nazwa zapisu", f"Trasa {dist}km")
                if st.button("Zapisz w profilu"):
                    db = SessionLocal()
                    new_r = SavedRoute(user_id=st.session_state.user['id'], name=r_name,
                                       geojson_data=json.dumps(data), visibility="public")
                    db.add(new_r)
                    db.commit()
                    db.close()
                    st.success("Zapisano!")
            else:
                st.info("Zaloguj się, aby zapisać.")
    else:
        st.info("Oczekiwanie na parametry trasy...")
        m_pre = folium.Map(location=st.session_state.map_center, zoom_start=12)
        st_folium(m_pre, width=1200, height=500, key="pre_map")

# --- ZAKŁADKI SPOŁECZNOŚCI ---
with tab2:
    db = SessionLocal()
    routes = db.query(SavedRoute).filter_by(visibility='public').all()
    for r in routes:
        with st.container(border=True):
            col_a, col_b = st.columns([4, 1])
            col_a.write(f"📌 **{r.name}** | Autor: {r.owner.username}")
            if col_b.button("Wczytaj", key=f"load_{r.id}"):
                load_route_action(r.geojson_data, r.name)
                st.rerun()
    db.close()

with tab3:
    if st.session_state.user:
        db = SessionLocal()
        my_routes = db.query(SavedRoute).filter_by(user_id=st.session_state.user['id']).all()
        for r in my_routes:
            with st.container(border=True):
                col_x, col_y = st.columns([4, 1])
                col_x.write(f"🗺️ {r.name}")
                if col_y.button("Usuń", key=f"del_{r.id}"):
                    db.delete(r)
                    db.commit()
                    st.rerun()
        db.close()
    else:
        st.warning("Zaloguj się, aby zobaczyć swoje trasy.")