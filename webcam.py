"""
camera_manager.py
=================
Webcam laptop dung de quay video phuc vu gan nhan hanh dong thu cong.

Nhiem vu duy nhat:
  1. Ghi video ra file .avi
  2. Ghi unix_timestamp chinh xac tung frame ra CSV
  3. Chia se t_start chung voi ESP32 de sau nay JOIN CSI data

Pipeline su dung:
  Thu du lieu  : Camera + 3 ESP32 cung bat dau tu t_start
  Gan nhan     : Xem video -> ghi labels.csv (t_start_action, t_end_action, label)
  Tao dataset  : JOIN labels.csv + csi_data.csv theo unix_timestamp
  Train model  : Hoc tu CSI, khong tu video

File output moi session:
  recordings/
  └── session_YYYYMMDD_HHMMSS/
      ├── video.avi          <- xem de gan nhan
      └── frame_times.csv    <- JOIN voi CSI data

frame_times.csv:
  # t_start, 1714201234.000000     <- moc chung voi ESP32
  frame_index, unix_timestamp
  0,           1714201234.123456
  1,           1714201234.156789

DUNG TRONG FASTAPI:
  from camera_manager import router as camera_router
  app.include_router(camera_router)

  Endpoint:
    POST /camera/start  body: { "t_start": 1714201234.0 }
    POST /camera/stop
    GET  /camera/status
"""

import csv
import logging
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2

logger = logging.getLogger(__name__)


# =============================================================================
# CAU HINH
# =============================================================================

class CameraConfig:
    def __init__(
        self,
        device_index: int = 0,     # 0 = webcam tich hop laptop
        width: int = 640,
        height: int = 480,
        fps: int = 30,
        output_dir: str = "recordings",
    ):
        self.device_index = device_index
        self.width        = width
        self.height       = height
        self.fps          = fps
        self.output_dir   = output_dir


# =============================================================================
# CAMERA MANAGER
# =============================================================================

class CameraManager:
    """
    Quan ly webcam: mo camera, ghi video + CSV timestamp theo tung session.

    Cach dung nhanh:
        cam = CameraManager()
        cam.open()

        t_start = time.time()
        # gui t_start cho ca 3 ESP32 truoc khi goi start()
        cam.start(t_start)
        ...
        info = cam.stop()

    Tai sao can t_start chung:
        ESP32 ghi CSI voi unix_timestamp lay tu laptop server.
        Camera cung dung unix_timestamp lay tu laptop server.
        => Cung moc dong ho => co the JOIN 2 file CSV theo thoi gian.

    Tai sao ghi timestamp tung frame thay vi tinh t = t_start + idx/fps:
        FPS webcam laptop khong on dinh (dao dong ±2-5ms/frame).
        Tinh nguoc se tich luy sai so. Ghi thuc te thi chinh xac hon.
    """

    def __init__(self, config: Optional[CameraConfig] = None):
        self.cfg          = config or CameraConfig()
        self._cap         = None
        self._writer      = None
        self._csv_file    = None
        self._csv_writer  = None
        self._thread      = None
        self._running     = False

        # Thong tin session
        self._session_dir  = None
        self._video_path   = None
        self._csv_path     = None
        self._t_start      = None
        self._frame_count  = 0

    # -------------------------------------------------------------------------
    # Mo / dong camera — goi 1 lan khi khoi dong / tat server
    # -------------------------------------------------------------------------

    def open(self) -> bool:
        cap = cv2.VideoCapture(self.cfg.device_index)
        if not cap.isOpened():
            logger.error("Khong mo duoc camera index=%d", self.cfg.device_index)
            return False

        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.cfg.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cfg.height)
        cap.set(cv2.CAP_PROP_FPS,          self.cfg.fps)

        w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        logger.info("Camera mo: %dx%d @ %.0ffps", w, h, fps)

        self._cap = cap
        return True

    def close(self):
        if self._running:
            self.stop()
        if self._cap:
            self._cap.release()
            self._cap = None

    # -------------------------------------------------------------------------
    # Bat dau ghi
    # -------------------------------------------------------------------------

    def start(self, t_start: Optional[float] = None) -> str:
        """
        Bat dau ghi video + frame_times.csv.

        Args:
            t_start: moc thoi gian chung voi ESP32 (unix timestamp, giay).
                     Nen truyen vao gia tri da dung de gui cho ESP32.
                     Neu de None thi tu lay time.time() tai day.

        Returns:
            session_id (ten thu muc) neu thanh cong, chuoi rong neu loi.
        """
        if self._running:
            logger.warning("Dang ghi roi, bo qua.")
            return ""
        if not self.is_open:
            logger.error("Camera chua mo.")
            return ""

        self._t_start     = t_start if t_start is not None else time.time()
        self._frame_count = 0

        # Tao thu muc session
        ts          = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_id  = f"session_{ts}"
        session_dir = Path(self.cfg.output_dir) / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        self._session_dir = session_dir
        self._video_path  = session_dir / "video.avi"
        self._csv_path    = session_dir / "frame_times.csv"

        # VideoWriter — dung XVID/.avi on dinh nhat tren laptop
        w      = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h      = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps    = self._cap.get(cv2.CAP_PROP_FPS) or self.cfg.fps
        fourcc = cv2.VideoWriter_fourcc(*"XVID")

        self._writer = cv2.VideoWriter(str(self._video_path), fourcc, fps, (w, h))
        if not self._writer.isOpened():
            logger.error("Khong tao duoc VideoWriter.")
            return ""

        # CSV: dong dau ghi t_start de tham chieu khi JOIN
        self._csv_file   = open(self._csv_path, "w", newline="", encoding="utf-8")
        self._csv_writer = csv.writer(self._csv_file)
        self._csv_writer.writerow(["# t_start", f"{self._t_start:.6f}"])
        self._csv_writer.writerow(["frame_index", "unix_timestamp"])

        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

        logger.info("Start: %s | t_start=%.6f", session_id, self._t_start)
        return session_id

    # -------------------------------------------------------------------------
    # Dung ghi
    # -------------------------------------------------------------------------

    def stop(self) -> dict:
        """
        Dung ghi, flush file, tra ve thong tin session.

        Returns:
            {
              session_dir, video_path, csv_path,
              t_start, t_end, duration_s, frame_count
            }
        """
        if not self._running:
            return {}

        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

        t_end = time.time()

        if self._writer:
            self._writer.release()
            self._writer = None
        if self._csv_file:
            self._csv_file.close()
            self._csv_file   = None
            self._csv_writer = None

        info = {
            "session_dir": str(self._session_dir),
            "video_path":  str(self._video_path),
            "csv_path":    str(self._csv_path),
            "t_start":     self._t_start,
            "t_end":       t_end,
            "duration_s":  round(t_end - self._t_start, 3),
            "frame_count": self._frame_count,
        }
        logger.info("Stop: %d frames | %.1fs", self._frame_count, info["duration_s"])
        return info

    # -------------------------------------------------------------------------
    # Vong lap ghi — chay trong thread rieng
    # -------------------------------------------------------------------------

    def _loop(self):
        """
        Doc frame tu camera lien tuc, ghi video + timestamp vao CSV.

        Lay time.time() ngay sau cap.read() de timestamp sat voi thoi
        diem thuc te camera chup frame, han che sai so do xu ly.
        """
        while self._running:
            ret, frame = self._cap.read()
            if not ret:
                time.sleep(0.005)
                continue

            ts = time.time()  # timestamp chinh xac tung frame

            self._writer.write(frame)
            self._csv_writer.writerow([self._frame_count, f"{ts:.6f}"])
            self._frame_count += 1

    # -------------------------------------------------------------------------
    # Trang thai
    # -------------------------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    @property
    def is_recording(self) -> bool:
        return self._running


