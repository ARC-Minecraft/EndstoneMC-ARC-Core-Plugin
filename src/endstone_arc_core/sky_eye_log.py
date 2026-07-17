# -*- coding: utf-8 -*-
"""天眼系统：按日期将玩家行为追加到 plugins/ARCCore/sky_eye/YYYYMMDD.txt，并可按保留天数滚动删除。"""
import re
import threading
from contextlib import suppress
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

_file_lock = threading.Lock()
_last_prune_calendar_date: Optional[date] = None
_date_filename_re = re.compile(r"^(\d{8})\.txt$")


def prune_sky_eye_logs(log_dir: Path, retention_days: int) -> None:
    """删除日期文件名早于「今天 − retention_days」的日志（retention_days<=0 时不删除）。"""
    if retention_days <= 0 or not log_dir.is_dir():
        return
    boundary = date.today() - timedelta(days=retention_days)
    for path in log_dir.iterdir():
        if not path.is_file():
            continue
        match = _date_filename_re.match(path.name)
        if not match:
            continue
        try:
            file_date = datetime.strptime(match.group(1), "%Y%m%d").date()
        except ValueError:
            continue
        if file_date <= boundary:
            try:
                path.unlink()
            except OSError:
                pass


def append_sky_eye_record(
    arc_root: str,
    dir_name: str,
    retention_days: int,
    action: str,
    player_name: str,
    player_xuid: str,
    dimension: str,
    pos_x: float,
    pos_y: float,
    pos_z: float,
    held_item: str,
    detail: str = "",
) -> None:
    """线程安全追加一行；跨日时触发一次滚动清理。"""
    log_root = Path(arc_root) / dir_name
    today = date.today()
    line_ts = datetime.now().isoformat(sep=" ", timespec="seconds")
    detail_s = (detail or "-").replace("\t", " ").replace("\n", " ")
    hand_s = (held_item or "-").replace("\t", " ").replace("\n", " ")
    line = (
        f"{line_ts}\t{action}\tplayer={player_name}\txuid={player_xuid}\t"
        f"dim={dimension}\tpos=({pos_x},{pos_y},{pos_z})\thand={hand_s}\t"
        f"detail={detail_s}\n"
    )
    global _last_prune_calendar_date
    with _file_lock:
        with suppress(OSError):
            log_root.mkdir(parents=True, exist_ok=True)
            if _last_prune_calendar_date != today:
                prune_sky_eye_logs(log_root, retention_days)
                _last_prune_calendar_date = today
            log_path = log_root / f"{today.strftime('%Y%m%d')}.txt"
            with log_path.open("a", encoding="utf-8") as log_file:
                log_file.write(line)
