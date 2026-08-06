/**
 * ============================================================
 * MARG ERP → WhatsApp Gateway Server
 * WhiskeySockets/Baileys — runs on your personal WA number
 * Install: npm install @whiskeysockets/baileys express qrcode-terminal
 * Run: node whatsapp_server.js
 * ============================================================
 */

const {
  default: makeWASocket,
  DisconnectReason,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
} = require("@whiskeysockets/baileys");

const express = require("express");
const fs = require("fs");
const path = require("path");
const pino = require("pino");
const qrcode = require("qrcode-terminal");

// ── Load config ──────────────────────────────────────────────
const config = JSON.parse(
  fs.readFileSync(path.resolve(__dirname, "../config/config.json"), "utf8")
);
const API_KEY = config.nodejs_server.api_key;
const PORT    = config.nodejs_server.port;
const SESSION = path.resolve(__dirname, "wa_session");

// ── Baileys logger ────────────────────────────────────────────
// Signal decryption failures on WhatsApp's own multi-device fan-out are
// routine and unrelated to our sends, so keep them on disk instead of
// drowning the console.
const LOG_DIR = path.resolve(__dirname, "../logs");
fs.mkdirSync(LOG_DIR, { recursive: true });
const waLogger = pino(
  { level: "warn" },
  pino.destination({ dest: path.join(LOG_DIR, "baileys.log"), sync: false })
);

// libsignal writes decryption failures straight to console.* and accepts no
// logger. File those lines instead of drowning the CMD window.
const SIGNAL_NOISE =
  /Session error:|Failed to decrypt message with any known session|No matching sessions found for message|Decrypted message with closed session|Session already (closed|open)|Closing (open session in favor|session:)|Opening session:|Removing old closed session:|Migrating session to:|V1 session storage migration error|Bad MAC/;

function formatConsoleArgs(args) {
  return args
    .map((a) => {
      if (a instanceof Error) return a.stack || a.message;
      return String(a);
    })
    .join(" ");
}

let suppressSignalStack = false;

function isSignalNoise(text) {
  const trimmed = text.trim();
  if (!trimmed) return suppressSignalStack;
  if (SIGNAL_NOISE.test(trimmed)) return true;
  if (suppressSignalStack && /^\s*at .+/.test(text)) return true;
  return false;
}

function installSignalConsoleFilter() {
  for (const level of ["log", "error", "warn", "info"]) {
    const passthrough = console[level].bind(console);
    console[level] = (...args) => {
      const text = formatConsoleArgs(args);
      if (isSignalNoise(text)) {
        suppressSignalStack = true;
        waLogger.warn(text);
        return;
      }
      suppressSignalStack = false;
      passthrough(...args);
    };
  }
}

installSignalConsoleFilter();

// ── Express API server ────────────────────────────────────────
const app  = express();
app.use(express.json({ limit: "50mb" }));

let sock = null;
let isConnected = false;
let reconnectTimer = null;

function explainDisconnect(code) {
  switch (code) {
    case 408: return "network timeout — reconnecting in 5s";
    case 428: return "connection closed — reconnecting in 5s";
    case 440: return "another WhatsApp session is open — close duplicate START_SERVER.bat windows";
    case 401: return "logged out — scan the QR code shown below";
    case 515: return "WhatsApp asked for restart — reconnecting in 5s";
    default:  return "reconnecting in 5s";
  }
}

// ── Auth middleware ───────────────────────────────────────────
function authMiddleware(req, res, next) {
  const key = req.headers["x-api-key"];
  if (key !== API_KEY) return res.status(401).json({ error: "Unauthorized" });
  next();
}

// ── Health check ──────────────────────────────────────────────
app.get("/status", (req, res) => {
  res.json({ connected: isConnected, timestamp: new Date().toISOString() });
});

/**
 * POST /send-text
 * body: { phone: "919XXXXXXXXX", message: "Hello!" }
 */
app.post("/send-text", authMiddleware, async (req, res) => {
  if (!isConnected) return res.status(503).json({ error: "WA not connected" });
  const { phone, message } = req.body;
  if (!phone || !message) return res.status(400).json({ error: "phone and message required" });

  try {
    const jid = await resolveJid(phone);
    await sock.sendMessage(jid, { text: message });
    console.log(`[TEXT SENT] → ${normalizePhone(phone)} | jid: ${jid}`);
    res.json({ success: true, to: normalizePhone(phone), jid });
  } catch (err) {
    console.error("[TEXT ERROR]", err.message);
    res.status(500).json({ error: err.message });
  }
});

