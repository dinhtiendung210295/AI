---
name: skill-format
description: trình bày SKILL.md theo format bảng Task, Input, Element, Output và Guidelines and Tools
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
- Ô input, output chỉ có đúng 1 object ngắn gọn dưới 5 chữ
- Dùng tên task nhất quán giữa bảng và tiêu đề chi tiết.

Mỗi task phải có phần chi tiết theo cấu trúc:

```markdown
## <Task>

### Input

- ...

### Elements

- ...



### Output

- ...


```


