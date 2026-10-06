from shapely.geometry import LineString, Point


# =========================================================
# 교차로 템플릿
#
# 모든 geometry는 Shapely geometry
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
            "W_IN": Point(1, 2), "W_OUT": Point(1, 3),
            "E_IN": Point(4, 3), "E_OUT": Point(4, 2),
            "S_IN": Point(3, 1), "S_OUT": Point(2, 1),
            "N_IN": Point(2, 4), "N_OUT": Point(3, 4),
        },
    },
    2: {
        "links": [
            LineString([(1, 3), (4, 3)]),
            LineString([(4, 4), (1, 4)]),
            LineString([(2, 4), (2, 1)]),
            LineString([(3, 1), (3, 4)]),
        ],
        "ports": {
            "W_IN": Point(1, 3), "W_OUT": Point(1, 4),
            "E_IN": Point(4, 4), "E_OUT": Point(4, 3),
            "S_IN": Point(3, 1), "S_OUT": Point(2, 1),
            "N_IN": Point(2, 4), "N_OUT": Point(3, 4),
        },
    },
    3: {
        "links": [
            LineString([(1, 3), (4, 3)]),
            LineString([(4, 4), (1, 4)]),
            LineString([(2, 3), (2, 1)]),
            LineString([(3, 1), (3, 3)]),
        ],
        "ports": {
            "W_IN": Point(1, 3), "W_OUT": Point(1, 4),
            "E_IN": Point(4, 4), "E_OUT": Point(4, 3),
            "S_IN": Point(3, 1), "S_OUT": Point(2, 1),
        },
    },
}


# =========================================================
# 회전 후 Port 방향 변환
# 반시계 방향
# =========================================================
PORT_ROTATION = {
    0: {"W": "W", "E": "E", "N": "N", "S": "S"},
    90: {"W": "S", "S": "E", "E": "N", "N": "W"},
    180: {"W": "E", "E": "W", "N": "S", "S": "N"},
    270: {"W": "N", "N": "E", "E": "S", "S": "W"},
}
