from __future__ import annotations

from typing import Any

import geopandas as gpd
import math
import random
from shapely.geometry import GeometryCollection, Point, LineString
from shapely.ops import substring, unary_union

from .config import AppConfig


def _point_key(point: Point, precision: int) -> tuple[float, float]:
    return round(point.x, precision), round(point.y, precision)


def _extract_intersection_points(intersection) -> list[Point]:
    if intersection.geom_type == "Point":
        return [intersection]
    if intersection.geom_type == "MultiPoint":
        return list(intersection.geoms)
    if isinstance(intersection, GeometryCollection):
        return [geom for geom in intersection.geoms if geom.geom_type == "Point"]
    # LineString overlap 등은 Node 생성 대상에서 제외
    return []


def detect_nodes(raw_links_gdf: gpd.GeoDataFrame, intersection_areas: list[dict[str, Any]], config: AppConfig):
    """교차로 Junction과 internal_road가 포함된 외부 Junction을 Node로 생성한다.

    U-TURN은 maneuver link이므로 시작/종료 endpoint만 기존 도로와 연결한다.
    U-TURN interior가 다른 링크를 가로질러도 추가 Junction Node를 만들지 않는다.
    """
    tolerance = config.topology.tolerance
    precision = config.topology.coordinate_precision
    intersection_area_union = unary_union([row["geometry"] for row in intersection_areas])
    node_points: dict[tuple[float, float], Point] = {}
    node_types: dict[tuple[float, float], int] = {}
    sindex = raw_links_gdf.sindex

    # 생성: interior×interior, endpoint×interior, interior×endpoint
    # 제외: endpoint×endpoint, LineString overlap, U-TURN interior 교차
    for i, geom_a in enumerate(raw_links_gdf.geometry):
        candidate_indices = sindex.query(geom_a, predicate="intersects")
        for j in candidate_indices:
            if j <= i:
                continue

            row_a = raw_links_gdf.iloc[i]
            row_b = raw_links_gdf.iloc[j]
            geom_b = row_b.geometry
            intersection = geom_a.intersection(geom_b)
            if intersection.is_empty:
                continue

            for point in _extract_intersection_points(intersection):
                a_start, a_end = Point(geom_a.coords[0]), Point(geom_a.coords[-1])
                b_start, b_end = Point(geom_b.coords[0]), Point(geom_b.coords[-1])
                a_is_endpoint = point.distance(a_start) <= tolerance or point.distance(a_end) <= tolerance
                b_is_endpoint = point.distance(b_start) <= tolerance or point.distance(b_end) <= tolerance

                # U-TURN은 endpoint만 topology 연결점으로 허용한다.
                if row_a["link_type"] == "uturn" and not a_is_endpoint:
                    continue
                if row_b["link_type"] == "uturn" and not b_is_endpoint:
                    continue

                # 기존 교차로 Node는 intersection area 내부에서만 생성한다.
                # internal_road가 포함된 교차는 블록 내부/Transition 접속점에서도 Node로 인정한다.
                internal_related = (
                    row_a["link_type"] == "internal_road"
                    or row_b["link_type"] == "internal_road"
                )
                if not intersection_area_union.covers(point) and not internal_related:
                    continue

                # endpoint × endpoint만 제외
                if a_is_endpoint and b_is_endpoint:
                    continue
                key = _point_key(point, precision)
                # node_type 결정: intersection area 내부 노드는 type 1, 그 외 link_type 변화 지점은 type 2
                if intersection_area_union.covers(point):
                    ntype = 1
                elif row_a.get("link_type") != row_b.get("link_type"):
                    ntype = 2
                else:
                    ntype = 1
                node_points[key] = point
                node_types[key] = ntype

    node_records = []
    node_lookup: dict[tuple[float, float], int] = {}
    for node_id, (key, point) in enumerate(sorted(node_points.items())):
        intersection_id = None
        for int_row in intersection_areas:
            if int_row["geometry"].covers(point):
                intersection_id = int_row["intersection_id"]
                break
        node_type = node_types.get(key, 1)
        node_lookup[key] = node_id
        node_records.append({"node_id": node_id, "intersection_id": intersection_id, "node_type": node_type, "geometry": point})

    nodes_gdf = gpd.GeoDataFrame(node_records, columns=["node_id", "intersection_id", "node_type", "geometry"], geometry="geometry", crs=None)
    return nodes_gdf, node_points, node_lookup


