# Changelog

Tất cả những thay đổi đáng chú ý của dự án **Luka-Loop** sẽ được ghi lại trong file này.

## [Unreleased]
### Fixed
- **Chữ của cột bên cạnh lẹm vào hình:** quy tắc khe cột (v1.1.26, v1.1.29) tìm khe từ khoảng trống trên cả trang, nên một hình rộng ở chỗ khác trên trang lấp mất khe; bước gắn nhãn theo khối (`_expand_plot_axis_labels`) cũng không kiểm tra khe. Hình ở cột trái khi đó lấy tiêu đề mục ngắn, dấu gạch đầu dòng hay phần đầu đoạn văn của cột phải (sách Surgical Atlas p42, p110). Nay tìm thêm **mép cột dóng hàng** (`_column_edges`): x nơi ít nhất 3 đoạn văn (≥ 12 từ, không chạm khung hình nào) cùng bắt đầu hoặc cùng kết thúc, lệch ≤ 1,5 pt. Cả ba bước gắn nhãn (theo khối, theo dòng, theo nét kẻ) không lấy nhãn vượt qua mép đó khi khung hình nằm hẳn ở phía bên kia và chồng theo chiều dọc với các đoạn văn của cột. Đoạn văn chạm khung hình không được tính, để chữ trong infographic hay thang màu không tạo mép giả.
  - DocLayNet: 6 trang đổi (tune 5, holdout 1), 0 trang kém hơn; ảnh dính chữ 213 → 209, trang lỗi nặng 545 → 541; hình đúng và bỏ sót không đổi. Đã xem ảnh cả 5 trang tune, đều tốt hơn (khung không còn trùm chữ cột bên cạnh). Không chấm mù vì ít trang đổi.
  - 5 cuốn sách tiêu biểu: chỉ Surgical Atlas p42 và p110 đổi, đều tốt hơn.
  - Thêm test `TestColumnEdge`.

## [1.1.31] - 2026-11-25
### Changed
- CI (`ci.yml`) nay cũng chạy khi chỉ đổi `.claude/**`, `CLAUDE.md` hoặc `dev/**` (các tệp mà `test_skill_contracts.py`, `test_eval_doclaynet.py`, `test_ab_judge.py` kiểm tra trực tiếp) và có thêm bước `ruff check tools/src tests` (ghim `ruff==0.15.7`).
- Dọn `dev/`: thêm dòng trống cuối cho 10 tệp theo `.editorconfig`, sửa 22 cảnh báo `ruff` (nhiều câu lệnh một dòng, import, `lambda`, biến mơ hồ); bước ruff của CI nay quét cả `dev`. Bộ sinh `dev/header-pdf` cho ảnh trang giống hệt trước khi dọn.

## [1.1.30] - 2026-11-25
### Fixed
- **Nhãn nối với hình bằng một nét kẻ bị bỏ ra ngoài ảnh:** nhãn trong sách giải phẫu/hướng dẫn thường được nối vào hình bằng đường dẫn nhãn (leader line), và có thể nằm xa hình hơn khoảng cách gắn nhãn thông thường, vắt qua khe cột hoặc nằm ở dải đầu trang; tên trục, số mốc và tên ô của đồ thị cũng hay nằm ở đầu một trục hay đường mốc. Bước mới `_attach_stroke_labels` (sau bước gắn nhãn theo dòng): một nét thẳng mảnh (≤ 1 pt, dài 5 pt đến 40% bề rộng trang) có một đầu nằm trong khung hình và đầu kia chạm (≤ 6 pt) một dòng chữ ngoài khung thì lấy trọn khối chữ của dòng đó (nhãn 2–3 dòng). Điều kiện: khối ≤ 10 từ, không dòng nào > 8 từ, không phải chú thích, tiêu đề mục hay tiêu đề chạy, không nằm trong hình khác; khung nới ra không chạm chú thích, hình khác hay đoạn văn và nới tối đa 100 pt mỗi phía. Gạch phân số của công thức (có chữ ngay trên và ngay dưới phần giữa nét ngang) không được coi là nét nối.
  - DocLayNet: 258 trang đổi (tune 176, holdout 52, val 14, test 16); 41 trang tốt hơn theo điểm, 0 trang kém hơn; hình đúng 4.698 → 4.735, trang lỗi nặng 576 → 545; bỏ sót (89) và ảnh dính chữ (213) không đổi.
  - Chấm mù AB8 (60 hình tune: đủ 27 trang tốt hơn theo điểm và 33 trang cùng điểm chọn ngẫu nhiên): bản mới tốt hơn 31, bản cũ 1 (khung cao thêm ~4 pt sát mép trang), như nhau 27, cả hai tệ 1 (khung ảnh rộng hơn phần nhìn thấy, có từ trước).
  - 4 cuốn sách tiêu biểu: Surgical Atlas 14 trang tốt hơn; Book of Proofs có 5 hình đổi nhỏ (lấy thêm tên trục hoặc số bài), không hình nào hỏng.
  - Thêm test `TestStrokeLabels`.

## [1.1.29] - 2026-11-25
### Fixed
- **Hình nằm ở cột chỉ có hình kéo chữ của cột bên cạnh vào ảnh:** khe giữa hai cột (v1.1.26) trước đây chỉ tìm từ đoạn văn, nên cần đoạn văn ở cả hai bên. Khi một cột chỉ chứa hình và chú thích (sách Surgical Atlas p361), không tìm ra khe và bước gắn nhãn kéo một dòng của cột chữ bên cạnh vào hình. Nay khung hình và chú thích hình/bảng cũng được tính là nội dung cột: mỗi bên khe cần nội dung chiếm ≥ 15% chiều cao trang, và ít nhất một bên có đoạn văn chiếm ≥ 15%.
  - DocLayNet: chỉ 2 trang tune đổi, cả hai tốt hơn (bỏ dính số phương trình và chữ của cột bên cạnh); holdout/val/test không đổi; ảnh dính chữ 215 → 213, trang lỗi nặng 578 → 576 (cả 4 tập); hình đúng, cắt nặng và bỏ sót không đổi. Không chấm mù vì chỉ 2 trang đổi; đã xem ảnh cả 2 trang.
  - 4 cuốn sách tiêu biểu: chỉ Surgical Atlas p361 đổi, tốt hơn.
  - Thêm test `test_gutter_found_beside_a_column_of_figures_only`.

## [1.1.28] - 2026-11-25
### Changed
- Cập nhật bộ chuyển đổi Antigravity (`.agents/adapters/antigravity.md`) và dấu hiệu nhận diện môi trường trong `AGENTS.md` cùng 2 `SKILL.md` cho khớp Antigravity 2.0 thực tế (vẫn tương thích bản cũ):
  - Nhận diện qua `App Data Directory` / `Artifact Directory Path` trong `<user_information>` (giữ `appDataDir` cho bản cũ) và dùng thẳng `<Artifact Directory Path>` cho `-TranscriptPath`;
  - Đặt `read_file` / `write_file` / `edit_file` làm bộ công cụ chính (giữ `view_file` / `write_to_file` / `replace_file_content` cho bản IDE cũ);
  - Ghi rõ bắt buộc đường dẫn tuyệt đối với `read_file`/`write_file`/`edit_file`, bỏ chú thích lỗi thời về lần mở đầu tiên 800 dòng, bổ sung `ByteOffset` và dùng `write_file` với `Append: true` cho thao tác ghi nối dần;
  - Cập nhật kiểm thử hợp đồng trong `tests/test_skill_contracts.py`.

## [1.1.27] - 2026-11-25
### Fixed
- **Biểu đồ đường bị coi là bảng và mất khỏi bản dịch:** bộ đếm đường cong (`_count_non_grid_detail`) chỉ đếm đoạn chéo dài hơn 2 pt theo cả hai chiều, trong khi phần mềm vẽ đồ thị thường vẽ một đường cong mượt bằng hàng trăm đoạn li ti ngắn hơn thế. Biểu đồ khi đó chỉ còn khung, đường lưới và số chia, nên luật nhận bảng (PyMuPDF `find_tables`) loại cả hình nếu chú thích "FIG." không nối được. Nay một nét vẽ có từ 6 đoạn chéo li ti trở lên (> 0,25 pt mỗi chiều) được tính là đường dữ liệu.
  - DocLayNet: tune 20 trang đổi, holdout 1, val/test không đổi; hình đúng tune 3.183 → 3.199; bỏ sót tune 78 → 67, holdout 20 → 19; trang lỗi nặng tune 423 → 408 (cả 4 tập 593 → 578). Holdout có 1 trang vừa bớt bỏ sót vừa thêm 1 hình cắt nặng và 1 ảnh dính chữ. 11/12 biểu đồ bị luật bảng loại nhầm trên tune được tách lại; còn lại là biểu đồ cột (không có đường chéo).
  - Chấm mù AB7 (14 hình tune, mỗi tài liệu một hình): bản mới tốt hơn 14, bản cũ 0, như nhau 0.
  - Thêm test `TestFinePolylinePlot`.

