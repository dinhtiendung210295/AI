---
name: skill-format
description: trình bày SKILL.md theo format bảng Task, Input, Element, Output
---

# Skill Format


## Phối hợp skill

- Dùng `$skill-creator` cùng skill này.
- `$skill-creator` quản lý chất lượng chung, phạm vi, frontmatter, resources và validation.
- `$skill-format` quản lý format riêng của FC+TC.


## Format bắt buộc

Đặt bảng tóm tắt ngay dưới tiêu đề cấp một của skill:

```markdown
| Task | Input  | Output | 
| --- | --- | ---| --- |
|<số task>.<Task> | <Input> | <Output> | 
```

- Mỗi task có đúng một dòng trong bảng
- Ô input chỉ có đúng 1 ý ngắn gọn dưới 5 chữ, ô output cũng vậy
- Dùng tên task nhất quán giữa bảng và tiêu đề chi tiết.

Mỗi task phải có phần chi tiết theo cấu trúc:

```markdown
## <Task>

- ... dùng ref ... và script ...
- ... output theo format ...
```

General Skill template: https://github.com/Leeaoyin/dr-agent-skills/blob/main/README.md?utm_source=chatgpt.com#recommended-skill-template

Workflow-Based: https://github.com/anthropics/knowledge-work-plugins/blob/main/product-management/skills/roadmap-update/SKILL.md?utm_source=chatgpt.com
Task-Based: https://github.com/anthropics/skills/blob/main/skills/pdf/SKILL.md?utm_source=chatgpt.com
Reference/Guidelines: https://github.com/anthropics/skills/blob/main/skills/brand-guidelines/SKILL.md?utm_source=chatgpt.com
Capabilities-Based: https://github.com/anthropics/knowledge-work-plugins/blob/main/product-management/skills/product-brainstorming/SKILL.md?utm_source=chatgpt.com




```


