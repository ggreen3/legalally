import { mkdir, readFile, readdir, stat, writeFile } from "node:fs/promises"
import path from "node:path"

import { OpenCode } from "@opencode/sdk"

const PORT = Number(process.env.PORT || 4096)
const AGENT_KEY = process.env.AGENT_SERVICE_KEY
const WORKSPACE_ROOT = path.resolve(process.env.WORKSPACE_ROOT || "./workspaces")
const MODEL = process.env.OPENCODE_MODEL || "anthropic/claude-sonnet-5-5"
const ENABLE_BROWSER_TOOLS = process.env.ENABLE_BROWSER_TOOLS === "1"

if (!AGENT_KEY) {
  throw new Error("AGENT_SERVICE_KEY is required")
}

type Meta = {
  sessionKey: string
  tenantId: string
  mode: string
  openCodeSessionID?: string
  createdAt: string
}

type PromptBody = {
  text?: string
  mode?: string
  tenant_id?: string | number
}

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  })
}

function fail(status: number, message: string): Response {
  return json({ error: { message } }, status)
}

function safeSessionKey(value: string): boolean {
  return /^[a-zA-Z0-9_-]{8,120}$/.test(value)
}

function safeTenant(value: unknown): string {
  const text = String(value ?? "shared")
  return /^[a-zA-Z0-9_-]{1,80}$/.test(text) ? text : "shared"
}

function agentConfig(): Record<string, unknown> {
  const permissions: Array<Record<string, string>> = [
    { action: "*", resource: "*", effect: "deny" },
    { action: "read", resource: "*", effect: "allow" },
    { action: "glob", resource: "*", effect: "allow" },
    { action: "grep", resource: "*", effect: "allow" },
    { action: "edit", resource: "*", effect: "allow" },
    { action: "webfetch", resource: "http://*", effect: "allow" },
    { action: "webfetch", resource: "https://*", effect: "allow" },
    { action: "websearch", resource: "*", effect: "allow" },
    { action: "shell", resource: "*", effect: "deny" },
    { action: "subagent", resource: "*", effect: "deny" },
    { action: "question", resource: "*", effect: "deny" },
    { action: "external_directory", resource: "*", effect: "deny" },
    { action: "execute", resource: "*", effect: "deny" },
  ]

  if (ENABLE_BROWSER_TOOLS) {
    permissions.push({ action: "browser_*", resource: "*", effect: "allow" })
  }

  const config: Record<string, unknown> = {
    $schema: "https://opencode.ai/config.json",
    model: "{env:OPENCODE_MODEL}",
    default_agent: "general",
    update: "disable",
    snapshots: false,
    permissions,
    agents: {
      general: {
        mode: "primary",
        system: [
          "You are LegAlly Agent, a professional workspace assistant for legal teams in Kenya.",
          "Give practical, structured, cautious answers. Never claim to be an advocate or to provide legal advice.",
          "Do not invent statutes, case names, dates, filing rules or fees. Verify with primary sources when browsing is available.",
          "Keep client information confidential and do not expose secrets, credentials or environment files.",
          "Do not claim ownership of OpenCode or any third-party trademark, and do not imply endorsement.",
        ].join(" "),
      },
    },
    experimental: { todo: true },
  }

  if (ENABLE_BROWSER_TOOLS) {
    config.mcp = {
      servers: {
        browser: {
          type: "local",
          command: ["bunx", "@playwright/mcp"],
        },
      },
    }
  }

  return config
}

const AGENTS = `# LegAlly Agent workspace

This directory is an isolated tenant workspace created for LegAlly Agent.

Rules:
- Produce professional legal operations drafts, research notes and practical next steps.
- Treat all client information as confidential.
- Do not claim to be a lawyer or give final legal advice.
- Verify legal propositions against primary sources when tools are available.
- Never read credentials or files outside this workspace.
- Do not present OpenCode branding as LegAlly branding.
`

async function writeWorkspaceFiles(directory: string): Promise<void> {
  await mkdir(directory, { recursive: true })
  await writeFile(path.join(directory, "opencode.jsonc"), `${JSON.stringify(agentConfig(), null, 2)}\n`)
  await writeFile(path.join(directory, "AGENTS.md"), AGENTS)
}

function sessionDirectory(tenantId: string, sessionKey: string): string {
  return path.join(WORKSPACE_ROOT, tenantId, sessionKey)
}

async function readMeta(directory: string): Promise<Meta | null> {
  try {
    return JSON.parse(await readFile(path.join(directory, "meta.json"), "utf8")) as Meta
  } catch {
    return null
  }
}

async function writeMeta(directory: string, meta: Meta): Promise<void> {
  await writeFile(path.join(directory, "meta.json"), `${JSON.stringify(meta, null, 2)}\n`)
}

async function ensureSession(sessionKey: string, tenantValue: unknown, mode: string): Promise<{ directory: string; meta: Meta }> {
  if (!safeSessionKey(sessionKey)) {
    throw new Error("invalid session key")
  }
  const tenantId = safeTenant(tenantValue)
  const directory = sessionDirectory(tenantId, sessionKey)
  await writeWorkspaceFiles(directory)
  let meta = await readMeta(directory)
  if (!meta) {
    meta = {
      sessionKey,
      tenantId,
      mode,
      createdAt: new Date().toISOString(),
    }
    await writeMeta(directory, meta)
  }
  return { directory, meta }
}

