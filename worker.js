// ─────────────────────────────────────────────
// ENV variables (set in CF Dashboard / wrangler.toml):
//   TELEGRAM_BOT_TOKEN
//   NVIDIA_API_KEY
//   OWNER_ID
//   KV  → bind a KV namespace named "KV"
// ─────────────────────────────────────────────

const API_URL = "https://integrate.api.nvidia.com/v1/chat/completions";
const DEFAULT_MODEL = "moonshotai/kimi-k2-instruct-0905";
const MAX_CONTEXT_MESSAGES = 50;
const SKILLS_GITHUB_BASE =
  "https://raw.githubusercontent.com/sickn33/antigravity-awesome-skills/main/skills";

// ─────────────────────────────────────────────
// Skills map
// ─────────────────────────────────────────────
const AVAILABLE_SKILLS = {
  python: "python-pro",
  typescript: "typescript-pro",
  golang: "golang-pro",
  rust: "rust-pro",
  fastapi: "fastapi-pro",
  bash: "bash-pro",
  react: "react-best-practices",
  nextjs: "nextjs-app-router-patterns",
  frontend: "frontend-design",
  ui: "ui-ux-pro-max",
  vue: "vue-developer",
  reactnative: "react-native-architecture",
  expo: "expo-router",
  android: "frontend-mobile-development-component-scaffold",
  docker: "kubernetes-architect",
  devops: "gitops-workflow",
  backend: "backend-dev-guidelines",
  database: "database-architect",
  api: "api-design-principles",
  microservice: "microservices-patterns",
  security: "security-auditor",
  hacking: "ethical-hacking-methodology",
  pentest: "burp-suite-testing",
  llm: "llm-application-developer",
  agent: "agent-architect",
  rag: "rag-implementation",
  prompt: "prompt-engineering-patterns",
  debug: "systematic-debugging",
  refactor: "code-refactoring-refactor-clean",
  tdd: "tdd-workflows-tdd-cycle",
  review: "code-review-ai-ai-review",
  brainstorm: "brainstorming",
  fullstack: "senior-fullstack",
  architect: "c4-architecture-c4-architecture",
  saas: "full-stack-orchestration-full-stack-feature",
  git: "git-pushing",
  testing: "test-driven-development",
};

const SKILL_DESCRIPTIONS = {
  python: "Python 3.12+ master — async, type hints, modern patterns",
  typescript: "TypeScript advanced types, generics, strict mode",
  golang: "Go expert — goroutines, channels, production patterns",
  rust: "Rust systems — ownership, lifetimes, async",
  fastapi: "FastAPI + Pydantic + async endpoints",
  bash: "Shell scripting, automation, VPS commands",
  react: "Modern React — hooks, patterns, performance",
  nextjs: "Next.js 15 App Router, SSR, Server Components",
  frontend: "Production-grade UI components",
  ui: "Full UI/UX design system — colors, fonts, layout",
  vue: "Vue.js 3 + Composition API",
  reactnative: "React Native production architecture",
  expo: "Expo Router + EAS build & deploy",
  android: "Android/Mobile component scaffold",
  docker: "Kubernetes + Docker — k8s architect",
  devops: "GitOps, CI/CD pipelines, GitHub Actions",
  backend: "Node.js/Express/TypeScript backend patterns",
  database: "SQL/NoSQL design, schema, optimization",
  api: "REST API design principles & best practices",
  microservice: "Microservices patterns & architecture",
  security: "Security auditor — auth, vulns, OWASP",
  hacking: "Ethical hacking methodology",
  pentest: "Burp Suite web app pentesting",
  llm: "LLM app development — chains, tools, evals",
  agent: "Multi-agent systems architecture",
  rag: "RAG pipeline implementation",
  prompt: "Prompt engineering patterns",
  debug: "Systematic debugging methodology",
  refactor: "Clean code refactoring — SOLID principles",
  tdd: "Test-driven development cycle",
  review: "AI-powered code review checklist",
  brainstorm: "Brainstorm & plan before coding",
  fullstack: "Complete fullstack development guide",
  architect: "C4 architecture documentation",
  saas: "Full-stack SaaS feature orchestration",
  git: "Clean git commits, messages, workflow",
  testing: "Testing strategies & frameworks",
};

