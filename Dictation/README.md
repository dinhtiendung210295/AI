# Dictation — ChatGPT voice input for Windows

Giữ **Ctrl + `** để nói, thả để lấy bản chép từ ChatGPT, copy clipboard và tự
dán vào ứng dụng đang nhập. Dùng một tab riêng trong group **🎙 Dictation**;
không cần OpenCode, Wispr Flow hay GPU local.

Đây là bản thử nghiệm điều khiển giao diện web ChatGPT, không phải sản phẩm/API
chính thức của OpenAI. Giao diện thay đổi có thể làm extension ngừng hoạt động.

## Yêu cầu

- Windows x64, Python 3.11+ (có Python Launcher `py`), Google Chrome.
- Tài khoản ChatGPT có dictation, mạng và micro được Chrome cho phép.
- Không cần quyền admin. Không tắt bảo mật hoặc thay PowerShell execution policy.

## Cài đặt

1. Chạy `setup.cmd` để tạo `.venv` và cài dependencies.
2. Chrome → `chrome://extensions` → Developer mode → Load unpacked → chọn
   thư mục `Dictation/extension`.
3. Copy **ID extension** ở trang đó. Chạy `register-windows.cmd`, dán ID vào.
   Mỗi máy/đường dẫn có thể có ID khác, không dùng ID của người khác.
4. Mở ChatGPT và tự đăng nhập trong Chrome bình thường. Không dùng Chrome do
   Playwright mở để đăng nhập Google.
5. Mở extension → **Bật Ctrl + ` toàn Windows**. Extension tạo tab riêng trong
   group tím **🎙 Dictation**. Nếu cần, mở tab đó và cho phép micro.
6. Đóng popup, click vào ô nhập của ứng dụng đích. Giữ **Ctrl + `**, nói, rồi
   thả một trong hai phím. Giữ nguyên ô nhập trong lúc chờ nhận dạng.

Khi có chữ, công cụ thay clipboard, thử gửi Ctrl+V tới đích đã xác minh, rồi xóa
ô nhập ChatGPT. Không tự nhấn Enter hay gửi tin nhắn ChatGPT. Nếu không xác minh
được đích hoặc focus đổi, chỉ copy — bạn có thể Ctrl+V thủ công.

Có thể dùng nút Bắt đầu/Dừng trong popup. Nút **Copy bản chép & xóa ô ChatGPT**
copy kết quả trước rồi xóa ô ChatGPT, kể cả nội dung ô đã được chỉnh sửa. Nếu
copy thất bại thì không xóa. Không dùng tab Dictation để soạn chat quan trọng.

## Giới hạn và quyền riêng tư

- Audio được gửi tới ChatGPT bằng tài khoản đã đăng nhập; không xử lý local GPU.
- Không lưu audio/transcript vào log. Native host nhận bản chữ trong RAM để copy.
- Clipboard cũ bị thay thế, không khôi phục. Kiểm tra trước khi dùng nội dung nhạy cảm.
- Chỉ hỗ trợ nhãn nút tiếng Anh đã kiểm chứng. Tốc độ/phạm vi dùng phụ thuộc ChatGPT.
- Edit control qua UI Automation hoặc Win32 được hỗ trợ theo provider; không bảo
  đảm mọi editor, trường mật khẩu hoặc ứng dụng elevated. Không tự nâng quyền.
- Kiểm tra focus/caret giảm nguy cơ dán nhầm nhưng không loại bỏ hoàn toàn race
  giữa kiểm tra và SendInput. Không dùng cho trường nhạy cảm.
- Ctrl+backtick có thể trùng phím tắt khác. Không chạy helper cũ cùng lúc.
- Tab group không phải profile riêng; các tab vẫn chung tài khoản/storage. Nếu
  website đồng bộ bản nháp giữa tab, group không ngăn được việc đó.
- Đóng popup không ngắt thu. Dùng Hủy; nếu không được, đóng tab Dictation để
  ngắt micro. Timer tab nền có thể bị Chrome trì hoãn.

Extension dùng `nativeMessaging`, `scripting`, `activeTab`, `storage`, `tabGroups`
và quyền host chỉ `https://chatgpt.com/*`. Không đọc cookie/password hay gọi API
nội bộ. Native Messaging đăng ký dưới HKCU, chỉ cho extension ID bạn cung cấp;
không mở HTTP port hay tự khởi động cùng Windows.

## Tắt / gỡ / cập nhật

- Bấm **Tắt** trong popup để nhả phím tắt Windows. Đóng Chrome cũng ngắt host.
- Chạy `unregister-windows.cmd` rồi gỡ extension để bỏ đăng ký cầu nối. Không tự
  xóa profile Chrome hay bản nháp. Trình gỡ từ chối nếu key thuộc đường dẫn khác.
- Khi đổi đường dẫn thư mục hoặc ID extension: gỡ đăng ký từ bản cũ trước, rồi
  đăng ký bản mới. Không chạy hai bản cùng lúc.
- Sửa extension → Reload ở `chrome://extensions`, tải lại tab sau khi lưu bản nháp.
  Sửa native host → Tắt/Bật cầu nối. Xem dòng trạng thái Windows trong popup.

## Kiểm thử logic (không dùng micro)

```powershell
node extension/test.cjs
node extension/test-background.cjs
```

Các bài test dùng DOM/native-message giả lập, không chứng minh độ chính xác
nhận dạng hay paste thực tế. Bản 0.3.0 đã được người dùng thử trên máy phát triển;
cần kiểm tra lại trên máy/Chrome/editor khác.

Thư mục này chỉ chứa bản extension/native host hiện tại, không chứa các prototype
Playwright, profile đăng nhập, môi trường Python hay dữ liệu chẩn đoán cá nhân.
