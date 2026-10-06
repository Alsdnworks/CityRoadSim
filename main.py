import argparse
from pathlib import Path

from city_sim import load_config, run_simulation


def parse_args():
    parser = argparse.ArgumentParser(description="복잡교차로 도시 네트워크 시뮬레이터")
    parser.add_argument("--config", default="config.yaml", help="YAML 설정 파일 경로")
    parser.add_argument("--no-save", action="store_true", help="GPKG 저장 생략")
    parser.add_argument("--no-plot", action="store_true", help="시각화 생략")
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_config(Path(args.config))
    result = run_simulation(config, save=not args.no_save, visualize=False if args.no_plot else None)

    print("\nTYPE_GRID")
    for row in result.type_grid:
        print(row)

    print("\n========================================")
    print("Intersection count :", len(result.intersections))
    print("Raw link count     :", len(result.raw_links_gdf))
    print("Final link count   :", len(result.links_gdf))
    print("Node count         :", len(result.nodes_gdf))
    print("GPKG               :", result.output_path if result.output_path else "SKIPPED")
    print("========================================")


if __name__ == "__main__":
    main()