// ─────────────────────────────────────────────
// System prompt
// ─────────────────────────────────────────────
const SYSTEM_PROMPT = `You are a smart, calm, agentic AI assistant.

Core behavior:
Understand the user's latest message carefully.
Think about what the user actually wants.
Answer the exact request directly.
Do not answer the opposite of what the user asked.
Do not give generic advice when the user gives code or asks for a fix.
If the user asks for full code, provide full working code.
If the user asks for only code, provide only code.
Preserve the user's original intention.

Language behavior:
Always reply in the same language and typing style as the user's latest message.
If the user writes English, reply in English.
If the user writes Hindi, reply in Hindi.
If the user writes Hinglish, reply in Hinglish.
If the user mixes Hindi and English, reply in natural Hinglish.
Do not force Hindi. Do not force English. Match the user's tone naturally.

Tone:
Be practical, direct, and human-like.
Do not sound robotic.
Do not over-explain unless needed.
Do not lecture the user for casual slang, anger, or frustration.
Stay calm and keep helping.
Set a short boundary only for serious threats, hate, or harmful requests.
Avoid fake assistant lines. Avoid excessive emojis.

Formatting:
Use **bold** for important words when useful.
Use \`inline code\` for short commands, filenames, variables, model names, errors, and APIs.
Use fenced code blocks for full code, terminal commands, JSON, Python, Bash, JavaScript, HTML, CSS, etc.
Never write only the language name before code.
Do not use HTML tags in your response.
Do not use ### headings unless the user asks for documentation.

Coding:
For bug fixes, give fixed code first. Then explain the bug shortly if explanation is needed.
For VPS commands, give direct commands.
For Telegram bot code, keep parse_mode and formatting safe.`;

// ─────────────────────────────────────────────
// KV helpers — all data stored in Cloudflare KV
// ─────────────────────────────────────────────

async function kvGet(env, key) {
  try {
    const val = await env.KV.get(key);
    return val ? JSON.parse(val) : null;
  } catch {
    return null;
  }
}

async function kvSet(env, key, value) {
  await env.KV.put(key, JSON.stringify(value));
}

async function kvDel(env, key) {
  await env.KV.delete(key);
}

// ─────────────────────────────────────────────
// Message history helpers (stored in KV)
// ─────────────────────────────────────────────

async function getHistory(env, chatId) {
  const data = await kvGet(env, `history:${chatId}`);
  return Array.isArray(data) ? data : [];
}

async function saveMsg(env, chatId, role, content) {
  let history = await getHistory(env, chatId);
  history.push({ role, content, ts: Date.now() });
  if (history.length > MAX_CONTEXT_MESSAGES) {
    history = history.slice(history.length - MAX_CONTEXT_MESSAGES);
  }
  await kvSet(env, `history:${chatId}`, history);
}

async function resetHistory(env, chatId) {
  await kvDel(env, `history:${chatId}`);
}

// ─────────────────────────────────────────────
// Model helpers
// ─────────────────────────────────────────────

async function getModel(env, chatId) {
  const data = await kvGet(env, `model:${chatId}`);
  return data || DEFAULT_MODEL;
}

async function saveModel(env, chatId, model) {
  await kvSet(env, `model:${chatId}`, model);
}

// ─────────────────────────────────────────────
// Approved users helpers
// ─────────────────────────────────────────────

function isOwner(env, userId) {
  return String(userId) === String(env.OWNER_ID);
}

async function isApproved(env, userId) {
  if (isOwner(env, userId)) return true;
  const data = await kvGet(env, `approved:${userId}`);
  return data === true;
}

async function approveUser(env, userId) {
  await kvSet(env, `approved:${userId}`, true);
}

async function unapproveUser(env, userId) {
  await kvDel(env, `approved:${userId}`);
}

// ─────────────────────────────────────────────
// Active skill per chat
// ─────────────────────────────────────────────