def split_links_at_nodes(raw_links_gdf: gpd.GeoDataFrame, node_points: dict, node_lookup: dict, config: AppConfig):
    """Node의 LineString 투영거리 기준으로 분할한다. U-TURN은 endpoint만 연결하고 interior에서는 분할하지 않는다."""
    tolerance = config.topology.tolerance
    precision = config.topology.coordinate_precision
    final_links = []
    final_link_id = 0

    for _, row in raw_links_gdf.iterrows():
        geom = row.geometry
        geom_length = geom.length
        split_distances = []

        # U-TURN 자체는 maneuver link 하나로 유지한다.
        if row["link_type"] != "uturn":
            for node_point in node_points.values():
                if geom.distance(node_point) > tolerance:
                    continue

                distance = geom.project(node_point)
                if distance <= tolerance or geom_length - distance <= tolerance:
                    continue

                if not any(abs(distance - existing) <= tolerance for existing in split_distances):
                    split_distances.append(distance)

        split_distances.sort()
        boundaries = [0.0, *split_distances, geom_length]
        parts = []
        for start_distance, end_distance in zip(boundaries[:-1], boundaries[1:]):
            if end_distance - start_distance <= tolerance:
                continue
            part = substring(geom, start_distance, end_distance)
            if part.geom_type == "LineString" and part.length > tolerance:
                parts.append(part)

        for part_no, part in enumerate(parts):
            part_start, part_end = Point(part.coords[0]), Point(part.coords[-1])
            final_links.append({
                "link_id": final_link_id,
                "parent_link_id": row["raw_link_id"],
                "part_no": part_no,
                "link_type": row["link_type"],
                "direction": row["direction"],
                "flow_dir": row.get("flow_dir"),
                "road_pair_id": row.get("road_pair_id"),
                "K_CONTROL": row.get("K_CONTROL"),
                "LINK_K": row.get("LINK_K"),
                "LANE_NUM": row.get("LANE_NUM"),
                "intersection_id": row["intersection_id"],
                "from_intersection": row["from_intersection"],
                "to_intersection": row["to_intersection"],
                "intersection_type": row["intersection_type"],
                "rotation": row["rotation"],
                "block_id": row.get("block_id"),
                "transition_a_id": row.get("transition_a_id"),
                "transition_b_id": row.get("transition_b_id"),
                "internal_orientation": row.get("internal_orientation"),
                "internal_grid_slot": row.get("internal_grid_slot"),
                "from_link_id": row.get("from_link_id"),
                "to_link_id": row.get("to_link_id"),
                "turn_direction": row.get("turn_direction"),
                "uturn_position_ratio": row.get("uturn_position_ratio"),
                "from_node": node_lookup.get(_point_key(part_start, precision)),
                "to_node": node_lookup.get(_point_key(part_end, precision)),
                "geometry": part,
            })
            final_link_id += 1

    return gpd.GeoDataFrame(final_links, geometry="geometry", crs=None)


