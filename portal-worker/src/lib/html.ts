// Shared minimal HTML page renderer for the worker's public, unauthenticated
// pages (unsubscribe / resubscribe confirmations). Kept dependency-free since
// these are plain browser-navigated pages, not JSON API responses.

export function resultPage(
  title: string,
  message: string,
  success: boolean,
  extraHtml = ""
): string {
  const colour = success ? "#2e7d32" : "#c62828";
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${title} — Bargain Hunter</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; background: #f5f5f5; display: flex; align-items: center; justify-content: center; min-height: 100vh; }
  .card { background: #fff; border-radius: 8px; padding: 40px 48px; max-width: 480px; box-shadow: 0 1px 4px rgba(0,0,0,.1); text-align: center; }
  .icon { font-size: 48px; margin-bottom: 16px; }
  h1 { margin: 0 0 12px; color: ${colour}; font-size: 22px; }
  p { margin: 0; color: #444; line-height: 1.6; }
  button { border: none; border-radius: 6px; padding: 11px 24px; font-size: 14px; font-weight: 600; cursor: pointer; color: #fff; }
</style>
</head>
<body>
<div class="card">
  <div class="icon">${success ? "✅" : "❌"}</div>
  <h1>${title}</h1>
  <p>${message}</p>
  ${extraHtml}
</div>
</body>
</html>`;
}

export function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

export function escapeAttr(s: string): string {
  return escapeHtml(s);
}
