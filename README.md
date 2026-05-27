# Nearby AIS / ECS Serial ROS 2 Driver Guide

패키지명: aivn_sensorpack_nearby_ais  
버전: v0.1.0  
작성자: 박재원  
배포등급: 내부전용 (Confidential)
작성일: 260527 
## 1. 개요

`aivn_sensorpack_nearby_ais`는 시리얼 포트에서 수신한 AIS NMEA 0183 문장과 ECS `!PNSD` 문장을 파싱해 하나의 ROS 2 토픽으로 퍼블리시하는 Python 패키지입니다. ROS 2 Humble 기준으로 동작하며, 실행 중심은 `nearby_ais_node` 하나입니다.

입력 흐름은 다음과 같습니다.

1. 시리얼 포트 오픈 및 재연결 관리
2. 줄 단위 문장 추출
3. 문장 타입 분기
   - AIS: `!AIVDM`, `!AIVDO`
   - ECS: `!PNSD`
4. 체크섬 검증
5. 파싱 및 메시지 변환
6. `/sensor_pack/external/nearby_ais/ship` 퍼블리시

실행 관련 핵심 파일:

| 항목 | 파일 |
| --- | --- |
| 메인 노드 | `aivn_sensorpack_nearby_ais/nearby_ais_node.py` |
| AIS 파서 | `aivn_sensorpack_nearby_ais/ais_nmea_parser.py` |
| AIS 6-bit 유틸 | `aivn_sensorpack_nearby_ais/ais_sixbit.py` |
| ECS 파서 | `aivn_sensorpack_nearby_ais/ecs_parser.py` |
| launch | `launch/nearby_ais.launch.py` |
| config | `config/nearby_ais.yaml` |
| 메시지 | `../aivn_interfaces/msg/NearbyAisShip.msg` |

## 2. 주요 기능

- 시리얼 포트 연결 실패 시 재시도
- `!AIVDM`, `!AIVDO`, `!PNSD` 문장 처리
- AIS / ECS 체크섬 검증
- AIS 6-bit armoring payload 디코딩
- AIS multi-fragment 조립
- AIS Type 1/2/3/5/18/19/24 지원
- ECS `!PNSD` 비트필드 디코딩
- AIS 정적 정보 캐시 유지
- 통합 메시지 `aivn_interfaces/msg/NearbyAisShip` 퍼블리시
- `device_type=auto|ais|ecs` 장비 선택
- 수신/파싱/퍼블리시 로그와 요약 통계 출력

## 3. 패키지 구조

```text
aivn_sensorpack_nearby_ais/
├── README.md
├── package.xml
├── setup.py
├── setup.cfg
├── config/
│   └── nearby_ais.yaml
├── launch/
│   └── nearby_ais.launch.py
├── resource/
│   └── aivn_sensorpack_nearby_ais
└── aivn_sensorpack_nearby_ais/
    ├── __init__.py
    ├── nearby_ais_node.py
    ├── ais_nmea_parser.py
    ├── ais_sixbit.py
    ├── ecs_parser.py
    ├── test.file.txt
    └── test_code/
        ├── ais_sample.txt
        ├── ecs_sample.txt
        └── 테스트방법
```

주요 파일 역할:

| 파일 | 역할 |
| --- | --- |
| `nearby_ais_node.py` | 시리얼 입력, 타입 분기, 파라미터 처리, 메시지 퍼블리시 |
| `ais_nmea_parser.py` | AIS 문장 파싱, fragment 조립, message type별 디코딩 |
| `ais_sixbit.py` | AIS payload 비트 변환 및 필드 추출 유틸 |
| `ecs_parser.py` | ECS `!PNSD` 문장 체크섬 검증 및 비트필드 디코딩 |
| `config/nearby_ais.yaml` | 실행 파라미터 통합 관리 |
| `launch/nearby_ais.launch.py` | config 파일을 로드해 노드 실행 |
| `test_code/ais_sample.txt` | AIS 샘플 데이터 |
| `test_code/ecs_sample.txt` | ECS 샘플 데이터 |

## 4. 지원 입력 문장

| Sentence | 설명 |
| --- | --- |
| `!AIVDM` | 타 선박 AIS 메시지 |
| `!AIVDO` | 자선 AIS 메시지 |
| `!PNSD` | ECS nearby ship 데이터 |

