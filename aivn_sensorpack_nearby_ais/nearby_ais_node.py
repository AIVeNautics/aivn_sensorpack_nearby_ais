from __future__ import annotations

from dataclasses import dataclass
import errno
import time
from typing import Dict, Optional

from aivn_interfaces.msg import NearbyAisShip
import rclpy
from rclpy.node import Node
import serial

from .ais_nmea_parser import AisDecoded, AisNmeaParser
from .ecs_parser import EcsDecoded, parse_ecs_sentence


@dataclass
class _AisStaticInfo:
    ship_name: str = ""
    call_sign: str = ""
    ship_type: int = 0
    updated_monotonic: float = 0.0


class NearbyAisNode(Node):
    def __init__(self) -> None:
        super().__init__("nearby_ais_node")

        self.declare_parameter("serial_port_name", "/dev/ttyUSB0")
        self.declare_parameter("baud_rate", 38400)
        self.declare_parameter("data_bits", 8)
        self.declare_parameter("parity", "NONE")
        self.declare_parameter("stop_bits", 1)
        self.declare_parameter("xonxoff", False)
        self.declare_parameter("rtscts", False)
        self.declare_parameter("dsrdtr", False)
        self.declare_parameter("topic_name", "/sensor_pack/external/nearby_ais/ship")
        self.declare_parameter("frame_id", "nearby_ais")
        self.declare_parameter("device_type", "auto")
        self.declare_parameter("checksum_required", True)
        self.declare_parameter("poll_period_sec", 0.005)
        self.declare_parameter("read_size", 8192)
        self.declare_parameter("reconnect_sec", 2.0)
        self.declare_parameter("stale_static_info_sec", 600.0)
        self.declare_parameter("no_data_warn_sec", 0.0)
        self.declare_parameter("no_sentence_warn_sec", 0.0)
        self.declare_parameter("verbose", False)
        self.declare_parameter("log_rx_sentence", False)
        self.declare_parameter("log_parse_result", True)
        self.declare_parameter("debug_hex_dump", False)
        self.declare_parameter("debug_hex_limit", 64)
        self.declare_parameter("debug_publish_reason", False)
        self.declare_parameter("debug_fragment", False)

        self.port = str(self.get_parameter("serial_port_name").value)
        self.baud = int(self.get_parameter("baud_rate").value)
        self.topic_name = str(self.get_parameter("topic_name").value)
        self.frame_id = str(self.get_parameter("frame_id").value)
        self.device_type = self._parse_device_type(str(self.get_parameter("device_type").value))
        self.checksum_required = bool(self.get_parameter("checksum_required").value)
        self.data_bits = self._parse_data_bits(int(self.get_parameter("data_bits").value))
        self.parity = self._parse_parity(str(self.get_parameter("parity").value))
        self.stop_bits = self._parse_stop_bits(float(self.get_parameter("stop_bits").value))
        self.xonxoff = bool(self.get_parameter("xonxoff").value)
        self.rtscts = bool(self.get_parameter("rtscts").value)
        self.dsrdtr = bool(self.get_parameter("dsrdtr").value)
        poll_period = float(self.get_parameter("poll_period_sec").value)
        self.read_size = int(self.get_parameter("read_size").value)
        self.reconnect_sec = float(self.get_parameter("reconnect_sec").value)
        self.stale_static_info_sec = float(self.get_parameter("stale_static_info_sec").value)
        self.no_data_warn_sec = float(self.get_parameter("no_data_warn_sec").value)
        self.no_sentence_warn_sec = float(self.get_parameter("no_sentence_warn_sec").value)
        self.verbose = bool(self.get_parameter("verbose").value)
        self.log_rx_sentence = bool(self.get_parameter("log_rx_sentence").value)
        self.log_parse_result = bool(self.get_parameter("log_parse_result").value)
        self.debug_hex_dump = bool(self.get_parameter("debug_hex_dump").value)
        self.debug_hex_limit = int(self.get_parameter("debug_hex_limit").value)
        self.debug_publish_reason = bool(self.get_parameter("debug_publish_reason").value)
        self.debug_fragment = bool(self.get_parameter("debug_fragment").value)

        parser_debug_cb = self._debug_fragment if self.debug_fragment else None
        self.ais_parser = AisNmeaParser(
            checksum_required=self.checksum_required,
            debug_cb=parser_debug_cb,
        )
        self.publisher_ = self.create_publisher(NearbyAisShip, self.topic_name, 100)

        self.ser: Optional[serial.Serial] = None
        self._last_open_attempt = 0.0
        self._raw_buf = bytearray()
        self._static_by_mmsi: Dict[int, _AisStaticInfo] = {}
        self._locked_device_type: Optional[str] = None
        self._last_summary_time = time.monotonic()
        self._last_rx_monotonic = 0.0
        self._last_no_data_warn_monotonic = 0.0
        self._last_no_sentence_warn_monotonic = 0.0
        self.stats = {
            "rx_bytes": 0,
            "rx_sentences": 0,
            "ais_published": 0,
            "ecs_published": 0,
            "decoded_err": 0,
        }

        self.timer = self.create_timer(poll_period, self._poll_serial)
        self.get_logger().info(
            "Nearby AIS node publishing "
            f"{self.topic_name}; port={self.port}, baud={self.baud}, "
            f"device_type={self.device_type}, "
            f"data_bits={self._data_bits_label()}, parity={self._parity_label()}, "
            f"stop_bits={self._stop_bits_label()}, xonxoff={self.xonxoff}, "
            f"rtscts={self.rtscts}, dsrdtr={self.dsrdtr}"
        )

    def destroy_node(self) -> bool:
        self._close_serial()
        return super().destroy_node()

    def _open_serial_if_needed(self) -> bool:
        if self.ser is not None and self.ser.is_open:
            return True

        now = time.monotonic()
        if now - self._last_open_attempt < self.reconnect_sec:
            return False
        self._last_open_attempt = now

        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baud,
                bytesize=self.data_bits,
                parity=self.parity,
                stopbits=self.stop_bits,
                timeout=0,
                xonxoff=self.xonxoff,
                rtscts=self.rtscts,
                dsrdtr=self.dsrdtr,
            )
            self._last_rx_monotonic = time.monotonic()
            self._last_no_data_warn_monotonic = 0.0
            self._last_no_sentence_warn_monotonic = 0.0
            self.get_logger().info(
                "Opened serial: "
                f"{self.port} ({self.baud} {self._data_bits_label()}"
                f"{self._parity_label()}{self._stop_bits_label()}, "
                f"xonxoff={self.xonxoff}, rtscts={self.rtscts}, dsrdtr={self.dsrdtr})"
            )
            return True
        except Exception as exc:
            self.ser = None
            if self._is_permission_error(exc):
                self.get_logger().warn(
                    "Serial open failed due to permissions: "
                    f"{exc}. Check access permissions for {self.port}."
                )
            else:
                self.get_logger().warn(f"Serial open failed: {exc}")
            return False

    def _close_serial(self) -> None:
        if self.ser is None:
            return
        try:
            self.ser.close()
        except Exception:
            pass
        self.ser = None

    def _poll_serial(self) -> None:
        if not self._open_serial_if_needed():
            return

        try:
            data = self.ser.read(self.read_size)
            if data:
                self._raw_buf += data
                self.stats["rx_bytes"] += len(data)
                self._last_rx_monotonic = time.monotonic()
                self._log_hex_dump(data)

            for line_bytes in self._extract_complete_lines():
                sentence = line_bytes.decode("ascii", errors="ignore").strip()
                if not sentence:
                    continue
                self.stats["rx_sentences"] += 1
                self._log_rx_sentence(sentence)
                self._handle_sentence(sentence)

            self._log_summary()
            self._log_no_data_warning()
            self._log_no_sentence_warning()
        except Exception as exc:
            self.get_logger().error(f"Serial read error: {exc}")
            self._close_serial()

    def _extract_complete_lines(self) -> list[bytes]:
        out: list[bytes] = []
        buf = self._raw_buf
        while True:
            newline_idx = buf.find(b"\n")
            if newline_idx == -1:
                break
            line = bytes(buf[:newline_idx]).rstrip(b"\r")
            del buf[:newline_idx + 1]
            out.append(line)
        return out

    def _handle_sentence(self, sentence: str) -> None:
        if sentence.startswith(("!AIVDM", "!AIVDO")):
            if not self._allow_device("ais"):
                return
            try:
                decoded = self.ais_parser.parse_sentence(sentence)
                if decoded is None:
                    self._log_parse_pending(sentence)
                    return
                self._lock_device_type("ais")
                self._log_ais_parse_success(decoded)
                self._handle_ais_decoded(decoded)
            except Exception as exc:
                self.stats["decoded_err"] += 1
                self._log_parse_failure(sentence, exc)
            return

        if sentence.startswith("!PNSD"):
            if not self._allow_device("ecs"):
                return
            try:
                decoded = parse_ecs_sentence(sentence, checksum_required=self.checksum_required)
                if decoded is None:
                    return
                self._lock_device_type("ecs")
                self._log_ecs_parse_success(decoded)
                self._publish_ecs(decoded)
            except Exception as exc:
                self.stats["decoded_err"] += 1
                self._log_parse_failure(sentence, exc)
            return

    def _allow_device(self, incoming_device: str) -> bool:
        if self.device_type == "auto":
            allowed = self._locked_device_type in (None, incoming_device)
            if not allowed and self.log_parse_result:
                self.get_logger().info(
                    "Nearby AIS ignored sentence due to auto-detected device lock: "
                    f"locked_device_type={self._locked_device_type} incoming_device={incoming_device}"
                )
            return allowed
        allowed = self.device_type == incoming_device
        if not allowed and self.log_parse_result:
            self.get_logger().info(
                "Nearby AIS ignored sentence due to configured device_type: "
                f"configured_device_type={self.device_type} incoming_device={incoming_device}"
            )
        return allowed

    def _lock_device_type(self, incoming_device: str) -> None:
        if self.device_type == "auto" and self._locked_device_type is None:
            self._locked_device_type = incoming_device
            self.get_logger().info(f"Auto-detected nearby_ais device_type={incoming_device}")

    def _handle_ais_decoded(self, decoded: AisDecoded) -> None:
        now_monotonic = time.monotonic()

        if decoded.static_valid:
            current = self._static_by_mmsi.get(decoded.mmsi, _AisStaticInfo())
            if decoded.ship_name:
                current.ship_name = decoded.ship_name
            if decoded.call_sign:
                current.call_sign = decoded.call_sign
            if decoded.ship_type:
                current.ship_type = decoded.ship_type
            current.updated_monotonic = now_monotonic
            self._static_by_mmsi[decoded.mmsi] = current

        static_info = self._static_by_mmsi.get(decoded.mmsi)
        if static_info and now_monotonic - static_info.updated_monotonic <= self.stale_static_info_sec:
            if not decoded.ship_name:
                decoded.ship_name = static_info.ship_name
            if not decoded.call_sign:
                decoded.call_sign = static_info.call_sign
            if not decoded.ship_type:
                decoded.ship_type = static_info.ship_type
            decoded.static_valid = decoded.static_valid or bool(
                decoded.ship_name or decoded.call_sign or decoded.ship_type
            )

        if not decoded.position_valid and not decoded.static_valid:
            if self.debug_publish_reason or self.log_parse_result:
                self.get_logger().info(
                    "AIS decoded message dropped before publish: "
                    f"msg_id={decoded.ais_message_id} mmsi={decoded.mmsi} "
                    f"position_valid={decoded.position_valid} static_valid={decoded.static_valid}"
                )
            return

        msg = self._ais_to_msg(decoded)
        self.publisher_.publish(msg)
        self.stats["ais_published"] += 1
        self._log_publish_result(msg)

    def _publish_ecs(self, decoded: EcsDecoded) -> None:
        msg = NearbyAisShip()
        now = self.get_clock().now()
        msg.header.stamp = now.to_msg()
        msg.header.frame_id = self.frame_id
        msg.source_device = "ecs"
        msg.parser_type = decoded.parser_type
        msg.source_port = self.port
        msg.original_sentence = decoded.original_sentence
        msg.has_ecs_ship = True
        msg.server_receive_time_unix = int(now.nanoseconds // 1_000_000_000)
        msg.device_time_unix = int(decoded.receiving_time_unix)
        msg.device_time_text = decoded.receiving_time_text
        msg.ship_id = decoded.ship_id
        msg.ship_name_ecs = decoded.ship_name
        msg.ship_type_ecs = decoded.ship_type
        msg.comm_net_ecs = decoded.comm_net
        msg.power_source_ecs = decoded.power_source
        msg.uc_num_ecs = int(decoded.uc_num)
        msg.lat_ecs = float(decoded.lat)
        msg.lon_ecs = float(decoded.lon)
        msg.sog_ecs = float(decoded.sog)
        msg.cog_ecs = float(decoded.cog)
        msg.heading_ecs = int(decoded.heading)
        self.publisher_.publish(msg)
        self.stats["ecs_published"] += 1
        self._log_publish_result(msg)

    def _ais_to_msg(self, decoded: AisDecoded) -> NearbyAisShip:
        msg = NearbyAisShip()
        now = self.get_clock().now()
        msg.header.stamp = now.to_msg()
        msg.header.frame_id = self.frame_id
        msg.source_device = "ais"
        msg.parser_type = decoded.parser_type
        msg.source_port = self.port
        msg.original_sentence = decoded.original_sentence
        msg.has_ais_position = bool(decoded.position_valid)
        msg.has_ais_static = bool(decoded.static_valid)
        msg.server_receive_time_unix = int(now.nanoseconds // 1_000_000_000)
        msg.ais_message_id = int(decoded.ais_message_id)
        msg.ais_mmsi = int(decoded.mmsi)
        msg.ship_id = decoded.ship_id or str(decoded.mmsi)
        msg.ship_name_ais = decoded.ship_name
        msg.call_sign_ais = decoded.call_sign
        msg.ship_type_ais = int(decoded.ship_type)
        msg.navigation_status_ais = int(decoded.navigation_status)
        msg.lat_ais = float(decoded.lat)
        msg.lon_ais = float(decoded.lon)
        msg.sog_ais = float(decoded.sog)
        msg.cog_ais = float(decoded.cog)
        msg.heading_ais = int(decoded.heading)
        return msg

    @staticmethod
    def _is_permission_error(exc: Exception) -> bool:
        err_no = getattr(exc, "errno", None)
        if err_no == errno.EACCES:
            return True
        return "Permission denied" in str(exc)

    @staticmethod
    def _parse_device_type(value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in {"auto", "ais", "ecs"}:
            raise ValueError(f"unsupported device_type: {value!r}")
        return normalized

    @staticmethod
    def _parse_data_bits(value: int) -> int:
        mapping = {
            5: serial.FIVEBITS,
            6: serial.SIXBITS,
            7: serial.SEVENBITS,
            8: serial.EIGHTBITS,
        }
        if value not in mapping:
            raise ValueError(f"unsupported data_bits: {value}")
        return mapping[value]

    @staticmethod
    def _parse_parity(value: str) -> str:
        normalized = (value or "").strip().upper()
        mapping = {
            "N": serial.PARITY_NONE,
            "NONE": serial.PARITY_NONE,
            "E": serial.PARITY_EVEN,
            "EVEN": serial.PARITY_EVEN,
            "O": serial.PARITY_ODD,
            "ODD": serial.PARITY_ODD,
            "M": serial.PARITY_MARK,
            "MARK": serial.PARITY_MARK,
            "S": serial.PARITY_SPACE,
            "SPACE": serial.PARITY_SPACE,
        }
        if normalized not in mapping:
            raise ValueError(f"unsupported parity: {value!r}")
        return mapping[normalized]

    @staticmethod
    def _parse_stop_bits(value: float) -> float:
        mapping = {
            1.0: serial.STOPBITS_ONE,
            1.5: serial.STOPBITS_ONE_POINT_FIVE,
            2.0: serial.STOPBITS_TWO,
        }
        normalized = round(float(value), 1)
        if normalized not in mapping:
            raise ValueError(f"unsupported stop_bits: {value}")
        return mapping[normalized]

    def _data_bits_label(self) -> int:
        reverse = {
            serial.FIVEBITS: 5,
            serial.SIXBITS: 6,
            serial.SEVENBITS: 7,
            serial.EIGHTBITS: 8,
        }
        return reverse[self.data_bits]

    def _parity_label(self) -> str:
        reverse = {
            serial.PARITY_NONE: "N",
            serial.PARITY_EVEN: "E",
            serial.PARITY_ODD: "O",
            serial.PARITY_MARK: "M",
            serial.PARITY_SPACE: "S",
        }
        return reverse[self.parity]

    def _stop_bits_label(self) -> str:
        reverse = {
            serial.STOPBITS_ONE: "1",
            serial.STOPBITS_ONE_POINT_FIVE: "1.5",
            serial.STOPBITS_TWO: "2",
        }
        return reverse[self.stop_bits]

    def _log_summary(self) -> None:
        now = time.monotonic()
        if not self.verbose or now - self._last_summary_time < 5.0:
            return
        self._last_summary_time = now
        self.get_logger().info(
            "Nearby AIS summary: "
            f"bytes={self.stats['rx_bytes']} "
            f"sentences={self.stats['rx_sentences']} "
            f"ais_published={self.stats['ais_published']} "
            f"ecs_published={self.stats['ecs_published']} "
            f"decoded_err={self.stats['decoded_err']}"
        )

    def _log_rx_sentence(self, sentence: str) -> None:
        if self.log_rx_sentence:
            self.get_logger().info(f"Nearby AIS RX: {sentence}")

    def _log_parse_pending(self, sentence: str) -> None:
        if self.log_parse_result:
            self.get_logger().info(
                "Nearby AIS parse pending/ignored: "
                f"fragment assembly still in progress or unsupported sentence / raw={sentence}"
            )

    def _log_ais_parse_success(self, decoded: AisDecoded) -> None:
        if self.log_parse_result:
            self.get_logger().info(
                "Nearby AIS parse success: "
                f"source=ais msg_id={decoded.ais_message_id} "
                f"mmsi={decoded.mmsi} "
                f"position_valid={decoded.position_valid} "
                f"static_valid={decoded.static_valid}"
            )

    def _log_ecs_parse_success(self, decoded: EcsDecoded) -> None:
        if self.log_parse_result:
            self.get_logger().info(
                "Nearby AIS parse success: "
                f"source=ecs ship_id={decoded.ship_id} "
                f"lat={decoded.lat:.6f} lon={decoded.lon:.6f}"
            )

    def _log_parse_failure(self, sentence: str, exc: Exception) -> None:
        if self.log_parse_result:
            self.get_logger().warn(f"Nearby AIS parse failure: raw={sentence} error={exc}")

    def _log_publish_result(self, msg: NearbyAisShip) -> None:
        if self.debug_publish_reason:
            self.get_logger().info(
                "Nearby AIS publishing message: "
                f"source_device={msg.source_device} ship_id={msg.ship_id} "
                f"has_ais_position={msg.has_ais_position} "
                f"has_ais_static={msg.has_ais_static} "
                f"has_ecs_ship={msg.has_ecs_ship}"
            )

    def _log_hex_dump(self, data: bytes) -> None:
        if not self.debug_hex_dump or not data:
            return
        preview = data[: self.debug_hex_limit]
        hex_text = " ".join(f"{byte:02X}" for byte in preview)
        ascii_text = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in preview)
        suffix = "..." if len(data) > len(preview) else ""
        self.get_logger().info(f"Nearby AIS RX bytes hex={hex_text}{suffix} ascii={ascii_text}{suffix}")

    def _log_no_data_warning(self) -> None:
        if self.no_data_warn_sec <= 0.0 or self._last_rx_monotonic <= 0.0:
            return
        now = time.monotonic()
        if now - self._last_rx_monotonic < self.no_data_warn_sec:
            return
        if now - self._last_no_data_warn_monotonic < self.no_data_warn_sec:
            return
        self._last_no_data_warn_monotonic = now
        self.get_logger().warn(f"No serial data received for {self.no_data_warn_sec:.1f}s on {self.port}")

    def _log_no_sentence_warning(self) -> None:
        if self.no_sentence_warn_sec <= 0.0:
            return
        if not self._raw_buf:
            return
        now = time.monotonic()
        if self._last_rx_monotonic <= 0.0:
            return
        if now - self._last_rx_monotonic < self.no_sentence_warn_sec:
            return
        if now - self._last_no_sentence_warn_monotonic < self.no_sentence_warn_sec:
            return
        self._last_no_sentence_warn_monotonic = now
        self.get_logger().warn(
            "Serial bytes are arriving but no complete sentence was extracted "
            f"for {self.no_sentence_warn_sec:.1f}s on {self.port}"
        )

    def _debug_fragment(self, message: str) -> None:
        self.get_logger().info(f"Nearby AIS fragment: {message}")


def main() -> None:
    rclpy.init()
    node = NearbyAisNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