## [1.1.26] - 2026-11-24
### Fixed
- **Hình ở một cột kéo chữ của cột bên cạnh vào ảnh** (dòng phương trình, đoạn văn ngắn của cột kia): bước gắn nhãn theo dòng (`_attach_adjacent_label_lines`) nay biết khe giữa hai cột chữ. Khe được tìm từ vị trí các đoạn văn (khối chữ ≥ 12 từ) chiếu xuống trục ngang: khoảng trống ≥ 6 pt nằm ở phần giữa trang (15–85% bề rộng), mỗi bên có đoạn văn chiếm ≥ 15% chiều cao trang. Hình không vượt qua đường giữa khe thì không nhận dòng chữ có tâm ở bên kia khe; hình rộng vắt qua đường giữa và trang không có khe (một cột, hoặc có đoạn văn chạy ngang cả trang) giữ cách cũ.
  - DocLayNet: tune 6 trang đổi, holdout 3 trang đổi, val/test không đổi; ảnh dính chữ tune 163 → 159, holdout 20 → 18; trang lỗi nặng tune 426 → 423, holdout 114 → 112; số hình đúng và bỏ sót không đổi. Xem ảnh cả 6 trang tune: đều tốt hơn, trong đó có `1001.1552.pdf` p11, ca duy nhất bản cũ thắng khi chấm mù luật cứu mảnh nhỏ (v1.1.24).
  - 32 bài báo đầy đủ (có nhận diện tiêu đề chạy): 4 trang đổi, đều tốt hơn; 6 cuốn sách tiêu biểu và `dev/header-pdf`: không đổi.

### Added
- `dev/quality_history.md`: lịch sử chất lượng tách hình theo từng bản phát hành (v1.1.13 → v1.1.25), chấm lại bằng cùng một bộ chấm trên 14.117 trang DocLayNet, kèm F1 theo quy ước DocLayNet (IoU ≥ 0,5) để tham khảo.

## [1.1.25] - 2026-11-24
### Added
- Thực thi giới hạn thời gian **30 giây/trang** cho bộ tách hình (`DetectorConfig.max_page_seconds = 30.0`, `PageContext.budget_exceeded()`): chốt kiểm tra hợp tác bằng đồng hồ thực đặt tại các bước phân tích nặng từ Pha 1 đến Pha 6 (cắt viền trắng ảnh raster, lọc/gom cụm/đánh giá vector, `find_tables`, cứu chú thích mồ côi, Pha 3b cứu mảnh vector nhỏ, nới nhãn trục và tra bảng metadata). Khi vượt 30 s, công cụ bỏ các bước nặng còn lại (cắt viền trắng, gom cụm nếu chưa gom, `find_tables`, cứu chú thích mồ côi, Pha 3b) nhưng vẫn chấm các cụm vector đã gom (tối đa 40 cụm lớn nhất, `DetectorConfig.budget_late_clusters`), vẫn chạy các bước rẻ (nới nhãn trục, gộp lần hai, gắn nhãn theo dòng, khử tiêu đề chạy) và in cảnh báo ra `stderr`; các trang chạy dưới ngưỡng 30 s giữ nguyên 100% luồng xử lý và kết quả. Giới hạn là "mềm": chỉ kiểm tra giữa các bước, nên một lệnh PyMuPDF lớn đang chạy (đọc nét vẽ, gom cụm) có thể kéo trang quá 30 s vài giây. Bổ sung các ca kiểm thử dùng đồng hồ giả trong `tests/test_detector_fixes.py`.

### Fixed
- Khi hết giờ ngay sau bước gom cụm nét vẽ (bước tốn thời gian nhất trên trang dày nét vẽ), bản đầu của giới hạn 30 s bỏ luôn mọi cụm đã gom mà chưa chấm, làm mất hình: `1002.2972.pdf` p9 mất hình duy nhất, `1001.1463.pdf` p13 còn một mảnh nhỏ thay vì 2 hình. Nay các cụm này vẫn được chấm, và mô phỏng hết giờ cho kết quả trùng với lần chạy không giới hạn.
- `dev/eval_doclaynet.py` chạy bộ tách hình **không** giới hạn thời gian: khi nhiều worker chạy song song, cả thời gian thực lẫn thời gian CPU đều phình ra, nên giới hạn cắt nhầm những trang chạy riêng chỉ mất 11–23 s và trộn tải máy vào số đo chất lượng. Báo cáo thay `pages_timed_out` bằng `pages_over_budget` (số trang có thời gian thực vượt 30 s trong lần đo; cần đo lại đơn luồng trước khi kết luận).
- `find_tables()` nhận bản sao cả `items` (không chỉ `rect`) của nét vẽ: PyMuPDF chèn thêm đoạn khép kín vào `items` của đường gấp khúc có `closePath`, mỗi lần tìm bảng lại chèn thêm, trong khi nhiều luật đếm số `items`. Với PyMuPDF 1.28.2 chưa gặp trường hợp này trên DocLayNet, nên đây là sửa phòng ngừa.

### Changed
- Tối ưu các điểm nghẽn lớn nhất của bộ tách hình mà không đánh đổi độ chính xác trên trang thường:
  - Bỏ cờ `TEXT_PRESERVE_IMAGES` khi đọc `page.get_text("dict")` trong `analyze_page` (tránh giải mã hàng nghìn ảnh nhúng rồi bỏ đi — trang chậm nhất `1001.2338.pdf` p20 giảm từ 49 s xuống 0,12 s ở Pha 1);
  - Chỉ yêu cầu `xrefs=True` trong `get_image_info` khi trang thực sự có ảnh XObject (`page.get_images(full=False)` khác rỗng);
  - Đánh chỉ mục `word_rects` theo dải tọa độ `y` 16 pt trong `_filter_drawings` thay cho quét $O(\text{drawings} \times \text{words})$;
  - Tái sử dụng `ctx.drawings` (nhân bản `rect` an toàn) khi gọi `find_tables()` để không trích lại nét vẽ lần 2.
  - Kết quả trên toàn bộ 14.117 trang DocLayNet (so với v1.1.24): thời gian trung bình giảm `0,514 s → 0,422 s/trang`, `p99` giảm `6,46 s → 5,25 s`, trang chậm nhất đo đơn luồng giảm xuống `26,15 s` (`0` trang vượt 30 s); 14.110/14.117 trang trùng khớp tuyệt đối từng hộp, 7 trang thay đổi do bỏ `TEXT_PRESERVE_IMAGES` đều cải thiện (`pages_with_severe_error: 601 → 598`, `figures_ok: 4.679 → 4.682`, `0` tụt chất lượng); `dev/header-pdf` (50 trang), 32 bài báo `dev/arxiv-b1` (461 trang) và 6/6 golden snapshot giữ nguyên 100%.

## [1.1.24] - 2026-11-24
### Fixed
- Hình không còn bị cắt mất phần hay bỏ sót khi được vẽ bằng nhiều mảnh nhỏ rời nhau (lưới ô vuông, sơ đồ chấm, ký hiệu chú giải, nhãn trục vẽ bằng nét). Bộ dò chỉ gom các nét cách nhau tối đa 5 pt, nên những hình như vậy vỡ thành nhiều cụm, mỗi cụm nhỏ hơn 42 pt và bị loại vì "quá nhỏ". Nay, sau các bước dò hình sẵn có, những mảnh bị loại mà chưa nằm trong hình nào được gom lại với nhau và với các hình đã tìm thấy khi cách nhau tối đa 20 pt. Mỗi khối gom được phải qua lại toàn bộ luật lọc như một cụm bình thường. Ba chốt chặn đi kèm:
  - mảnh nằm đè lên câu văn hay chú thích (gạch phân số, dấu căn trong công thức) không được gom;
  - nhóm mảnh nối liền hai hình có sẵn thì bỏ qua, để các bước gộp sẵn có quyết định;
  - khối chỉ gồm mảnh vụn phải có chú thích "Figure" riêng, và không khối nào được nuốt chú thích nằm giữa hai hình. Chốt này thêm vào sau khi thấy catalog kỹ thuật vẽ tiêu đề, mục bằng nét bị gom cả trang thành một hình.

  Kết quả:
  - DocLayNet tune: 96 hình cắt hụt hoặc bỏ sót nay lấy đủ (cắt hụt 444 → 354, bỏ sót 84 → 78).
  - DocLayNet holdout cũng tốt lên: cắt hụt 148 → 115, bỏ sót 26 → 21.
  - Không có hình giả mới, tốc độ không đổi.
  - Chấm mù 50 trang (bản chưa có hai chốt sau): code mới tốt hơn 36, ngang 13, code cũ tốt hơn 1.
  - Kiểm tra trên 6 cuốn sách thật (280 trang): 3 trang đổi, 1 tốt hơn, 1 ngang, 1 xấu hơn nhẹ (hình kéo theo một dòng tiêu đề phụ vẽ bằng nét).
  - Còn vài trang hình kéo theo số trang ở đầu trang. Trên tài liệu nhiều trang, bộ lọc tiêu đề chạy (bản 1.1.23) gỡ được số trang này; đã kiểm trên bài gốc từ arXiv.
  - Bộ đề `dev/header-pdf`: vẫn 0 ảnh dính tiêu đề/số trang, hình cắt hụt giảm từ 7 xuống 4.

