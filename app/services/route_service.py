import osmnx as ox
import networkx as nx
import os
from typing import List, Tuple
import math

# --- KONFIGURACJA OPTYMALIZACJI ---
ox.settings.use_cache = True
ox.settings.log_console = False


# --- HEURYSTYKA DLA ALGORYTMU A* ---
def dist_heuristic(u, v, G):
    """
    Heurystyka odległości dla A*.
    Oblicza dystans w linii prostej między węzłami.
    """
    u_node = G.nodes[u]
    v_node = G.nodes[v]
    # Wykorzystujemy wbudowaną w OSMnx funkcję dystansu (bardziej precyzyjna niż prosta Pitagoras)
    return ox.distance.euclidean(u_node['y'], u_node['x'], v_node['y'], v_node['x'])


# --- LOGIKA POBIERANIA MAPY ---

def get_graph(lat: float, lon: float, dist: float, network_type: str = "bike"):
    cache_dir = "data/graphs"
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir, exist_ok=True)

    file_name = f"graph_{round(lat, 2)}_{round(lon, 2)}.graphml"
    file_path = os.path.join(cache_dir, file_name)

    if os.path.exists(file_path):
        return ox.load_graphml(file_path)
    else:
        # [POPRAWKA] graph_from_point sam w sobie upraszcza graf,
        # więc nie wywołujemy już ręcznie ox.simplify_graph.
        G = ox.graph_from_point((lat, lon), dist=dist, network_type=network_type, simplify=True)
        ox.save_graphml(G, file_path)
        return G


# --- LOGIKA TRASOWANIA ---

def find_path_avoiding_edges(G, start_node, end_node, forbidden_edges):
    # Tworzymy kopię widoku grafu zamiast pełnej kopii (oszczędność pamięci)
    temp_G = G.copy()

    # Usuwamy krawędzie, które już odwiedziliśmy
    for u, v in list(temp_G.edges()):
        if (u, v) in forbidden_edges or (v, u) in forbidden_edges:
            if temp_G.has_edge(u, v):
                temp_G.remove_edge(u, v)

    try:
        # Próba szybkiego wyliczenia A*
        return nx.astar_path(
            temp_G,
            start_node,
            end_node,
            heuristic=lambda u, v: dist_heuristic(u, v, temp_G),
            weight='length'
        )
    except (nx.NetworkXNoPath, KeyError):
        # Jeśli A* zawiedzie w okrojonym grafie, wracamy do Dijkstry na pełnym grafie
        return nx.shortest_path(G, start_node, end_node, weight='length')


def find_circular_route(G, corners):
    # Znajdowanie węzłów najbliższych zadanym punktom kwadratu
    corner_nodes = [ox.nearest_nodes(G, lon, lat) for lon, lat in corners]
    route_segments = []
    used_edges = set()

    for i in range(len(corner_nodes)):
        start, end = corner_nodes[i], corner_nodes[(i + 1) % len(corner_nodes)]
        try:
            segment = find_path_avoiding_edges(G, start, end, used_edges)
            # Dodajemy segment bez ostatniego punktu (aby nie dublować punktów styku)
            route_segments.extend(segment[:-1])

            # Rejestrujemy krawędzie jako zużyte
            for u, v in zip(segment[:-1], segment[1:]):
                used_edges.add((u, v))
                used_edges.add((v, u))
        except Exception:
            return []

    if route_segments:
        route_segments.append(route_segments[0])  # Zamknięcie pętli
    return route_segments


# --- CZYSZCZENIE GEOMETRII ---

def clean_line_coordinates(coordinates: List[List[float]]) -> List[List[float]]:
    if not coordinates: return []
    cleaned = [coordinates[0]]
    for i in range(1, len(coordinates)):
        if coordinates[i] != coordinates[i - 1]:
            cleaned.append(coordinates[i])
    return remove_backtracking(cleaned)


def remove_backtracking(coordinates: List[List[float]]) -> List[List[float]]:
    if len(coordinates) < 3: return coordinates
    i, result = 0, []
    while i < len(coordinates):
        result.append(coordinates[i])
        found_backtrack = False
        # Sprawdzamy czy ścieżka nie wróciła do tego samego punktu w krótkim czasie
        for j in range(i + 2, min(i + 30, len(coordinates))):
            if coordinates[i] == coordinates[j]:
                i, found_backtrack = j, True
                break
        if not found_backtrack:
            i += 1
    return result