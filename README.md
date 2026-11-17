# luka-loop
Quy trình AI Agent tự động dịch tài liệu PDF tiếng Anh sang tiếng Việt. Không yêu cầu cài thêm bất cứ phần mềm hỗ trợ nào. Chỉ cần mở thư mục trên [Antigravity](https://antigravity.google/) là bắt đầu dùng được ngay.

Định dạng đầu ra mặc định: Bản dịch tiếng Việt trả về ở cả 2 định dạng đồng thời là HTML và PDF.

## Yêu cầu hệ thống
- **Hệ điều hành:** Windows 10 hoặc Windows 11 **64-bit (x64)** *(bộ công cụ `extract_assets.exe` hiện biên dịch ở kiến trúc x64, chưa hỗ trợ Windows 32-bit), hầu hết các máy tính hiện nay trên thị trường đều là bản 64-bit*.
- **PowerShell:** Windows PowerShell 5.1 (có sẵn mặc định trên Windows 10/11, bạn không cần phải điều chỉnh, cài cắm gì thêm).
- **Trình duyệt (tùy chọn để tự động xuất PDF):** Công cụ dùng Microsoft Edge (ưu tiên) hoặc Google Chrome để xuất tệp PDF. Nếu không có, quy trình vẫn xuất hoàn chỉnh tệp `*_vi.html`.

## Lý do tồn tại
Tôi đã có sản phẩm https://github.com/kiencang/PDF-silaTranslator có chức năng tương đương, nhưng hiện tại chỉ API Key trả phí mới sử dụng được. 

luka-loop sử dụng agent Gemini thông qua Antigravity, và hoàn toàn dùng được với tài khoản miễn phí. Ngoài ra, việc sử dụng các thư viện python chất lượng cao như PyMuPDF giúp công cụ có sự cải tiến tốt hơn trong khả năng tách ảnh.

## Cách dùng
Rất đơn giản, bạn vào https://github.com/kiencang/luka-loop/releases tải source code .zip của phiên bản mới nhất.

Sao đó giải nén file zip đó ở bất kỳ thư mục làm việc nào mà bạn muốn. Khi giải nén, nhớ chọn tùy chọn `Extract Here`, thư mục được giải nén, bạn click vào thấy ngay file có tên `AGENTS.md` nghĩa là bạn đã giải nén thành công.

Phần khó nhất đã xong! Giờ để dùng công cụ dịch, bạn chỉ việc vào Antigravity, chọn Workspace > Create Project > Add Folder, rồi bạn thêm thư mục vừa giải nén xong là OK.

Giờ thì bạn chỉ việc tải file PDF rồi gõ câu lệnh kiểu như `Dịch tài liệu sang tiếng Việt.` là agent Gemini sẽ tiến hành dịch, và gửi kết quả về cả ở 2 định dạng HTML và PDF. Nếu muốn giữ sát bố cục/thiết kế gốc từng trang của PDF (slide, brochure, tạp chí nhiều cột...), hãy nêu rõ trong yêu cầu (ví dụ: `Dịch tài liệu sang tiếng Việt và bảo toàn thiết kế/layout.`).

**Lưu ý**:
- Khi làm việc với Antigravity nên chọn chế độ **Turbo** (thay vì mặc định Request Review) để không phải liên tục nhận được các câu hỏi xác nhận quyền thực thi.
- Nếu đặt thư mục `luka-loop` bên trong vùng đồng bộ đám mây (OneDrive, Google Drive, Dropbox...), hãy bật tùy chọn giữ tệp ngoại tuyến trên máy (*Always keep on this device* / *Mirror files* / *Available offline*) để `extract_assets.exe` nạp đủ các thư viện đi kèm và tránh lồng đường dẫn quá sâu vượt giới hạn ký tự trên Windows.

## Cấu trúc dự án
- [`AGENTS.md`](./AGENTS.md) — Quy tắc điều phối dành cho AI Agent trong workspace.
- [`.agents/skills/pdf-to-html-vi/`](./.agents/skills/pdf-to-html-vi/) — Skill mặc định `pdf-to-html-vi` (đọc mượt 1 cột) gồm quy trình 4 bước ([`SKILL.md`](./.agents/skills/pdf-to-html-vi/SKILL.md)) và bộ chuẩn dịch thuật học thuật / CSS ([`si_academic_html.md`](./.agents/skills/pdf-to-html-vi/si_academic_html.md)).
- [`.agents/skills/pdf-to-html-vi-layout/`](./.agents/skills/pdf-to-html-vi-layout/) — Skill tùy chọn `pdf-to-html-vi-layout` (kích hoạt khi yêu cầu bảo toàn thiết kế/layout) gồm quy trình tách pha tiết kiệm token ([`SKILL.md`](./.agents/skills/pdf-to-html-vi-layout/SKILL.md)), bộ quy chuẩn chuyên dịch ([`si_translation.md`](./.agents/skills/pdf-to-html-vi-layout/si_translation.md)) và bộ quy chuẩn thiết kế từng trang ([`si_layout.md`](./.agents/skills/pdf-to-html-vi-layout/si_layout.md)).
- [`tools/`](./tools/) — Bộ công cụ PowerShell & portable:
  - [`_path_guards.ps1`](./tools/_path_guards.ps1) — Tiện ích dùng chung kiểm tra và bảo vệ đường dẫn cục bộ (`Test-IsReparsePoint`, `Assert-SafeOutputPath`, `Assert-LocalNoUncPath`).
  - [`extract_pdf_assets.ps1`](./tools/extract_pdf_assets.ps1) gọi [`extract_assets/extract_assets.exe`](./tools/extract_assets/extract_assets.exe) để tự động tách ảnh/sơ đồ và xuất `manifest.json`.
  - [`pdf_fallback_tools.ps1`](./tools/pdf_fallback_tools.ps1) render trang PDF scan qua WinRT `Windows.Data.Pdf` và cắt khung ảnh theo JSON.
  - [`html_packager.ps1`](./tools/html_packager.ps1) nhúng ảnh Base64 tối ưu, bơm lớp vỏ đọc [`reader_shell.html`](./tools/reader_shell.html) (hoặc giữ nguyên HTML thuần khi bật `-PreserveLayout`), kiểm định Auto-QA, tự động đánh số chống ghi đè (`_2`, `_3`...) khi trùng tên trong `output/` và xuất PDF.
  - [`src/extract_assets.py`](./tools/src/extract_assets.py) — Mã nguồn Python gốc dùng để biên dịch ra `extract_assets.exe` *(chỉ dùng tham khảo/build lại; khi chạy dịch thuật tuyệt đối không gọi Python hệ thống)*.
- `output/` — Thư mục chứa tệp đầu ra (`*_vi.html`/`*_vi.pdf` cho bản đọc mượt mặc định; `*_layout_vi.html`/`*_layout_vi.pdf` cho bản bảo toàn thiết kế; tự động thêm `_2`, `_3`... nếu dịch lại nhiều lần cùng một file), tự động được tạo khi đóng gói và được bỏ qua bởi [`.gitignore`](./.gitignore).

## Cách công cụ xử lý ảnh

Công cụ kết hợp tách ảnh tự động bằng PyMuPDF ([`extract_assets.exe`](./tools/extract_assets/extract_assets.exe)) ở Bước 1 cho cả **ảnh bitmap** lẫn **sơ đồ/biểu đồ vector**, kèm cơ chế **Sàng lọc trước khi Cắt (`Triage before Crop`)** để không lãng phí công đoạn cắt thủ công cho các sơ đồ đơn giản dựng lại được bằng HTML/CSS, đồng thời bắt buộc đối chiếu trực quan song song các tệp PNG đã tách trước khi đóng gói:

```mermaid
flowchart TD
    IN["PDF đầu vào (Workspace -PdfPath hoặc kéo-thả -TranscriptPath)"] --> S1

    subgraph B1["Bước 1: Tách tự động (extract_pdf_assets.ps1 -> extract_assets.exe)"]
        S1["Quét bitmap get_image_info() + vector get_drawings() & cluster_drawings()"]
        S1 --> S1O["Xuất work/assets/fig_pX_Y.png (180 DPI) + manifest.json + scanned_pages"]
    end

    S1O --> CHK{"Phân loại kết quả Bước 1"}

    CHK -->|"0 hình và scanned_pages rỗng"| TXT["PDF thuần chữ: Bỏ qua bước đọc ảnh & fallback"]

    CHK -->|"Có figures[] trên trang chuẩn"| B2A["Bước 2a: Bắt buộc read_file song song tất cả PNG tách + đọc manifest.json"]
    B2A -->|"Đối chiếu 1-1 với PDF gốc"| STD{"Phân loại từng hình"}
    STD -->|"Ảnh nằm trong ô bảng"| TBL["Nhúng ảnh vào đúng ô bảng tương ứng"]
    STD -->|"Nhóm A: Sơ đồ đơn giản"| GA["Dựng thẳng bằng HTML/CSS (bỏ PNG gốc để tránh trùng)"]
    STD -->|"Nhóm B: Ảnh chụp, biểu đồ dày"| GB["Giữ PNG gốc (tăng -Dpi 250/300 nếu chữ nhỏ mờ)"]
    B2A -.->|"Phát hiện trang chuẩn có hình bị tách sót"| TRI

    CHK -->|"scanned_pages khác rỗng"| TRI{"Bước 2b: Sàng lọc trước khi Cắt (Triage before Crop)"}
    TRI -->|"Nhóm A: Sơ đồ đơn giản (Cấm CropFromJson)"| SCANA{"Ảnh trang gốc đã rõ chữ?"}
    SCANA -->|"Đã rõ"| SKIPR["Bỏ qua cả RenderPages & CropFromJson"]
    SKIPR --> GA
    SCANA -->|"Bị mờ"| RENDONLY["Chỉ chạy RenderPages trang đó để đọc chữ rõ hơn"]
    RENDONLY --> GA

    TRI -->|"Nhóm B: Ảnh chụp, tế bào, biểu đồ phức tạp"| SCANB["1. RenderPages -Pages (tạo page_p.png)"]
    SCANB --> SPEC["2. read_file trang -> ghi work/crop_spec.json -> CropFromJson"]
    SPEC --> VER["3. Bắt buộc read_file kiểm tra PNG cắt (tự nhớ out_name vì không ghi vào manifest.json)"]
    VER --> GB

    TXT --> S3
    TBL --> S3
    GA --> S3
    GB --> S3

    subgraph B34["Bước 3 & 4: Lắp ghép HTML & Đóng gói (html_packager.ps1)"]
        S3["Bước 3: Viết work/draft.html (đủ minh họa Nhóm B PNG + Nhóm A HTML/CSS + full chú thích)"]
        S3 --> S4["Bước 4: Nén tối ưu ảnh -> nhúng Base64 -> bơm reader_shell.html -> Auto-QA"]
        S4 --> OUT["Xuất song song output/*_vi.html & output/*_vi.pdf -> tự dọn sạch work/"]
    end
```

## Tuyên bố từ chối trách nhiệm
Công cụ này có thể được sử dụng cho mục đích nghiên cứu và học tập cá nhân.

`luka-loop` cũng như người phát triển nó không đưa ra bất kỳ bảo đảm rõ ràng hay ngụ ý nào, cũng như không tuyên bố rằng công cụ sẽ vận hành hoàn hảo, chính xác hoặc cập nhật. Người phát triển sẽ không chịu trách nhiệm cho bất kỳ tổn thất hay thiệt hại nào phát sinh trực tiếp hoặc gián tiếp liên quan đến hoặc phát sinh từ việc sử dụng công cụ này.

## Giấy phép & Thành phần Bên thứ ba (License & Third-Party Notices)

- **Mã nguồn gốc của `luka-loop`:** Phần kịch bản điều phối Agent, Skill, script PowerShell, lớp vỏ [`tools/reader_shell.html`](./tools/reader_shell.html) và mã nguồn tự viết [`tools/src/extract_assets.py`](./tools/src/extract_assets.py) được cấp phép theo **MIT License** — xem chi tiết tại [`LICENSE`](./LICENSE).
- **Bộ công cụ thực thi dựng sẵn (`tools/extract_assets/`):** Bản đóng gói portable phân phối kèm trong kho lưu trữ có tích hợp các thành phần phần mềm bên thứ ba và chịu sự điều chỉnh của giấy phép tương ứng từng thành phần:
  - **PyMuPDF / MuPDF:** Cấp phép theo **AGPL-3.0**; toàn bộ mã nguồn tương ứng của công cụ tách ảnh được công khai đầy đủ tại [`tools/src/extract_assets.py`](./tools/src/extract_assets.py).
  - **Python 3.12.7:** Cấp phép theo **PSF License v2**.
  - **OpenSSL 3.0.15 (`libcrypto-3.dll`):** Cấp phép theo **Apache License 2.0**.
  - **PyInstaller:** Bootloader theo **GPL-2.0-or-later** (kèm *Bootloader Exception*) và runtime hooks theo **Apache License 2.0**.
  - **Microsoft Visual C++ Runtime / Universal CRT:** Thuộc bản quyền của Microsoft Corporation.

Vui lòng xem đầy đủ thông báo bản quyền và toàn văn các giấy phép bên thứ ba tại [`THIRD_PARTY_LICENSES.md`](./THIRD_PARTY_LICENSES.md) và thư mục [`licenses/`](./licenses/).
