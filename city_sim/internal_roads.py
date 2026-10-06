from __future__ import annotations

import random
from collections import defaultdict
from itertools import product
from typing import Any

from shapely.geometry import GeometryCollection, LineString, MultiPoint, Point
from shapely.ops import substring

from .config import AppConfig


TransitionRecord = dict[str, Any]


def _pair_key(a: str, b: str) -> frozenset[str]:
    return frozenset((a, b))


def _build_block_transition_sides(
    pair_to_transitions: dict[frozenset[str], list[TransitionRecord]],
    row: int,
    col: int,
) -> dict[str, list[TransitionRecord]]:
    """(row, col) Block의 N/E/S/W 경계를 구성하는 Transition 목록을 반환한다."""
    i00 = f"I_{row}_{col}"
    i10 = f"I_{row + 1}_{col}"
    i01 = f"I_{row}_{col + 1}"
    i11 = f"I_{row + 1}_{col + 1}"

    return {
        "S": pair_to_transitions.get(_pair_key(i00, i01), []),
        "N": pair_to_transitions.get(_pair_key(i10, i11), []),
        "W": pair_to_transitions.get(_pair_key(i00, i10), []),
        "E": pair_to_transitions.get(_pair_key(i01, i11), []),
    }


def _trim_transition(geometry: LineString, clearance: float) -> LineString | None:
    """Transition 양 끝 clearance를 제거한 안전 구간을 반환한다."""
    if geometry.length <= clearance * 2:
        return None
    trimmed = substring(geometry, clearance, geometry.length - clearance)
    if trimmed.geom_type != "LineString" or trimmed.is_empty:
        return None
    return trimmed


def _safe_axis_range(
    transitions_a: list[TransitionRecord],
    transitions_b: list[TransitionRecord],
    orientation: str,
    clearance: float,
) -> tuple[float, float] | None:
    """
    서로 마주보는 두 Block side에서 공통으로 사용할 수 있는 grid 축 범위를 계산한다.

    orientation='vertical'   -> S/N Transition의 공통 X 범위
    orientation='horizontal' -> W/E Transition의 공통 Y 범위
    """
    ranges: list[tuple[float, float]] = []
    for transition in transitions_a + transitions_b:
        trimmed = _trim_transition(transition["geometry"], clearance)
        if trimmed is None:
            continue
        minx, miny, maxx, maxy = trimmed.bounds
        ranges.append((minx, maxx) if orientation == "vertical" else (miny, maxy))

    if not ranges:
        return None

    lo = max(value[0] for value in ranges)
    hi = min(value[1] for value in ranges)
    if hi <= lo:
        return None
    return lo, hi


def _grid_coordinate(axis_range: tuple[float, float], slot: int, grid_size: int) -> float:
    """양 끝을 제외한 n개 등간격 slot의 실제 좌표를 반환한다."""
    lo, hi = axis_range
    fraction = (slot + 1) / (grid_size + 1)
    return lo + (hi - lo) * fraction


def _extract_points(geometry: Any) -> list[Point]:
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Point":
        return [geometry]
    if geometry.geom_type == "MultiPoint":
        return list(geometry.geoms)
    if geometry.geom_type == "GeometryCollection":
        return [part for part in geometry.geoms if part.geom_type == "Point"]
    return []


