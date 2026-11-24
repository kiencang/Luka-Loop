# Lịch sử chất lượng tách hình

Chất lượng của bộ tách hình (`extract_assets.exe`) qua từng bản phát hành, đo trên **14.117 trang khoa học của DocLayNet** (tune 9.881 · holdout 2.349 · val 944 · test 943; 5.259 hình có nhãn) bằng `dev/eval_doclaynet.py`. Mọi dòng được chấm lại bằng **cùng một bộ chấm** (bản hiện tại), nên các dòng so sánh trực tiếp được với nhau. Cách chạy và chi tiết bộ chấm: mục *Đánh giá bộ tách hình trên DocLayNet* trong [DEVELOPMENT.md](DEVELOPMENT.md).

## Cách tính

Mỗi hình có nhãn `Picture` của DocLayNet được so với các ảnh công cụ xuất ra (đã nới lề 4 pt, đúng như ảnh thật):

- **Bỏ sót:** các ảnh xuất ra phủ dưới 50% diện tích hình.
- **Bị cắt nặng:** từ 3 ô chữ của hình trở lên (nhãn trục, số chia, chú giải) nằm ngoài ảnh và có mực thật ở chỗ đó, hoặc hình bị cắt mất hơn 10% diện tích.
- **Bị cắt nhẹ:** chỉ 1–2 ô chữ nằm ngoài ảnh, thường là nhãn panel kiểu "(a)". Không tính là lỗi nặng.
- **Hình đúng:** hình không bị bỏ sót và không bị cắt, kể cả cắt nhẹ; nghĩa là ảnh xuất ra chứa trọn hình và đủ chữ của hình. Bốn cột *hình đúng + cắt nặng + cắt nhẹ + bỏ sót* cộng lại đúng 5.259 hình (vd v1.1.25: 4.682 + 362 + 114 + 101).
- **Ảnh dính chữ:** số ảnh xuất ra có chữ của nội dung khác (chú thích, đoạn văn, công thức, bảng, tiêu đề trang…) lọt vào. Đếm theo ảnh xuất ra, không theo hình có nhãn, nên không cộng vào 5.259.
- **Gộp lệch:** ảnh vừa bao nhiều hình vừa dính chữ (đã nằm trong cột *ảnh dính chữ*). Ảnh bao nhiều hình mà không dính chữ thì chấp nhận được.
- **Trang lỗi nặng:** trang có ít nhất một hình bị bỏ sót hoặc cắt nặng, hoặc một ảnh dính chữ.

Trang scan: cả tập chỉ có **1 trang** bị công cụ nhận là trang scan (thuộc tune, có 1 hình). Với trang scan, công cụ không tách hình mà để agent render cả trang, nên hình đó luôn bị tính là *bỏ sót* ở mọi bản; mức ảnh hưởng 1/5.259 hình, như nhau giữa các dòng.

Mỗi lần phát hành thêm một dòng. Các bản cùng mã tách hình (chỉ khác tài liệu, skill hay đóng gói) gộp chung một dòng. Bản trước v1.1.13 không được đo (cấu trúc mã cũ, công cụ đo chưa có).

## Tổng hợp 4 tập

| Bản | Hình đúng | Bị cắt nặng | Bị cắt nhẹ | Bỏ sót | Ảnh dính chữ | Gộp lệch | Trang lỗi nặng | F1 (IoU ≥ 0,5) ² | Giây/trang ¹ |
|---|---|---|---|---|---|---|---|---|---|
| v1.1.13 | 4.146 (78,8%) | 733 | 245 | 135 | 206 | 11 | 948 | 88,1% | 0,32 |
| v1.1.14 – v1.1.21 | 4.530 (86,1%) | 484 | 123 | 122 | 218 | 9 | 711 | 88,5% | 0,43 |
| v1.1.22 | 4.533 (86,2%) | 488 | 125 | 113 | 214 | 9 | 706 | 88,6% | 0,43 |
| v1.1.23 | 4.533 (86,2%) | 488 | 125 | 113 | 214 | 9 | 706 | 88,6% | 0,49 |
| v1.1.24 | 4.679 (89,0%) | 364 | 114 | 102 | 220 | 9 | 601 | 88,9% | 0,51 |
| v1.1.25 | 4.682 (89,0%) | 362 | 114 | 101 | 220 | 9 | 598 | 89,0% | 0,35 |
| v1.1.26 | 4.682 (89,0%) | 362 | 114 | 101 | 214 | 9 | 593 | 89,0% | 0,35 |
| v1.1.27 | 4.698 (89,3%) | 357 | 115 | 89 | 215 | 9 | 578 | 89,1% | 0,36 |

¹ **Tốc độ chỉ mang tính tương đối:** phụ thuộc cấu hình máy và điều kiện lúc đo (số tiến trình song song, máy có đang chạy việc khác không). Các lần đo v1.1.23 và v1.1.24 chạy khi máy đang bận việc khác. Đừng so tốc độ giữa các dòng như số liệu chính xác.

