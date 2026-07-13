// On-page comments for the Creator Program dashboard.
// Stores comments in comments.json in the GitHub repo (no DB), emails Mel on each new one (if RESEND_API_KEY set).
const REPO = process.env.COMMENTS_REPO || "melina-pixel/creator-dashboard";
const TOKEN = process.env.GH_TOKEN;
const FILE = "comments.json";
const API = `https://api.github.com/repos/${REPO}/contents/${FILE}`;
const H = { Authorization: `Bearer ${TOKEN}`, Accept: "application/vnd.github+json", "User-Agent": "creator-dashboard" };

async function getFile() {
  const r = await fetch(API, { headers: H });
  if (r.status === 404) return { comments: [], sha: null };
  if (!r.ok) throw new Error("gh read " + r.status);
  const j = await r.json();
  let data = { comments: [] };
  try { data = JSON.parse(Buffer.from(j.content, "base64").toString("utf8")); } catch (e) {}
  return { comments: data.comments || [], sha: j.sha };
}

module.exports = async (req, res) => {
  try {
    if (req.method === "GET") {
      const { comments } = await getFile();
      res.setHeader("Cache-Control", "no-store");
      return res.status(200).json({ comments });
    }
    if (req.method === "POST") {
      let b = req.body;
      if (typeof b === "string") { try { b = JSON.parse(b || "{}"); } catch (e) { b = {}; } }
      b = b || {};
      const name = String(b.name || "").trim().slice(0, 60);
      const text = String(b.text || "").trim().slice(0, 2000);
      if (!name || !text) return res.status(400).json({ error: "name and text required" });
      const { comments, sha } = await getFile();
      const c = { name, text, ts: new Date().toISOString() };
      comments.push(c);
      const put = await fetch(API, {
        method: "PUT",
        headers: { ...H, "Content-Type": "application/json" },
        body: JSON.stringify({
          message: `comment from ${name}`,
          content: Buffer.from(JSON.stringify({ comments }, null, 2)).toString("base64"),
          sha: sha || undefined,
        }),
      });
      if (!put.ok) return res.status(500).json({ error: "save failed" });
      if (process.env.RESEND_API_KEY) {
        try {
          await fetch("https://api.resend.com/emails", {
            method: "POST",
            headers: { Authorization: `Bearer ${process.env.RESEND_API_KEY}`, "Content-Type": "application/json" },
            body: JSON.stringify({
              from: "Creator Dashboard <onboarding@resend.dev>",
              to: ["melina@supernormal.com"],
              subject: `💬 New dashboard comment from ${name}`,
              text: `${name} commented on the Creator Program dashboard:\n\n${text}\n\n— https://creator-pipeline-dashboard-melina-5949s-projects.vercel.app`,
            }),
          });
        } catch (e) {}
      }
      return res.status(200).json({ ok: true, comment: c });
    }
    res.status(405).json({ error: "method not allowed" });
  } catch (e) {
    res.status(500).json({ error: "server error" });
  }
};
