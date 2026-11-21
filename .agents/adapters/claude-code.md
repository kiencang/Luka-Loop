# Bộ chuyển đổi môi trường: Claude Code

> **Chỉ áp dụng cho Claude Code** (tab Code trong ứng dụng desktop Claude hoặc Claude Code dòng lệnh) chạy trên Windows. Tệp này được nạp tự động qua `CLAUDE.md`; agent khác bỏ qua.
>
> Tệp gom các chi tiết phụ thuộc vào cách Claude Code vận hành. Khi Claude Code thay đổi, chỉ cần sửa tệp này, không phải sửa `SKILL.md`.

## 1. Chạy lệnh công cụ

- Chạy **nguyên văn** các lệnh `tools\*.ps1` trong `SKILL.md` (chỉ thay giá trị trong `<...>`) bằng công cụ **PowerShell** của Claude Code.
- Nếu phiên Claude Code chỉ có công cụ **Bash**, vẫn chạy nguyên văn lệnh đó trong Bash: lệnh tự mở chương trình PowerShell có sẵn trên Windows. Riêng tệp có dấu `'` trong tên (vd `O'Brien 2024.pdf`), Bash làm hỏng đường dẫn; khi đó hãy đề nghị người dùng đổi tên tệp.
- `.claude/settings.json` của dự án cho phép sẵn đúng dạng lệnh này (qua cả công cụ PowerShell lẫn Bash) với 3 script `tools\extract_pdf_assets.ps1`, `tools\pdf_fallback_tools.ps1`, `tools\html_packager.ps1`. Viết khác đi (vd `& .\tools\html_packager.ps1 ...`, đổi thứ tự tham số đầu) sẽ khiến Claude Code phải hỏi lại người dùng.
- **Mỗi lệnh chạy riêng một lần gọi**, không nối nhiều lệnh bằng `;`, `&&` hay `|`.

## 2. Lấy tệp PDF

- Claude Code làm việc với đường dẫn tệp: người dùng nêu tên/đường dẫn, nhắc tệp bằng `@`, hoặc kéo tệp vào cửa sổ để dán đường dẫn. Luôn đi theo **Trường hợp 2** của Bước 1 (`-PdfPath`) và giữ tên gốc của tệp khi đặt tên đầu ra.
- Nếu người dùng chỉ dán ảnh/nội dung mà không có tệp PDF trên đĩa, đề nghị họ đặt tệp PDF vào thư mục `input\` của dự án.

## 3. Đọc nội dung PDF

- **PDF tới 10 trang:** đọc cả tệp bằng `Read`.
- **PDF trên 10 trang:** `Read` chỉ đọc theo cụm trang (tham số `pages`, tối đa 20 trang mỗi lần, vd `"1-10"`). Cách đọc này cần chương trình `pdftoppm` (poppler) trên máy. Nếu `Read` báo `pdftoppm is not installed`, **không tự cài phần mềm**; coi như agent không đọc trực tiếp được PDF và làm theo mục **"Agent không đọc trực tiếp được PDF"** trong `SKILL.md` (render từng cụm trang bằng `RenderPages` rồi mở xem các ảnh trang).

## 4. Ánh xạ thao tác trong `SKILL.md` sang công cụ Claude Code

| Cách viết trong `SKILL.md` | Công cụ Claude Code |
| :--- | :--- |
| "đọc tệp", "đọc trọn 1 lần" (các tệp SI) | `Read` cả tệp — các tệp SI đều nhỏ hơn giới hạn một lần đọc của `Read` |
| "đọc theo từng đoạn" (`manifest.json` lớn, `work\translated.md` dài) | `Read` với `offset`/`limit` |
| "mở xem song song trong 1 lượt" các ảnh đã tách | Nhiều lệnh `Read` trong **cùng một lượt trả lời**, mỗi lệnh một đường dẫn ảnh cụ thể, không dùng ký tự đại diện `*` |
| "ghi nối dần" vào `work\draft.html` / `work\translated.md` | Lô đầu: `Write` tạo tệp và đặt dòng đánh dấu `<!-- LUKA-CONTINUE -->` ngay trước phần đóng (`</article></body></html>` hoặc cuối tệp Markdown). Mỗi lô sau: `Edit` thay dòng đánh dấu bằng nội dung lô mới **kèm lại** dòng đánh dấu. Lô cuối: xóa dòng đánh dấu |
