"""검색 지역을 격자로 쪼개고 구글 맵 검색 URL을 만든다."""

from __future__ import annotations

import math
from dataclasses import dataclass
from urllib.parse import quote_plus

#: 위도 1도의 거리(km). 경도는 여기에 cos(위도)를 곱해 보정한다.
KM_PER_DEGREE = 111.32

#: 셀 크기를 특정할 수 없을 때 쓰는 줌.
DEFAULT_ZOOM = 14

MIN_ZOOM = 10
MAX_ZOOM = 17


@dataclass(frozen=True)
class Tile:
    lat: float
    lng: float
    zoom: int

    @property
    def label(self) -> str:
        """레코드 추적용 짧은 식별자."""
        return f"{self.lat:.5f},{self.lng:.5f},{self.zoom}z"


def zoom_for(cell_diameter_km: float) -> int:
    """셀이 뷰포트를 대략 채우는 줌 레벨. 1km -> 15, 2km -> 14, 4km -> 13."""
    if cell_diameter_km <= 0:
        return DEFAULT_ZOOM
    raw = round(15 - math.log2(cell_diameter_km))
    return max(MIN_ZOOM, min(MAX_ZOOM, raw))


def plan_tiles(
    center: tuple[float, float] | None, radius_km: float, n: int
) -> list[Tile | None]:
    """중심과 반경을 덮는 n x n 타일. center가 없으면 뷰포트 없는 단일 검색."""
    if center is None:
        return [None]
    if n < 1:
        raise ValueError("grid must be >= 1")

    lat, lng = center
    cell_km = (2 * radius_km) / n
    dlat = cell_km / KM_PER_DEGREE
    dlng = cell_km / (KM_PER_DEGREE * math.cos(math.radians(lat)))
    zoom = zoom_for(cell_km)
    offset = (n - 1) / 2

    return [
        Tile(lat + (row - offset) * dlat, lng + (col - offset) * dlng, zoom)
        for row in range(n)
        for col in range(n)
    ]


def search_url(keyword: str, tile: Tile | None, lang: str) -> str:
    """구글 맵 검색 URL. 타일이 있으면 뷰포트를 좌표로 고정한다."""
    query = quote_plus(keyword)
    if tile is None:
        return f"https://www.google.com/maps/search/{query}?hl={lang}"
    return (
        f"https://www.google.com/maps/search/{query}"
        f"/@{tile.lat:.6f},{tile.lng:.6f},{tile.zoom}z?hl={lang}"
    )