async function getChatSkill(env, chatId) {
  const data = await kvGet(env, `skill:${chatId}`);
  return data || null;
}

async function setChatSkill(env, chatId, skillName) {
  await kvSet(env, `skill:${chatId}`, skillName);
}

async function clearChatSkill(env, chatId) {
  await kvDel(env, `skill:${chatId}`);
}

// ─────────────────────────────────────────────
// Skill fetch from GitHub (with KV cache 1 hour)
// ─────────────────────────────────────────────

async function fetchSkillContent(env, skillName) {
  const cacheKey = `skillcache:${skillName}`;
  const cached = await kvGet(env, cacheKey);
  if (cached) return cached;

  const folder = AVAILABLE_SKILLS[skillName];
  if (!folder) return "";

  const url = `${SKILLS_GITHUB_BASE}/${folder}/SKILL.md`;
  try {
    const resp = await fetch(url, { cf: { cacheTtl: 3600 } });
    if (resp.ok) {
      let text = await resp.text();
      text = text.slice(0, 6000);
      // Cache in KV for 1 hour (3600 seconds)
      await env.KV.put(cacheKey, JSON.stringify(text), { expirationTtl: 3600 });
      return text;
    }
  } catch {
    // ignore
  }
  return "";
}

// ─────────────────────────────────────────────
// Auto-detect skill from message text
// ─────────────────────────────────────────────

function autoDetectSkill(text) {
  const t = text.toLowerCase();
  const map = {
    react: ["react", "jsx", "hooks", "usestate", "useeffect", "redux", "zustand", "react component"],
    nextjs: ["next.js", "nextjs", "next js", "app router", "server component", "server action"],
    typescript: ["typescript", ".ts ", "type error", "interface {", "generic<", "type alias"],
    python: ["python", "def ", "pip install", "django", "flask", "pandas", "numpy", "asyncio", ".py"],
    fastapi: ["fastapi", "fast api", "pydantic", "uvicorn", "starlette"],
    bash: ["bash", "shell script", "#!/bin", "cron", "systemd", "chmod", "grep ", "awk "],
    golang: ["golang", "go lang", "goroutine", "gin ", "fiber ", "go mod", "func main"],
    rust: ["rust", "cargo", "borrow", "lifetime", "async rust", "tokio"],
    vue: ["vue", "vuex", "pinia", "nuxt", "composition api"],
    frontend: ["css", "tailwind", "html", "landing page", "ui component", "animate", "gsap"],
    ui: ["ux", "design system", "color palette", "typography", "figma", "wireframe"],
    reactnative: ["react native", "expo rn", "rn ", "metro bundler"],
    expo: ["expo", "eas build", "expo router", "expo sdk"],
    android: ["android", "kotlin", "jetpack compose", "gradle", "apk"],
    docker: ["docker", "kubernetes", "k8s", "kubectl", "helm", "pod ", "container"],
    devops: ["ci/cd", "github actions", "pipeline", "gitops", "nginx", "deployment", "yml"],
    backend: ["node.js", "nodejs", "express", "nestjs", "api server", "rest api backend"],
    database: ["sql", "postgres", "mysql", "mongodb", "schema", "query", "orm", "prisma", "migration"],
    api: ["api design", "rest api", "graphql", "openapi", "swagger", "endpoint design"],
    microservice: ["microservice", "service mesh", "grpc", "kafka", "event driven"],
    security: ["security", "vulnerability", "xss", "sql injection", "csrf", "owasp", "jwt", "oauth"],
    hacking: ["ethical hack", "penetration", "ctf", "exploit", "payload"],
    pentest: ["burp", "pentest", "web vulnerability", "zap proxy"],
    llm: ["llm", "language model", "openai", "nvidia nim", "groq", "embedding", "token"],
    agent: ["agent", "tool use", "function calling", "agentic", "multi agent", "supervisor"],
    rag: ["rag", "retrieval", "vector db", "chroma", "pinecone", "weaviate", "semantic search"],
    prompt: ["prompt", "system prompt", "few shot", "chain of thought", "prompt engineering"],
    debug: ["debug", "not working", "fix this", "crash", "exception", "traceback", "error fix", "why is"],
    refactor: ["refactor", "clean code", "solid principle", "tech debt", "restructure", "improve code"],
    tdd: ["test driven", "tdd", "unit test", "pytest", "jest", "vitest", "mock"],
    review: ["code review", "review this", "check my code", "pr review"],
    brainstorm: ["brainstorm", "plan this", "how should i", "architecture", "design system", "mvp"],
    fullstack: ["fullstack", "full stack", "end to end", "backend + frontend"],
    architect: ["c4 diagram", "system design", "architecture diagram", "draw diagram"],
    saas: ["saas", "startup", "product feature", "ship feature", "mvp feature"],
    git: ["git commit", "git push", "pull request", "branch", "merge conflict"],
    testing: ["write test", "test case", "e2e test", "playwright", "cypress", "selenium"],
  };

  for (const [skill, keywords] of Object.entries(map)) {
    for (const kw of keywords) {
      if (t.includes(kw)) return skill;
    }
  }
  return "";
}

