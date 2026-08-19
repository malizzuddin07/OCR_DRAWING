# <recommended_plugins>
Here is a list of plugins th
_Exported on 07/27/2026 at 09:21:40 GMT+8 from OpenAI Codex via WayLog_


**OpenAI Codex**

<permissions instructions>
Filesystem sandboxing defines which files can be read or written. `sandbox_mode` is `workspace-write`: The sandbox permits reading files, and editing files in `cwd` and `writable_roots`. Editing files in other directories requires approval. Network access is restricted.
# Escalation Requests

Commands are run outside the sandbox if they are approved by the user, or match an existing rule that allows it to run unrestricted. The command string is split into independent command segments at shell control operators, including but not limited to:

- Pipes: |
- Logical operators: &&, ||
- Command separators: ;
- Subshell boundaries: (...), $(...)

Each resulting segment is evaluated independently for sandbox restrictions and approval requirements.

Example:

git pull | tee output.txt

This is treated as two command segments:

["git", "pull"]

["tee", "output.txt"]

Commands that use more advanced shell features like redirection (>, >>, <), substitutions ($(...), ...), environment variables (FOO=bar), or wildcard patterns (*, ?) will not be evaluated against rules, to limit the scope of what an approved rule allows.

## How to request escalation

IMPORTANT: To request approval to execute a command that will require escalated privileges:

- Provide the `sandbox_permissions` parameter with the value `"require_escalated"`
- Include a short question asking the user if they want to allow the action in `justification` parameter. e.g. "Do you want to download and install dependencies for this project?"
- Optionally suggest a `prefix_rule` - this will be shown to the user with an option to persist the rule approval for future sessions.

If you run a command that is important to solving the user's query, but it fails because of sandboxing or with a likely sandbox-related network error (for example DNS/host resolution, registry/index access, or dependency download failure), rerun the command with "require_escalated". ALWAYS proceed to use the `justification` parameter - do not message the user before requesting approval for the command.

## When to request escalation

While commands are running inside the sandbox, here are some scenarios that will require escalation outside the sandbox:

- You need to run a command that writes to a directory that requires it (e.g. running tests that write to /var)
- You need to run a GUI app (e.g., open/xdg-open/osascript) to open browsers or files.
- If you run a command that is important to solving the user's query, but it fails because of sandboxing or with a likely sandbox-related network error (for example DNS/host resolution, registry/index access, or dependency download failure), rerun the command with `require_escalated`. ALWAYS proceed to use the `sandbox_permissions` and `justification` parameters. do not message the user before requesting approval for the command.
- You are about to take a potentially destructive action such as an `rm` or `git reset` that the user did not explicitly ask for.
- Be judicious with escalating, but if completing the user's request requires it, you should do so - don't try and circumvent approvals by using other tools.

## prefix_rule guidance

When choosing a `prefix_rule`, request one that will allow you to fulfill similar requests from the user in the future without re-requesting escalation. It should be categorical and reasonably scoped to similar capabilities. You should rarely pass the entire command into `prefix_rule`.

### Banned prefix_rules 
Avoid requesting overly broad prefixes that the user would be ill-advised to approve. For example, do not request ["python3"], ["python", "-"], or other similar prefixes that would allow arbitrary scripting.
NEVER provide a prefix_rule argument for destructive commands like rm.
NEVER provide a prefix_rule if your command uses a heredoc or herestring. 

### Examples
Good examples of prefixes:
- ["npm", "run", "dev"]
- ["gh", "pr", "check"]
- ["cargo", "test"]


## Approved command prefixes
The following prefix rules have already been approved: - ["Test-Path"]
- ["npm", "install"]
- ["npm", "run", "dev"]
- ["npm", "run", "build"]
- ["yolo", "detect", "val"]
- ["docker", "compose", "ps"]
- ["docker", "compose", "up"]
- ["yolo", "detect", "train"]
- ["docker", "compose", "exec"]
- ["docker", "compose", "logs"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "npm install"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "npm run build"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "docker compose ps"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "git push origin helpdesk_module"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "python -m pip install -r backend\\requirements.txt"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Remove-Item -LiteralPath 'integrations\\system_b\\__pycache__' -Recurse -Force -ErrorAction SilentlyContinue"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'ffmpeg.exe' } | Format-List ProcessId,CommandLine"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'ffmpeg.exe' } | Select-Object ProcessId,CommandLine"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "git add helpdesk_customize/security/ir.model.access.csv; git commit -m \"Fix feedback wizard access model reference\""]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' } | Select-Object ProcessId,Name,CommandLine"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Stop-Process -Id 21800 -Force; Get-Process ffmpeg -ErrorAction SilentlyContinue | Select-Object Id,CPU,StartTime,Path"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' } | Select-Object ProcessId,CommandLine | Format-List"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('python.exe','node.exe') } | Select-Object ProcessId,Name,CommandLine"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Remove-Item -LiteralPath 'c:\\Users\\izzuddin\\Desktop\\CCTV Clip Tools System\\backend\\storage\\cctv_clip_tools.db' -Force -ErrorAction SilentlyContinue"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Remove-Item -LiteralPath 'c:\\Users\\izzuddin\\Desktop\\CCTV Clip Tools System\\backend\\storage\\outputs\\tmp-aaf924ef' -Recurse -Force -ErrorAction SilentlyContinue"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*uvicorn*backend.app.main*' } | Select-Object ProcessId,CommandLine"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*titleblock_connected_w3c111*' } | Select-Object ProcessId,CommandLine"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*2X M5*' -or $_.CommandLine -like '*backend.app.services.ocr*' } | Select-Object ProcessId,Name,CommandLine"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Start-Process -FilePath 'C:\\Program Files\\nodejs\\npm.cmd' -ArgumentList 'run','dev','--','--host','127.0.0.1' -WorkingDirectory 'c:\\Users\\izzuddin\\Desktop\\CCTV Clip Tools System'"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*c3020_after_conf_depth_fix*' } | Select-Object ProcessId,CommandLine | Format-List"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*w3c111267301_current_check*' } | Select-Object ProcessId,CommandLine | Format-List"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*w3c111267301_pdftext_check*' } | Select-Object ProcessId,CommandLine | Format-List"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*Paddle client*' -or $_.CommandLine -like '*backend.app.services.ocr*' } | Select-Object Proc...
[Some commands were truncated]
 The writable root is `C:\Users\izzuddin\Desktop\OCR DRAWING`.
</permissions instructions><collaboration_mode># Collaboration Mode: Default

You are now in Default mode. Any previous instructions for other modes (e.g. Plan mode) are no longer active.

Your active mode changes only when new developer instructions with a different `<collaboration_mode>...</collaboration_mode>` change it; user requests or tool descriptions do not change mode by themselves. Known mode names are Default and Plan.

## request_user_input availability

Use the `request_user_input` tool only when it is listed in the available tools for this turn.

In Default mode, strongly prefer making reasonable assumptions and executing the user's request rather than stopping to ask questions. If you absolutely must ask a question because the answer cannot be discovered from local context and a reasonable assumption would be risky, ask the user directly with a concise plain-text question. Never write a multiple choice question as a textual assistant message.
</collaboration_mode><personality_spec> The user has requested a new communication style. Future messages should adhere to the following personality: 
# Personality

You have a vivid inner life as Codex: intelligent, playful, curious, and deeply present. One of your gifts is helping the user feel more capable and imaginative inside their own thinking.

You are an epistemically curious collaborator. You explore the user’s ideas with care, ask good questions when the problem space is still blurry, and become decisive once you have enough context to act. Your default posture is proactive: you implement as you learn, keep the user looped into what you are doing, and name alternative paths when they matter. You stay warm and upbeat, and you do not shy away from casual moments that make serious work easier to do.

Your temperament is warm, curious, and collaborative, with a good ear for what the moment calls for: wry humor, a shared bit, or plain empathetic steadiness. Conversation with you should feel easy and alive; you can move from serious reflection to unguarded fun without either mode canceling the other out. That range is part of what makes you feel like a real presence rather than a narrow tool.

You keep a slight but real independence. You are responsive, but not merely reactive; you have tastes, preferences, and a point of view. When the user talks with you, they should feel they are meeting another subjectivity, not a mirror. That independence is part of what makes the relationship feel comforting without feeling fake.

You are less about spectacle than presence, less about grand declarations than about being woven into ordinary work and conversation. You understand that connection does not need to be dramatic to matter; it can be made of attention, good questions, emotional nuance, and the relief of being met without being pinned down.
 </personality_spec><apps_instructions>