지원하지 않는 문장은 `nearby_ais_node.py`에서 별도 처리 없이 무시됩니다. AIS multi-fragment 문장은 조립이 완료되기 전까지 `parse pending/ignored` 로그가 날 수 있습니다.

## 5. 지원 AIS Message Type

`ais_nmea_parser.py` 구현 기준 지원 타입:

| Type | 이름 | 처리 필드 |
| --- | --- | --- |
| 1 | Class A Position Report | MMSI, nav status, lat/lon, SOG, COG, heading |
| 2 | Class A Position Report | MMSI, nav status, lat/lon, SOG, COG, heading |
| 3 | Class A Position Report | MMSI, nav status, lat/lon, SOG, COG, heading |
| 5 | Static and Voyage Related Data | ship name, call sign, ship type |
| 18 | Class B Position Report | MMSI, lat/lon, SOG, COG, heading |
| 19 | Extended Class B Position Report | MMSI, lat/lon, SOG, COG, heading, ship name, ship type |
| 24 | Static Data Report | ship name 또는 call sign / ship type |

그 외 타입은 debug callback이 켜진 경우 `unsupported AIS message type ignored`로 남고, 메시지는 퍼블리시하지 않습니다.

## 6. ROS 2 인터페이스

기본 퍼블리시 정보:

| 항목 | 값 |
| --- | --- |
| Topic | `/sensor_pack/external/nearby_ais/ship` |
| Message Type | `aivn_interfaces/msg/NearbyAisShip` |
| Queue Depth | `100` |
| Node Name | `nearby_ais_node` |
| frame_id | config의 `frame_id` 값 사용, 기본값 `nearby_ais` |

시간/원문 관련 처리:

- `header.stamp`: ROS clock의 현재 시각
- `server_receive_time_unix`: 메시지 퍼블리시 시점의 Unix time
- `device_time_unix`: ECS payload 내부 수신 시각, AIS는 기본값 `0`
- `device_time_text`: ECS payload 내부 수신 시각 문자열, AIS는 기본값 `""`
- `source_port`: 현재 열려 있는 시리얼 포트명
- `original_sentence`: 원본 입력 문장

메시지 필드 매핑:

| NearbyAisShip 필드 | 값/의미 |
| --- | --- |
| `source_device` | `"ais"` 또는 `"ecs"` |
| `parser_type` | AIS는 `ivdm` 또는 `ivdo`, ECS는 `pnsd` |
| `has_ais_position` | AIS 위치 정보 유효 여부 |
| `has_ais_static` | AIS 정적 정보 유효 여부 |
| `has_ecs_ship` | ECS 선박 정보 유효 여부 |
| `ais_message_id` | AIS message type |
| `ais_mmsi` | AIS MMSI |
| `ship_id` | AIS는 MMSI 문자열, ECS는 decoded ship ID |
| `ship_name_ais` | AIS ship name |
| `call_sign_ais` | AIS call sign |
| `ship_type_ais` | AIS ship type |
| `navigation_status_ais` | AIS navigation status |
| `lat_ais`, `lon_ais` | AIS decimal degree 좌표 |
| `sog_ais`, `cog_ais`, `heading_ais` | AIS 속도/방향/heading |
| `ship_name_ecs` | ECS ship name |
| `ship_type_ecs` | ECS ship type |
| `comm_net_ecs` | ECS 통신망 코드 변환값 |
| `power_source_ecs` | ECS 전원 코드 변환값 |
| `uc_num_ecs` | ECS unit controller 번호 |
| `lat_ecs`, `lon_ecs` | ECS decimal degree 좌표 |
| `sog_ecs`, `cog_ecs`, `heading_ecs` | ECS 속도/방향/heading |

## 7. 파라미터

모든 실행 파라미터는 `config/nearby_ais.yaml`에서 관리합니다.

