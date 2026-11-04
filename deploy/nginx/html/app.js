// 临时测试页共用的小工具，正式前端完成后删除

async function api(path, body) {
  const options = body === undefined
    ? { method: "GET" }
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const response = await fetch(path, options);
  let data = {};
  try { data = await response.json(); } catch (_) { /* 无内容 */ }
  if (!response.ok) {
    let detail = data.detail;
    if (Array.isArray(detail)) detail = "填写的内容格式不正确";
    if (response.status === 429 && !detail) detail = "操作太频繁，请稍后再试";
    throw new Error(detail || `请求失败（${response.status}）`);
  }
  return data;
}

function show(element, text, ok) {
  element.textContent = text;  // 用 textContent，不解析 HTML
  element.className = "message " + (ok ? "ok" : "error");
}

function tokenFromUrl() {
  return new URLSearchParams(location.search).get("token");
}