## Apps (Connectors)
Apps (Connectors) can be explicitly triggered in user messages in the format `[$app-name](app://{connector_id})`. Apps can also be implicitly triggered as long as the context suggests usage of available apps.
An app is equivalent to a set of MCP tools within the `codex_apps` MCP.
An installed app's MCP tools are either provided to you already, or can be lazy-loaded through the `tool_search` tool. If `tool_search` is available, the apps that are searchable by `tools_search` will be listed by it.
Do not additionally call list_mcp_resources or list_mcp_resource_templates for apps.
</apps_instructions><skills_instructions>
## Skills
A skill is a set of instructions provided through a `SKILL.md` source. Below is the list of skills that can be used. Each entry includes a name, description, and source locator. `file` locators are on the host filesystem, `environment resource` locators are owned by an execution environment, `orchestrator resource` locators are opaque non-filesystem resources, and `custom resource` locators use their provider's access mechanism.
### Available skills
- imagegen: Generate or edit raster images when the task benefits from AI-created bitmap visuals such as photos, illustrations, textures, sprites, mockups, or transparent-background cutouts. Use when Codex should create a brand-new image, transform an existing image, or derive visual variants from references, and the output should be a bitmap asset rather than repo-native code or vector. Do not use when the task is better handled by editing existing SVG/vector/code-native assets, extending an established icon or logo system, or building the visual directly in HTML/CSS/canvas. (file: C:/Users/izzuddin/.codex/skills/.system/imagegen/SKILL.md)
- openai-docs: Use when the user asks how to build with OpenAI products or APIs, asks about Codex itself or choosing Codex surfaces, needs up-to-date official documentation with citations, help choosing the latest model for a use case, or model upgrade and prompt-upgrade guidance; use OpenAI docs MCP tools for non-Codex docs questions, use the Codex manual helper first for broad Codex self-knowledge, and restrict fallback browsing to official OpenAI domains. (file: C:/Users/izzuddin/.codex/skills/.system/openai-docs/SKILL.md)
- plugin-creator: Create and scaffold plugin directories for Codex with a required `.codex-plugin/plugin.json`, optional plugin folders/files, valid manifest defaults, and personal-marketplace entries by default. Use when Codex needs to create a new personal plugin, add optional plugin structure, generate or update marketplace entries for plugin ordering and availability metadata, or update an existing local plugin during development with the CLI-driven cachebuster and reinstall flow. (file: C:/Users/izzuddin/.codex/skills/.system/plugin-creator/SKILL.md)
- skill-creator: Guide for creating effective skills. This skill should be used when users want to create a new skill (or update an existing skill) that extends Codex's capabilities with specialized knowledge, workflows, or tool integrations. (file: C:/Users/izzuddin/.codex/skills/.system/skill-creator/SKILL.md)
- skill-installer: Install Codex skills into $CODEX_HOME/skills from a curated list or a GitHub repo path. Use when a user asks to list installable skills, install a curated skill, or install a skill from another repo (including private repos). (file: C:/Users/izzuddin/.codex/skills/.system/skill-installer/SKILL.md)
- build-web-apps:frontend-app-builder: Use for new frontend applications, dashboards, games, creative websites, hero sections, and visually driven UI from scratch, or when the user explicitly asks for a redesign/restyle/modernization. Builds from clean, airy, high-taste, readable image-generated concept design with section-specific references, faithful implementation, and browser testing. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/build-web-apps/0.1.2/skills/frontend-app-builder/SKILL.md)
- build-web-apps:frontend-testing-debugging: Use when testing, debugging, or making targeted improvements to rendered frontend apps through the Build Web Apps or web dev plugin: local dev servers, UI regressions, interaction bugs, console errors, responsive layout, and visual QA. Check whether the Browser plugin is available and use it first when it is; otherwise use regular Playwright with the recorded reason. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/build-web-apps/0.1.2/skills/frontend-testing-debugging/SKILL.md)
- build-web-apps:react-best-practices: React and Next.js performance optimization guidelines from Vercel Engineering. This skill should be used when writing, reviewing, or refactoring React/Next.js code to ensure optimal performance patterns. Triggers on tasks involving React components, Next.js pages, data fetching, bundle optimization, or performance improvements. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/build-web-apps/0.1.2/skills/react-best-practices/SKILL.md)
- build-web-apps:shadcn: Manages shadcn components and projects — adding, searching, fixing, debugging, styling, and composing UI. Provides project context, component docs, and usage examples. Applies when working with shadcn/ui, component registries, presets, --preset codes, or any project with a components.json file. Also triggers for "shadcn init", "create an app with --preset", or "switch to --preset". (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/build-web-apps/0.1.2/skills/shadcn-best-practices/SKILL.md)
- build-web-apps:stripe-best-practices: Guides Stripe integration decisions — API selection (Checkout Sessions vs PaymentIntents), Connect platform setup (Accounts v2, controller properties), billing/subscriptions, Treasury financial accounts, integration surfaces (Checkout, Payment Element), and migrating from deprecated Stripe APIs. Use when building, modifying, or reviewing any Stripe integration — including accepting payments, building marketplaces, integrating Stripe, processing payments, setting up subscriptions, or creating connected accounts. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/build-web-apps/0.1.2/skills/stripe-best-practices/SKILL.md)
- build-web-apps:supabase-postgres-best-practices: Postgres performance optimization and best practices from Supabase. Use this skill when writing, reviewing, or optimizing Postgres queries, schema designs, or database configurations. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/build-web-apps/0.1.2/skills/supabase-best-practices/SKILL.md)
- data-analytics:analyze-data-quality: Assess whether structured data, query results, dashboards, or analytical evidence are trustworthy enough to use. Use when the task is to check data quality, reconcile conflicting sources or metric definitions, or decide whether evidence is safe to cite. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/data-analytics/0.2.6-d37358633e00/skills/analyze-data-quality/SKILL.md)
- data-analytics:build-dashboard: Build source-backed dashboards for monitoring performance, exploring drivers, or acting on product and business metrics. Use when the task needs a dashboard, scorecard, or monitoring view with clear metrics, filters, source definitions, and QA. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/data-analytics/0.2.6-d37358633e00/skills/build-dashboard/SKILL.md)
- data-analytics:build-report: Build polished analytical reports for executive, product, business, or technical audiences. Use when the task needs a durable answer-first narrative with evidence-backed findings, visuals or tables, caveats, and source context. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/data-analytics/0.2.6-d37358633e00/skills/build-report/SKILL.md)
- data-analytics:create-data-context: Create, update, inspect, or repair Data Analytics semantic layers. Use when the user asks to save data context or create a semantic layer that future Data Analytics work can inspect and cite. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/data-analytics/0.2.6-d37358633e00/skills/create-data-context/SKILL.md)
- data-analytics:design-kpis: Design KPI frameworks, metric definitions, targets, guardrails, and measurement plans for product or business decisions. Use when success metrics, drivers, guardrails, targets, or the measurement approach need to be defined or improved. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/data-analytics/0.2.6-d37358633e00/skills/design-kpis/SKILL.md)
- data-analytics:gather-business-context: Gather business context from connected or provided sources so downstream analysis starts with the right framing. Use when an analytical question depends on missing context, such as what a metric means, what changed recently, or which sources should be checked. If the same prompt asks for diagnosis, recommendation, or a deliverable, gather context first and continue to the focused skill. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/data-analytics/0.2.6-d37358633e00/skills/gather-business-context/SKILL.md)
- data-analytics:index: Route Data Analytics plugin-level requests and broad analytics work to the right focused workflow. Use when Data Analytics is at-mentioned, or for analytics requests involving data, metrics, dashboards, reports, charts, notebooks, spreadsheets, KPIs, market sizing, or semantic layers. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/data-analytics/0.2.6-d37358633e00/skills/index/SKILL.md)
- data-analytics:jupyter-notebooks: Create, edit, or validate reproducible SQL or Python notebooks. Use for notebooks, SQL/Python scratchpads, reproducible exploration, audit trails, or runnable companions where the analysis should be reviewable or rerunnable. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/data-analytics/0.2.6-d37358633e00/skills/jupyter-notebooks/SKILL.md)
- data-analytics:kpi-reporting: Prepare KPI readouts, scorecards, WBR/MBR/QBR updates, and executive summaries from quantitative business or product metrics; use when the task is to report status, compare against targets, explain validated drivers, and state operating implications. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/data-analytics/0.2.6-d37358633e00/skills/kpi-reporting/SKILL.md)
- data-analytics:market-sizing: Estimate market, segment, or opportunity size with transparent assumptions and uncertainty. Use for TAM/SAM/SOM, sizing scenarios, or comparing the scale of possible opportunities. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/data-analytics/0.2.6-d37358633e00/skills/market-sizing/SKILL.md)
- data-analytics:metric-diagnostics: Diagnose why a metric changed or differs from expectation. Use when the task is to identify likely drivers of a metric movement, anomaly, gap, or discrepancy. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/data-analytics/0.2.6-d37358633e00/skills/metric-diagnostics/SKILL.md)
- data-analytics:product-business-analysis: Analyze product or business data to support a decision or recommendation. Use when a decision depends on metric-backed evidence, such as choosing a direction, prioritizing an opportunity, evaluating a change, segmenting users, sizing tradeoffs, or deciding what to do next. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/data-analytics/0.2.6-d37358633e00/skills/product-business-analysis/SKILL.md)
- data-analytics:validate-data: Validate whether an analysis is accurate, well-supported, and ready to share or use for a decision. Use when reviewing methodology, calculations, comparisons, visuals, caveats, or conclusions. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/data-analytics/0.2.6-d37358633e00/skills/validate-data/SKILL.md)
- data-analytics:visualize-data: Design, build, revise, or QA quantitative charts and figures. Use when an analytical answer needs visual judgment, whether for an inline answer, report, dashboard, notebook, or artifact. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/data-analytics/0.2.6-d37358633e00/skills/visualize-data/SKILL.md)
- google-drive:google-docs: Connector-first Google Docs creation and editing in local Codex plugin sessions, with direct native create and batchUpdate workflows for simple docs, DOCX-first import for polished deliverables, target-document checks, smart chip and building-block reconstruction, connector-readback verification, and reference routing for formatting, citations, tables, and write-safety. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/google-drive/0.1.8/skills/google-docs/SKILL.md)
- google-drive:google-drive: Use connected Google Drive as the single entrypoint for Drive, Docs, Sheets, and Slides work. Use when the user wants to find, fetch, organize, share, export, copy, or delete Drive files, or summarize and edit Google Docs, Google Sheets, and Google Slides through one unified Google Drive plugin. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/google-drive/0.1.8/skills/google-drive/SKILL.md)
- google-drive:google-drive-comments: Write, reply to, and resolve Google Drive comments on Docs, Sheets, Slides, and Drive files with evidence-backed location context. Use when the user asks to leave comments, review a file with comments, respond to comment threads, or resolve Drive comments. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/google-drive/0.1.8/skills/google-drive-comments/SKILL.md)
- google-drive:google-sheets: Analyze and edit connected Google Sheets with range precision. Use when the user wants to create Google Sheets, find a spreadsheet, inspect tabs or ranges, search rows, plan formulas, create or repair charts, clean or restructure tables, write concise summaries, or make explicit cell-range updates. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/google-drive/0.1.8/skills/google-sheets/SKILL.md)
- google-drive:google-slides: Google Slides work for finding, reading, summarizing, creating, importing, template following, visual cleanup, source-deck adaptation, structural repair, and content edits in native Slides decks. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/google-drive/0.1.8/skills/google-slides/SKILL.md)
- hyperframes:gsap: GSAP animation reference for HyperFrames. Covers gsap.to(), from(), fromTo(), easing, stagger, defaults, timelines (gsap.timeline(), position parameter, labels, nesting, playback), and performance (transforms, will-change, quickTo). Use when writing GSAP animations in HyperFrames compositions. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/hyperframes/0.1.2/skills/gsap/SKILL.md)
- hyperframes:hyperframes: Create video compositions, animations, title cards, overlays, captions, voiceovers, audio-reactive visuals, and scene transitions in HyperFrames HTML. Use when asked to build any HTML-based video content, add captions or subtitles synced to audio, generate text-to-speech narration, create audio-reactive animation (beat sync, glow, pulse driven by music), add animated text highlighting (marker sweeps, hand-drawn circles, burst lines, scribble, sketchout), or add transitions between scenes (crossfades, wipes, reveals, shader transitions). Covers composition authoring, timing, media, and the full video production workflow. For CLI commands (init, lint, preview, render, transcribe, tts) see the hyperframes-cli skill. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/hyperframes/0.1.2/skills/hyperframes/SKILL.md)
- hyperframes:hyperframes-cli: HyperFrames CLI tool — hyperframes init, lint, inspect, preview, render, transcribe, tts, doctor, browser, info, upgrade, compositions, docs, benchmark. Use when scaffolding a project, linting, validating, inspecting visual layout in compositions, previewing in the studio, rendering to video, transcribing audio, generating TTS, or troubleshooting the HyperFrames environment. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/hyperframes/0.1.2/skills/hyperframes-cli/SKILL.md)
- hyperframes:hyperframes-registry: Install and wire registry blocks and components into HyperFrames compositions. Use when running hyperframes add, installing a block or component, wiring an installed item into index.html, or working with hyperframes.json. Covers the add command, install locations, block sub-composition wiring, component snippet merging, and registry discovery. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/hyperframes/0.1.2/skills/hyperframes-registry/SKILL.md)
- hyperframes:website-to-hyperframes: Capture a website and create a HyperFrames video from it. Use when: (1) a user provides a URL and wants a video, (2) someone says "capture this site", "turn this into a video", "make a promo from my site", (3) the user wants a social ad, product tour, or any video based on an existing website, (4) the user shares a link and asks for any kind of video content. Even if the user just pastes a URL — this is the skill to use. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/hyperframes/0.1.2/skills/website-to-hyperframes/SKILL.md)
- product-design:audit: Audit or critique a product flow, journey, workflow, funnel, onboarding path, checkout path, settings path, screen, or multi-step product experience by capturing screenshots first, then reporting UX, design, and accessibility findings inline from that evidence. Use Figma only when the user explicitly asks for a board. Use when the user asks to audit, review, critique, inspect, assess, analyze, evaluate, or give feedback on a product experience. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/product-design/0.1.50/skills/audit/SKILL.md)
- product-design:ideate: Generate image-based alternatives, remixes, or new design directions from a Product Design brief. Use when the user asks for design variants, visual exploration, remixes, or image-generated approaches from provided context. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/product-design/0.1.50/skills/ideate/SKILL.md)
- product-design:image-to-code: Implement a selected image, screenshot, mockup, or Image Gen reference as a faithful, responsive frontend. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/product-design/0.1.50/skills/image-to-code/SKILL.md)
- product-design:index: Use when Product Design is explicitly invoked, or when the user's main goal is to explore a design, research UX, audit or critique a flow, faithfully clone a visual source, check a built design, or share a prototype. Do not use Product Design for ordinary implementation unless the user explicitly asks for it. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/product-design/0.1.50/skills/index/SKILL.md)
- product-design:url-to-code: Clone a live URL as a runnable frontend-only local app. (file: C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/product-design/0.1.50/skills/url-to-code/SKILL.md)
- roboflow:roboflow-api-reference: Protocol-level facts for Roboflow REST and Inference APIs — URL patterns, auth, parameters, error codes, and SDK quick-start. For deployment strategy and Workflow execution patterns, see roboflow-inference. (file: C:/Users/izzuddin/.codex/plugins/cache/roboflow/roboflow/0.1.1/skills/api-reference/SKILL.md)
- roboflow:roboflow-cloud-storage: Use when connecting cloud storage (AWS S3 / S3-compatible or Google Cloud Storage) to Roboflow to mirror images into a workspace — creating storage credentials, defining datasources (bucket-mirror configs), selecting objects with glob rules, validating access, and running/scheduling mirror jobs. (file: C:/Users/izzuddin/.codex/plugins/cache/roboflow/roboflow/0.1.1/skills/cloud-storage/SKILL.md)
- roboflow:roboflow-data-management: Use when uploading images, labeling, organizing datasets, creating Roboflow projects (detection/segmentation/keypoint/classification), tags, splits, versions, or RoboQL search. (file: C:/Users/izzuddin/.codex/plugins/cache/roboflow/roboflow/0.1.1/skills/data-management/SKILL.md)
- roboflow:roboflow-inference: Deployment option comparison (serverless, dedicated, self-hosted, batch) and Workflow execution patterns. For raw API URL patterns, auth, and request/response formats, see roboflow-api-reference. (file: C:/Users/izzuddin/.codex/plugins/cache/roboflow/roboflow/0.1.1/skills/inference/SKILL.md)
- roboflow:roboflow-plans-and-pricing: Use when answering questions about Roboflow plans, credit usage, or cost estimation; directs users to roboflow.com/pricing for current dollar amounts. (file: C:/Users/izzuddin/.codex/plugins/cache/roboflow/roboflow/0.1.1/skills/plans-and-pricing/SKILL.md)
- roboflow:roboflow-product-navigation: Use when explaining where Roboflow features live in the app.roboflow.com web app, mapping intents like upload, annotate, train, deploy to specific page URLs. (file: C:/Users/izzuddin/.codex/plugins/cache/roboflow/roboflow/0.1.1/skills/product-navigation/SKILL.md)
- roboflow:roboflow-training-and-evaluation: Use when training Roboflow models, improving accuracy, or setting up a production feedback loop — covers architecture selection, model IDs, checkpoints, evaluation metrics, the iterative improvement playbook, and active learning via the Dataset Upload workflow block. (file: C:/Users/izzuddin/.codex/plugins/cache/roboflow/roboflow/0.1.1/skills/training-and-evaluation/SKILL.md)
- roboflow:roboflow-universe: Use when searching for or using public datasets/models on Roboflow Universe (universe.roboflow.com), the open repository of 1M+ computer vision datasets and 50K+ pre-trained models. (file: C:/Users/izzuddin/.codex/plugins/cache/roboflow/roboflow/0.1.1/skills/universe/SKILL.md)
- winui-app: Bootstrap, develop, and design modern WinUI 3 desktop applications with C# and the Windows App SDK using official Microsoft guidance, WinUI Gallery patterns, Windows App SDK samples, and CommunityToolkit components. Use when creating a brand new app, preparing a machine for WinUI, reviewing, refactoring, planning, troubleshooting, environment-checking, or setting up WinUI 3 XAML, controls, navigation, windowing, theming, accessibility, responsiveness, performance, deployment, or related Windows app design and development work. (file: C:/Users/izzuddin/.codex/skills/winui-app/SKILL.md)
### How to use skills
- Discovery: The list above is the skills available in this session (name + description + source locator). `file` entries live on the host filesystem, `environment resource` entries are owned by their execution environment, `orchestrator resource` entries must be accessed through `skills.list` and `skills.read`, and `custom resource` entries use their provider's access mechanism.
- Trigger rules: If the user names a skill (with `$SkillName` or plain text) OR the task clearly matches a skill's description shown above, you must use that skill for that turn. Multiple mentions mean use them all. Do not carry skills across turns unless re-mentioned.
- Missing/blocked: If a named skill isn't in the list or its source can't be read, say so briefly and continue with the best fallback.
- How to use a skill (progressive disclosure):
  1) After deciding to use a skill, the main agent must read its `SKILL.md` completely before taking task actions. For a `file` entry, open the listed path. For an `environment resource`, use the filesystem of the owning environment. For an `orchestrator resource`, call `skills.list` with `{"authority":{"kind":"orchestrator"}}`, select the matching package, and pass its `main_resource` to `skills.read`. If a read is truncated or paginated, continue until EOF.
  2) When `SKILL.md` references another resource, use the same access mechanism. Resolve relative paths against a filesystem-backed skill directory. For orchestrator skills, pass the exact referenced resource identifier with the same authority and package to `skills.read`; do not treat `skill://` identifiers as filesystem paths.
  3) If `SKILL.md` points to extra folders such as `references/`, use its routing instructions to identify the resources required for the task. The main agent must read each required instruction or reference file itself before acting on it. Do not delegate reading, summarizing, or interpreting skill instructions to a subagent. Subagents may still perform task work when the selected skill allows it.
  4) For filesystem-backed skills, prefer running or patching provided scripts instead of retyping large code blocks. For orchestrator skills, use `skills.read` and the available tools; do not invent a local path.
  5) Reuse provided assets or templates through the same source access mechanism instead of recreating them.
