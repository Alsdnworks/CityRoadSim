from __future__ import annotations

from typing import Any

import geopandas as gpd
from shapely.geometry import GeometryCollection, MultiPoint, Point
from shapely.ops import split, unary_union

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
    """실제 교차로 영역 안의 topological junction만 Node로 생성한다."""
    tolerance = config.topology.tolerance
    precision = config.topology.coordinate_precision
    intersection_area_union = unary_union([row["geometry"] for row in intersection_areas])
    node_points: dict[tuple[float, float], Point] = {}
    sindex = raw_links_gdf.sindex

    # 생성: interior×interior, endpoint×interior, interior×endpoint
    # 제외: endpoint×endpoint, LineString overlap
    for i, geom_a in enumerate(raw_links_gdf.geometry):
        candidate_indices = sindex.query(geom_a, predicate="intersects")
        for j in candidate_indices:
            if j <= i:
                continue

            geom_b = raw_links_gdf.geometry.iloc[j]
            intersection = geom_a.intersection(geom_b)
            if intersection.is_empty:
                continue

            for point in _extract_intersection_points(intersection):
                if not intersection_area_union.covers(point):
                    continue

                a_start, a_end = Point(geom_a.coords[0]), Point(geom_a.coords[-1])
                b_start, b_end = Point(geom_b.coords[0]), Point(geom_b.coords[-1])
                a_is_endpoint = point.distance(a_start) <= tolerance or point.distance(a_end) <= tolerance
                b_is_endpoint = point.distance(b_start) <= tolerance or point.distance(b_end) <= tolerance

                # endpoint × endpoint만 제외
                if a_is_endpoint and b_is_endpoint:
                    continue
                node_points[_point_key(point, precision)] = point

    node_records = []
    node_lookup: dict[tuple[float, float], int] = {}
    for node_id, (key, point) in enumerate(sorted(node_points.items())):
        intersection_id = None
        for int_row in intersection_areas:
            if int_row["geometry"].covers(point):
                intersection_id = int_row["intersection_id"]
                break
        node_lookup[key] = node_id
        node_records.append({"node_id": node_id, "intersection_id": intersection_id, "geometry": point})

    nodes_gdf = gpd.GeoDataFrame(node_records, columns=["node_id", "intersection_id", "geometry"], geometry="geometry", crs=None)
    return nodes_gdf, node_points, node_lookup


def split_links_at_nodes(raw_links_gdf: gpd.GeoDataFrame, node_points: dict, node_lookup: dict, config: AppConfig):
    """Node가 LineString 내부에 있을 때만 분할한다. Transition vertex는 분할하지 않는다."""
    tolerance = config.topology.tolerance
    precision = config.topology.coordinate_precision
    final_links = []
    final_link_id = 0

    for _, row in raw_links_gdf.iterrows():
        geom = row.geometry
        start_point, end_point = Point(geom.coords[0]), Point(geom.coords[-1])
        split_points = []

        for node_point in node_points.values():
            if geom.distance(node_point) > tolerance:
                continue
            if node_point.distance(start_point) > tolerance and node_point.distance(end_point) > tolerance:
                split_points.append(node_point)

        if split_points:
            result = split(geom, MultiPoint(split_points))
            parts = [part for part in result.geoms if part.geom_type == "LineString" and part.length > tolerance]
        else:
            parts = [geom]

        for part_no, part in enumerate(parts):
            part_start, part_end = Point(part.coords[0]), Point(part.coords[-1])
            final_links.append({
                "link_id": final_link_id,
                "parent_link_id": row["raw_link_id"],
                "part_no": part_no,
                "link_type": row["link_type"],
                "direction": row["direction"],
                "intersection_id": row["intersection_id"],
                "from_intersection": row["from_intersection"],
                "to_intersection": row["to_intersection"],
                "intersection_type": row["intersection_type"],
                "rotation": row["rotation"],
                "from_node": node_lookup.get(_point_key(part_start, precision)),
                "to_node": node_lookup.get(_point_key(part_end, precision)),
                "geometry": part,
            })
            final_link_id += 1

    return gpd.GeoDataFrame(final_links, geometry="geometry", crs=None)


def build_topology(raw_links_gdf: gpd.GeoDataFrame, intersection_areas: list[dict[str, Any]], config: AppConfig):
    nodes_gdf, node_points, node_lookup = detect_nodes(raw_links_gdf, intersection_areas, config)
    links_gdf = split_links_at_nodes(raw_links_gdf, node_points, node_lookup, config)
    return links_gdf, nodes_gdf
