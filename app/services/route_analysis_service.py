import osmnx as ox

BIKE_PROFILES = {
    "Szosowy/miejski": {
        "surface_paved": 0,
        "surface_unpaved": 5,
        "highway_smooth": 0,
        "highway_rough": 4,
        "track_good": 3,
        "track_bad": 5,
        "max_perfect": 1.2,
        "max_acceptable": 2.2
    },
    "Gravel (hybrydowy)": {
        "surface_paved": 0,
        "surface_unpaved": 1.5,
        "highway_smooth": 0,
        "highway_rough": 1.5,
        "track_good": 0.5,
        "track_bad": 4.5,
        "max_perfect": 1.8,
        "max_acceptable": 3.0
    },
    "MTB (terenowy)": {
        "surface_paved": 1.5,
        "surface_unpaved": 0,
        "highway_smooth": 1.5,
        "highway_rough": 0,
        "track_good": 0,
        "track_bad": 1.0,
        "max_perfect": 1.5,
        "max_acceptable": 3.5
    }
}


def get_edge_difficulty(edge_data, bike_type):
    """Ocenia trudność odcinka w skali 0-5 w zależności od profilu roweru."""
    profile = BIKE_PROFILES.get(bike_type)
    if not profile:
        return 2.5

    score = 2.5

    # 1. Heurystyka po typie drogi (highway) — TYLKO jako baza,
    #    zostanie nadpisana przez surface poniżej, jeśli ta informacja jest dostępna
    highway = edge_data.get('highway', '')
    highway_list = [highway] if isinstance(highway, str) else highway
    if any(h in ['primary', 'secondary', 'tertiary', 'residential'] for h in highway_list):
        score = profile["highway_smooth"]
    if any(h in ['track', 'path'] for h in highway_list):
        score = max(score, profile["highway_rough"])

    # 2. Analiza nawierzchni (surface) — NADRZĘDNA względem klasy drogi,
    #    bo to bezpośrednia, bardziej wiarygodna informacja o stanie drogi
    surface = edge_data.get('surface', '')
    surface_list = [surface] if isinstance(surface, str) else surface
    if any(s in ['asphalt', 'concrete', 'paved', 'paving_stones'] for s in surface_list):
        score = profile["surface_paved"]
    elif any(s in ['unpaved', 'gravel', 'ground', 'dirt', 'grass', 'sand'] for s in surface_list):
        score = profile["surface_unpaved"]

    # 3. Doprecyzowanie klasy drogi leśnej (tracktype)
    ttype = edge_data.get('tracktype', '')
    if ttype == 'grade1':
        score = profile["track_good"]
    if ttype in ['grade4', 'grade5']:
        score = profile["track_bad"]

    return score

def analyze_route_compatibility(G, route_nodes, bike_type):
    """
    Analizuje trasę pod kątem wybranego roweru (jeśli podano) i zawsze zwraca
    statystyki nawierzchniowe dla trasy.
    """
    edges = ox.routing.route_to_gdf(G, route_nodes)

    weighted_score_sum = 0
    total_route_length_m = 0
    valid_edges = 0

    paved_length = 0
    unpaved_length = 0
    unknown_length = 0

    # Flaga sprawdzająca czy użytkownik wybrał konkretny typ roweru
    has_bike_type = bike_type and bike_type != "Brak"

    for _, row in edges.iterrows():
        edge_len = row.get('length', 0)
        if edge_len <= 0:
            continue

        total_route_length_m += edge_len
        valid_edges += 1

        # Obliczanie trudności tylko, jeśli wybrano typ roweru
        if has_bike_type:
            difficulty = get_edge_difficulty(row, bike_type)
            weighted_score_sum += (difficulty * edge_len)

        # Agregacja nawierzchni (wykonywana ZAWSZE)
        surface = row.get('surface', '')
        if any(s in ['asphalt', 'concrete', 'paved', 'paving_stones'] for s in
               ([surface] if isinstance(surface, str) else surface)):
            paved_length += edge_len
        elif any(s in ['unpaved', 'gravel', 'ground', 'dirt', 'grass', 'sand'] for s in
                 ([surface] if isinstance(surface, str) else surface)):
            unpaved_length += edge_len
        else:
            highway = row.get('highway', '')
            if any(h in ['primary', 'secondary', 'tertiary', 'residential'] for h in
                   ([highway] if isinstance(highway, str) else highway)):
                paved_length += edge_len
            elif any(h in ['track', 'path'] for h in ([highway] if isinstance(highway, str) else highway)):
                unpaved_length += edge_len
            else:
                unknown_length += edge_len

    if valid_edges == 0 or total_route_length_m == 0:
        return "Brak danych do analizy", "gray", None

    # Obliczanie końcowych statystyk procentowych nawierzchni
    surface_stats = {
        "paved_pct": round((paved_length / total_route_length_m) * 100),
        "unpaved_pct": round((unpaved_length / total_route_length_m) * 100),
        "unknown_pct": round((unknown_length / total_route_length_m) * 100),
        "paved_km": round(paved_length / 1000, 1),
        "unpaved_km": round(unpaved_length / 1000, 1),
        "unknown_km": round(unknown_length / 1000, 1)
    }

    # Jeśli nie podano typu roweru, zwracamy tylko statystyki nawierzchni bez rekomendacji
    if not has_bike_type:
        return None, None, surface_stats

    # Wyznaczenie statusu dopasowania (jeśli wybrano typ roweru)
    avg_score = weighted_score_sum / total_route_length_m
    profile = BIKE_PROFILES[bike_type]

    if avg_score <= profile["max_perfect"]:
        status_text = f"🟢 Idealna dla: {bike_type.split('/')[0].split('(')[0]} (Indeks: {round(avg_score, 1)})"
        color = "green"
    elif avg_score <= profile["max_acceptable"]:
        status_text = f"🟡 Przejezdna (Indeks: {round(avg_score, 1)})"
        color = "orange"
    else:
        status_text = f"🔴 Zbyt trudna / Niekompatybilna (Indeks: {round(avg_score, 1)})"
        color = "red"

    return status_text, color, surface_stats