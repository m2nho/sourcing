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


# ── 셀 크기로 격자를 정한다 ──────────────────────────────────────
# 실측: 셀이 8km일 때 첫 타일이 260건 중 156건을 먹고 나머지 타일은 중복만
# 돌려줬다. 셀을 4km로 줄이니 같은 반경에서 218곳 -> 769곳이 됐다.
# grid 숫자를 사람이 계산하는 것보다 "한 번에 몇 km를 볼지"가 자연스럽다.


def test_grid_for_cell_splits_until_cells_are_small_enough():
    from sourcing.grid import grid_for_cell

    # 반경 12km = 한 변 24km. 셀 3km면 최소 8칸이 필요하다.
    assert grid_for_cell(radius_km=12, cell_km=3) == 8


def test_grid_for_cell_rounds_up_so_cells_never_exceed_the_target():
    from sourcing.grid import grid_for_cell

    # 한 변 20km를 3km 셀로 나누면 6.67 -> 7칸 (셀 2.86km)
    assert grid_for_cell(radius_km=10, cell_km=3) == 7


def test_small_area_still_gets_one_tile():
    from sourcing.grid import grid_for_cell

    assert grid_for_cell(radius_km=1, cell_km=3) == 1


def test_grid_for_cell_rejects_nonsense():
    from sourcing.grid import grid_for_cell

    with pytest.raises(ValueError):
        grid_for_cell(radius_km=10, cell_km=0)


def test_derived_grid_produces_cells_at_or_under_the_target():
    from sourcing.grid import grid_for_cell, plan_tiles, zoom_for

    radius, target = 12.0, 3.0
    n = grid_for_cell(radius, target)
    cell = (2 * radius) / n
    assert cell <= target
    # 그 셀 크기에 맞는 줌이 나와야 한다
    assert zoom_for(cell) >= zoom_for(target)
    assert len(plan_tiles((51.5, -0.14), radius, n)) == n * n
