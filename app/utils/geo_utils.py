import math
from datetime import datetime
from typing import List, Tuple

#Ta funkcja odpowiada za wyznaczenie punktów zwrotnych dla algorytmu trasy pętlowej. Przelicza płaski kwadrat na zakrzywioną powierzchnię Ziemi.
def calculate_square_corners(start_lon: float, start_lat: float, side_length: float) -> List[Tuple[float, float]]:
    R = 6371000
    corners = []
    current_lon, current_lat = start_lon, start_lat
    bearings = [0, 90, 180, 270] #azymuty
    for bearing in bearings:   #Uruchamia pętlę dla każdego z 4 kierunków. W każdym kroku pętli dodaje aktualny punkt do listy wierzchołków kwadratu.
        corners.append((current_lon, current_lat))
        lat_rad, lon_rad = math.radians(current_lat), math.radians(current_lon)
        bearing_rad = math.radians(bearing)     #konwersja na radiany
        angular_distance = side_length / R  # odległość kątowa = długość boku / promień Ziemi
        new_lat_rad = math.asin(math.sin(lat_rad) * math.cos(angular_distance) +            #Wylicza nową szerokość geograficzną (w radianach) po przesunięciu się o określoną odległość w danym kierunku na sferze
                                math.cos(lat_rad) * math.sin(angular_distance) * math.cos(bearing_rad))
        new_lon_rad = lon_rad + math.atan2(math.sin(bearing_rad) * math.sin(angular_distance) * math.cos(lat_rad),  #Wylicza nową długość geograficzną (w radianach), uwzględniając zbieżność południków im bliżej bieguna się znajdujemy.
                                           math.cos(angular_distance) - math.sin(lat_rad) * math.sin(new_lat_rad))
        current_lon, current_lat = math.degrees(new_lon_rad), math.degrees(new_lat_rad)
    return corners  #lista czterech par współrzędnych

# tu dokonuje się zamiana: wewnętrzny format danych mapy (GeoJSON) na oficjalny standard plików nawigacji rowerowej (GPX). (format gpx to plik do pobrania i wczytania na apke mobilna)
def create_gpx(geojson_data):
    coords = geojson_data['features'][0]['geometry']['coordinates']
    now = datetime.now().isoformat()
    gpx = '<?xml version="1.0" encoding="UTF-8"?>\n'
    gpx += '<gpx version="1.1" creator="BikePlanner" xmlns="http://www.topografix.com/GPX/1/1">\n'
    gpx += f'  <metadata><time>{now}</time></metadata>\n'
    gpx += '  <trk>\n'
    gpx += '    <name>Trasa Projektant</name>\n'
    gpx += '    <trkseg>\n'
    for lon, lat in coords:
        gpx += f'      <trkpt lat="{lat}" lon="{lon}"></trkpt>\n'
    gpx += '    </trkseg>\n'
    gpx += '  </trk>\n'
    gpx += '</gpx>'
    return gpx

