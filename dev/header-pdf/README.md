# Bộ đề tiêu đề chạy / số trang (`dev/header-pdf`)

Bộ đề do dự án **tự sinh hoàn toàn** (không chứa tài liệu của bên thứ ba): 10 tệp PDF khoa học giả lập, mỗi tệp 5 trang, chữ tiếng Anh, font DejaVu Sans (giấy phép tự do) nhúng qua matplotlib. Dùng để kiểm tra lỗi **ảnh tách ra dính tiêu đề chạy (running head) hoặc số trang**, và để chắc rằng bản sửa không cắt hụt hình.

Bố cục mô phỏng các thói quen dàn trang hay gây lỗi trong DocLayNet:

- hình nổi ở đầu cột/trang ngay dưới tiêu đề chạy;
- hình xuất kèm khung trắng rộng, nên khung đặt hình chạm vào dải tiêu đề;
- số trang đứng riêng ở góc trên;
- sách/luận văn có lề trên sâu, tiêu đề chạy nằm thấp hơn 10% chiều cao trang, có khi kèm đường kẻ;
- hình ở cuối trang ngay trên số trang ở chân trang.

Mỗi tệp đều có **trang đối chứng**: hình giữa trang, tiêu đề panel hoặc vạch chia trục ngay trên vùng vẽ, để bản sửa kiểu "cắt bỏ phần trên của mọi ảnh" bị phát hiện.

## Tệp

| Tệp | Nội dung |
|---|---|
| `01_…pdf` … `10_…pdf` | 10 tệp đề |
| `truth.json` | Đáp án do bộ sinh ghi ra: vị trí tiêu đề chạy/số trang và khung từng hình trên mỗi trang |
| `baseline_v1.1.22_report.json`, `baseline_v1.1.22.sha256` | Mốc đã chốt trước khi sửa (v1.1.22): 42 ảnh, 18 ảnh dính tiêu đề/số trang, 0 bỏ sót, 7 cắt hụt; kèm mã băm của 10 tệp đề |
| `tools/make_header_set.py` | Bộ sinh đề (`python dev/header-pdf/tools/make_header_set.py <thư mục ra>`; cần matplotlib, numpy, PyMuPDF) |
| `tools/hdr_check.py` | Chấm điểm bộ tách hình hiện tại theo `truth.json` |
| `tools/hdr_gallery.py`, `tools/hdr_peek.py` | Trang HTML / ảnh PNG để xem tận mắt khung ảnh đã tách |

## Chấm điểm

```powershell
python dev/header-pdf/tools/hdr_check.py "$env:TEMP\hdr_run"
python dev/header-pdf/tools/hdr_gallery.py "$env:TEMP\hdr_run" "$env:TEMP\hdr_run\gallery.html"
```

`hdr_check.py` chạy `extract_images` trên cả 10 tệp, ghi `report.json` vào thư mục ra và in tổng:

- `header`: số ảnh chứa ≥ 50% một hộp tiêu đề chạy/số trang (lỗi cần diệt);
- `missed`: hình không có ảnh nào phủ tâm;
- `cut`: phần có mực của hình lòi ra ngoài ảnh hơn 2 pt.

Kết quả đã ghi nhận:

| Phiên bản | `header` | `cut` |
|---|---|---|
| v1.1.22 | 18 | 7 |
| v1.1.23 | 0 | 7 |
| Bản cứu mảnh vector nhỏ | 0 | 4 |

Đây là bộ đề do chính người sửa lỗi soạn, nên chỉ dùng **bổ trợ**. Kết luận chính về tiêu đề chạy dựa trên các bài báo gốc arXiv của những trang lỗi trong DocLayNet (xem `CHANGELOG.md`, bản 1.1.23).