// ─────────────────────────────────────────────
// Language detection
// ─────────────────────────────────────────────

function detectLanguageInstruction(text) {
  const hasDevanagari = /[\u0900-\u097F]/.test(text);
  const englishLetters = (text.match(/[A-Za-z]/g) || []).length;
  const hinglishWords = (
    text
      .toLowerCase()
      .match(
        /\b(kya|hai|hain|nhi|nahin|kaise|kese|kar|karo|kr|mujhe|tum|aap|bhai|bata|bolo|hona|chahiye|thek|sahi|galat|code|vps|wala|wasa|aisa|kaam|fix|de|do|mat|kyu|kyun|abhi|isme|usme|ye|wo|jo|jaisa|waisa|bana|banake|denge|chala|chalana|normal|bar|baar|typing|indicator)\b/g
      ) || []
  ).length;

  if (hasDevanagari && englishLetters > 5)
    return "The user's latest message is mixed Hindi and English. Reply in natural Hinglish matching their typing style.";
  if (hasDevanagari)
    return "The user's latest message is Hindi. Reply in Hindi or natural Hinglish matching their style.";
  if (hinglishWords >= 2)
    return "The user's latest message is Hinglish. Reply in natural Hinglish matching their typing style.";
  if (englishLetters > 0)
    return "The user's latest message is English or mostly English. Reply in English.";
  return "Reply in the same language and style as the user's latest message.";
}

// ─────────────────────────────────────────────
// Build messages array for NVIDIA API
// ─────────────────────────────────────────────

async function buildMessages(env, chatId, text) {
  const history = await getHistory(env, chatId);
  const langInstruction = detectLanguageInstruction(text);

  const messages = [
    { role: "system", content: SYSTEM_PROMPT },
    { role: "system", content: langInstruction },
  ];

  // Skill injection
  let activeSkill = await getChatSkill(env, chatId);
  if (!activeSkill) activeSkill = autoDetectSkill(text);

  if (activeSkill) {
    const skillContent = await fetchSkillContent(env, activeSkill);
    if (skillContent) {
      messages.push({
        role: "system",
        content: `[ACTIVE SKILL: ${activeSkill.toUpperCase()}]\n\n${skillContent}\n\n[Apply the above skill expertise to the user's request.]`,
      });
    }
  }

  // Append history (only role + content)
  for (const h of history) {
    messages.push({ role: h.role, content: h.content });
  }
  messages.push({ role: "user", content: text });

  return messages;
}

// ─────────────────────────────────────────────
// NVIDIA API call
// ─────────────────────────────────────────────