def build_topology(raw_links_gdf: gpd.GeoDataFrame, intersection_areas: list[dict[str, Any]], config: AppConfig):
    """Directed pair, U-TURN maneuver, Junction Node와 split link를 생성한다."""
    opposite = {"E": "W", "W": "E", "N": "S", "S": "N"}

    def _axis(direction: str) -> str:
        return "H" if direction in ("E", "W") else "V"

    def _k_from_flow(flow: str | None) -> int | None:
        if flow == "F":
            return 0
        if flow == "R":
            return 5
        return None

    def _geometry_direction(geom: LineString) -> str:
        x0, y0 = geom.coords[0]
        x1, y1 = geom.coords[-1]
        dx, dy = x1 - x0, y1 - y0
        if abs(dx) >= abs(dy):
            return "E" if dx >= 0 else "W"
        return "N" if dy >= 0 else "S"

    def _orient_geometry(geom: LineString, direction: str) -> LineString:
        if _geometry_direction(geom) == direction:
            return geom
        return LineString(list(geom.coords)[::-1])

    def _bezier_uturn(p0: Point, p3: Point, vx: float, vy: float, depth: float, samples: int = 12) -> LineString:
        # P0에서 현재 진행방향으로 진입하고, P3에서는 반대 진행방향으로 자연스럽게 빠져나오는 cubic Bezier.
        p1x, p1y = p0.x + vx * depth, p0.y + vy * depth
        p2x, p2y = p3.x + vx * depth, p3.y + vy * depth
        coords = []
        for i in range(samples + 1):
            t = i / samples
            omt = 1.0 - t
            x = omt**3 * p0.x + 3 * omt**2 * t * p1x + 3 * omt * t**2 * p2x + t**3 * p3.x
            y = omt**3 * p0.y + 3 * omt**2 * t * p1y + 3 * omt * t**2 * p2y + t**3 * p3.y
            coords.append((x, y))
        return LineString(coords)

    raw_rows = [dict(row) for _, row in raw_links_gdf.iterrows()]
    processed: list[dict[str, Any]] = []

    # 1) 모든 일반 링크를 directed record로 정규화한다.
    for row in raw_rows:
        dirv = row.get("direction")
        row["LINK_K"] = row.get("LINK_K") if row.get("LINK_K") is not None else 2
        row["LANE_NUM"] = row.get("LANE_NUM") if row.get("LANE_NUM") is not None else 1

        if dirv in ("E", "N"):
            row["geometry"] = _orient_geometry(row["geometry"], dirv)
            row["flow_dir"] = "F"
            row["K_CONTROL"] = _k_from_flow("F")
            processed.append(row)
            continue
        if dirv in ("W", "S"):
            row["geometry"] = _orient_geometry(row["geometry"], dirv)
            row["flow_dir"] = "R"
            row["K_CONTROL"] = _k_from_flow("R")
            processed.append(row)
            continue
        if dirv == "BOTH":
            orientation = row.get("internal_orientation")
            if orientation == "horizontal":
                forward_dir, reverse_dir = "E", "W"
            elif orientation == "vertical":
                forward_dir, reverse_dir = "N", "S"
            else:
                minx, miny, maxx, maxy = row["geometry"].bounds
                if (maxx - minx) >= (maxy - miny):
                    forward_dir, reverse_dir = "E", "W"
                else:
                    forward_dir, reverse_dir = "N", "S"

            for d in (forward_dir, reverse_dir):
                new_row = dict(row)
                new_row["direction"] = d
                new_row["geometry"] = _orient_geometry(row["geometry"], d)
                new_row["flow_dir"] = "F" if d in ("E", "N") else "R"
                new_row["K_CONTROL"] = _k_from_flow(new_row["flow_dir"])
                processed.append(new_row)
            continue

        row["flow_dir"] = None
        row["K_CONTROL"] = None
        processed.append(row)

    # 2) Link 종류별로 실제 반대방향 counterpart끼리만 road_pair_id를 공유한다.
    pair_groups: dict[tuple, list[dict[str, Any]]] = {}
    for r in processed:
        direction = r.get("direction")
        if direction not in opposite:
            continue

        link_type = r.get("link_type")
        axis = _axis(direction)
        if link_type == "intersection":
            key = ("intersection", r.get("intersection_id"), axis)
        elif link_type == "transition":
            endpoints = tuple(sorted((str(r.get("from_intersection")), str(r.get("to_intersection")))))
            key = ("transition", endpoints, axis)
        elif link_type == "internal_road":
            # BOTH에서 복제된 두 방향은 동일 raw_link_id를 공유한다.
            key = ("internal_road", r.get("raw_link_id"))
        else:
            key = (link_type, r.get("raw_link_id"), axis)
        pair_groups.setdefault(key, []).append(r)

    rp_counter = 1
    for rows in pair_groups.values():
        road_pair_id = f"R{rp_counter:04d}"
        rp_counter += 1
        for r in rows:
            r["road_pair_id"] = road_pair_id

    # 3) Transition은 '열린 side' 판정에만 사용한다.
    if getattr(config, "uturn", None) and config.uturn.enabled:
        out_map: dict[tuple[str, str], bool] = {}
        in_map: dict[tuple[str, str], bool] = {}
        out_point: dict[tuple[str, str], Point] = {}
        in_point: dict[tuple[str, str], Point] = {}

        for r in processed:
            if r.get("link_type") != "transition":
                continue
            
            direction = r.get("direction")
            if direction not in opposite:
                continue
            
            from_int = r.get("from_intersection")
            to_int = r.get("to_intersection")
            geom = r["geometry"]

            out_map[(from_int, direction)] = True
            in_map[(to_int, opposite[direction])] = True

            # 실제 intersection ↔ transition 접속점
            out_point[(from_int, direction)] = Point(geom.coords[0])
            in_point[(to_int, opposite[direction])] = Point(geom.coords[-1])

        side_open: dict[tuple[str, str], bool] = {}
        for key in set(out_map) | set(in_map):
            side_open[key] = out_map.get(key, False) and in_map.get(key, False)

        intersection_pairs: dict[str, list[dict[str, Any]]] = {}
        for r in processed:
            if r.get("link_type") != "intersection":
                continue
            rp = r.get("road_pair_id")
            if rp is not None:
                intersection_pairs.setdefault(rp, []).append(r)

        rng = random.Random(f"{config.simulation.seed}:uturn")
        prob = config.uturn.probability
        pos_ratio = config.uturn.position_ratio
        next_raw_link_id = max((r.get("raw_link_id", -1) for r in processed), default=-1) + 1

        for rp, rows in intersection_pairs.items():
            # E / W / N / S 모두 U-TURN 진입 후보
            directed_links = [
                r for r in rows
                if r.get("direction") in opposite
            ]

            if len(directed_links) < 2:
                continue
            
            for f in directed_links:
                inter = f.get("intersection_id")
                f_direction = f.get("direction")
                # Type 3에서는 S 방향 U-TURN 생성 금지
                # 현재 차량이 교차로에 진입한 side
                entry_side = opposite[f_direction]
                # Type 3의 closed side에는 U-TURN 생성 금지
                if str(f.get("intersection_type")) in ["2", "3"]:
                    rotation = int(f.get("rotation") or 0) % 360

                    closed_side = {
                        0:   "N",
                        90:  "W",
                        180: "S",
                        270: "E",
                    }[rotation]

                    if entry_side == closed_side:
                        continue

                if not side_open.get((inter, entry_side), False):
                    continue
                
                # 동일 pair의 반대 진행방향 링크
                r = next(
                    (
                        candidate for candidate in directed_links
                        if candidate is not f
                        and candidate.get("direction") == opposite[f_direction]
                    ),
                    None,
                )

                if r is None:
                    continue
                
                # -------------------------------------------------
                # T-junction closed side 방지
                # 실제 IN/OUT Transition과 연결된 side인지 검증
                # -------------------------------------------------
                in_pt = in_point.get((inter, entry_side))
                out_pt = out_point.get((inter, entry_side))

                if in_pt is None or out_pt is None:
                    continue
                
                f_start = Point(f["geometry"].coords[0])
                r_end = Point(r["geometry"].coords[-1])

                tol = config.topology.tolerance

                if f_start.distance(in_pt) > tol:
                    continue
                
                if r_end.distance(out_pt) > tol:
                    continue



                f_geom: LineString = f["geometry"]
                r_geom: LineString = r["geometry"]
                ut_dist = f_geom.length * pos_ratio
                p_in = f_geom.interpolate(ut_dist)
                p_out = r_geom.interpolate(r_geom.project(p_in))

                # 실제 local tangent에서 LEFT를 계산한다.
                eps = min(max(f_geom.length * 0.01, 1e-6), 0.1)
                p_prev = f_geom.interpolate(max(0.0, ut_dist - eps))
                p_next = f_geom.interpolate(min(f_geom.length, ut_dist + eps))
                dx, dy = p_next.x - p_prev.x, p_next.y - p_prev.y
                norm = math.hypot(dx, dy)
                if norm <= config.topology.tolerance:
                    continue
                vx, vy = dx / norm, dy / norm

                # p_out은 반드시 incoming 진행방향의 LEFT에 있어야 한다.
                tx, ty = p_out.x - p_in.x, p_out.y - p_in.y
                cross = vx * ty - vy * tx
                if cross <= config.topology.tolerance:
                    continue

                lane_separation = math.hypot(tx, ty)
                remaining = max(f_geom.length - ut_dist, config.topology.tolerance)
                depth = min(max(0.25, lane_separation * 0.75), max(0.25, remaining * 0.40))
                uturn_geom = _bezier_uturn(p_in, p_out, vx, vy, depth)

                processed.append({
                    "raw_link_id": next_raw_link_id,
                    "link_type": "uturn",
                    "direction": "UTURN",
                    "intersection_id": inter,
                    "from_intersection": inter,
                    "to_intersection": inter,
                    "intersection_type": f.get("intersection_type"),
                    "rotation": f.get("rotation"),
                    "block_id": None,
                    "transition_a_id": None,
                    "transition_b_id": None,
                    "internal_orientation": None,
                    "internal_grid_slot": None,
                    "geometry": uturn_geom,
                    "road_pair_id": rp,
                    "flow_dir": None,
                    "K_CONTROL": None,
                    "LINK_K": 8,
                    "LANE_NUM": 1,
                    "from_link_id": f.get("raw_link_id"),
                    "to_link_id": r.get("raw_link_id"),
                    "turn_direction": "LEFT",
                    "uturn_position_ratio": pos_ratio,
                })
                next_raw_link_id += 1

    processed_gdf = gpd.GeoDataFrame(processed, geometry="geometry", crs=raw_links_gdf.crs)
    nodes_gdf, node_points, node_lookup = detect_nodes(processed_gdf, intersection_areas, config)
    links_gdf = split_links_at_nodes(processed_gdf, node_points, node_lookup, config)
    return links_gdf, nodes_gdf