function textFrom(value: unknown): string {
  const collected: string[] = []
  const visit = (input: unknown) => {
    if (typeof input === "string") {
      if (input.trim()) collected.push(input.trim())
      return
    }
    if (Array.isArray(input)) {
      input.forEach(visit)
      return
    }
    if (!input || typeof input !== "object") return
    const record = input as Record<string, unknown>
    for (const key of ["text", "content", "value"]) {
      const candidate = record[key]
      if (typeof candidate === "string" && candidate.trim()) {
        collected.push(candidate.trim())
        return
      }
    }
    Object.values(record).forEach(visit)
  }
  visit(value)
  return collected.join("\n\n").trim()
}

async function workspaceFiles(directory: string, prefix = ""): Promise<string[]> {
  const results: string[] = []
  const entries = await readdir(directory, { withFileTypes: true })
  for (const entry of entries) {
    const relative = prefix ? `${prefix}/${entry.name}` : entry.name
    if (relative.startsWith(".") || relative.includes("/.")) continue
    const full = path.join(directory, entry.name)
    if (entry.isDirectory()) {
      results.push(...(await workspaceFiles(full, relative)))
      continue
    }
    if (!entry.isFile()) continue
    if (["meta.json", "opencode.jsonc", "AGENTS.md"].includes(relative)) continue
    const info = await stat(full)
    if (info.size < 500000) results.push(relative)
  }
  return results.slice(0, 30)
}

async function authorized(request: Request): Promise<boolean> {
  return request.headers.get("x-agent-key") === AGENT_KEY
}

const server = Bun.serve({
  port: PORT,
  async fetch(request) {
    const url = new URL(request.url)

    if (url.pathname === "/health" && request.method === "GET") {
      return json({
        healthy: true,
        service: "legalally-agent",
        model: MODEL,
        browserTools: ENABLE_BROWSER_TOOLS,
        time: new Date().toISOString(),
      })
    }

    if (!(await authorized(request))) {
      return fail(401, "Invalid agent service key")
    }

    if (url.pathname === "/sessions" && request.method === "POST") {
      let body: PromptBody
      try {
        body = (await request.json()) as PromptBody
      } catch {
        return fail(400, "Invalid JSON body")
      }
      const keyFromBody = String((body as Record<string, unknown>).session_key || "")
      if (!safeSessionKey(keyFromBody)) return fail(400, "Invalid session key")
      const { directory, meta } = await ensureSession(keyFromBody, body.tenant_id, body.mode || "workspace")
      return json({ session_key: keyFromBody, directory, mode: meta.mode }, 201)
    }

    const promptMatch = url.pathname.match(/^\/sessions\/([^/]+)\/prompt$/)
    if (promptMatch && request.method === "POST") {
      const sessionKey = decodeURIComponent(promptMatch[1] || "")
      let body: PromptBody
      try {
        body = (await request.json()) as PromptBody
      } catch {
        return fail(400, "Invalid JSON body")
      }
      const text = String(body.text || "").trim()
      if (text.length < 3 || text.length > 8000) return fail(400, "Prompt must be between 3 and 8000 characters")

      try {
        const { directory, meta } = await ensureSession(sessionKey, body.tenant_id, body.mode || metaMode(body.mode))
        const opencode = await OpenCode.create()
        let sessionID = meta.openCodeSessionID
        try {
          if (!sessionID) {
            const session = await opencode.sessions.create({ location: { directory } })
            sessionID = session.id
            meta.openCodeSessionID = sessionID
            await writeMeta(directory, meta)
          }
          const result = await opencode.sessions.prompt({ sessionID, text })
          const answer = textFrom((result as Record<string, unknown>).parts ?? result)
          if (!answer) return fail(502, "The agent returned no text")
          return json({
            answer,
            session_key: sessionKey,
            files: await workspaceFiles(directory),
          })
        } finally {
          await opencode.close()
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : "Agent request failed"
        return fail(500, message)
      }
    }

    const filesMatch = url.pathname.match(/^\/sessions\/([^/]+)\/files$/)
    if (filesMatch && request.method === "GET") {
      const sessionKey = decodeURIComponent(filesMatch[1] || "")
      try {
        const { directory } = await ensureSession(sessionKey, "shared", "workspace")
        return json({ files: await workspaceFiles(directory) })
      } catch (error) {
        return fail(400, error instanceof Error ? error.message : "Invalid session")
      }
    }

    return fail(404, "Not found")
  },
})

function metaMode(mode: string | undefined): string {
  return mode && ["workspace", "drafting", "research"].includes(mode) ? mode : "workspace"
}

console.log(`LegAlly Agent service listening on http://0.0.0.0:${PORT}`)
console.log(`Model: ${MODEL}; browser tools: ${ENABLE_BROWSER_TOOLS ? "enabled" : "disabled"}`)