def _point_at_axis_coordinate(
    geometry: LineString,
    orientation: str,
    coordinate: float,
    clearance: float,
    tolerance: float,
) -> Point | None:
    """
    Transition과 수직/수평 probe를 교차시켜 정확히 같은 grid column/row에 endpoint를 만든다.
    따라서 internal_road는 사선이 아니라 축 정렬된 수직선/수평선이 된다.
    """
    minx, miny, maxx, maxy = geometry.bounds
    margin = max(geometry.length, 1.0) + 1.0

    if orientation == "vertical":
        probe = LineString([(coordinate, miny - margin), (coordinate, maxy + margin)])
    else:
        probe = LineString([(minx - margin, coordinate), (maxx + margin, coordinate)])

    points = _extract_points(geometry.intersection(probe))
    valid: list[Point] = []
    for point in points:
        distance = geometry.project(point)
        if distance + tolerance < clearance:
            continue
        if distance - tolerance > geometry.length - clearance:
            continue
        valid.append(point)

    if not valid:
        return None

    # Offset bend 등으로 같은 probe가 여러 점을 만날 경우 transition 중앙에 가까운 점을 사용한다.
    middle = geometry.length / 2
    return min(valid, key=lambda point: abs(geometry.project(point) - middle))


def _target_intersection_is_valid(
    candidate: LineString,
    transition: LineString,
    target_point: Point,
    tolerance: float,
) -> bool:
    """선택한 Transition과 지정 endpoint 한 점에서만 만나야 한다."""
    intersection = candidate.intersection(transition)
    return intersection.geom_type == "Point" and intersection.distance(target_point) <= tolerance


def _crosses_other_transition(
    candidate: LineString,
    transitions: list[TransitionRecord],
    allowed_ids: set[int],
) -> bool:
    """선택하지 않은 Transition과 접촉/교차하면 후보를 폐기한다."""
    for transition in transitions:
        if int(transition["raw_link_id"]) in allowed_ids:
            continue
        if candidate.intersects(transition["geometry"]):
            return True
    return False


def _overlaps_internal_road(
    candidate: LineString,
    internal_roads: list[dict[str, Any]],
    tolerance: float,
) -> bool:
    """internal_road끼리 Point 교차는 허용하되 선형 overlap/중복은 허용하지 않는다."""
    for road in internal_roads:
        intersection = candidate.intersection(road["geometry"])
        if intersection.is_empty:
            continue
        if intersection.geom_type in {"LineString", "MultiLineString"} and intersection.length > tolerance:
            return True
    return False


def _try_build_grid_road(
    orientation: str,
    slot: int,
    side_transitions: dict[str, list[TransitionRecord]],
    all_transitions: list[TransitionRecord],
    internal_roads: list[dict[str, Any]],
    config: AppConfig,
    rng: random.Random,
) -> tuple[LineString, TransitionRecord, TransitionRecord] | None:
    cfg = config.internal_road
    tolerance = config.topology.tolerance

    if orientation == "vertical":
        side_a, side_b = "S", "N"
    else:
        side_a, side_b = "W", "E"

    transitions_a = side_transitions[side_a]
    transitions_b = side_transitions[side_b]
    if not transitions_a or not transitions_b:
        return None

    axis_range = _safe_axis_range(
        transitions_a,
        transitions_b,
        orientation,
        cfg.transition_endpoint_clearance,
    )
    if axis_range is None:
        return None

    coordinate = _grid_coordinate(axis_range, slot, cfg.sampling_grid_size)
    pairs = list(product(transitions_a, transitions_b))
    rng.shuffle(pairs)

    for transition_a, transition_b in pairs:
        point_a = _point_at_axis_coordinate(
            transition_a["geometry"],
            orientation,
            coordinate,
            cfg.transition_endpoint_clearance,
            tolerance,
        )
        point_b = _point_at_axis_coordinate(
            transition_b["geometry"],
            orientation,
            coordinate,
            cfg.transition_endpoint_clearance,
            tolerance,
        )
        if point_a is None or point_b is None:
            continue

        candidate = LineString([(point_a.x, point_a.y), (point_b.x, point_b.y)])
        if candidate.length < cfg.min_length:
            continue

        if not _target_intersection_is_valid(candidate, transition_a["geometry"], point_a, tolerance):
            continue
        if not _target_intersection_is_valid(candidate, transition_b["geometry"], point_b, tolerance):
            continue

        allowed_ids = {int(transition_a["raw_link_id"]), int(transition_b["raw_link_id"])}
        if _crosses_other_transition(candidate, all_transitions, allowed_ids):
            continue
        if _overlaps_internal_road(candidate, internal_roads, tolerance):
            continue

        return candidate, transition_a, transition_b

    return None


