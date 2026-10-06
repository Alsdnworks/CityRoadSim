from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd

from .config import AppConfig, load_config
from .generator import TypeGrid, build_raw_network
from .io import save_gpkg
from .topology import build_topology
from .visualization import plot_network


@dataclass
class SimulationResult:
    type_grid: TypeGrid
    intersections: dict[tuple[int, int], dict[str, Any]]
    raw_links_gdf: gpd.GeoDataFrame
    links_gdf: gpd.GeoDataFrame
    nodes_gdf: gpd.GeoDataFrame
    output_path: Path | None


def run_simulation(config: AppConfig | str | Path, save: bool = True, visualize: bool | None = None) -> SimulationResult:
    """GUI/CLI에서 공통으로 호출하는 전체 시뮬레이션 파이프라인."""
    if not isinstance(config, AppConfig):
        config = load_config(config)

    type_grid, intersections, raw_links_gdf, intersection_areas = build_raw_network(config)
    links_gdf, nodes_gdf = build_topology(raw_links_gdf, intersection_areas, config)
    output_path = save_gpkg(links_gdf, nodes_gdf, config) if save else None

    should_visualize = config.visualization.enabled if visualize is None else visualize
    if should_visualize:
        plot_network(links_gdf, nodes_gdf, intersections, config)

    return SimulationResult(
        type_grid=type_grid,
        intersections=intersections,
        raw_links_gdf=raw_links_gdf,
        links_gdf=links_gdf,
        nodes_gdf=nodes_gdf,
        output_path=output_path,
    )
