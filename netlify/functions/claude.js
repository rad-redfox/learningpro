// Server-side proxy to the Anthropic Messages API.
// The API key lives in a Netlify environment variable (ANTHROPIC_API_KEY) and
// never reaches the browser. The Life games and AI tutor POST {messages, max_tokens}
// here; we add auth + the version header and forward to Anthropic.
//
// Setup (one time): in Netlify → Site settings → Environment variables, add
//   ANTHROPIC_API_KEY = sk-ant-...
// then redeploy. Get a key at https://console.anthropic.com/.

const MODEL = "claude-sonnet-4-6"; // forced server-side so the client can't request a pricier model
const MAX_TOKENS_CAP = 4096;       // ceiling so a tampered client can't run up a huge bill

exports.handler = async (event) => {
  if (event.httpMethod !== "POST") {
    return { statusCode: 405, body: JSON.stringify({ error: "Method not allowed" }) };
  }

  const key = process.env.ANTHROPIC_API_KEY;
  if (!key) {
    return {
      statusCode: 500,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ error: "Server not configured: ANTHROPIC_API_KEY is missing." }),
    };
  }

  let body;
  try {
    body = JSON.parse(event.body || "{}");
  } catch {
    return { statusCode: 400, body: JSON.stringify({ error: "Invalid JSON body" }) };
  }

  const { messages, max_tokens } = body;
  if (!Array.isArray(messages) || messages.length === 0) {
    return { statusCode: 400, body: JSON.stringify({ error: "messages must be a non-empty array" }) };
  }

  try {
    const upstream = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify({
        model: MODEL,
        max_tokens: Math.min(Math.max(Number(max_tokens) || 1024, 1), MAX_TOKENS_CAP),
        messages,
      }),
    });

    const data = await upstream.text(); // pass the body through verbatim
    return {
      statusCode: upstream.status,
      headers: { "Content-Type": "application/json" },
      body: data,
    };
  } catch (err) {
    return {
      statusCode: 502,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ error: "Upstream request failed", detail: String(err) }),
    };
  }
};