# =============================================================================
# FASTAPI ROUTER
# =============================================================================

try:
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel

    router = APIRouter(prefix="/camera", tags=["camera"])
    _cam   = CameraManager()

    class StartBody(BaseModel):
        t_start: float  # unix_timestamp tinh o server, da gui cho ESP32

    @router.on_event("startup")
    async def _startup():
        _cam.open()

    @router.on_event("shutdown")
    async def _shutdown():
        _cam.close()

    @router.post("/start")
    async def api_start(body: StartBody):
        """
        Bat dau ghi. Goi sau khi da gui t_start cho ESP32.
        t_start phai la cung gia tri da gui cho ESP32.
        """
        sid = _cam.start(t_start=body.t_start)
        if not sid:
            raise HTTPException(500, "Khong the bat dau ghi.")
        return {"session_id": sid, "t_start": body.t_start}

    @router.post("/stop")
    async def api_stop():
        info = _cam.stop()
        if not info:
            raise HTTPException(400, "Khong co session dang chay.")
        return info

    @router.get("/status")
    async def api_status():
        return {
            "is_open":      _cam.is_open,
            "is_recording": _cam.is_recording,
            "frame_count":  _cam._frame_count,
            "t_start":      _cam._t_start,
        }

except ImportError:
    router = None  # chay doc lap khong can fastapi


# =============================================================================
# TEST THU CONG
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level  = logging.INFO,
        format = "%(asctime)s [%(levelname)s] %(message)s",
    )

    cam = CameraManager(CameraConfig(device_index=0))
    if not cam.open():
        raise SystemExit("Khong mo duoc camera.")

    # Trong thuc te: tinh t_start o server roi gui cho ca ESP32 lan camera
    t_start = time.time()
    print(f"\nt_start = {t_start:.6f}")
    print("(Gia tri nay can duoc gui cho ESP32 truoc khi ghi)")
    print("\nENTER -> bat dau ghi")
    input()

    sid = cam.start(t_start=t_start)
    print(f"Dang ghi: {sid}")
    print("ENTER -> dung ghi")
    input()

    info = cam.stop()
    print("\nKet qua session:")
    for k, v in info.items():
        print(f"  {k}: {v}")

    cam.close()