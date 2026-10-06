import os
import random
from pathlib import Path

import matplotlib.pyplot as plt
import geopandas as gpd

from shapely.geometry import (
    Point,
    LineString,
    MultiPoint,
    GeometryCollection,
    box
)
from shapely.affinity import rotate, translate
from shapely.ops import split, unary_union


# =========================================================
# 설정
# =========================================================
N = 16
BLOCK_SIZE = 32
CENTER = 2.5
SEED = 42
OUTPUT_GPKG = r"C:\Users\alsdn\OneDrive\바탕 화면\DUMP\JCT_MPER\city_sim.gpkg"
TYPE_VALUES = [1, 2, 3]
TYPE_WEIGHTS = [0.33, 0.33, 0.34]
ROTATIONS = [0, 90, 180, 270]
SHOW_NODE_ID = False

random.seed(SEED)


# =========================================================
# 교차로 템플릿
#
# 모든 geometry는 Shapely geometry
#
# T1 : 일반 교차로
# T2 : Offset 교차로
# T3 : 기본 북쪽 폐쇄 T
# =========================================================
INTERSECTION_TYPES = {
    1: {
        "links": [
            LineString([(1, 2), (4, 2)]),
            LineString([(4, 3), (1, 3)]),
            LineString([(3, 1), (3, 4)]),
            LineString([(2, 4), (2, 1)]),
        ],
        "ports": {
            "W_IN":  Point(1, 2),
            "W_OUT": Point(1, 3),
            "E_IN":  Point(4, 3),
            "E_OUT": Point(4, 2),
            "S_IN":  Point(3, 1),
            "S_OUT": Point(2, 1),
            "N_IN":  Point(2, 4),
            "N_OUT": Point(3, 4),
        }
    },

    2: {
        "links": [
            LineString([(1, 3), (4, 3)]),
            LineString([(4, 4), (1, 4)]),
            LineString([(2, 4), (2, 1)]),
            LineString([(3, 1), (3, 4)]),
        ],
        "ports": {
            "W_IN":  Point(1, 3),
            "W_OUT": Point(1, 4),
            "E_IN":  Point(4, 4),
            "E_OUT": Point(4, 3),
            "S_IN":  Point(3, 1),
            "S_OUT": Point(2, 1),
            "N_IN":  Point(2, 4),
            "N_OUT": Point(3, 4),
        }
    },

    3: {
        "links": [
            LineString([(1, 3), (4, 3)]),
            LineString([(4, 4), (1, 4)]),
            LineString([(2, 3), (2, 1)]),
            LineString([(3, 1), (3, 3)]),
        ],
        "ports": {
            "W_IN":  Point(1, 3),
            "W_OUT": Point(1, 4),
            "E_IN":  Point(4, 4),
            "E_OUT": Point(4, 3),
            "S_IN":  Point(3, 1),
            "S_OUT": Point(2, 1),
        }
    }
}


# =========================================================
# 회전 후 Port 방향 변환
# 반시계 방향
# =========================================================
PORT_ROTATION = {
    0: {
        "W": "W",
        "E": "E",
        "N": "N",
        "S": "S"
    },

    90: {
        "W": "S",
        "S": "E",
        "E": "N",
        "N": "W"
    },

    180: {
        "W": "E",
        "E": "W",
        "N": "S",
        "S": "N"
    },

    270: {
        "W": "N",
        "N": "E",
        "E": "S",
        "S": "W"
    }
}


# =========================================================
# TYPE_GRID 랜덤 생성
#
# T1 : 회전 없음
# T2 : 랜덤 회전
# T3 : 랜덤 회전
# =========================================================
TYPE_GRID = []

for row in range(N):

    grid_row = []

    for col in range(N):

        int_type = random.choices(
            TYPE_VALUES,
            weights=TYPE_WEIGHTS,
            k=1
        )[0]

        if int_type in [2, 3]:
            rot = random.choice(ROTATIONS)
            grid_row.append((int_type, rot))

        else:
            grid_row.append(1)

    TYPE_GRID.append(grid_row)


