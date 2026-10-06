from __future__ import annotations

import matplotlib.pyplot as plt

from .config import AppConfig


def plot_network(links_gdf, nodes_gdf, intersections, config: AppConfig, show: bool | None = None):
    """Matplotlib Figure를 반환한다. GUI에서는 show=False로 호출해 Figure를 임베드할 수 있다."""
    vis = config.visualization
    fig, ax = plt.subplots(figsize=vis.figure_size)

    for _, row in links_gdf.iterrows():
        geom = row.geometry
        x, y = geom.xy
        if row["link_type"] == "intersection":
            color = vis.intersection_colors.get(int(row["intersection_type"]), "black")
            linewidth = vis.intersection_linewidth
        else:
            color = vis.transition_color
            linewidth = vis.transition_linewidth

        ax.plot(x, y, color=color, linewidth=linewidth)
        coords = list(geom.coords)
        if len(coords) >= 2:
            ax.annotate(
                "", xy=coords[-1], xytext=coords[-2],
                arrowprops=dict(
                    facecolor=color, edgecolor=color, arrowstyle="-|>", lw=linewidth,
                    mutation_scale=8, shrinkA=0, shrinkB=0,
                ),
            )

    # NODE 표시
    if not nodes_gdf.empty:
        ax.scatter(nodes_gdf.geometry.x, nodes_gdf.geometry.y, s=vis.node_size, color=vis.node_color, zorder=10)
        if vis.show_node_id:
            for _, row in nodes_gdf.iterrows():
                ax.text(
                    row.geometry.x + vis.node_label_offset,
                    row.geometry.y + vis.node_label_offset,
                    f'N{row["node_id"]}', fontsize=vis.node_label_fontsize, zorder=11,
                )

    # Intersection ID / Type / Rotation
    block_size = config.simulation.block_size
    center = config.simulation.center
    for (row, col), data in intersections.items():
        cx, cy = col * block_size + center, row * block_size + center
        if data["intersection_type"] in config.intersection.rotatable_types:
            text = f'{data["intersection_id"]}\nT{data["intersection_type"]} R{data["rotation"]}'
        else:
            text = f'{data["intersection_id"]}\nT{data["intersection_type"]}'
        ax.text(
            cx, cy, text, fontsize=vis.intersection_label_fontsize, ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.15", facecolor="white", alpha=0.75), zorder=20,
        )

    n = config.simulation.grid_size
    ax.set_xlim(-vis.axis_padding_min, (n - 1) * block_size + vis.axis_padding_max)
    ax.set_ylim(-vis.axis_padding_min, (n - 1) * block_size + vis.axis_padding_max)
    ax.set_aspect("equal")
    if vis.grid:
        ax.grid(True, linestyle="--", alpha=0.2)
    plt.tight_layout()

    should_show = vis.show_window if show is None else show
    if should_show:
        plt.show()
    return fig, ax
