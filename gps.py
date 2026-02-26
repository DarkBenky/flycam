from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from typing import Optional

try:
    import serial
except ImportError:
    print("ERROR: pyserial not installed. Run: pip install pyserial", file=sys.stderr)
    sys.exit(1)

PORT = "/dev/ttyS0"   # or /dev/ttyAMA0
BAUD_RATE = 115200
TIMEOUT = 2.0


@dataclass
class GNSSRecord:
    utc_time: Optional[str] = None
    utc_date: Optional[str] = None
    status: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    speed_knots: Optional[float] = None
    course_deg: Optional[float] = None
    fix_quality: Optional[int] = None
    satellites_used: Optional[int] = None
    hdop: Optional[float] = None
    altitude_m: Optional[float] = None
    raw: list[str] = field(default_factory=list)


def _nmea_to_decimal(value: str, hemisphere: str) -> float:
    if not value:
        return 0.0
    dot = value.index(".")
    deg_digits = dot - 2
    degrees = float(value[:deg_digits])
    minutes = float(value[deg_digits:])
    decimal = degrees + minutes / 60.0
    if hemisphere in ("S", "W"):
        decimal = -decimal
    return decimal


def _verify_checksum(sentence: str) -> bool:
    if "*" not in sentence:
        return True
    data, checksum_hex = sentence.rsplit("*", 1)
    data = data.lstrip("$")
    calculated = 0
    for ch in data:
        calculated ^= ord(ch)
    try:
        return calculated == int(checksum_hex.strip(), 16)
    except ValueError:
        return False


def _parse_rmc(fields: list[str], record: GNSSRecord) -> None:
    try:
        raw_time = fields[1]
        if len(raw_time) >= 6:
            record.utc_time = f"{raw_time[0:2]}:{raw_time[2:4]}:{raw_time[4:]}"

        record.status = fields[2]

        if fields[3] and fields[4]:
            record.latitude = _nmea_to_decimal(fields[3], fields[4])
        if fields[5] and fields[6]:
            record.longitude = _nmea_to_decimal(fields[5], fields[6])

        if fields[7]:
            record.speed_knots = float(fields[7])
        if fields[8]:
            record.course_deg = float(fields[8])

        raw_date = fields[9]
        if len(raw_date) == 6:
            record.utc_date = f"{raw_date[0:2]}/{raw_date[2:4]}/{raw_date[4:]}"
    except (IndexError, ValueError):
        pass


def _parse_gga(fields: list[str], record: GNSSRecord) -> None:
    try:
        if fields[6]:
            record.fix_quality = int(fields[6])
        if fields[7]:
            record.satellites_used = int(fields[7])
        if fields[8]:
            record.hdop = float(fields[8])
        if fields[9]:
            record.altitude_m = float(fields[9])
    except (IndexError, ValueError):
        pass


def parse_sentence(line: str, record: GNSSRecord) -> None:
    line = line.strip()
    if not line.startswith("$") or not _verify_checksum(line):
        return
    clean = line.split("*")[0].lstrip("$")
    fields = clean.split(",")
    sentence_id = fields[0].upper()

    if sentence_id in ("GNRMC", "GPRMC"):
        _parse_rmc(fields, record)
    elif sentence_id in ("GNGGA", "GPGGA"):
        _parse_gga(fields, record)