print("\nTYPE_GRID")

for row in TYPE_GRID:
    print(row)


# =========================================================
# 교차로 및 RAW LINK 생성
# =========================================================
intersections = {}
raw_links = []
intersection_areas = []

raw_link_id = 0


for row in range(N):

    for col in range(N):

        cell = TYPE_GRID[row][col]

        if isinstance(cell, (tuple, list)):
            int_type = cell[0]
            rot = cell[1]

        else:
            int_type = cell
            rot = 0

        dx = col * BLOCK_SIZE
        dy = row * BLOCK_SIZE

        intersection_id = f"I_{row}_{col}"

        template = INTERSECTION_TYPES[int_type]

        ports = {}

        # =====================================================
        # Port geometry 회전 + 이동
        # =====================================================
        for port_name, port_geom in template["ports"].items():

            geom = rotate(
                port_geom,
                rot,
                origin=(CENTER, CENTER),
                use_radians=False
            )

            geom = translate(
                geom,
                xoff=dx,
                yoff=dy
            )

            side, io = port_name.split("_")

            new_side = PORT_ROTATION[rot][side]

            new_port_name = f"{new_side}_{io}"

            ports[new_port_name] = geom


        intersections[(row, col)] = {
            "intersection_id": intersection_id,
            "intersection_type": int_type,
            "rotation": rot,
            "ports": ports
        }


        # =====================================================
        # Intersection 영역
        #
        # Node 생성은 이 영역 내부/경계에서만 허용
        # =====================================================
        area_geom = box(
            dx + 1,
            dy + 1,
            dx + 4,
            dy + 4
        )

        intersection_areas.append({
            "intersection_id": intersection_id,
            "geometry": area_geom
        })


        # =====================================================
        # Intersection 내부 링크
        # =====================================================
        for base_geom in template["links"]:

            geom = rotate(
                base_geom,
                rot,
                origin=(CENTER, CENTER),
                use_radians=False
            )

            geom = translate(
                geom,
                xoff=dx,
                yoff=dy
            )

            raw_links.append({
                "raw_link_id": raw_link_id,
                "link_type": "intersection",
                "direction": None,
                "intersection_id": intersection_id,
                "from_intersection": intersection_id,
                "to_intersection": intersection_id,
                "intersection_type": int_type,
                "rotation": rot,
                "geometry": geom
            })

            raw_link_id += 1