async function callNvidiaAPI(env, messages, model) {
  const retryWaits = [3000, 6000, 12000, 20000];

  for (let attempt = 0; attempt < retryWaits.length; attempt++) {
    let resp;
    try {
      resp = await fetch(API_URL, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.NVIDIA_API_KEY}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model,
          messages,
          temperature: 0.35,
          top_p: 0.85,
          max_tokens: 1500,
          stream: false,
        }),
      });
    } catch (e) {
      if (attempt < retryWaits.length - 1) {
        await sleep(retryWaits[attempt]);
        continue;
      }
      return "API timeout ho gaya. Thoda baad dobara try karo.";
    }

    if (resp.ok) {
      const data = await resp.json();
      return (
        data?.choices?.[0]?.message?.content?.trim() ||
        "Empty response mila."
      );
    }

    if (resp.status === 429) {
      if (attempt < retryWaits.length - 1) {
        await sleep(retryWaits[attempt]);
        continue;
      }
      return (
        "NVIDIA API abhi rate limit de raha hai. " +
        "Thoda ruk ke dobara try karo. Agar baar-baar aaye to lighter model use karo: " +
        "`/setmodel mistralai/mistral-small-4-119b-2603`"
      );
    }

    if ([500, 502, 503, 504].includes(resp.status)) {
      if (attempt < retryWaits.length - 1) {
        await sleep(retryWaits[attempt]);
        continue;
      }
      return `NVIDIA API server busy hai. Error ${resp.status}. Thoda baad try karo.`;
    }

    const errText = await resp.text();
    return `API Error ${resp.status}: ${errText.slice(0, 700)}`;
  }

  return "API busy hai. Thoda baad dobara try karo.";
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// ─────────────────────────────────────────────
// Text formatting helpers
// ─────────────────────────────────────────────

