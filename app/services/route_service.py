import osmnx as ox
import networkx as nx
import os
from typing import List, Tuple
import math

ox.settings.use_cache = True  #aktywacja cache'a rejonowego
ox.settings.log_console = False # wyciszenie logów


# definicja funkcji heurystycznej - heurystyka jest potrzebna do A*
def dist_heuristic(u, v, G):    #u- wezel startowy ; v - wezel kocowy ; G - graf
    """
    Heurystyka odległości dla A*.
    Oblicza dystans w linii prostej między węzłami.
    """
    u_node = G.nodes[u]
    v_node = G.nodes[v]
    # Wykorzystujemy wbudowaną w OSMnx funkcję dystansu - zwrócona wartość jest szacowanym kosztem dotarcia do celu
    return ox.distance.euclidean(u_node['y'], u_node['x'], v_node['y'], v_node['x'])


# definicja funkcji budującej graf siatki dróg w promieniu dist

def get_graph(lat: float, lon: float, dist: float, network_type: str = "bike"):
    cache_dir = "data/graphs"
    if not os.path.exists(cache_dir): #deklaracja ścieżi do pamięci podręcznej
        os.makedirs(cache_dir, exist_ok=True)

    file_name = f"graph_{round(lat, 2)}_{round(lon, 2)}.graphml" #zapis pliku
    file_path = os.path.join(cache_dir, file_name)

    if os.path.exists(file_path): #czy taki wycinek mapy był już kiedyś pobrany ?
        return ox.load_graphml(file_path) #jeśli tak to wczytujemy błyskawicznie bez wykonywania zapytań sieciowych
    else:
        G = ox.graph_from_point((lat, lon), dist=dist, network_type=network_type, simplify=True)
        ox.save_graphml(G, file_path)
        return G


#funkcja szukająca ścieżi między dwoma punktami

def find_path_avoiding_edges(G, start_node, end_node, forbidden_edges):
    #kopia widoku grafu
    temp_G = G.copy()

    #pętla przegląda wszystkie krawędzie w tymczasowym grafie
    #krawędż która była użyta w poprzednim fragmencie pętli jest usuwana z tego grafu
    for u, v in list(temp_G.edges()):
        if (u, v) in forbidden_edges or (v, u) in forbidden_edges:
            if temp_G.has_edge(u, v):
                temp_G.remove_edge(u, v)

    try:
        #próba wyliczenia najkrótszej ścieżki A*
        return nx.astar_path(
            temp_G,
            start_node,
            end_node,
            heuristic=lambda u, v: dist_heuristic(u, v, temp_G),
            weight='length'
        )
    except (nx.NetworkXNoPath, KeyError):
        #jeśli graf podczas okrajania stał się niespójny to awaryjnie wyznaczamy algorytmem Dijkstry trasę na PEŁNYM oryginalnym grafie
        return nx.shortest_path(G, start_node, end_node, weight='length')

#funkcja spinająca 4 wierzchołki kwadratu w pętlę
def find_circular_route(G, corners):
    #mapowanie każdego podanego wierzchołka do najbliższego węzła
    corner_nodes = [ox.nearest_nodes(G, lon, lat) for lon, lat in corners]
    route_segments = []
    used_edges = set() #'system unikania'  - wykorzystane krawędzie

    for i in range(len(corner_nodes)):
        start, end = corner_nodes[i], corner_nodes[(i + 1) % len(corner_nodes)] # modulo zapewnia połączenie punktu 4 z 1 = pętla
        try:
            segment = find_path_avoiding_edges(G, start, end, used_edges)
            # Dodajemy segment bez ostatniego punktu (aby nie dublować punktów styku)
            route_segments.extend(segment[:-1])

            # Rejestrujemy krawędzie jako zużyte (w obu kierunkach)
            for u, v in zip(segment[:-1], segment[1:]):
                used_edges.add((u, v))
                used_edges.add((v, u))
        except Exception:
            return []   #awaria zwraca pustą listę

    if route_segments:  #jeśli lista segmentów nie jest pusta to doklejamy do niej pierwszy punkt trasy ( domknięcie pętli )
        route_segments.append(route_segments[0])
    return route_segments


#ta funkcja usuwa duplikaty pozycji stojących w miejscu obok siebie

def clean_line_coordinates(coordinates: List[List[float]]) -> List[List[float]]:
    if not coordinates: return []
    cleaned = [coordinates[0]]
    for i in range(1, len(coordinates)):
        if coordinates[i] != coordinates[i - 1]:
            cleaned.append(coordinates[i])
    return remove_backtracking(cleaned)

#funkcja usuwająca backtracking
def remove_backtracking(coordinates: List[List[float]]) -> List[List[float]]:
    if len(coordinates) < 3: return coordinates
    i, result = 0, []
    while i < len(coordinates):
        result.append(coordinates[i])
        found_backtrack = False
        # Sprawdzamy czy ścieżka nie wróciła do tego samego punktu w przeciągu 30 węzłów
        for j in range(i + 2, min(i + 30, len(coordinates))):
            if coordinates[i] == coordinates[j]:
                i, found_backtrack = j, True
                break
        if not found_backtrack:
            i += 1
    return result