/**
 * POST /send-pdf
 * body: { phone: "919XXXXXXXXX", pdf_base64: "...", filename: "INV-001.pdf", caption: "Your Invoice" }
 */
app.post("/send-pdf", authMiddleware, async (req, res) => {
  if (!isConnected) return res.status(503).json({ error: "WA not connected" });
  const { phone, pdf_base64, filename, caption } = req.body;
  if (!phone || !pdf_base64) return res.status(400).json({ error: "phone and pdf_base64 required" });

  try {
    const jid      = await resolveJid(phone);
    const pdfBuffer = Buffer.from(pdf_base64, "base64");

    await sock.sendMessage(jid, {
      document: pdfBuffer,
      mimetype: "application/pdf",
      fileName: filename || "invoice.pdf",
      caption:  caption  || "",
    });
    console.log(`[PDF SENT] → ${normalizePhone(phone)} | jid: ${jid} | ${filename}`);
    res.json({ success: true, to: normalizePhone(phone), jid, file: filename });
  } catch (err) {
    console.error("[PDF ERROR]", err.message);
    res.status(500).json({ error: err.message });
  }
});

/**
 * POST /send-bulk-text
 * body: { messages: [{ phone, message }, ...] }
 * Adds 3-5 second delay between messages to avoid WA ban
 */
app.post("/send-bulk-text", authMiddleware, async (req, res) => {
  if (!isConnected) return res.status(503).json({ error: "WA not connected" });
  const { messages } = req.body;
  if (!Array.isArray(messages)) return res.status(400).json({ error: "messages array required" });

  const results = [];
  for (const item of messages) {
    try {
      const jid = await resolveJid(item.phone);
      await sock.sendMessage(jid, { text: item.message });
      results.push({ phone: normalizePhone(item.phone), status: "sent", jid });
      console.log(`[BULK TEXT] → ${normalizePhone(item.phone)} | jid: ${jid}`);
    } catch (err) {
      results.push({ phone: item.phone, status: "failed", error: err.message });
    }
    // Delay 3–5 seconds to mimic human behavior
    await sleep(3000 + Math.random() * 2000);
  }
  res.json({ results });
});

// ── Helper: normalize phone (India 91) ─────────────────────────
function normalizePhone(phone) {
  let digits = phone.toString().replace(/\D/g, "");
  if (digits.startsWith("0") && digits.length === 11) digits = digits.slice(1);
  if (digits.length === 10 && /^[6-9]/.test(digits)) digits = "91" + digits;
  return digits;
}

async function resolveJid(phone) {
  const clean = normalizePhone(phone);
  if (clean.length < 12) {
    throw new Error(`Invalid phone after normalize: ${clean || phone}`);
  }
  const check = await sock.onWhatsApp(clean);
  const row = check && check[0];
  if (!row || !row.exists) {
    throw new Error(`Number not registered on WhatsApp: ${clean}`);
  }
  return row.jid;
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// ── Start Baileys connection ──────────────────────────────────
async function startBaileys() {
  const { state, saveCreds } = await useMultiFileAuthState(SESSION);
  const { version }          = await fetchLatestBaileysVersion();

  sock = makeWASocket({
    version,
    auth:            state,
    logger:          waLogger,
    printQRInTerminal: false,
    browser:         ["Marg ERP Automation", "Chrome", "1.0.0"],
    syncFullHistory: false,
    shouldSyncHistoryMessage: () => false,
    markOnlineOnConnect: false,
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", ({ connection, lastDisconnect, qr }) => {
    if (qr) {
      console.log("\n📱 SCAN THIS QR CODE WITH YOUR WHATSAPP:\n");
      qrcode.generate(qr, { small: true });
    }

    if (connection === "close") {
      isConnected = false;
      const code  = lastDisconnect?.error?.output?.statusCode;
      const retry = code !== DisconnectReason.loggedOut;
      console.log(`[WA] Connection closed (code ${code}). ${explainDisconnect(code)}`);
      console.log("     Bills will NOT send until you see: ✅ WhatsApp connected!");
      if (retry) {
        clearTimeout(reconnectTimer);
        reconnectTimer = setTimeout(startBaileys, 5000);
      }
    }

    if (connection === "connecting") {
      isConnected = false;
      console.log("[WA] Connecting to WhatsApp...");
    }

    if (connection === "open") {
      isConnected = true;
      console.log("✅ WhatsApp connected! Server ready on port", PORT);
    }
  });
}

// ── Boot ──────────────────────────────────────────────────────
startBaileys().catch(console.error);
app.listen(PORT, "127.0.0.1", () => {
  console.log(`🚀 WA API server listening on http://127.0.0.1:${PORT}`);
});
