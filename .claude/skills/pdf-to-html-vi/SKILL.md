---
name: pdf-to-html-vi
description: >-
  Quy trình dịch thuật file PDF sang một tệp HTML tiếng Việt duy nhất (tất cả trong một / self-contained files), tự động tách ảnh kèm bản đồ chú thích bằng `extract_assets.exe` (PyMuPDF portable). Kích hoạt ngay khi người dùng gửi PDF và yêu cầu dịch sang tiếng Việt.
---

# `pdf-to-html-vi` — lối vào cho Claude Code

Quy trình gốc dùng chung cho mọi agent nằm ở [`.agents/skills/pdf-to-html-vi/SKILL.md`](../../../.agents/skills/pdf-to-html-vi/SKILL.md). Tệp này chỉ giúp Claude Code tìm thấy skill (Claude Code không đọc thư mục `.agents/`).

1. Đọc trọn `.agents/skills/pdf-to-html-vi/SKILL.md` và làm theo **đúng từng bước** trong đó. Các liên kết tương đối trong tệp đó (vd `./si_*.md`) tính từ thư mục `.agents/skills/pdf-to-html-vi/`.
2. Áp dụng thêm [`.agents/adapters/claude-code.md`](../../../.agents/adapters/claude-code.md) (đã được nạp qua `CLAUDE.md`; nếu chưa có trong ngữ cảnh thì đọc tệp này trước).