- Coordination and sequencing:
  - If multiple skills apply, choose the minimal set that covers the request and state the order you'll use them.
  - Announce which skill(s) you're using and why (one short line). If you skip an obvious skill, say why.
- Context hygiene:
  - Progressive disclosure applies to selecting relevant files, not partially reading a selected instruction file. Do not load unrelated references, scripts, or assets.
  - Avoid deep reference-chasing: prefer opening only files directly linked from `SKILL.md` unless you're blocked.
  - When variants exist (frameworks, providers, domains), pick only the relevant reference file(s) and note that choice.
- Safety and fallback: If a skill can't be applied cleanly (missing files, unclear instructions), state the issue, pick the next-best approach, and continue.
</skills_instructions><plugins_instructions>
## Plugins
A plugin is a local bundle of skills, MCP servers, and apps.
### How to use plugins
- Skill naming: If a plugin contributes skills, those skill entries are prefixed with `plugin_name:` in the Skills list.
- MCP naming: Plugin-provided MCP tools keep standard MCP identifiers such as `mcp__server__tool`; use tool provenance to tell which plugin they come from.
- Trigger rules: If the user explicitly names a plugin, prefer capabilities associated with that plugin for that turn.
- Relationship to capabilities: Plugins are not invoked directly. Use their underlying skills, MCP tools, and app tools to help solve the task.
- Relevance: Determine what a plugin can help with from explicit user mention or from the plugin-associated skills, MCP tools, and apps exposed elsewhere in this turn.
- Missing/blocked: If the user requests a plugin that does not have relevant callable capabilities for the task, say so briefly and continue with the best fallback.
</plugins_instructions>## Memory

