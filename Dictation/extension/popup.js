const status = document.querySelector("#status");
const result = document.querySelector("#result");
let target;
async function connect() {
  const bridge = await chrome.runtime.sendMessage({type:'windows-bridge',action:'status'});
  if (bridge.enabled && bridge.target) {
    target = bridge.target;
    return;
  }
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || new URL(tab.url || "about:blank").origin !== "https://chatgpt.com") {
    throw new Error("Hãy chọn tab https://chatgpt.com đã đăng nhập rồi mở extension.");
  }
  target = tab.id;
  await chrome.scripting.executeScript({ target: { tabId: target }, files: ["content.js"] });
}
async function request(action, extra = {}) {
  if (!target) await connect();
  const value = await chrome.tabs.sendMessage(target, { type: "dictation-trial", action, ...extra });
  if (!value) throw new Error("Tab chưa phản hồi.");
  document.querySelector('#controls').textContent = (value.controls || []).join(' | ');
  if (action !== "status" || !status.dataset.actionError) status.textContent = value.status;
  if (action !== "status") status.dataset.actionError = value.error ? "1" : "";
  result.value = value.text || "";
}
function report(error) { status.textContent = error.message || String(error); }
for (const action of ["start", "stop", "cancel"]) {
  document.querySelector(`#${action}`).onclick = () => {
    request(action).catch(report);
  };
}
document.querySelector("#copy").onclick = async () => {
  const copied = result.value;
  if (!copied) return;
  try {
    await navigator.clipboard.writeText(copied);
  } catch {
    result.focus(); result.select(); status.textContent = "Chưa copy được nên KHÔNG xóa ô nhập ChatGPT. Nhấn Ctrl+C để copy thủ công.";
    status.dataset.actionError = "1";
    return;
  }
  try {
    await request("clearCopied", { copied });
  } catch (error) {
    status.textContent = "Đã copy clipboard nhưng chưa xóa được ô nhập ChatGPT: " + error.message;
    status.dataset.actionError = "1";
  }
};
connect().then(() => request("status")).catch(report);
async function bridge(action) {
  const value = await chrome.runtime.sendMessage({type:'windows-bridge', action, tabId:target});
  document.querySelector('#bridgeStatus').textContent = value.status;
  if (value.enabled && value.target) target = value.target;
}
document.querySelector('#windowsOn').onclick = () => bridge('enable').catch(report);
document.querySelector('#windowsOff').onclick = () => bridge('disable').catch(report);
document.querySelector('#showTab').onclick = () => bridge('show').catch(report);
// Poll only while this user-opened popup exists; closing it does not stop capture.
setInterval(() => { if (target) { request("status").catch(report); bridge('status').catch(report); } }, 700);
