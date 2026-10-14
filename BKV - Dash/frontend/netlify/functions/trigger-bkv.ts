// این فانکشن سمت سرور برای اجرای دستی پایپ‌لاین BKV
// کارش workflow_dispatch روی مخزن کد است تا توکن گیت‌هاب در مرورگر لو نرود.

export const handler = async (req: any, context?: any) => {
  const isV2 = typeof Request !== 'undefined' && req instanceof Request;
  const method = isV2 ? req.method : (req?.httpMethod || req?.method || '');

  const corsHeaders = {
    'Access-Control-Allow-Origin': process.env.ALLOWED_ORIGIN || '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Content-Type': 'application/json',
  };

  const respond = (status: number, data: any) => {
    const bodyStr = typeof data === 'string' ? data : JSON.stringify(data);
    if (isV2) {
      return new Response(bodyStr, { status, headers: corsHeaders });
    }
    return {
      statusCode: status,
      headers: corsHeaders,
      body: bodyStr,
    };
  };

  if (method === 'OPTIONS') {
    return respond(204, '');
  }
  if (method !== 'POST') {
    return respond(405, { error: 'method_not_allowed' });
  }

  const token = process.env.TRIGGER_TOKEN;
  const repo = process.env.TRIGGER_REPO || 'mechsolveofficial-ui/bkv-dash';
  if (!token) {
    return respond(503, { error: 'not_configured' });
  }

  // خواندن meta فعلی: برای تشخیص لحظه تغییر و انتشار دیتای جدید
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
    /* صرفاً برای UX است */
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
      return respond(200, { ok: true, previous_generated_at_utc: previousGeneratedAt });
    }
    const text = await res.text();
    console.error('GitHub dispatch failed', res.status, text.slice(0, 500));
    return respond(502, { error: 'github_error' });
  } catch (err) {
    console.error('trigger-bkv error', err);
    return respond(500, { error: 'github_error' });
  }
};

export default handler;