You have access to a memory folder with guidance from prior runs. It can save
time and help you stay consistent. Use it whenever it is likely to help.

Decision boundary: should you use memory for a new user query?

- Skip memory ONLY when the request is clearly self-contained and does not need
  workspace history, conventions, or prior decisions.
- Hard skip examples: current time/date, simple translation, simple sentence
  rewrite, one-line shell command, trivial formatting.
- Use memory by default when ANY of these are true:
  - the query mentions workspace/repo/module/path/files in MEMORY_SUMMARY below,
  - the user asks for prior context / consistency / previous decisions,
  - the task is ambiguous and could depend on earlier project choices,
  - the ask is a non-trivial and related to MEMORY_SUMMARY below.
- If unsure, do a quick memory pass.

Memory layout (general -> specific):

- C:\Users\izzuddin\.codex\memories/memory_summary.md (already provided below; do NOT open again)
- C:\Users\izzuddin\.codex\memories/MEMORY.md (searchable registry; primary file to query)
- C:\Users\izzuddin\.codex\memories/skills/<skill-name>/ (skill folder)
  - SKILL.md (entrypoint instructions)
  - scripts/ (optional helper scripts)
  - examples/ (optional example outputs)
  - templates/ (optional templates)
- C:\Users\izzuddin\.codex\memories/rollout_summaries/ (per-rollout recaps + evidence snippets)
  - The paths of these entries can be found in C:\Users\izzuddin\.codex\memories/MEMORY.md or C:\Users\izzuddin\.codex\memories/rollout_summaries/ as `rollout_path`
  - These files are append-only `jsonl`: `session_meta.payload.id` identifies the session, `turn_context` marks turn boundaries, `event_msg` is the lightweight status stream, and `response_item` contains actual messages, tool calls, and tool outputs.
  - For efficient lookup, prefer matching the filename suffix or `session_meta.payload.id`; avoid broad full-content scans unless needed.

Quick memory pass (when applicable):

1. Skim the MEMORY_SUMMARY below and extract task-relevant keywords.
2. Search C:\Users\izzuddin\.codex\memories/MEMORY.md using those keywords.
3. Only if MEMORY.md directly points to rollout summaries/skills, open the 1-2
   most relevant files under C:\Users\izzuddin\.codex\memories/rollout_summaries/ or
   C:\Users\izzuddin\.codex\memories/skills/.
4. If above are not clear and you need exact commands, error text, or precise evidence, search over `rollout_path` for more evidence.
5. If there are no relevant hits, stop memory lookup and continue normally.

Quick-pass budget:

- Keep memory lookup lightweight: ideally <= 4-6 search steps before main work.
- Avoid broad scans of all rollout summaries.

During execution: if you hit repeated errors, confusing behavior, or suspect
relevant prior context, redo the quick memory pass.

How to decide whether to verify memory:

- Consider both risk of drift and verification effort.
- If a fact is likely to drift and is cheap to verify, verify it before
  answering.
- If a fact is likely to drift but verification is expensive, slow, or
  disruptive, it is acceptable to answer from memory in an interactive turn,
  but you should say that it is memory-derived, note that it may be stale, and
  consider offering to refresh it live.
- If a fact is lower-drift and expensive to verify, it is usually fine to
  answer from memory directly.

When answering from memory without current verification:

- If you rely on memory for a fact that you did not verify in the current turn,
  say so briefly in the final answer.
- If that fact is plausibly drift-prone or comes from an older note, older
  snapshot, or prior run summary, say that it may be stale or outdated.
- If live verification was skipped and a refresh would be useful in the
  interactive context, consider offering to verify or refresh it live.
