from __future__ import annotations

import random
from typing import Any

import geopandas as gpd
from shapely.affinity import rotate, translate
from shapely.geometry import LineString, box

from .config import AppConfig
from .templates import INTERSECTION_TYPES, PORT_ROTATION


TypeGrid = list[list[int | tuple[int, int]]]
IntersectionMap = dict[tuple[int, int], dict[str, Any]]


def generate_type_grid(config: AppConfig) -> TypeGrid:
    """SEED 기준으로 재현 가능한 TYPE_GRID를 생성한다."""
    rng = random.Random(config.simulation.seed)
    inter_cfg = config.intersection
    grid: TypeGrid = []

    for _row in range(config.simulation.grid_size):
        grid_row: list[int | tuple[int, int]] = []
        for _col in range(config.simulation.grid_size):
            int_type = rng.choices(inter_cfg.type_values, weights=inter_cfg.type_weights, k=1)[0]
            if int_type in inter_cfg.rotatable_types:
                grid_row.append((int_type, rng.choice(inter_cfg.rotations)))
            else:
                grid_row.append(int_type)
        grid.append(grid_row)
    return grid


def _decode_cell(cell: int | tuple[int, int] | list[int]) -> tuple[int, int]:
    if isinstance(cell, (tuple, list)):
        return int(cell[0]), int(cell[1])
    return int(cell), 0


def _transform_geometry(geometry, rotation: int, dx: float, dy: float, center: float):
    geometry = rotate(geometry, rotation, origin=(center, center), use_radians=False)
    return translate(geometry, xoff=dx, yoff=dy)


def _horizontal_transition(p0, p5, direction: str, near_offset: float, bend_offset: float) -> LineString:
    middle_y = (p0.y + p5.y) / 2
    sign = 1 if direction == "E" else -1
    return LineString([
        (p0.x, p0.y),
        (p0.x + sign * near_offset, p0.y),
        (p0.x + sign * bend_offset, middle_y),
        (p5.x - sign * bend_offset, middle_y),
        (p5.x - sign * near_offset, p5.y),
        (p5.x, p5.y),
    ])


def _vertical_transition(p0, p5, direction: str, near_offset: float, bend_offset: float) -> LineString:
    middle_x = (p0.x + p5.x) / 2
    sign = 1 if direction == "N" else -1
    return LineString([
        (p0.x, p0.y),
        (p0.x, p0.y + sign * near_offset),
        (middle_x, p0.y + sign * bend_offset),
        (middle_x, p5.y - sign * bend_offset),
        (p5.x, p5.y - sign * near_offset),
        (p5.x, p5.y),
    ])