def generate_internal_roads(
    raw_links: list[dict[str, Any]],
    next_raw_link_id: int,
    config: AppConfig,
) -> tuple[list[dict[str, Any]], int]:
    """
    Block 내부에 n×n 바둑판형 샘플 위치를 만들고 축 정렬 internal_road를 생성한다.

    - vertical:   S Transition ↔ N Transition, 동일 grid column(X) 연결
    - horizontal: W Transition ↔ E Transition, 동일 grid row(Y) 연결
    - vertical_weight / horizontal_weight로 방향 비율을 제어한다.
    - diagonal 연결은 생성하지 않는다.
    - 선택하지 않은 제3 Transition과 만나면 후보를 폐기한다.
    - internal_road끼리 Point 교차는 허용한다.
    """
    cfg = config.internal_road
    if not cfg.enabled or config.simulation.grid_size < 2:
        return [], next_raw_link_id

    transitions = [row for row in raw_links if row["link_type"] == "transition"]
    if not transitions:
        return [], next_raw_link_id

    rng = random.Random(f"{config.simulation.seed}:internal_road")
    n = config.simulation.grid_size
    internal_roads: list[dict[str, Any]] = []
    pair_to_transitions: dict[frozenset[str], list[TransitionRecord]] = defaultdict(list)
    for transition in transitions:
        pair_to_transitions[
            _pair_key(transition["from_intersection"], transition["to_intersection"])
        ].append(transition)

    for row in range(n - 1):
        for col in range(n - 1):
            if rng.random() > cfg.block_probability:
                continue

            block_id = f"B_{row}_{col}"
            side_transitions = _build_block_transition_sides(pair_to_transitions, row, col)

            slots = {
                "vertical": list(range(cfg.sampling_grid_size))
                if side_transitions["S"] and side_transitions["N"] and cfg.vertical_weight > 0
                else [],
                "horizontal": list(range(cfg.sampling_grid_size))
                if side_transitions["W"] and side_transitions["E"] and cfg.horizontal_weight > 0
                else [],
            }
            if not slots["vertical"] and not slots["horizontal"]:
                continue

            rng.shuffle(slots["vertical"])
            rng.shuffle(slots["horizontal"])
            target_count = rng.randint(cfg.min_count_per_block, cfg.max_count_per_block)
            created = 0
            attempts = 0

            while created < target_count and attempts < cfg.max_attempts:
                attempts += 1
                available_axes = [axis for axis, values in slots.items() if values]
                if not available_axes:
                    break

                weights = [
                    cfg.vertical_weight if axis == "vertical" else cfg.horizontal_weight
                    for axis in available_axes
                ]
                orientation = rng.choices(available_axes, weights=weights, k=1)[0]
                slot = slots[orientation].pop()

                result = _try_build_grid_road(
                    orientation,
                    slot,
                    side_transitions,
                    transitions,
                    internal_roads,
                    config,
                    rng,
                )
                if result is None:
                    continue

                candidate, transition_a, transition_b = result
                internal_roads.append({
                    "raw_link_id": next_raw_link_id,
                    "link_type": "internal_road",
                    "direction": "BOTH",
                    "intersection_id": None,
                    "from_intersection": None,
                    "to_intersection": None,
                    "intersection_type": None,
                    "rotation": None,
                    "block_id": block_id,
                    "transition_a_id": int(transition_a["raw_link_id"]),
                    "transition_b_id": int(transition_b["raw_link_id"]),
                    "internal_orientation": orientation,
                    "internal_grid_slot": slot,
                    "geometry": candidate,
                })
                next_raw_link_id += 1
                created += 1

    return internal_roads, next_raw_link_id
