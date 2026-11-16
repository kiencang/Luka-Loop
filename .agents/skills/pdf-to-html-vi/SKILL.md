---
name: pdf-to-html-vi
description: >-
  Quy trình dịch thuật file PDF sang một tệp HTML tiếng Việt duy nhất (tất cả trong một / self-contained files), tự động tách ảnh kèm bản đồ chú thích bằng `extract_assets.exe` (PyMuPDF portable). Kích hoạt ngay khi người dùng gửi PDF và yêu cầu dịch sang tiếng Việt.
---

# `pdf-to-html-vi` — Dịch PDF sang HTML Tự động, Kèm Tách Ảnh Bằng `extract_assets.exe`

Quy trình 4 bước tự động hoàn toàn (người dùng **không cần gõ bất kỳ câu lệnh nào**). Phần **Contract công cụ** bên dưới đã mô tả đủ đầu vào/đầu ra và quy ước đường dẫn; Agent **gọi trực tiếp CLI theo đúng contract và không cần mở mã nguồn trong `tools\`**.

> **QUY TẮC CỨNG (KHÔNG DÙNG PYTHON HỆ THỐNG):** **Tuyệt đối KHÔNG gọi `python`, `python3`, `py`, `pip`** hoặc chạy tệp nguồn tham khảo `tools\src\extract_assets.py`. Mọi thao tác tách ảnh, fallback scan và đóng gói đều chạy bằng công cụ portable (`tools\extract_pdf_assets.ps1` gọi `extract_assets.exe`, `tools\pdf_fallback_tools.ps1` và `tools\html_packager.ps1`).

## Bước 1: Tự động tách ảnh & tạo bản đồ `manifest.json`
> **Tối ưu song song:** Ngay trong lượt thực thi Bước 1, gọi **đồng thời** lệnh tách ảnh dưới đây và `read_file` đọc **trọn 1 lần** [si_academic_html.md](./si_academic_html.md) (**không** truyền `StartLine`/`EndLine` vì tệp chỉ ~245 dòng / ~28 KB, nằm gọn trong giới hạn 800 dòng / 46 KB của `read_file`).

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
    - Khi truyền `-Meta`, ghi `manifest.json` (UTF-8) gồm: `pdf` (tên tệp), `total_pages` (`int`), `scanned_pages` (`list[int]` đánh số từ `1`), và `figures[]` (`file`, `page`, `bbox` `[x0, y0, x1, y1]` tính theo **tọa độ PDF point** — khác với `box` tỷ lệ `0..1` của `CropFromJson`, `width_px`, `height_px`, `caption`, `context` trong đó `context` chỉ có giá trị khi `caption` là `null`).
  - **Đầu ra stdout:**
    - `Resolved PDF -> <đường_dẫn_PDF_thực>` *(dùng trực tiếp đường dẫn này nếu phải fallback scan)*.
    - `Extracted <N> figures -> <out_dir>`, kèm `[Note] Detected <K> scanned/full-page image page(s): [...]` (nếu có trang scan) và `Wrote manifest -> <out_dir>\manifest.json` (khi dùng `-Meta`).
    - Nếu bản rút gọn `<= -MaxMetaBytes` (`16 KB`): in thêm khối `=== MANIFEST JSON START === ... === MANIFEST JSON END ===` (đã cắt `caption`/`context` còn tối đa `-MaxMetaWords` từ) ngay trong stdout để Agent sử dụng luôn mà không cần gọi `read_file`; trong khi tệp `work\assets\manifest.json` trên ổ cứng vẫn giữ nguyên bản đầy đủ. Nếu vượt ngưỡng: in `Manifest too large for stdout (...); use read_file -> <path>` để Agent đọc phân trang.
- **Fallback PDF scan / cắt hình thủ công (`tools\pdf_fallback_tools.ps1`):** Mặc định bỏ qua; chỉ chạy theo mục **Phụ lục: Fallback PDF Scan** ở cuối tệp khi stdout báo `[Note] Detected ... scanned/full-page image page(s)` (`scanned_pages` khác rỗng) hoặc PDF có sơ đồ/khung hình phức tạp không tách tự động đủ.

## Bước 2: Đối chiếu bản đồ `manifest.json`, nội dung PDF, ảnh tách & Bộ quy tắc SI
- **Trường hợp PDF thuần văn bản (`0` hình):** Nếu Bước 1 báo `Extracted 0 figures` với `"figures": []` và `"scanned_pages": []` (và kiểm tra PDF thấy tài liệu chỉ gồm chữ/bảng biểu, không bị sót hình minh họa), **KHÔNG** gọi fallback scan và bỏ qua bước xem ảnh tách — chuyển thẳng sang Bước 3 để dịch và tạo `work\draft.html`.
- Nếu Bước 1 đã in khối `=== MANIFEST JSON START === ... === MANIFEST JSON END ===` ra stdout, **dùng ngay bản đồ đó** (không gọi `read_file` đọc lại `work\assets\manifest.json`). Chỉ dùng `read_file` (theo từng đoạn `StartLine`/`EndLine`) khi Bước 1 báo `Manifest too large for stdout`. Đối chiếu `page`, `bbox` và `caption`/`context` để đặt đúng thứ tự ảnh. **Lưu ý:** trong bản in `stdout` của `extract_pdf_assets.ps1`, trường `caption`/`context` được rút gọn tối đa 20 từ (`...`) **chỉ để định vị ảnh** (tệp `manifest.json` trên đĩa vẫn giữ nguyên toàn văn) — khi dịch `<figcaption>`, bắt buộc lấy toàn văn chú thích từ nội dung PDF gốc.
- **Đọc nội dung PDF:** Nếu người dùng kéo-thả PDF vào chat, nội dung OCR và ảnh chụp từng trang đã có sẵn trong tin nhắn đầu vào — **không gọi `read_file` đọc lại tệp PDF lần 2**; chỉ dùng `read_file` đọc `<input.pdf>` khi người dùng chỉ gửi đường dẫn tệp trong workspace.
- **Xem ảnh đối chiếu (nếu có):** Khi có ảnh tách trong `figures[]` hoặc ảnh cắt từ `CropFromJson`, gọi **song song trong 1 lượt** nhiều `read_file` với đường dẫn cụ thể từng tệp (lấy theo `work\assets\<figures[].file>` hoặc `work\assets\<out_name>`, vd: `work\assets\fig_p2_1.png`, ... — **không** dùng ký tự đại diện `*` như `work\assets\*.png` trong `read_file`) để đối chiếu trực quan và đánh giá xem sơ đồ nào nên giữ nguyên ảnh tách hay tái tạo thêm bằng HTML/CSS.

## Bước 3: Dịch & Tái tạo HTML/CSS theo Chuẩn SI
Viết file trung gian `work\draft.html` (bắt đầu `<!DOCTYPE html>`, kết thúc `</html>`) tuân thủ nghiêm ngặt [si_academic_html.md](./si_academic_html.md) và các ràng buộc tương thích với `html_packager.ps1`:
- **Ngôn ngữ & Thuật ngữ:** Áp dụng tái cấu trúc cú pháp có kiểm soát, bảo toàn *hedging*/nhân quả/bị động khách quan, ngôi xưng *chúng tôi* vs *chúng ta/ta*, quy đổi kép đơn vị (Imperial kèm gốc), định dạng số Việt Nam (nhưng giữ dấu `.` trong LaTeX & CSS), giữ nguyên thành phần nhận diện của `References` (link DOI/URL nhấp được).
- **Khung CSS Nội dung & Chuẩn bị gắn Vỏ tương tác:** Chèn đầy đủ khối CSS nội dung từ [si_academic_html.md](./si_academic_html.md) (giữ hệ biến màu Sáng/Dịu mắt/Tối, `body`, `figure`, `.table-wrapper`, `.ws-nowrap`, `.grid-*`, `pre`/`code` và `@media print` cho nội dung). **Không cần tự viết CSS/HTML/JS cho thanh công cụ đọc, mục lục tự động hay hộp phóng to ảnh** — `html_packager.ps1` sẽ tự động gắn lớp vỏ tương tác ở Bước 4 (chỉ cần giữ đủ cấu trúc `<head>...</head>` và `<body>...</body>` cùng thẻ ngữ nghĩa `<header>`, `<h1>`–`<h3>`, `<figure><img><figcaption>`).
- **Cấu trúc Ngữ nghĩa & Công thức:** Ép văn bản chính về **1 cột duy nhất** (nối các câu gãy dòng PDF, bỏ header/footer lặp); bọc mọi `<table>` trực tiếp trong `<div class="table-wrapper">` kèm `<thead>`/`<tbody>`/`<th>`; dùng LaTeX `\( \)` / `\[ \]` + nhúng `<script>` có `MathJax` vào `<head>` nếu bài có công thức.
- **Quy ước đường dẫn ảnh & định dạng hợp lệ:** `html_packager.ps1` phân giải đường dẫn `src` tương đối **theo thư mục cha chứa `-HtmlPath`** (tức `work\`). Vì vậy, trong `work\draft.html` **BẮT BUỘC viết `src="assets/fig_pX_Y.png"`** (tuyệt đối không viết `work/assets/...`) và chỉ dùng định dạng `.png`, `.jpg` hoặc `.jpeg` cho ảnh cục bộ trong `<img>`. Đối chiếu với `work\assets\manifest.json` (cộng thêm các tệp `out_name` vừa cắt từ `CropFromJson` nếu có dùng fallback) để đảm bảo **không bỏ sót hoặc đặt nhầm** ảnh, chèn `<figure><img src="assets/fig_pX_Y.png" alt="..."><figcaption>...</figcaption></figure>` đúng vị trí.
- **Xử lý Tài liệu Khoa học Dài (`> 10 trang`):** Không dịch gộp một lượt dễ bị cắt bớt hoặc tóm tắt. Chia theo từng mục/chương hoặc cụm 5–8 trang, ghi khung đầu `<head>` vào `work\draft.html` trước rồi nối dần (`Append` hoặc `edit_file`) từng `<section>` đầy đủ (giữ trọn mọi bảng biểu, hình minh họa trong `manifest.json` và mục `References`).

## Bước 4: Đóng gói song song HTML + PDF, kiểm tra & tự dọn nháp (`tools\html_packager.ps1`)
Chạy **một lệnh duy nhất** để nhúng Base64, chạy Auto-QA, xuất song song cả 2 tệp **`output\<tên_file_gốc>_vi.html`** và **`output\<tên_file_gốc>_vi.pdf`**, đồng thời tự động dọn thư mục nháp `work\` ngay khi thành công:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "tools\html_packager.ps1" -Action EmbedImages -HtmlPath "work\draft.html" -OutHtmlPath "output\<tên_file_gốc>_vi.html" -AlsoPdf -CleanDir "work"
```

