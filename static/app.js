const urlInput = document.getElementById("urlInput");
const scrapeBtn = document.getElementById("scrapeBtn");
const scrapeStatus = document.getElementById("scrapeStatus");
const chatCard = document.getElementById("chatCard");
const chatBox = document.getElementById("chatBox");
const chatForm = document.getElementById("chatForm");
const questionInput = document.getElementById("questionInput");

const sessionId = crypto.randomUUID();
let activeUrl = "";
let notifiedStart = false;

async function parseResponse(res) {
  const text = await res.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

function addMessage(role, text) {
  const div = document.createElement("div");
  div.className = `message ${role}`;
  div.textContent = `${role === "user" ? "You" : "Bot"}: ${text}`;
  chatBox.appendChild(div);
  chatBox.scrollTop = chatBox.scrollHeight;
}

async function notifyChatStart() {
  if (notifiedStart || !activeUrl) return;
  await fetch("/api/chat/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, url: activeUrl }),
  });
  notifiedStart = true;
}

scrapeBtn.addEventListener("click", async () => {
  const url = urlInput.value.trim();
  if (!url) {
    scrapeStatus.textContent = "Please enter a website URL.";
    return;
  }

  scrapeBtn.disabled = true;
  scrapeStatus.textContent = "Scraping website... this can take up to a minute.";

  try {
    const res = await fetch("/api/scrape", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });

    const data = await parseResponse(res);

    if (!res.ok) {
      throw new Error(data.detail || "Scrape failed");
    }

    // ✅ FIXED PART
    activeUrl = url;
    chatCard.classList.remove("hidden");

    scrapeStatus.textContent =
      `Done. Pages: ${data.pages}, Chunks: ${data.chunks}.`;

    addMessage("bot", "Website ready. Ask me anything about this business.");

  } catch (err) {
    scrapeStatus.textContent = `Error: ${err.message}`;
  } finally {
    scrapeBtn.disabled = false;
  }
});

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = questionInput.value.trim();
  if (!question || !activeUrl) return;

  addMessage("user", question);
  questionInput.value = "";
  addMessage("bot", "Thinking...");

  const thinkingEl = chatBox.lastChild;

  try {
    await notifyChatStart();

    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        url: activeUrl,
        question,
      }),
    });

    const data = await parseResponse(res);

    if (!res.ok) {
      throw new Error(data.detail || "Chat request failed");
    }

    thinkingEl.textContent = `Bot: ${data.answer}`;

  } catch (err) {
    thinkingEl.textContent = `Bot: Error: ${err.message}`;
  }
});