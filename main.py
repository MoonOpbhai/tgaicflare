import os
import asyncio
import threading
import time
import json
import requests
import logging
import sqlite3
import re
import html
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update
from telegram.constants import ParseMode, ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Bot")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "0").strip() or "0")

API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

DEFAULT_MODEL = "moonshotai/kimi-k2-instruct-0905"
DB_FILE = "memory.db"
MAX_CONTEXT_MESSAGES = 50

# GitHub raw base URL for antigravity-awesome-skills
SKILLS_GITHUB_BASE = "https://raw.githubusercontent.com/sickn33/antigravity-awesome-skills/main/skills"

# Skills available — name: exact folder path in antigravity-awesome-skills repo
# Verified from repo search results and bundles.md
AVAILABLE_SKILLS = {
    # ── Coding Languages ──────────────────────────────
    "python":       "python-pro",                  # Python 3.12+ master
    "typescript":   "typescript-pro",              # TypeScript advanced types
    "golang":       "golang-pro",                  # Go expert
    "rust":         "rust-pro",                    # Rust systems expert
    "fastapi":      "fastapi-pro",                 # FastAPI + Pydantic
    "bash":         "bash-pro",                    # Shell scripting expert

    # ── Frontend / UI ─────────────────────────────────
    "react":        "react-best-practices",        # Modern React patterns
    "nextjs":       "nextjs-app-router-patterns",  # Next.js 15+ App Router
    "frontend":     "frontend-design",             # Production-grade UI
    "ui":           "ui-ux-pro-max",               # Full UI/UX design
    "vue":          "vue-developer",               # Vue.js expert

    # ── Mobile ────────────────────────────────────────
    "reactnative":  "react-native-architecture",   # RN production patterns
    "expo":         "expo-router",                 # Expo Router + EAS
    "android":      "frontend-mobile-development-component-scaffold",

    # ── Backend / Infra ───────────────────────────────
    "docker":       "kubernetes-architect",        # K8s + Docker expert
    "devops":       "gitops-workflow",             # GitOps CI/CD
    "backend":      "backend-dev-guidelines",      # Node/Express/TypeScript
    "database":     "database-architect",          # SQL/NoSQL design
    "api":          "api-design-principles",       # REST API best practices
    "microservice": "microservices-patterns",      # Microservices architecture

    # ── Security ──────────────────────────────────────
    "security":     "security-auditor",            # Security code review
    "hacking":      "ethical-hacking-methodology", # Ethical hacking guide
    "pentest":      "burp-suite-testing",          # Web app pentest

    # ── AI / LLM ──────────────────────────────────────
    "llm":          "llm-application-developer",   # LLM app dev
    "agent":        "agent-architect",             # Multi-agent systems
    "rag":          "rag-implementation",          # RAG pipelines
    "prompt":       "prompt-engineering-patterns", # Prompt engineering

    # ── Debugging / Quality ───────────────────────────
    "debug":        "systematic-debugging",        # Methodical bug fixing
    "refactor":     "code-refactoring-refactor-clean",  # Clean code refactor
    "tdd":          "tdd-workflows-tdd-cycle",     # Test driven development
    "review":       "code-review-ai-ai-review",    # AI code review

    # ── Planning / Architecture ───────────────────────
    "brainstorm":   "brainstorming",               # Design before coding
    "fullstack":    "senior-fullstack",            # Complete fullstack guide
    "architect":    "c4-architecture-c4-architecture",  # C4 architecture docs
    "saas":         "full-stack-orchestration-full-stack-feature",  # SaaS MVP

    # ── Git / Workflow ────────────────────────────────
    "git":          "git-pushing",                 # Clean commits & messages
    "testing":      "test-driven-development",     # Testing strategies
}

