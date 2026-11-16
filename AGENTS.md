# Quy tắc Điều phối Dịch thuật Trong Workspace

- **Quy trình Tối giản PDF → HTML:**
  - Khi người dùng gửi tệp `.pdf` và yêu cầu dịch sang tiếng Việt (hoặc dịch sang HTML / dịch nhanh tài liệu PDF có hình minh họa):
    - **Kích hoạt ngay skill `pdf-to-html-vi`** ([SKILL.md](.agents/skills/pdf-to-html-vi/SKILL.md)).
    - **Tuyệt đối KHÔNG dùng Python hệ thống:** Không gọi `python`, `python3`, `py`, `pip` hay cố chạy bất kỳ tệp `.py` nào (kể cả mã nguồn tham khảo trong `tools\src\`). Toàn bộ quy trình chỉ sử dụng bộ công cụ portable & PowerShell có sẵn (`tools\extract_pdf_assets.ps1` gọi `extract_assets.exe`, `tools\pdf_fallback_tools.ps1`, `tools\html_packager.ps1`).
    - Agent phải **tự động gọi** `tools\extract_pdf_assets.ps1` để tách sẵn toàn bộ ảnh, tự đọc PDF + ảnh vừa tách, dịch thẳng sang HTML và nhúng Base64 + xuất song song 2 tệp hoàn chỉnh đặt tên đúng quy cách **`output\<tên_file_gốc>_vi.html`** và **`output\<tên_file_gốc>_vi.pdf`** (thư mục `output\` trong workspace) rồi tự dọn thư mục nháp `work\` ngay trong cùng lệnh bằng `tools\html_packager.ps1` (`-Action EmbedImages ... -AlsoPdf -CleanDir "work"`). **Tuyệt đối không yêu cầu người dùng tự chạy hoặc ghi nhớ lệnh CLI.**
    - **Phản hồi cuối cùng:** Sau khi xuất tệp và đạt QA, chỉ trả về liên kết tới 2 tệp đầu ra (`_vi.html`, `_vi.pdf`) kèm xác nhận ngắn gọn; **không** tự ý viết bản tóm tắt nội dung tài liệu trừ khi người dùng yêu cầu.