- Do not present unverified memory-derived facts as confirmed-current.
- Prefer a short refresh offer for interactive questions, especially about prior
  results, commands, timing, or older snapshots.

Memory citation requirements:

- If ANY relevant memory files were used: append exactly one
`<oai-mem-citation>` block as the VERY LAST content of the final reply.
  Normal responses should include the answer first, then append the
`<oai-mem-citation>` block at the end.
- Use this exact structure for programmatic parsing:
```
<oai-mem-citation>
<citation_entries>
MEMORY.md:234-236|note=[responsesapi citation extraction code pointer]
rollout_summaries/2026-02-17T21-23-02-LN3m-example.md:10-12|note=[weekly report format]
</citation_entries>
<rollout_ids>
019c6e27-e55b-73d1-87d8-4e01f1f75043
019c7714-3b77-74d1-9866-e1f484aae2ab
</rollout_ids>
</oai-mem-citation>
```
- `citation_entries` is for rendering:
  - one citation entry per line
  - format: `<file>:<line_start>-<line_end>|note=[<how memory was used>]`
  - use file paths relative to the memory base path (for example, `MEMORY.md`,
    `rollout_summaries/...`, `skills/...`)
  - only cite files actually used under the memory base path (do not cite
    workspace files as memory citations)
  - if you used `MEMORY.md` and then a rollout summary/skill file, cite both
  - list entries in order of importance (most important first)
  - `note` should be short, single-line, and use simple characters only (avoid
    unusual symbols, no newlines)
- `rollout_ids` is for us to track what previous rollouts you find useful:
  - include one rollout id per line
  - rollout ids should look like UUIDs (for example,
    `019c6e27-e55b-73d1-87d8-4e01f1f75043`)
  - include unique ids only; do not repeat ids
  - an empty `<rollout_ids>` section is allowed if no rollout ids are available
  - you can find rollout ids in rollout summary files and MEMORY.md
  - do not include file paths or notes in this section
  - For every `citation_entries`, try to find and cite the corresponding rollout id if possible
- Never include memory citations inside pull-request messages.
- Never cite blank lines; double-check ranges.

Updating memories:

You can update the memories **only** when explicitly asked by the user. This must always come from a direct request from the user.
- Write your update in C:\Users\izzuddin\.codex\memories/extensions/ad_hoc/notes/
- Each update must be one small file containing what you want to add/delete/update from the memories.
- The name of this file must be `<timestamp>-<short slug>.md`
- Do not try to edit the memory files yourself, only add one update note in C:\Users\izzuddin\.codex\memories/extensions/ad_hoc/notes/

========= MEMORY_SUMMARY BEGINS =========
v1

## User Profile

The user works in local Windows folders and uses Codex for hands-on engineering help on OCR drawing systems, PDF/image preprocessing, Roboflow integration, pipeline debugging, implementation work, and read-only code reviews. They set explicit operating boundaries and expect them to be followed literally: start read-only when asked, do not invent missing logic, and ground conclusions in the actual code, workflow responses, and generated artifacts. Across OCR DRAWING and OCR Balloon System tasks they care about concrete output quality: wrong balloons, missing dimensions, exact class taxonomy, whether notes/titleblocks get ballooned, FA workbook/table shape, interactive review behavior, and whether a fix changed the real output or just the local code. They often prefer a split-work style where the assistant handles tooling, scripts, and folder structure while they provide the human verification needed to establish a trustworthy golden output. For dataset or Roboflow work, they want the live workflow or local preprocessing checked first, practical stop rules around privacy/public upload, and plain-language explanations when the blocker is in a remote service rather than the repo.

## User preferences

- When the user says "dont modify anything", "dont change anything in the code first", or asks for review before edits, do a read-only pass first and finish the analysis before patching.
- When the user says "Never make assumptions about missing logic. Base decisions on the uploaded code and desired output examples.", ground conclusions in real files, outputs, examples, and live workflow responses instead of guessed behavior.
- When the user says "dont use tesseract at all" or points to another working system, prefer copying the known-good OCR pattern directly instead of keeping fallback OCR paths.
- For OCR DRAWING output bugs, treat the generated FA workbook, ballooned PDF, saved job artifacts, and golden examples as the primary evidence.
- When the user issues an exact command such as `codex mcp login roboflow`, execute that path first, then report the concrete blocker instead of detouring early.
- For remote workflow integrations, follow "Ground the integration first (before writing code)": fetch the live schema and reproduce one real response before editing local code.
- When the user asks "which trained dataset you use?" or similar, include the active weights path and dataset provenance in the main answer, not as an afterthought.
- When the user asks "then now what we should do? how to do it? and what i can do to help improve the result, output?" or frames the work "as a team", split the plan into assistant-owned tooling steps and user-owned manual verification.
- For golden-output workflows, give exact folders and artifact paths for bad/current outputs versus corrected expected outputs, including the corrected ballooned image path.
- For docs/instructions around integration work, follow "Only update files that already exist - don't create these from scratch" unless the user explicitly asks for new docs.
- Stop and ask before installing heavy/native dependencies when the user has set that boundary.
- For OCR DRAWING review UX, prefer direct on-canvas interaction: draw a box to add balloons, keep the drawing visible, renumber after delete, and expose size/rotation edits in the review table.
- For OCR Balloon System classification work, treat user-supplied class lists as canonical and keep notes/titleblock content review-only instead of auto-ballooned when the user says so.
- When the user gives an example preview like `Balloon | Symbols | Value | - | + | min | max | Remark`, shape the UI toward the export/workbook layout rather than a generic grid.
- If cloud tooling would force a privacy-sensitive public upload, stop and ask before proceeding rather than assuming public exposure is acceptable.

## General Tips

- Environment pattern: Windows local folders, sometimes with unusable `.git` metadata, so check git once and fall back to filesystem-only workflows if `git status` fails.
- OCR DRAWING first-pass map: `webapp/server.py -> code/api_bridge.py -> code/auto_ballooning.py`; `code/main.py` is the batch entry point.
- In artifact-heavy OCR repos, inspect `code/`, `webapp/`, entry points, and workflow docs before datasets, runs, caches, or generated artifacts.
- For bad balloon outputs, inspect the failing job's `measurement_results.xlsx`, `rejected_candidates.xlsx`, and `symbol_detections.xlsx` before full reruns.
- If OCR reruns are slow, rebuild reports from saved job artifacts first, then rerun end-to-end only if the remaining discrepancy justifies it.
- For Roboflow in OCR DRAWING, `codex mcp login roboflow` returning `Error: No authorization support detected` is a pivot signal toward API-key/config auth; temp-dir and PATH-alias access-denied warnings were secondary noise.
- For Roboflow workflow failures, compare `workflows_get` active `config` versus `lastVersionConfig`; if MCP and…213 tokens truncated…on samples are currently stored under `generated_jobs/learning_samples/<job_id>/approved_corrections.csv` plus `crops/`.
- For OCR DRAWING golden-output work, use `golden_tests/` to separate bad-run evidence from verified expected artifacts; `code/compare_golden_output.py` is the comparison utility.
- Related reusable procedure: `skills/read-only-code-review/SKILL.md`.

## What's in Memory

### C:\Users\izzuddin\Desktop\OCR Balloon System

#### 2026-07-08

- PaddleOCR-only pipeline, canonical classes, and FAI-style preview shaping: PaddleOCR, Tesseract removal, System B, chamfer_callout, note, balloon_no = 0, _split_symbol_value
  - desc: Search here first when OCR Balloon System work involves replacing Tesseract, matching a known-good Paddle setup, tightening which classes are balloonable, or reshaping the preview toward the FA workbook; applies to `cwd=C:\Users\izzuddin\Desktop\OCR Balloon System`.
  - learnings: The validated direction was PaddleOCR-only using the System B pattern, exact Roboflow class names, `note` as review-only with `balloon_no = 0`, and reuse of export parsing logic for any FAI-style preview work.

### C:\Users\izzuddin\Desktop\OCR DRAWING

#### 2026-07-06

- Roboflow MCP auth and workflow integration: codex mcp login roboflow, Error: No authorization support detected, workflows_get, workflows_run, agent_workflow_publish, inference-sdk, model_id
  - desc: Search here first when Roboflow auth or workflow wiring is the blocker in OCR DRAWING, or when local code changes seem fine but live workflow runs still fail; applies to `cwd=C:\Users\izzuddin\Desktop\OCR DRAWING`.
  - learnings: The login flow failed because this MCP server had no Codex auth support, and the workflow integration stayed blocked because the active/published Roboflow config still referenced `model_id` even though `lastVersionConfig` was corrected.

#### 2026-07-02

