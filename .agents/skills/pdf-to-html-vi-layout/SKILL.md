---
name: pdf-to-html-vi-layout
description: >-
  Quy trình dịch tệp PDF sang HTML/PDF tiếng Việt theo chế độ BẢO TOÀN TỐI ĐA THIẾT KẾ & BỐ CỤC TỪNG TRANG (tách pha dịch Markdown trung gian trước khi dựng HTML/CSS cô lập từng trang, không gắn reader_shell.html). CHỈ kích hoạt khi người dùng nêu rõ các yêu cầu như "bảo toàn thiết kế", "bảo toàn layout", "giữ thiết kế", "giữ layout", "giữ nguyên định dạng"; nếu chỉ yêu cầu dịch sang tiếng Việt thì dùng skill mặc định `pdf-to-html-vi`.
---

# `pdf-to-html-vi-layout` — Dịch PDF sang HTML/PDF Bảo toàn Thiết kế (Quy trình Tách pha Tiết kiệm Token)

Quy trình 4 bước tự động hoàn toàn (người dùng **không cần gõ bất kỳ câu lệnh nào**). Phần **Contract công cụ** bên dưới đã mô tả đủ đầu vào/đầu ra và quy ước đường dẫn; Agent **gọi trực tiếp CLI theo đúng contract và không cần mở mã nguồn trong `tools\`**.

> **QUY TẮC CỨNG (KHÔNG DÙNG PYTHON HỆ THỐNG):** **Tuyệt đối KHÔNG gọi `python`, `python3`, `py`, `pip`** hoặc mở/chạy các tệp nguồn tham khảo trong `tools\src\`. Mọi thao tác tách ảnh, fallback scan và đóng gói đều chạy bằng các wrapper portable chuyển tiếp vào `extract_assets.exe` (`tools\extract_pdf_assets.ps1`, `tools\pdf_fallback_tools.ps1` và `tools\html_packager.ps1`).

---

## Bước 1: Tách ảnh & Nạp Chỉ dẫn Chuyên Dịch (`si_translation.md`)
> **Tối ưu token theo Pha (*Lazy Phase Loading*):** Ngay trong lượt Bước 1, gọi **đồng thời** lệnh tách ảnh dưới đây và `read_file` **CHỈ đọc trọn 1 lần** [si_translation.md](./si_translation.md) (~126 dòng / ~17 KB — không truyền `StartLine`/`EndLine`). **TUYỆT ĐỐI CHƯA đọc `si_layout.md` ở Bước 1** để giữ ngữ cảnh gọn nhẹ và giúp Agent dồn 100% sự tập trung cho chất lượng dịch thuật ở Bước 2.

Chọn 1 trong 2 lệnh sau tùy cách người dùng cung cấp tệp PDF:

- **Trường hợp 1 — Kéo-thả PDF trực tiếp vào khung chat** *(dấu hiệu: trong tin nhắn đã có sẵn nội dung OCR/ảnh từng trang PDF và người dùng **không** ghi đường dẫn tệp `.pdf` trong workspace)*: **KHÔNG dùng `read_file` mở `transcript.jsonl`**, chạy thẳng 1 lệnh sau (thay `<appDataDir>` và `<conversation-id>` bằng giá trị sẵn có trong `<user_information>`):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "tools\extract_pdf_assets.ps1" -TranscriptPath "<appDataDir>\brain\<conversation-id>\.system_generated\logs\transcript.jsonl" -OutDir "work\assets" -Meta
```

