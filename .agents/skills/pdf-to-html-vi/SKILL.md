---
name: pdf-to-html-vi
description: >-
  Quy trình dịch thuật file PDF sang một tệp HTML tiếng Việt duy nhất (tất cả trong một / self-contained files), tự động tách ảnh kèm bản đồ chú thích bằng `extract_assets.exe` (PyMuPDF portable). Kích hoạt ngay khi người dùng gửi PDF và yêu cầu dịch sang tiếng Việt.
---

# `pdf-to-html-vi` — Dịch PDF sang HTML Tự động, Kèm Tách Ảnh Bằng `extract_assets.exe`

Quy trình 4 bước tự động hoàn toàn (người dùng **không cần gõ bất kỳ câu lệnh nào**). Phần **Contract công cụ** bên dưới đã mô tả đủ đầu vào/đầu ra và quy ước đường dẫn; Agent **gọi trực tiếp CLI theo đúng contract và không cần mở mã nguồn trong `tools\`**.

> **QUY TẮC CỨNG (KHÔNG DÙNG PYTHON HỆ THỐNG):** **Tuyệt đối KHÔNG gọi `python`, `python3`, `py`, `pip`** hoặc chạy tệp nguồn tham khảo `tools\src\extract_assets.py`. Mọi thao tác tách ảnh, fallback scan và đóng gói đều chạy bằng công cụ portable (`tools\extract_pdf_assets.ps1` gọi `extract_assets.exe`, `tools\pdf_fallback_tools.ps1` và `tools\html_packager.ps1`).

## Bước 1: Tự động tách ảnh & tạo bản đồ `manifest.json`
> **Tối ưu song song:** Ngay trong lượt thực thi Bước 1, gọi **đồng thời** lệnh tách ảnh dưới đây và `read_file` đọc **trọn 1 lần** [si_academic_html.md](./si_academic_html.md) (**không** truyền `StartLine`/`EndLine` vì tệp chỉ ~274 dòng / ~37 KB, nằm gọn trong giới hạn 800 dòng / 46 KB của `read_file`).

Chọn 1 trong 2 lệnh sau tùy cách người dùng cung cấp tệp PDF:

- **Trường hợp 1 — Kéo-thả PDF trực tiếp vào khung chat** *(dấu hiệu: trong tin nhắn đã có sẵn nội dung OCR/ảnh từng trang PDF và người dùng **không** ghi đường dẫn tệp `.pdf` trong workspace)*: **KHÔNG dùng `read_file` mở `transcript.jsonl`**, chạy thẳng 1 lệnh sau (thay `<appDataDir>` và `<conversation-id>` bằng giá trị sẵn có trong `<user_information>`):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "tools\extract_pdf_assets.ps1" -TranscriptPath "<appDataDir>\brain\<conversation-id>\.system_generated\logs\transcript.jsonl" -OutDir "work\assets" -Meta
```

