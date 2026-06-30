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
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': None
    }
)

st.markdown("""
    <style>
        /* 1. UKRYWANIE ELEMENTÓW SYSTEMOWYCH */
        .stAppDeployButton { display:none !important; }
        #MainMenu { visibility: hidden; }
        footer { visibility: hidden; }
        div[data-testid="stStatusWidget"] { visibility: hidden; }

        /* 2. STYLIZACJA SIDEBARU */
        [data-testid="stSidebar"] { 
            background-color: #0b3d16 !important;       /* Głęboka, nowoczesna zieleń */
            border-right: 3px solid #cccc99 !important;   /* Beżowo-złota ramka */
            border-radius: 0px 20px 20px 0px;            /* Zaokrąglenie prawych rogów */
        }

        /* Teksty i etykiety wewnątrz sidebaru */
        [data-testid="stSidebar"] .stMarkdown p, 
        [data-testid="stSidebar"] label {
            color: #ffffff !important;
            font-weight: 500 !important;
        }

        /* 3. CUSTOMOWE TŁO APLIKACJI I TYPOGRAFIA (ZAKŁADKI / GŁÓWNY WIDOK) */
        .stApp { 
            /* Płynny gradient radialny (efekt poświaty od lewego górnego rogu w stronę mroku) */
            background: radial-gradient(circle at 10% 10%, #061f0b 0%, #0d130e 50%, #000000 100%) !important;
            background-attachment: fixed !important;
        }

        /* Główne nagłówki (st.title, st.header, st.subheader) */
        h1, h2, h3 {
            color: #cccc99 !important;                   /* Beżowo-złoty kolor nagłówków */
            font-family: 'Helvetica Neue', sans-serif !important;
            padding-bottom: 8px;
        }

        /* Zwykły tekst na zakładkach (st.write, opisy itp.) */
        .stMarkdown p {
            color: #e2e8f0 !important;                   /* Jasnoszary, wysoce czytelny tekst */
            font-size: 15px !important;
        }

        /* 4. STYLIZACJA PRZYCISKÓW (st.button) NA ZAKŁADKACH */
        div.stButton > button {
            background-color: #166534 !important;        /* Ciemnozielone tło przycisków */
            color: #ffffff !important;                   /* Biały tekst */
            border: 1px solid #cccc99 !important;        /* Beżowa ramka spójna z aplikacją */
            border-radius: 8px !important;               /* Zaokrąglone rogi przycisku */
            padding: 8px 16px !important;
            font-weight: 600 !important;
            transition: all 0.3s ease !important;        /* Płynna animacja najechania */
        }

        /* Efekt po najechaniu na przycisk (Hover) */
        div.stButton > button:hover {
            background-color: #cccc99 !important;        /* Złotawo-beżowe tło */
            color: #000000 !important;                   /* Czarny tekst */
            border-color: #ffffff !important;
            box-shadow: 0px 4px 12px rgba(204, 204, 153, 0.3) !important;
        }

        /* Przycisk typu 'primary' (np. wyznaczanie trasy) - wyróżnienie */
        div.stButton > button[data-testid="stBaseButton-primary"] {
            background-color: #cccc99 !important;
            color: #000000 !important;
        }
        div.stButton > button[data-testid="stBaseButton-primary"]:hover {
            background-color: #ffffff !important;
            box-shadow: 0px 4px 15px rgba(255, 255, 255, 0.4) !important;
        }

        /* 5. NAGŁÓWKI ZAKŁADEK (st.tabs) - JEŚLI SĄ UŻYWANE */
        button[data-baseweb="tab"] {
            color: #888888 !important;                   /* Szare nieaktywne zakładki */
            font-size: 16px !important;
            font-weight: 500 !important;
            transition: color 0.2s ease !important;
        }
        button[data-baseweb="tab"][aria-selected="true"] {
            color: #cccc99 !important;                   /* Aktywna zakładka w kolorze beżowo-złotym */
            border-bottom-color: #cccc99 !important;     /* Podkreślenie aktywnej zakładki */
            font-weight: bold !important;
        }

        /* 6. POLA WPROWADZANIA TEKSTU (st.text_input / wyszukiwarki) */
        div[data-testid="stTextInput"] input {
            background-color: #1a1a1a !important;        /* Bardzo ciemne tło pól tekstowych */
            color: #ffffff !important;                   /* Biały wpisywany tekst */
            border: 1px solid #444444 !important;        /* Ciemnoszara dyskretna ramka */
            border-radius: 8px !important;
            transition: border-color 0.2s !important;
        }
        /* Aktywne/kliknięte pole tekstowe */
        div[data-testid="stTextInput"] input:focus {
            border-color: #cccc99 !important;            /* Ramka zmienia kolor na beżowo-złoty */
            box-shadow: 0 0 0 1px #cccc99 !important;
        }

        /* 7. TWOJE DOTYCHCHASOWE STYLE KONTENERÓW */
        /* Kontenery blokowe */
        div[data-testid="stVerticalBlockBorderWrapper"] { 
            border: 1px solid #e0e0e0 !important; 
            border-radius: 10px !important; 
            padding: 10px !important; 
            background-color: #ffffff !important;         /* Białe tło dla wyznaczonych bloków danych */
        }
        /* Etykiety i teksty wewnątrz białych bloków, by były czytelne na jasnym tle */
        div[data-testid="stVerticalBlockBorderWrapper"] .stMarkdown p,
        div[data-testid="stVerticalBlockBorderWrapper"] h1,
        div[data-testid="stVerticalBlockBorderWrapper"] h2,
        div[data-testid="stVerticalBlockBorderWrapper"] h3 {
            color: #1a1a1a !important;
        }

        /* Rozwijane kontenery (st.expander) */
        .stElementContainer div[data-testid="stExpander"] { 
            border: 1px solid #ffcc00 !important; 
            background-color: #111111 !important;        /* Ciemne tło wewnątrz expandera */
        }
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


# --- OKNO MODALNE (DIALOGOWE) DO DODAWANIA OPINII ---
@st.dialog("💬 Dodaj opinię o trasie")
def review_dialog(route_id, route_name):
    st.write(f"Oceniasz trasę: **{route_name}**")

    add_rating = st.checkbox("Chcę dodać ocenę punktową", value=True)
    rating_val = None
    if add_rating:
        rating_val = st.slider("Ocena trasy (1 - słaba, 5 - genialna)", 1, 5, 5)

    add_comment = st.checkbox("Chcę dodać komentarz tekstowy", value=True)
    comment_val = None
    if add_comment:
        comment_val = st.text_area("Wpisz swoją opinię o warunkach na trasie:",
                                   placeholder="np. Świetne widoki, ale na 5 kilometrze sporo piasku...")

    st.divider()
    if st.button("Zapisz opinię", use_container_width=True, type="primary"):
        if not add_rating and not add_comment:
            st.error("Musisz wybrać przynajmniej jedną opcję (ocenę lub komentarz)!")
            return

        if add_comment and not comment_val.strip():
            st.error("Komentarz nie może być pusty, jeśli zaznaczyłeś tę opcję.")
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
# KROK 1: WYBÓR TRYBU (Niezawodna kontrola segmentowa)
# =========================================================================
active_tab = st.segmented_control(
    "Wybierz tryb projektowania:",
    options=["🚲 Projektant automatyczny", "Projektant ręczny", "🌍 Społeczność", "📒 Zapisane Trasy"],
    default="🚲 Projektant automatyczny",
    label_visibility="collapsed"
)

# Zmienne globalne dla sidebaru
generate_btn = False
dist_km = 15
bike_type = "Brak"

# =========================================================================
# KROK 2: SIDEBAR (Budowany reaktywnie bez lagów)
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

            with st.expander("Zapomniałeś hasła?"):
                reset_email = st.text_input("Wpisz e-mail do resetu", key="res_em")
                if st.button("Wyślij kod"):
                    from app.services.auth import initiate_password_reset

                    code = initiate_password_reset(reset_email)
                    if code:
                        send_custom_email(reset_email, "Kod resetu hasła", f"Twój kod to: {code}")
                        st.info("Jeśli e-mail istnieje, kod został wysłany.")
                    else:
                        st.error("Nie znaleziono takiego adresu.")
        else:
            new_u = st.text_input("Twoje Imię/Nick")
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
                        st.toast(f"Znaleziono: {location.address[:45]}...", icon="📍")
                        st.rerun()
                    else:
                        st.error("Nie znaleziono takiego miejsca.")
                except Exception as e:
                    st.error(f"Błąd wyszukiwania: {e}")

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
        st.caption("Przełącz na projektant automatyczny lub ręczny, aby zmienić ustawienia.")

# =========================================================================
# KROK 3: TREŚĆ OKNA GŁÓWNEGO
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
        if status:
            c2.markdown(f"**Status dopasowania do roweru:** \n**{status}**")
            if surf_stats:
                c2.markdown("---")
                c2.markdown("**Struktura nawierzchni trasy:**")
                c2.markdown(
                    f"🟦 **Utwardzona (Asfalt/Beton):** `{surf_stats['paved_pct']}%` ({surf_stats['paved_km']} km)")
                c2.markdown(
                    f"🟫 **Nieutwardzona (Szuter/Grunt):** `{surf_stats['unpaved_pct']}%` ({surf_stats['unpaved_km']} km)")
                if surf_stats['unknown_pct'] > 0:
                    c2.markdown(
                        f"⬜ **Nieokreślona (Brak danych):** `{surf_stats['unknown_pct']}%` ({surf_stats['unknown_km']} km)")

        with c3:
            with st.popover("❓", help="Dowiedz się, jak liczymy dopasowanie"):
                st.markdown("### 🧠 Algorytm Indeksowania Trudności")
                st.info("""
                        Ocena wyliczana jest dynamicznie w skali **0 (Idealnie) do 5 (Nieprzejezdne)** relatywnie dla wybranego typu roweru:
                        - **Dla Szosy:** Nawierzchnie gruntowe drastycznie podnoszą trudność.
                        - **Dla MTB:** Asfalt traktowany jest jako nieefektywny (nakłada lekką karę), a piach i leśne ścieżki dają indeks optymalny (0).
                        - **Dla Gravela:** Szuter i ubitą ziemię system indeksuje jako perfekcyjne środowisko.
                    """)

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
                        st.error(f"Błąd bazy danych: {e}"); target_email = None
                    finally:
                        db.close()

                    if target_email:
                        with st.spinner("Wysyłanie..."):
                            if send_custom_email(target_email.strip(), "Twoja trasa GPX",
                                                 "Cześć! W załączniku przesyłamy trasę.", current_gpx,
                                                 f"trasa_{ts}.gpx"):
                                st.toast("E-mail został wysłany!")
                            else:
                                st.error("Błąd serwera e-mail.")
                else:
                    st.error("Nie znaleziono adresu e-mail lub nie jesteś zalogowany.")

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
        st.info("Ustaw parametry i naciśnij 'Wygeneruj Trasę', by uzyskać podgląd...")
        m_preview = folium.Map(location=st.session_state.map_center, zoom_start=13)
        folium.Marker(st.session_state.map_center, popup="Twoja lokalizacja",
                      icon=folium.Icon(color='blue', icon='info-sign')).add_to(m_preview)
        st_folium(m_preview, use_container_width=True, height=550, key="preview_map")

elif active_tab == "Projektant ręczny":
    show_manual_designer(bike_type)

elif active_tab == "🌍 Społeczność":
    st.header("🌍 Trasy dodane przez społeczność")
    db = SessionLocal()
    routes = db.query(SavedRoute).filter_by(visibility='public').all()

    for r in routes:
        avg_rating_query = db.query(func.avg(RouteReview.rating)).filter(RouteReview.route_id == r.id).scalar()
        avg_text = f"⭐ {round(avg_rating_query, 1)}/5" if avg_rating_query else "🔹 Brak ocen"

        with st.container(border=True):
            c1, c2, c3 = st.columns([2.5, 1, 1])
            try:
                r_data = json.loads(r.geojson_data)
                r_dist = r_data['features'][0]['properties'].get('length_km', '??')
            except:
                r_dist = "??"

            c1.write(f"**{r.name}** ({r_dist} km) | Autor: `{r.owner.username}` | **{avg_text}**")

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
                    r_dist = r_data['features'][0]['properties'].get('length_km', '??')
                except:
                    r_dist = "??"

                c1.write(f"**{r.name}** ({r_dist} km) [{r.visibility}]")

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