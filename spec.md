# 복잡교차로 도시 네트워크 시뮬레이션 스펙

## 1. 목적

N×N 격자 형태의 가상 도시 도로망을 생성하고, 서로 다른 형태의 교차로를 랜덤 배치하여 교차로 및 Stroke/Topology 알고리즘을 실험하기 위한 시뮬레이션 데이터를 생성한다.

최종 공간 산출물은 GeoPackage(GPKG)이며 모든 공간 데이터는 Shapely/GeoPandas Geometry로 관리한다. 향후 GUI 적용을 전제로 하며, **설정값은 YAML, 계산 로직은 Python 모듈, 실행/GUI는 orchestration 계층**으로 분리한다.

---

## 2. 설계 원칙

1. `config.yaml`을 설정의 단일 기준(single source of truth)으로 사용한다.
2. 시뮬레이션 계산 모듈 내부에는 사용자 조정용 전역 설정값을 두지 않는다.
3. GUI는 `config.yaml`과 동일한 항목을 편집하고 `AppConfig`를 생성하여 pipeline을 호출할 수 있어야 한다.
4. Geometry 생성, topology 생성, 출력, 시각화를 서로 분리한다.
5. 시각화 함수는 Figure를 반환하고 `show()`를 강제하지 않아 GUI canvas에 임베드할 수 있어야 한다.
6. 동일한 `seed`와 동일한 설정에서는 동일한 `TYPE_GRID`가 생성되어야 한다.
7. Synthetic 좌표이므로 현재 CRS는 지정하지 않는다.

---

## 3. 프로젝트 구조

```text
city_sim_modular/
├─ config.yaml
├─ main.py
├─ requirements.txt
├─ spec.md
└─ city_sim/
   ├─ __init__.py
   ├─ config.py
   ├─ templates.py
   ├─ generator.py
   ├─ topology.py
   ├─ io.py
   ├─ visualization.py
   └─ pipeline.py
```

### 3.1 모듈 책임

| 모듈 | 책임 |
|---|---|
| `config.py` | YAML 로드, dataclass 변환, 설정 검증, 상대 출력 경로 해석 |
| `templates.py` | T1/T2/T3 기본 Geometry와 Port 회전 규칙 |
| `generator.py` | `TYPE_GRID`, 교차로, Port, 내부 Link, Transition 생성 |
| `topology.py` | 실제 Junction Node 판정, Node ID 생성, Node 기준 Link split |
| `io.py` | GPKG `links`, `nodes` 저장 |
| `visualization.py` | Matplotlib 시각화 및 Figure 반환 |
| `pipeline.py` | 전체 처리 순서 통합, GUI/CLI 공용 API 제공 |
| `main.py` | CLI 진입점 |

`templates.py`의 Geometry는 도로 유형 자체의 정의이므로 설정값과 분리한다. 교차로 종류 자체를 GUI에서 편집하는 기능이 필요해지면 차후 별도 template YAML/JSON 스키마로 확장한다.

---

## 4. YAML 설정

기존 Python 상단 전역변수 대신 다음 구조를 사용한다.

```yaml
simulation:
  grid_size: 16
  block_size: 32.0
  center: 2.5
  seed: 42

intersection:
  type_values: [1, 2, 3]
  type_weights: [0.33, 0.33, 0.34]
  rotations: [0, 90, 180, 270]
  rotatable_types: [2, 3]
  area_bounds: [1.0, 1.0, 4.0, 4.0]

transition:
  near_offset: 1.0
  bend_offset: 2.0

topology:
  tolerance: 1.0e-8
  coordinate_precision: 9

output:
  gpkg: ./output/city_sim.gpkg
  links_layer: links
  nodes_layer: nodes
  overwrite: true

visualization:
  enabled: true
  show_window: true
  show_node_id: false
  figure_size: [14, 14]
  axis_padding_min: 1.0
  axis_padding_max: 6.0
  grid: true
  intersection_colors:
    1: blue
    2: green
    3: red
  transition_color: black
  node_color: black
  intersection_linewidth: 2.5
  transition_linewidth: 1.8
  node_size: 30
  node_label_offset: 0.08
  node_label_fontsize: 6
  intersection_label_fontsize: 7
```

### 4.1 주요 설정 의미

`simulation.grid_size`는 가로/세로 교차로 개수이며 전체 교차로 수는 `grid_size × grid_size`이다. `simulation.block_size`는 인접 교차로 기준 좌표 간격이다. `simulation.seed`를 고정하면 동일한 랜덤 도시를 재현한다.