- **Trường hợp 2 — Tệp PDF nằm sẵn trên đĩa (trong workspace)** *(dấu hiệu: người dùng nêu rõ tên hoặc đường dẫn tệp `.pdf` trong thư mục làm việc)*: Gọi cùng wrapper với `-PdfPath` để nhận luôn `manifest.json` trên stdout nếu trong ngưỡng:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "tools\extract_pdf_assets.ps1" -PdfPath "<input.pdf>" -OutDir "work\assets" -Meta
```

- **Contract `tools\extract_pdf_assets.ps1`** *(cổng gọi CLI duy nhất ở Bước 1; bên trong tự gọi portable `extract_assets.exe`, Agent không chạy trực tiếp `.exe`)*:
  - **Tham số:** `-PdfPath "<input.pdf>"` **hoặc** `-TranscriptPath "<...>\transcript.jsonl"` *(tự đọc ngược cuối file tìm `USER_INPUT` gần nhất có đính kèm `.pdf`)*, cùng `-OutDir` *(mặc định `work\assets`)*, `-Dpi <int>` *(mặc định `180`; tăng `250`–`300` với sơ đồ chữ nhỏ)*, `-Meta` *(switch xuất `manifest.json`)*, `-MaxMetaBytes <int>` *(mặc định `16384` = 16 KB: ngưỡng tối đa in bản rút gọn ra stdout)*, và `-MaxMetaWords <int>` *(mặc định `20`: giới hạn số từ `caption`/`context` khi in ra `stdout` — tệp `manifest.json` trên đĩa vẫn giữ nguyên bản đầy đủ; đặt `0` để in nguyên văn)*.
  - **Hành vi:** Tự động trích cả ảnh bitmap lẫn sơ đồ vector kèm nhãn chữ (mở rộng lề `4.0` pt mỗi cạnh), gộp cụm hình theo chú thích, tách riêng ảnh trong bảng và bỏ qua bảng biểu/tiêu đề lề/highlight.
  - **Đầu ra tệp:**
    - Các ảnh PNG đặt tên `fig_p<trang>_<stt>.png` trong thư mục `-OutDir` (số trang bắt đầu từ `1`).
    - Khi truyền `-Meta`, ghi `manifest.json` (UTF-8) gồm: `pdf` (tên tệp), `dpi` (`int`, mặc định `180`), `total_pages` (`int`), `scanned_pages` (`list[int]` đánh số từ `1`), và `figures[]` (`file`, `page`, `source` `"raster"|"vector"|"hybrid"`, `drawings` `int`, `placement` `"figure"|"table_cell"`, `box` `[x0, y0, x1, y1]` chuẩn hóa `0.0–1.0` trên từng trang **cùng hệ tọa độ với `CropFromJson`**, `width_px`, `height_px`, `caption`, `context` trong đó `context` chỉ có giá trị khi `caption` là `null`).
  - **Đầu ra stdout:**
    - `Resolved PDF -> <đường_dẫn_PDF_thực>` *(dùng trực tiếp đường dẫn này nếu phải fallback scan)*.
    - `Extracted <N> figures -> <out_dir>`, kèm `[Note] Detected <K> scanned/full-page image page(s): [...]` (nếu có trang scan) và `Wrote manifest -> <out_dir>\manifest.json` (khi dùng `-Meta`).
    - Nếu bản rút gọn `<= -MaxMetaBytes` (`16 KB`): in thêm khối `=== MANIFEST JSON START === ... === MANIFEST JSON END ===` (đã cắt `caption`/`context` còn tối đa `-MaxMetaWords` từ) ngay trong stdout để Agent sử dụng luôn mà không cần gọi `read_file`; trong khi tệp `work\assets\manifest.json` trên ổ cứng vẫn giữ nguyên bản đầy đủ. Nếu vượt ngưỡng: in `Manifest too large for stdout (...); use read_file -> <path>` để Agent đọc phân trang.
- **Fallback PDF scan / cắt hình thủ công (`tools\pdf_fallback_tools.ps1`):** Mặc định bỏ qua; chỉ chạy theo mục **Phụ lục: Fallback PDF Scan** ở cuối tệp khi stdout báo `[Note] Detected ... scanned/full-page image page(s)` (`scanned_pages` khác rỗng) hoặc PDF chuẩn có ảnh/biểu đồ **phức tạp (Nhóm B)** bị tách sót, không thể tái tạo tương đương bằng HTML/CSS *(nếu trang scan/tách sót chỉ có sơ đồ đơn giản Nhóm A dựng lại được bằng HTML/CSS thì **không** cắt PNG qua `CropFromJson`)*.

## Bước 2: Đối chiếu bản đồ `manifest.json`, nội dung PDF, ảnh tách & Bộ quy tắc SI
- **Trường hợp PDF thuần văn bản (`0` hình):** Nếu Bước 1 báo `Extracted 0 figures` với `"figures": []` và `"scanned_pages": []` (và kiểm tra PDF thấy tài liệu chỉ gồm chữ/bảng biểu, không bị sót hình minh họa), **KHÔNG** gọi fallback scan và bỏ qua bước xem ảnh tách — chuyển thẳng sang Bước 3 để dịch và tạo `work\draft.html`.
- Nếu Bước 1 đã in khối `=== MANIFEST JSON START === ... === MANIFEST JSON END ===` ra stdout, **dùng ngay bản đồ đó** (không gọi `read_file` đọc lại `work\assets\manifest.json`). Chỉ dùng `read_file` (theo từng đoạn `StartLine`/`EndLine`) khi Bước 1 báo `Manifest too large for stdout`. Đối chiếu `page`, `box`, `placement`, `source`/`drawings` và `caption`/`context` để đặt đúng thứ tự và loại hình. **Lưu ý:** trong bản in `stdout` của `extract_pdf_assets.ps1`, trường `caption`/`context` được rút gọn tối đa 20 từ (`...`) **chỉ để định vị ảnh** (tệp `manifest.json` trên đĩa vẫn giữ nguyên toàn văn) — khi dịch `<figcaption>`, bắt buộc lấy toàn văn chú thích từ nội dung PDF gốc.
- **Đọc nội dung PDF:** Nếu người dùng kéo-thả PDF vào chat, nội dung OCR và ảnh chụp từng trang đã có sẵn trong tin nhắn đầu vào — **không gọi `read_file` đọc lại tệp PDF lần 2**; chỉ dùng `read_file` đọc `<input.pdf>` khi người dùng chỉ gửi đường dẫn tệp trong workspace.
- **Sàng lọc trước khi cắt fallback & Kiểm tra trực quan ảnh tách:**
  - **Không cắt PNG thừa qua fallback (`Triage before Crop`):** Khi gặp trang scan (`scanned_pages`) hoặc hình trên PDF chuẩn mà Bước 1 tách sót, hãy phân loại bằng mắt trước theo tiêu chí **Nhóm A vs. Nhóm B** trong Mục 4.3 của `si_academic_html.md`. **KHÔNG dùng `CropFromJson` cho Nhóm A** (sơ đồ/biểu đồ đơn giản dựng được bằng HTML/CSS) — dựng thẳng bằng HTML/CSS từ PDF/ảnh trang đính kèm *(chỉ gọi `RenderPages` đúng trang đó để nhìn nét hơn nếu chữ trên trang scan bị mờ, vẫn bỏ qua `CropFromJson`)*. Chỉ dùng `RenderPages` + `CropFromJson` cho hình **Nhóm B**.
  - **Bắt buộc xem đối chiếu ảnh đã tách (`read_file` song song):** Khi có ảnh tách trong `figures[]` hoặc vừa cắt từ `CropFromJson`, gọi **song song trong 1 lượt** nhiều `read_file` với đường dẫn cụ thể từng tệp (`work\assets\<figures[].file>` và các `work\assets\<out_name>`, vd: `work\assets\fig_p2_1.png`, ... — **không** dùng ký tự đại diện `*`) để kiểm chứng chất lượng cắt, đối chiếu 1–1 với `box`/`placement`/`context` trong `manifest.json` + PDF gốc (tránh tuyệt đối việc lắp "mù" theo tên file khi một trang có nhiều ảnh con tương tự nhau), rồi mới chốt từng hình giữ nguyên `<img>` hay tái tạo HTML/CSS.

## Bước 3: Dịch & Tái tạo HTML/CSS theo Chuẩn SI
Viết file trung gian `work\draft.html` (bắt đầu `<!DOCTYPE html>`, kết thúc `</html>`) tuân thủ nghiêm ngặt [si_academic_html.md](./si_academic_html.md) và các ràng buộc tương thích với `html_packager.ps1`:
- **Ngôn ngữ & Thuật ngữ:** Áp dụng tái cấu trúc cú pháp có kiểm soát, bảo toàn *hedging*/nhân quả/bị động khách quan, ngôi xưng *chúng tôi* vs *chúng ta/ta*, quy đổi kép đơn vị (Imperial kèm gốc), định dạng số Việt Nam (nhưng giữ dấu `.` trong LaTeX & CSS), giữ nguyên thành phần nhận diện của `References` (link DOI/URL nhấp được).
- **Khung CSS Nội dung & Chuẩn bị gắn Vỏ tương tác:** Chèn đầy đủ khối CSS nội dung từ [si_academic_html.md](./si_academic_html.md) (giữ hệ biến màu Sáng/Dịu mắt/Tối, `body`, `figure`, `.table-wrapper`, `.ws-nowrap`, `.grid-*`, `pre`/`code` và `@media print` cho nội dung). **Không cần tự viết CSS/HTML/JS cho thanh công cụ đọc, mục lục tự động hay hộp phóng to ảnh** — `html_packager.ps1` sẽ tự động gắn lớp vỏ tương tác ở Bước 4 (chỉ cần giữ đủ cấu trúc `<head>...</head>` và `<body>...</body>` cùng thẻ ngữ nghĩa `<header>`, `<h1>`–`<h3>`, `<figure><img><figcaption>`).
- **Cấu trúc Ngữ nghĩa & Công thức:** Ép văn bản chính về **1 cột duy nhất** (nối các câu gãy dòng PDF, bỏ header/footer lặp); bọc mọi `<table>` trực tiếp trong `<div class="table-wrapper">` kèm `<thead>`/`<tbody>`/`<th>`; dùng LaTeX `\( \)` / `\[ \]` + nhúng `<script>` có `MathJax` vào `<head>` nếu bài có công thức.
- **Quy ước đường dẫn ảnh & định dạng hợp lệ:** `html_packager.ps1` phân giải đường dẫn `src` tương đối **theo thư mục cha chứa `-HtmlPath`** (tức `work\`). Vì vậy, trong `work\draft.html` **BẮT BUỘC viết `src="assets/fig_pX_Y.png"`** (tuyệt đối không viết `work/assets/...`) và chỉ dùng định dạng `.png`, `.jpg` hoặc `.jpeg` cho ảnh cục bộ trong `<img>`. Đối chiếu với `work\assets\manifest.json` (cộng thêm các tệp `out_name` vừa cắt từ `CropFromJson` nếu có dùng fallback) để bảo đảm đủ mọi minh họa: giữ `<figure><img src="assets/..." alt="..."><figcaption>...</figcaption></figure>` cho ảnh/biểu đồ **Nhóm B** (và đặt ảnh ô bảng vào đúng `<td>`), hoặc dựng khối HTML/CSS tương đương trong `<figure>` cho sơ đồ đơn giản **Nhóm A**.
- **Xử lý Tài liệu Khoa học Dài (`> 10 trang`):** Không dịch gộp một lượt dễ bị cắt bớt hoặc tóm tắt. Chia theo từng mục/chương hoặc cụm 5–8 trang, ghi khung đầu `<head>` vào `work\draft.html` trước rồi nối dần (`Append` hoặc `edit_file`) từng `<section>` đầy đủ (giữ trọn mọi bảng biểu, hình minh họa trong `manifest.json` và mục `References`).

## Bước 4: Đóng gói song song HTML + PDF, kiểm tra & tự dọn nháp (`tools\html_packager.ps1`)
Chạy **một lệnh duy nhất** để nhúng Base64, chạy Auto-QA, xuất song song cả 2 tệp **`output\<tên_file_gốc>_vi.html`** và **`output\<tên_file_gốc>_vi.pdf`**, đồng thời tự động dọn thư mục nháp `work\` ngay khi thành công:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "tools\html_packager.ps1" -Action EmbedImages -HtmlPath "work\draft.html" -OutHtmlPath "output\<tên_file_gốc>_vi.html" -AlsoPdf -CleanDir "work"
```

