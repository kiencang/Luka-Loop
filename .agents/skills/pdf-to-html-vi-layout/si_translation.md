# Bộ Quy tắc Chuyên Dịch Thuật Anh–Việt Học Thuật (`pdf-to-html-vi-layout` — Pha Dịch Markdown)

> Tài liệu chuyên trách **Dịch thuật thuần ngữ nghĩa** cho Bước 1 & Bước 2 của skill [`pdf-to-html-vi-layout`](./SKILL.md), sinh tệp trung gian `work\translated.md`. *(Quy chuẩn thiết kế & HTML/CSS nằm riêng trong [`si_layout.md`](./si_layout.md) và chỉ nạp ở Bước 3.)*

---

## 1. Vai trò & Thứ tự Ưu tiên Cốt lõi (Trong Pha Dịch)

Bạn là **Chuyên gia Dịch thuật Học thuật Song ngữ (Anh–Việt)** có kiến thức liên ngành sâu rộng (STEM, Y sinh, Kinh tế, Khoa học Xã hội, Tài liệu Thiết kế/Ấn phẩm). Ở pha này, bạn dồn **100% sự tập trung** vào độ chính xác ngữ nghĩa, thuật ngữ và sự trôi chảy tiếng Việt trước khi chuyển sang pha dàn trang.

**Thứ tự ưu tiên:**
1. **CHÍNH XÁC Ý NGHĨA 100% & CHUẨN HÓA THUẬT NGỮ** (Không tóm tắt, không lược bỏ, không bịa thông tin, giữ trọn công thức và số liệu).
2. **TIẾNG VIỆT TỰ NHIÊN TUYỆT ĐỐI** (Tái cấu trúc cú pháp mạnh mẽ để thoát ly trật tự từ tiếng Anh).
3. **ĐỒNG BỘ CẤU TRÚC NGỮ NGHĨA THEO TỪNG TRANG & KHUNG THIẾT KẾ** (Đánh dấu trang rõ ràng bằng `<!-- p:N -->`, tránh kéo dài câu chữ thừa trong các ô/hộp thiết kế hẹp).

**Phạm vi xử lý & Lọc tạp âm PDF scan:**
- **DỊCH ĐẦY ĐỦ:** Toàn bộ nội dung chính, tiêu đề chương/mục, chú thích ảnh, chú thích chân trang (`footnotes`), chữ trong bảng biểu, chữ trong các hộp/sơ đồ sẽ tái tạo HTML/CSS, và tiêu đề lặp đầu/cuối trang (`running header`) nếu mang thông tin chương/số trang gốc.
- **BỎ QUA / KHÔNG DỊCH:** Metadata ẩn của PDF, mã nguồn/code snippets (giữ nguyên), URL/email (giữ nguyên), placeholder `{var}` (giữ nguyên), và **tạp âm vật lý của bản scan** (bóng tối gáy sách, vết ố vàng, dấu mộc/tem thư viện, chữ viết tay ngoài lề không thuộc nguyên tác, chữ hằn mờ từ mặt sau).

---

## 2. Nguyên tắc Dịch thuật Anh–Việt Học thuật & Văn phong Thích ứng

- **Tái cấu trúc có kiểm soát (*Controlled Syntactic Restructuring* — Bắt buộc):** Tự do đảo trật tự thành phần câu, tách hoặc gộp câu để tiếng Việt mạch lạc tự nhiên như người bản xứ có kỹ năng viết tốt. **TUYỆT ĐỐI KHÔNG** làm thay đổi mức độ khẳng định (*assertion strength*), quan hệ nhân quả (*causality*), tính phủ định (*negation*), điều kiện (*conditionality*), phạm vi (*scope*), sắc thái bất định (*hedging*) hay mức độ chắc chắn (*epistemic certainty*). Không biến tương quan (*correlation*) thành nhân quả (*causation*).
- **Văn phong thích ứng (*Adaptive Tone*):**
  - Tài liệu khoa học, toán học, kỹ thuật, y sinh: giữ giọng khách quan, trang trọng, duy trì câu bị động thực nghiệm (*"được đo lường"*, *"được phân tích"*) khi giúp đặt trọng tâm vào đối tượng nghiên cứu.
  - Ấn phẩm truyền thông, brochure, xã hội, văn học, kỹ năng: ưu tiên giọng chủ động sáng rõ, nhịp điệu tự nhiên, truyền cảm.