`intersection.type_values`와 `intersection.type_weights`는 같은 길이를 가져야 한다. `rotatable_types`에 포함된 타입만 `rotations` 중 하나를 랜덤 선택한다. 현재 T1은 회전하지 않고 T2/T3만 회전한다.

`intersection.area_bounds`는 각 Grid cell의 원점 `(dx, dy)`에 더해지는 local 교차로 영역 `[minx, miny, maxx, maxy]`이다. Node 후보는 이 영역 내부/경계에서만 허용한다.

`transition.near_offset`, `transition.bend_offset`은 기존 Transition의 `p1~p4` vertex 형상을 제어한다. 이 지점은 Geometry vertex일 뿐 Node가 아니다.

`topology.tolerance`는 endpoint 판정과 split 판정에 사용한다. `coordinate_precision`은 Node key를 만들 때 XY round 자릿수이다.

`output.gpkg`가 상대 경로이면 `config.yaml` 위치를 기준으로 해석한다. GUI가 다른 작업 디렉터리에서 실행되더라도 출력 위치가 변하지 않도록 한다.

---

## 5. 설정 객체

`config.py`는 YAML dictionary를 직접 전체 코드에 전달하지 않고 dataclass로 변환한다.

```text
AppConfig
├─ simulation: SimulationConfig
├─ intersection: IntersectionConfig
├─ transition: TransitionConfig
├─ topology: TopologyConfig
├─ output: OutputConfig
└─ visualization: VisualizationConfig
```

GUI에서는 위 객체의 필드와 widget 값을 1:1로 대응시키는 것을 기본으로 한다. 계산 모듈은 GUI widget을 직접 참조하지 않는다.

---

## 6. 교차로 타입

### 6.1 Type 1 — 일반 십자 교차로

회전하지 않으며 4방향 모두 진입/진출 가능하다.

```text
        ↑
        │
←───────┼───────→
        │
        ↓
```

내부 링크는 Eastbound, Westbound, Northbound, Southbound 총 4개이다.

### 6.2 Type 2 — Offset 십자 교차로

일반 십자 교차로와 동일하게 4방향이 연결되지만 도로 중심 위치에 Offset이 존재한다.

```text
          ↑
          │
←─────────┼─────────→
        │
        ↓
```

현재 0/90/180/270° 중 하나로 랜덤 회전하며 Offset 위치도 Geometry와 함께 회전한다.

### 6.3 Type 3 — T자 교차로

기본 Geometry는 북쪽 방향이 폐쇄된 형태이다.

```text
←─────────┬─────────→
          │
          ↓
```

회전 결과는 다음과 같다.

```text
(3, 0)   : 북쪽 폐쇄
(3, 90)  : 서쪽 폐쇄
(3, 180) : 남쪽 폐쇄
(3, 270) : 동쪽 폐쇄
```

---

## 7. TYPE_GRID

각 Grid cell에 교차로 타입을 랜덤 배치한다. 회전하지 않는 Type 1은 정수 `1`, 회전 타입은 `(type, rotation)` 형태를 유지한다.

```python
TYPE_GRID = [
    [1, (2, 90), (3, 270)],
    [(3, 90), (2, 0), 1],
    [1, (2, 90), 1],
]
```

`generate_type_grid(config)`는 Python 전역 `random.seed()`를 변경하지 않고 로컬 `random.Random(seed)` 객체를 사용한다. 따라서 GUI나 다른 모듈의 random 상태와 분리된다.

---

## 8. Geometry 처리 원칙

모든 선형 데이터는 `LineString`, Node 데이터는 `Point` Geometry로 관리한다. `start`, `end` 좌표 필드를 별도로 저장하지 않는다.

링크 시작/종료점은 필요할 때 Geometry에서 계산한다.

```python
Point(geometry.coords[0])
Point(geometry.coords[-1])
```

---

## 9. 교차로 내부 Link

교차로 내부 도로는 각각 하나의 `LineString`이다. 생성 순서는 다음과 같다.

1. `templates.py`에서 타입별 local Geometry를 가져온다.
2. `(CENTER, CENTER)` 기준으로 회전한다.
3. Grid 위치의 `(dx, dy)`만큼 translation한다.
4. `raw_link_id`를 부여하여 RAW Link에 추가한다.

회전은 `shapely.affinity.rotate()`, 이동은 `translate()`를 사용한다.

---

## 10. Port

Port는 인접 도로를 연결하기 위한 교차로 경계 `Point`이다.

```text
W_IN / W_OUT
E_IN / E_OUT
N_IN / N_OUT
S_IN / S_OUT
```

교차로 회전 시 Port Geometry와 Port 방향 이름을 같이 회전한다. 예를 들어 `E_OUT`을 90° 반시계 방향 회전하면 `N_OUT`이 된다.