² **F1 theo quy ước so khớp của DocLayNet**, chỉ để tham khảo: một khung tách ra được tính là trúng khi trùng ít nhất 50% (IoU ≥ 0,5) với khung hình có nhãn, mỗi khung có nhãn chỉ ghép với một khung tách ra. Chỉ số chuẩn của DocLayNet là mAP, cần điểm tin cậy cho từng khung, mà công cụ không có, nên dùng F1 thay thế. Cột này không phân biệt hình bị cắt mất chữ hay không (IoU vẫn cao khi chỉ hụt một dòng nhãn), vì thế tăng chậm hơn nhiều so với *Hình đúng*.

## Theo từng tập (hình đúng · trang lỗi nặng)

| Bản | tune | holdout | val | test |
|---|---|---|---|---|
| v1.1.13 | 2.802 · 664 | 744 · 181 | 311 · 52 | 289 · 51 |
| v1.1.14 – v1.1.21 | 3.082 · 505 | 794 · 138 | 342 · 24 | 312 · 44 |
| v1.1.22 | 3.085 · 502 | 794 · 138 | 342 · 24 | 312 · 42 |
| v1.1.23 | 3.085 · 502 | 794 · 138 | 342 · 24 | 312 · 42 |
| v1.1.24 | 3.183 · 426 | 832 · 117 | 348 · 22 | 316 · 36 |
| v1.1.25 | 3.183 · 426 | 835 · 114 | 348 · 22 | 316 · 36 |
| v1.1.26 | 3.183 · 423 | 835 · 112 | 348 · 22 | 316 · 36 |
| v1.1.27 | 3.199 · 408 | 835 · 112 | 348 · 22 | 316 · 36 |

## Nguồn số liệu

| Bản | Commit | Ngày | Dấu vân tay bộ tách hình |
|---|---|---|---|
| v1.1.13 | `75ed129` | 2026-11-21 | `98b5395668dac5a6` |
| v1.1.14 – v1.1.21 | `f9f6a64 … cce9a53` | 2026-11-21 → 22 | `37db5525b514bdce` |
| v1.1.22 | `9dfd3d9` | 2026-11-22 | `6db9a28ce1f91666` |
| v1.1.23 | `7313092` | 2026-11-23 | `13561b2b28e39bf7` |
| v1.1.24 | `f2883a9` | 2026-11-24 | `42d47d183f852106` |
| v1.1.25 | `61c61d4` | 2026-11-24 | `e05cece7d0df4c2c` |
| v1.1.26 | `8d92c1a` | 2026-11-24 | `172519787d7789f6` |
| v1.1.27 | `b3b1347` | 2026-11-25 | `c412ca96d270a58f` |

Dấu vân tay là mã băm của `tools/src/figure_detector/*.py` và `tools/src/image_ops.py`; kết quả từng trang nằm trong `%TEMP%\luka_doclaynet_eval\pages\<dấu vân tay>.jsonl` (bộ đệm cục bộ, có thể bị xóa).

## Ghi chú theo bản

- **v1.1.14:** nhảy vọt so với v1.1.13 (+384 hình đúng, trang lỗi nặng 948 → 711). Đây không phải lần đầu dùng luật riêng (bộ tách đã có luật riêng từ v1.0.0, viết lại 6 pha ở v1.1.5, tinh chỉnh theo DocLayNet ở v1.1.7), mà là lần đầu có bộ chấm mức độ lỗi, nhờ đó sửa trúng hai lỗi phổ biến nhất: gắn nhãn trục theo từng dòng và cắt lề trắng của ảnh raster.
- **v1.1.23:** giống hệt v1.1.22 trên cả 14.117 trang. Bản này sửa lỗi dính tiêu đề chạy, mà mỗi trang DocLayNet là một tệp PDF một trang riêng, nên không có nhiều trang để nhận ra tiêu đề lặp lại; cải tiến được đo bằng `dev/header-pdf` (dính tiêu đề 18 → 0).
- **v1.1.24:** luật cứu mảnh vector quá nhỏ (+146 hình đúng).
- **v1.1.25:** giới hạn 30 giây/trang và tăng tốc các trang chậm; 7 trang đổi, đều tốt hơn. Đo không bật giới hạn thời gian.
- **v1.1.26:** bước gắn nhãn không vượt khe giữa hai cột chữ; 9 trang đổi (tune 6, holdout 3), đều tốt hơn: ảnh dính chữ 220 → 214, trang lỗi nặng 598 → 593.
- **v1.1.27:** bộ đếm đường cong tính cả đường gấp khúc gồm nhiều đoạn chéo li ti, nên biểu đồ đường không còn bị luật nhận bảng loại; 21 trang đổi (tune 20, holdout 1), bỏ sót 101 → 89; chấm mù AB7 bản mới thắng 14/14.
