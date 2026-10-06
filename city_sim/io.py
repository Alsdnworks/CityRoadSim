from pathlib import Path

import geopandas as gpd

from .config import AppConfig


def save_gpkg(links_gdf: gpd.GeoDataFrame, nodes_gdf: gpd.GeoDataFrame, config: AppConfig) -> Path:
    """최종 links/nodes Layer를 하나의 GPKG에 저장한다."""
    output_path = config.output.gpkg
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists() and config.output.overwrite:
        output_path.unlink()
    elif output_path.exists():
        raise FileExistsError(f"출력 파일이 이미 존재합니다: {output_path}")

    links_gdf.to_file(output_path, layer=config.output.links_layer, driver="GPKG")
    nodes_gdf.to_file(output_path, layer=config.output.nodes_layer, driver="GPKG", mode="a")
    return output_path