# =========================================================
# 교차로 사이 Transition
#
# Transition 전체 = LineString 1개
#
# p1~p4는 geometry vertex일 뿐 NODE가 아님
# =========================================================
for row in range(N):

    for col in range(N):

        A = intersections[(row, col)]


        # =====================================================
        # RIGHT
        # =====================================================
        if col < N - 1:

            B = intersections[(row, col + 1)]


            # -------------------------------------------------
            # EAST →
            # -------------------------------------------------
            if "E_OUT" in A["ports"] and "W_IN" in B["ports"]:

                p0 = A["ports"]["E_OUT"]
                p5 = B["ports"]["W_IN"]

                middle_y = (
                    p0.y + p5.y
                ) / 2

                coords = [
                    (p0.x, p0.y),
                    (p0.x + 1, p0.y),
                    (p0.x + 2, middle_y),
                    (p5.x - 2, middle_y),
                    (p5.x - 1, p5.y),
                    (p5.x, p5.y)
                ]

                geom = LineString(coords)

                raw_links.append({
                    "raw_link_id": raw_link_id,
                    "link_type": "transition",
                    "direction": "E",
                    "intersection_id": None,
                    "from_intersection": A["intersection_id"],
                    "to_intersection": B["intersection_id"],
                    "intersection_type": None,
                    "rotation": None,
                    "geometry": geom
                })

                raw_link_id += 1


            # -------------------------------------------------
            # WEST ←
            # -------------------------------------------------
            if "W_OUT" in B["ports"] and "E_IN" in A["ports"]:

                p0 = B["ports"]["W_OUT"]
                p5 = A["ports"]["E_IN"]

                middle_y = (
                    p0.y + p5.y
                ) / 2

                coords = [
                    (p0.x, p0.y),
                    (p0.x - 1, p0.y),
                    (p0.x - 2, middle_y),
                    (p5.x + 2, middle_y),
                    (p5.x + 1, p5.y),
                    (p5.x, p5.y)
                ]

                geom = LineString(coords)

                raw_links.append({
                    "raw_link_id": raw_link_id,
                    "link_type": "transition",
                    "direction": "W",
                    "intersection_id": None,
                    "from_intersection": B["intersection_id"],
                    "to_intersection": A["intersection_id"],
                    "intersection_type": None,
                    "rotation": None,
                    "geometry": geom
                })

                raw_link_id += 1


        # =====================================================
        # UP
        # =====================================================
        if row < N - 1:

            B = intersections[(row + 1, col)]


            # -------------------------------------------------
            # NORTH ↑
            # -------------------------------------------------
            if "N_OUT" in A["ports"] and "S_IN" in B["ports"]:

                p0 = A["ports"]["N_OUT"]
                p5 = B["ports"]["S_IN"]

                middle_x = (
                    p0.x + p5.x
                ) / 2

                coords = [
                    (p0.x, p0.y),
                    (p0.x, p0.y + 1),
                    (middle_x, p0.y + 2),
                    (middle_x, p5.y - 2),
                    (p5.x, p5.y - 1),
                    (p5.x, p5.y)
                ]

                geom = LineString(coords)

                raw_links.append({
                    "raw_link_id": raw_link_id,
                    "link_type": "transition",
                    "direction": "N",
                    "intersection_id": None,
                    "from_intersection": A["intersection_id"],
                    "to_intersection": B["intersection_id"],
                    "intersection_type": None,
                    "rotation": None,
                    "geometry": geom
                })

                raw_link_id += 1


            # -------------------------------------------------
            # SOUTH ↓
            # -------------------------------------------------
            if "S_OUT" in B["ports"] and "N_IN" in A["ports"]:

                p0 = B["ports"]["S_OUT"]
                p5 = A["ports"]["N_IN"]

                middle_x = (
                    p0.x + p5.x
                ) / 2

                coords = [
                    (p0.x, p0.y),
                    (p0.x, p0.y - 1),
                    (middle_x, p0.y - 2),
                    (middle_x, p5.y + 2),
                    (p5.x, p5.y + 1),
                    (p5.x, p5.y)
                ]

                geom = LineString(coords)

                raw_links.append({
                    "raw_link_id": raw_link_id,
                    "link_type": "transition",
                    "direction": "S",
                    "intersection_id": None,
                    "from_intersection": B["intersection_id"],
                    "to_intersection": A["intersection_id"],
                    "intersection_type": None,
                    "rotation": None,
                    "geometry": geom
                })

                raw_link_id += 1


# =========================================================
# RAW GeoDataFrame
#
# Synthetic 좌표이므로 CRS는 일부러 지정하지 않음
# =========================================================
raw_links_gdf = gpd.GeoDataFrame(
    raw_links,
    geometry="geometry",
    crs=None
)


# =========================================================
# Intersection 영역 Union
# =========================================================
intersection_area_union = unary_union(
    [
        row["geometry"]
        for row in intersection_areas
    ]
)
# =========================================================
# 실제 교차점 NODE 생성
#
# 생성:
# - interior × interior : X형 교차
# - endpoint × interior : T형 접촉
# - interior × endpoint : T형 접촉
#
# 제외:
# - endpoint × endpoint : 단순 링크 연결
# - LineString overlap
# =========================================================
node_points = {}

sindex = raw_links_gdf.sindex
TOL = 1e-8

