# Hướng dẫn phát triển Luka-Loop

Tệp này dành cho người và AI agent khi **phát triển, sửa lỗi hoặc kiểm thử chính công cụ**. Khi dịch tài liệu, làm theo `AGENTS.md` và `SKILL.md`, không làm theo tệp này. Ở chế độ phát triển được phép đọc mã nguồn `tools\` và dùng Python hệ thống để build/test.

## Môi trường

- Windows 10/11 x64, Windows PowerShell 5.1 (có sẵn) và nên có PowerShell 7 (`pwsh`) để chạy test trên cả hai phiên bản như CI.
- Python **3.12.7** (khớp CI) và các gói ghim phiên bản: `python -m pip install -r tools\src\requirements-build.txt` (PyMuPDF, PyInstaller).
- Microsoft Edge hoặc Google Chrome để chạy các test xuất PDF thật.

## Cấu trúc mã

- `tools\src\` — mã nguồn Python của `extract_assets.exe`:
  - `extract_assets.py`: điểm vào CLI, phân luồng theo `--mode` (`extract`, `render-pages`, `crop-json`, `embed-images`, `html-to-pdf`).
  - `figure_detector\` (package): tách hình/sơ đồ theo bố cục (pipeline 6 pha, ngưỡng gom trong `DetectorConfig`). Phân tầng — mỗi module chỉ import từ module đứng trước: `model` (proxy `pymupdf` nạp trễ, `DetectorConfig`, regex chú thích, dataclass) → `geometry` → `text` (Pha 1) → `caption_match` (khớp chú thích, dùng chung cho Pha 2–6) → `raster` (Pha 2) → `vector` (Pha 3) → `captions` (Pha 4) → `merge` (Pha 5) → `pipeline` (chạy Pha 1–5 cho một trang) → `extract` (Pha 6, `extract_images`). `__init__.py` giữ nguyên các tên công khai cũ.
    - **Quy tắc phân loại cụm vector (Pha 3, `vector.py`):** `_evaluate_vector_cluster` áp lần lượt các quy tắc trong `_VECTOR_CLUSTER_RULES`; quy tắc đầu tiên trả về `FilterDecision` thắng, không quy tắc nào loại thì giữ cụm. Mỗi quy tắc là một hàm `_reject_<lý_do>(f)` nhận `_ClusterFeatures` (các đặc trưng tính lười bằng `cached_property`, nên phần nặng như `get_text`/`find_tables` chỉ chạy khi có quy tắc cần) và tự nêu đủ điều kiện của mình (kể cả "không có raster", "không có chú thích hình"). Thêm quy tắc mới: viết hàm `_reject_...`, chèn vào đúng vị trí trong `_VECTOR_CLUSTER_RULES` (thứ tự quyết định lý do thắng), cập nhật `test_rule_order_is_unchanged` và thêm ca thử trong `tests\test_vector_rules.py`; nếu kết quả tách hình đổi có chủ đích, sinh lại golden và xem kỹ diff.
  - `image_ops.py`: render trang, cắt ảnh theo JSON, tối ưu ảnh.
  - Bước 4 (đóng gói), tách theo trách nhiệm — `packager.py` → `reader_shell.py`, `html_qa.py`, `pdf_export.py`, `output_paths.py` (không có vòng phụ thuộc):
    - `packager.py`: điểm vào `embed-images` — nhúng ảnh Base64 rồi điều phối các module dưới.
    - `reader_shell.py`: gắn `tools\reader_shell.html` (CSS, thanh công cụ, script), lấy script tin cậy, tiêm CSP.
    - `html_qa.py`: Auto-QA — bộ quét DOM & bảo mật một lượt (`_QADOMScanner`, `run_html_qa_check`).
    - `pdf_export.py`: điểm vào `html-to-pdf` — xuất PDF bằng Edge/Chrome headless cô lập.
    - `output_paths.py`: làm sạch tên tệp đầu ra, đánh số `_2`/`_3`, dọn `work\` sau khi đã có đầu ra.
  - `transcript.py`: tìm PDF đính kèm mới nhất trong `transcript.jsonl` (Antigravity `-TranscriptPath`).
  - `manifest.py`: in bản rút gọn `manifest.json` ra stdout (chỉ dùng thư viện chuẩn, không import module nào khác của dự án — bộ tách hình không phụ thuộc bộ đóng gói).
  - `path_guards.py`: kiểm tra an toàn đường dẫn (UNC, NTFS ADS, symlink/junction, tên thiết bị Windows), dọn `work\` an toàn.
- `tools\*.ps1` — wrapper PowerShell mỏng chuyển tiếp tham số vào exe; `tools\_path_guards.ps1` là tiện ích dùng chung.
- `tools\extract_assets\` — kết quả build (không đưa vào git; gói phát hành do CI build).
- Chỉ dẫn cho agent: `AGENTS.md`, `CLAUDE.md`, `.agents\skills\` (quy trình + SI dịch), `.agents\adapters\` (chi tiết riêng từng môi trường agent), `.claude\` (lối vào và quyền cho Claude Code).

## Build và test

```powershell
.\tools\build_extractor.ps1                 # build lại tools\extract_assets\extract_assets.exe
.\tests\run_tests.ps1 -IncludePython        # test PowerShell 5.1 + toàn bộ test Python
pwsh -NoProfile -File .\tests\run_tests.ps1 # test PowerShell 7
```

- **Build lại exe sau mọi thay đổi trong `tools\src\`** trước khi chạy test PowerShell: các wrapper và test PowerShell gọi exe, không gọi mã Python.
- Chạy nhanh riêng test Python: `$env:PYTHONUTF8='1'; python -m unittest discover -s tests -p "test_*.py"`.
- Các tệp test chỉ cần thư viện chuẩn (không cần PyMuPDF/Edge): `test_skill_contracts.py`, `test_pdf_export_resilience.py`, `test_clean_dir_scope.py`, `test_cli.py`, `test_eval_doclaynet.py`.
- Test chỉ ghi vào thư mục tạm của hệ thống, không ghi vào `work\` hay `output\` của dự án.
- CI (`.github\workflows\ci.yml`) chạy khi đổi `tools/**`, `tests/**`, `.agents/**` hoặc `AGENTS.md`; quy trình phát hành (`release.yml`) chạy khi đẩy tag `v*`.

## Đánh giá bộ tách hình trên DocLayNet

`dev\eval_doclaynet.py` chạy chính mã `figure_detector` (giống trong exe) trên PDF gốc nhúng trong **DocLayNet v1.2** (bản parquet trên Hugging Face, có cột `pdf`) và so với hộp `Picture` do người gán nhãn — chỉ lấy `doc_category = scientific_articles`. Cần Python hệ thống có thêm `pyarrow`; bộ dữ liệu (~37 GB) để ngoài repo, truyền đường dẫn qua `--data`.

```powershell
python -X utf8 dev\eval_doclaynet.py --data D:\PdfSamples --subset tune                       # đo trên tập hiệu chỉnh
python -X utf8 dev\eval_doclaynet.py --data D:\PdfSamples --subset tune --gallery 8              # + trang minh họa lỗi nặng
python -X utf8 dev\eval_doclaynet.py --data D:\PdfSamples --subset tune --limit 500 --overlays 20  # mẫu nhỏ + ảnh chồng trang lỗi
python -X utf8 dev\eval_doclaynet.py --data D:\PdfSamples --subset tune --disable-rule _reject_too_small  # đo đóng góp một quy tắc
```

- **Các tập:** `tune` = train trừ hold-out (xem lỗi, chỉnh quy tắc ở đây); `holdout` = ~20% **tài liệu** của train, chọn bằng hash cố định trong script — chỉ để đo, công cụ cấm `--overlays` trên tập này; `val`/`test` = bộ mà bộ phát hiện từng được hiệu chỉnh trước đây (không còn là thước đo khách quan).
- **Tọa độ:** hộp DocLayNet là `[x, y, w, h]` trên ảnh 1025×1025 bị kéo giãn → quy đổi riêng từng trục về kích thước trang thật.
- **Chỉ số chính — mức độ nghiêm trọng với bản dịch** (`severity`, không phụ thuộc cách gộp/tách panel; ảnh được xét đúng như khi xuất, tức đã nới lề 4 pt):
  - *Hình bị cắt thiếu* (`clipped`): chữ thuộc hình (nhãn trục, số chia, chú giải — lấy từ `pdf_cells` của hộp `Picture`) nằm ngoài mọi ảnh đã tách **và có mực thật ở đó** (render kiểm tra, vì `pdf_cells` đôi khi nằm trên chữ ẩn), hoặc > 10% diện tích hình bị cắt. Chia mức: `major` (≥ 3 ô chữ hoặc cắt diện tích) và `minor` (1–2 ô chữ, thường là nhãn panel); `minor` không tính là lỗi nặng. *Bỏ sót* (`missed`): phủ < 50%.
  - *Ảnh lấn chữ* (`intrusion`): ô chữ của nội dung được gán nhãn ngoài hình (Caption, Text, Formula, Table, Page-header…) lọt vào ảnh; *gộp lệch* (`bad_merge`): một ảnh bao nhiều hình **và** lấn chữ. Ảnh bao nhiều hình mà không lấn chữ là `merge_ok` — chấp nhận được.
- **Chỉ số phụ — khớp theo quy ước DocLayNet** (`matching`): khớp một-một; `strict` = IoU ≥ 0,5; `lenient` thêm trường hợp hộp phủ ≥ 90% hộp nhãn và không lớn quá 2 lần. Hộp không khớp được phân loại `missed`/`partial`/`split`/`merged`, `merge`/`fragment`/`fp_<lớp>`/`fp_unlabeled`. DocLayNet vẽ một `Picture` cho mỗi chú thích ở ~99% trường hợp, nên split/merge chủ yếu phản ánh cách gom panel — ít ảnh hưởng tới bản dịch.
- **Nhiễu nhãn:** DocLayNet có trang thiếu hoặc lệch nhãn; xem ảnh minh họa trước khi coi một nhóm lỗi là thật.
- **Đầu ra:** mặc định trong `%TEMP%\luka_doclaynet_eval\` — kết quả bộ phát hiện từng trang lưu đệm theo dấu vân tay mã nguồn (`pages\<fingerprint>.jsonl`, đổi mã là tự chạy lại); nhãn lưu đệm riêng (`ground_truth_v1.jsonl`) và việc chấm điểm luôn tính lại, nên đổi cách chấm không phải chạy lại bộ phát hiện. Mỗi lần chạy có `runs\<tên>\summary.json`, `worst_pages.json`, `overlays\` (`--overlays N`) và `gallery.html` (`--gallery N`: N ví dụ mỗi loại lỗi nặng, ảnh cắt sát vùng hình; chấm cam = chữ lọt vào ảnh, chấm xanh dương = chữ của hình bị cắt; kèm **ảnh xuất ra thực tế** để đối chiếu — ảnh chồng dễ gây hiểu lầm vì chữ bị cắt thường nằm sát ngay ngoài đường viền).
- **Quy trình cải tiến:** chọn một nhóm lỗi nặng trên `tune` → sửa/thêm quy tắc → đo lại `tune` → kiểm tra `holdout` không tụt → chạy test, sinh lại golden nếu kết quả mẫu đổi có chủ đích và xem kỹ diff.

## Quy ước

- **Xuống dòng & mã hóa:** LF và UTF-8 cho mọi tệp văn bản (`.gitattributes`, `.editorconfig`); riêng `.cmd`/`.bat` dùng CRLF. Khi sửa tệp, giữ nguyên kiểu xuống dòng của tệp.
- **Chỉ dẫn cho agent:**
  - `AGENTS.md` và `SKILL.md` viết trung lập theo hành động ("đọc trọn 1 lần", "mở xem song song", "ghi nối dần"), không ghi tên công cụ của một agent cụ thể.
  - Chi tiết riêng của Antigravity chỉ đặt trong `.agents\adapters\antigravity.md`; riêng Claude Code trong `.agents\adapters\claude-code.md`.
  - `.claude\skills\` chỉ là lối vào: phần frontmatter (`name`, `description`) phải giống hệt skill gốc trong `.agents\skills\`.
  - Lệnh mẫu trong tài liệu bắt đầu đúng dạng `powershell.exe -NoProfile -ExecutionPolicy Bypass -File 'tools\<script>.ps1'` để khớp quy tắc cho phép trong `.claude\settings.json`.
  - Sau mọi thay đổi ở các tệp này, chạy `test_skill_contracts.py`: test đối chiếu tham số, giá trị mặc định, dòng stdout, liên kết và kích thước tệp SI với mã thật.
- **Đổi dòng stdout của exe:** nếu `SKILL.md` dựa vào dòng đó, cập nhật `SKILL.md` cùng lúc (test đối chiếu sẽ báo nếu quên).
- **CHANGELOG:** ghi thay đổi vào mục `[Unreleased]`. Khi phát hành, đổi `[Unreleased]` thành số phiên bản, commit, rồi đẩy tag `vX.Y.Z` để CI build và đóng gói.
- **Commit:** tách theo chủ đề, tiêu đề tiếng Anh dạng `fix: …`, `feat: …`, `test: …`, `refactor: …`, `chore: …`, `docs: …`. Không commit `output\`, `work\`, `tools\extract_assets\`.