- **Quy tắc đặt tên file đầu ra:** Lưu trong thư mục `output\` và giữ nguyên chính xác phần tên gốc không đuôi của file PDF trong workspace (vd: `bao-cao-2026.pdf` $\rightarrow$ `output\bao-cao-2026_vi.html` và `output\bao-cao-2026_vi.pdf`, không tự dịch tên file hay tự đổi sang slug khác). Riêng trường hợp kéo-thả vào chat khiến tệp tải lên mang tên tạm `media_<id>.pdf` (hệ thống không lưu tên gốc ban đầu trên máy): **không lấy tên tạm `media_...` và không tìm ngược tên gốc trên máy**, hãy đặt tên theo **tiêu đề chính ngắn gọn của tài liệu** (dạng ASCII `snake_case`, không dấu, trừ khi người dùng chỉ định rõ tên đầu ra) kèm `_vi.html` / `_vi.pdf`.

- **Contract `tools\html_packager.ps1`:**
  - **Action `EmbedImages`:**
    - Tham số: `-HtmlPath` *(bắt buộc)*, `-OutHtmlPath` *(tùy chọn; bỏ trống sẽ ghi đè `-HtmlPath` theo UTF-8 không BOM)*, `-AlsoPdf` *(switch xuất PDF cùng tên bên cạnh HTML đích)*, `-OutPdfPath` *(tùy chọn chỉ định đường dẫn PDF đích; cũng tự bật xuất PDF)*, `-JpegQuality` *(mặc định `90`)*, `-MaxImageWidth` *(mặc định `1400` px)*, `-CleanDir` *(tùy chọn; truyền `"work"` để tự xóa thư mục tạm **chỉ sau khi** `[QA PASS]` và xuất PDF thành công, và từ chối xóa nếu thư mục đích chứa tệp đầu ra hoặc là thư mục gốc)*.
    - **Tự động gắn lớp vỏ tương tác (`tools\reader_shell.html`):** Trước khi chạy Auto-QA, kiểm tra tệp HTML có đủ `<head>...</head>` và `<body>...</body>`, rồi bơm idempotent các mảnh còn thiếu (CSS vỏ `rsfv-*` trước `</head>`, thanh `.rsfv-toolbar` ngay sau `<body...>`, và `#rsfv-img-lightbox` + `<script>` trước `</body>`); bỏ qua nếu HTML đã có sẵn vỏ tương tác (kể cả định dạng cũ `.reader-toolbar` / `#img-lightbox`).
    - **Tối ưu ảnh:** Ảnh chụp nhiều màu không có kênh alpha (`>= 200` cụm màu mẫu) được thử nén JPEG theo `-JpegQuality` và chỉ giữ khi nhỏ hơn bản gốc (`<= 85%` nếu không resize); sơ đồ ít màu hoặc có độ trong suốt được giữ nguyên PNG.
    - **Cổng Auto-QA (chạy trước khi ghi tệp ra `output\` — ném lỗi dừng chạy nếu vi phạm bất kỳ điều kiện nào sau đây; khi fail sẽ không tạo/ghi đè tệp đích và giữ nguyên `work\` để sửa):**
      1. `0` thẻ `<img>` trỏ tới tệp cục bộ chưa được nhúng (mọi `src` phải là `data:image/...` hoặc `http(s)://`).
      2. Mọi thẻ `<img>` đều phải có thuộc tính `alt`.
      3. Số container `.table-wrapper` $\ge$ số `<table>` (ngoài `<script>`/`<style>`).
      4. Nếu ngoài `<script>`/`<style>` xuất hiện `\(` hoặc `\[`, HTML phải chứa `<script ... MathJax>`.
      5. `0` liên kết nội bộ `href="#..."` bị gãy (đều có `id="..."` tương ứng).
      - *Phục hồi khi QA fail:* Đọc thông báo lỗi từ stdout/stderr, mở sửa trực tiếp `work\draft.html` rồi chạy lại đúng lệnh Bước 4.
  - **Action `HtmlToPdf`** *(xuất PDF độc lập từ tệp HTML đã đóng gói trọn vẹn / self-contained)*:
    - CLI: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "tools\html_packager.ps1" -Action HtmlToPdf -HtmlPath "<in.html>" [-OutPdfPath "<out.pdf>"] [-CleanDir "<dir>"]`
    - Tự tìm Microsoft Edge (ưu tiên) hoặc Chrome headless có sẵn trên Windows để in PDF (bỏ header/footer trình duyệt). Nếu bỏ trống `-OutPdfPath`, xuất cùng thư mục với đuôi `.pdf`. Nếu máy không có Edge/Chrome, xuất cảnh báo `Write-Warning` và bỏ qua xuất PDF.
  - **Đầu ra stdout xác nhận thành công (theo thứ tự thực thi):**
    - `[QA PASS] Base64 images: <N> | Tables wrapped: <M>/<M> | LaTeX/MathJax OK | Broken anchors: 0`
    - `Injected reader shell -> CSS, Toolbar, Script` *(hoặc `Reader shell already present (skipped injection)`)*
    - `Embedded images into HTML -> <đường_dẫn>.html (<bytes> bytes)`
    - `Exported PDF -> <đường_dẫn>.pdf (<bytes> bytes)`
    - `Cleaned temp directory -> <đường_dẫn>\work` *(khi dùng `-CleanDir`)*
- Xác nhận từ stdout lệnh trên đã có `[QA PASS]`, `Injected reader shell` (hoặc `already present`), `Embedded images into HTML`, `Exported PDF` và `Cleaned temp directory` (không cần gọi thêm lệnh xóa `work\` riêng).
- **Quy tắc phản hồi sau khi hoàn tất:** Chỉ trả về liên kết tới 2 tệp đầu ra (`output\<tên_file_gốc>_vi.html` và `output\<tên_file_gốc>_vi.pdf`) kèm xác nhận ngắn gọn (số ảnh nhúng / trạng thái QA). **Tuyệt đối không tự ý viết bản tóm tắt hay lặp lại nội dung tài liệu đã dịch** trừ khi người dùng yêu cầu rõ.

---

## Phụ lục: Fallback PDF Scan (`tools\pdf_fallback_tools.ps1`)
Chỉ sử dụng khi Bước 1 phát hiện trang scan (`scanned_pages` khác rỗng / stdout có `[Note] Detected ... scanned/full-page image page(s)`) hoặc thiếu khung hình phức tạp không tách tự động được:

1. **Render từng trang ra PNG (`RenderPages`):**
   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "tools\pdf_fallback_tools.ps1" -Action RenderPages -PdfPath "<input.pdf>" -OutDir "work\pages"
   ```
   - Tham số tùy chọn: `-Scale` (mặc định `2.5`; bề rộng ảnh tối thiểu `800` px). Với file kéo-thả, lấy `<input.pdf>` trực tiếp từ dòng `Resolved PDF -> ...` ở Bước 1.
   - Đầu ra: `work\pages\page_1.png`, `page_2.png`, ...
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