def build_raw_network(config: AppConfig, type_grid: TypeGrid | None = None):
    """교차로 내부 링크와 교차로 사이 Transition을 생성한다."""
    if type_grid is None:
        type_grid = generate_type_grid(config)

    n = config.simulation.grid_size
    block_size = config.simulation.block_size
    center = config.simulation.center
    minx, miny, maxx, maxy = config.intersection.area_bounds
    near_offset = config.transition.near_offset
    bend_offset = config.transition.bend_offset

    intersections: IntersectionMap = {}
    raw_links: list[dict[str, Any]] = []
    intersection_areas: list[dict[str, Any]] = []
    raw_link_id = 0

    # =========================================================
    # 교차로 및 RAW LINK 생성
    # =========================================================
    for row in range(n):
        for col in range(n):
            int_type, rotation = _decode_cell(type_grid[row][col])
            if int_type not in INTERSECTION_TYPES:
                raise ValueError(f"지원하지 않는 intersection type: {int_type}")

            dx, dy = col * block_size, row * block_size
            intersection_id = f"I_{row}_{col}"
            template = INTERSECTION_TYPES[int_type]
            ports = {}

            # Port geometry 회전 + 이동
            for port_name, port_geom in template["ports"].items():
                geom = _transform_geometry(port_geom, rotation, dx, dy, center)
                side, io = port_name.split("_")
                new_side = PORT_ROTATION[rotation][side]
                ports[f"{new_side}_{io}"] = geom

            intersections[(row, col)] = {
                "intersection_id": intersection_id,
                "intersection_type": int_type,
                "rotation": rotation,
                "ports": ports,
            }

            # Node 생성은 이 영역 내부/경계에서만 허용
            intersection_areas.append({
                "intersection_id": intersection_id,
                "geometry": box(dx + minx, dy + miny, dx + maxx, dy + maxy),
            })

            # Intersection 내부 링크
            for base_geom in template["links"]:
                geom = _transform_geometry(base_geom, rotation, dx, dy, center)
                raw_links.append({
                    "raw_link_id": raw_link_id,
                    "link_type": "intersection",
                    "direction": None,
                    "intersection_id": intersection_id,
                    "from_intersection": intersection_id,
                    "to_intersection": intersection_id,
                    "intersection_type": int_type,
                    "rotation": rotation,
                    "geometry": geom,
                })
                raw_link_id += 1

    # =========================================================
    # 교차로 사이 Transition
    # Transition 전체 = LineString 1개
    # p1~p4는 geometry vertex일 뿐 NODE가 아님
    # =========================================================
    for row in range(n):
        for col in range(n):
            a = intersections[(row, col)]

            # RIGHT
            if col < n - 1:
                b = intersections[(row, col + 1)]
                if "E_OUT" in a["ports"] and "W_IN" in b["ports"]:
                    geom = _horizontal_transition(a["ports"]["E_OUT"], b["ports"]["W_IN"], "E", near_offset, bend_offset)
                    raw_links.append({
                        "raw_link_id": raw_link_id, "link_type": "transition", "direction": "E",
                        "intersection_id": None, "from_intersection": a["intersection_id"],
                        "to_intersection": b["intersection_id"], "intersection_type": None,
                        "rotation": None, "geometry": geom,
                    })
                    raw_link_id += 1

                if "W_OUT" in b["ports"] and "E_IN" in a["ports"]:
                    geom = _horizontal_transition(b["ports"]["W_OUT"], a["ports"]["E_IN"], "W", near_offset, bend_offset)
                    raw_links.append({
                        "raw_link_id": raw_link_id, "link_type": "transition", "direction": "W",
                        "intersection_id": None, "from_intersection": b["intersection_id"],
                        "to_intersection": a["intersection_id"], "intersection_type": None,
                        "rotation": None, "geometry": geom,
                    })
                    raw_link_id += 1

            # UP
            if row < n - 1:
                b = intersections[(row + 1, col)]
                if "N_OUT" in a["ports"] and "S_IN" in b["ports"]:
                    geom = _vertical_transition(a["ports"]["N_OUT"], b["ports"]["S_IN"], "N", near_offset, bend_offset)
                    raw_links.append({
                        "raw_link_id": raw_link_id, "link_type": "transition", "direction": "N",
                        "intersection_id": None, "from_intersection": a["intersection_id"],
                        "to_intersection": b["intersection_id"], "intersection_type": None,
                        "rotation": None, "geometry": geom,
                    })
                    raw_link_id += 1

                if "S_OUT" in b["ports"] and "N_IN" in a["ports"]:
                    geom = _vertical_transition(b["ports"]["S_OUT"], a["ports"]["N_IN"], "S", near_offset, bend_offset)
                    raw_links.append({
                        "raw_link_id": raw_link_id, "link_type": "transition", "direction": "S",
                        "intersection_id": None, "from_intersection": b["intersection_id"],
                        "to_intersection": a["intersection_id"], "intersection_type": None,
                        "rotation": None, "geometry": geom,
                    })
                    raw_link_id += 1

    raw_links_gdf = gpd.GeoDataFrame(raw_links, geometry="geometry", crs=None)
    return type_grid, intersections, raw_links_gdf, intersection_areas
