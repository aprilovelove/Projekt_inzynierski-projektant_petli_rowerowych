import streamlit as st
from streamlit_folium import st_folium
import folium
import osmnx as ox
import networkx as nx


def show_manual_designer():
    st.markdown("### 🛠️ Projektant Ręczny")

    # 1. NIEZALEŻNE ŁADOWANIE MIASTA (jeśli grafu nie ma w pamięci)
    if 'G' not in st.session_state or st.session_state.G is None:
        st.warning("Brak załadowanego obszaru.")
        with st.expander("🌍 Załaduj mapę dla projektanta", expanded=True):
            city_name = st.text_input("Wpisz miasto lub adres (np. Chorzów):", key="manual_city_input")
            if st.button("Pobierz mapę"):
                with st.spinner("Pobieranie grafu..."):
                    # Pobieramy i zapisujemy do globalnego stanu, by obie zakładki go widziały
                    st.session_state.G = ox.graph_from_place(city_name, network_type='bike')
                    st.success("Mapa gotowa!")
                    st.rerun()
        return  # Nie pokazujemy mapy, dopóki nie ma grafu

    G = st.session_state.G

    # 2. INICJALIZACJA STANÓW RĘCZNYCH
    if 'm_nodes' not in st.session_state: st.session_state.m_nodes = []
    if 'm_coords' not in st.session_state: st.session_state.m_coords = []

    # Przyciski kontrolne
    c1, c2 = st.columns(2)
    with c1:
        if st.button("↩️ COFNIJ OSTATNI", use_container_width=True):
            if len(st.session_state.m_nodes) > 1:
                st.session_state.m_nodes.pop()
                # Przeliczamy trasę od nowa po usunięciu węzła (dla pewności)
                new_coords = []
                for i in range(len(st.session_state.m_nodes) - 1):
                    p = nx.shortest_path(G, st.session_state.m_nodes[i], st.session_state.m_nodes[i + 1],
                                         weight='length')
                    pts = [[G.nodes[n]['y'], G.nodes[n]['x']] for n in p]
                    new_coords.extend(pts if not new_coords else pts[1:])
                st.session_state.m_coords = new_coords
                st.rerun()
            elif len(st.session_state.m_nodes) == 1:
                st.session_state.m_nodes = []
                st.session_state.m_coords = []
                st.rerun()

    # 3. BUDOWA MAPY
    # Środek mapy (ostatni punkt ręczny lub środek grafu)
    center = st.session_state.m_coords[-1] if st.session_state.m_coords else [52.23, 21.01]
    m = folium.Map(location=center, zoom_start=14)

    # --- WIDMO (GHOST ROUTE) ---
    # Jeśli w sesji jest trasa z zakładki automatycznej (np. 'auto_coords'), rysujemy ją blado
    if 'auto_coords' in st.session_state and st.session_state.auto_coords:
        folium.PolyLine(
            st.session_state.auto_coords,
            color="gray",
            weight=4,
            opacity=0.3,
            dash_array='10, 10',
            tooltip="Trasa z automatu (podgląd)"
        ).add_to(m)

    # --- TRASA RĘCZNA ---
    if st.session_state.m_coords:
        folium.PolyLine(st.session_state.m_coords, color="#FF4B4B", weight=6).add_to(m)
        folium.Marker(st.session_state.m_coords[0], icon=folium.Icon(color='green')).add_to(m)
        folium.Marker(st.session_state.m_coords[-1], icon=folium.Icon(color='red')).add_to(m)

    # 4. OBSŁUGA KLIKNIĘĆ
    out = st_folium(m, width="100%", height=600, key="manual_designer_map")

    if out.get("last_clicked"):
        lat, lon = out["last_clicked"]["lat"], out["last_clicked"]["lng"]
        new_node = ox.nearest_nodes(G, X=lon, Y=lat)

        if not st.session_state.m_nodes or new_node != st.session_state.m_nodes[-1]:
            if st.session_state.m_nodes:
                try:
                    path = nx.shortest_path(G, st.session_state.m_nodes[-1], new_node, weight='length')
                    path_pts = [[G.nodes[n]['y'], G.nodes[n]['x']] for n in path]
                    if not st.session_state.m_coords:
                        st.session_state.m_coords.extend(path_pts)
                    else:
                        st.session_state.m_coords.extend(path_pts[1:])
                except nx.NetworkXNoPath:
                    st.error("Brak połączenia!")
                    return
            else:
                st.session_state.m_coords = [[G.nodes[new_node]['y'], G.nodes[new_node]['x']]]

            st.session_state.m_nodes.append(new_node)
            st.rerun()