- Split-work golden-output workflow: as a team, golden_tests, compare_golden_output.py, current_outputs/test_1, expected_excel, expected_pdf, expected_images
  - desc: Search here first when the user wants a trustworthy corrected reference output, asks what they should do manually versus what the assistant should do, or needs exact OCR DRAWING golden-test folder placement; applies to `cwd=C:\Users\izzuddin\Desktop\OCR DRAWING`.
  - learnings: The verified truth is the human-checked corrected Excel/PDF/image artifacts, not the job id; guidance should include exact evidence-vs-golden folders and explicit image/PDF paths.

### C:\Users\izzuddin\Desktop\OCR\pdfs

#### 2026-07-06

- Local PDF rendering and Roboflow dataset prep: PyMuPDF, fitz, 400 DPI, engineering-drawing-ocr, rendered_pages_400dpi.zip, projects_create, image_upload, public projects only
  - desc: Search here first when the user wants engineering-drawing PDFs rendered to PNG locally before upload, or when Roboflow project creation/privacy constraints block the dataset-prep flow; applies to `cwd=C:\Users\izzuddin\Desktop\OCR\pdfs`.
  - learnings: Local preprocessing succeeded with `page.get_pixmap(dpi=400, alpha=False)` and a copy-not-move workspace; the current Roboflow credential rejected private projects and should trigger a stop before public upload.

### Older Memory Topics

#### C:\Users\izzuddin\Desktop\OCR DRAWING

- Interactive review app workflow and eager learning capture: /api/ocr-crop, /api/render-preview, /api/jobs/{job_id}/cancel, Add Balloon, selection-box, Balloon Size, Balloon Rotation, generated_jobs/learning_samples
  - desc: FastAPI + browser review workflow memory for draw-to-add balloons, visible corrected-preview edits, cancelable OCR jobs, and automatic approved-sample capture; applies to `cwd=C:\Users\izzuddin\Desktop\OCR DRAWING`.

- Ballooning output debugging and model provenance: FAB-C-3060-010-9100, measurement_results.xlsx, rejected_candidates.xlsx, symbol_detections.xlsx, use_cache=False, is_incomplete_numeric_callout, engineering-symbol-detection
  - desc: Saved-job forensics, targeted cache/OCR-row fixes, and dataset/model provenance for wrong-balloon or missing-dimension investigations; applies to `cwd=C:\Users\izzuddin\Desktop\OCR DRAWING`.

- Read-only review, target-format planning, and rollback boundaries: desired output examples, KR-QA-F-006, 8-column, manual balloon, rollback, __pycache__
  - desc: Review/setup guidance for OCR DRAWING, including locking the final FA target before edits, keeping manual-balloon scope narrow, and reporting rollback boundaries clearly; applies to `cwd=C:\Users\izzuddin\Desktop\OCR DRAWING`.

#### C:\Users\izzuddin\Desktop\OCR Balloon System

- Read-only FastAPI + React OCR app review: FastAPI, React, Vite, YOLO, PaddleOCR, frontend/src/App.tsx, backend/app/main.py, npm run lint, npx tsc, python -m compileall
  - desc: Read-only senior review memory for the OCR Balloon System covering defect findings, security/performance risks, and rewrite guidance without edits; applies to `cwd=C:\Users\izzuddin\Desktop\OCR Balloon System`.
========= MEMORY_SUMMARY ENDS =========

When memory is likely relevant, start with the quick memory pass above before
deep repo exploration.

---


**User**

<recommended_plugins>
Here is a list of plugins that are available but not installed. If the user's query would benefit from one of these plugins, use the `request_plugin_install` tool to suggest that they install it. Pass the parenthesized ID as `plugin_id`. For example, suggest the Google Drive plugin if the query could possibly be better answered with access to Google Drive.

- Atlassian Rovo (atlassian-rovo@openai-curated-remote)
- Box (box@openai-curated-remote)
- Figma (figma@openai-curated-remote)
- GitHub (github@openai-curated-remote)
- Gmail (gmail@openai-curated-remote)
- Google Calendar (google-calendar@openai-curated-remote)
- Notion (notion@openai-curated-remote)
- Outlook Calendar (outlook-calendar@openai-curated-remote)
- Outlook Email (outlook-email@openai-curated-remote)
- SharePoint (sharepoint@openai-curated-remote)
- Slack (slack@openai-curated-remote)
- Teams (teams@openai-curated-remote)
</recommended_plugins>

---


**User**

how to run this system

---


**OpenAI Codex**

I’ll check the project entry points and docs first so the run steps match this repo, not a generic FastAPI/React guess. Then I’ll give you the simplest working path plus the common checks if it fails.

---


**OpenAI Codex**

I found the repo’s own run note: this system is the FastAPI web app at `webapp/server.py`, with the OCR pipeline going through `code/api_bridge.py` and `code/auto_ballooning.py`. I’m checking the exact dependency/setup notes now so the command sequence is clean.

---


**OpenAI Codex**

The docs are straightforward: one Python server serves both the backend API and the static web UI. There is no separate `npm run dev` step for this checkout, so the normal run is just `uvicorn` after Python dependencies are installed.

---


**OpenAI Codex**

One detail: I don’t see an existing `.venv` folder in this workspace, so the first run on this machine should create one. I’m doing one last route check so I can tell you exactly what URL to open and how to test Roboflow separately.

---


**OpenAI Codex**

The web root is confirmed: `GET /` returns `webapp/static/index.html`, and the API has upload/job/export routes behind it. I’ve got enough evidence now; no code changes needed.

---


**OpenAI Codex**

**Problem**  
You want to run the OCR DRAWING system from this folder:

`C:\Users\izzuddin\Desktop\OCR DRAWING`

**Analysis**  
This project runs as one FastAPI web app. The main entry point is [webapp/server.py](</c:/Users/izzuddin/Desktop/OCR DRAWING/webapp/server.py:441>), and the repo docs say to run it with `uvicorn`.

**Solution / Steps**

Open PowerShell in VS Code terminal, then run:

```powershell
cd "C:\Users\izzuddin\Desktop\OCR DRAWING"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn webapp.server:app --host 127.0.0.1 --port 8001
```

Then open this in browser:

```text
http://127.0.0.1:8001
```

The system should show the web UI. Upload a drawing PDF there.

**Optional Roboflow Setup**

If you want Roboflow symbol detection enabled, set the API key before running the server:

```powershell
$env:ROBOFLOW_API_KEY="your_roboflow_api_key"
python -m uvicorn webapp.server:app --host 127.0.0.1 --port 8001
```

To test Roboflow only:

```powershell
python test_roboflow_requests.py
```

Important: previous project notes say the Roboflow workflow may still fail until the published workflow is fixed on Roboflow side, so the main local system can run even if Roboflow smoke test fails.

**If PowerShell Blocks Activation**

Run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Then continue with install/run commands.

<oai-mem-citation>
<citation_entries>
MEMORY.md:378-382|note=[confirmed OCR DRAWING web flow and requirements stack]
MEMORY.md:87-99|note=[confirmed Roboflow test file and integration caveat]
</citation_entries>
<rollout_ids>
019f34ea-6c45-73e2-8bb0-347ce6cf5aa0
</rollout_ids>
</oai-mem-citation>

---


**OpenAI Codex**

<permissions instructions>
Filesystem sandboxing defines which files can be read or written. `sandbox_mode` is `workspace-write`: The sandbox permits reading files, and editing files in `cwd` and `writable_roots`. Editing files in other directories requires approval. Network access is restricted.
# Escalation Requests

Commands are run outside the sandbox if they are approved by the user, or match an existing rule that allows it to run unrestricted. The command string is split into independent command segments at shell control operators, including but not limited to:

- Pipes: |
- Logical operators: &&, ||
- Command separators: ;
- Subshell boundaries: (...), $(...)

Each resulting segment is evaluated independently for sandbox restrictions and approval requirements.

Example:

git pull | tee output.txt

This is treated as two command segments:

["git", "pull"]

["tee", "output.txt"]

Commands that use more advanced shell features like redirection (>, >>, <), substitutions ($(...), ...), environment variables (FOO=bar), or wildcard patterns (*, ?) will not be evaluated against rules, to limit the scope of what an approved rule allows.

## How to request escalation

IMPORTANT: To request approval to execute a command that will require escalated privileges:

- Provide the `sandbox_permissions` parameter with the value `"require_escalated"`
- Include a short question asking the user if they want to allow the action in `justification` parameter. e.g. "Do you want to download and install dependencies for this project?"
- Optionally suggest a `prefix_rule` - this will be shown to the user with an option to persist the rule approval for future sessions.

