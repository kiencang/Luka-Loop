# Bộ chuyển đổi môi trường: Antigravity

> **Chỉ áp dụng khi agent đang chạy trong Antigravity** — dấu hiệu: ngữ cảnh có khối `<user_information>` chứa `App Data Directory` / `Artifact Directory Path` (hoặc `appDataDir` ở bản cũ). Agent khác **bỏ qua toàn bộ tệp này** và làm theo phần chung trong `SKILL.md`.
>
> Tệp này gom mọi chi tiết phụ thuộc vào cách Antigravity vận hành (đường dẫn nội bộ, tên công cụ, giới hạn công cụ). Các chi tiết này **có thể thay đổi theo phiên bản Antigravity**: khi Antigravity cập nhật, chỉ cần sửa tệp này, không phải sửa `SKILL.md`.

## 1. Ánh xạ thao tác trong `SKILL.md` sang công cụ Antigravity

Bộ công cụ tệp mặc định trên Antigravity 2.0 là `read_file` / `write_file` / `edit_file` (và `run_command` để chạy PowerShell). Một số phiên bản Antigravity IDE đời cũ đặt tên tương ứng là `view_file` / `write_to_file` / `replace_file_content` / `multi_replace_file_content` — nếu danh sách công cụ của bạn dùng tên cũ thì ánh xạ tương ứng.

| Cách viết trong `SKILL.md` | Công cụ Antigravity |
| :--- | :--- |
| "đọc tệp", "đọc trọn 1 lần", "đọc toàn bộ, không chia đoạn" | `read_file` (hoặc `view_file`) với **đường dẫn tuyệt đối**, **không** truyền `StartLine`/`EndLine` |
| "đọc theo từng đoạn" (tệp lớn: `manifest.json` vượt ngưỡng, `work\translated.md` dài) | `read_file` (hoặc `view_file`) với `StartLine`/`EndLine` (thêm `ByteOffset` nếu một đoạn bị cắt theo ngưỡng byte) |
| "mở xem song song trong 1 lượt" các ảnh đã tách | Nhiều lệnh `read_file` (hoặc `view_file`) gọi **cùng một lượt**, mỗi lệnh một **đường dẫn tuyệt đối** cụ thể (`<workspace>\work\assets\fig_p2_1.png`...), **không** dùng ký tự đại diện `*` |
| "ghi nối dần" vào `work\draft.html` / `work\translated.md` | Lô đầu: `write_file` với `Overwrite: true` (chưa ghi thẻ đóng `</article></body></html>`); mỗi lô sau: `write_file` với `Append: true` (không kèm `Overwrite: true`), đóng thẻ ở lô cuối. *(Nếu phiên bản không có `Append` — vd `write_to_file` cũ — dùng `edit_file` / `replace_file_content` với điểm neo duy nhất ngay trước thẻ đóng; lưu ý `edit_file` thay **mọi** vị trí khớp `Target`.)* |

- **Đường dẫn tuyệt đối bắt buộc:** `read_file`, `write_file` và `edit_file` từ chối đường dẫn tương đối — luôn ghép từ `Active Workspaces` / `Command Working Directory` trong `<user_information>` (chỉ các tham số truyền vào lệnh PowerShell qua `run_command` mới dùng đường dẫn tương đối như `work\assets`).
- **Giới hạn hiện tại của `read_file` (`view_file`):** khoảng 800 dòng / 46 KB (`46080` byte) mỗi lần gọi; `read_file` tôn trọng `StartLine`/`EndLine` ngay từ lần mở đầu tiên *(riêng một số bản `view_file` cũ trả 800 dòng đầu ở lần mở đầu)*. Các tệp SI (`si_academic_html.md`, `si_translation.md`, `si_layout.md`) đều nằm gọn trong giới hạn này nên đọc trọn được trong 1 lần.

## 2. Tải lên tệp (kéo thả vào khung chat hoặc bấm nút thêm tệp `+`)

- **Dấu hiệu:** tin nhắn của người dùng đã đính kèm trực tiếp nội dung/ảnh từng trang PDF và người dùng **không** nêu đường dẫn tệp `.pdf` trên đĩa.
- **Lấy tệp PDF thật:** **không** dùng `read_file` mở `transcript.jsonl`; chạy thẳng lệnh sau ở Bước 1 bằng `run_command` — lấy trực tiếp `Artifact Directory Path` từ `<user_information>` (chính là `<App Data Directory>\brain\<conversation-id>`, bản cũ là `<appDataDir>\brain\<conversation-id>`), giữ nguyên các tham số còn lại như lệnh Bước 1 trong `SKILL.md`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File 'tools\extract_pdf_assets.ps1' -TranscriptPath '<Artifact Directory Path>\.system_generated\logs\transcript.jsonl' -OutDir 'work\assets' -Meta
```

  - `-TranscriptPath` tự đọc ngược transcript, tìm lượt `USER_INPUT` gần nhất có đính kèm `.pdf`, và in `Resolved PDF -> <đường_dẫn_PDF_thực>`. Dùng đúng đường dẫn này cho `-PdfPath` ở các lệnh sau (vd `RenderPages` trong phụ lục fallback).
  - Nếu lệnh báo không tìm thấy transcript hoặc không tìm thấy PDF (Antigravity có thể đã đổi cấu trúc thư mục nội bộ hoặc bật Terminal Sandbox chặn đọc ngoài workspace), **không đoán đường dẫn khác**: đề nghị người dùng đặt tệp PDF vào thư mục `input\` của dự án rồi làm lại Bước 1 với `-PdfPath`.
- **Đọc nội dung PDF:** nội dung và ảnh từng trang đã có trong tin nhắn đầu vào — **không** đọc lại tệp PDF lần 2.
- **Tên tệp tạm `media_<id>.pdf`:** Antigravity sao chép tệp tải lên vào thư mục của phiên (`<Artifact Directory Path>\.user_uploaded\media_<id>.pdf`, chính là đường dẫn in ở dòng `Resolved PDF -> ...`) và đổi sang tên tạm; tên gốc trên máy người dùng không được giữ lại. Khi đặt tên đầu ra ở Bước 4: **không** dùng `media_...`, **không** tìm ngược tên gốc trên máy; đặt theo tiêu đề chính ngắn gọn của tài liệu (ASCII `snake_case`, không dấu) kèm hậu tố của skill (`_vi` hoặc `_layout_vi`), trừ khi người dùng chỉ định tên.
- **Giới hạn tải lên:** khung chat Antigravity nhận tệp tối đa khoảng 10 MB. PDF lớn hơn cần được đặt vào `input\` và xử lý như tệp trên đĩa.
