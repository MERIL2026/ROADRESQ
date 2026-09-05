import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Coordinates:
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if not (-90.0 <= self.latitude <= 90.0):
            raise ValueError(f"Latitude must be between -90 and 90, got {self.latitude}")
        if not (-180.0 <= self.longitude <= 180.0):
            raise ValueError(f"Longitude must be between -180 and 180, got {self.longitude}")


def haversine_distance_km(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """
    Computes great-circle distance between two GPS coordinates in kilometers
    using the Haversine formula.
    """
    earth_radius_km = 6371.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    distance = earth_radius_km * c
    return round(distance, 2)


def is_within_radius_km(
    center_lat: float,
    center_lon: float,
    target_lat: float,
    target_lon: float,
    radius_km: float,
) -> bool:
    """Returns True if target coordinates are within radius_km from center."""
    dist = haversine_distance_km(center_lat, center_lon, target_lat, target_lon)
    return dist <= radius_km
