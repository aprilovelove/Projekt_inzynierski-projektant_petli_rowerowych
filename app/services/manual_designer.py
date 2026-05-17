import streamlit as st
import folium
from streamlit_folium import st_folium
import osmnx as ox
import networkx as nx
import json
import requests
from datetime import datetime
from app.utils.geo_utils import create_gpx
from app.db.database import SessionLocal, SavedRoute, User

# Słownik ratunkowy (Hardcoded Fallback) na wypadek awarii sieci
LOCAL_POIS = {
    "lidl gałeczki": (50.2831, 18.9612, "Lidl, Gałeczki, Chorzów"),
    "teatr rozrywki": (50.2974, 18.9538, "Teatr Rozrywki, Chorzów"),
    "planetarium śląskie": (50.2917, 18.9922, "Planetarium Śląskie, Park Śląski"),
    "auchan": (50.2712, 18.9214, "Auchan, DTŚ, Chorzów"),
    "park śląski": (50.2891, 18.9734, "Park Śląski, Chorzów"),
    "rynek chorzów": (50.2977, 18.9515, "Rynek, Chorzów"),
    "silesia city center": (50.2694, 19.0041, "Silesia City Center, Katowice")
}


def alternative_geocode(query: str):
    """
    Bezpieczna alternatywa dla Nominatim korzystająca z API Photon (Komoot).
    """
    q_clean = query.lower().strip()

    # 1. Sprawdzenie w lokalnym słowniku ratunkowym
    for key, coords in LOCAL_POIS.items():
        if key in q_clean:
            return coords[0], coords[1], coords[2]

    # 2. Zapytanie do API Photon
    try:
        url = f"https://photon.komoot.io/api/?q={requests.utils.quote(query)}&bias_ltrb=18.85,50.22,19.05,50.35&limit=1"
        response = requests.get(url, timeout=3)
        if response.status_code == 200:
            data = response.json()
            if data and data.get("features"):
                feat = data["features"][0]
                lon, lat = feat["geometry"]["coordinates"]
                name = feat["properties"].get("name", query)
                city = feat["properties"].get("city", "Śląsk")
                street = feat["properties"].get("street", "")
                full_name = f"{name}, {street} ({city})" if street else f"{name} ({city})"
                return lat, lon, full_name
    except Exception:
        pass

    return None