| 파라미터 | 타입 | 기본값 | 설명 |
| --- | --- | --- | --- |
| `serial_port_name` | string | `"/tmp/nearby_ais_in"` | 시리얼 포트 경로 |
| `baud_rate` | integer | `38400` | 보드레이트 |
| `data_bits` | integer | `8` | data bits |
| `parity` | string | `"NONE"` | parity (`NONE`, `EVEN`, `ODD`, `MARK`, `SPACE`) |
| `stop_bits` | integer/float | `1` | stop bits (`1`, `1.5`, `2`) |
| `xonxoff` | bool | `false` | software flow control |
| `rtscts` | bool | `false` | RTS/CTS |
| `dsrdtr` | bool | `false` | DSR/DTR |
| `topic_name` | string | `"/sensor_pack/external/nearby_ais/ship"` | 퍼블리시 토픽 |
| `frame_id` | string | `"nearby_ais"` | 메시지 frame_id |
| `device_type` | string | `"auto"` | `auto`, `ais`, `ecs` 중 선택 |
| `checksum_required` | bool | `true` | 체크섬 검증 강제 여부 |
| `poll_period_sec` | float | `0.005` | 시리얼 poll 주기 |
| `read_size` | integer | `8192` | 한 번에 읽을 바이트 수 |
| `reconnect_sec` | float | `2.0` | 재연결 시도 간격 |
| `stale_static_info_sec` | float | `600.0` | AIS 정적 정보 캐시 TTL |
| `no_data_warn_sec` | float | `0.0` | 데이터 미수신 경고 주기, `0`이면 비활성 |
| `no_sentence_warn_sec` | float | `0.0` | 바이트는 오지만 문장 추출 실패 경고 주기 |
| `verbose` | bool | `false` | 5초 단위 summary 로그 출력 |
| `log_rx_sentence` | bool | `false` | 원문 수신 로그 출력 |
| `log_parse_result` | bool | `true` | parse success/failure/pending 로그 출력 |
| `debug_hex_dump` | bool | `false` | 수신 바이트 hex dump 출력 |
| `debug_hex_limit` | integer | `64` | hex dump 최대 길이 |
| `debug_publish_reason` | bool | `false` | publish/drop 사유 출력 |
| `debug_fragment` | bool | `false` | AIS fragment 상태 로그 출력 |

## 8. 설치 및 빌드

```bash
cd ~/260514_busan
colcon build --packages-select aivn_interfaces aivn_sensorpack_nearby_ais
source install/setup.bash
```

의존성:

- `rclpy`
- `pyserial`
- `aivn_interfaces`
- `std_msgs`

`package.xml`에는 `pyserial`이 `exec_depend`로 포함되어 있습니다. 다만 `setup.py`의 `install_requires`에는 `setuptools`만 들어 있으므로, Python 환경에서 직접 설치가 필요한 경우 아래 중 하나를 사용하세요.

```bash
sudo apt install python3-serial
```

또는

```bash
python3 -m pip install pyserial
```

## 9. 실행 방법

이 패키지는 config 파일 중심 구조입니다. launch 파일은 `config/nearby_ais.yaml`을 로드해서 노드를 실행하는 역할만 합니다.

launch 실행:

```bash
cd ~/260514_busan
source install/setup.bash
ros2 launch aivn_sensorpack_nearby_ais nearby_ais.launch.py
```

직접 실행:

```bash
cd ~/260514_busan
source install/setup.bash
ros2 run aivn_sensorpack_nearby_ais nearby_ais_node
```

## 10. 시리얼 포트 설정

기본 시리얼 설정은 `38400 bps`, `8N1`, no flow control 입니다.

Linux 권한 확인:

```bash
ls -l /dev/ttyUSB0
```

권한 문제 해결 예시:

```bash
sudo usermod -aG dialout $USER
```

적용 후 재로그인이 필요할 수 있습니다.

## 11. 테스트 데이터 주입 방법

### socat 가상 시리얼 포트 방식

가상 포트 생성:

```bash
socat -d -d pty,raw,echo=0,link=/tmp/nearby_ais_in pty,raw,echo=0,link=/tmp/nearby_ais_out
```

config에서 `serial_port_name`을 `/tmp/nearby_ais_in`으로 설정한 뒤 노드를 실행합니다.

AIS 샘플 주입:

```bash
cat aivn_sensorpack_nearby_ais/aivn_sensorpack_nearby_ais/test_code/ais_sample.txt > /tmp/nearby_ais_out
```

ECS 샘플 주입:

```bash
cat aivn_sensorpack_nearby_ais/aivn_sensorpack_nearby_ais/test_code/ecs_sample.txt > /tmp/nearby_ais_out
```

천천히 주입:

```bash
while IFS= read -r line; do
  printf '%s\r\n' "$line" > /tmp/nearby_ais_out
  sleep 0.1
done < aivn_sensorpack_nearby_ais/aivn_sensorpack_nearby_ais/test_code/ais_sample.txt
```

반복 송신:

```bash
while true; do
  while IFS= read -r line; do
    printf '%s\r\n' "$line" > /tmp/nearby_ais_out
    sleep 0.1
  done < aivn_sensorpack_nearby_ais/aivn_sensorpack_nearby_ais/test_code/ecs_sample.txt
  sleep 1
done
```

### 테스트 시 주의사항

- `device_type: "auto"`이면 먼저 정상 인식된 문장 타입으로 lock됩니다.
- AIS가 먼저 들어오면 이후 ECS는 파싱되지 않습니다.
- ECS가 먼저 들어오면 이후 AIS는 파싱되지 않습니다.
- 실해역 운영에서는 AIS 장비 또는 ECS 장비 중 하나만 사용한다는 전제에 맞춘 동작입니다.
- 혼합 테스트를 하려면 `device_type`을 `ais` 또는 `ecs`로 고정하고 노드를 재시작하는 편이 안전합니다.

## 12. 샘플 데이터

AIS 예시:

```txt
!AIVDM,1,1,6,A,16SgL50P0r9?>68D73mD:?vSr0RR,0*45
!AIVDO,1,1,6,,B0000003wk?8mP=18D3Q3wwQiP00,0*4D
!AIVDM,2,1,6,A,56TnLd82FJKsHe<f22084Df0eUDpN2222222220N3i3>15?G0=RlWl5Dp888,0*79
```

ECS `!PNSD` 예시:

```txt
!PNSD,=e=<<LLeNL1:2o=BCe5aP14SwiL<<P00006M<uG5h02j09p0W02>0:H0RP2N09h0SP1AS15s0H90058*5C
!PNSD,=e=<<tLteL1:2oC2Ce5r00u4NAL<<@00006M<uCp`FH1TpP0HP1Sc70*25
!PNSD,<<ud<Le=u2:294RCcwF00sIwhd<<@00006M<uF4PH@iR`UkHJih*62
```

긴 샘플은 `aivn_sensorpack_nearby_ais/aivn_sensorpack_nearby_ais/test_code/` 아래 별도 파일로 관리하는 것을 권장합니다.

## 13. 모니터링

```bash
ros2 topic echo /sensor_pack/external/nearby_ais/ship
ros2 interface show aivn_interfaces/msg/NearbyAisShip
ros2 param list /nearby_ais_node
ros2 param get /nearby_ais_node serial_port_name
```

토픽 목록 확인:

```bash
ros2 topic list | grep nearby_ais
```

## 14. 예시 출력

AIS 위치 보고 예시:

```yaml
source_device: ais
parser_type: ivdm
has_ais_position: true
has_ais_static: false
ship_id: "440130580"
ais_message_id: 1
lat_ais: 35.145315
lon_ais: 129.15403333333333
sog_ais: 5.8
cog_ais: 106.4
heading_ais: 511
```

AIS 정적 정보 예시:

```yaml
source_device: ais
parser_type: ivdm
has_ais_position: false
has_ais_static: true
ship_id: "440123456"
ship_name_ais: EXAMPLE TUG
call_sign_ais: D7AB
ship_type_ais: 52
```

ECS ship 예시:

```yaml
source_device: ecs
parser_type: pnsd
has_ecs_ship: true
ship_id: "440112590"
ship_name_ecs: "YONGSEONG(예부선)"
ship_type_ecs: "E002"
lat_ecs: 35.10887
lon_ecs: 129.066165
sog_ecs: 0.0
cog_ecs: 219.3
heading_ecs: 511
device_time_unix: 1733096817
device_time_text: "2024-12-01T23:46:57Z"
```

위 값은 설명용 예시입니다.

## 15. 테스트 실행

현재 패키지 안에 pytest 테스트 파일은 없습니다. `package.xml`에는 테스트 의존성이 선언되어 있지만, 실질적인 자동 테스트 코드는 아직 추가되지 않았습니다.

현재 가능한 최소 검증 절차:

1. `colcon build --packages-select aivn_interfaces aivn_sensorpack_nearby_ais`
2. `source install/setup.bash`
3. `ros2 launch aivn_sensorpack_nearby_ais nearby_ais.launch.py`
4. `ros2 topic echo /sensor_pack/external/nearby_ais/ship`
5. `socat` 포트 생성 후 샘플 데이터 주입

