# Third-Party Licenses & Notices

Mã nguồn gốc của dự án **luka-loop** (bao gồm `AGENTS.md`, thư mục `.agents/skills/`, các script PowerShell trong `tools/`, `tools/reader_shell.html` và bộ mã nguồn tham chiếu trong `tools/src/`) được phát hành theo [MIT License](./LICENSE).

Tuy nhiên, gói công cụ thực thi dựng sẵn dành cho Windows (`tools/extract_assets/`, được biên dịch tự động trên GitHub Actions và phân phối kèm trong gói phát hành Release `luka-loop-win-x64.zip`) chứa các thư viện và tệp nhị phân của bên thứ ba dưới các giấy phép riêng biệt sau đây:

## Tổng hợp thành phần bên thứ ba trong `tools/extract_assets/`

| Thành phần | Tệp tiêu biểu trong repo | Chủ sở hữu / Nguồn | Giấy phép | Toàn văn giấy phép |
| :--- | :--- | :--- | :--- | :--- |
| **PyMuPDF / MuPDF** | `_internal/pymupdf/mupdfcpp64.dll`, `_mupdf.pyd`, `_extra.pyd` | Artifex Software, Inc. | **AGPL-3.0** | [licenses/AGPL-3.0.txt](./licenses/AGPL-3.0.txt) |
| **Python 3.12.7** | `_internal/python312.dll`, `python3.dll`, `base_library.zip`, `*.pyd` | Python Software Foundation | **PSF-2.0** | [licenses/PSF-2.0.txt](./licenses/PSF-2.0.txt) |
| **OpenSSL 3.0.15** | `_internal/libcrypto-3.dll` | The OpenSSL Authors | **Apache-2.0** | [licenses/Apache-2.0.txt](./licenses/Apache-2.0.txt) |
| **PyInstaller** | Bootloader của `extract_assets.exe` & runtime hooks | PyInstaller Development Team | **GPL-2.0-or-later** (kèm Bootloader Exception) & **Apache-2.0** | [licenses/PyInstaller-COPYING.txt](./licenses/PyInstaller-COPYING.txt) |
| **Microsoft Visual C++ Runtime & UCRT** | `MSVCP140.dll`, `VCRUNTIME140.dll`, `VCRUNTIME140_1.dll`, `ucrtbase.dll`, `api-ms-win-*.dll` | Microsoft Corporation | Microsoft Runtime Redistribution Terms | Xem thông báo bên dưới |

---

## Thông báo chi tiết theo từng thành phần

### 1. PyMuPDF / MuPDF (GNU Affero General Public License v3.0 — AGPL-3.0)
- Gói thực thi `tools/extract_assets/extract_assets.exe` (tự động build từ [`tools/build_extractor.ps1`](./tools/build_extractor.ps1)) được biên dịch liên kết trực tiếp với thư viện **PyMuPDF / MuPDF**, do đó bản phân phối nhị phân kết hợp tuân theo các điều khoản của **AGPL-3.0**.
- Toàn bộ mã nguồn phía ứng dụng dùng để tạo `extract_assets.exe` được công khai đầy đủ tại [`tools/src/`](./tools/src/) ([`extract_assets.py`](./tools/src/extract_assets.py), [`html_packager_core.py`](./tools/src/html_packager_core.py), [`path_guards.py`](./tools/src/path_guards.py)). Mã nguồn thượng nguồn của PyMuPDF và MuPDF được cung cấp công khai bởi Artifex Software tại <https://github.com/pymupdf/PyMuPDF> và <https://mupdf.com/>.
- Toàn văn giấy phép xem tại [`licenses/AGPL-3.0.txt`](./licenses/AGPL-3.0.txt).

### 2. Python 3.12.7 (Python Software Foundation License Version 2)
```text
This distribution incorporates Python 3.12.7.
Python is Copyright (c) 2001-2024 Python Software Foundation; All Rights Reserved.
Licensed under the Python Software Foundation License Version 2 (PSF-2.0).
```
- Toàn văn giấy phép xem tại [`licenses/PSF-2.0.txt`](./licenses/PSF-2.0.txt).

### 3. OpenSSL 3.0.15 (Apache License 2.0)
```text
This product includes cryptographic software written by the OpenSSL Project
for use in the OpenSSL Toolkit (https://www.openssl.org/).
Copyright 1998-2024 The OpenSSL Authors. All rights reserved.
OpenSSL 3.0.15 (libcrypto-3.dll) is licensed under the Apache License, Version 2.0.
```
- Toàn văn giấy phép xem tại [`licenses/Apache-2.0.txt`](./licenses/Apache-2.0.txt).

### 4. PyInstaller (GPL-2.0-or-later với Bootloader Exception & Apache-2.0)
- `extract_assets.exe` sử dụng bootloader của **PyInstaller**, được phân phối kèm ngoại lệ *Bootloader Exception* (cho phép kết hợp với mã nguồn khác) và các runtime hook theo Apache-2.0.
- Toàn văn điều khoản xem tại [`licenses/PyInstaller-COPYING.txt`](./licenses/PyInstaller-COPYING.txt).

### 5. Microsoft Visual C++ Runtime & Universal CRT
- Các tệp `MSVCP140.dll`, `VCRUNTIME140.dll`, `VCRUNTIME140_1.dll`, `ucrtbase.dll` và bộ `api-ms-win-crt-*.dll` / `api-ms-win-core-*.dll` mang bản quyền `© Microsoft Corporation. All rights reserved.` và chỉ được đóng gói lại như thành phần runtime phụ trợ đi kèm bản dựng Python portable trên Windows.

---

## Tài nguyên tải qua CDN khi xem HTML (tùy chọn phía trình duyệt)
Các tệp HTML đầu ra có thể tham chiếu tới tài nguyên công cộng qua Internet (không đóng gói nhị phân trong repo):
- **MathJax 3** (tải từ `cdn.jsdelivr.net` khi tài liệu có công thức toán học): **Apache License 2.0**.
- **Google Fonts — Noto Sans & Roboto** (tải từ `fonts.googleapis.com`): **SIL Open Font License 1.1** (`Noto Sans`) và **Apache License 2.0** (`Roboto`).