def show_manual_designer():
    st.header("📍 Projektant ręczny (Wyszukiwarka Punktów)")
    st.write("Wpisz lokalizacje, zweryfikuj podgląd tekstowy, a następnie nanieś je i połącz w trasę!")

    # Inicjalizacja stanu sesji
    if 'manual_points' not in st.session_state:
        st.session_state.manual_points = ["", ""]
    if 'manual_geojson' not in st.session_state:
        st.session_state.manual_geojson = None
    if 'manual_route_name' not in st.session_state:
        st.session_state.manual_route_name = "Moja Trasa Ręczna"
    if 'confirmed_coords' not in st.session_state:
        st.session_state.confirmed_coords = []

    # Dynamiczne dodawanie/usuwanie pól
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("➕ Dodaj kolejny punkt pośredni", use_container_width=True):
            st.session_state.manual_points.append("")
            st.rerun()
    with col_btn2:
        if len(st.session_state.manual_points) > 2:
            if st.button("❌ Usuń ostatni punkt", use_container_width=True):
                st.session_state.manual_points.pop()
                st.session_state.manual_geojson = None
                st.rerun()

    st.subheader("🗺️ Etapy Twojej trasy:")

    # Słownik do przechowywania współrzędnych wygenerowanych na żywo podczas renderowania pól
    live_coords = []
    all_fields_resolved = True

    # Renderowanie pól tekstowych wraz ze sprawdzaniem na żywo
    for i in range(len(st.session_state.manual_points)):
        if i == 0:
            label = "🏁 Punkt Startowy"
        elif i == len(st.session_state.manual_points) - 1:
            label = "🏁 Punkt Końcowy (Meta)"
        else:
            label = f"📍 Punkt pośredni {i}"

        val = st.text_input(label, value=st.session_state.manual_points[i], key=f"manual_pt_{i}",
                            placeholder="np. Lidl Gałeczki, Chorzów")
        st.session_state.manual_points[i] = val

        # MODYFIKACJA 1: Sprawdzanie i komunikacik na żywo pod każdym polem
        if val.strip():
            res = alternative_geocode(val)
            if res:
                live_coords.append(res)
                st.caption(f"🟩 **Znaleziono:** `{res[2]}` (Lat: {round(res[0], 4)}, Lon: {round(res[1], 4)})")
            else:
                all_fields_resolved = False
                st.caption("⚠️ **Status:** Nie znaleziono punktu. Dopisz miasto lub zmień nazwę.")
        else:
            all_fields_resolved = False
            st.caption("ℹ️ **Status:** Oczekiwanie na wpisanie lokalizacji...")

    st.divider()

    # KROK 1: Naniesienie punktów (teraz po prostu przepisuje gotowe dane z widoku live)
    if st.button("🔍 1. Zatwierdź i nanieś punkty na mapę", use_container_width=True, type="secondary"):
        if not all_fields_resolved or len(live_coords) != len(st.session_state.manual_points):
            st.error("Nie wszystkie punkty zostały poprawnie odnalezione lub któreś pole jest puste!")
        else:
            st.session_state.confirmed_coords = live_coords
            st.success(f"Pomyślnie narysowano punkty ({len(live_coords)}) na mapie podglądu!")

    # KROK 2: Budowanie i nawlekanie trasy na osmnx
    if st.button("🪡 2. Połącz punkty i wyznacz trasę rowerową", type="primary", use_container_width=True):
        coords_list = st.session_state.confirmed_coords

        if len(coords_list) < 2:
            st.error("Najpierw musisz poprawnie zatwierdzić i nanieść punkty na mapę przyciskiem (Krok 1)!")
        else:
            with st.spinner("Trwa kalkulacja i dopasowanie trasy do sieci rowerowej..."):
                try:
                    full_route_coords = []
                    total_length_m = 0

                    center_lat = sum(c[0] for c in coords_list) / len(coords_list)
                    center_lon = sum(c[1] for c in coords_list) / len(coords_list)

                    G_manual = ox.graph_from_point((center_lat, center_lon), dist=8000, network_type="bike")
                    nodes_df, _ = ox.graph_to_gdfs(G_manual)

                    for idx in range(len(coords_list) - 1):
                        orig_coords = coords_list[idx]
                        dest_coords = coords_list[idx + 1]

                        orig_node = ox.nearest_nodes(G_manual, X=orig_coords[1], Y=orig_coords[0])
                        dest_node = ox.nearest_nodes(G_manual, X=dest_coords[1], Y=dest_coords[0])

                        sub_route = nx.shortest_path(G_manual, orig_node, dest_node, weight='length')

                        for u, v in zip(sub_route[:-1], sub_route[1:]):
                            edge_data = G_manual.get_edge_data(u, v)
                            if edge_data:
                                total_length_m += edge_data[0].get('length', 0)

                        for node in sub_route:
                            y, x = nodes_df.loc[node].y, nodes_df.loc[node].x
                            if not full_route_coords or full_route_coords[-1] != [x, y]:
                                full_route_coords.append([x, y])

                    st.session_state.manual_geojson = {
                        "type": "FeatureCollection",
                        "features": [{
                            "type": "Feature",
                            "geometry": {"type": "LineString", "coordinates": full_route_coords},
                            "properties": {"length_km": round(total_length_m / 1000, 2)}
                        }]
                    }
                    st.toast("Trasa wyznaczona!", icon="🚴")
                except Exception as e:
                    st.error(f"Błąd sieci rowerowej: {e}. Spróbuj skorygować punkty pośrednie.")

    # --- MAPA ---
    coords_list = st.session_state.confirmed_coords
    map_center = [coords_list[0][0], coords_list[0][1]] if coords_list else [50.2859, 18.9549]

    m_manual = folium.Map(
        location=map_center,
        zoom_start=14,
        tiles='https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}',
        attr='Google Maps'
    )

    if st.session_state.manual_geojson:
        folium.GeoJson(st.session_state.manual_geojson,
                       style_function=lambda x: {'color': '#3498db', 'weight': 6}).add_to(m_manual)
        dist_km = st.session_state.manual_geojson['features'][0]['properties']['length_km']
        st.metric("Całkowita długość zaprojektowanej trasy", f"{dist_km} km")

    for i, c in enumerate(coords_list):
        color = 'green' if i == 0 else 'red' if i == len(st.session_state.manual_points) - 1 else 'blue'
        folium.Marker(
            [c[0], c[1]],
            popup=f"Etap {i + 1}: {c[2]}",
            icon=folium.Icon(color=color, icon='info-sign')
        ).add_to(m_manual)

    st_folium(m_manual, use_container_width=True, height=500, key="manual_designer_map")

    # --- EKSPORT (Z MODYFIKACJĄ O EMAIL) ---
    if st.session_state.manual_geojson:
        st.divider()
        st.subheader("📲 Opcje zapisu i wysyłki trasy ręcznej")

        active_geojson = st.session_state.manual_geojson
        current_gpx = create_gpx(active_geojson)
        ts = datetime.now().strftime("%H%M%S")

        col_down1, col_down2, col_down3 = st.columns([1, 1, 1])

        # Kolumna 1: Pobieranie lokalne pliku GPX
        with col_down1:
            st.download_button(
                label="🗺️ POBIERZ PLIK GPX",
                data=current_gpx,
                file_name=f"trasa_reczna_{ts}.gpx",
                mime="application/gpx+xml",
                use_container_width=True,
                key=f"dl_manual_{ts}"
            )

        # MODYFIKACJA 2: Kolumna 2 - Wysyłka trasy ręcznej na e-mail użytkownika
        with col_down2:
            if st.button("📧 WYŚLIJ NA MÓJ E-MAIL", use_container_width=True, key="email_manual_btn"):
                if st.session_state.user:
                    db = SessionLocal()
                    try:
                        curr_user = db.get(User, st.session_state.user['id'])
                        target_email = curr_user.email if curr_user else None
                    except Exception as e:
                        st.error(f"Błąd bazy danych przy pobieraniu maila: {e}")
                        target_email = None
                    finally:
                        db.close()

                    if target_email:
                        with st.spinner("Wysyłanie e-maila ze śladem GPX..."):
                            from app.services.email_service import send_custom_email
                            success = send_custom_email(
                                recipient_email=target_email.strip(),
                                subject="Zaprojektowana trasa ręczna - GPX",
                                body=f"Cześć! W załączniku przesyłamy ręcznie zaprojektowaną trasę rowerową ({dist_km} km).",
                                attachment_data=current_gpx,
                                attachment_name=f"trasa_reczna_{ts}.gpx"
                            )
                            if success:
                                st.toast("E-mail z trasą został wysłany!", icon="📬")
                            else:
                                st.error("Błąd serwera wysyłkowego. Spróbuj później.")
                    else:
                        st.error("Nie znaleziono adresu e-mail przypisanego do Twojego profilu.")
                else:
                    st.error("Musisz być zalogowany, aby wysłać trasę na e-mail.")

        # Kolumna 3: Zapis w bazie danych
        with col_down3:
            if st.session_state.user:
                with st.popover("💾 Zapisz w profilu", use_container_width=True):
                    r_name = st.text_input("Nazwa trasy", value=st.session_state.manual_route_name)
                    r_vis = st.selectbox("Widoczność trasy", ["private", "public"], key="manual_vis")
                    if st.button("Potwierdź Zapis", use_container_width=True):
                        db = SessionLocal()
                        try:
                            new_r = SavedRoute(
                                user_id=st.session_state.user['id'],
                                name=r_name,
                                geojson_data=json.dumps(active_geojson),
                                visibility=r_vis
                            )
                            db.add(new_r)
                            db.commit()
                            st.success("Zapisano!")
                        except Exception as e:
                            st.error(f"Błąd zapisu: {e}")
                        finally:
                            db.close()
            else:
                st.button("💾 Zaloguj się by zapisać", disabled=True, use_container_width=True)