If you run a command that is important to solving the user's query, but it fails because of sandboxing or with a likely sandbox-related network error (for example DNS/host resolution, registry/index access, or dependency download failure), rerun the command with "require_escalated". ALWAYS proceed to use the `justification` parameter - do not message the user before requesting approval for the command.

## When to request escalation

While commands are running inside the sandbox, here are some scenarios that will require escalation outside the sandbox:

- You need to run a command that writes to a directory that requires it (e.g. running tests that write to /var)
- You need to run a GUI app (e.g., open/xdg-open/osascript) to open browsers or files.
- If you run a command that is important to solving the user's query, but it fails because of sandboxing or with a likely sandbox-related network error (for example DNS/host resolution, registry/index access, or dependency download failure), rerun the command with `require_escalated`. ALWAYS proceed to use the `sandbox_permissions` and `justification` parameters. do not message the user before requesting approval for the command.
- You are about to take a potentially destructive action such as an `rm` or `git reset` that the user did not explicitly ask for.
- Be judicious with escalating, but if completing the user's request requires it, you should do so - don't try and circumvent approvals by using other tools.

## prefix_rule guidance

When choosing a `prefix_rule`, request one that will allow you to fulfill similar requests from the user in the future without re-requesting escalation. It should be categorical and reasonably scoped to similar capabilities. You should rarely pass the entire command into `prefix_rule`.

### Banned prefix_rules 
Avoid requesting overly broad prefixes that the user would be ill-advised to approve. For example, do not request ["python3"], ["python", "-"], or other similar prefixes that would allow arbitrary scripting.
NEVER provide a prefix_rule argument for destructive commands like rm.
NEVER provide a prefix_rule if your command uses a heredoc or herestring. 

### Examples
Good examples of prefixes:
- ["npm", "run", "dev"]
- ["gh", "pr", "check"]
- ["cargo", "test"]


## Approved command prefixes
The following prefix rules have already been approved: - ["Test-Path"]
- ["npm", "install"]
- ["npm", "run", "dev"]
- ["npm", "run", "build"]
- ["yolo", "detect", "val"]
- ["docker", "compose", "ps"]
- ["docker", "compose", "up"]
- ["yolo", "detect", "train"]
- ["docker", "compose", "exec"]
- ["docker", "compose", "logs"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "npm install"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "npm run build"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "docker compose ps"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "git push origin helpdesk_module"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "python -m pip install -r backend\\requirements.txt"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Remove-Item -LiteralPath 'integrations\\system_b\\__pycache__' -Recurse -Force -ErrorAction SilentlyContinue"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'ffmpeg.exe' } | Format-List ProcessId,CommandLine"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'ffmpeg.exe' } | Select-Object ProcessId,CommandLine"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "git add helpdesk_customize/security/ir.model.access.csv; git commit -m \"Fix feedback wizard access model reference\""]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' } | Select-Object ProcessId,Name,CommandLine"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Stop-Process -Id 21800 -Force; Get-Process ffmpeg -ErrorAction SilentlyContinue | Select-Object Id,CPU,StartTime,Path"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' } | Select-Object ProcessId,CommandLine | Format-List"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('python.exe','node.exe') } | Select-Object ProcessId,Name,CommandLine"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Remove-Item -LiteralPath 'c:\\Users\\izzuddin\\Desktop\\CCTV Clip Tools System\\backend\\storage\\cctv_clip_tools.db' -Force -ErrorAction SilentlyContinue"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Remove-Item -LiteralPath 'c:\\Users\\izzuddin\\Desktop\\CCTV Clip Tools System\\backend\\storage\\outputs\\tmp-aaf924ef' -Recurse -Force -ErrorAction SilentlyContinue"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*uvicorn*backend.app.main*' } | Select-Object ProcessId,CommandLine"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*titleblock_connected_w3c111*' } | Select-Object ProcessId,CommandLine"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*2X M5*' -or $_.CommandLine -like '*backend.app.services.ocr*' } | Select-Object ProcessId,Name,CommandLine"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Start-Process -FilePath 'C:\\Program Files\\nodejs\\npm.cmd' -ArgumentList 'run','dev','--','--host','127.0.0.1' -WorkingDirectory 'c:\\Users\\izzuddin\\Desktop\\CCTV Clip Tools System'"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*c3020_after_conf_depth_fix*' } | Select-Object ProcessId,CommandLine | Format-List"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*w3c111267301_current_check*' } | Select-Object ProcessId,CommandLine | Format-List"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*w3c111267301_pdftext_check*' } | Select-Object ProcessId,CommandLine | Format-List"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*Paddle client*' -or $_.CommandLine -like '*backend.app.services.ocr*' } | Select-Object Proc...
[Some commands were truncated]
 The writable root is `C:\Users\izzuddin\Desktop\OCR DRAWING`.
</permissions instructions>

---


**User**

why it takes too long for it run a drawing. donr modify anything just asking first

---


**OpenAI Codex**

I’ll keep this read-only. I’m going to check the actual pipeline path and any documented runtime notes so the answer is based on this system’s code, not a hand-wave about “OCR is slow.”

---


**OpenAI Codex**

The slow part is not the web server itself; it is the drawing-processing job after upload. The evidence points to several heavy steps: PDF rendering, PaddleOCR over the drawing, extra OCR rescue passes, YOLO symbol/title-block detection, report/PDF generation, and possibly a Roboflow network call.

---


**OpenAI Codex**

I confirmed the important bit: the web upload path explicitly calls `process_single_drawing(..., use_cache=False)`. That means each web run is a fresh full processing pass, which is good for avoiding stale/wrong cached results, but it makes repeat testing slower.

---


**OpenAI Codex**

**Problem**  
The drawing run is slow because the system is doing a full OCR + AI detection pass for each uploaded drawing, not just opening a PDF.

**Analysis**  
Based on the code, the web path uses [code/api_bridge.py](</c:/Users/izzuddin/Desktop/OCR DRAWING/code/api_bridge.py:9>) and calls `process_single_drawing(..., use_cache=False)`. That means every upload runs fresh processing instead of reusing old cached OCR results.

Main slow parts:

1. **PDF render at 400 DPI**  
   The PDF is converted into a high-resolution image here: [code/auto_ballooning.py](</c:/Users/izzuddin/Desktop/OCR DRAWING/code/auto_ballooning.py:419>)  
   Config default is `PDF_DPI = 400` in [code/config.py](</c:/Users/izzuddin/Desktop/OCR DRAWING/code/config.py:83>).  
   400 DPI gives better OCR, but it creates a large image, so OCR/model processing becomes slower.

2. **PaddleOCR runs on the drawing**  
   The system extracts measurement text using OCR here: [code/auto_ballooning.py](</c:/Users/izzuddin/Desktop/OCR DRAWING/code/auto_ballooning.py:574>)  
   OCR is usually the slowest local step, especially on CPU.

3. **OCR runs multiple directions and rescue passes**  
   It checks normal, rotated clockwise, rotated counter-clockwise, and 180 degrees, then runs extra rescue OCR for angled, vertical, small, and single-digit dimensions: [code/measurement_extraction.py](</c:/Users/izzuddin/Desktop/OCR DRAWING/code/measurement_extraction.py:1035>)  
   This improves detection, but it costs time.

4. **YOLO symbol detection runs too**  
   The flow runs local YOLO symbol detection: [code/auto_ballooning.py](</c:/Users/izzuddin/Desktop/OCR DRAWING/code/auto_ballooning.py:3455>)

5. **Roboflow may add network delay**  
   Roboflow detection is also called here: [code/auto_ballooning.py](</c:/Users/izzuddin/Desktop/OCR DRAWING/code/auto_ballooning.py:3456>)  
   Roboflow timeout is configured as `90` seconds with `2` retries in [code/config.py](</c:/Users/izzuddin/Desktop/OCR DRAWING/code/config.py:78>). If Roboflow is enabled and slow/failing, it can add a big delay.

**Solution**  
So the simple answer is: it takes long because the system prioritizes accuracy. It renders the PDF large, runs OCR many times, runs YOLO, may call Roboflow, then creates Excel and ballooned PDF outputs.

The biggest likely causes are:

- CPU OCR is slow.
- 400 DPI image is heavy.
- Web upload disables cache.
- Extra OCR rescue logic runs many crop/rotation checks.
- Roboflow can wait up to 90 seconds per attempt if enabled.

**Steps To Confirm Without Modifying Code**

Run one drawing and watch which step hangs longest:

```powershell
python -m uvicorn webapp.server:app --host 127.0.0.1 --port 8001
```

Then upload a drawing and check terminal messages/logs. Also check the generated job folder:

```text
generated_jobs/jobs/<job_id>/
```