Port 방향 변환 규칙은 `templates.PORT_ROTATION`에서 관리한다.

---

## 11. Transition Link

서로 인접한 두 교차로 사이의 도로는 하나의 `LineString`으로 생성한다. Offset 변화가 있어도 여러 Link로 분할하지 않는다.

```text
Intersection A                           Intersection B

───────╲                              ╱───────
        ╲____________________________╱
```

전체 형상은 `p0~p5`를 포함한 하나의 LineString이다.

```python
LineString([p0, p1, p2, p3, p4, p5])
```

`p1~p4`는 단순 Geometry Vertex이며 Node가 아니다.

### 11.1 Transition 생성 조건

대응 Port가 양쪽 교차로에 모두 있을 때만 생성한다.

```text
East  : A.E_OUT → B.W_IN
West  : B.W_OUT → A.E_IN
North : A.N_OUT → B.S_IN
South : B.S_OUT → A.N_IN
```

T자 교차로 때문에 대응 Port가 없으면 해당 방향 Transition을 생성하지 않는다.

### 11.2 Offset 연결

두 Port의 lane 위치가 다르면 Transition 내부에서 Offset을 처리한다. `near_offset`과 `bend_offset`이 p1~p4 위치를 결정하지만 전체 Transition은 계속 하나의 Link이다.

---

## 12. Node 정의

Node는 모든 Link Endpoint에 생성하지 않는다. **실제 교차로 구조를 구성하는 교차점에만 생성한다.**

### 12.1 Node 생성 조건

```text
Interior × Interior    → Node
Endpoint × Interior    → Node
Interior × Endpoint    → Node
```

### 12.2 Node 미생성 조건

```text
Endpoint × Endpoint    → 제외
Transition Vertex      → 제외
LineString Overlap     → 제외
```

Transition과 Intersection Link가 단순히 endpoint에서 이어지는 위치도 Node가 아니다.

---

## 13. Node 판정 논리

두 RAW Link의 intersection 결과가 `Point`, `MultiPoint`, 또는 Point를 포함한 `GeometryCollection`이면 각 Point에 대해 endpoint 여부를 판정한다.

```python
if a_is_endpoint and b_is_endpoint:
    # Node 생성 안 함
    continue

# 나머지는 실제 Junction Node
```

Node 후보 검색은 GeoDataFrame spatial index의 `intersects` predicate를 사용한다.

---

## 14. Node 생성 공간 범위

Node는 교차로 영역 안에서 발생한 교차점만 대상으로 한다. 기본 local 영역은 YAML의 다음 값이다.

```yaml
intersection:
  area_bounds: [1.0, 1.0, 4.0, 4.0]
```

각 cell의 `(dx, dy)`에 더해 `box(dx+1, dy+1, dx+4, dy+4)` 형태가 되며, 전체 교차로 영역은 `unary_union()`으로 결합하여 후보 필터링에 사용한다.

---

## 15. Link Split

Node가 생성된 지점은 실제 Topological Junction이므로 해당 위치에서 LineString을 분할한다. 분할에는 `shapely.ops.split()`을 사용한다.

Node가 Link endpoint에 있는 경우 추가 split은 필요하지 않는다. Transition 중간 Offset vertex에는 Node가 없으므로 Transition은 중간 vertex 때문에 분할되지 않는다.

---

## 16. Link 데이터 스키마

최종 `links` Layer:

```text
link_id
parent_link_id
part_no
link_type
direction
intersection_id
from_intersection
to_intersection
intersection_type
rotation
from_node
to_node
geometry
```

`link_type`:

```text
intersection
transition
```

`direction`:

```text
E
W
N
S
NULL
```

교차로 내부 Link는 현재 `direction=NULL`을 유지한다.

---

## 17. Node 데이터 스키마

최종 `nodes` Layer:

```text
node_id
intersection_id
geometry
```

Geometry 타입은 `Point`이며 실제 Junction 위치에만 존재한다.

---

## 18. ID 규칙

Intersection ID는 Grid 위치를 사용한다.

```text
I_{row}_{col}
```

원본 Link에는 `raw_link_id`를 순차 부여한다. Node split 이후 최종 Link에는 `link_id`를 새로 부여하며 원본과의 관계는 `parent_link_id`로 유지한다.

---

## 19. 시각화 규칙

기본 색상은 YAML에서 변경 가능하며 초기값은 다음과 같다.

```text
T1 : Blue
T2 : Green
T3 : Red
Transition : Black
Node : Black Point
```

Node ID 표시는 `visualization.show_node_id`로 제어한다.