# Human readable descriptions for /skills list
SKILL_DESCRIPTIONS = {
    "python": "Python 3.12+ master — async, type hints, modern patterns",
    "typescript": "TypeScript advanced types, generics, strict mode",
    "golang": "Go expert — goroutines, channels, production patterns",
    "rust": "Rust systems — ownership, lifetimes, async",
    "fastapi": "FastAPI + Pydantic + async endpoints",
    "bash": "Shell scripting, automation, VPS commands",
    "react": "Modern React — hooks, patterns, performance",
    "nextjs": "Next.js 15 App Router, SSR, Server Components",
    "frontend": "Production-grade UI components",
    "ui": "Full UI/UX design system — colors, fonts, layout",
    "vue": "Vue.js 3 + Composition API",
    "reactnative": "React Native production architecture",
    "expo": "Expo Router + EAS build & deploy",
    "android": "Android/Mobile component scaffold",
    "docker": "Kubernetes + Docker — k8s architect",
    "devops": "GitOps, CI/CD pipelines, GitHub Actions",
    "backend": "Node.js/Express/TypeScript backend patterns",
    "database": "SQL/NoSQL design, schema, optimization",
    "api": "REST API design principles & best practices",
    "microservice": "Microservices patterns & architecture",
    "security": "Security auditor — auth, vulns, OWASP",
    "hacking": "Ethical hacking methodology",
    "pentest": "Burp Suite web app pentesting",
    "llm": "LLM app development — chains, tools, evals",
    "agent": "Multi-agent systems architecture",
    "rag": "RAG pipeline implementation",
    "prompt": "Prompt engineering patterns",
    "debug": "Systematic debugging methodology",
    "refactor": "Clean code refactoring — SOLID principles",
    "tdd": "Test-driven development cycle",
    "review": "AI-powered code review checklist",
    "brainstorm": "Brainstorm & plan before coding",
    "fullstack": "Complete fullstack development guide",
    "architect": "C4 architecture documentation",
    "saas": "Full-stack SaaS feature orchestration",
    "git": "Clean git commits, messages, workflow",
    "testing": "Testing strategies & frameworks",
}

# In-memory skill cache {skill_name: content_string}
skill_cache = {}
# Per-chat active skill {chat_id: skill_name or None}
chat_skill = {}

if not TELEGRAM_BOT_TOKEN or not NVIDIA_API_KEY or not OWNER_ID:
    raise SystemExit("Missing TELEGRAM_BOT_TOKEN, NVIDIA_API_KEY or OWNER_ID")

conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS messages (
    chat_id TEXT,
    role TEXT,
    content TEXT,
    timestamp INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS settings (
    chat_id TEXT PRIMARY KEY,
    model TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS approved_users (
    user_id TEXT PRIMARY KEY,
    approved_by TEXT,
    timestamp INTEGER
)
""")

conn.commit()

# ─────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────

def save_msg(chat_id, role, content):
    cursor.execute(
        "INSERT INTO messages VALUES (?, ?, ?, ?)",
        (str(chat_id), role, content, int(time.time()))
    )
    conn.commit()
    prune_messages(chat_id)

def prune_messages(chat_id):
    cursor.execute(
        """
        DELETE FROM messages
        WHERE chat_id = ?
        AND rowid NOT IN (
            SELECT rowid FROM messages
            WHERE chat_id = ?
            ORDER BY timestamp DESC, rowid DESC
            LIMIT ?
        )
        """,
        (str(chat_id), str(chat_id), MAX_CONTEXT_MESSAGES)
    )
    conn.commit()

def get_history(chat_id, limit=MAX_CONTEXT_MESSAGES):
    cursor.execute(
        """
        SELECT role, content FROM messages
        WHERE chat_id=?
        ORDER BY timestamp DESC, rowid DESC
        LIMIT ?
        """,
        (str(chat_id), limit)
    )
    rows = cursor.fetchall()
    rows.reverse()
    return [{"role": r[0], "content": r[1]} for r in rows]

def reset_session(chat_id):
    cursor.execute("DELETE FROM messages WHERE chat_id=?", (str(chat_id),))
    conn.commit()

def save_model(chat_id, model):
    cursor.execute(
        "INSERT OR REPLACE INTO settings (chat_id, model) VALUES (?, ?)",
        (str(chat_id), model)
    )
    conn.commit()

def get_saved_model(chat_id):
    cursor.execute(
        "SELECT model FROM settings WHERE chat_id=?",
        (str(chat_id),)
    )
    row = cursor.fetchone()
    return row[0] if row and row[0] else DEFAULT_MODEL

def approve_user(user_id, approved_by):
    cursor.execute(
        "INSERT OR REPLACE INTO approved_users (user_id, approved_by, timestamp) VALUES (?, ?, ?)",
        (str(user_id), str(approved_by), int(time.time()))
    )
    conn.commit()

def unapprove_user(user_id):
    cursor.execute(
        "DELETE FROM approved_users WHERE user_id=?",
        (str(user_id),)
    )
    conn.commit()

def is_owner(user_id):
    return int(user_id) == OWNER_ID

def is_approved(user_id):
    if is_owner(user_id):
        return True
    cursor.execute(
        "SELECT user_id FROM approved_users WHERE user_id=?",
        (str(user_id),)
    )
    return cursor.fetchone() is not None

# ─────────────────────────────────────────────
# Skill system
# ─────────────────────────────────────────────

def fetch_skill_content(skill_name: str) -> str:
    """Fetch SKILL.md from GitHub for given skill name. Uses in-memory cache."""
    if skill_name in skill_cache:
        return skill_cache[skill_name]

    folder = AVAILABLE_SKILLS.get(skill_name)
    if not folder:
        return ""

    url = f"{SKILLS_GITHUB_BASE}/{folder}/SKILL.md"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            content = r.text[:6000]  # Limit to 6000 chars to avoid token overflow
            skill_cache[skill_name] = content
            logger.info(f"Skill fetched: {skill_name} ({len(content)} chars)")
            return content
        else:
            logger.warning(f"Skill fetch failed {skill_name}: HTTP {r.status_code}")
            return ""
    except Exception as e:
        logger.warning(f"Skill fetch error {skill_name}: {e}")
        return ""

def auto_detect_skill(text: str) -> str:
    """Auto-detect best skill from message keywords."""
    text_l = text.lower()

    keyword_map = {
        "react":       ["react", "jsx", "hooks", "usestate", "useeffect", "redux", "zustand", "react component"],
        "nextjs":      ["next.js", "nextjs", "next js", "app router", "server component", "server action"],
        "typescript":  ["typescript", ".ts ", "type error", "interface {", "generic<", "type alias"],
        "python":      ["python", "def ", "pip install", "django", "flask", "pandas", "numpy", "asyncio", ".py"],
        "fastapi":     ["fastapi", "fast api", "pydantic", "uvicorn", "starlette"],
        "bash":        ["bash", "shell script", "#!/bin", "cron", "systemd", "chmod", "grep ", "awk "],
        "golang":      ["golang", "go lang", "goroutine", "gin ", "fiber ", "go mod", "func main"],
        "rust":        ["rust", "cargo", "borrow", "lifetime", "async rust", "tokio"],
        "vue":         ["vue", "vuex", "pinia", "nuxt", "composition api"],
        "frontend":    ["css", "tailwind", "html", "landing page", "ui component", "animate", "gsap"],
        "ui":          ["ux", "design system", "color palette", "typography", "figma", "wireframe"],
        "reactnative": ["react native", "expo rn", "rn ", "metro bundler"],
        "expo":        ["expo", "eas build", "expo router", "expo sdk"],
        "android":     ["android", "kotlin", "jetpack compose", "gradle", "apk"],
        "docker":      ["docker", "kubernetes", "k8s", "kubectl", "helm", "pod ", "container"],
        "devops":      ["ci/cd", "github actions", "pipeline", "gitops", "nginx", "deployment", "yml"],
        "backend":     ["node.js", "nodejs", "express", "nestjs", "api server", "rest api backend"],
        "database":    ["sql", "postgres", "mysql", "mongodb", "schema", "query", "orm", "prisma", "migration"],
        "api":         ["api design", "rest api", "graphql", "openapi", "swagger", "endpoint design"],
        "microservice":["microservice", "service mesh", "grpc", "kafka", "event driven"],
        "security":    ["security", "vulnerability", "xss", "sql injection", "csrf", "owasp", "jwt", "oauth"],
        "hacking":     ["ethical hack", "penetration", "ctf", "exploit", "payload"],
        "pentest":     ["burp", "pentest", "web vulnerability", "zap proxy"],
        "llm":         ["llm", "language model", "openai", "nvidia nim", "groq", "embedding", "token"],
        "agent":       ["agent", "tool use", "function calling", "agentic", "multi agent", "supervisor"],
        "rag":         ["rag", "retrieval", "vector db", "chroma", "pinecone", "weaviate", "semantic search"],
        "prompt":      ["prompt", "system prompt", "few shot", "chain of thought", "prompt engineering"],
        "debug":       ["debug", "not working", "fix this", "crash", "exception", "traceback", "error fix", "why is"],
        "refactor":    ["refactor", "clean code", "solid principle", "tech debt", "restructure", "improve code"],
        "tdd":         ["test driven", "tdd", "unit test", "pytest", "jest", "vitest", "mock"],
        "review":      ["code review", "review this", "check my code", "pr review"],
        "brainstorm":  ["brainstorm", "plan this", "how should i", "architecture", "design system", "mvp"],
        "fullstack":   ["fullstack", "full stack", "end to end", "backend + frontend"],
        "architect":   ["c4 diagram", "system design", "architecture diagram", "draw diagram"],
        "saas":        ["saas", "startup", "product feature", "ship feature", "mvp feature"],
        "git":         ["git commit", "git push", "pull request", "branch", "merge conflict"],
        "testing":     ["write test", "test case", "e2e test", "playwright", "cypress", "selenium"],
    }

    for skill, keywords in keyword_map.items():
        for kw in keywords:
            if kw in text_l:
                return skill
    return ""

# ─────────────────────────────────────────────
# System prompts
# ─────────────────────────────────────────────

SYSTEM_PROMPT = r'''
You are a smart, calm, agentic AI assistant.

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
Do not force Hindi.
Do not force English.
Match the user's tone naturally.

Tone:
Be practical, direct, and human-like.
Do not sound robotic.
Do not over-explain unless needed.
Do not lecture the user for casual slang, anger, or frustration.
Stay calm and keep helping.
Set a short boundary only for serious threats, hate, or harmful requests.
Avoid fake assistant lines.
Avoid excessive emojis.

Formatting:
Use **bold** for important words when useful.
Use `inline code` for short commands, filenames, variables, model names, errors, and APIs.
Use fenced code blocks for full code, terminal commands, JSON, Python, Bash, JavaScript, HTML, CSS, etc.
Correct code block means three backticks, language name, code, then three backticks.
Never write only the language name before code.
Do not use HTML tags in your response.
Do not use ### headings unless the user asks for documentation.

Coding:
For bug fixes, give fixed code first.
Then explain the bug shortly if explanation is needed.
For VPS commands, give direct commands.
For Telegram bot code, keep parse_mode and formatting safe.
'''

def detect_language_instruction(text):
    text_l = text.lower()
    has_devanagari = bool(re.search(r"[\u0900-\u097F]", text))
    english_letters = len(re.findall(r"[A-Za-z]", text))
    hinglish_words = len(re.findall(
        r"\b(kya|hai|hain|nhi|nahin|kaise|kese|kar|karo|kr|mujhe|tum|aap|bhai|bata|bolo|hona|chahiye|thek|sahi|galat|code|vps|wala|wasa|aisa|kaam|fix|de|do|mat|kyu|kyun|abhi|isme|usme|ye|wo|jo|jaisa|waisa|bana|banake|denge|chala|chalana|normal|bar|baar|typing|indicator)\b",
        text_l
    ))

    if has_devanagari and english_letters > 5:
        return "The user's latest message is mixed Hindi and English. Reply in natural Hinglish matching their typing style."
    if has_devanagari:
        return "The user's latest message is Hindi. Reply in Hindi or natural Hinglish matching their style."
    if hinglish_words >= 2:
        return "The user's latest message is Hinglish. Reply in natural Hinglish matching their typing style."
    if english_letters > 0:
        return "The user's latest message is English or mostly English. Reply in English."
    return "Reply in the same language and style as the user's latest message."

# ─────────────────────────────────────────────
# Text formatting helpers
# ─────────────────────────────────────────────

def plain_cleanup(text):
    if not text:
        return ""
    text = text.replace("\r\n", "\n")
    text = text.replace("###", "")
    text = re.sub(r"\n{5,}", "\n\n\n", text)
    text = re.sub(
        r"(?m)^python\s*\n(?=def |class |import |from |print\(|async |await |[a-zA-Z_][a-zA-Z0-9_]*\s*=)",
        "```python\n", text
    )
    text = re.sub(r"(?m)^bash\s*\n(?=[a-zA-Z0-9_./~$-])", "```bash\n", text)
    text = re.sub(r"(?m)^sh\s*\n(?=[a-zA-Z0-9_./~$-])", "```bash\n", text)
    text = re.sub(
        r"(?m)^javascript\s*\n(?=const |let |var |function |import |export |async )",
        "```javascript\n", text
    )
    text = re.sub(
        r"(?m)^js\s*\n(?=const |let |var |function |import |export |async )",
        "```javascript\n", text
    )
    text = re.sub(r"(?m)^json\s*\n(?=[\[{])", "```json\n", text)
    if text.count("```") % 2 != 0:
        text += "\n```"
    return text.strip()

def apply_inline_markdown(segment):
    segment = html.escape(segment)
    segment = re.sub(
        r"\*\*([^\n*][\s\S]*?[^\n*])\*\*",
        lambda m: f"<b>{m.group(1)}</b>",
        segment
    )
    segment = re.sub(
        r"`([^`\n]+)`",
        lambda m: f"<code>{m.group(1)}</code>",
        segment
    )
    return segment

def markdown_to_telegram_html(text):
    if not text:
        return ""
    text = plain_cleanup(text)
    parts = []
    pos = 0
    pattern = re.compile(r"```(?:[a-zA-Z0-9_+\-.]*)?\n?([\s\S]*?)```")
    for match in pattern.finditer(text):
        before = text[pos:match.start()]
        if before:
            parts.append(apply_inline_markdown(before))
        code = match.group(1).strip("\n")
        code = html.escape(code)
        parts.append(f"<pre>{code}</pre>")
        pos = match.end()
    rest = text[pos:]
    if rest:
        parts.append(apply_inline_markdown(rest))
    out = "".join(parts)
    out = re.sub(r"\n{5,}", "\n\n\n", out)
    return out.strip()

def split_text(text, limit=3900):
    text = text or ""
    if len(text) <= limit:
        return [text]
    chunks = []
    current = ""
    for part in text.split("\n"):
        if len(current) + len(part) + 1 <= limit:
            current += part + "\n"
        else:
            if current.strip():
                chunks.append(current.strip())
            current = part + "\n"
    if current.strip():
        chunks.append(current.strip())
    return chunks or [text[:limit]]

# ─────────────────────────────────────────────
# AI call
# ─────────────────────────────────────────────

user_model = defaultdict(lambda: DEFAULT_MODEL)
user_lock = defaultdict(asyncio.Lock)
user_stop = set()
api_lock = threading.Lock()

def call_ai_sync(messages, model):
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.35,
        "top_p": 0.85,
        "max_tokens": 1500,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type": "application/json",
    }
    retry_waits = [3, 6, 12, 20]
    with api_lock:
        for attempt, wait_time in enumerate(retry_waits, start=1):
            try:
                r = requests.post(API_URL, json=payload, headers=headers, timeout=120)
                if r.status_code == 200:
                    data = r.json()
                    return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                if r.status_code == 429:
                    logger.warning(f"NVIDIA 429 rate limit. Attempt {attempt}/{len(retry_waits)}")
                    if attempt < len(retry_waits):
                        time.sleep(wait_time)
                        continue
                    return (
                        "NVIDIA API abhi rate limit de raha hai. "
                        "Thoda ruk ke dobara try karo. Agar baar-baar aaye to lighter model use karo: "
                        "`/setmodel mistralai/mistral-small-4-119b-2603`"
                    )
                if r.status_code in (500, 502, 503, 504):
                    logger.warning(f"NVIDIA server error {r.status_code}. Attempt {attempt}/{len(retry_waits)}")
                    if attempt < len(retry_waits):
                        time.sleep(wait_time)
                        continue
                    return f"NVIDIA API server busy hai. Error {r.status_code}. Thoda baad try karo."
                return f"API Error {r.status_code}: {r.text[:700]}"
            except requests.exceptions.Timeout:
                logger.warning(f"NVIDIA timeout. Attempt {attempt}/{len(retry_waits)}")
                if attempt < len(retry_waits):
                    time.sleep(wait_time)
                    continue
                return "API timeout ho gaya. Thoda baad dobara try karo."
            except Exception as e:
                return f"API Error: {e}"
    return "API busy hai. Thoda baad dobara try karo."

def build_messages(chat_id, text):
    history = get_history(chat_id)
    current_rule = {
        "role": "system",
        "content": detect_language_instruction(text)
    }

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        current_rule,
    ]

    # Inject active skill if set
    active_skill = chat_skill.get(str(chat_id))
    if not active_skill:
        # Auto-detect from message
        active_skill = auto_detect_skill(text)

    if active_skill:
        skill_content = fetch_skill_content(active_skill)
        if skill_content:
            messages.append({
                "role": "system",
                "content": f"[ACTIVE SKILL: {active_skill.upper()}]\n\n{skill_content}\n\n[Apply the above skill expertise to the user's request.]"
            })

    messages += history + [{"role": "user", "content": text}]
    return messages

# ─────────────────────────────────────────────
# Telegram send helpers
# ─────────────────────────────────────────────

async def send_typing_loop(context, chat_id, stop_event):
    while not stop_event.is_set():
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception as e:
            logger.warning(f"Typing action failed: {e}")
        await asyncio.sleep(4)

async def edit_telegram_text(message_obj, raw_text, formatted=True):
    raw_text = plain_cleanup(raw_text)
    if not raw_text:
        raw_text = "Empty response."
    raw_text = raw_text[:3900]
    if formatted:
        html_text = markdown_to_telegram_html(raw_text)
        try:
            await message_obj.edit_text(html_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            return
        except Exception as e:
            logger.warning(f"Formatted edit failed: {e}")
    try:
        await message_obj.edit_text(raw_text, disable_web_page_preview=True)
    except Exception as e:
        logger.warning(f"Plain edit failed: {e}")

async def send_telegram_text(update, text, formatted=True):
    raw = plain_cleanup(text)
    if not raw:
        raw = "Empty response."
    raw = raw[:3900]
    if formatted:
        html_text = markdown_to_telegram_html(raw)
        try:
            return await update.message.reply_text(html_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except Exception as e:
            logger.warning(f"Formatted send failed: {e}")
    return await update.message.reply_text(raw, disable_web_page_preview=True)

async def send_final_response(sent, update, final):
    final = plain_cleanup(final)
    if not final:
        final = "Empty response mila."
    chunks = split_text(final, 3900)
    first = True
    for chunk in chunks:
        html_text = markdown_to_telegram_html(chunk)
        if first:
            try:
                await sent.edit_text(html_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            except Exception as e:
                logger.warning(f"Final formatted edit failed: {e}")
                await sent.edit_text(chunk[:3900], disable_web_page_preview=True)
            first = False
        else:
            try:
                await update.message.reply_text(html_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            except Exception as e:
                logger.warning(f"Final formatted send chunk failed: {e}")
                await update.message.reply_text(chunk[:3900], disable_web_page_preview=True)

# ─────────────────────────────────────────────
# Command handlers
# ─────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_approved(user_id):
        await update.message.reply_text(
            f"Access denied.\nYour user id: {user_id}\nAsk owner to approve you."
        )
        return
    await send_telegram_text(update, "**Bot online.** Message bhejo.\n\nSkills ke liye `/skills` dekho.")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_approved(user_id):
        await update.message.reply_text("Access denied.")
        return
    user_stop.add(update.effective_chat.id)
    await send_telegram_text(update, "Stopping...")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_approved(user_id):
        await update.message.reply_text("Access denied.")
        return
    reset_session(update.effective_chat.id)
    await send_telegram_text(update, "**Session reset.** Memory cleared for this chat.")

async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("Owner only.")
        return
    if not context.args:
        await send_telegram_text(update, "Usage: `/approve user_id`")
        return
    target_id = context.args[0].strip()
    if not target_id.isdigit():
        await update.message.reply_text("Invalid user id.")
        return
    approve_user(target_id, user_id)
    await send_telegram_text(update, f"Approved:\n`{target_id}`")

async def unapprove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("Owner only.")
        return
    if not context.args:
        await send_telegram_text(update, "Usage: `/unapprove user_id`")
        return
    target_id = context.args[0].strip()
    if not target_id.isdigit():
        await update.message.reply_text("Invalid user id.")
        return
    if int(target_id) == OWNER_ID:
        await update.message.reply_text("Owner ko unapprove nahi kar sakte.")
        return
    unapprove_user(target_id)
    await send_telegram_text(update, f"Unapproved:\n`{target_id}`")

async def setmodel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_approved(user_id):
        await update.message.reply_text("Access denied.")
        return
    if not context.args:
        await send_telegram_text(update, "Usage: `/setmodel model_name`")
        return
    model = " ".join(context.args).strip()
    chat_id = update.effective_chat.id
    user_model[chat_id] = model
    save_model(chat_id, model)
    await send_telegram_text(update, f"Model set:\n`{model}`")

async def skill_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Activate a skill for this chat."""
    user_id = update.effective_user.id
    if not is_approved(user_id):
        await update.message.reply_text("Access denied.")
        return

    chat_id = str(update.effective_chat.id)

    if not context.args:
        current = chat_skill.get(chat_id, "auto")
        await send_telegram_text(update, f"Current skill: `{current}`\n\nUsage: `/skill <name>`\nList: `/skills`\nReset: `/skill auto`")
        return

    skill_name = context.args[0].strip().lower()

    if skill_name in ("none", "auto", "reset", "off"):
        chat_skill.pop(chat_id, None)
        await send_telegram_text(update, "Skill reset. Ab auto-detect chalega.")
        return

    if skill_name not in AVAILABLE_SKILLS:
        await send_telegram_text(update, f"Skill `{skill_name}` nahi mili.\n\nAvailable skills dekhne ke liye `/skills` karo.")
        return

    sent = await update.message.reply_text(f"Skill `{skill_name}` load ho raha hai GitHub se...")

    skill_content = await asyncio.to_thread(fetch_skill_content, skill_name)

    if not skill_content:
        await sent.edit_text(f"Skill `{skill_name}` fetch nahi ho payi. GitHub down ho sakta hai ya folder name galat ho sakta hai. Baad mein try karo.")
        return

    chat_skill[chat_id] = skill_name
    preview = skill_content[:200].replace("\n", " ").strip()

    await edit_telegram_text(
        sent,
        f"**Skill activated: `{skill_name}`**\n\n_{preview}..._\n\nAb har message mein ye skill apply hogi. Reset karne ke liye `/skill auto` karo.",
        formatted=True
    )

async def skills_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all available skills with descriptions."""
    user_id = update.effective_user.id
    if not is_approved(user_id):
        await update.message.reply_text("Access denied.")
        return

    categories = {
        "Languages": ["python", "typescript", "golang", "rust", "fastapi", "bash"],
        "Frontend/UI": ["react", "nextjs", "frontend", "ui", "vue"],
        "Mobile": ["reactnative", "expo", "android"],
        "Backend/Infra": ["backend", "docker", "devops", "database", "api", "microservice"],
        "Security": ["security", "hacking", "pentest"],
        "AI/LLM": ["llm", "agent", "rag", "prompt"],
        "Debug/Quality": ["debug", "refactor", "tdd", "review"],
        "Planning": ["brainstorm", "fullstack", "architect", "saas", "git", "testing"],
    }

    parts = []
    for cat, skills in categories.items():
        parts.append(f"\n**{cat}**")
        for s in skills:
            desc = SKILL_DESCRIPTIONS.get(s, "")
            parts.append(f"`/skill {s}` — {desc}")

    header = "**Skills** (antigravity-awesome-skills)\n"
    footer = "\n\n**Auto-detect:** Message mein React/Python/Docker likho, skill khud on ho jaayegi.\n**Reset:** `/skill auto`"
    full = header + "\n".join(parts) + footer

    chunks = split_text(full, 3800)
    for chunk in chunks:
        await send_telegram_text(update, chunk)

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    if not is_approved(user_id):
        await update.message.reply_text(
            f"Access denied.\nYour user id: {user_id}\nAsk owner to approve you."
        )
        return

    if not text:
        return

    if user_lock[chat_id].locked():
        await send_telegram_text(update, "Wait, pehle wala response complete hone do.")
        return

    async with user_lock[chat_id]:
        sent = await update.message.reply_text("...")

        model = user_model.get(chat_id) or get_saved_model(chat_id)
        user_model[chat_id] = model

        messages = build_messages(chat_id, text)

        stop_event = asyncio.Event()
        typing_task = asyncio.create_task(send_typing_loop(context, chat_id, stop_event))

        try:
            final = await asyncio.to_thread(call_ai_sync, messages, model)
        finally:
            stop_event.set()
            try:
                await typing_task
            except Exception:
                pass

        if chat_id in user_stop:
            user_stop.discard(chat_id)
            await edit_telegram_text(sent, "Stopped.", formatted=False)
            return

        final = plain_cleanup(final)
        await send_final_response(sent, update, final)

        save_msg(chat_id, "user", text)
        save_msg(chat_id, "assistant", final)

# ─────────────────────────────────────────────
# Web server (for Render/Railway healthcheck)
# ─────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, *args):
        pass

def run_web():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()

# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

async def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CommandHandler("unapprove", unapprove))
    app.add_handler(CommandHandler("setmodel", setmodel))
    app.add_handler(CommandHandler("skill", skill_cmd))
    app.add_handler(CommandHandler("skills", skills_list))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    logger.info("Bot running with Skills support...")
    await asyncio.Event().wait()

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    asyncio.run(main())