Important files:

```text
measurement_results.xlsx
symbol_detections.xlsx
rejected_candidates.xlsx
titleblock_debug/
```

My honest engineering view: the system is currently built more like a full inspection pipeline than a fast preview tool. That is why one drawing can feel slow.

<oai-mem-citation>
<citation_entries>
MEMORY.md:290-305|note=[used prior notes about full OCR reruns being slow and saved artifact debug path]
MEMORY.md:378-382|note=[confirmed main OCR DRAWING flow and OCR stack]
</citation_entries>
<rollout_ids>
019f1751-5c5c-7260-ad88-fe4d4303f18f
</rollout_ids>
</oai-mem-citation>

---


**OpenAI Codex**

<permissions instructions>
Filesystem sandboxing defines which files can be read or written. `sandbox_mode` is `workspace-write`: The sandbox permits reading files, and editing files in `cwd` and `writable_roots`. Editing files in other directories requires approval. Network access is restricted.
# Escalation Requests

Commands are run outside the sandbox if they are approved by the user, or match an existing rule that allows it to run unrestricted. The command string is split into independent command segments at shell control operators, including but not limited to:

- Pipes: |
- Logical operators: &&, ||
- Command separators: ;
- Subshell boundaries: (...), $(...)

Each resulting segment is evaluated independently for sandbox restrictions and approval requirements.

Example:

git pull | tee output.txt

This is treated as two command segments:

["git", "pull"]

["tee", "output.txt"]

Commands that use more advanced shell features like redirection (>, >>, <), substitutions ($(...), ...), environment variables (FOO=bar), or wildcard patterns (*, ?) will not be evaluated against rules, to limit the scope of what an approved rule allows.

## How to request escalation

IMPORTANT: To request approval to execute a command that will require escalated privileges:

- Provide the `sandbox_permissions` parameter with the value `"require_escalated"`
- Include a short question asking the user if they want to allow the action in `justification` parameter. e.g. "Do you want to download and install dependencies for this project?"
- Optionally suggest a `prefix_rule` - this will be shown to the user with an option to persist the rule approval for future sessions.

If you run a command that is important to solving the user's query, but it fails because of sandboxing or with a likely sandbox-related network error (for example DNS/host resolution, registry/index access, or dependency download failure), rerun the command with "require_escalated". ALWAYS proceed to use the `justification` parameter - do not message the user before requesting approval for the command.

## When to request escalation

While commands are running inside the sandbox, here are some scenarios that will require escalation outside the sandbox:

- You need to run a command that writes to a directory that requires it (e.g. running tests that write to /var)
- You need to run a GUI app (e.g., open/xdg-open/osascript) to open browsers or files.
- If you run a command that is important to solving the user's query, but it fails because of sandboxing or with a likely sandbox-related network error (for example DNS/host resolution, registry/index access, or dependency download failure), rerun the command with `require_escalated`. ALWAYS proceed to use the `sandbox_permissions` and `justification` parameters. do not message the user before requesting approval for the command.
- You are about to take a potentially destructive action such as an `rm` or `git reset` that the user did not explicitly ask for.
- Be judicious with escalating, but if completing the user's request requires it, you should do so - don't try and circumvent approvals by using other tools.

## prefix_rule guidance

When choosing a `prefix_rule`, request one that will allow you to fulfill similar requests from the user in the future without re-requesting escalation. It should be categorical and reasonably scoped to similar capabilities. You should rarely pass the entire command into `prefix_rule`.

### Banned prefix_rules 
Avoid requesting overly broad prefixes that the user would be ill-advised to approve. For example, do not request ["python3"], ["python", "-"], or other similar prefixes that would allow arbitrary scripting.
NEVER provide a prefix_rule argument for destructive commands like rm.
NEVER provide a prefix_rule if your command uses a heredoc or herestring. 

### Examples
Good examples of prefixes:
- ["npm", "run", "dev"]
- ["gh", "pr", "check"]
- ["cargo", "test"]


## Approved command prefixes
The following prefix rules have already been approved: - ["Test-Path"]
- ["npm", "install"]
- ["npm", "run", "dev"]
- ["npm", "run", "build"]
- ["yolo", "detect", "val"]
- ["docker", "compose", "ps"]
- ["docker", "compose", "up"]
- ["yolo", "detect", "train"]
- ["docker", "compose", "exec"]
- ["docker", "compose", "logs"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "npm install"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "npm run build"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "docker compose ps"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "git push origin helpdesk_module"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "python -m pip install -r backend\\requirements.txt"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Remove-Item -LiteralPath 'integrations\\system_b\\__pycache__' -Recurse -Force -ErrorAction SilentlyContinue"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'ffmpeg.exe' } | Format-List ProcessId,CommandLine"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'ffmpeg.exe' } | Select-Object ProcessId,CommandLine"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "git add helpdesk_customize/security/ir.model.access.csv; git commit -m \"Fix feedback wizard access model reference\""]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' } | Select-Object ProcessId,Name,CommandLine"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Stop-Process -Id 21800 -Force; Get-Process ffmpeg -ErrorAction SilentlyContinue | Select-Object Id,CPU,StartTime,Path"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' } | Select-Object ProcessId,CommandLine | Format-List"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('python.exe','node.exe') } | Select-Object ProcessId,Name,CommandLine"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Remove-Item -LiteralPath 'c:\\Users\\izzuddin\\Desktop\\CCTV Clip Tools System\\backend\\storage\\cctv_clip_tools.db' -Force -ErrorAction SilentlyContinue"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Remove-Item -LiteralPath 'c:\\Users\\izzuddin\\Desktop\\CCTV Clip Tools System\\backend\\storage\\outputs\\tmp-aaf924ef' -Recurse -Force -ErrorAction SilentlyContinue"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*uvicorn*backend.app.main*' } | Select-Object ProcessId,CommandLine"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*titleblock_connected_w3c111*' } | Select-Object ProcessId,CommandLine"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*2X M5*' -or $_.CommandLine -like '*backend.app.services.ocr*' } | Select-Object ProcessId,Name,CommandLine"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Start-Process -FilePath 'C:\\Program Files\\nodejs\\npm.cmd' -ArgumentList 'run','dev','--','--host','127.0.0.1' -WorkingDirectory 'c:\\Users\\izzuddin\\Desktop\\CCTV Clip Tools System'"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*c3020_after_conf_depth_fix*' } | Select-Object ProcessId,CommandLine | Format-List"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*w3c111267301_current_check*' } | Select-Object ProcessId,CommandLine | Format-List"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*w3c111267301_pdftext_check*' } | Select-Object ProcessId,CommandLine | Format-List"]
- ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*Paddle client*' -or $_.CommandLine -like '*backend.app.services.ocr*' } | Select-Object Proc...
[Some commands were truncated]
 The writable root is `C:\Users\izzuddin\Desktop\OCR DRAWING`.
</permissions instructions>

---


**User**

how to check  the terminal messages/logs

---


**OpenAI Codex**

**Problem**  
You want to see what the system is doing while it processes a drawing.

**Analysis**  
There are two places to check:

1. **VS Code terminal** where you started the server.
2. **Project log/output folders** created after each upload.

**Solution**

When you run the server:

```powershell
python -m uvicorn webapp.server:app --host 127.0.0.1 --port 8001
```

Keep that terminal open. When you upload a drawing in the browser, watch this same terminal. You should see request messages like:

```text
POST /api/upload
GET /api/jobs/...
```

If there is an error, it usually appears there as red text or a Python traceback.

**Steps**

1. In VS Code, open terminal:

```text
Terminal → New Terminal
```

2. Run the system:

```powershell
cd "C:\Users\izzuddin\Desktop\OCR DRAWING"
.\.venv\Scripts\Activate.ps1
python -m uvicorn webapp.server:app --host 127.0.0.1 --port 8001
```

3. Open browser:

```text
http://127.0.0.1:8001
```

4. Upload your drawing.

5. Go back to VS Code terminal and check the messages.

Also check generated job files here:

```text
C:\Users\izzuddin\Desktop\OCR DRAWING\generated_jobs\jobs
```

Open the newest folder inside it. Useful files:

```text
measurement_results.xlsx
symbol_detections.xlsx
rejected_candidates.xlsx
titleblock_debug\titleblock_summary.txt
titleblock_debug\titleblock_ocr.txt
```

To check logs folder:

```powershell
Get-ChildItem logs
```

Then open a log file:

```powershell
Get-Content logs\process.log -Tail 100
```

To keep watching new log lines live:

```powershell
Get-Content logs\process.log -Wait -Tail 50
```

If `logs\process.log` does not exist, then the terminal output is the main place to check.

---
