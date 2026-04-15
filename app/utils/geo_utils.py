import math
import qrcode
from io import BytesIO
from datetime import datetime
from typing import List, Tuple

def calculate_square_corners(start_lon: float, start_lat: float, side_length: float) -> List[Tuple[float, float]]:
    R = 6371000
    corners = []
    current_lon, current_lat = start_lon, start_lat
    bearings = [0, 90, 180, 270]
    for bearing in bearings:
        corners.append((current_lon, current_lat))
        lat_rad, lon_rad = math.radians(current_lat), math.radians(current_lon)
        bearing_rad = math.radians(bearing)
        angular_distance = side_length / R
        new_lat_rad = math.asin(math.sin(lat_rad) * math.cos(angular_distance) +
                                math.cos(lat_rad) * math.sin(angular_distance) * math.cos(bearing_rad))
        new_lon_rad = lon_rad + math.atan2(math.sin(bearing_rad) * math.sin(angular_distance) * math.cos(lat_rad),
                                           math.cos(angular_distance) - math.sin(lat_rad) * math.sin(new_lat_rad))
        current_lon, current_lat = math.degrees(new_lon_rad), math.degrees(new_lat_rad)
    return corners

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

def generate_qr_image(lat, lon):
    data = f"http://osmand.net/go?lat={lat}&lon={lon}&z=14"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()