for i, geom_a in enumerate(raw_links_gdf.geometry):

    candidate_indices = sindex.query(
        geom_a,
        predicate="intersects"
    )

    for j in candidate_indices:

        if j <= i:
            continue

        geom_b = raw_links_gdf.geometry.iloc[j]

        inter = geom_a.intersection(geom_b)

        if inter.is_empty:
            continue

        # ---------------------------------------------
        # Point 추출
        # ---------------------------------------------
        if inter.geom_type == "Point":
            points = [inter]

        elif inter.geom_type == "MultiPoint":
            points = list(inter.geoms)

        elif inter.geom_type == "GeometryCollection":
            points = [
                g for g in inter.geoms
                if g.geom_type == "Point"
            ]

        else:
            # LineString overlap 제외
            continue

        # ---------------------------------------------
        # 각 교차점 판정
        # ---------------------------------------------
        for point in points:

            # 교차로 영역 내부만
            if not intersection_area_union.covers(point):
                continue

            a_start = Point(geom_a.coords[0])
            a_end   = Point(geom_a.coords[-1])

            b_start = Point(geom_b.coords[0])
            b_end   = Point(geom_b.coords[-1])

            # 각 geometry에서 해당 점이 endpoint인지 확인
            a_is_endpoint = (
                point.distance(a_start) <= TOL
                or
                point.distance(a_end) <= TOL
            )

            b_is_endpoint = (
                point.distance(b_start) <= TOL
                or
                point.distance(b_end) <= TOL
            )

            # -----------------------------------------
            # endpoint × endpoint만 제외
            # -----------------------------------------
            if a_is_endpoint and b_is_endpoint:
                continue

            # 나머지는 모두 실제 Junction
            # interior × interior
            # endpoint × interior
            # interior × endpoint
            key = (
                round(point.x, 9),
                round(point.y, 9)
            )

            node_points[key] = point


# =========================================================
# NODE 생성
# =========================================================
node_records = []
node_lookup = {}

node_id = 0


for key, point in sorted(node_points.items()):

    intersection_id = None

    for int_row in intersection_areas:

        if int_row["geometry"].covers(point):

            intersection_id = int_row[
                "intersection_id"
            ]

            break


    node_lookup[key] = node_id

    node_records.append({
        "node_id": node_id,
        "intersection_id": intersection_id,
        "geometry": point
    })

    node_id += 1


nodes_gdf = gpd.GeoDataFrame(
    node_records,
    geometry="geometry",
    crs=None
)


# =========================================================
# Intersection 내부 LINK를 Node 기준으로 분할
#
# Transition은 Node가 양 끝점에만 있으므로
# 하나의 LineString으로 그대로 유지됨
# =========================================================
final_links = []
final_link_id = 0

TOL = 1e-8


for _, row in raw_links_gdf.iterrows():

    geom = row.geometry

    split_points = []


    for key, node_point in node_points.items():

        if geom.distance(node_point) > TOL:
            continue


        start_point = Point(
            geom.coords[0]
        )

        end_point = Point(
            geom.coords[-1]
        )


        # LineString 내부 Node만 split
        # 끝점 Node는 split 필요 없음
        if (
            node_point.distance(start_point) > TOL
            and
            node_point.distance(end_point) > TOL
        ):

            split_points.append(
                node_point
            )


    # =====================================================
    # Node가 내부에 있다면 split
    # =====================================================
    if split_points:

        splitter = MultiPoint(
            split_points
        )

        result = split(
            geom,
            splitter
        )

        parts = [
            g
            for g in result.geoms
            if g.geom_type == "LineString"
            and g.length > TOL
        ]

    else:

        parts = [geom]


    # =====================================================
    # 최종 LINK 생성
    # =====================================================
    for part_no, part in enumerate(parts):

        start_point = Point(
            part.coords[0]
        )

        end_point = Point(
            part.coords[-1]
        )


        start_key = (
            round(start_point.x, 9),
            round(start_point.y, 9)
        )

        end_key = (
            round(end_point.x, 9),
            round(end_point.y, 9)
        )


        from_node = node_lookup.get(
            start_key
        )

        to_node = node_lookup.get(
            end_key
        )


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
            "from_node": from_node,
            "to_node": to_node,
            "geometry": part
        })

        final_link_id += 1


