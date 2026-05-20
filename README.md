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

| Method | Endpoint | Chức năng | Request Body | Response 200 | Response lỗi | Ghi chú |
|--------|----------|-----------|--------------|--------------|--------------|---------|
| GET | `/camera/scan` | Quét danh sách camera khả dụng | _(không cần)_ | `{ "cameras": [{ "index": 0, "name": "Camera 0 (built-in)", "width": 640, "height": 480, "fps": 30 }] }` | — | Dùng `index` từ response để gọi `/camera/connect` |
| POST | `/camera/connect` | Kết nối camera theo index chỉ định | `{ "device_index": 0 }` | `{ "connected": true, "device_index": 0 }` | 500: `{ "detail": "Khong ket noi duoc camera index=0" }` | Tự ngắt camera cũ nếu đang kết nối |
| POST | `/camera/stream/start` | Bắt đầu luồng stream ngầm | _(không cần)_ | `{ "streaming": true }` | 500: `{ "detail": "Khong the bat dau stream." }` | Phải gọi trước khi hiển thị `<img src="/camera/stream">` |
| POST | `/camera/stream/stop` | Dừng luồng stream | _(không cần)_ | `{ "streaming": false }` | — | Gọi khi ẩn preview hoặc trước khi disconnect |
| GET | `/camera/stream` | Xem live feed định dạng MJPEG | _(không cần)_ | `multipart/x-mixed-replace` stream | — | Dùng trực tiếp: `<img src="http://localhost:8000/camera/stream">`. Stream chạy khi `is_streaming` hoặc `is_recording` = true |
| POST | `/camera/record/start` | Bắt đầu ghi video + CSV timestamp | `{ "filename": "session_walk_01", "t_trigger": 1714201234.000000 }` | `{ "recording": true, "filename": "session_walk_01", "t_trigger": 1714201234.0 }` | 500: `{ "detail": "Khong the bat dau ghi." }` | `t_trigger` là Unix timestamp (float), phải trùng với giá trị đã gửi ESP32. Nếu bỏ qua, server tự lấy timestamp frame đầu |
| POST | `/camera/record/stop` | Dừng ghi và trả về metadata session | _(không cần)_ | `{ "session_dir": "recordings/session_walk_01", "video_path": "recordings/session_walk_01/video.avi", "csv_path": "recordings/session_walk_01/frame_times.csv", "t_trigger": 1714201234.0, "t_end": 1714201267.123, "duration_s": 33.123, "frame_count": 994 }` | 400: `{ "detail": "Khong co session dang ghi." }` | Flush toàn bộ file video + CSV trước khi trả về |
| GET | `/camera/status` | Kiểm tra trạng thái hiện tại | _(không cần)_ | `{ "is_connected": true, "is_streaming": false, "is_recording": true, "device_index": 0, "frame_count": 312, "t_trigger": 1714201234.0 }` | — | Poll mỗi 1–2s để enable/disable nút trên UI theo `is_connected`, `is_streaming`, `is_recording` |
