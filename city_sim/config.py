from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class SimulationConfig:
    grid_size: int
    block_size: float
    center: float
    seed: int


@dataclass(frozen=True)
class IntersectionConfig:
    type_values: tuple[int, ...]
    type_weights: tuple[float, ...]
    rotations: tuple[int, ...]
    rotatable_types: tuple[int, ...]
    area_bounds: tuple[float, float, float, float]


@dataclass(frozen=True)
class TransitionConfig:
    near_offset: float
    bend_offset: float


@dataclass(frozen=True)
class InternalRoadConfig:
    enabled: bool
    block_probability: float
    min_count_per_block: int
    max_count_per_block: int
    sampling_grid_size: int
    vertical_weight: float
    horizontal_weight: float
    transition_endpoint_clearance: float
    min_length: float
    max_attempts: int


@dataclass(frozen=True)
class TopologyConfig:
    tolerance: float
    coordinate_precision: int


@dataclass(frozen=True)
class OutputConfig:
    gpkg: Path
    links_layer: str
    nodes_layer: str
    overwrite: bool


@dataclass(frozen=True)
class VisualizationConfig:
    enabled: bool
    show_window: bool
    show_node_id: bool
    figure_size: tuple[float, float]
    axis_padding_min: float
    axis_padding_max: float
    grid: bool
    intersection_colors: dict[int, str]
    transition_color: str
    internal_road_color: str
    node_color: str
    intersection_linewidth: float
    transition_linewidth: float
    internal_road_linewidth: float
    node_size: float
    node_label_offset: float
    node_label_fontsize: float
    intersection_label_fontsize: float


@dataclass(frozen=True)
class AppConfig:
    simulation: SimulationConfig
    intersection: IntersectionConfig
    transition: TransitionConfig
    internal_road: InternalRoadConfig
    topology: TopologyConfig
    output: OutputConfig
    visualization: VisualizationConfig
    config_path: Path


def _require(mapping: dict[str, Any], key: str, section: str) -> Any:
    if key not in mapping:
        raise ValueError(f"config.yaml: '{section}.{key}' 설정이 없습니다.")
    return mapping[key]


def _validate(config: AppConfig) -> None:
    sim = config.simulation
    inter = config.intersection
    topo = config.topology
    internal = config.internal_road

    if sim.grid_size <= 0:
        raise ValueError("simulation.grid_size는 1 이상이어야 합니다.")
    if sim.block_size <= 0:
        raise ValueError("simulation.block_size는 0보다 커야 합니다.")
    if len(inter.type_values) != len(inter.type_weights):
        raise ValueError("intersection.type_values와 type_weights 길이가 같아야 합니다.")
    if not inter.type_values:
        raise ValueError("intersection.type_values는 비어 있을 수 없습니다.")
    if any(weight < 0 for weight in inter.type_weights) or sum(inter.type_weights) <= 0:
        raise ValueError("intersection.type_weights는 음수가 아니며 합이 0보다 커야 합니다.")
    if any(rotation not in (0, 90, 180, 270) for rotation in inter.rotations):
        raise ValueError("intersection.rotations는 0/90/180/270만 지원합니다.")
    if any(int_type not in inter.type_values for int_type in inter.rotatable_types):
        raise ValueError("intersection.rotatable_types는 type_values에 포함되어야 합니다.")
    if len(inter.area_bounds) != 4:
        raise ValueError("intersection.area_bounds는 [minx, miny, maxx, maxy] 4개 값이어야 합니다.")
    minx, miny, maxx, maxy = inter.area_bounds
    if minx >= maxx or miny >= maxy:
        raise ValueError("intersection.area_bounds의 min 값은 max 값보다 작아야 합니다.")
    if not 0 <= internal.block_probability <= 1:
        raise ValueError("internal_road.block_probability은 0~1 범위여야 합니다.")
    if internal.min_count_per_block < 0:
        raise ValueError("internal_road.min_count_per_block은 0 이상이어야 합니다.")
    if internal.max_count_per_block < internal.min_count_per_block:
        raise ValueError("internal_road.max_count_per_block은 min_count_per_block 이상이어야 합니다.")
    if internal.sampling_grid_size <= 0:
        raise ValueError("internal_road.sampling_grid_size는 1 이상이어야 합니다.")
    if internal.vertical_weight < 0 or internal.horizontal_weight < 0:
        raise ValueError("internal_road vertical/horizontal weight는 0 이상이어야 합니다.")
    if internal.vertical_weight + internal.horizontal_weight <= 0:
        raise ValueError("internal_road vertical_weight + horizontal_weight 합은 0보다 커야 합니다.")
    if internal.transition_endpoint_clearance < 0:
        raise ValueError("internal_road.transition_endpoint_clearance는 0 이상이어야 합니다.")
    if internal.min_length <= 0:
        raise ValueError("internal_road.min_length는 0보다 커야 합니다.")
    if internal.max_attempts <= 0:
        raise ValueError("internal_road.max_attempts는 1 이상이어야 합니다.")
    if topo.tolerance <= 0:
        raise ValueError("topology.tolerance는 0보다 커야 합니다.")
    if topo.coordinate_precision < 0:
        raise ValueError("topology.coordinate_precision은 0 이상이어야 합니다.")