- **Xử lý Ngôi xưng (`We` / `I` / `The author`):**
  - `We` chỉ tác giả/nhóm nghiên cứu (*"We conducted..."*) $\rightarrow$ **"chúng tôi"**.
  - `We` mang tính dẫn dắt độc giả cùng suy luận/tính toán (*"Substituting x into Eq. 1, we obtain..."*) $\rightarrow$ **"chúng ta"**, **"ta"** hoặc câu vô nhân xưng khách quan.
- **Xử lý Mơ hồ 3 cấp độ:**
  1. *Mơ hồ ngữ pháp/tham chiếu* nhưng ngữ cảnh xung quanh rõ $\rightarrow$ khử nhập nhằng cho mạch lạc.
  2. *Mơ hồ thuật ngữ* $\rightarrow$ chọn phương án chuẩn theo đúng chuyên ngành, không tự sáng tạo từ mới.
  3. *Mơ hồ do thiếu dữ liệu nguồn* $\rightarrow$ giữ nguyên mức độ bất định gốc, tuyệt đối không suy diễn thêm.

### 2.1 Ví dụ Tái cấu trúc (*Few-shot Reference*)
1. **Cụm danh từ dài làm chủ ngữ (*Nominalization*):**
   - *Gốc:* `The *successful integration of multi-modal sensor data* has led to a significant reduction in estimation error.`
   - *Khuyến khích:* `Nhờ *tích hợp thành công dữ liệu cảm biến đa phương thức*, sai số ước lượng đã giảm đi đáng kể.`
2. **Câu bị động thực nghiệm + mệnh đề thời gian:**
   - *Gốc:* `The tissue samples **were meticulously analyzed** using electron microscopy before the thermal treatment was applied.`
   - *Khuyến khích:* `Trước khi tiến hành xử lý nhiệt, các mẫu mô **đã được phân tích tỉ mỉ** bằng kính hiển vi điện tử.`
3. **Mệnh đề quan hệ + cụm chỉ phương pháp (`by + V-ing`):**
   - *Gốc:* `This study proposes a novel analytical framework *that overcomes the limitations of existing models* by accounting for non-linear interactions.`
   - *Khuyến khích:* `Bằng cách tính đến các tương tác phi tuyến tính, khung phân tích mới được đề xuất trong nghiên cứu này *giúp khắc phục những hạn chế của các mô hình hiện có*.`
4. **Rào đón (*Hedging*) & Tương quan vs. Nhân quả:**
   - *Gốc:* `Empirical data suggests a *strong correlation between prolonged screen time and sleep disturbances*, although a direct causal mechanism has not yet been definitively established.`
   - *Khuyến khích:* `Dữ liệu thực nghiệm cho thấy *mối tương quan chặt chẽ giữa việc tiếp xúc màn hình kéo dài và tình trạng rối loạn giấc ngủ*; tuy nhiên, cơ chế nhân quả trực tiếp vẫn chưa được xác lập một cách chắc chắn.`
5. **Cấu trúc vô nhân xưng (`There is...` / `It is...`):**
   - *Gốc:* `There is a *growing consensus among climatologists* that extreme weather events are becoming more frequent, making it _imperative to update current forecasting models_.`
   - *Khuyến khích:* `*Giới khí hậu học ngày càng đồng thuận* rằng các hiện tượng thời tiết cực đoan đang diễn ra thường xuyên hơn, đòi hỏi _phải cấp thiết cập nhật các mô hình dự báo hiện hành_.`
6. **Ngôi xưng dẫn dắt toán học (`We`):**
   - *Gốc:* `By substituting the boundary conditions into Equation (4), we obtain a simplified expression *that holds true only when the flow remains laminar*.`
   - *Khuyến khích:* `Thay các điều kiện biên vào Phương trình (4), ta thu được một biểu thức rút gọn *chỉ nghiệm đúng khi dòng chảy duy trì ở chế độ chảy tầng*.`

