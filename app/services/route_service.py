import osmnx as ox
import networkx as nx
import os
from typing import List, Tuple

# --- LOGIKA POBIERANIA MAPY (KROK 3: CACHING) ---

def get_graph(lat: float, lon: float, dist: float, network_type: str = "bike"):
    """
    Pobiera graf z dysku (jeśli istnieje) lub z API OSMnx.
    To rozwiązuje problem długiego oczekiwania na trasę.
    """
    # Folder na mapy - upewnij się, że go stworzyłeś w projekcie!
    cache_dir = "data/graphs"
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir, exist_ok=True)

    # Tworzymy unikalną nazwę pliku dla lokalizacji (zaokrąglona do 2 miejsc po przecinku)
    file_name = f"graph_{round(lat, 2)}_{round(lon, 2)}.graphml"
    file_path = os.path.join(cache_dir, file_name)

    if os.path.exists(file_path):
        # Inżynierskie wczytywanie z pliku - trwa milisekundy
        return ox.load_graphml(file_path)
    else:
        # Pobieranie z internetu (tylko raz dla danego rejonu)
        G = ox.graph_from_point((lat, lon), dist=dist, network_type=network_type)
        ox.save_graphml(G, file_path)
        return G

# --- LOGIKA TRASOWANIA ---

def find_path_avoiding_edges(G, start_node, end_node, forbidden_edges):
    temp_G = G.copy()
    for u, v in list(temp_G.edges()):
        if (u, v) in forbidden_edges or (v, u) in forbidden_edges:
            temp_G.remove_edge(u, v)
    try:
        # Próba znalezienia alternatywnej drogi
        return nx.shortest_path(temp_G, start_node, end_node, weight='length')
    except nx.NetworkXNoPath:
        # Jeśli nie ma innej opcji, wróć do najkrótszej (nawet z powtórzeniem)
        return nx.shortest_path(G, start_node, end_node, weight='length')

def find_circular_route(G, corners):
    corner_nodes = [ox.nearest_nodes(G, lon, lat) for lon, lat in corners]
    route_segments = []
    used_edges = set()
    for i in range(len(corner_nodes)):
        start, end = corner_nodes[i], corner_nodes[(i + 1) % len(corner_nodes)]
        try:
            segment = find_path_avoiding_edges(G, start, end, used_edges)
            route_segments.extend(segment[:-1])
            for u, v in zip(segment[:-1], segment[1:]):
                used_edges.add((u, v))
                used_edges.add((v, u))
        except:
            return []
    if route_segments: route_segments.append(route_segments[0])
    return route_segments

# --- CZYSZCZENIE GEOMETRII ---

def clean_line_coordinates(coordinates: List[List[float]]) -> List[List[float]]:
    if not coordinates: return []
    cleaned = [coordinates[0]]
    for i in range(1, len(coordinates)):
        if coordinates[i] != coordinates[i - 1]: cleaned.append(coordinates[i])
    return remove_backtracking(cleaned)

def remove_backtracking(coordinates: List[List[float]]) -> List[List[float]]:
    if len(coordinates) < 3: return coordinates
    i, result = 0, []
    while i < len(coordinates):
        result.append(coordinates[i])
        found_backtrack = False
        for j in range(i + 2, min(i + 50, len(coordinates))):
            if coordinates[i] == coordinates[j]:
                i, found_backtrack = j, True
                break
        if not found_backtrack: i += 1
    return result