### Added
- Đưa bộ đề tự sinh `dev/header-pdf` (10 PDF × 5 trang, đáp án, bộ sinh và công cụ chấm) vào repo làm tài liệu tham khảo cho dev, kèm README.

## [1.1.23] - 2026-11-23
### Fixed
- Ảnh tách ra không còn dính tiêu đề chạy (tên tạp chí, tên chương) và số trang in sát phía trên hình. Trước khi dò hình, công cụ quét cả tài liệu, tìm dòng trên cùng/dưới cùng lặp lại ở cùng độ cao trên ít nhất 2 trang khác gần đó (số trang phải thay đổi như bộ đếm, nên số trên trục biểu đồ không bị nhầm). Các dòng này không bao giờ được gom vào hình, và mép hình chạm vào chúng được kéo lùi lại. Trên bộ đề 10 tệp × 5 trang (`dev/header-pdf`), số ảnh dính tiêu đề/số trang giảm từ 18/42 xuống 0, không thêm hình cắt hụt hay bỏ sót. Trên tài liệu thật: 56 trang lỗi dính tiêu đề của DocLayNet, chạy lại trong bản đầy đủ của 30 bài báo arXiv, code cũ dính cả 56, code mới sạch cả 56 mà không mất phần nào của hình (kiểm bằng máy, chấm mù và xem tận mắt 93 ảnh); 1.007 trang sách thật không đổi khung nào, tốc độ như cũ. Tài liệu một trang giữ nguyên kết quả (DocLayNet: cả 14.117 trang cho khung hình y hệt).

## [1.1.22] - 2026-11-22
### Fixed
- Tách hình trên trang PDF bị xoay (`/Rotate` 90/180/270): trước đây công cụ dò hình theo tọa độ trang chưa xoay nhưng lại cắt ảnh theo trang đã xoay, nên ảnh cắt lệch sang vùng khác của trang (trên DocLayNet, cả 10/10 hình ở 27 trang xoay đều hỏng). Nay bộ dò chạy trên trang tạm bỏ xoay, rồi chuyển hộp sang trang hiển thị: ảnh cắt đúng hình, đứng thẳng như khi xem, `box` trong `manifest.json` tính theo trang hiển thị và hình được đánh số theo thứ tự đọc trên trang hiển thị. Trang không xoay giữ nguyên kết quả.

### Changed
- Auto-QA (`html_qa.py`): tách hàm kiểm tra thẻ mở `_process_start_tag` (212 dòng, 108 nhánh) thành các hàm nhỏ theo việc: cấu trúc, `<script>`, `<img>`, `<table>`, thuộc tính, và từng nhóm đường dẫn (`<a>`, `<link>`, `<img>`, `<script>`, còn lại). Không đổi quy tắc nào: bản cũ và bản mới cho kết quả giống hệt nhau trên toàn bộ HTML trong repo và 30.000 tài liệu sinh ngẫu nhiên.

## [1.1.21] - 2026-11-22
### Fixed
- Chọn chế độ giữ thiết kế: `AGENTS.md` và hai `SKILL.md` nhận diện theo quy tắc ("giữ/giữ nguyên/bảo toàn" + "định dạng/format/bố cục/layout/thiết kế/trình bày") kèm ví dụ, thay cho danh sách 5 cụm từ cố định. Trước đây câu "Giữ định dạng" bị chuyển sang skill mặc định (bản một cột). Thêm ví dụ các yêu cầu về nội dung ("dịch sát nghĩa", "giữ hình ảnh/bảng biểu") không được nhầm thành chế độ giữ thiết kế.

## [1.1.20] - 2026-11-22
### Fixed
- Skill bảo toàn thiết kế (`pdf-to-html-vi-layout`): agent không còn xếp hình theo số trong tên tệp `fig_pX_Y`. Số `Y` đánh từ trên xuống trên cả trang, không theo cột, nên trên trang 2 cột thường xen kẽ giữa hai cột và có thể nhảy số; xếp theo tên tệp từng khiến hình đặt sai chỗ hoặc đảo thứ tự bước. `si_translation.md` nay giải thích cách đặt tên và yêu cầu xác định vị trí bằng `page`/`box` trong `manifest.json`, đối chiếu nhãn in trên hình và quan sát bản gốc; `si_layout.md` yêu cầu giữ đúng thứ tự trên–dưới trong từng cột và thêm mục này vào danh sách tự kiểm tra.

## [1.1.19] - 2026-11-22
### Fixed
- Bộ chuyển đổi Claude Code: PDF tới 10 trang phải đọc bằng một lệnh `Read` chỉ có `file_path`, không kèm tham số `pages` (kể cả `pages: "1-5"`). Đọc cả tệp, Claude nhận cả lớp chữ lẫn hình từng trang nên chữ, số liệu và ký hiệu chính xác hơn, và không cần `pdftoppm`; chính tham số `pages` mới đòi `pdftoppm` và gây lỗi `pdftoppm is not installed` trên Windows.

## [1.1.18] - 2026-11-22
### Fixed
- Cập nhật cho Claude adapter dùng luôn Render Pages để đọc file PDF dài;
- Chỉnh sửa README, phân biệt 2 dòng sản phẩm;

## [1.1.17] - 2026-11-22
### Security
- Auto-QA nay từ chối comment HTML dị dạng `<!-->`, `<!--->` và dấu đóng `--!>`. Trình duyệt kết thúc comment ngay tại các dạng này, còn bộ quét đọc tiếp tới `-->` kế tiếp, nên thẻ đặt phía sau (vd `<meta http-equiv="refresh">` chuyển hướng sang trang khác, điều CSP không chặn được) từng lọt qua QA mà vẫn chạy trong trình duyệt. Bước 3 của cả hai `SKILL.md` dặn agent chỉ viết comment dạng chuẩn `<!-- nội dung -->`.

## [1.1.16] - 2026-11-21
### Fixed
- Dòng `WARNING: Microsoft Edge/Chrome not found; skipped automatic PDF export …` nay in qua stdout (trước là stderr), nên hiện đúng vị trí sau `Embedded images into HTML` thay vì nhảy lên đầu kết quả.

### Changed
- Hướng dẫn cho agent (`SKILL.md`, bộ chuyển đổi Claude Code/Antigravity) dễ làm đúng hơn:
  - Agent không đọc được PDF (vd Codex) render từng cụm trang bằng `RenderPages` rồi xem ảnh; cụm cuối không vượt `total_pages`.
  - Bước 4 ghi đúng các dòng đầu ra theo thứ tự công cụ in, kể cả dòng báo máy không có Edge/Chrome.
  - Mô tả skill `pdf-to-html-vi` nói rõ khi nào dùng và khi nào chuyển sang `pdf-to-html-vi-layout`.
  - Mọi ví dụ tham số dùng nháy đơn.
  - Claude Code: ưu tiên công cụ PowerShell, Bash chỉ là đường lui; mô tả hai cách đưa tệp vào (tải lên tệp, nêu đường dẫn).
  - Antigravity: tên công cụ hiện tại `view_file`…; tệp tải lên được lưu ở `.user_uploaded\media_<id>.pdf`.

## [1.1.15] - 2026-11-21
### Security
- Auto-QA nay từ chối `<style>`, `<script>`, `<textarea>`, `<title>`… nằm trong `<svg>`/`<math>`: trình duyệt đọc nội dung các thẻ này như HTML thật, nên trước đây thẻ độc hại giấu bên trong (vd `<img onerror>`, `<script href>`) lọt qua QA.
- CSP chỉ cho phép đúng thư mục MathJax (vd `https://cdn.jsdelivr.net/npm/mathjax@3/es5/`) thay vì cả tên miền `cdn.jsdelivr.net`/`cdnjs.cloudflare.com`.

### Added
- `dev/ab_judge.py`: công cụ chấm mù trái/phải hai bản bộ tách hình trên DocLayNet (`build` tạo trang HTML, `score` tính sign test, lưu đợt chấm vào `dev/ab_history/`); kèm `dev/experiments/` và `tests/test_ab_judge.py`.

