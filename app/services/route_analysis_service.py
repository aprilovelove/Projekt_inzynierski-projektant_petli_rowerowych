import osmnx as ox
# --- NOWA LOGIKA HEURYSTYCZNA ---

# Progi punktowe dla rowerów (średni koszt "trudności" na odcinek)
BIKE_THRESHOLD = {
    "Szosowy/miejski": {"max_allowed": 2.5, "label": "Szosowy"},
    "Gravel(hybrydowy)": {"max_allowed": 6.0, "label": "Gravel"},
    "MTB(terenowy)": {"max_allowed": 10.0, "label": "MTB"}
}


def get_edge_difficulty(edge_data):
    """Ocenia trudność odcinka w skali 0-10 na podstawie wielu tagów."""
    score = 5  # Startujemy od środka, jeśli brak danych

    # 1. Sprawdzamy nawierzchnię (najważniejsza)
    surface = edge_data.get('surface', '')
    if any(s in ['asphalt', 'concrete', 'paved', 'paving_stones'] for s in
           ([surface] if isinstance(surface, str) else surface)):
        score = 0
    elif any(s in ['unpaved', 'gravel', 'ground', 'dirt', 'grass', 'sand'] for s in
             ([surface] if isinstance(surface, str) else surface)):
        score = 8

    # 2. Heurystyka po typie drogi (jeśli nawierzchnia nie jest jednoznaczna)
    highway = edge_data.get('highway', '')
    if any(h in ['primary', 'secondary', 'tertiary', 'residential'] for h in
           ([highway] if isinstance(highway, str) else highway)):
        score = min(score, 1)  # To raczej gładka droga
    if any(h in ['track', 'path'] for h in ([highway] if isinstance(highway, str) else highway)):
        score = max(score, 7)  # To raczej teren

    # 3. Tracktype (doprecyzowanie dróg leśnych)
    ttype = edge_data.get('tracktype', '')
    if ttype == 'grade1': score = min(score, 2)
    if ttype in ['grade4', 'grade5']: score = max(score, 9)

    return score

def analyze_route_compatibility(G, route_nodes, bike_type):
    if not bike_type or bike_type == "Brak":
        return None, None

    edges = ox.routing.route_to_gdf(G, route_nodes)

    total_score = 0
    valid_edges = 0

    for _, row in edges.iterrows():
        total_score += get_edge_difficulty(row)
        valid_edges += 1

    if valid_edges == 0:
        return "Brak danych do analizy", "gray"

    avg_score = total_score / valid_edges
    threshold = BIKE_THRESHOLD[bike_type]["max_allowed"]

    # Logika oceny
    if avg_score <= threshold:
        return f"🟢 Idealna (Trudność: {round(avg_score, 1)})", "green"
    elif avg_score <= threshold + 2.0:
        return f"🟡 Przejezdna (Trudność: {round(avg_score, 1)})", "orange"
    else:
        return f"🔴 Zbyt trudna (Trudność: {round(avg_score, 1)})", "red"