- **Trường hợp 2 — Tệp PDF nằm sẵn trên đĩa (trong workspace)**:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "tools\extract_pdf_assets.ps1" -PdfPath "<input.pdf>" -OutDir "work\assets" -Meta
```

- **Contract `tools\extract_pdf_assets.ps1`** *(cổng gọi CLI duy nhất ở Bước 1; bên trong tự gọi `extract_assets.exe` — **không mở mã nguồn `.ps1`/`.py`**)*:
  - **Tham số:** `-PdfPath` hoặc `-TranscriptPath`, `-OutDir` *(mặc định `work\assets`)*, `-Dpi <int>` *(`36–1200`, mặc định `180`; tăng `250`–`300` với ảnh/sơ đồ Nhóm B chữ nhỏ)*, `-Meta` *(xuất `manifest.json`)*, `-MaxMetaBytes <int>` *(mặc định `16384`)*, `-MaxMetaWords <int>` *(mặc định `20`; đặt `0` để in đủ)*.
  - **Đầu ra `manifest.json` & stdout:** `pdf`, `dpi`, `total_pages`, `scanned_pages[]` (`1`-based), và `figures[]` (`file`, `page`, `source` `"raster"|"vector"|"hybrid"`, `drawings` `int`, `placement` `"figure"|"table_cell"`, `box` `[x0, y0, x1, y1]` chuẩn hóa `0.0–1.0` **cùng hệ tọa độ với `CropFromJson`**, `width_px`, `height_px`, `caption`, `context`). Stdout luôn in `Resolved PDF -> <path>` (dùng khi cần fallback scan) và khối `=== MANIFEST JSON START ===` (nếu `<= -MaxMetaBytes`) hoặc báo `Manifest too large for stdout` để đọc phân trang bằng `read_file`.
  - **Fallback PDF scan / cắt hình thủ công (`tools\pdf_fallback_tools.ps1`):** Mặc định bỏ qua; chỉ chạy theo mục **Phụ lục: Fallback PDF Scan** khi `scanned_pages` khác rỗng hoặc PDF chuẩn có ảnh/biểu đồ **phức tạp (Nhóm B)** bị tách sót.

---

## Bước 2: Đối chiếu Ảnh & Dịch thuần sang Markdown (`work\translated.md`)

1. **Kiểm kê ảnh & Đọc đối chiếu (không tốn lượt thừa):**
   - **PDF thuần văn bản (`0` hình):** Nếu Bước 1 báo `Extracted 0 figures` (`"figures": []` và `"scanned_pages": []`) và kiểm tra PDF xác nhận không sót hình minh họa → bỏ qua bước xem ảnh và fallback, dịch thẳng sang `work\translated.md`.
   - **Dùng `manifest.json` trên stdout:** Nếu Bước 1 đã in khối `=== MANIFEST JSON START === ... === MANIFEST JSON END ===`, dùng ngay (không gọi `read_file` đọc lại `work\assets\manifest.json`; chỉ đọc theo đoạn khi stdout báo vượt ngưỡng 16 KB). **CẢNH BÁO:** chuỗi `caption`/`context` rút gọn 20 từ (`...`) trên stdout chỉ dùng định vị — khi dịch phải lấy toàn văn từ PDF gốc hoặc đọc đĩa.
   - **Đọc PDF:** Nếu kéo-thả PDF vào chat, nội dung và ảnh từng trang đã có sẵn trong tin nhắn đầu — **không gọi `read_file` đọc lại tệp PDF lần 2**; chỉ gọi `read_file` đọc `<input.pdf>` khi tệp nằm trong workspace.
   - **Sàng lọc trước khi cắt fallback (`Triage before Crop`):** Khi gặp trang scan hoặc hình bị tách sót, **KHÔNG dùng `CropFromJson` cho sơ đồ đơn giản (Nhóm A)** — giữ để dựng HTML/CSS ở Bước 3 *(chỉ chạy `RenderPages` trang đó nếu chữ bị mờ)*. Chỉ chạy `RenderPages` + `CropFromJson` cho hình/ảnh chụp phức tạp (**Nhóm B**).
   - **Bắt buộc `read_file` song song ảnh đã tách:** Khi có ảnh trong `figures[]` hoặc vừa cắt bằng `CropFromJson`, gọi **song song trong 1 lượt** nhiều `read_file` với đường dẫn cụ thể từng tệp (`work\assets\<figures[].file>` / `work\assets\<out_name>`, tuyệt đối không dùng `*`) để kiểm chứng chất lượng cắt, đối chiếu 1–1 với PDF gốc + `manifest.json`, tránh lắp "mù" và đảm bảo biết rõ nội dung hình để dịch chú thích/nhãn chính xác.

2. **Xuất bản dịch trung gian `work\translated.md` (tuân thủ [si_translation.md](./si_translation.md)):**
   - Chỉ viết **nội dung tiếng Việt đã dịch đầy đủ**, bọc từng trang bằng thẻ ngắn:
     `<!-- p:1 --> ... <!-- /p:1 -->`
   - Đánh dấu vị trí các thành phần bằng tag siêu gọn (`[FIG: fig_pX_Y.png]`, `[TBL-IMG: fig_pX_Y.png]`, `[DIAGRAM-A]`, `[CALLOUT]`, `[HEADER]`, `[FOOTER]`, `[FN]`, bảng Markdown). **TUYỆT ĐỐI KHÔNG viết mô tả CSS, màu sắc hay pixel vào `work\translated.md`** (tránh đốt token vô ích vì Bước 3 nhìn thẳng PDF gốc + `box` `0..1`).
   - Áp dụng nghiêm ngặt quy tắc **dịch đầy đủ 100% nội dung** (mọi đoạn văn, phụ lục, bảng biểu và trọn vẹn `References` kèm DOI/URL — **tuyệt đối không tóm tắt hay rút gọn `...`**), xử lý **câu vắt qua ranh giới hai trang** (`<!-- cont -->`, không chém cụt câu) và **dịch súc tích cho các hộp/ô hẹp**.
   - **Độ dài tài liệu:** Nếu `<= 6 trang`, ghi trọn 1 lần vào `work\translated.md`. Nếu `> 6 trang`, chia từng cụm `5–6` trang nối dần (`Append` / `edit_file`) vào `work\translated.md` — **thực hiện liên tục đủ mọi lô tới hết tài liệu rồi chuyển thẳng sang Bước 3; KHÔNG dừng lại giữa chừng để hỏi xác nhận làm tiếp.**

---

## Bước 3: Nạp `si_layout.md` & Tái tạo Từng Trang vào `work\draft.html`
1. **Nạp chỉ dẫn thiết kế:** Gọi `read_file` đọc **trọn 1 lần** [si_layout.md](./si_layout.md) (~241 dòng / ~20 KB — không truyền `StartLine`/`EndLine`).
   - *Tiết kiệm token đọc lại:* Nếu tài liệu `<= 6 trang` và `work\translated.md` vừa được tạo ngay ở lượt trước (đã nằm đầy đủ trong ngữ cảnh), dùng trực tiếp để dựng HTML — **không gọi `read_file` đọc lại `work\translated.md`**; chỉ đọc phân trang theo `StartLine`/`EndLine` khi tài liệu dài đã chia nhiều lô hoặc ngữ cảnh đã cũ.
2. **Dựng `work\draft.html` (`<!DOCTYPE html> ... </html>`) chuẩn [si_layout.md](./si_layout.md):**
   - **Chế độ thuần HTML/CSS:** **TUYỆT ĐỐI KHÔNG** viết thanh công cụ đọc, hộp Mục lục tự động, lightbox phóng to ảnh hay bất kỳ `<script>` nào (ngoại trừ đúng 1 thẻ `<script id="MathJax-script" ...>` nếu bài có LaTeX `\( \)` / `\[ \]` — và nhớ **chừa khoảng trắng quanh `<` và `>`**: `\( x < y \)`). Chuyển hóa sạch toàn bộ tag trung gian từ `work\translated.md` (`[FIG:]`, `[CALLOUT]`, `<!-- p:N -->`, `<!-- cont -->`...) và gắn `<a href="..." target="_blank" rel="noopener">` cho mọi URL/DOI trong `References`.
   - **Global CSS + Cô lập Từng Trang:** Định nghĩa **Global CSS** ở `<head>` (font `'Inter'` + fallback `'Segoe UI'`, cỡ thân bài `18px`, `--page-width` linh hoạt trong `740px–1000px`, bảng màu trích từ PDF gốc, `.pdf-page` khung tờ giấy chiều cao `height: auto`, `.multi-column-flow` cho văn bản chảy liên tục, bảng biểu, callout, `@media print`). Bên trong `<body>`, bọc mỗi trang bằng `<section id="pdf-page-N" class="pdf-page" data-page="N">...</section>`, dùng `id` scoped `#pdf-page-N ...`, `class` và `style="..."` nội tuyến cho các khác biệt cục bộ từng trang.
   - **Ảnh & Sơ đồ:** `html_packager.ps1` phân giải đường dẫn `src` tương đối **theo thư mục cha của `-HtmlPath`** (tức `work\`). Vì vậy, trong `work\draft.html` **BẮT BUỘC viết `src="assets/<tên_file>.png"`** *(tuyệt đối không viết `work/assets/...`)*, chỉ dùng `.png`/`.jpg`/`.jpeg`, đủ `alt` tiếng Việt, toàn văn `<figcaption>`. Đối chiếu `manifest.json` (`box` `0.0–1.0`, `placement`, `source`/`drawings`) + ảnh cắt `CropFromJson` để đặt đúng ảnh Nhóm B / ảnh ô `<td>`, và tái tạo trọn vẹn sơ đồ Nhóm A bằng HTML/CSS.
   - **Độ dài tài liệu:** Nếu `<= 6 trang`, ghi trọn 1 lần vào `work\draft.html`. Nếu `> 6 trang`, ghi `<head>` + Global CSS trước rồi nối dần từng cụm `3–4 trang` (`<section id="pdf-page-...">`) vào `work\draft.html` (đóng `</body></html>` ở lô cuối) — **chạy liên tục hết mọi cụm trang rồi chạy luôn Bước 4 đóng gói xuất tệp; TUYỆT ĐỐI KHÔNG dừng giữa chừng để báo tiến độ hay hỏi có làm tiếp không.**
   - Thực hiện rà soát 5 điểm ở **Mục 5** của [si_layout.md](./si_layout.md) trước khi đóng gói.

---

## Bước 4: Đóng gói bằng `-PreserveLayout`, Xuất PDF & Tự Dọn `work\` (`tools\html_packager.ps1`)
Chạy **trực tiếp lệnh duy nhất** dưới đây (**KHÔNG mở đọc `tools\html_packager.ps1`**) với công tắc **`-PreserveLayout`** để nhúng Base64 (giữ nguyên 100% HTML/CSS do AI tạo, không bơm `reader_shell.html`), chạy Auto-QA bảo toàn thiết kế, xuất song song **`output\<tên_file_gốc>_layout_vi.html`** và **`output\<tên_file_gốc>_layout_vi.pdf`**, và tự động xóa sạch toàn bộ thư mục nháp `work\` (gồm cả `work\translated.md` và `work\draft.html`):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "tools\html_packager.ps1" -Action EmbedImages -HtmlPath "work\draft.html" -OutHtmlPath "output\<tên_file_gốc>_layout_vi.html" -PreserveLayout -AlsoPdf -CleanDir "work"
```

- **Quy tắc đặt tên file đầu ra & Chống ghi đè:** Lưu trong `output\` với hậu tố **`_layout_vi`** và giữ nguyên chính xác tên gốc không đuôi của file PDF trong workspace (vd: `bao-cao-2026.pdf` → `output\bao-cao-2026_layout_vi.html` và `output\bao-cao-2026_layout_vi.pdf`). Riêng trường hợp kéo-thả PDF mang tên tạm `media_<id>.pdf`: đặt tên theo **tiêu đề chính ngắn gọn của tài liệu** dạng ASCII `snake_case`, không dấu kèm `_layout_vi.html` / `_layout_vi.pdf`.
  - **Không tự đoán/gắn tên model AI** vào tên file (chỉ thêm nhãn phụ nếu người dùng chỉ định rõ trong câu lệnh).
  - **Tự động tăng số `_2`, `_3` khi trùng:** Nếu tệp `.html` hoặc `.pdf` đích đã tồn tại trong `output\`, `html_packager.ps1` luôn tự tạo thư mục (nếu chưa có) và **tự động đánh số đồng bộ cả cặp** thành `<tên>_layout_vi_2.html` / `_layout_vi_2.pdf`, `_3`... để tránh ghi đè bản trước — **KHÔNG** chạy thêm lệnh kiểm tra/liệt kê `output\` trước hoặc sau Bước 4.

- **Contract `tools\html_packager.ps1`:**
  - **Action `EmbedImages`:**
    - **Tham số:** `-HtmlPath` *(bắt buộc)*, `-OutHtmlPath` *(tùy chọn; bỏ trống sẽ cập nhật trực tiếp `-HtmlPath` theo UTF-8 không BOM)*, `-PreserveLayout` *(switch bắt buộc cho Skill 2 — bỏ tiêm `reader_shell.html` và bỏ yêu cầu `.table-wrapper`)*, `-AlsoPdf` *(switch xuất PDF cùng tên/cùng chỉ số bên cạnh HTML đích bằng Edge/Chrome headless)*, `-OutPdfPath` *(tùy chọn chỉ định đường dẫn PDF đích; cũng tự bật xuất PDF)*, `-JpegQuality <int>` *(`1–100`, mặc định `95`)*, `-MaxImageWidth <int>` *(`0–10000`, mặc định `1400` px)*, `-CleanDir` *(tùy chọn; truyền `"work"` để tự xóa thư mục tạm **chỉ sau khi** `[QA PASS]` và xuất PDF thành công; từ chối xóa nếu ngoài `work\` hoặc chứa tệp đầu ra)*, `-PdfTimeoutSeconds <int>` *(`5–600`, mặc định `60`)*.
    - **Tối ưu ảnh:** Ảnh chụp nhiều màu không có kênh alpha (`>= 200` cụm màu mẫu) được thử nén JPEG theo `-JpegQuality` (giữ bản nhỏ hơn `<= 85%` nếu không resize); sơ đồ ít màu hoặc có kênh alpha được giữ nguyên PNG. Ảnh vượt `-MaxImageWidth` tự co theo tỷ lệ.
    - **Cổng Auto-QA dưới `-PreserveLayout` (chạy trước khi ghi tệp ra `output\` — ném lỗi dừng chạy nếu vi phạm; khi fail KHÔNG tạo tệp đích và vẫn giữ nguyên `work\` để sửa):**
      1. HTML có đủ thẻ `<head>...</head>` và `<body>...</body>`.
      2. `0` thẻ `<img>` trỏ tới tệp cục bộ chưa được nhúng hoặc đường dẫn ảnh mạng ngoài (`http(s)://`) — mọi `<img>` đều phải là Base64 nội bộ và đều có thuộc tính `alt`.
      3. Cho phép `<table>` không bọc `.table-wrapper` để giữ nguyên cấu trúc bảng vừa trang.
      4. Nếu ngoài `<pre>`/`<code>`/`<textarea>`/`<script>`/`<style>` và HTML comment xuất hiện `\(` hoặc `\[`, HTML phải có thẻ `<script>` MathJax v3 CDN tin cậy (`cdn.jsdelivr.net` / `cdnjs.cloudflare.com`, thân thẻ rỗng) trong `<head>`.
      5. `0` liên kết nội bộ `href="#..."` bị gãy (đều có `id="..."` tương ứng trong DOM thật).
      6. **An toàn HTML/DOM:** Chỉ cho phép duy nhất `<script>` MathJax CDN hợp lệ trong `<head>` (**tuyệt đối cấm mọi `<script>` nội tuyến kể cả `reader_shell.html`**); chặn `<iframe>`/`<object>`/`<embed>`/`<applet>`/`<base>`/`<form>`/`<meta http-equiv="refresh">`, thuộc tính `on*`/`srcdoc`/`ping`, URI nguy hiểm (`javascript:`, `vbscript:`, `file:`, `//...`, `data:` ngoài ảnh raster), và tài nguyên/CSS `url(...)` trỏ ra ngoài ngoài Google Fonts.
      - *Phục hồi khi QA fail:* Xem dòng báo lỗi trên stdout/stderr, mở sửa thẳng `work\draft.html` rồi chạy lại đúng lệnh Bước 4 (không chạy lại Bước 1–2).
  - **Action `HtmlToPdf`** *(xuất PDF độc lập từ HTML đã đóng gói)*:
    - CLI: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "tools\html_packager.ps1" -Action HtmlToPdf -HtmlPath "<in.html>" [-OutPdfPath "<out.pdf>"] [-PdfTimeoutSeconds <60>] [-CleanDir "<dir>"]` *(tự tìm Microsoft Edge hoặc Chrome headless, tự đánh số `_2`, `_3`... nếu PDF đích đã tồn tại; phát `Write-Warning` và bỏ qua nếu thiếu trình duyệt)*.
  - **Đầu ra stdout xác nhận thành công (theo thứ tự thực thi):**
    - `[QA PASS] Base64 images: <N> | Tables: <T> (wrapper optional) | LaTeX/MathJax OK | Broken anchors: 0`
    - `Output collision avoided; auto-numbered -> <đường_dẫn>` *(nếu tệp cũ đã tồn tại)*
    - `PreserveLayout mode: skipped reader shell injection`
    - `Embedded images into HTML -> <đường_dẫn>.html (<bytes> bytes)`
    - `Exported PDF -> <đường_dẫn>.pdf (<bytes> bytes)`
    - `Cleaned temp directory -> <đường_dẫn>\work` *(khi dùng `-CleanDir` — đủ căn cứ xác nhận từ stdout, không cần gọi thêm lệnh kiểm tra `output\` hay xóa `work\` riêng)*
- **Quy tắc phản hồi sau khi hoàn tất:** Lấy **đúng tên tệp thực tế** in ở `Embedded images into HTML -> ...` và `Exported PDF -> ...` trên stdout (kể cả khi đã tự tăng số `_2`, `_3`...), rồi trả về liên kết tới các tệp đầu ra theo đúng mẫu thân thiện với người dùng cuối bên dưới (**tránh dùng các cụm từ kỹ thuật** như `"tự chứa"`, `"Self-contained"`, `"Base64"`, `"QA PASS"`, hay nhắc thư mục tạm `work/`; **tuyệt đối không tự ý viết bản tóm tắt hay lặp lại nội dung tài liệu đã dịch** trừ khi người dùng yêu cầu rõ):

  ```markdown
  Bản dịch tiếng Việt (chế độ giữ thiết kế) đã hoàn thành (nằm ở thư mục `output` trong thư mục ứng dụng):
  - **HTML (mở bằng trình duyệt):** [<tên_tệp_thực_tế>.html](file:///<đường_dẫn_workspace>/output/<tên_tệp_thực_tế>.html) *(thường cho kết quả hiển thị, bố cục đẹp hơn)*
  - **PDF:** [<tên_tệp_thực_tế>.pdf](file:///<đường_dẫn_workspace>/output/<tên_tệp_thực_tế>.pdf)

  **Trạng thái kiểm định:** Đạt chuẩn (đã tích hợp đủ <N> ảnh vào HTML, <T> bảng biểu giữ đúng thiết kế, 0 liên kết gãy).
  ```
  *(Điều chỉnh số liệu trong ngoặc theo kết quả Auto-QA thực tế — vd bổ sung `công thức toán đầy đủ` nếu bài có LaTeX, lược ý ảnh / bảng nếu bằng `0`; nếu máy thiếu Microsoft Edge/Chrome nên bỏ qua xuất PDF, thay dòng PDF thành: `- **PDF:** Chưa xuất được do máy không có sẵn Microsoft Edge hoặc Chrome (bạn vẫn có thể mở tệp HTML bằng trình duyệt rồi In → Lưu thành PDF).`)*

---

## Phụ lục: Fallback PDF Scan (`tools\pdf_fallback_tools.ps1`)
Chỉ sử dụng khi Bước 1 phát hiện trang scan (`scanned_pages` khác rỗng) hoặc PDF chuẩn có hình/biểu đồ phức tạp bị tách sót (**không mở đọc `tools\pdf_fallback_tools.ps1`**):

> **Quy tắc Sàng lọc trước khi Cắt (`Triage before Crop`):**
> - **Sơ đồ/biểu đồ đơn giản (Nhóm A — tái tạo được bằng HTML/CSS):** **KHÔNG dùng `CropFromJson`**. Nếu ảnh trang có sẵn từ PDF đã đọc rõ chữ → bỏ qua cả `RenderPages` lẫn `CropFromJson`, dựng thẳng HTML/CSS ở Bước 3; chỉ gọi `RenderPages` trang đó nếu cần soi chữ mờ.
> - **Ảnh chụp & biểu đồ phức tạp (Nhóm B — bắt buộc giữ PNG):** Mới chạy 2 bước `RenderPages` → `CropFromJson`.

1. **Render từng trang ra PNG (`RenderPages`):**
   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "tools\pdf_fallback_tools.ps1" -Action RenderPages -PdfPath "<input.pdf>" -OutDir "work\pages" -Pages "<trang_can_render>"
   ```
   - Tham số: `-PdfPath`, `-OutDir` *(mặc định `.`)*, `-Pages` *(vd `"2"`, `"2,5"`, `"2-4"` — bỏ trống sẽ render toàn bộ trang; với file kéo-thả lấy `<input.pdf>` từ dòng `Resolved PDF -> ...` ở Bước 1)*, `-Scale <double>` *(`0.5–10.0`, mặc định `2.5`; bề rộng tối thiểu `800` px)*. Đầu ra: `work\pages\page_<p>.png`.
2. **Cắt ảnh theo tọa độ JSON (`CropFromJson`):**
   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "tools\pdf_fallback_tools.ps1" -Action CropFromJson -SpecJson "work\crop_spec.json" -OutDir "work\assets"
   ```
   - **Contract `work\crop_spec.json` (UTF-8, mảng JSON):**
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
     - `page_png` *(bắt buộc)*, `box` *(bắt buộc `[x0, y0, x1, y1]` `0.0–1.0`, `x1 > x0`, `y1 > y0`)*, `out_name` *(bắt buộc, tên file đơn trong `-OutDir`)*, `auto_trim` *(tùy chọn, mặc định `true`)*. **Lưu ý:** In `Cropped <out_name> -> <path> (<W>x<H>)` và **không** tự cập nhật `work\assets\manifest.json`; dùng trực tiếp `out_name` ở Bước 2 & 3 và mở kiểm tra lại qua `read_file`.
