I. Tổng quan kiến trúc
  CameraConfig  →  cấu hình khởi tạo
  CameraInfo    →  DTO kết quả scan
  CameraManager →  logic chính (scan/connect/stream/record)
  FastAPI router→  HTTP API wrapper
II. Các chức năng đã làm được
  A. Scan camera
    •	Thử mở lần lượt index 0–9 bằng cv2.VideoCapture(i)
    •	Đọc thông số thực tế: resolution, FPS
    •	Trả về list CameraInfo, tự phân biệt built-in (index 0) vs USB (index ≥ 1)
  B. Connect + Warm-up
    •	Set resolution/FPS theo CameraConfig
    •	Warm-up 30 frame để camera ổn định sensor/exposure trước khi ghi thật
    •	Tự disconnect() camera cũ nếu đang kết nối trước khi connect mới
  C. Stream preview (MJPEG) - cho phép xem camera trước khi record thật
    •	Chạy _stream_loop trên thread riêng, lưu frame mới nhất vào _latest_frame
    •	get_jpeg_frame() encode sang JPEG bytes để phục vụ endpoint MJPEG
    •	Browser hoặc <img> tag có thể xem trực tiếp qua GET /camera/stream
  D. Record 
    Ghi video.avi bằng codec XVID
    •	Ghi frame_times.csv với 4 cột: frame_index, relative_ms, unix_timestamp, datetime
    •	Hỗ trợ t_trigger — mốc thời gian chung với ESP32: 
      o	Nếu truyền vào: relative_ms tính từ mốc đó (có thể âm nếu camera bắt đầu muộn hơn)
      o	Nếu không truyền: tự lấy timestamp frame đầu tiên làm mốc
    •	Ghi comment # t_trigger,... ở đầu CSV để truy vết mốc đồng bộ
    •	Dùng utf-8-sig (BOM) + ghi thủ công từng dòng — tránh Excel tự parse số/ngày sai
    •	Overlay timestamp lên góc dưới frame video (để xem video biết frame nào ứng thời điểm nào)
    •	Vừa record vừa cập nhật _latest_frame → MJPEG stream vẫn hoạt động song song
  E. FastAPI REST API
    Endpoint:	Chức năng
    GET /camera/scan:	Quét camera
    POST /camera/connect:	Kết nối theo index
    POST /camera/stream/start:	Bắt đầu stream
    POST /camera/stream/stop:	Dừng stream
    GET /camera/stream:	MJPEG live feed
    POST /camera/record/start:	Bắt đầu ghi, nhận filename + t_trigger
    POST /camera/record/stop:	Dừng ghi, trả về metadata session
    GET /camera/status:	Trạng thái hiện tại

  