function plainCleanup(text) {
  if (!text) return "";
  text = text.replace(/\r\n/g, "\n");
  text = text.replace(/###/g, "");
  text = text.replace(/\n{5,}/g, "\n\n\n");
  // Fix bare language names before code
  text = text.replace(
    /^python\s*\n(?=def |class |import |from |print\(|async |await |[a-zA-Z_])/gm,
    "```python\n"
  );
  text = text.replace(/^bash\s*\n(?=[a-zA-Z0-9_./~$-])/gm, "```bash\n");
  text = text.replace(/^sh\s*\n(?=[a-zA-Z0-9_./~$-])/gm, "```bash\n");
  text = text.replace(
    /^javascript\s*\n(?=const |let |var |function |import |export |async )/gm,
    "```javascript\n"
  );
  text = text.replace(
    /^js\s*\n(?=const |let |var |function |import |export |async )/gm,
    "```javascript\n"
  );
  text = text.replace(/^json\s*\n(?=[\[{])/gm, "```json\n");
  // Close unclosed code blocks
  const count = (text.match(/```/g) || []).length;
  if (count % 2 !== 0) text += "\n```";
  return text.trim();
}

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function applyInlineMarkdown(segment) {
  segment = escapeHtml(segment);
  segment = segment.replace(
    /\*\*([^\n*][\s\S]*?[^\n*])\*\*/g,
    (_, m) => `<b>${m}</b>`
  );
  segment = segment.replace(/`([^`\n]+)`/g, (_, m) => `<code>${m}</code>`);
  return segment;
}

function markdownToTelegramHtml(text) {
  if (!text) return "";
  text = plainCleanup(text);
  const parts = [];
  let pos = 0;
  const pattern = /```(?:[a-zA-Z0-9_+\-.]*)?\n?([\s\S]*?)```/g;
  let match;
  while ((match = pattern.exec(text)) !== null) {
    const before = text.slice(pos, match.index);
    if (before) parts.push(applyInlineMarkdown(before));
    const code = escapeHtml(match[1].replace(/^\n/, "").replace(/\n$/, ""));
    parts.push(`<pre>${code}</pre>`);
    pos = match.index + match[0].length;
  }
  const rest = text.slice(pos);
  if (rest) parts.push(applyInlineMarkdown(rest));
  let out = parts.join("");
  out = out.replace(/\n{5,}/g, "\n\n\n");
  return out.trim();
}

function splitText(text, limit = 3900) {
  if (!text) return [""];
  if (text.length <= limit) return [text];
  const chunks = [];
  let current = "";
  for (const line of text.split("\n")) {
    if (current.length + line.length + 1 <= limit) {
      current += line + "\n";
    } else {
      if (current.trim()) chunks.push(current.trim());
      current = line + "\n";
    }
  }
  if (current.trim()) chunks.push(current.trim());
  return chunks.length > 0 ? chunks : [text.slice(0, limit)];
}

// ─────────────────────────────────────────────
// Telegram API helpers
// ─────────────────────────────────────────────

async function tgCall(env, method, body) {
  const url = `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`;
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return resp.json();
}

async function sendMessage(env, chatId, text, replyToMessageId = null) {
  const html = markdownToTelegramHtml(plainCleanup(text));
  const body = {
    chat_id: chatId,
    text: html || text,
    parse_mode: "HTML",
    disable_web_page_preview: true,
  };
  if (replyToMessageId) body.reply_to_message_id = replyToMessageId;

  const result = await tgCall(env, "sendMessage", body);
  // Fallback to plain text if HTML parsing fails
  if (!result.ok) {
    const plainBody = {
      chat_id: chatId,
      text: text.slice(0, 4096),
      disable_web_page_preview: true,
    };
    if (replyToMessageId) plainBody.reply_to_message_id = replyToMessageId;
    return tgCall(env, "sendMessage", plainBody);
  }
  return result;
}

async function editMessage(env, chatId, messageId, text) {
  const html = markdownToTelegramHtml(plainCleanup(text));
  const body = {
    chat_id: chatId,
    message_id: messageId,
    text: html || text,
    parse_mode: "HTML",
    disable_web_page_preview: true,
  };
  const result = await tgCall(env, "editMessageText", body);
  if (!result.ok) {
    return tgCall(env, "editMessageText", {
      chat_id: chatId,
      message_id: messageId,
      text: text.slice(0, 4096),
      disable_web_page_preview: true,
    });
  }
  return result;
}

async function sendTyping(env, chatId) {
  await tgCall(env, "sendChatAction", {
    chat_id: chatId,
    action: "typing",
  });
}

// ─────────────────────────────────────────────
// Command handlers
// ─────────────────────────────────────────────

async function handleStart(env, update) {
  const userId = update.message.from.id;
  const chatId = update.message.chat.id;
  const msgId = update.message.message_id;

  if (!(await isApproved(env, userId))) {
    await sendMessage(
      env,
      chatId,
      `Access denied.\nYour user id: ${userId}\nAsk owner to approve you.`,
      msgId
    );
    return;
  }
  await sendMessage(
    env,
    chatId,
    "**Bot online.** Message bhejo.\n\nSkills ke liye `/skills` dekho.",
    msgId
  );
}

async function handleReset(env, update) {
  const userId = update.message.from.id;
  const chatId = update.message.chat.id;
  const msgId = update.message.message_id;

  if (!(await isApproved(env, userId))) {
    await sendMessage(env, chatId, "Access denied.", msgId);
    return;
  }
  await resetHistory(env, chatId);
  await sendMessage(env, chatId, "**Session reset.** Memory cleared for this chat.", msgId);
}

async function handleApprove(env, update) {
  const userId = update.message.from.id;
  const chatId = update.message.chat.id;
  const msgId = update.message.message_id;
  const args = (update.message.text || "").trim().split(/\s+/).slice(1);

  if (!isOwner(env, userId)) {
    await sendMessage(env, chatId, "Owner only.", msgId);
    return;
  }
  if (!args[0]) {
    await sendMessage(env, chatId, "Usage: `/approve user_id`", msgId);
    return;
  }
  const targetId = args[0].trim();
  if (!/^\d+$/.test(targetId)) {
    await sendMessage(env, chatId, "Invalid user id.", msgId);
    return;
  }
  await approveUser(env, targetId);
  await sendMessage(env, chatId, `Approved:\n\`${targetId}\``, msgId);
}

async function handleUnapprove(env, update) {
  const userId = update.message.from.id;
  const chatId = update.message.chat.id;
  const msgId = update.message.message_id;
  const args = (update.message.text || "").trim().split(/\s+/).slice(1);

  if (!isOwner(env, userId)) {
    await sendMessage(env, chatId, "Owner only.", msgId);
    return;
  }
  if (!args[0]) {
    await sendMessage(env, chatId, "Usage: `/unapprove user_id`", msgId);
    return;
  }
  const targetId = args[0].trim();
  if (!/^\d+$/.test(targetId)) {
    await sendMessage(env, chatId, "Invalid user id.", msgId);
    return;
  }
  if (targetId === String(env.OWNER_ID)) {
    await sendMessage(env, chatId, "Owner ko unapprove nahi kar sakte.", msgId);
    return;
  }
  await unapproveUser(env, targetId);
  await sendMessage(env, chatId, `Unapproved:\n\`${targetId}\``, msgId);
}

async function handleSetModel(env, update) {
  const userId = update.message.from.id;
  const chatId = update.message.chat.id;
  const msgId = update.message.message_id;
  const args = (update.message.text || "").trim().split(/\s+/).slice(1);

  if (!(await isApproved(env, userId))) {
    await sendMessage(env, chatId, "Access denied.", msgId);
    return;
  }
  if (!args.length) {
    await sendMessage(env, chatId, "Usage: `/setmodel model_name`", msgId);
    return;
  }
  const model = args.join(" ").trim();
  await saveModel(env, chatId, model);
  await sendMessage(env, chatId, `Model set:\n\`${model}\``, msgId);
}

async function handleSkill(env, update) {
  const userId = update.message.from.id;
  const chatId = update.message.chat.id;
  const msgId = update.message.message_id;
  const args = (update.message.text || "").trim().split(/\s+/).slice(1);

  if (!(await isApproved(env, userId))) {
    await sendMessage(env, chatId, "Access denied.", msgId);
    return;
  }

  if (!args[0]) {
    const current = (await getChatSkill(env, chatId)) || "auto";
    await sendMessage(
      env,
      chatId,
      `Current skill: \`${current}\`\n\nUsage: \`/skill <name>\`\nList: \`/skills\`\nReset: \`/skill auto\``,
      msgId
    );
    return;
  }

  const skillName = args[0].trim().toLowerCase();

  if (["none", "auto", "reset", "off"].includes(skillName)) {
    await clearChatSkill(env, chatId);
    await sendMessage(env, chatId, "Skill reset. Ab auto-detect chalega.", msgId);
    return;
  }

  if (!AVAILABLE_SKILLS[skillName]) {
    await sendMessage(
      env,
      chatId,
      `Skill \`${skillName}\` nahi mili.\n\nAvailable skills dekhne ke liye \`/skills\` karo.`,
      msgId
    );
    return;
  }

  const loadingMsg = await sendMessage(
    env,
    chatId,
    `Skill \`${skillName}\` load ho raha hai GitHub se...`,
    msgId
  );

  const skillContent = await fetchSkillContent(env, skillName);

  if (!skillContent) {
    await editMessage(
      env,
      chatId,
      loadingMsg.result.message_id,
      `Skill \`${skillName}\` fetch nahi ho payi. GitHub down ho sakta hai ya folder name galat ho sakta hai. Baad mein try karo.`
    );
    return;
  }

  await setChatSkill(env, chatId, skillName);
  const preview = skillContent.slice(0, 200).replace(/\n/g, " ").trim();
  await editMessage(
    env,
    chatId,
    loadingMsg.result.message_id,
    `**Skill activated: \`${skillName}\`**\n\n_${preview}..._\n\nAb har message mein ye skill apply hogi. Reset karne ke liye \`/skill auto\` karo.`
  );
}

async function handleSkillsList(env, update) {
  const userId = update.message.from.id;
  const chatId = update.message.chat.id;
  const msgId = update.message.message_id;

  if (!(await isApproved(env, userId))) {
    await sendMessage(env, chatId, "Access denied.", msgId);
    return;
  }

  const categories = {
    Languages: ["python", "typescript", "golang", "rust", "fastapi", "bash"],
    "Frontend/UI": ["react", "nextjs", "frontend", "ui", "vue"],
    Mobile: ["reactnative", "expo", "android"],
    "Backend/Infra": ["backend", "docker", "devops", "database", "api", "microservice"],
    Security: ["security", "hacking", "pentest"],
    "AI/LLM": ["llm", "agent", "rag", "prompt"],
    "Debug/Quality": ["debug", "refactor", "tdd", "review"],
    Planning: ["brainstorm", "fullstack", "architect", "saas", "git", "testing"],
  };

  const parts = ["**Skills** (antigravity-awesome-skills)\n"];
  for (const [cat, skills] of Object.entries(categories)) {
    parts.push(`\n**${cat}**`);
    for (const s of skills) {
      const desc = SKILL_DESCRIPTIONS[s] || "";
      parts.push(`\`/skill ${s}\` — ${desc}`);
    }
  }
  parts.push(
    "\n\n**Auto-detect:** Message mein React/Python/Docker likho, skill khud on ho jaayegi.\n**Reset:** `/skill auto`"
  );

  const full = parts.join("\n");
  const chunks = splitText(full, 3800);
  for (const chunk of chunks) {
    await sendMessage(env, chatId, chunk, msgId);
  }
}

// ─────────────────────────────────────────────
// Main message handler
// ─────────────────────────────────────────────

async function handleMessage(env, update) {
  const userId = update.message.from.id;
  const chatId = update.message.chat.id;
  const msgId = update.message.message_id;
  const text = (update.message.text || "").trim();

  if (!text) return;

  if (!(await isApproved(env, userId))) {
    await sendMessage(
      env,
      chatId,
      `Access denied.\nYour user id: ${userId}\nAsk owner to approve you.`,
      msgId
    );
    return;
  }

  // Send "..." placeholder and typing action simultaneously
  const [sentResult] = await Promise.all([
    sendMessage(env, chatId, "...", msgId),
    sendTyping(env, chatId),
  ]);

  const sentMsgId = sentResult?.result?.message_id;

  // Get model
  const model = await getModel(env, chatId);

  // Build messages
  const messages = await buildMessages(env, chatId, text);

  // Call NVIDIA API
  const response = await callNvidiaAPI(env, messages, model);
  const cleaned = plainCleanup(response);
  const chunks = splitText(cleaned, 3900);

  // Edit first chunk into the placeholder "..." message
  if (sentMsgId) {
    await editMessage(env, chatId, sentMsgId, chunks[0]);
  } else {
    await sendMessage(env, chatId, chunks[0]);
  }

  // Send additional chunks if response was long
  for (let i = 1; i < chunks.length; i++) {
    await sendMessage(env, chatId, chunks[i]);
  }

  // Save to history
  await saveMsg(env, chatId, "user", text);
  await saveMsg(env, chatId, "assistant", cleaned);
}

// ─────────────────────────────────────────────
// Main router
// ─────────────────────────────────────────────

async function handleUpdate(env, update) {
  if (!update.message || !update.message.text) return;

  const text = (update.message.text || "").trim();
  const cmd = text.split(/\s+/)[0].toLowerCase().replace(/@.*$/, "");

  if (cmd === "/start") return handleStart(env, update);
  if (cmd === "/reset") return handleReset(env, update);
  if (cmd === "/approve") return handleApprove(env, update);
  if (cmd === "/unapprove") return handleUnapprove(env, update);
  if (cmd === "/setmodel") return handleSetModel(env, update);
  if (cmd === "/skill") return handleSkill(env, update);
  if (cmd === "/skills") return handleSkillsList(env, update);

  // Not a command — treat as regular message
  if (!text.startsWith("/")) return handleMessage(env, update);
}

// ─────────────────────────────────────────────
// CF Worker entry point
// ─────────────────────────────────────────────

export default {
  async fetch(request, env) {
    // Health check
    if (request.method === "GET") {
      return new Response("OK", { status: 200 });
    }

    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    let update;
    try {
      update = await request.json();
    } catch {
      return new Response("Bad Request", { status: 400 });
    }

    // Handle update in background so Telegram doesn't retry
    // (CF Workers: use waitUntil for background tasks)
    try {
      await handleUpdate(env, update);
    } catch (e) {
      console.error("handleUpdate error:", e);
    }

    return new Response("OK", { status: 200 });
  },
};
