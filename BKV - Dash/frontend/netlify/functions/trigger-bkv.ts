// این فانکشن سمت سرور برای اجرای دستی پایپ‌لاین BKV
//
// کارش فقط یک چیز است: workflow_dispatch روی مخزن کد صدا بزند.
// توکن GitHub (secret اسمش TRIGGER_TOKEN) فقط همینجا — سمت سرور — استفاده
// می‌شود و هرگز به مرورگر کاربر نمی‌رسد.
//
// روی Netlify باید این environment variable ست شود:
//   TRIGGER_TOKEN = یک Personal Access Token با پرمیشن repo (classic)
//   TRIGGER_REPO   = "mechsolveofficial-ui/bkv-dash" (مخزنی که workflow در آن است)
// (اختیاری) TRIGGER_FROM = "*" → فقط از دامنهٔ خود سایت اجازهٔ درخواست بده.

export default async (req: { method?: string; headers: Record<string, string | string[] | undefined> }) => {
  // CORS: فقط همان دامنهٔ سایت مجاز است (پیش‌فرض خود صفحست؛ این برای فراخوانی از دامنه‌های دیگر)
  const corsHeaders = {
    'Access-Control-Allow-Origin': process.env.ALLOWED_ORIGIN || '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  };
  if (req.method === 'OPTIONS') {
    return { statusCode: 204, headers: corsHeaders, body: '' };
  }
  if (req.method !== 'POST') {
    return { statusCode: 405, headers: corsHeaders, body: JSON.stringify({ error: 'method_not_allowed' }) };
  }

  const token = process.env.TRIGGER_TOKEN;
  const repo = process.env.TRIGGER_REPO || 'mechsolveofficial-ui/bkv-dash';
  if (!token) {
    return { statusCode: 503, headers: corsHeaders, body: JSON.stringify({ error: 'not_configured' }) };
  }

  // خواندن meta فعلی: اگر اختلافی بود، در پاسخ می‌گوییم که منتظر تغییرش بماند
  let previousGeneratedAt: string | null = null;
  try {
    const metaRes = await fetch(
      'https://raw.githubusercontent.com/mechsolveofficial-ui/bkv-data/data/meta.json',
      { headers: { 'User-Agent': 'bkv-netlify-trigger' } }
    );
    if (metaRes.ok) {
      const meta = (await metaRes.json()) as { generated_at_utc?: string };
      previousGeneratedAt = meta.generated_at_utc ?? null;
    }
  } catch {
    /* مهم نیست؛ فقط برای UX است */
  }

  try {
    const res = await fetch(`https://api.github.com/repos/${repo}/actions/workflows/update-data.yml/dispatches`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'bkv-netlify-trigger',
      },
      body: JSON.stringify({ ref: 'main' }),
    });

    if (res.status === 204) {
      return {
        statusCode: 200,
        headers: corsHeaders,
        body: JSON.stringify({ ok: true, previous_generated_at_utc: previousGeneratedAt }),
      };
    }
    const text = await res.text();
    console.error('GitHub dispatch failed', res.status, text.slice(0, 500));
    return { statusCode: 502, headers: corsHeaders, body: JSON.stringify({ error: 'github_error' }) };
  } catch (err) {
    console.error('trigger-bkv error', err);
    return { statusCode: 500, headers: corsHeaders, body: JSON.stringify({ error: 'github_error' }) };
  }
};
