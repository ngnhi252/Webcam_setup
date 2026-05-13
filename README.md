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

| Phương thức | Endpoint | Chức năng |
| :--- | :--- | :--- |
| **GET** | `/camera/scan` | Quét danh sách các camera khả dụng |
| **POST** | `/camera/connect` | Kết nối camera theo index chỉ định |
| **POST** | `/camera/stream/start` | Bắt đầu luồng stream ngầm |
| **POST** | `/camera/stream/stop` | Dừng luồng stream |
| **GET** | `/camera/stream` | Xem live feed định dạng MJPEG |
| **POST** | `/camera/record/start` | Bắt đầu ghi video (Nhận filename & t_trigger) |
| **POST** | `/camera/record/stop` | Dừng ghi và trả về metadata của session |
| **GET** | `/camera/status` | Kiểm tra trạng thái hiện tại của hệ thống |