## [1.1.14] - 2026-11-21
### Added
- `dev/eval_doclaynet.py`: công cụ phát triển đánh giá bộ tách hình trên DocLayNet v1.2 (phần `scientific_articles`, dùng PDF gốc nhúng trong parquet). Chia train thành `tune` và `holdout` (~20% tài liệu, hash cố định, cấm xem ảnh chồng), chạy song song, lưu đệm kết quả theo dấu vân tay mã bộ phát hiện, báo precision/recall/F1 (IoU ≥ 0,5 và tiêu chí nới), IoU trung bình, phân loại từng lỗi (`missed`/`split`/`merged`/`fragment`/`fp_<lớp>`…), độ chính xác theo nguồn hình, hỗ trợ tắt từng quy tắc để đo đóng góp và xuất ảnh chồng các trang tệ nhất. Thêm `tests/test_eval_doclaynet.py` (logic chấm điểm, chỉ dùng thư viện chuẩn) và hướng dẫn trong `dev/DEVELOPMENT.md`.
- `dev/eval_doclaynet.py`: chỉ số theo **mức độ nghiêm trọng với bản dịch**, không phụ thuộc cách gộp/tách panel — hình bị cắt thiếu (chữ thuộc hình như nhãn trục/chú giải nằm ngoài mọi ảnh, dựa trên `pdf_cells`), bỏ sót, ảnh lấn chữ (chú thích/văn bản/công thức/bảng/số trang lọt vào ảnh, xét cả lề 4 pt khi xuất) và gộp lệch; chỉ số khớp theo quy ước DocLayNet giữ làm tham khảo. Nhãn được lưu đệm riêng và việc chấm điểm luôn tính lại, nên đổi cách chấm không phải chạy lại bộ phát hiện. Thêm `--gallery N` xuất trang HTML cục bộ với ví dụ cho từng loại lỗi nặng, kèm ảnh xuất ra thực tế. Chữ bị cắt chỉ được tính khi render thấy mực thật nằm ngoài ảnh (loại báo động giả từ `pdf_cells` nằm trên chữ ẩn); hình cắt thiếu chia mức `major` (≥ 3 ô chữ hoặc cắt diện tích) và `minor` (1–2 ô chữ, không tính là lỗi nặng).
- `tests/test_detector_fixes.py`: test hồi quy (PDF tổng hợp) cho hai bản sửa bên dưới, kể cả trường hợp giải mã ảnh nhúng lỗi (mặt nạ khác kích thước, ảnh đã có kênh alpha) phải lặng lẽ giữ khung gốc thay vì làm hỏng cả lần tách hình.

### Fixed
- **Ảnh tách ra lấy cả viền trắng của ảnh nhúng** (đè lên số trang, đoạn văn, chú thích bên cạnh): Pha 2 nay cắt ảnh raster theo vùng mực thật — phân tích điểm ảnh của chính ảnh nhúng (kèm mặt nạ trong suốt) rồi quy đổi qua ma trận đặt ảnh, nên đúng cả với ảnh xoay/lật. Chạy sau các kiểm tra "ảnh nền cả trang" (trang quét có lề trắng vẫn được nhận là nền) và gom lại nhãn ngắn in đè trên phần viền vừa cắt (nhãn trục, chữ panel).
- **Cắt mất nhãn trục / tiêu đề trục / chú giải**: thêm bước gom nhãn theo **dòng chữ** sau bước gom theo khối hiện có — nhận dòng nằm sát trái (≤ 28 pt), phải (≤ 20), trên (≤ 18), dưới (≤ 26) hoặc chồng lên mép hình; không bao giờ gom chú thích, dòng của đoạn văn/công thức/bảng (cả khối chữ phải "giống nhãn"), tiêu đề mục, dòng chữ lớn phía trên hình, lề trên/dưới trang, hay thứ làm ảnh chạm sang hình khác. Các ngưỡng nằm trong `DetectorConfig` (`label_gap_*`, `label_max_growth`, `raster_trim_*`).
- Đo trên DocLayNet (bài báo khoa học, chỉ số mức độ nghiêm trọng): tỉ lệ hình tách gọn tune 78,8% → 86,7%, holdout 77,9% → 83,1%, val 80,2% → 88,1%, test 80,5% → 86,9%; hình bị cắt thiếu nhiều giảm 25–54%; trang có lỗi nặng tune 664 → 505, holdout 181 → 138. Ảnh lấn chữ còn tăng nhẹ trên tune (156 → 168, chủ yếu `Page-header`) và test (19 → 24, chủ yếu `Formula`) — cần xử lý tiếp. Tốc độ tách hình chậm hơn khoảng 35% do tìm bảng khi gom nhãn. Golden của `journal_2col_academic` (ảnh gọn hơn) và `synthetic_urban_benchmark` (có thêm tiêu đề trục Y) được sinh lại sau khi đối chiếu bằng mắt.
- Kiểm chứng bằng mắt người qua **chấm mù trái/phải** (đúng ảnh exe xuất ra, bản cũ/mới xáo ngẫu nhiên, 150 hình từ 150 tài liệu DocLayNet khác nhau): bản mới tốt hơn 51 hình, bản cũ tốt hơn 4, như nhau 83, cả hai đều chưa tốt 12 — bản mới thắng 93% số cặp phân định được (khoảng tin cậy 95%: 83–97%). Các lỗi còn lại đã ghi nhận: nhãn nằm giữa hai hình đôi khi bị gán cho hình xa hơn, tiêu đề chạy đôi khi lọt vào ảnh, mép ảnh cắt ngang dòng tiêu đề trục, ảnh lan sang cột văn bản bên cạnh, mất một phần hình.