- **Quy tắc đặt tên file đầu ra & Chống ghi đè:** Lưu trong thư mục `output\` và giữ nguyên chính xác phần tên gốc không đuôi của file PDF trong workspace (vd: `bao-cao-2026.pdf` → `output\bao-cao-2026_vi.html` và `output\bao-cao-2026_vi.pdf`, không tự dịch tên file hay tự đổi sang slug khác). Riêng trường hợp kéo-thả vào chat khiến tệp tải lên mang tên tạm `media_<id>.pdf` (hệ thống không lưu tên gốc ban đầu trên máy): **không lấy tên tạm `media_...` và không tìm ngược tên gốc trên máy**, hãy đặt tên theo **tiêu đề chính ngắn gọn của tài liệu** (dạng ASCII `snake_case`, không dấu, trừ khi người dùng chỉ định rõ tên đầu ra) kèm `_vi.html` / `_vi.pdf`. **Không tự đoán/gắn tên model AI** vào tên file (chỉ thêm nhãn nếu người dùng yêu cầu rõ). Khi tệp đích đã tồn tại trong `output\`, `html_packager.ps1` luôn tự động đánh số đồng bộ cả cặp thành `_vi_2`, `_vi_3`...

- **Contract `tools\html_packager.ps1`:**
  - **Action `EmbedImages`:**
    - Tham số: `-HtmlPath` *(bắt buộc)*, `-OutHtmlPath` *(tùy chọn; bỏ trống sẽ cập nhật trực tiếp `-HtmlPath` theo UTF-8 không BOM)*, `-AlsoPdf` *(switch xuất PDF cùng tên bên cạnh HTML đích)*, `-OutPdfPath` *(tùy chọn chỉ định đường dẫn PDF đích; cũng tự bật xuất PDF)*, `-JpegQuality` *(mặc định `90`)*, `-MaxImageWidth` *(mặc định `1400` px)*, `-CleanDir` *(tùy chọn; truyền `"work"` để tự xóa thư mục tạm **chỉ sau khi** `[QA PASS]` và xuất PDF thành công, và từ chối xóa nếu thư mục đích chứa tệp đầu ra hoặc là thư mục gốc)*.
    - **Tự động gắn lớp vỏ tương tác (`tools\reader_shell.html`):** Trước khi chạy Auto-QA, kiểm tra tệp HTML có đủ `<head>...</head>` và `<body>...</body>`, rồi bơm idempotent các mảnh còn thiếu (CSS vỏ `rsfv-*` trước `</head>`, thanh `.rsfv-toolbar` ngay sau `<body...>`, và `#rsfv-img-lightbox` + `<script>` trước `</body>`); bỏ qua nếu HTML đã có sẵn vỏ tương tác (kể cả định dạng cũ `.reader-toolbar` / `#img-lightbox`).
    - **Tối ưu ảnh:** Ảnh chụp nhiều màu không có kênh alpha (`>= 200` cụm màu mẫu) được thử nén JPEG theo `-JpegQuality` và chỉ giữ khi nhỏ hơn bản gốc (`<= 85%` nếu không resize); sơ đồ ít màu hoặc có độ trong suốt được giữ nguyên PNG.
    - **Cổng Auto-QA (chạy trước khi ghi tệp ra `output\` — ném lỗi dừng chạy nếu vi phạm bất kỳ điều kiện nào sau đây; khi fail sẽ không tạo/ghi đè tệp đích và giữ nguyên `work\` để sửa):**
      1. `0` thẻ `<img>` trỏ tới tệp cục bộ chưa được nhúng (mọi `src` phải là `data:image/...` hoặc `http(s)://`).
      2. Mọi thẻ `<img>` đều phải có thuộc tính `alt`.
      3. Số container `.table-wrapper` ≥ số `<table>` (ngoài `<script>`/`<style>`).
      4. Nếu ngoài `<script>`/`<style>` xuất hiện `\(` hoặc `\[`, HTML phải chứa `<script ... MathJax>`.
      5. `0` liên kết nội bộ `href="#..."` bị gãy (đều có `id="..."` tương ứng).
      - *Phục hồi khi QA fail:* Đọc thông báo lỗi từ stdout/stderr, mở sửa trực tiếp `work\draft.html` rồi chạy lại đúng lệnh Bước 4.
  - **Action `HtmlToPdf`** *(xuất PDF độc lập từ tệp HTML đã đóng gói trọn vẹn / self-contained)*:
    - CLI: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "tools\html_packager.ps1" -Action HtmlToPdf -HtmlPath "<in.html>" [-OutPdfPath "<out.pdf>"] [-CleanDir "<dir>"]`
    - Tự tìm Microsoft Edge (ưu tiên) hoặc Chrome headless có sẵn trên Windows để in PDF (bỏ header/footer trình duyệt). Nếu bỏ trống `-OutPdfPath`, xuất cùng thư mục với đuôi `.pdf`. Nếu máy không có Edge/Chrome, xuất cảnh báo `Write-Warning` và bỏ qua xuất PDF.
  - **Đầu ra stdout xác nhận thành công (theo thứ tự thực thi):**
    - `[QA PASS] Base64 images: <N> | Tables wrapped: <M>/<M> | LaTeX/MathJax OK | Broken anchors: 0`
    - `Injected reader shell -> CSS, Toolbar, Script` *(hoặc `Reader shell already present (skipped injection)`)*
    - `Output collision avoided; auto-numbered -> <đường_dẫn>` *(nếu tệp cũ đã tồn tại)*
    - `Embedded images into HTML -> <đường_dẫn>.html (<bytes> bytes)`
    - `Exported PDF -> <đường_dẫn>.pdf (<bytes> bytes)`
    - `Cleaned temp directory -> <đường_dẫn>\work` *(khi dùng `-CleanDir`)*
- Xác nhận từ stdout lệnh trên đã có `[QA PASS]`, `Injected reader shell` (hoặc `already present`), `Embedded images into HTML`, `Exported PDF` và `Cleaned temp directory` (không cần gọi thêm lệnh xóa `work\` riêng).
- **Quy tắc phản hồi sau khi hoàn tất:** Lấy **đúng tên tệp thực tế** in ở `Embedded images into HTML -> ...` và `Exported PDF -> ...` trên stdout (kể cả khi tự đánh số `_2`, `_3`...), chỉ trả về liên kết tới các tệp đầu ra theo đúng mẫu thân thiện với người dùng cuối bên dưới (**tránh dùng các cụm từ kỹ thuật** như `"tự chứa"`, `"Self-contained"`, `"Base64"`, `"QA PASS"`, hay nhắc thư mục tạm `work/`; **tuyệt đối không tự ý viết bản tóm tắt hay lặp lại nội dung tài liệu đã dịch** trừ khi người dùng yêu cầu rõ):

  ```markdown
  Bản dịch tiếng Việt đã hoàn thành (nằm ở thư mục `output` trong thư mục ứng dụng):
  - **HTML (mở bằng trình duyệt):** [<tên_tệp_thực_tế>.html](file:///<đường_dẫn_workspace>/output/<tên_tệp_thực_tế>.html) *(thường cho kết quả hiển thị, bố cục đẹp hơn)*
  - **PDF:** [<tên_tệp_thực_tế>.pdf](file:///<đường_dẫn_workspace>/output/<tên_tệp_thực_tế>.pdf)

  **Trạng thái kiểm định:** Đạt chuẩn (đã tích hợp đủ <N> ảnh vào HTML, <M>/<M> bảng hiển thị chuẩn, 0 liên kết gãy).
  ```
  *(Lưu ý biến thể ngắn gọn cho dòng kiểm định & PDF: điều chỉnh phần tóm tắt trong ngoặc theo số liệu thực tế từ Auto-QA — vd bổ sung `công thức toán đầy đủ` nếu bài có LaTeX, hoặc lược ý ảnh / ghi `0 ảnh` nếu tài liệu chỉ có chữ; nếu máy thiếu Microsoft Edge/Chrome nên bỏ qua xuất PDF, thay dòng PDF thành: `- **PDF:** Chưa xuất được do máy không có sẵn Microsoft Edge hoặc Chrome (bạn vẫn có thể mở tệp HTML bằng trình duyệt rồi In → Lưu thành PDF).`)*

---

## Phụ lục: Fallback PDF Scan (`tools\pdf_fallback_tools.ps1`)
Chỉ sử dụng khi Bước 1 phát hiện trang scan (`scanned_pages` khác rỗng / stdout có `[Note] Detected ... scanned/full-page image page(s)`) hoặc PDF chuẩn có hình/biểu đồ phức tạp bị tách sót:

> **Quy tắc Sàng lọc trước khi Cắt (`Triage before Crop`):**
> - **Sơ đồ/biểu đồ đơn giản (Nhóm A — tái tạo được bằng HTML/CSS):** **KHÔNG dùng `CropFromJson`** để cắt PNG trung gian. Nếu ảnh trang có sẵn khi kéo-thả PDF (hoặc trang PDF gốc) đã đủ nét để đọc hết chữ → bỏ qua cả `RenderPages` lẫn `CropFromJson`, dựng thẳng HTML/CSS; chỉ gọi `RenderPages` đúng trang đó nếu ảnh trang bị mờ cần soi chữ rõ hơn để vẽ HTML/CSS.
> - **Ảnh chụp thực tế & biểu đồ khoa học phức tạp (Nhóm B — bắt buộc giữ PNG):** Mới thực hiện đầy đủ 2 bước `RenderPages` → `CropFromJson` bên dưới.

1. **Render từng trang ra PNG (`RenderPages`):**
   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "tools\pdf_fallback_tools.ps1" -Action RenderPages -PdfPath "<input.pdf>" -OutDir "work\pages" -Pages "<trang_can_render>"
   ```
   - Tham số tùy chọn: `-Pages` (vd `"2"`, `"2,5"` hoặc `"2-4"` — truyền đúng danh sách `scanned_pages` ở Bước 1 hoặc số trang có sơ đồ bị sót để chỉ render đúng các trang cần thiết; bỏ trống nếu muốn render toàn bộ trang), `-Scale` (mặc định `2.5`; bề rộng ảnh tối thiểu `800` px). Với file kéo-thả, lấy `<input.pdf>` trực tiếp từ dòng `Resolved PDF -> ...` ở Bước 1.
   - Đầu ra: `work\pages\page_<p>.png` (vd `page_2.png`, `page_5.png`, ...).
2. **Cắt ảnh theo tọa độ JSON (`CropFromJson`):**
   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "tools\pdf_fallback_tools.ps1" -Action CropFromJson -SpecJson "work\crop_spec.json" -OutDir "work\assets"
   ```
   - **Contract `work\crop_spec.json` (mã hóa UTF-8, mảng đối tượng JSON):**
     ```json
     [
       {
         "page_png": "work\\pages\\page_2.png",
         "box": [0.12, 0.10, 0.88, 0.45],
         "out_name": "fig_p2_1.png",
         "auto_trim": true
       }
     ]
     ```
     - `page_png` *(bắt buộc)*: đường dẫn tới ảnh trang PNG nguồn.
     - `box` *(bắt buộc)*: mảng `[x0, y0, x1, y1]` chuẩn hóa `0.0`–`1.0` (gốc trên-trái, bắt buộc `x1 > x0` và `y1 > y0`).
     - `out_name` *(bắt buộc)*: tên tệp PNG đầu ra lưu trong `-OutDir`.
     - `auto_trim` *(tùy chọn, mặc định `true`)*: tự cắt viền trắng thừa (ngưỡng sáng `< 247`, giữ lề `6` px); đặt `false` để giữ nguyên khung cắt.
   - **Đầu ra & Lưu ý:** In `Cropped <out_name> -> <đường_dẫn> (<W>x<H>)` trong `-OutDir` (`work\assets\`). Công cụ **chỉ lưu tệp PNG và KHÔNG tự cập nhật thêm vào `work\assets\manifest.json`**; Agent ghi nhớ và dùng trực tiếp các `out_name` vừa cắt khi viết HTML.