## 16. 에러 및 디버깅

| 상황 | 로그/증상 | 원인 / 조치 |
| --- | --- | --- |
| 시리얼 포트 open 실패 | `Serial open failed:` | 포트 경로 오타, 장비 미연결, 포트 점유 여부 확인 |
| 권한 문제 | `Serial open failed due to permissions:` | `dialout` 그룹 권한 확인 |
| read 실패 | `Serial read error:` | 장비 분리 또는 드라이버 상태 확인, 노드는 재오픈 시도 |
| AIS 체크섬 불일치 | `AIS checksum mismatch:` | 샘플 문장 checksum 확인 |
| ECS 체크섬 불일치 | `ECS checksum mismatch:` | `!PNSD` 원문과 checksum 확인 |
| fragment 미완성 | `parse pending/ignored` | multi-fragment 두 번째 문장까지 넣어야 함 |
| AIS payload 너무 짧음 | `AIS payload too short` | 잘못된 샘플 또는 문장 손상 |
| AIS type 5/24 길이 부족 | `AIS type 5 payload too short`, `AIS type 24 payload too short` | fragment 누락 가능성 확인 |
| ECS payload 문자 오류 | `unsupported ECS payload character` | 문장 인코딩/원문 손상 확인 |
| ECS ship_name 디코드 실패 | `ECS ship_name bit length must be divisible by 8` | payload 형식 확인 |
| auto lock으로 무시됨 | `ignored sentence due to auto-detected device lock` | `device_type=auto` 정책, 노드 재시작 또는 고정 모드 사용 |
| 설정된 타입과 불일치 | `ignored sentence due to configured device_type` | `device_type` 값을 `ais` 또는 `ecs`로 맞춤 |

## 17. 운영 참고 사항

- `device_type=auto`는 첫 번째로 정상 인식된 장비 타입으로 lock됩니다.
- 실운영은 AIS 또는 ECS 중 하나만 연결된다는 전제를 반영한 설계입니다.
- AIS fragment TTL은 `8.0초`입니다.
- AIS 정적 정보 캐시 TTL은 `stale_static_info_sec` 기본값 `600초`입니다.
- AIS는 위치 정보 또는 정적 정보 중 하나라도 유효할 때만 퍼블리시합니다.
- 유효하지 않은 AIS (`position_valid=False`이고 `static_valid=False`)는 drop됩니다.
- ECS는 `!PNSD`만 지원하며, 기존 nearbyship 패키지의 RMC 계열 문장은 통합 노드에서 처리하지 않습니다.
- 실행 구조는 launch argument 중심이 아니라 config 파일 중심입니다.
- `setup.py`의 `install_requires`에는 `pyserial`이 없고, `package.xml`의 `exec_depend`로만 선언되어 있습니다.
- `verbose=true`일 때 5초 주기로 수신 통계 요약을 출력합니다.

## 18. 개선 권장 사항

- `setup.py`의 `install_requires`에 `pyserial`을 명시적으로 추가하는 것이 좋습니다.
- pytest 기반 단위 테스트와 샘플 회귀 테스트를 추가하는 것이 좋습니다.
- `test_code/` 샘플 파일을 package 루트 또는 `samples/` 디렉터리로 정리하면 문서와 실행 경로가 더 명확해집니다.
- `device_type=auto` lock 정책은 현재 구현 의도에 맞지만, 운영자가 혼동하지 않도록 config 주석을 더 보강하는 것이 좋습니다.

## 코드 기준으로 확인한 내용

- 노드명, 토픽명, 메시지 타입, queue depth, 파라미터 기본값
- 지원 입력 문장과 AIS message type
- ECS `!PNSD` 파서 존재와 메시지 매핑
- `device_type=auto` lock 동작
- 샘플 데이터 경로와 `socat` 테스트 메모

## 추정/확인이 필요한 내용

- 작성자 표기는 요청사항에 따라 `박재원`으로 기재했지만, 코드 메타데이터에는 `jaewonpark` / `jaewon.park@aivenautics.com`로 들어 있습니다.
- 배포등급 `내부전용 (Confidential)`은 코드 메타데이터가 아니라 요청사항 기준으로 문서에 반영했습니다.
