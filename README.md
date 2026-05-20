# Webcam Setup System

## I. Tổng quan kiến trúc
*   **CameraConfig** → Cấu hình khởi tạo (Resolution, FPS, Index).
*   **CameraInfo** → Đối tượng dữ liệu (DTO) chứa kết quả sau khi quét thiết bị.
*   **CameraManager** → Luồng logic chính điều khiển phần cứng (Scan, Connect, Stream, Record).
*   **FastAPI router** → Lớp vỏ bọc (HTTP API Wrapper) giúp điều khiển qua giao diện Web.

---

## II. Các chức năng đã triển khai

### A. Quét thiết bị (Scan camera)
*   Tự động thử mở lần lượt các index từ **0–9** bằng `cv2.VideoCapture(i)`.
*   Truy xuất thông số kỹ thuật thực tế từ phần cứng: **Resolution** và **FPS**.
*   Phân loại thiết bị thông minh:
    *   **Built-in Camera**: Mặc định là index 0.
    *   **USB Camera**: Các index từ 1 trở đi.

### B. Kết nối & Khởi tạo (Connect + Warm-up)
*   Thiết lập thông số hình ảnh theo cấu hình `CameraConfig`.
*   **Warm-up 30 frame**: Cho phép cảm biến camera ổn định độ phơi sáng (exposure) và cân bằng trắng trước khi bắt đầu ghi dữ liệu chính thức.
*   Quản lý tài nguyên: Tự động `disconnect()` camera cũ đang hoạt động trước khi thiết lập kết nối mới.

### C. Xem trực tiếp (Stream preview - MJPEG)
*   **Multi-threading**: Chạy vòng lặp `_stream_loop` trên một luồng riêng biệt để không gây treo ứng dụng.
*   Cập nhật liên tục khung hình mới nhất vào biến `_latest_frame`.
*   Mã hóa hình ảnh sang định dạng **JPEG bytes** phục vụ giao thức MJPEG.
*   Hỗ trợ xem trực tiếp trên trình duyệt thông qua thẻ `<img>` tại endpoint `GET /camera/stream`.

### D. Ghi hình dữ liệu (Record)
*   Lưu video định dạng `.avi` sử dụng codec **XVID**.
*   Xuất tệp nhật ký `frame_times.csv` chi tiết gồm 4 cột: `frame_index`, `relative_ms`, `unix_timestamp`, `datetime`.
*   **Đồng bộ hóa (t_trigger)**: 
    *   Hỗ trợ mốc thời gian chung với ESP32.
    *   Tính toán thời gian tương đối (`relative_ms`) chính xác theo mốc trigger được truyền vào.
*   **Độ tin cậy dữ liệu**:
    *   Ghi chú mốc đồng bộ `# t_trigger` ở đầu file CSV.
    *   Sử dụng định dạng **utf-8-sig (BOM)** và cơ chế ghi thủ công từng dòng để đảm bảo hiển thị đúng trên Excel.
*   **Video Overlay**: Chèn trực tiếp Timestamp lên góc dưới khung hình video để đối chiếu dữ liệu ngoại tuyến.
*   Duy trì luồng MJPEG hoạt động song song ngay cả khi đang ghi hình.

---

## III. Danh mục API (FastAPI Endpoints)

| Method | Endpoint | Mô tả | Request Body | Response thành công | Ghi chú |
|--------|----------|-------|--------------|---------------------|---------|
| GET | `/camera/scan` | Quét camera khả dụng | — | `{ "cameras": [{ "index": 0, "name": "Camera 0 (built-in)", "width": 640, "height": 480, "fps": 30 }] }` | Lấy `index` từ đây để dùng cho `/camera/connect` |
| POST | `/camera/connect` | Kết nối camera | `{ "device_index": 0 }` | `{ "connected": true, "device_index": 0 }` | Tự ngắt camera cũ trước khi kết nối |
| POST | `/camera/stream/start` | Bật stream | — | `{ "streaming": true }` | Gọi trước khi hiển thị live feed |
| POST | `/camera/stream/stop` | Tắt stream | — | `{ "streaming": false }` | — |
| GET | `/camera/stream` | Live feed MJPEG | — | MJPEG stream | Dùng trực tiếp làm `src` của thẻ `<img>`, không cần fetch |
| POST | `/camera/record/start` | Bắt đầu ghi | `{ "filename": "session_walk_01", "t_trigger": 1714201234.0 }` | `{ "recording": true, "filename": "session_walk_01", "t_trigger": 1714201234.0 }` | `t_trigger` là Unix timestamp (float), phải trùng với giá trị đã gửi ESP32. Có thể bỏ qua, server tự lấy timestamp frame đầu |
| POST | `/camera/record/stop` | Dừng ghi | — | `{ "session_dir": "recordings/session_walk_01", "video_path": "...", "csv_path": "...", "t_trigger": ..., "t_end": ..., "duration_s": 33.1, "frame_count": 994 }` | Output gồm `video.avi` + `frame_times.csv` trong thư mục `recordings/<filename>/` |
| GET | `/camera/status` | Trạng thái hệ thống | — | `{ "is_connected": true, "is_streaming": false, "is_recording": true, "device_index": 0, "frame_count": 312, "t_trigger": ... }` | Poll định kỳ để enable/disable nút UI theo `is_connected`, `is_streaming`, `is_recording` |