def load_config(config_path: str | Path) -> AppConfig:
    config_path = Path(config_path).expanduser().resolve()
    with config_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    simulation = _require(raw, "simulation", "root")
    intersection = _require(raw, "intersection", "root")
    transition = _require(raw, "transition", "root")
    internal_road = _require(raw, "internal_road", "root")
    topology = _require(raw, "topology", "root")
    output = _require(raw, "output", "root")
    visualization = _require(raw, "visualization", "root")

    gpkg = Path(_require(output, "gpkg", "output")).expanduser()
    if not gpkg.is_absolute():
        gpkg = (config_path.parent / gpkg).resolve()

    color_map = {
        int(key): str(value)
        for key, value in _require(visualization, "intersection_colors", "visualization").items()
    }

    config = AppConfig(
        simulation=SimulationConfig(
            grid_size=int(_require(simulation, "grid_size", "simulation")),
            block_size=float(_require(simulation, "block_size", "simulation")),
            center=float(_require(simulation, "center", "simulation")),
            seed=int(_require(simulation, "seed", "simulation")),
        ),
        intersection=IntersectionConfig(
            type_values=tuple(map(int, _require(intersection, "type_values", "intersection"))),
            type_weights=tuple(map(float, _require(intersection, "type_weights", "intersection"))),
            rotations=tuple(map(int, _require(intersection, "rotations", "intersection"))),
            rotatable_types=tuple(map(int, _require(intersection, "rotatable_types", "intersection"))),
            area_bounds=tuple(map(float, _require(intersection, "area_bounds", "intersection"))),
        ),
        transition=TransitionConfig(
            near_offset=float(_require(transition, "near_offset", "transition")),
            bend_offset=float(_require(transition, "bend_offset", "transition")),
        ),
        internal_road=InternalRoadConfig(
            enabled=bool(_require(internal_road, "enabled", "internal_road")),
            block_probability=float(_require(internal_road, "block_probability", "internal_road")),
            min_count_per_block=int(_require(internal_road, "min_count_per_block", "internal_road")),
            max_count_per_block=int(_require(internal_road, "max_count_per_block", "internal_road")),
            sampling_grid_size=int(_require(internal_road, "sampling_grid_size", "internal_road")),
            vertical_weight=float(_require(internal_road, "vertical_weight", "internal_road")),
            horizontal_weight=float(_require(internal_road, "horizontal_weight", "internal_road")),
            transition_endpoint_clearance=float(_require(internal_road, "transition_endpoint_clearance", "internal_road")),
            min_length=float(_require(internal_road, "min_length", "internal_road")),
            max_attempts=int(_require(internal_road, "max_attempts", "internal_road")),
        ),
        topology=TopologyConfig(
            tolerance=float(_require(topology, "tolerance", "topology")),
            coordinate_precision=int(_require(topology, "coordinate_precision", "topology")),
        ),
        output=OutputConfig(
            gpkg=gpkg,
            links_layer=str(_require(output, "links_layer", "output")),
            nodes_layer=str(_require(output, "nodes_layer", "output")),
            overwrite=bool(_require(output, "overwrite", "output")),
        ),
        visualization=VisualizationConfig(
            enabled=bool(_require(visualization, "enabled", "visualization")),
            show_window=bool(_require(visualization, "show_window", "visualization")),
            show_node_id=bool(_require(visualization, "show_node_id", "visualization")),
            figure_size=tuple(map(float, _require(visualization, "figure_size", "visualization"))),
            axis_padding_min=float(_require(visualization, "axis_padding_min", "visualization")),
            axis_padding_max=float(_require(visualization, "axis_padding_max", "visualization")),
            grid=bool(_require(visualization, "grid", "visualization")),
            intersection_colors=color_map,
            transition_color=str(_require(visualization, "transition_color", "visualization")),
            internal_road_color=str(_require(visualization, "internal_road_color", "visualization")),
            node_color=str(_require(visualization, "node_color", "visualization")),
            intersection_linewidth=float(_require(visualization, "intersection_linewidth", "visualization")),
            transition_linewidth=float(_require(visualization, "transition_linewidth", "visualization")),
            internal_road_linewidth=float(_require(visualization, "internal_road_linewidth", "visualization")),
            node_size=float(_require(visualization, "node_size", "visualization")),
            node_label_offset=float(_require(visualization, "node_label_offset", "visualization")),
            node_label_fontsize=float(_require(visualization, "node_label_fontsize", "visualization")),
            intersection_label_fontsize=float(_require(visualization, "intersection_label_fontsize", "visualization")),
        ),
        config_path=config_path,
    )
    _validate(config)
    return config