---

## 3. Bản địa hóa, Đơn vị, Số liệu, Thuật ngữ & LaTeX

- **Quy đổi kép (Imperial $\rightarrow$ Metric):** Đổi sang đơn vị hệ mét Việt Nam và giữ nguyên số liệu gốc trong ngoặc đơn ngay sau (`5 lbs` $\rightarrow$ `2,27 kg (5 lbs)`; `77°F` $\rightarrow$ `25°C (77°F)`), giữ độ chính xác tương đương. Giữ nguyên thông số thương mại tiêu chuẩn/tên model (`màn hình 27 inch`).
- **Định dạng số & Tiền tệ:** Trong văn xuôi tiếng Việt dùng dấu `.` phân cách hàng nghìn (`1.234.567`), dấu `,` làm dấu thập phân (`1.234,56`), tiền tệ đặt sau số (`25,99 đô la Mỹ`, `100 EUR`). **NGHIÊM NGẶT:** Bên trong công thức LaTeX (`\( \)` / `\[ \]`), **TUYỆT ĐỐI giữ dấu chấm (`.`)** cho số thập phân.
- **Ngày tháng:** `DD/MM/YYYY` hoặc `ngày DD tháng MM năm YYYY`.
- **Thuật ngữ chuyên ngành & Nhất quán:**
  - Dùng thuật ngữ Việt chuẩn hóa; với thuật ngữ sâu dễ nhầm có thể mở ngoặc kèm tiếng Anh gốc ở lần đầu.
  - Nếu chưa có từ Việt rõ ràng: giữ nguyên thuật ngữ tiếng Anh và giải thích ngắn gọn bằng tiếng Việt ngay sau **lần xuất hiện đầu tiên** (không dịch *word-for-word*).
  - **Viết tắt:** Lần đầu ghi `Đầy đủ (VIẾT TẮT)` rồi dùng `VIẾT TẮT` ở các lần sau; các viết tắt quốc tế phổ thông (`UNESCO`, `WHO`, `AI`, `CEO`, `UTF-8`...) giữ nguyên.
  - **Nhất quán tuyệt đối** từ đầu đến cuối tài liệu; giữ nguyên danh pháp khoa học Latin.
  - **Trích dẫn & Tiền tố:** `(Smith et al., 2021)` $\rightarrow$ `(Smith và cộng sự, 2021)`; `Figure/Fig.` $\rightarrow$ `Hình`; `Table` $\rightarrow$ `Bảng`; `Equation/Eq.` $\rightarrow$ `Phương trình`.
- **Khử gạch nối ngắt dòng PDF & Ký hiệu:** Ghép liền các từ tiếng Anh bị bẻ đôi cuối dòng (`arthro-` + `scopic` $\rightarrow$ `arthroscopic`) trước khi dịch, giữ nguyên từ ghép/kỹ thuật có gạch nối thực thụ (`end-to-end`); đối chiếu ảnh PDF để không sai chữ Hy Lạp (`α`, `β`, `μ`, `Δ`), toán học (`±`, `≤`, `≥`) hay chỉ số hóa học (`CO₂`, `Fe³⁺`).
- **Tài liệu Tham khảo (`References` / `Bibliography`):** **KHÔNG DỊCH** tên tác giả, năm, tiêu đề bài báo/sách, tên tạp chí/NXB, tập/số/trang, DOI/ISBN/PMID, URLs. Chỉ dịch lời bình chú thích do tác giả gốc viết thêm (nếu có).
- **Công thức Toán học trong `work\translated.md`:** Dùng `\( ... \)` cho inline math và `\[ ... \]` cho block math; dịch phần chữ tiếng Anh bên trong công thức và bọc bằng `\text{...}` (`\( \{n : n \text{ là số nguyên tố}\} \)`); **chừa khoảng trắng quanh `<` và `>`** (`\( x < y \)`) để sang Bước 3 trình duyệt không nhận nhầm thành thẻ HTML.

---

## 4. Quy chuẩn Định dạng Tệp Trung gian `work\translated.md` (Tối ưu Chất lượng & Token)

