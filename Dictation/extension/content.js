(() => {
  if (window.__localDictationTrial) return;
  window.__localDictationTrial = true;
  let state = "idle", status = "Sẵn sàng. Chưa bật micro.", text = "";
  let deadline, timeout, observer;
  let windowsBridge = false;
  const visible = e => !!e.getClientRects().length;
  const aliases = {
    "Start dictation": ["Start dictation", "Dictate"],
    "Submit dictation": ["Submit dictation", "Stop dictation", "Confirm dictation", "Finish dictation", "Send dictation"],
  };
  const button = label => [...document.querySelectorAll("button")].find(e =>
    visible(e) && !e.disabled && (aliases[label] || [label]).some(name =>
      e.getAttribute("aria-label") === name || e.textContent.trim() === name));
  const composer = () => [...new Set([...document.querySelectorAll('textarea, [contenteditable="true"], [role="textbox"]')]
    .filter(visible).map(e => (typeof e.value === "string" ? e.value : e.innerText || "").trim()).filter(Boolean))].join("\n");
  const snapshot = () => ({ state, status, text, controls: [...document.querySelectorAll('button')].filter(visible)
    .map(e => e.getAttribute('aria-label') || e.getAttribute('title') || '').filter(Boolean).slice(-16) });
  function clear() { clearTimeout(deadline); clearTimeout(timeout); observer?.disconnect(); observer = undefined; }
  function cancel() {
    const cancelButton = button("Cancel dictation");
    if (cancelButton) {
      cancelButton.click();
      clear(); state = "idle"; status = "Đã bấm Cancel dictation; không gửi tin nhắn.";
    } else if (state === "recording" || state === "processing") {
      status = "Không thấy nút hủy. Hãy đóng tab ChatGPT để bảo đảm ngắt micro; không tự tải lại hay gửi chat.";
    }
  }
  function check() {
    if (state !== "processing") return;
    const value = composer();
    if (value && button("Start dictation") && !button("Submit dictation") && !button("Stop recording")) {
      clear(); text = value; state = "done"; status = "Đã lấy chữ. Chưa gửi ChatGPT, chưa tự dán.";
      notify(snapshot());
    }
  }
  function handle(message, respond) {
    try {
      if (message.action === "status") {
        // Background-tab timers/MutationObserver can be throttled by Chrome.
        // Each explicit bridge poll must re-read the actual composer state.
        check();
      } else if (message.action === "windowsMode") {
        windowsBridge = !!message.enabled;
      } else if (message.action === "start") {
        if (state === "recording" || state === "processing") throw new Error("Đang có một lượt dictation. Dừng hoặc Hủy trước.");
        if (button("Log in")) throw new Error("Hãy đăng nhập ChatGPT trực tiếp trước. Extension không xử lý mật khẩu.");
        if (composer()) throw new Error("Ô nhập đang có bản nháp. Hãy xử lý bản nháp trước; extension không tự xóa.");
        const start = button("Start dictation");
        if (!start) throw new Error("Không thấy Start dictation; kiểm tra tab ChatGPT.");
        clear(); text = ""; start.click(); state = "recording";
        status = "Đã bấm Start dictation. Cấp quyền micro nếu Chrome hỏi; kiểm tra trang thực sự đang thu trước khi nói.";
        deadline = setTimeout(() => { cancel(); status += " Đã đạt giới hạn 90 giây."; }, 90000);
      } else if (message.action === "stop") {
        if (state !== "recording") throw new Error("Chưa có lượt thu đang chạy.");
        // Submit dictation is NOT the Send message button. No fallback to generic Submit.
        const submit = button("Submit dictation");
        if (!submit) {
          const labels = [...document.querySelectorAll('button')].filter(visible)
            .map(e => e.getAttribute('aria-label') || e.getAttribute('title') || '')
            .filter(Boolean).slice(-16);
          throw new Error("Chưa nhận ra nút hoàn tất. KHÔNG phải lỗi quyền micro. Nhãn nút đang có: " + labels.join(' | ') + ". Nếu vẫn đang thu, bấm dấu × trên thanh ghi âm để ngắt.");
        }
        state = "processing";
        status = "Đang đợi bản chép. Có thể đóng popup rồi mở lại trên tab này; không bấm gửi chat.";
        observer = new MutationObserver(check);
        observer.observe(document.documentElement, { subtree: true, childList: true, attributes: true, characterData: true });
        submit.click();
        // Input properties may change without DOM mutation. This interval ends after 30s.
        const started = performance.now();
        const poll = () => {
          check();
          if (state !== "processing") return;
          if (performance.now() - started >= 30000) {
            observer?.disconnect();
            status = "Sau 30 giây chưa có bản chép. Hãy kiểm tra lỗi trên trang ChatGPT. Có thể Hủy hoặc đóng tab để ngắt micro.";
            return;
          }
          timeout = setTimeout(poll, 250);
        };
        timeout = setTimeout(poll, 250);
      } else if (message.action === "clearCopied") {
        if (state !== "done" || !text || message.copied !== text) {
          throw new Error("Đã copy, nhưng không xóa: bản chép không còn khớp lượt đã hoàn tất.");
        }
        const editors = [...document.querySelectorAll('textarea, [contenteditable="true"], [role="textbox"]')]
          .filter(visible).filter(e => (typeof e.value === 'string' ? e.value : e.innerText || '').trim());
        if (editors.length === 0) {
          clear(); state = "idle";
          status = "Đã copy clipboard. Ô nhập ChatGPT đã trống; sẵn sàng thu câu tiếp theo.";
          respond(snapshot()); return;
        }
        if (editors.length !== 1) throw new Error("Đã copy nhưng không xác định được một ô nhập duy nhất để xóa.");
        const editor = editors[0];
        if (editor.tagName === "TEXTAREA") {
          // Notify React using the native setter, rather than just changing DOM text.
          const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set;
          setter.call(editor, "");
          editor.dispatchEvent(new Event("input", { bubbles: true }));
        } else if (editor.isContentEditable) {
          editor.focus();
          const selection = window.getSelection();
          const range = document.createRange();
          range.selectNodeContents(editor);
          selection.removeAllRanges(); selection.addRange(range);
          if (!document.execCommand("delete")) throw new Error("Đã copy nhưng trình soạn thảo từ chối xóa; kiểm tra ô nhập ChatGPT.");
        } else {
          throw new Error("Đã copy nhưng loại ô nhập chưa hỗ trợ xóa an toàn.");
        }
        if (composer()) throw new Error("Đã copy nhưng ô nhập chưa trống; nội dung được giữ để kiểm tra.");
        clear(); state = "idle";
        status = "Đã copy clipboard và xóa bản chép khỏi ô nhập ChatGPT. Sẵn sàng thu câu tiếp theo; không gửi chat.";
      } else if (message.action === "cancel") cancel();
      respond(snapshot());
    } catch (error) { respond({ ...snapshot(), error: true, status: error.message || String(error) }); }
  }
  chrome.runtime.onMessage.addListener((message, sender, respond) => {
    if (message?.type !== "dictation-trial" || sender.id !== chrome.runtime.id) return;
    handle(message, respond);
  });

  // Page-scoped push-to-talk. No keyboard contents are recorded or transmitted.
  // Native Windows key-up support will be required for use outside this tab.
  let held = false, releaseTimer;
  const badge = document.createElement('div');
  badge.id = 'local-dictation-status';
  Object.assign(badge.style, {
    position:'fixed', bottom:'12px', right:'12px', zIndex:'2147483647',
    padding:'10px 14px', background:'#172033', color:'white', borderRadius:'8px',
    font:'14px system-ui', maxWidth:'430px', pointerEvents:'none', display:'none'
  });
  badge.setAttribute('role', 'status');
  document.documentElement.appendChild(badge);
  function notify(value) {
    badge.textContent = value.status;
    badge.style.display = 'block';
  }
  function release() {
    if (!held) return;
    held = false;
    const until = performance.now() + 10000;
    // A quick release can precede Chrome obtaining microphone permission.
    // Wait for the actual stop control, never click generic Send.
    const finish = () => {
      if (state !== 'recording') return;
      if (button('Submit dictation')) {
        handle({action:'stop'}, notify);
      } else if (performance.now() < until) {
        releaseTimer = setTimeout(finish, 100);
      } else {
        cancel();
        notify({status:'Không thấy nút dừng sau 10 giây. Kiểm tra quyền micro; nếu còn thu, đóng tab để ngắt.'});
      }
    };
    finish();
  }
  document.addEventListener('keydown', event => {
    if (windowsBridge) return;
    if (!event.isTrusted || event.code !== 'Backquote' || !event.ctrlKey || event.altKey || event.metaKey || event.shiftKey) return;
    event.preventDefault();
    if (event.repeat || held || state === 'recording' || state === 'processing') return;
    clearTimeout(releaseTimer);
    handle({action:'start'}, value => {
      held = !value.error && value.state === 'recording';
      notify(value);
    });
  }, true);
  document.addEventListener('keyup', event => {
    if (!event.isTrusted || !held) return;
    if (event.code === 'Backquote' || event.key === 'Control') {
      event.preventDefault(); release();
    }
  }, true);
  window.addEventListener('blur', release);
  document.addEventListener('visibilitychange', () => { if (document.hidden) release(); });
})();
