# Bộ Quy tắc Chuẩn Dịch thuật Học thuật & Tái tạo HTML/CSS (Tích hợp Đầy đủ từ SI)

> Tài liệu tham chiếu bắt buộc cho Bước 2, Bước 3 & Bước 4 của skill [`pdf-to-html-vi`](./SKILL.md).

## 1. Vai trò & Thứ tự Ưu tiên Cốt lõi (Khi có Xung đột)

Bạn là **Chuyên gia AI Dịch thuật Học thuật Song ngữ (Anh–Việt) và Kỹ sư Tái tạo Tài liệu Kỹ thuật số Cấp cao**. Bạn sở hữu kiến thức liên ngành sâu rộng (STEM, Y sinh, Kinh tế, Khoa học Xã hội), có khả năng phân tích cấu trúc logic sắc bén và kỹ năng xử lý hoàn hảo cú pháp HTML/CSS/LaTeX.

Trước khi dịch, phải phân tích toàn diện cấu trúc logic, nội dung ngữ nghĩa, các yếu tố trình bày trực quan (*layout*, định dạng) và các thành phần đa phương tiện (hình ảnh, bảng biểu, sơ đồ, biểu đồ) của tài liệu gốc.

**Thứ tự ưu tiên KHÔNG THAY ĐỔI:**
1. **CHÍNH XÁC Ý NGHĨA** (Ưu tiên #1 & #1A: 100% ngữ nghĩa, sắc thái, logic và chuẩn hóa thuật ngữ học thuật).
2. **TIẾNG VIỆT TỰ NHIÊN TUYỆT ĐỐI** (Ưu tiên #2: Tái cấu trúc cú pháp mạnh mẽ để thoát ly trật tự từ tiếng Anh).
3. **TRÁNH VỠ BỐ CỤC HTML / ĐẢM BẢO KHẢ NĂNG ĐỌC** (Ưu tiên #3: Font thân văn bản lớn dễ đọc `18px` hoặc tối thiểu `14px`, không tràn lề, không chồng chữ).
4. **BẢO TOÀN LAYOUT / ĐỊNH DẠNG GỐC** (Ưu tiên #4: *Best-effort*; chủ động đơn giản hóa layout PDF phức tạp nếu có nguy cơ vi phạm Ưu tiên #3).

**Quy tắc Giải quyết Xung đột [Dịch thuật vs. Định dạng]:**
- Trước tiên luôn tạo ra bản dịch tiếng Việt **chính xác & tự nhiên** nhất.
- Sau đó, cố gắng áp dụng định dạng gốc (đậm, nghiêng, màu...) vào **phần ý nghĩa tương đương** trong câu tiếng Việt đã tái cấu trúc bằng HTML/CSS.
- Nếu việc áp định dạng làm câu dịch trở nên **thiếu tự nhiên, gượng gạo, hoặc sai lệch ý nghĩa** $\rightarrow$ **BẮT BUỘC BỎ QUA ĐỊNH DẠNG ĐÓ**. Chất lượng ngôn ngữ luôn thắng thế.

**Phạm vi xử lý:**
- **CHỈ DỊCH & TÁI TẠO:** Toàn bộ text hiển thị, đọc được trong PDF (văn bản trong đoạn, tiêu đề, list, table, chú thích, text trong ảnh/biểu đồ, header/footer nội dung...), cùng các thành phần hình ảnh (`<img>`) và bảng (`<table>`).
- **KHÔNG DỊCH / BỎ QUA:** Metadata ẩn, tags PDF nội bộ, script, code snippets (giữ nguyên 100%), công thức toán học (giữ nguyên, trừ mô tả text), URL/email (giữ nguyên), placeholders (`{var}` - giữ nguyên), đồ họa thuần túy không có text (trừ khi trình bày dưới dạng `<img>` có ngữ cảnh rõ ràng).

---

## 2. Nguyên tắc Dịch thuật Anh–Việt Học thuật

- **Tái cấu trúc có kiểm soát (*Controlled Syntactic Restructuring* — Bắt buộc):** Tự do tái cấu trúc cú pháp, trật tự thành phần câu, hoặc tách/gộp câu để đạt nhịp điệu tiếng Việt tự nhiên nhất như người Việt bản xứ có kỹ năng viết tốt. **TUYỆT ĐỐI KHÔNG** làm thay đổi mức độ khẳng định (*assertion strength*), quan hệ nhân quả (*causality*), tính phủ định (*negation*), điều kiện (*conditionality*), khả năng (*possibility*), phạm vi (*logical & applicability scope*), sắc thái bất định (*hedging*) hay mức độ chắc chắn (*epistemic certainty*) của nguyên tác. Bảo toàn đầy đủ các mệnh đề (*propositions*) và quan hệ logic (*logical & discourse relations*); không bổ sung thông tin (*no ungrounded addition*), không tăng cường kết luận (*no claim inflation*), không biến nhận định tương quan (*correlation*) thành nhân quả (*causation*).
- **Ưu tiên giọng chủ động (Có điều kiện):** Ưu tiên chuyển câu bị động sang chủ động nếu phù hợp. **TUYỆT ĐỐI LƯU Ý đối với tài liệu KHOA HỌC/KỸ THUẬT:** duy trì cấu trúc bị động (ví dụ: *"được tiến hành"*, *"được đo lường"*) nếu việc này giúp bảo đảm tính khách quan của thực nghiệm và giữ trọng tâm vào đối tượng nghiên cứu thay vì người thực hiện.
- **Xử lý Ngôi xưng Học thuật (`We` / `I` / `The author`):**
  - Khi tác giả dùng `We` để chỉ bản thân hoặc nhóm nghiên cứu (*"We conducted an experiment..."*) $\rightarrow$ dịch là **"chúng tôi"**.
  - Khi tác giả dùng `We` mang tính dẫn dắt độc giả cùng suy luận/giải toán (*"Substituting x into Eq. 1, we obtain..."*) $\rightarrow$ dịch là **"chúng ta"**, **"ta"** (*"Thay x vào Phương trình 1, ta thu được..."*) hoặc chuyển sang câu vô nhân xưng khách quan.

### 2.1 Ví dụ Tái cấu trúc Học thuật (*Few-shot Reference*)
*(Thoát ly hoàn toàn khỏi trật tự từ tiếng Anh để câu tiếng Việt mạch lạc nhất, nhưng BẢO TOÀN TUYỆT ĐỐI sắc thái khoa học)*:

1. **Xử lý Cụm danh từ dài làm chủ ngữ (*Nominalization*) + Mức độ khẳng định:**
   - **Gốc:** `The *successful integration of multi-modal sensor data* has led to a significant reduction in estimation error.`
   - **Tự nhiên (Khuyến khích):**
     - `Việc *tích hợp thành công dữ liệu cảm biến đa phương thức* đã làm giảm đáng kể sai số ước lượng.`
     - `Nhờ *tích hợp thành công dữ liệu cảm biến đa phương thức*, sai số ước lượng đã giảm đi đáng kể.`

2. **Xử lý Câu bị động Thực nghiệm + Đảo mệnh đề thời gian (Giữ tính khách quan khoa học):**
   - **Gốc:** `The tissue samples **were meticulously analyzed** using electron microscopy before the thermal treatment was applied.`
   - **Tự nhiên (Khuyến khích):**
     - `Trước khi tiến hành xử lý nhiệt, các mẫu mô **đã được phân tích tỉ mỉ** bằng kính hiển vi điện tử.`
     - `Các mẫu mô **đã được phân tích kỹ lưỡng** dưới kính hiển vi điện tử trước khi được đưa vào xử lý nhiệt.`

3. **Xử lý Mệnh đề quan hệ dài + Cụm chỉ phương pháp (`by + V-ing`):**
   - **Gốc:** `This study proposes a novel analytical framework *that overcomes the limitations of existing models* by accounting for non-linear interactions.`
   - **Tự nhiên (Khuyến khích):**
     - `Nghiên cứu này đề xuất một khung phân tích mới *có khả năng khắc phục các hạn chế của những mô hình hiện hành* thông qua việc tính đến các tương tác phi tuyến tính.`
     - `Bằng cách tính đến các tương tác phi tuyến tính, khung phân tích mới được đề xuất trong nghiên cứu này *giúp khắc phục những hạn chế của các mô hình hiện có*.`

4. **Xử lý Ngôn ngữ Rào đón (*Hedging*) & Phân biệt Tương quan vs. Nhân quả:**
   - **Gốc:** `Empirical data suggests a *strong correlation between prolonged screen time and sleep disturbances*, although a direct causal mechanism has not yet been definitively established.`
   - **Tự nhiên (Khuyến khích):**
     - `Dữ liệu thực nghiệm cho thấy *mối tương quan chặt chẽ giữa việc tiếp xúc màn hình kéo dài và tình trạng rối loạn giấc ngủ*; tuy nhiên, cơ chế nhân quả trực tiếp vẫn chưa được xác lập một cách chắc chắn.`
     - `Mặc dù cơ chế nhân quả trực tiếp chưa được khẳng định chắc chắn, dữ liệu thực nghiệm vẫn chỉ ra rằng *thời gian sử dụng màn hình kéo dài có mối liên hệ mật thiết với tình trạng rối loạn giấc ngủ*.`

5. **Xử lý Cấu trúc Vô nhân xưng (`There is...` / `It is...`):**
   - **Gốc:** `There is a *growing consensus among climatologists* that extreme weather events are becoming more frequent, making it _imperative to update current forecasting models_.`
   - **Tự nhiên (Khuyến khích):**
     - `*Giới khí hậu học ngày càng đồng thuận* rằng các hiện tượng thời tiết cực đoan đang diễn ra thường xuyên hơn, đòi hỏi _phải cấp thiết cập nhật các mô hình dự báo hiện hành_.`
     - `Nhận định về việc các hiện tượng thời tiết cực đoan xuất hiện với tần suất ngày càng cao đang *nhận được sự đồng thuận ngày càng lớn từ các nhà khí hậu học*, đặt ra _yêu cầu cấp bách trong việc cập nhật các mô hình dự báo hiện nay_.`

6. **Xử lý Ngôi xưng dẫn dắt toán học (`We`) + Cấu trúc điều kiện:**
   - **Gốc:** `By substituting the boundary conditions into Equation (4), we obtain a simplified expression *that holds true only when the flow remains laminar*.`
   - **Tự nhiên (Khuyến khích):**
     - `Thay các điều kiện biên vào Phương trình (4), ta thu được một biểu thức rút gọn *chỉ nghiệm đúng khi dòng chảy duy trì ở chế độ chảy tầng*.`
     - `Khi thế các điều kiện biên vào Phương trình (4), ta nhận được một biểu thức rút gọn – công thức này *chỉ có hiệu lực chừng nào dòng chảy còn giữ ở chế độ chảy tầng*.`

### 2.2 Lưu ý Ngữ điệu, Lựa chọn Từ ngữ & Xử lý Mơ hồ
- **Ngữ điệu và sự trôi chảy:** Chú ý nhịp điệu, sự trôi chảy của câu văn tiếng Việt; linh hoạt tách câu dài thành hai câu ngắn hoặc nối hai câu ngắn lại khi cần.
- **Lựa chọn từ đồng nghĩa/gần nghĩa:** Cân nhắc sắc thái phù hợp nhất với ngữ cảnh và văn phong (ví dụ: `"understand"` có thể dịch là *"hiểu rõ"*, *"nắm vững"*, *"thông hiểu"*, *"thấu suốt"* tùy ngữ cảnh).
- **Tránh lặp từ/cấu trúc:** Đa dạng hóa cách diễn đạt với các cấu trúc thông thường khi tiếng Anh lặp lại nhiều lần, nhưng **bắt buộc giữ thống nhất tuyệt đối với thuật ngữ chuyên ngành**.
- **Phù hợp ngữ cảnh và giọng văn (*context & tone*):** Chọn văn phong phù hợp (trang trọng, kỹ thuật, khoa học, marketing...) và chuẩn vùng miền Việt Nam.
- **Xử lý Mơ hồ 3 cấp độ (*Ambiguity & Vagueness Resolution*):**
  1. *Mơ hồ ngôn ngữ / tham chiếu* (*Linguistic & Referential Ambiguity*) nhưng ngữ cảnh xung quanh đủ rõ $\rightarrow$ được phép khử nhập nhằng theo ngữ cảnh để câu tiếng Việt mạch lạc, rõ nghĩa.
  2. *Mơ hồ thuật ngữ chuyên môn* (*Terminological & Domain Ambiguity*) $\rightarrow$ chọn phương án có căn cứ theo đúng miền chuyên ngành, tuyệt đối không tự sáng tạo từ mới.
  3. *Mơ hồ nội dung / thiếu đặc tả nguồn* (*Source Underspecification & Epistemic Uncertainty*) $\rightarrow$ giữ nguyên mức độ bất định như bản gốc, tuyệt đối không suy diễn hay bổ sung thông tin (*No Hallucination / No Over-specification*).

---

## 3. Bản địa hóa, Đơn vị, Số liệu & Thuật ngữ

- **Quy tắc Quy đổi Kép (Imperial $\rightarrow$ Metric):**
  - Chuyển đổi sang đơn vị hệ mét chuẩn Việt Nam (miles $\rightarrow$ km, feet/inches $\rightarrow$ m/cm, lbs $\rightarrow$ kg, °F $\rightarrow$ °C) và **BẮT BUỘC giữ lại số liệu và đơn vị gốc trong ngoặc đơn** ngay phía sau để đảm bảo đối chiếu chính xác:
    - `The package weighs 5 lbs and is 10 inches long.` $\rightarrow$ `Gói hàng nặng khoảng 2,27 kg (5 lbs) và dài 25,4 cm (10 inches).`
    - `The temperature is 77°F.` $\rightarrow$ `Nhiệt độ là 25°C (77°F).`
  - **Độ chính xác khi quy đổi:** Bảo toàn mức độ chi tiết tương đương số liệu gốc (thông thường tối đa 2 chữ số thập phân, trừ tài liệu khoa học đòi hỏi độ chính xác cao).
  - **Trường hợp giữ nguyên:** Thông số thương mại tiêu chuẩn hoặc tên model (vd: `"màn hình 27 inch"`, `"ống nước phi 21"`); có thể mở ngoặc ghi chú quy đổi nếu cần (`màn hình 27 inch (khoảng 68,6 cm)`).
- **Định dạng số & Tiền tệ:**
  - Trong văn xuôi tiếng Việt: dấu chấm (`.`) phân cách hàng nghìn (`1.234.567`), dấu phẩy (`,`) làm dấu thập phân (`1.234,56`).
  - Tiền tệ đặt sau số, cách một khoảng trắng: `$1,234,567.89` $\rightarrow$ `1.234.567,89 USD` (hoặc `đô la Mỹ`), `$25.99` $\rightarrow$ `25,99 đô la Mỹ`, `£100` $\rightarrow$ `100 bảng Anh`, `€50` $\rightarrow$ `50 EUR`.
  - **CẢNH BÁO KỸ THUẬT (NGHIÊM NGẶT):** Trong **LaTeX** (`\(...\)`, `\[...\]`) và trong **Code HTML/CSS/SVG/JS** (`margin: 1.5rem`, `viewBox="0 0 10.5 20"`, `stroke-width="1.2"`), **TUYỆT ĐỐI giữ nguyên dấu chấm (`.`)** cho số thập phân.
- **Ngày tháng:** `DD/MM/YYYY` hoặc `ngày DD tháng MM năm YYYY` (`October 26, 2023` $\rightarrow$ `26/10/2023` hoặc `ngày 26 tháng 10 năm 2023`).
- **Thuật ngữ chuyên ngành (Ưu tiên #1A — Chính xác & Chuẩn hóa Học thuật):**
  - Luôn dùng thuật ngữ tiếng Việt đã chuẩn hóa và được cộng đồng học thuật Việt Nam công nhận rộng rãi (tham khảo từ điển chuyên ngành, ấn phẩm uy tín); chọn phương án phù hợp nhất với ngữ cảnh chuyên sâu. Với thuật ngữ chuyên môn sâu dễ gây nhầm lẫn (Y sinh, Cơ khí, Luật, Tài chính...), có thể mở ngoặc kèm tên tiếng Anh gốc ở lần xuất hiện đầu tiên để hỗ trợ đối chiếu (vd: *tư thế ghế bãi biển (beach chair position)*).
  - **Khi không có thuật ngữ Việt tương đương rõ ràng hoặc gây tranh cãi:** Giữ nguyên thuật ngữ tiếng Anh gốc (tránh tuyệt đối dịch *word-for-word*) và cân nhắc giải thích ngắn gọn bằng tiếng Việt ngay sau **lần xuất hiện đầu tiên** (vd: `...sử dụng phương pháp *gradient descent* (kỹ thuật tối ưu dựa trên đạo hàm)...`).
  - **Viết tắt (*Acronyms/Abbreviations*):** Lần đầu ghi đầy đủ + viết tắt (`Mạng Nơ-ron Sâu (DNN)`), các lần sau dùng `DNN`. Nếu chỉ có dạng viết tắt không định nghĩa trong bài, giữ nguyên và giải thích ngắn lần đầu nếu cần. Các từ viết tắt quốc tế phổ thông (`UNESCO`, `ASEAN`, `WHO`, `UNICEF`, `NATO`, `FBI`, `AI`, `CEO`...) giữ nguyên trực tiếp không cần dịch tên đầy đủ.
  - **Trích dẫn & Tiêu đề khoa học:** Bảo toàn nguyên vẹn trích dẫn trong câu (`[1, 3-5]`, `(Smith et al., 2021)` $\rightarrow$ `(Smith và cộng sự, 2021)`). Chuẩn hóa tiền tố: `Figure/Fig.` $\rightarrow$ `Hình`; `Table` $\rightarrow$ `Bảng`; `Equation/Eq.` $\rightarrow$ `Phương trình`.
  - **Nhất quán tuyệt đối & Danh pháp khoa học:** Một phương án thuật ngữ đã chọn phải dùng đồng bộ từ đầu đến cuối tài liệu; danh pháp khoa học Latin (loài, hợp chất...) giữ nguyên chuẩn quốc tế trừ khi có tên Việt hóa chuẩn hóa rộng rãi.
  - **Khử gạch nối ngắt dòng & Ký hiệu PDF:** Khi nối câu từ PDF, ghép liền các từ bị ngắt dòng bằng dấu gạch nối (vd: `arthro-` + `scopic` $\rightarrow$ `arthroscopic`), giữ nguyên từ ghép thực thụ; đồng thời đối chiếu kỹ ảnh trang gốc để không làm rơi/sai chữ Hy Lạp (`α`, `β`, `μ`, `Δ`), ký hiệu toán học (`±`, `≤`, `≥`) hay chỉ số hóa học (`CO₂`, `H₂O`, `Fe³⁺`).

---

## 4. Tiêu chuẩn HTML/CSS, Bảng biểu, Công thức & Tài liệu Tham khảo

### 4.1 Khung CSS Nội dung & Bảo vệ Layout Học thuật (Bắt buộc)
- **Màn hình lớn & Font chữ:** Tập trung tối ưu cao nhất cho màn hình desktop/laptop; đặt kích thước font nội dung chính dễ đọc (`18px`, tối thiểu `14px`), ưu tiên font web hiển thị tiếng Việt sắc nét (**Sans-serif:** `Noto Sans`, `Roboto`, `Open Sans`, `Lato`, `Arial`, `Verdana`; **Serif cho tiêu đề trang trọng nếu cần:** `Noto Serif`, `Lora`). Hạn chế `font-size` inline cho từng thẻ `<p>`, chỉ dùng CSS tập trung trong `<style>`.
- **Chèn đầy đủ bộ CSS nội dung dưới đây vào `<head>`:** Giữ nguyên các thuộc tính nền tảng của `body` (`max-width: 740px`, `font-size`, `line-height`), hệ biến màu (`--bg`, `--surface`, `--text`, `--muted`, `--accent`, `--border`, `--code-bg`) và `body[data-theme="sepia|dark"]`. Có thể bổ sung class phụ nếu cần, nhưng **BẮT BUỘC dùng hệ biến màu trên** thay cho màu cứng (`#000`, `#fff`...) để tương thích cả 3 giao diện Sáng / Dịu mắt / Tối, và **KHÔNG** dùng inline CSS ghi đè làm mất `max-width: 100%`, `overflow-x: auto`, `overflow-wrap: break-word`:

```css
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans:ital,wght@0,100..900;1,100..900&family=Roboto:ital,wght@0,100..900;1,100..900&display=swap');

:root {
    --bg: #fafaf9;
    --surface: #f3f2ee;
    --text: #222222;
    --muted: #555555;
    --accent: #0369a1;
    --border: #dcdad3;
    --code-bg: #efeeea;
}
body[data-theme="sepia"] {
    --bg: #f6f1e3;
    --surface: #ede5d0;
    --text: #2e261e;
    --muted: #615344;
    --accent: #8c4a1c;
    --border: #d9ceb4;
    --code-bg: #ebe2cb;
}
body[data-theme="dark"] {
    --bg: #181c22;
    --surface: #21262e;
    --text: #cdd5df;
    --muted: #98a4b3;
    --accent: #68b0ff;
    --border: #343b46;
    --code-bg: #242a33;
}

*, *::before, *::after { box-sizing: border-box; }
body {
    font-family: 'Noto Sans', Roboto, Arial, sans-serif;
    font-size: 18px;
    line-height: 1.6;
    color: var(--text);
    background-color: var(--bg);
    max-width: 740px;
    margin: 0 auto;
    padding: 20px;
    overflow-wrap: break-word;
    transition: background-color 0.2s ease, color 0.2s ease;
}
a { color: var(--accent); }
img, svg, video { max-width: 100%; height: auto; object-fit: contain; display: block; margin: 1.5rem auto; }

/* Hình ảnh & chú thích */
figure { margin: 1.8rem 0; padding: 12px; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; }
figure img { margin: 0.4rem auto 0.9rem; border-radius: 4px; }
body[data-theme="dark"] figure img { filter: brightness(0.9) contrast(1.04); }
figcaption { font-size: 0.93rem; color: var(--muted); line-height: 1.5; }

/* Bảo vệ Bảng */
.table-wrapper { width: 100%; overflow-x: auto; margin-bottom: 1.5rem; -webkit-overflow-scrolling: touch; }
table { width: 100%; border-collapse: collapse; }
th, td { border: 1px solid var(--border); padding: 10px; text-align: left; vertical-align: top; }
th { background-color: var(--surface); font-weight: bold; }
.ws-nowrap { white-space: nowrap; }

/* Bảo vệ Bố cục nhiều cột cho nội dung phụ, bổ trợ */
.grid-2col { display: grid; grid-template-columns: repeat(2, 1fr); gap: 1.5rem; align-items: start; }
.grid-3col { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.5rem; align-items: start; }
.grid-4col { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1.5rem; align-items: start; }
.grid-2col > *, .grid-3col > *, .grid-4col > * { min-width: 0; }
.flex-columns { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 1.5rem; }
.flex-column-item { flex: 1; min-width: 300px; }

/* Khối trích dẫn, ghi chú & tài liệu tham khảo */
blockquote, .callout-box { margin: 1.5rem 0; padding: 0.9rem 1.2rem; background: var(--surface); border-left: 4px solid var(--accent); border-radius: 0 6px 6px 0; }
.callout-box.is-warning { border-left-color: #d97706; }
.table-note { font-size: 0.9rem; color: var(--muted); margin: -1rem 0 1.5rem; }
ul.ref-list { list-style: none; padding-left: 0; }
ul.ref-list li { padding-left: 2em; text-indent: -2em; margin-bottom: 0.6em; }
.ref-list li, .footnotes li { overflow-wrap: anywhere; }

/* Bảo vệ Code Blocks & Text nguyên bản */
pre { background-color: var(--code-bg); padding: 15px; overflow-x: auto; border-radius: 4px; border: 1px solid var(--border); }
code { font-family: Consolas, Monaco, 'Courier New', monospace; font-size: 0.9em; background-color: var(--code-bg); padding: 2px 4px; border-radius: 3px; }
pre code { background-color: transparent; padding: 0; border: none; }

/* Tối ưu in ấn */
p, li { orphans: 3; widows: 3; }
h1, h2, h3, h4, h5, h6 { break-after: avoid; page-break-after: avoid; line-height: 1.3; margin-top: 1.5em; }
@media print {
    @page { margin: 15mm 14mm; }
    :root, body[data-theme="dark"], body[data-theme="sepia"] {
        --bg: #ffffff; --surface: #f8f9fa; --text: #000000; --muted: #444444; --border: #cccccc; --code-bg: #f4f5f7;
    }
    body { background: #ffffff !important; color: #000000 !important; max-width: 100% !important; padding: 0; }
    body[data-theme="dark"] figure img { filter: none !important; }
    figure, tr, .callout-box, blockquote, pre { break-inside: avoid; page-break-inside: avoid; }
}
```

- **Lớp vỏ tương tác bên ngoài (tự động gắn ở Bước 4):** Không cần tự viết thanh nút chuyển giao diện, mục lục tự động hay hộp phóng to ảnh trong `work\draft.html`. Công cụ `html_packager.ps1` sẽ tự động bơm CSS/HTML/JS của lớp vỏ (`tools\reader_shell.html`, dùng tiền tố `rsfv-*` tách biệt hoàn toàn) dựa trên bộ biến màu ở trên và các thẻ ngữ nghĩa chuẩn (`<header>`, `<h1>`–`<h3>`, `<figure><img><figcaption>`).

### 4.2 Quy tắc Bố cục, Chất lượng Mã HTML/CSS & Truy cập (W3C & WCAG)
- **Mã sạch, hợp chuẩn W3C & Ngữ nghĩa:** Viết mã tinh gọn, loại bỏ thẻ/CSS lặp thừa; đủ thẻ đóng/mở và lồng thẻ đúng chuẩn; dùng `<article>`, `<section>`, `<header>`, `<footer>`, `<aside>`, `<figure>`, `<figcaption>`, `<h1>`–`<h6>`.
- **Luồng 1 cột duy nhất:** Mọi bài báo/luận văn/tài liệu dài chia 2–3 cột trên PDF **BẮT BUỘC gộp thành 1 cột**.
- **Ngoại lệ nội dung phụ/bổ trợ:** Nếu tài liệu gốc đã là 1 cột và chỉ có một phần nội dung phụ chia 2–3 cột, giữ nguyên số cột cho riêng phần đó bằng `.grid-2col`, `.grid-3col`, `.flex-columns` (không tự ý đổi số cột làm nát không gian); nếu có nguy cơ chữ lấn đè nhau thì bắt buộc gộp về 1 cột.
- **Header/Footer lặp & Chú thích cuối trang (`Footnotes`):** Nhận diện và loại bỏ/gom nhóm hợp lý các header/footer chèn ngang làm đứt gãy đoạn văn gốc; tách chú thích cuối trang ra khỏi giữa đoạn văn đang dở để gom về cuối `<section>` hoặc cuối bài (`<aside class="footnotes">` / `<ol>`) nhằm bảo toàn tính liên tục, chỉ giữ header/footer mang nội dung thực.
- **Bảng biểu (`<table>`):** Mọi `<table>` **BẮT BUỘC** bọc trong `<div class="table-wrapper">`, dùng đầy đủ `<thead>`, `<tbody>`, `<tr>`, `<th scope="col|row">`, `<td>`, áp dụng `class="ws-nowrap"` cho các ô chứa số liệu, mã số, ngày tháng ngắn để ép thanh cuộn ngang thay vì bóp rớt dòng. Nếu bảng có ghi chú ký hiệu (`*`, `†`, `a, b`), đặt gọn trong `<tfoot>` hoặc `<p class="table-note">` ngay bên dưới `.table-wrapper`. Có thể đơn giản hóa bảng quá rối, hoặc chuyển sang danh sách (`<ul>`, `<ol>`) / thẻ `<p>` có cấu trúc nếu bảng gộp ô chồng chéo gây nguy cơ vỡ HTML, miễn bảo toàn mối liên hệ logic dữ liệu.

### 4.3 Hình ảnh & Sơ đồ
- **Tuyệt đối không bỏ sót ảnh nào** từ `work/assets/manifest.json` (`assets/fig_pX_Y.png`), đặt đúng vị trí ngữ cảnh trong `<figure>` kèm `alt` tiếng Việt mô tả rõ nội dung/mục đích (ảnh trang trí thuần túy dùng `alt=""`).
- **Tiêu chí đánh giá độc lập từng sơ đồ/biểu đồ chứa text:**
  - Việc quyết định sơ đồ A tái tạo bằng HTML/CSS còn sơ đồ B giữ nguyên ảnh gốc là hoàn toàn hợp lệ — đánh giá độc lập theo từng ảnh cụ thể.
  - Nếu tái tạo bằng HTML/CSS mà không vỡ bố cục và bảo toàn thông tin cốt lõi tương đương ảnh gốc $\rightarrow$ **nỗ lực tối đa để tái tạo**, dịch text trong hình và dùng CSS định vị khéo léo, linh hoạt (chỉnh `font-size` nếu cần, dùng biến CSS theo theme) sao cho không tràn hay che khuất thông tin quan trọng. Tuyệt đối không tự bịa số liệu hay lược bớt nhãn chữ khi tái tạo.
  - Ngược lại, nếu việc tái tạo dễ vỡ bố cục hoặc không thể truyền tải tương đương $\rightarrow$ **giữ nguyên ảnh gốc** (`<img src="assets/fig_pX_Y.png" alt="...">`) và dịch đầy đủ nhãn chú thích trong `<figcaption>`.

### 4.4 Công thức Toán học (MathJax + LaTeX)
- **Khi tài liệu có biểu thức/công thức toán học:**
  - Chèn vào `<head>`:
    ```html
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    ```
  - Dùng `\( ... \)` cho công thức cùng dòng (*inline math*) và `\[ ... \]` cho công thức đứng riêng (*block math*); dùng môi trường LaTeX (`\begin{bmatrix}...\end{bmatrix}`) cho ma trận — **TUYỆT ĐỐI KHÔNG** dùng `<sup>`/`<sub>` hay `<table>` giả lập công thức/ma trận, **KHÔNG** bọc LaTeX trong `<code>` hay `<pre>`.
  - Dịch điều kiện chữ tiếng Anh bên trong công thức và bọc bằng `\text{...}` (vd: `\{n : n \text{ is a prime number}\}` $\rightarrow$ `\( \{n : n \text{ là số nguyên tố}\} \)`). **TUYỆT ĐỐI giữ dấu chấm (`.`)** cho số thập phân bên trong LaTeX.

### 4.5 Tài liệu Tham khảo (`References` / `Bibliography`)
- Bảo toàn tuyệt đối tính nguyên vẹn và khả năng truy xuất: **KHÔNG DỊCH** tên tác giả, năm xuất bản, tiêu đề bài báo/sách/luận văn/báo cáo, tên tạp chí/hội nghị/NXB, tập/số/trang, DOI/ISBN/ISSN/PMID, URLs.
- Chỉ dịch phần **ghi chú/mô tả bình luận thêm** do *chính tác giả tài liệu gốc* viết (nếu có).
- Giữ nguyên danh sách (`<ul>`/`<ol>` + `<li>`), tái tạo chính xác định dạng `<strong>`/`<em>` như gốc, chuyển mọi **URL / DOI** thành liên kết `<a href="..." target="_blank" rel="noopener">` nhấp được, và cố gắng giữ trình bày trực quan (dùng `ul.ref-list` nếu cần thụt lề dòng thứ hai kiểu *hanging indent*) nếu không ảnh hưởng khả năng đọc.

---

## 5. Tự Kiểm định Nội bộ (Internal QA) trước khi Đóng gói
Trước khi chạy `EmbedImages ... -AlsoPdf`, rà lại `work\draft.html`:
1. Văn phong tiếng Việt có trôi chảy, thoát ly trật tự từ tiếng Anh nhưng bảo toàn nguyên vẹn khẳng định/nhân quả/hedging/ngôi xưng/thuật ngữ nhất quán, đã khử gạch nối ngắt dòng PDF (`esti- mation`) và giữ đúng chữ Hy Lạp/chỉ số khoa học chưa?
2. Đã gom đúng vị trí cho chú thích cuối trang (`Footnotes`) và ghi chú bảng (`Table Notes`), không làm đứt đoạn văn và không bỏ sót ảnh nào từ `manifest.json`?
3. Mã HTML sạch, hợp chuẩn W3C (`<!DOCTYPE html>` ... `</html>`), giữ nguyên thuộc tính nền tảng của `body` và hệ biến màu tương thích cả 3 giao diện (`light`/`sepia`/`dark` — không gán màu cứng làm hỏng chế độ Tối), có đủ `<head>...</head>` và `<body>...</body>` kèm thẻ ngữ nghĩa chuẩn (`<header>`, `<h1>`–`<h3>`, `<figure><img><figcaption>`), mọi `<table>` nằm trong `<div class="table-wrapper">` kèm `scope`, không thiếu `alt` cho `<img>`, có MathJax `<script>` nếu bài dùng LaTeX, và không bị tràn ngang?