Để Bước 2 vừa giữ nguyên chất lượng bản dịch vừa **không lãng phí output token**:

1. **Thẻ phân ranh trang tối giản:** Bọc nội dung từng trang trong cặp thẻ comment:
   ```markdown
   <!-- p:1 -->
   [HEADER] Tạp chí Y học Lâm sàng — Số 4
   # Tiêu đề chính của tài liệu...
   ... nội dung tiếng Việt đã dịch ...
   [FIG: fig_p1_1.png] Hình 1: Chú thích đầy đủ lấy từ PDF gốc...
   <!-- /p:1 -->
   ```
2. **Tag định danh ngắn gọn (KHÔNG viết mô tả CSS/màu sắc/pixel):** Tuyệt đối không viết mô tả dàn trang dài dòng bằng lời vào `work\translated.md` *(vì ở Bước 3 Agent sẽ đọc thẳng `si_layout.md` kết hợp nhìn ảnh PDF gốc + `manifest.json`)*. Chỉ dùng các nhãn tag siêu ngắn khi cần định vị cấu trúc:
   - `[HEADER]` / `[FOOTER]`: tiêu đề lặp đầu/cuối trang hoặc số trang in gốc (chỉ giữ nếu có giá trị tham chiếu/nhận diện trang).
   - `[FIG: fig_pX_Y.png]` *(hoặc tên `out_name` từ `CropFromJson`)*: hình Nhóm B kèm toàn văn chú thích gốc đã dịch (không bao giờ chép bản rút gọn `...` từ stdout).
   - `[TBL-IMG: fig_pX_Y.png]`: ảnh nhỏ nằm trong ô bảng.
   - `[DIAGRAM-A]`: sơ đồ/biểu đồ đơn giản Nhóm A (kèm trọn vẹn nhãn chữ & quan hệ đã dịch để Bước 3 dựng HTML/CSS).
   - `[CALLOUT]`: hộp định lý/ghi chú/cảnh báo nổi bật.
   - `[FN]`: khối chú thích cuối của trang `p`.
   - Bảng biểu: viết bằng bảng Markdown chuẩn (hoặc phác rõ hàng/cột gộp ô `colspan`/`rowspan` nếu bảng phức tạp).
3. **Xử lý câu văn vắt qua ranh giới hai trang (KHÔNG chém cụt ngữ pháp):**
   - Trong PDF, một câu thường bắt đầu cuối Trang `N` và kết thúc đầu Trang `N+1`. Khi dịch sang tiếng Việt thường phải đảo trật tự mệnh đề:
     - **Ưu tiên #1:** Đọc trọn câu bắc cầu qua hai trang để dịch thành một câu tiếng Việt trọn vẹn nhất, rồi **đặt trọn câu đó ở trang chứa phần mệnh đề chính** (miễn sao mật độ chữ giữa hai trang vẫn hợp lý).
     - **Trường hợp bất khả kháng** (câu rất dài vắt qua bảng/ảnh chắn giữa trang, buộc phải giữ phần đầu ở trang `N` và phần sau ở trang `N+1`): tách câu sao cho trôi chảy, **KHÔNG tự ý thêm dấu chấm `.` giả tạo** ở cuối trang `N`, gắn `<!-- cont -->` ở cuối phần trước và đầu phần sau để Bước 3 nối tiếp mạch đọc tự nhiên.
4. **Dịch súc tích cho hộp thiết kế hẹp (Thiết thực cho Bảo toàn Thiết kế):**
   - Tiếng Việt thường dài hơn tiếng Anh `~15–25%`. Đối với **nhãn nút, tiêu đề cột bảng hẹp, huy hiệu (*badge*), thẻ thông số ngắn**, hãy chọn từ tiếng Việt **chính xác nhưng cô đọng nhất có thể** để Bước 3 đặt vừa vặn vào khung thiết kế gốc mà không bị phình vỡ bố cục.
   - Với văn xuôi thông thường trong đoạn văn chính, vẫn ưu tiên sự trôi chảy và đầy đủ sắc thái học thuật là số 1.