`plot_network()`는 `(fig, ax)`를 반환한다. GUI에서는 `show=False`로 호출하여 Qt Matplotlib Canvas 등에 임베드할 수 있다. CLI에서는 `visualization.show_window=true`일 경우 창을 표시한다.

---

## 20. GPKG 출력

최종 결과는 하나의 GeoPackage에 두 Layer로 출력한다.

```text
city_sim.gpkg
├─ links
└─ nodes
```

기본 경로는 다음과 같다.

```yaml
output:
  gpkg: ./output/city_sim.gpkg
```

상대 경로는 `config.yaml` 파일이 있는 디렉터리를 기준으로 해석한다.

---

## 21. Pipeline API

GUI와 CLI는 동일한 pipeline을 사용한다.

```python
from city_sim import load_config, run_simulation

config = load_config("config.yaml")
result = run_simulation(config)
```

`SimulationResult`는 다음 값을 제공한다.

```text
type_grid
intersections
raw_links_gdf
links_gdf
nodes_gdf
output_path
```

따라서 GUI는 pipeline 실행 후 GPKG를 다시 읽지 않고도 즉시 생성 결과와 통계, 지도 preview를 표시할 수 있다.

### 21.1 GUI에서 저장 없이 Preview

```python
result = run_simulation(config, save=False, visualize=False)
```

그 후:

```python
from city_sim.visualization import plot_network
fig, ax = plot_network(
    result.links_gdf,
    result.nodes_gdf,
    result.intersections,
    config,
    show=False,
)
```

형태로 preview를 구성할 수 있다.

---

## 22. CLI 실행

```bash
python main.py --config config.yaml
```

저장 없이 실행:

```bash
python main.py --config config.yaml --no-save
```

시각화 없이 실행:

```bash
python main.py --config config.yaml --no-plot
```

---

## 23. 설정 검증

`load_config()` 단계에서 최소한 다음을 검증한다.

```text
grid_size > 0
block_size > 0
type_values 길이 == type_weights 길이
type_weights 합 > 0
rotation ∈ {0, 90, 180, 270}
rotatable_types ⊆ type_values
area_bounds 형식 정상
tolerance > 0
coordinate_precision >= 0
```

GUI에서도 동일 검증 로직을 그대로 재사용한다. GUI가 별도의 validation 규칙을 중복 구현하지 않는 것을 원칙으로 한다.

---

## 24. 현재 시뮬레이션 핵심 Topology 규칙

```text
1. 모든 도로 데이터는 LineString Geometry이다.
2. T2와 T3는 기본적으로 0/90/180/270° 회전 가능하다.
3. 교차로 사이 도로는 하나의 Transition LineString이다.
4. Transition 내부 Offset 꺾임점은 Node가 아니다.
5. 단순 Link Endpoint 연결부도 Node가 아니다.
6. Interior × Interior 교차점은 Node이다.
7. Endpoint × Interior 형태의 T Junction도 Node이다.
8. Interior × Endpoint도 Node이다.
9. Node 위치에서는 Link를 분할한다.
10. 최종 출력은 links + nodes GPKG이다.
```

---

## 25. 처리 순서

```text
config.yaml
   ↓
load_config()
   ↓
generate_type_grid()
   ↓
build_raw_network()
   ├─ intersections
   ├─ intersection areas
   └─ raw_links_gdf
   ↓
detect_nodes()
   ↓
split_links_at_nodes()
   ↓
links_gdf + nodes_gdf
   ├─ save_gpkg()
   └─ plot_network()
```

---

## 26. 향후 GUI 확장 원칙

GUI는 계산 알고리즘을 포함하지 않고 다음 역할만 담당한다.

```text
YAML Load / Save
설정값 편집
Run / Preview 버튼
TYPE_GRID 및 통계 표시
Matplotlib Figure 임베드
GPKG 출력 경로 선택
실행 오류/validation 메시지 표시
```

권장 흐름은 다음과 같다.

```text
GUI Widget
  ↕
YAML-compatible settings
  ↓
AppConfig
  ↓
run_simulation()
  ↓
SimulationResult
  ↓
Preview / Export / Statistics
```

이 구조에서는 CLI와 GUI가 같은 generator/topology 코드를 사용하므로 두 실행 방식의 결과가 달라지는 문제를 방지할 수 있다.

---

## 27. 용도

생성된 네트워크는 이후 다음 실험의 입력 데이터로 사용할 수 있다.

```text
Stroke 생성
Stroke 분리
Degree 기반 Junction 판정
복잡교차로 진입/이탈 판단
LEFT / RIGHT / STRAIGHT / U-TURN 판단
T Junction 판정
Offset 도로 대응
교차로 추적
NetworkX Directed Graph 변환
```
