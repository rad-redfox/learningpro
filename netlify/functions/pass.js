// Manual 2-month pass: validate a hand-distributed code and issue a signed
// 60-day pass token. Codes live in the VALID_CODES env var (comma-separated),
// never in the public code. Tokens are HMAC-signed with PASS_SECRET so a pass
// can't be faked without redeeming a real code.
//
// Setup (Netlify → Site settings → Environment variables):
//   VALID_CODES = LP-XXXX-XXXX,LP-YYYY-YYYY,...   (the codes you hand out)
//   PASS_SECRET = <a long random string>           (keep secret)
//
// When Lemon Squeezy is approved later, its license keys become another source
// of codes — the app side doesn't change.

const crypto = require("crypto");
const PASS_DAYS = 60;

function b64url(buf) {
  return Buffer.from(buf).toString("base64url");
}
function sign(payload, secret) {
  const body = b64url(JSON.stringify(payload));
  const sig = crypto.createHmac("sha256", secret).update(body).digest("base64url");
  return body + "." + sig;
}
function verify(token, secret) {
  try {
    const [body, sig] = String(token).split(".");
    if (!body || !sig) return null;
    const expect = crypto.createHmac("sha256", secret).update(body).digest("base64url");
    const a = Buffer.from(sig), b = Buffer.from(expect);
    if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) return null;
    return JSON.parse(Buffer.from(body, "base64url").toString());
  } catch {
    return null;
  }
}

exports.handler = async (event) => {
  if (event.httpMethod !== "POST") {
    return { statusCode: 405, body: JSON.stringify({ error: "Method not allowed" }) };
  }
  const secret = process.env.PASS_SECRET;
  if (!secret) {
    return json(500, { error: "Server not configured: PASS_SECRET is missing." });
  }

  let body;
  try { body = JSON.parse(event.body || "{}"); }
  catch { return json(400, { error: "Invalid JSON body" }); }

  // Verify an existing pass token (called on app load)
  if (body.action === "verify") {
    const payload = verify(body.token, secret);
    const active = !!(payload && payload.exp && payload.exp * 1000 > Date.now());
    return json(200, { active, exp: payload ? payload.exp : null });
  }

  // Redeem a code → issue a 60-day token. Accepts a manual code OR a Lemon Squeezy license key.
  if (body.action === "redeem") {
    const raw = String(body.code || "").trim();
    if (!raw) return json(400, { ok: false, error: "Please enter a code." });
    const exp = Math.floor(Date.now() / 1000) + PASS_DAYS * 24 * 60 * 60;

    // 1) Manual code list (VALID_CODES env var)
    const manual = (process.env.VALID_CODES || "")
      .split(",").map((c) => c.trim().toUpperCase()).filter(Boolean);
    if (manual.includes(raw.toUpperCase())) {
      return json(200, { ok: true, token: sign({ exp }, secret), exp });
    }

    // 2) Lemon Squeezy license key (no API key needed for validate)
    try {
      const r = await fetch("https://api.lemonsqueezy.com/v1/licenses/validate", {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ license_key: raw }).toString(),
      });
      const d = await r.json();
      // Optional: lock to your store. Set LEMONSQUEEZY_STORE_ID to enforce.
      const wantStore = process.env.LEMONSQUEEZY_STORE_ID;
      const storeOk = !wantStore || (d && d.meta && String(d.meta.store_id) === String(wantStore));
      if (d && d.valid && storeOk) {
        return json(200, { ok: true, token: sign({ exp }, secret), exp });
      }
    } catch (e) { /* fall through to invalid */ }

    return json(200, { ok: false, error: "That code isn’t valid. Check it and try again." });
  }

  return json(400, { error: "Unknown action" });
};

function json(statusCode, obj) {
  return { statusCode, headers: { "Content-Type": "application/json" }, body: JSON.stringify(obj) };
}