## [1.1.13] - 2026-11-21
### Fixed
- Windows PowerShell 5.1 (và PowerShell 7.0–7.2) làm hỏng tham số đường dẫn có khoảng trắng và kết thúc bằng `\` (vd `-OutDir 'C:\my dir\'`): dấu `\` cuối bị hiểu là escape cho dấu `"` đóng, nuốt mọi tham số phía sau. `Invoke-ExtractAssetsExe` nay nhân đôi các `\` cuối trước khi gọi `extract_assets.exe` khi host dùng kiểu truyền tham số cũ;
- `-CleanDir` không hợp lệ (ngoài `work\`, hoặc chứa tệp đầu ra) trước đây chỉ bị phát hiện **sau khi** HTML/PDF đã ghi ra `output\`, khiến lệnh báo thất bại và Agent chạy lại tạo bản trùng `_2`. Nay `EmbedImages` và `HtmlToPdf` kiểm tra `-CleanDir` trước khi ghi tệp hoặc mở trình duyệt; lỗi dọn dẹp phát sinh sau khi đầu ra đã hoàn tất chỉ in `WARNING: Skipped cleaning temp directory; outputs are complete` (stderr) thay vì làm hỏng cả lệnh;
- Bỏ import thừa `get_repo_root` trong `html_packager_core.py`.

### Added
- `path_guards.validate_clean_dir()`: chạy đủ các kiểm tra an toàn của `safe_clean_dir` mà không xóa gì;
- Test: `-CleanDir` sai không tạo tệp nào trong `output\` và không khởi động trình duyệt, lỗi dọn dẹp sau khi ghi chỉ cảnh báo, `RenderPages` với `-OutDir` có khoảng trắng + `\` cuối;
- `tests/test_golden_extraction.py` + `tests/golden/`: chụp kết quả tách hình (manifest, manifest rút gọn trên stdout, SHA-256 từng PNG) của 6 PDF mẫu làm chuẩn so sánh cho các bước tái cấu trúc.

### Changed
- Chuyển các hàm in manifest (`emit_compacted_manifest_stdout`, `limit_manifest_words`, `_sanitize_manifest_text`) từ `html_packager_core.py` sang module mới `tools/src/manifest.py` (chỉ dùng thư viện chuẩn): bộ tách hình không còn phải import bộ đóng gói. Chỉ di chuyển mã, không đổi hành vi.
- Tách `html_packager_core.py` (~1.300 dòng) thành 6 module phẳng theo trách nhiệm, không có vòng phụ thuộc: `packager.py` (nhúng ảnh, điều phối Bước 4), `reader_shell.py` (vỏ đọc + CSP), `html_qa.py` (Auto-QA), `pdf_export.py` (Edge/Chrome headless), `output_paths.py` (đặt tên/đánh số đầu ra, dọn `work\` sau khi ghi) và `transcript.py` (tìm PDF trong transcript). Mã được chuyển nguyên văn; 5 hàm nội bộ dùng chéo giữa các module bỏ tiền tố `_`. README và `THIRD_PARTY_LICENSES.md` liệt kê đúng danh sách tệp nguồn (kể cả `manifest.py`).
- Tách `figure_detector.py` (~2.200 dòng) thành package `tools/src/figure_detector/` gồm 10 module phân tầng theo pha (`model`, `geometry`, `text`, `caption_match`, `raster`, `vector`, `captions`, `merge`, `pipeline`, `extract`), không có vòng phụ thuộc; các hàm khớp chú thích mà Pha 2–3 dùng tới được tách thành tầng `caption_match` riêng. 82 định nghĩa được chuyển nguyên văn; chỉ biến toàn cục `pymupdf` nạp trễ được thay bằng một proxy dùng chung (vẫn không nạp PyMuPDF khi import, tốc độ tách hình không đổi). `__init__.py` giữ nguyên các tên công khai cũ. Kết quả tách hình của 6 PDF mẫu trùng khớp tuyệt đối với golden.
- Viết lại `_evaluate_vector_cluster` (Pha 3, ~170 dòng `if` lồng nhau) thành danh sách quy tắc: đặc trưng của cụm gom vào `_ClusterFeatures` (tính lười, mỗi đặc trưng tối đa một lần), mỗi lý do loại bỏ là một hàm `_reject_*` nhỏ có docstring, thứ tự áp dụng nằm trong `_VECTOR_CLUSTER_RULES`. Ba lần quét đường cong (`_has_non_grid_detail` ngưỡng 12/2/1) gộp thành một lần (`_count_non_grid_detail`). Kết quả không đổi: so song song bản cũ/mới không lệch quyết định nào trên toàn bộ bộ test và ~70.000 cụm sinh ngẫu nhiên phủ cả 16 quy tắc; golden trùng khớp. Thêm `tests/test_vector_rules.py` (13 test: thứ tự quy tắc, quy tắc đầu tiên thắng, tính lười, và từng quy tắc kèm điều kiện chặn).
- Dọn `extract_assets.py` (CLI): 6 hàm kiểm tra giá trị gần như giống nhau gộp thành một hàm tạo validator theo khoảng (`_number_in_range`); chuỗi `if/elif` theo `--mode` thay bằng bảng `_MODES` (mỗi mode: mô tả, hàm khai báo tham số, hàm chạy); bỏ việc xuất lại các hàm private (`_optimize_image_bytes`, `_split_dict_block`…) chỉ để test dùng — test nay import thẳng từ module gốc. Tham số, giá trị mặc định, thông báo lỗi khoảng giá trị và nội dung `--help` của mọi mode giữ nguyên; riêng lỗi giá trị không phải số nay ghi `invalid int value: 'abc'` thay vì `invalid _validate_dpi value: 'abc'`. Thêm `tests/test_cli.py` (11 test chốt cách mỗi mode phân tích tham số và gọi hàm xử lý).
- `test_skill_contracts.py` quét mã nguồn `tools/src/` đệ quy và khóa cache exe trong CI dùng `tools/src/**/*.py`, để mã trong package vẫn được đối chiếu và vẫn kích hoạt build lại exe.

## [1.1.12] - 2026-11-20
### Fixed
- Xuất PDF lỗi (Edge/Chrome quá thời gian hoặc tạo PDF rỗng) không còn làm cả lệnh `-Action EmbedImages` báo thất bại: HTML đã đạt QA vẫn được giữ, `work\` vẫn được dọn, tệp PDF dở dang tự xóa và stdout in `WARNING: PDF export failed; HTML output is complete -> ...` — tránh việc Agent chạy lại Bước 4 tạo bản trùng `_2`, `_3`;
- Tăng `--virtual-time-budget` của trình duyệt headless từ `4000` lên `7000` ms để MathJax kịp dàn công thức trước khi in PDF;
- Cập nhật 2 `SKILL.md` và `AGENTS.md` với mẫu phản hồi khi chỉ riêng PDF lỗi; thêm `tests/test_pdf_export_resilience.py` (trình duyệt giả, không cần Edge/PyMuPDF).
- Thu hẹp phạm vi `-CleanDir`: ngoài `work\` của workspace, chỉ cho dọn `<thư mục hiện hành>\work` khi thư mục hiện hành nằm trong thư mục tạm của hệ thống (dành cho test), tránh xóa nhầm một thư mục `work` không liên quan; thêm `tests/test_clean_dir_scope.py`.
- Sửa lỗi gõ `ingput/` → `input/` trong README.

### Added
- Hỗ trợ **Claude Code**: `CLAUDE.md` nạp `AGENTS.md` và bộ chuyển đổi `.agents/adapters/claude-code.md` (chạy lệnh nguyên văn, lấy PDF theo đường dẫn, đọc PDF dài theo cụm trang và tự chuyển sang `RenderPages` khi máy thiếu `pdftoppm`, ánh xạ sang `Read`/`Write`/`Edit`); `.claude/skills/` chứa 2 skill trỏ đường tới skill gốc; `.claude/settings.json` cho phép sẵn đúng 3 lệnh `tools\*.ps1` (PowerShell tool và Bash); gói phát hành kèm `CLAUDE.md` và `.claude/` (không kèm `settings.local.json`); README thêm mục "Dùng với Claude Code";
- `tests/test_skill_contracts.py`: kiểm tra skill trỏ đường khớp tên/mô tả với skill gốc, `CLAUDE.md` nhập đúng `AGENTS.md` và bộ chuyển đổi, quy tắc cấp quyền chỉ cho phép 3 script công cụ và khớp với mọi lệnh mẫu trong tài liệu;
- `tests/test_skill_contracts.py`: tự động đối chiếu `AGENTS.md` + các `SKILL.md` với mã thật — lệnh mẫu gọi đúng script/tham số/`-Action`, giá trị mặc định khớp `param()`, các dòng stdout được nhắc tới thực sự được in ra, liên kết và đường dẫn `tools\` tồn tại, file SI đọc 1 lần nằm trong giới hạn `read_file` và khớp kích thước ghi trong SKILL;
- CI chạy cả khi `.agents/**` hoặc `AGENTS.md` thay đổi;
- Thêm `.editorconfig` (UTF-8, LF) để trình soạn thảo tạo tệp mới đúng chuẩn.

### Changed
- Tách chỉ dẫn riêng của Antigravity ra `.agents/adapters/antigravity.md` (đường dẫn transcript nội bộ, khối `<user_information>`, tệp tạm `media_<id>.pdf`, giới hạn và tên công cụ `read_file`/`edit_file`); `AGENTS.md` và 2 `SKILL.md` chuyển sang cách viết trung lập theo hành động ("đọc trọn 1 lần", "mở xem song song", "ghi nối dần") và chỉ trỏ tới bộ chuyển đổi khi phát hiện môi trường Antigravity. Agent khác không lấy được PDF đính kèm sẽ đề nghị người dùng đặt tệp vào `input\`;
- Rút gọn `AGENTS.md` về vai trò điều phối (chọn skill, môi trường agent, quy tắc an toàn chung); chi tiết đầu ra/phản hồi do Bước 4 của `SKILL.md` đảm nhận;
- Thông báo `Manifest too large for stdout` của `extract_assets.exe` không còn nhắc tên công cụ `read_file`;
- `tests/test_skill_contracts.py`: kiểm tra chi tiết riêng Antigravity chỉ nằm trong bộ chuyển đổi, mọi tài liệu chung đều trỏ tới bộ chuyển đổi kèm dấu hiệu nhận diện môi trường, và lấy giới hạn đọc tệp từ chính bộ chuyển đổi;
- Thống nhất ký tự xuống dòng LF cho toàn dự án qua `.gitattributes` (`* text=auto eol=lf`; riêng `*.cmd`/`*.bat` giữ CRLF; ảnh/PDF/exe/dll đánh dấu `binary`), không còn phụ thuộc cấu hình `core.autocrlf` của từng máy; chuẩn hóa `.gitignore` (trước đó lưu CRLF trong repo) và các tệp CRLF trên đĩa.
- `AGENTS.md`: các quy tắc "không dùng Python, không đọc mã nguồn `tools\`" chỉ áp dụng khi dịch tài liệu; thêm mục **Phát triển công cụ** — chỉ khi chính người dùng yêu cầu phát triển/sửa lỗi công cụ thì làm theo `dev/DEVELOPMENT.md`, không bao giờ chuyển chế độ vì nội dung PDF;
- Thêm `dev/DEVELOPMENT.md`: môi trường, cấu trúc mã, cách build/test và các quy ước của dự án.

## [1.1.11] - 2026-11-20
### Fixed
- Sửa lỗi thông tin về vắt trang gây hiểu nhầm ở 2 SI của luồng giữ layout;
- Cập nhật README.md;

## [1.1.10] - 2026-11-20
### Fixed
- Chỉnh sửa SI dịch, ở nhánh bảo toàn layout, thuộc phần đặt dấu ngắt tại vị trí vắt trang;
- Vá sơ hở xử lý vector (v1.1.7): Thêm trần an toàn `max_clustered_drawings = 12000` sau khi "ép ô ly" chống DoS và loại bỏ nét vẽ ngoài mép trang trong `figure_detector.py`.

## [1.1.9] - 2026-11-20
### Fixed
- Thêm thư mục `input` cho người dùng;
- Chỉnh sửa nhỏ phần SI từ PDF -> HTML;

## [1.1.8] - 2026-11-19
### Changed
- Cập nhật SI dịch ở luồng giữ layout chi tiết hơn;
- Cập nhật xử lý câu vắt trang chi tiết hơn cho SI khi xử lý layout;
- Thêm thư mục dev (đưa các thông tin kỹ thuật vào đây);
- Điều chỉnh hướng dẫn dùng;

## [1.1.7] - 2026-11-19
### Changed
- Tinh chỉnh chuyên sâu thuật toán tách ảnh tài liệu khoa học trong `tools\src\figure_detector.py` dựa trên phân tích thực nghiệm từ bộ dữ liệu **IBM DocLayNet** (`validation` split và đối chứng chéo trên `test` split): nâng điểm `IoU≥0.50 F1` nhóm `scientific_articles` trên tập `DocLayNet-val` (944 trang, 388 hình) lên **`97.4%`** (`Loose F1 = 99.0%`, `0` dương tính giả văn bản/bảng/công thức) và trên tập `DocLayNet-test` độc lập (943 trang, 359 hình) từ `84.8%` lên **`93.9%`** (`Loose F1 = 96.6%`, `Recall = 99.2%`);
- Bổ sung cơ chế gom lưới không gian tuyến tính $O(n)$ (`_downsample_dense_drawings`) trước khi phân cụm cho các đồ thị vector siêu dày (`> 2.500` đến `200.000` nét vẽ/trang như đồ thị quỹ đạo hỗn loạn 3D), nhận diện lưới giản đồ Feynman/sơ đồ vật lý nhiều thành phần nhỏ (`24–41 pt`) trong vùng trống phía trên chú thích (`_is_in_caption_above_zone`), và giữ nguyên từng đồ thị độc lập đối với ma trận nhiều hàng × 2 cột đồ thị lớn không đánh nhãn `(a)/(b)` (`_is_unlabeled_two_col_plot_grid`).

### Fixed
- Khắc phục lỗi hai subplot xếp chồng trên bài báo 2 cột bị `_is_table_row_pair` / `_row_aligned_text_indices` chặn gộp do quét sang đoạn văn xuôi ở cột bên cạnh hoặc các ký hiệu hạt/toán học ngắn (`<= 2` ký tự);
- Khấu trừ token số chia vạch trục (`_TICK_TOKEN_RE`) trên đồ thị nhiều đường cong để không loại nhầm hình nhiều subplot có trên `150` số chia trục ở bộ lọc `uncaptioned_high_words` và `prose_box`;
- Mở rộng `_PROSE_AFTER_NUM_RE` chặn dòng văn xuôi ngắt dòng bắt đầu bằng `Figure <số> that/where/when...`, sửa `_has_obstacle_between` không nhận nhầm trục X dưới đáy đồ thị trên thành đường kẻ ngăn cách trang, và nâng ngưỡng cầu nối nhãn trục X (`caption_below_bridge_gap`: `78 → 96 pt`).

## [1.1.6] - 2026-11-19
### Security
- **Chặn PowerShell Double-Quote Injection & Indirect Prompt Injection:** Bổ sung ranh giới dữ liệu không tin cậy vào `AGENTS.md` và cả hai `SKILL.md`, chuyển toàn bộ mẫu tham số đường dẫn PowerShell sang ngoặc đơn `'...'` (không bung `$(...)`/`$var` từ tên tệp PDF) và lọc ký tự điều khiển / chuỗi giả mạo `=== MANIFEST JSON START/END ===` trên stdout;
- **Auto-QA HTML/URI/CSS theo Allowlist + Chặn MathJax/SVG & tiêm CSP:** `<a href>` chỉ cho phép `#`, `https://`, `http://`, `mailto:` (chặn mọi Windows protocol handler `search-ms:`, `ms-appinstaller:`, `ms-msdt:`, `smb:`, `blob:`, `\\UNC`); CSS `url()` và `image-set()` chuyển sang allowlist; chặn `<foreignObject>`, `<animate*>`, `<set>`, `<template>`, `<noscript>`, DOM clobbering `MathJax`, và macro LaTeX nguy hiểm (`\href{javascript:...}`, `\style{...url(...)}`); tự động tiêm `<meta http-equiv="Content-Security-Policy">` kèm hash `'sha256-...'` động cho `reader_shell.html` và chặn symlink tệp vỏ;
- **Khóa đường dẫn `-Action HtmlToPdf` & cô lập mạng Edge/Chrome headless:** Bắt buộc chạy `run_html_qa_check` trước khi in PDF trực tiếp, bổ sung cờ cô lập trình duyệt và `--host-resolver-rules` chỉ cho phép 4 host MathJax CDN / Google Fonts;
- **Chống bom tài nguyên PDF & bom giải nén ảnh:** Tự động hạ tỷ lệ render trong `extract_images`/`render_pages` giữ `<= 6.000 px`/cạnh và `<= 25 MP`; kiểm tra header PNG/JPEG/GIF/BMP/WebP trước khi giải nén chặn ảnh `> 50 MB` hoặc `> 50 MP` (`> 16.000 px`/cạnh); giới hạn `25.000` nét vẽ vector/trang và `256 MB` cho HTML đầu vào;
- **NTFS ADS & tự làm sạch tên tệp đầu ra:** Chặn cứng NTFS Alternate Data Streams (`:` sau ổ đĩa) trong `tools\src\path_guards.py` và `tools\_path_guards.ps1`, đồng thời tự động làm sạch tên tệp đầu ra khi tên gốc trùng tên thiết bị Windows (`CON` → `doc_CON`), chứa ký tự shell/URL nhạy cảm hoặc vượt `150` ký tự để vẫn dịch bình thường.

### Changed
- Đồng bộ thương hiệu và URL tài liệu sang **Luka-Loop** (`README.md`, `CHANGELOG.md`, `THIRD_PARTY_LICENSES.md`), giữ nguyên tên gói `luka-loop-win-x64.zip` và khóa `localStorage` để đảm bảo tương thích ngược;
- Mở rộng bộ kiểm thử red-team tại `tests\test_extract_assets.py` (30 ca) và `tests\test_powershell.ps1` (15 ca); dọn hàm shim `_collect_page_candidates` không còn sử dụng trong `tools\src\figure_detector.py`.

## [1.1.5] - 2026-11-19
### Added
- Viết lại hoàn chỉnh `tools\src\figure_detector.py` theo kiến trúc **6 pha tuyến tính** (thuần PyMuPDF): tập trung cấu hình ngưỡng tại `DetectorConfig`, phân tích trang một lần vào `PageContext` (cache lazy `get_page_tables()`), phân loại minh bạch qua `FilterDecision(keep, reason)` và bổ sung API truy vết `detect_page_figures_debug(page)`;
- Tự động nới khung biểu đồ vector/hybrid để ôm trọn số chia trục, tiêu đề trục Y xoay 90° và tiêu đề trục X (`_expand_plot_axis_labels`), kèm nối dòng chú thích bị ngắt khối (`_merge_caption_continuations`) và hỗ trợ mẫu `Figure. A.7:`;
- Mở rộng bộ kiểm thử hồi quy tại `tests\test_extract_assets.py` (27 ca) và `tests\test_powershell.ps1` (14 ca) bao phủ toàn bộ 3 mẫu `tests\layout_samples\` và các tính năng mới của pipeline 6 pha.

### Changed
- Tinh chỉnh thuật toán ghép chú thích và gộp đa panel dựa trên đối chứng định lượng **4.999 trang IBM DocLayNet** (`scientific_articles` tăng IoU≥0.50 F1 từ `70.1%` lên `84.8%`, Loose F1 từ `79.3%` lên `91.6%` với Recall `98.3%`; toàn bộ 6 thể loại đạt IoU≥0.50 F1 `62.9%` / Loose F1 `68.7%`): ưu tiên chú thích trên/dưới hơn cạnh bên, áp dụng bất biến chống nuốt (`_violates_merge_invariants`) và bỏ xích gộp các khối không chú thích rời nhau.

### Fixed
- Khắc phục lỗi chia cắt đồ thị khoa học xếp chồng (không để số trục Y / tiêu đề trục xoay 90° bị nhận nhầm thành ô bảng, nhận diện nhãn toán/hóa học ngắn và cho phép dải sơ đồ ngang có chú thích `>= 18 pt`);
- Cứu biểu đồ vector vẽ nét nhỏ và heatmap nhiều ô ít chữ khỏi bị bộ lọc chữ vẽ nét (`outlined_glyph_confetti`) hoặc `find_tables()` loại nhầm;
- Loại sạch dương tính giả UI/bố cục hiện đại (Chrome/Skia/WeasyPrint): hộp bo góc nhiều đoạn Bézier, hero banner đầu trang, khung sidebar trái, thẻ giá/KPI có bullet căn cột + pill badge và bảng bo góc chứa `Table X` bên trong.

## [1.1.4] - 2026-11-19
### Added
- Gia cố bảo mật HTML/DOM trong `run_html_qa_check` (`tools\src\html_packager_core.py`): whitelist `<script>` (chỉ cho phép MathJax v3 CDN rỗng thân trong `<head>` và đúng mã `tools\reader_shell.html` khi không bật `-PreserveLayout`), chặn thẻ nhúng/chuyển hướng (`<iframe>`, `<object>`, `<embed>`, `<applet>`, `<base>`, `<form>`, `<meta http-equiv="refresh">`), thuộc tính `on*`/`srcdoc`/`ping`, URI nguy hiểm (`javascript:`, `vbscript:`, `file:`, `//...`, `data:` ngoài ảnh raster), ảnh/tài nguyên/CSS `url(...)` trỏ ra ngoài ngoài Google Fonts, và liệt kê cụ thể `src` ảnh lỗi;
- Lọc tên thiết bị dành riêng của Windows (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`) và tên kết thúc bằng dấu `.` trong `resolve_safe_crop_out_file` (`tools\src\path_guards.py`), kèm bộ kiểm thử bảo mật mới tại `tests\test_extract_assets.py` (25 ca) và `tests\test_powershell.ps1`.

### Changed
- Tách `tools\src\extract_assets.py` thành 3 module gọn (`extract_assets.py`, `figure_detector.py`, `image_ops.py`) vẫn đóng gói thành 1 tệp `extract_assets.exe` duy nhất (giữ nguyên lazy-import PyMuPDF); bỏ `onclick` và `src=""` mặc định trong `tools\reader_shell.html`; đồng bộ `SKILL.md`, `README.md` và `THIRD_PARTY_LICENSES.md`.

### Removed
- Gỡ bỏ chế độ CLI cũ không còn sử dụng `--mode optimize-images` (`optimize_images_batch`, `_optimize_single_image`) và hàm chết `_validate_bare_filename`.

## [1.1.3] - 2026-11-19
### Added
- Thu hồi các biểu đồ cột/thanh tách rời cạnh chú thích hình trong `tools\src\extract_assets.py` và mở rộng `tests\test_extract_assets.py` (từ 18 lên 24 ca) cho toàn bộ các ca bố cục, đồ thị và lọc nhiễu mới.

### Changed
- Nâng cấp ghép chú thích & đa khung hình trong `tools\src\extract_assets.py`: tách dòng qua ranh giới cột/giữa block, phân biệt chú thích với câu văn tham chiếu, hỗ trợ chú thích bên cạnh căn đáy, khoảng cách trên hình (`<= 64 pt`), cầu nối nhãn trục (`<= 78 pt`), phân xử chú thích hai phía, gộp nhiều subplot chung legend và giữ dải hình minh họa thấp trong ô bảng (`>= 16 pt`).

### Fixed
- Khắc phục sót đồ thị khoa học đa khung và biểu đồ phân tán nhiều điểm dấu (không để nhận nhầm biểu đồ có đường cong/chéo thành bảng và bảo vệ cụm có trục/khung dài);
- Lọc mạnh dương tính giả thực chiến: trang scan chia nhiều dải ngang, dải trang trí tràn lề, banner rộng đầu/cuối trang, watermark vector/raster dưới đoạn văn, thanh tiêu đề có chữ đè, cột bảng thưa chữ, bảng tài chính kẻ ngang không cột dọc và poster/công thức chữ vẽ nét `0`-từ.

## [1.1.2] - 2026-11-19
### Added
- Bổ sung mục **Cách công cụ giảm dung lượng ảnh** kèm sơ đồ Mermaid và tóm tắt 3 chốt bảo vệ vào `README.md`;
- Mở rộng `tests\test_extract_assets.py` (lên 18 ca) và `tests\test_powershell.ps1` cho các ca ảnh thang xám 8-bit, JPEG ít màu vượt `1400 px`, Auto-QA DOM/comment và kiểm tra junction nhánh ngoài workspace.

### Changed
- Nâng hệ số nén JPEG mặc định (`-JpegQuality` / `--quality`) từ `90` lên `95` đồng bộ trên `tools\html_packager.ps1`, `tools\src\html_packager_core.py`, `tools\src\extract_assets.py`, cả hai `SKILL.md` và bộ kiểm thử;
- Bổ sung quy tắc giới hạn phạm vi ghi tệp (`work\` / `output\` trong workspace) vào `AGENTS.md` và làm rõ chỉ thị xử lý liên tục tài liệu dài, đồng bộ mô tả Auto-QA mới trong cả hai `SKILL.md`.

### Fixed
- Sửa tối ưu ảnh trong `tools\src\extract_assets.py`: `_analyze_sample_grid` nhận diện ảnh thuần thang xám (`max-min <= 2`) để đếm đủ sắc độ 8-bit (`0..255`), và `_optimize_image_bytes` cho phép co kích thước JPEG ít màu vượt `MaxImageWidth` (`1400 px`) khi giúp giảm dung lượng;
- Thay kiểm tra regex phẳng trong `run_html_qa_check` (`tools\src\html_packager_core.py`) bằng `_QADOMScanner(HTMLParser)`: kiểm tra lồng thẻ `.table-wrapper` thực sự trên DOM, bỏ qua HTML comment (`<!-- ... -->`) và `<script>`/`<style>`/`<textarea>`, xử lý `<code>` lồng nhau, xác nhận MathJax `<script>` nằm trong `<head>`, đồng thời bỏ qua comment/raw blocks khi nhúng `<img>` và tiêm `reader_shell.html`;
- Sửa nhánh ngoài workspace của `assert_safe_output_path` (`tools\src\path_guards.py`) và `Assert-SafeOutputPath` (`tools\_path_guards.ps1`): bỏ `break` sớm để kiểm tra toàn bộ các thư mục tổ tiên tồn tại cho tới gốc ổ đĩa thay vì bỏ sót symlink/junction phía trên tệp hoặc thư mục con đã tồn tại.

## [1.1.1] - 2026-11-18
### Changed
- Đồng bộ chuẩn typography SKILL 1 (`pdf-to-html-vi\si_academic_html.md`) sang họ font `Inter` (fallback Windows `'Segoe UI'`), bật `tabular-nums` cho `table`, `'JetBrains Mono'` cho code và cập nhật thông báo font trong `THIRD_PARTY_LICENSES.md`;
- Bổ sung quy tắc trong `AGENTS.md` và cả 2 `SKILL.md` cấm chạy lệnh liệt kê/kiểm tra `output\` trước hoặc sau Bước 4 (tận dụng cơ chế tự tạo thư mục và tự đánh số `_2`, `_3` của `html_packager.ps1` để giảm lượt gọi thừa của Agent);
- Tinh gọn và đồng bộ 2 cặp tài liệu `SKILL` / `SI`: tỉa trùng lặp điều phối CLI khỏi `si_academic_html.md`, gỡ `@import` lặp ở `si_layout.md`, nối khít bước chuyển hóa tag trung gian + liên kết DOI/URL `References` giữa `si_translation.md` và `si_layout.md`, đồng thời bổ sung chốt chặn thực chiến (lọc tạp âm bản scan, chừa khoảng trắng quanh `<`/`>` trong LaTeX, lớp `.cjk`, `<header>` + `<article>` khớp `reader_shell.html`, `tr` + `.table-note` + `figure img { max-height: 82vh; }` an toàn in PDF).

## [1.1.0] - 2026-11-18
### Changed
- Tái cấu trúc `extract_assets.exe` tiếp nhận toàn bộ nghiệp vụ xử lý chính qua mô-đun `tools\src\path_guards.py` và `tools\src\html_packager_core.py`: kiểm tra an toàn đường dẫn/UNC/junction, phân giải PDF từ `transcript.jsonl`, tối ưu & nhúng Base64 trực tiếp trong bộ nhớ (không tạo ảnh tạm trên đĩa), Auto-QA HTML, bơm `reader_shell.html`, đánh số chống ghi đè, xuất PDF qua Edge/Chrome headless và dọn `work\`;
- Nâng cấp `PyMuPDF` từ `1.25.2` lên `1.28.2` trong `tools\src\requirements-build.txt` và bật lazy-import `_ensure_pymupdf()` (tắt thông báo gợi ý `pymupdf_layout` trên stdout để giữ đầu ra sạch);
- Rút gọn `tools\extract_pdf_assets.ps1`, `tools\pdf_fallback_tools.ps1` và `tools\html_packager.ps1` về dạng wrapper CLI siêu mỏng (51–85 dòng) giữ 100% tương thích tham số cũ, đồng bộ `.github\workflows\ci.yml` (`tools/src/*.py`), `build_extractor.ps1`, `SKILL.md`, `README.md`, `THIRD_PARTY_LICENSES.md` và bổ sung unit test trong `tests\test_extract_assets.py`.

## [1.0.8] - 2026-11-18
### Added
- Thiết lập GitHub Actions CI/CD (`.github\workflows\ci.yml` và `release.yml`): kiểm thử tự động trên **Windows PowerShell 5.1**, **PowerShell 7** và Python (cache binary theo mã băm nguồn khi push nhánh `main`), và build sạch `extract_assets.exe` khi đẩy tag `v*` để đóng gói trọn bộ `luka-loop-win-x64.zip` kèm `hashes.sha256` lên GitHub Releases;
- Thêm `tools\build_extractor.ps1` và tệp ghim phiên bản build `tools\src\requirements-build.txt` (`PyMuPDF==1.25.2`, `pyinstaller==6.20.0`).

### Changed
- Gỡ bỏ thư mục nhị phân `tools\extract_assets\` (58 tệp) khỏi theo dõi Git và thêm vào `.gitignore` để ngăn phình dung lượng lịch sử Git;
- Cập nhật `README.md` sang link tải 1-click trọn gói (`.../releases/latest/download/luka-loop-win-x64.zip`), đồng bộ `THIRD_PARTY_LICENSES.md` và bổ sung gợi ý tải/build trong `tools\_path_guards.ps1`.

## [1.0.7] - 2026-11-18
### Added
- Bổ sung 3 chế độ thuần PyMuPDF cho `extract_assets.py` / `extract_assets.exe` (`--mode render-pages`, `--mode crop-json`, `--mode optimize-images`) và gom hàm dùng chung `Resolve-SafeOutDirectory`, `Invoke-ExtractAssetsExe` vào `tools\_path_guards.ps1`;
- Mở rộng bộ kiểm thử `tests\test_extract_assets.py` (11 ca) và `tests\test_powershell.ps1` (13 ca): kiểm tra AST cấm API phụ thuộc GDI+/C# động/WinRT, hỗ trợ tự chạy theo `pwsh.exe` hoặc `powershell.exe`.

### Changed
- Hỗ trợ chạy song song trên cả **Windows PowerShell 5.1** lẫn **PowerShell 7+** (`pwsh.exe`): chuyển `tools\pdf_fallback_tools.ps1` và `tools\html_packager.ps1` sang gọi `extract_assets.exe`, loại bỏ hoàn toàn WinRT `Windows.Data.Pdf`, `System.Drawing` và `Add-Type` (kể cả trong `tests\test_powershell.ps1`);
- Tối ưu `html_packager.ps1`: khử trùng lặp ảnh cục bộ, xử lý theo lô 1 tiến trình duy nhất (bỏ qua nếu HTML có 0 ảnh), cập nhật build `extract_assets.exe` giữ nguyên quy mô 58 tệp (~56,5 MB) không thêm thư viện ngoài, và cập nhật `README.md`.
- Điều chỉnh SI dịch cho luồng bảo vệ định dạng;

### Fixed
- Bổ sung `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8` vào `pdf_fallback_tools.ps1` và `html_packager.ps1` để không lỗi dấu đường dẫn tiếng Việt trên console `cp437`/`cp1252`;
- Sửa lỗi truyền `ConvertTo-Json` cho PowerShell 5.1 (`[pscustomobject]`), chuẩn hóa `--scale` theo `InvariantCulture`, và xử lý ngắt dòng `ConciseView` của PowerShell 7 trong `Invoke-CliPs1`.

## [1.0.6] - 2026-11-18
### Added
- Thêm skill `pdf-to-html-vi-layout` (chế độ bảo toàn thiết kế/layout): tách pha dịch `work\translated.md` (`si_translation.md`) trước khi dựng HTML/CSS cô lập từng trang (`si_layout.md`, font `Inter` `18px`, `--page-width` `740px–1000px`, CSS Multi-Columns/Grid);
- Thêm `-PreserveLayout` vào `tools\html_packager.ps1` (không tiêm `reader_shell.html`, cho phép `<table>` không bọc `.table-wrapper`) và 3 tệp PDF mẫu đa cột/bảng/scan tại `tests\layout_samples\`.

### Changed
- Phân tách hậu tố đầu ra `_vi.*` (mặc định) và `_layout_vi.*` (giữ thiết kế); `html_packager.ps1` luôn tự đánh số `_2`, `_3`... chống ghi đè đồng bộ cả cặp `.html`/`.pdf`;
- Cập nhật `AGENTS.md`, `README.md`, contract đầy đủ trong `SKILL.md` (chạy thẳng CLI, không đọc mã nguồn `tools\`) và ca kiểm thử tương ứng trong `tests\test_powershell.ps1`.

## [1.0.5] - 2026-11-18
### Added
- Bổ sung mục **Cách công cụ xử lý ảnh** kèm sơ đồ Mermaid tổng quan vào `README.md`;
- Bổ sung vào `manifest.json` các trường `dpi`, `source` (`raster`/`vector`/`hybrid`), `drawings`, `placement` (`figure`/`table_cell`) và ca kiểm thử tương ứng trong `tests\`;

### Changed
- Thay `bbox` PDF point bằng `box` chuẩn hóa `0.0–1.0` trong `manifest.json` (đồng bộ với `CropFromJson`) và build lại `extract_assets.exe` gọn nhẹ (58 tệp);
- Cập nhật `SKILL.md`, `si_academic_html.md` và `AGENTS.md`: quy tắc khai thác `manifest.json`, **Sàng lọc trước khi Cắt (`Triage before Crop`)** không cắt `CropFromJson` cho sơ đồ đơn giản (vẫn bắt buộc `read_file` song song ảnh đã tách), CSS ảnh ô bảng `td img`, và mẫu phản hồi kết quả thân thiện với người dùng cuối;

### Fixed
- Hỗ trợ nhận diện hàng bảng và trích `context` cho chữ căn giữa theo chiều dọc trong `extract_assets.py` (tránh bắt nhầm dòng tiêu đề bảng);
- Bổ sung `tests export-ignore` vào `.gitattributes` để loại bỏ cả thư mục `tests\` rỗng khỏi gói Release ZIP;

## [1.0.4] - 2026-11-17
### Added
- Thêm bộ kiểm thử tự động `tests\` (`run_tests.ps1`, `test_powershell.ps1`, `test_extract_assets.py`) kèm 3 tệp PDF mẫu (chuẩn, scan, hỗn hợp) và `.gitattributes` loại `tests\` khỏi gói Release ZIP;
- Bổ sung tham số `-Pages` cho `pdf_fallback_tools.ps1` (`RenderPages`) để chỉ render đúng các trang scan cần dùng;

### Changed
- Gom các hàm kiểm tra đường dẫn dùng chung sang `tools\_path_guards.ps1` và tối ưu phân tích ảnh bằng `LockBits` trong `html_packager.ps1`;
- Tương thích thư mục đồng bộ đám mây (OneDrive, Dropbox, Google Drive...): phân biệt symlink/junction thật với placeholder Cloud, cảnh báo tệp chưa tải offline và xử lý mềm khi khóa tệp lúc dọn `work\`;

### Fixed
- Sửa `extract_assets.py` và build lại `extract_assets.exe`: nhận diện đúng chú thích (`Fig. S1`, `Sơ đồ`, tránh văn xuôi bẫy), giữ nét nối lưu đồ & trục biểu đồ X/Y, giữ sơ đồ vector `>80` từ có chú thích, bỏ qua khung `<pre><code>`, hỗ trợ `CropBox`, PDF khóa mật khẩu và `stdout` UTF-8;
- Sửa Auto-QA `html_packager.ps1` (hỗ trợ nháy đơn, bỏ qua `\(`/`\[` trong `<pre>`/`<code>`), bật `PYTHONUTF8` & lọc `application/pdf` trong `extract_pdf_assets.ps1`, đọc ảnh không khóa file trong `pdf_fallback_tools.ps1` và đồng bộ `aria-hidden` ở `reader_shell.html`;

## [1.0.3] - 2026-11-17
### Fixed
- Cập nhật README.md rõ ràng hơn;
- Cập nhật để các file .ps1 an toàn và dự phòng lỗi tốt hơn;

## [1.0.2] - 2026-11-17
### Fixed
- README chi tiết hơn;
- Thông tin LICENSES chi tiết hơn;
- Cập nhật AGENTS.md để nó đồng bộ hơn với SKILL.md;

## [1.0.1] - 2026-11-17
### Fixed
- Điều chỉnh một chút CSS, và SI;

## [1.0.0] - 2026-11-16
### Fixed
- Điều chỉnh các vấn đề logic trong SKILL.md;
