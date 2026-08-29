import math

import pytest

from sourcing.grid import Tile, plan_tiles, search_url, zoom_for


def test_no_center_yields_single_viewportless_tile():
    assert plan_tiles(None, 10.0, 3) == [None]


def test_grid_produces_n_squared_tiles():
    tiles = plan_tiles((-6.2, 106.8), 10.0, 3)
    assert len(tiles) == 9
    assert all(isinstance(t, Tile) for t in tiles)


def test_odd_grid_center_tile_matches_center():
    tiles = plan_tiles((-6.2, 106.8), 10.0, 3)
    centers = [(round(t.lat, 6), round(t.lng, 6)) for t in tiles]
    assert (-6.2, 106.8) in centers


def test_longitude_spacing_widens_with_latitude():
    # cos(60도) = 0.5 이므로 경도 간격은 위도 간격의 정확히 2배여야 한다
    tiles = plan_tiles((60.0, 10.0), 10.0, 3)
    lats = sorted({round(t.lat, 9) for t in tiles})
    lngs = sorted({round(t.lng, 9) for t in tiles})
    dlat = lats[1] - lats[0]
    dlng = lngs[1] - lngs[0]
    assert dlng == pytest.approx(dlat * 2, rel=1e-6)


def test_tiles_cover_the_bounding_box():
    tiles = plan_tiles((0.0, 0.0), 10.0, 2)
    # 반경 10km -> 한 변 20km, 셀 10km. 셀 중심은 중심에서 +-5km 떨어진다.
    half_cell_deg = 5.0 / 111.32
    lats = sorted(tile.lat for tile in tiles)
    assert lats[0] == pytest.approx(-half_cell_deg)
    assert lats[-1] == pytest.approx(half_cell_deg)


def test_grid_size_must_be_positive():
    with pytest.raises(ValueError):
        plan_tiles((0.0, 0.0), 10.0, 0)


@pytest.mark.parametrize(
    "cell_km,expected",
    [(1.0, 15), (2.0, 14), (4.0, 13), (0.01, 17), (5000.0, 10), (0.0, 14)],
)
def test_zoom_for(cell_km, expected):
    assert zoom_for(cell_km) == expected


def test_search_url_without_tile_has_no_viewport():
    url = search_url("rumah sakit", None, "id")
    assert url == "https://www.google.com/maps/search/rumah+sakit?hl=id"


def test_search_url_with_tile_embeds_viewport():
    url = search_url("rumah sakit", Tile(-6.2, 106.8, 13), "id")
    assert url == (
        "https://www.google.com/maps/search/rumah+sakit/@-6.200000,106.800000,13z?hl=id"
    )


def test_search_url_escapes_keyword():
    assert "b%E1%BB%87nh+vi%E1%BB%87n" in search_url("bệnh viện", None, "vi")


def test_tile_label_is_stable():
    assert Tile(-6.2, 106.8, 13).label == "-6.20000,106.80000,13z"