class GPSReader:
    """Persistent NMEA reader — opens the serial port once and streams records.
    Use this in long-running threads instead of read_gps_records, which
    opens and closes the port on every call."""

    def __init__(self, port: str = PORT, baud: int = BAUD_RATE,
                 timeout: float = TIMEOUT) -> None:
        print(f"Opening {port} at {baud} baud …", flush=True)
        try:
            self._ser = serial.Serial(port, baud, timeout=timeout)
        except serial.SerialException as e:
            print(f"ERROR: Cannot open {port}: {e}", file=sys.stderr)
            raise
        self._current = GNSSRecord()
        self._last_rmc_time: Optional[str] = None

    def read_one(self) -> Optional[GNSSRecord]:
        """Block until the next complete NMEA epoch (one full RMC cycle).
        Returns None on serial error; the caller should then close and retry."""
        while True:
            try:
                raw_line = self._ser.readline()
            except serial.SerialException:
                return None
            if not raw_line:
                continue
            try:
                line = raw_line.decode("ascii", errors="replace").strip()
            except Exception:
                continue
            if not line:
                continue

            self._current.raw.append(line)
            parse_sentence(line, self._current)

            if line.startswith(("$GNRMC", "$GPRMC")):
                if (self._last_rmc_time is not None
                        and self._current.utc_time != self._last_rmc_time):
                    completed = self._current
                    self._current = GNSSRecord()
                    self._current.raw.append(line)
                    parse_sentence(line, self._current)
                    self._last_rmc_time = self._current.utc_time
                    return completed
                self._last_rmc_time = self._current.utc_time

    def close(self) -> None:
        try:
            self._ser.close()
        except Exception:
            pass


def read_gps_records(
    count: int = 5,
    port: str = PORT,
    baud: int = BAUD_RATE,
    timeout: float = TIMEOUT,
    require_fix: bool = False,
) -> list[GNSSRecord]:
    records: list[GNSSRecord] = []
    print(f"Opening {port} at {baud} baud …", flush=True)
    try:
        ser_obj = serial.Serial(port, baud, timeout=timeout)
    except serial.SerialException as e:
        print(f"ERROR: Cannot open {port}: {e}", file=sys.stderr)
        sys.exit(1)
    with ser_obj as ser:
        print(f"Waiting for {count} valid GNSS record(s) …\n", flush=True)

        current = GNSSRecord()
        last_rmc_time: Optional[str] = None

        while len(records) < count:
            raw_line = ser.readline()
            if not raw_line:
                continue

            try:
                line = raw_line.decode("ascii", errors="replace").strip()
            except Exception:
                continue

            if not line:
                continue

            current.raw.append(line)
            parse_sentence(line, current)

            if line.startswith(("$GNRMC", "$GPRMC")):
                if last_rmc_time is not None and current.utc_time != last_rmc_time:
                    if not require_fix or current.status == "A":
                        records.append(current)
                        lat = f"{current.latitude:.6f}" if current.latitude is not None else "N/A"
                        lon = f"{current.longitude:.6f}" if current.longitude is not None else "N/A"
                        print(
                            f"[{len(records)}/{count}]  "
                            f"Time={current.utc_time}  "
                            f"Lat={lat}  "
                            f"Lon={lon}  "
                            f"Alt={current.altitude_m}m  "
                            f"Sats={current.satellites_used}"
                        )
                    else:
                        print(f"[skip] No fix (status={current.status!r})  Time={current.utc_time}")
                    current = GNSSRecord()
                    current.raw.append(line)
                    parse_sentence(line, current)

                last_rmc_time = current.utc_time

    return records


if __name__ == "__main__":
    NUM_RECORDS = 5
    try:
        start = time.time()
        data = read_gps_records(count=NUM_RECORDS, require_fix=False)
        print(data)
        elapsed = time.time() - start

        print(f"\nCollected {len(data)} record(s) in {elapsed:.1f}s\n")
        for i, rec in enumerate(data, 1):
            print(f"\nRecord {i}:")
            print(f"  UTC Date/Time : {rec.utc_date} {rec.utc_time}")
            print(f"  Status        : {'Fix OK' if rec.status == 'A' else 'No fix'}")
            print(f"  Latitude      : {rec.latitude}")
            print(f"  Longitude     : {rec.longitude}")
            print(f"  Altitude      : {rec.altitude_m} m")
            print(f"  Speed         : {rec.speed_knots} knots")
            print(f"  Course        : {rec.course_deg}°")
            print(f"  Fix quality   : {rec.fix_quality}")
            print(f"  Satellites    : {rec.satellites_used}")
            print(f"  HDOP          : {rec.hdop}")
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