links_gdf = gpd.GeoDataFrame(
    final_links,
    geometry="geometry",
    crs=None
)


# =========================================================
# 시각화
# =========================================================
fig, ax = plt.subplots(
    figsize=(14, 14)
)


for _, row in links_gdf.iterrows():

    geom = row.geometry

    x, y = geom.xy


    if row["link_type"] == "intersection":

        if row["intersection_type"] == 1:
            color = "blue"

        elif row["intersection_type"] == 2:
            color = "green"

        else:
            color = "red"

        lw = 2.5


    else:

        color = "black"
        lw = 1.8


    ax.plot(
        x,
        y,
        color=color,
        linewidth=lw
    )


    # 방향 화살표
    coords = list(
        geom.coords
    )

    if len(coords) >= 2:

        ax.annotate(
            "",
            xy=coords[-1],
            xytext=coords[-2],
            arrowprops=dict(
                facecolor=color,
                edgecolor=color,
                arrowstyle="-|>",
                lw=lw,
                mutation_scale=8,
                shrinkA=0,
                shrinkB=0
            )
        )


# =========================================================
# NODE 표시
# =========================================================
if not nodes_gdf.empty:

    ax.scatter(
        nodes_gdf.geometry.x,
        nodes_gdf.geometry.y,
        s=30,
        color="black",
        zorder=10
    )


    if SHOW_NODE_ID:

        for _, row in nodes_gdf.iterrows():

            ax.text(
                row.geometry.x + 0.08,
                row.geometry.y + 0.08,
                f'N{row["node_id"]}',
                fontsize=6,
                zorder=11
            )


# =========================================================
# Intersection ID / Type / Rotation
# =========================================================
for (row, col), data in intersections.items():

    cx = (
        col * BLOCK_SIZE
        + CENTER
    )

    cy = (
        row * BLOCK_SIZE
        + CENTER
    )


    if data["intersection_type"] in [2, 3]:

        txt = (
            f'{data["intersection_id"]}\n'
            f'T{data["intersection_type"]} '
            f'R{data["rotation"]}'
        )

    else:

        txt = (
            f'{data["intersection_id"]}\n'
            f'T1'
        )


    ax.text(
        cx,
        cy,
        txt,
        fontsize=7,
        ha="center",
        va="center",
        bbox=dict(
            boxstyle="round,pad=0.15",
            facecolor="white",
            alpha=0.75
        ),
        zorder=20
    )


ax.set_xlim(
    -1,
    (N - 1) * BLOCK_SIZE + 6
)

ax.set_ylim(
    -1,
    (N - 1) * BLOCK_SIZE + 6
)

ax.set_aspect(
    "equal"
)

ax.grid(
    True,
    linestyle="--",
    alpha=0.2
)

plt.tight_layout()
plt.show()


# =========================================================
# GPKG 출력
# =========================================================
output_path = Path(
    OUTPUT_GPKG
)

output_path.parent.mkdir(
    parents=True,
    exist_ok=True
)

if output_path.exists():
    output_path.unlink()


links_gdf.to_file(
    OUTPUT_GPKG,
    layer="links",
    driver="GPKG"
)

nodes_gdf.to_file(
    OUTPUT_GPKG,
    layer="nodes",
    driver="GPKG",
    mode="a"
)


print()
print("========================================")
print("Intersection count :", len(intersections))
print("Raw link count     :", len(raw_links_gdf))
print("Final link count   :", len(links_gdf))
print("Node count         :", len(nodes_gdf))
print("GPKG               :", OUTPUT_GPKG)
print("========================================")