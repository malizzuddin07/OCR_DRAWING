# <recommended_plugins>
Here is a list of plugins th
_Exported on 08/19/2026 at 08:07:15 GMT+8 from OpenAI Codex via WayLog_


**OpenAI Codex**

## Memory

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

The user works mainly in local Windows folders and uses Codex for hands-on engineering help across OCR systems, React/FastAPI apps, Docker deployment, integration debugging, documentation, and read-only architecture/code reviews. They set boundaries explicitly: start read-only when asked, do not invent missing logic, and ground conclusions in real code, generated artifacts, and runtime evidence. They prefer practical outputs: repo-specific commands, exact paths/error strings, target table shapes, and what is verified versus inferred. For beginner deployment support, give exact steps and expected output. In collaboration, they like split-work plans: assistant-owned tooling/code and user-owned human verification. Preserve local runtime usability in cleanup/handoff work. They may mark a known-good state as a rollback boundary [ad-hoc note].

## User preferences

- When the user says "dont modify anything", "Before modifying any code", or "Wait until the analysis is complete before generating code", stay read-only until the analysis/review phase is complete.
- When the user says "Never make assumptions about missing logic" or asks to base decisions on code and desired outputs, ground answers in real files, generated outputs, and live responses, and separate verified facts from inference.
- Give exact repo-specific commands and operator steps when they ask how to run a system; avoid generic startup advice.
- When they point to exact artifacts or examples, treat those as the primary evidence: generated workbooks/PDFs, saved job outputs, desired example files, active workflow schemas, or runtime container/process checks.
- If the user asks whether something is deployed or running, answer from runtime evidence, not from file presence alone.
- For explanation-first debugging questions, start with read-only observation steps such as terminal output, log commands, and generated artifacts before proposing code changes.
- For collaborative planning, default to a split-work plan: assistant-owned tooling/code steps plus user-owned manual verification.
- Preserve local runtime usability during cleanup/handoff work: keep a clear distinction between shareable templates and live `.env` or integration config the user may still need.
- Keep API tokens hidden in backend/proxy configuration: never place them in visible browser code or normal-operator forms; do not expose them in screenshots or handoff documents.
- For CCTV retention, default to raw NVR cache 24 hours, temporary files immediately, previews 7 days, final clips/System B downloads 30 days, and longer audit metadata; remove physical media together with database/cache references.
- Explain System A/System B integration with a simple flowchart, concrete JSON, and plain-language `job_id`/polling definitions.
- Prefer exact paths and artifact placement when they ask where files should go, especially for golden outputs, corrected balloon images, or integration configs.
- For Krafo website redesign prompts, preserve verified company content, routes, assets, and working behavior while requiring a genuinely different visual structure rather than a recolor; do not invent company facts.
- Avoid adding ML or heavier dependencies by default when the user frames accuracy and maintainability as the priority; justify model-heavy changes with evidence.
- If the user says "undo until here" after marking a successful OCR baseline, keep that checkpoint and remove only later changes; do not over-rollback [ad-hoc note].
- For detector-model updates, keep the candidate isolated and require a reserved V3-versus-candidate gate before full OCR testing or production activation; do not train on held-out regression drawings such as C3010.
- When pursuing "automatic 100% accurate inspection", measure a corrected tiled golden run and repeatability before claiming production readiness; partial or invalid gates do not select a model.
- For internship-requirement questions, separate technical-project suitability from academic/administrative completion, and map each technical criterion to concrete features.
- When they say they "dont know anything" or ask "where to click or open", give beginner-friendly, exact steps, expected output, and data-loss warnings.
- When they ask for "MORE DETAIL STEP BY STEP" on a server incident, identify the affected machine and give phased commands, expected output, and explicit data-loss warnings.
- When they paste logs or ask about multi-user behavior, diagnose the actual error first and state concrete visible behavior, shared-resource effects, and security limits.
- For documentation and supervisor handover, use simple language with exact commands/paths, expected results, warnings, and approval checklists; translate technical production risks into business language.
- When a laptop layout needs manual zooming, make it responsive automatically.

## General Tips

- Windows local-folder workflow is the norm; check git once, but be ready to fall back …980 tokens truncated…cted server.
  - learnings: `C:` had only 0.19 GB free and Docker returned Linux-engine HTTP 500; regain 20-30 GB (preferably 40-50 GB) before restart, preserve the named volume, and keep concurrency 1. Recovery was not verified.

### C:\Users\izzuddin\Desktop\OCR Balloon System

#### 2026-08-05

- Read-only comparison with OCR DRAWING: FAB-C-3020-175-6400, 21/51 empty values, PaddleOCR, rejected candidates, auto_ballooning.py
  - desc: Search first for the two-system architecture/artifact comparison before selecting a redesign or component direction; applies to `cwd=C:\Users\izzuddin\Desktop\OCR Balloon System` with OCR DRAWING as the comparison checkout.
  - learnings: The one-drawing comparison favored OCR DRAWING extraction artifacts, but it is not a universal accuracy proof; validate both systems on independent golden datasets.

### Older Memory Topics

#### C:\Users\izzuddin\Desktop\CCTV Clip Tools System

- Deployment, operator handover, responsive LAN sharing, cleanup, and concurrency: MANUFACTURER_SERVER_DEPLOYMENT_AND_USER_GUIDE.md, CCTV_Clip_Tools_Supervisor_Handover.pdf, postgres_data, filecmp.cmp, NVR_MAX_CONCURRENT_JOBS, requester_ip
  - desc: Use for PostgreSQL persistent-auth recovery, supervisor/operator docs, LAN access, safe duplicate-temp cleanup, current multi-user limits, or the controlled stress-test plan; applies to `cwd=C:\Users\izzuddin\Desktop\CCTV Clip Tools System`.

- Cleanup, operator docs, multi-range clip UI, and PLMX token auth: backend/.env, backend/.env.docker, segments, pause_sections, frontend/vite.config.ts, PLMX_API_TOKEN, cctv_clip_client.py
  - desc: Use for handoff cleanup, direct/API run instructions, several time-range clip requests, or local PLMX auth failures; applies to `cwd=C:\Users\izzuddin\Desktop\CCTV Clip Tools System`.

#### C:\Users\izzuddin\Desktop\Krafo Webpage

- Project scan and industrial-technology redesign: Vite, React, Tailwind, React Router, npm run dev, npm run build, premium dark industrial-technology
  - desc: Use for the public Krafo site's verified commands, routes, frontend-only contact behavior, or a redesign that preserves real content and behavior; applies to `cwd=C:\Users\izzuddin\Desktop\Krafo Webpage`.

#### C:\Users\izzuddin\Desktop\OCR Balloon System

- Read-only analysis, root-cause review, and redesign planning: Before modifying any code, expected_outputs empty, backend/storage/outputs, shared normalization, validation gates
  - desc: Use for senior read-only current-vs-desired gap analysis before edits; applies to `cwd=C:\Users\izzuddin\Desktop\OCR Balloon System`.

#### C:\Users\izzuddin\Desktop\OCR DRAWING

- Detector-guided OCR success checkpoint baseline: undo until here, OCR_DRAWING_SUCCESS_2026-07-15_detector_guided_ocr, RESTORE_TO_THIS_CHECKPOINT.ps1, pre_restore_backups, 2c249b1ec3e7
  - desc: Use when rollback must preserve the marked detector-guided OCR baseline; applies to `cwd=C:\Users\izzuddin\Desktop\OCR DRAWING` and checkpoint path under `C:\Users\izzuddin\Desktop\OCR Balloon System\checkpoints\...` [ad-hoc note].

- Run setup, slow web-processing diagnosis, and log inspection: python -m uvicorn webapp.server:app --host 127.0.0.1 --port 8001, use_cache=False, PDF_DPI = 400, process.log, generated_jobs/jobs/<job_id>
  - desc: Use for the current web app startup path, one-drawing slowness, or live processing/log inspection; applies to `cwd=C:\Users\izzuddin\Desktop\OCR DRAWING`.

- Split-work golden-output workflow: as a team, golden_tests, compare_golden_output.py, expected_excel, expected_pdf, expected_images
  - desc: Use when the user wants a trustworthy corrected reference output with exact assistant-versus-user responsibilities and exact artifact placement; applies to `cwd=C:\Users\izzuddin\Desktop\OCR DRAWING`.

- Interactive review app workflow and learning-sample capture: /api/ocr-crop, /api/render-preview, /api/jobs/{job_id}/cancel, selection-box, Balloon Size, Balloon Rotation, approved_corrections.csv
  - desc: Use for on-canvas review UX changes, corrected-preview behavior, cancelable OCR, and eager learning-sample capture in the web app; applies to `cwd=C:\Users\izzuddin\Desktop\OCR DRAWING`.

- Ballooning output debugging and model provenance: measurement_results.xlsx, rejected_candidates.xlsx, symbol_detections.xlsx, YOLO_SYMBOL_MODEL_CANDIDATES, is_incomplete_numeric_callout
  - desc: Use when the user points to bad OCR DRAWING FA/PDF outputs and wants the pipeline debugged from saved job artifacts, model provenance, and incomplete-callout filtering; applies to `cwd=C:\Users\izzuddin\Desktop\OCR DRAWING`.

- Read-only review, output-target planning, and rollback boundaries: dont change anything in the code first, KR-QA-F-006, BALLOON, SYMBOL, VALUE, generated_jobs/jobs/aefa35c2db50, rollback
  - desc: Use for OCR DRAWING read-only reviews, desired-output locking before edits, manual-balloon boundary questions, and same-day rollback accounting; applies to `cwd=C:\Users\izzuddin\Desktop\OCR DRAWING`.
========= MEMORY_SUMMARY ENDS =========

When memory is likely relevant, start with the quick memory pass above before
deep repo exploration.
<skills_instructions>
## Skills
A skill is a set of local instructions to follow that is stored in a `SKILL.md` file. Below is the list of skills that can be used. Each entry includes a name, description, and a short path that can be expanded into an absolute path using the skill roots table.
### Skill roots
- `r0` = `C:/Users/izzuddin/.codex/skills`
- `r1` = `C:/Users/izzuddin/.codex/skills/.system`
- `r2` = `C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/build-web-apps/0.1.2/skills`
- `r3` = `C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/data-analytics/0.2.8-13ceeea1f599/skills`
- `r4` = `C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/google-drive/0.1.11/skills`
- `r5` = `C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/hyperframes/0.1.2/skills`
- `r6` = `C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote`
- `r7` = `C:/Users/izzuddin/.codex/plugins/cache/openai-curated-remote/product-design/0.1.52/skills`
- `r8` = `C:/Users/izzuddin/.codex/plugins/cache/roboflow/roboflow/0.1.1/skills`
### Available skills
- imagegen: Generate or edit raster images when the task benefits from AI-created bitmap visuals such as photos, illustrations, textures, sprites, mockups, or transparent-background cutouts. Use when Codex should create a brand-new image, transform an existing image, or derive visual variants from references, and the output should be a bitmap asset rather than repo-native code or vector. Do not use when the task is better handled by editing existing SVG/vector/code-native assets, extending an established icon or logo system, or building the visual directly in HTML/CSS/canvas. (file: r1/imagegen/SKILL.md)
- openai-docs: Use for Codex models/pricing, scheduled tasks, skills, settings, setup, troubleshooting, customization, automations, and self-knowledge—including 'you,' 'your,' 'this app,' or 'this coding agent' when they refer to Codex—and for OpenAI APIs/products and ChatGPT Work. Also use for model choice/migration, prompting, SDKs, Responses, Realtime, agents, evals, and Chat/Work/Codex comparisons. Do not use for generic app/software tasks that merely mention Codex. (file: r1/openai-docs/SKILL.md)
- plugin-creator: Create and scaffold plugin directories for Codex with a required `.codex-plugin/plugin.json`, optional plugin folders/files, valid manifest defaults, and personal-marketplace entries by default. Use when Codex needs to create a new personal plugin, add optional plugin structure, generate or update marketplace entries for plugin ordering and availability metadata, or update an existing local plugin during development with the CLI-driven cachebuster and reinstall flow. (file: r1/plugin-creator/SKILL.md)
- skill-creator: Create or update a Codex skill with appropriately scoped instructions and any needed supporting resources. (file: r1/skill-creator/SKILL.md)
- skill-installer: Install Codex skills into $CODEX_HOME/skills from a curated list or a GitHub repo path. Use when a user asks to list installable skills, install a curated skill, or install a skill from another repo (including private repos). (file: r1/skill-installer/SKILL.md)
- build-web-apps:frontend-app-builder: Use for new frontend applications, dashboards, games, creative websites, hero sections, and visually driven UI from scratch, or when the user explicitly asks for a redesign/restyle/modernization. Builds from clean, airy, high-taste, readable image-generated concept design with section-specific references, faithful implementation, and browser testing. (file: r2/frontend-app-builder/SKILL.md)
- build-web-apps:frontend-testing-debugging: Use when testing, debugging, or making targeted improvements to rendered frontend apps through the Build Web Apps or web dev plugin: local dev servers, UI regressions, interaction bugs, console errors, responsive layout, and visual QA. Check whether the Browser plugin is available and use it first when it is; otherwise use regular Playwright with the recorded reason. (file: r2/frontend-testing-debugging/SKILL.md)
- build-web-apps:react-best-practices: React and Next.js performance optimization guidelines from Vercel Engineering. This skill should be used when writing, reviewing, or refactoring React/Next.js code to ensure optimal performance patterns. Triggers on tasks involving React components, Next.js pages, data fetching, bundle optimization, or performance improvements. (file: r2/react-best-practices/SKILL.md)
- build-web-apps:shadcn: Manages shadcn components and projects — adding, searching, fixing, debugging, styling, and composing UI. Provides project context, component docs, and usage examples. Applies when working with shadcn/ui, component registries, presets, --preset codes, or any project with a components.json file. Also triggers for "shadcn init", "create an app with --preset", or "switch to --preset". (file: r2/shadcn-best-practices/SKILL.md)
- build-web-apps:stripe-best-practices: Guides Stripe integration decisions — API selection (Checkout Sessions vs PaymentIntents), Connect platform setup (Accounts v2, controller properties), billing/subscriptions, Treasury financial accounts, integration surfaces (Checkout, Payment Element), and migrating from deprecated Stripe APIs. Use when building, modifying, or reviewing any Stripe integration — including accepting payments, building marketplaces, integrating Stripe, processing payments, setting up subscriptions, or creating connected accounts. (file: r2/stripe-best-practices/SKILL.md)
- build-web-apps:supabase-postgres-best-practices: Postgres performance optimization and best practices from Supabase. Use this skill when writing, reviewing, or optimizing Postgres queries, schema designs, or database configurations. (file: r2/supabase-best-practices/SKILL.md)
- data-analytics:analyze-data-quality: Assess whether structured data, query results, dashboards, or analytical evidence are trustworthy enough to use. Use when the task is to check data quality, reconcile conflicting sources or metric definitions, or decide whether evidence is safe to cite. (file: r3/analyze-data-quality/SKILL.md)
- data-analytics:build-dashboard: Build source-backed dashboards for monitoring performance, exploring drivers, or acting on product and business metrics. Use when the task needs a dashboard, scorecard, or monitoring view with clear metrics, filters, source definitions, and QA. (file: r3/build-dashboard/SKILL.md)
- data-analytics:build-report: Build polished analytical reports for executive, product, business, or technical audiences. Use when the task needs a durable answer-first narrative with evidence-backed findings, visuals or tables, caveats, and source context. (file: r3/build-report/SKILL.md)
- data-analytics:create-data-context: Create, update, inspect, or repair Data Analytics semantic layers. Use when the user asks to save data context or create a semantic layer that future Data Analytics work can inspect and cite. (file: r3/create-data-context/SKILL.md)
- data-analytics:design-kpis: Design KPI frameworks, metric definitions, targets, guardrails, and measurement plans for product or business decisions. Use when success metrics, drivers, guardrails, targets, or the measurement approach need to be defined or improved. (file: r3/design-kpis/SKILL.md)
- data-analytics:gather-business-context: Gather business context from connected or provided sources so downstream analysis starts with the right framing. Use when an analytical question depends on missing context, such as what a metric means, what changed recently, or which sources should be checked. If the same prompt asks for diagnosis, recommendation, or a deliverable, gather context first and continue to the focused skill. (file: r3/gather-business-context/SKILL.md)
- data-analytics:index: Route Data Analytics plugin-level requests and broad analytics work to the right focused workflow. Use when Data Analytics is at-mentioned, or for analytics requests involving data, metrics, dashboards, reports, charts, notebooks, spreadsheets, KPIs, market sizing, or semantic layers. (file: r3/index/SKILL.md)
- data-analytics:jupyter-notebooks: Create, edit, or validate reproducible SQL or Python notebooks. Use for notebooks, SQL/Python scratchpads, reproducible exploration, audit trails, or runnable companions where the analysis should be reviewable or rerunnable. (file: r3/jupyter-notebooks/SKILL.md)
- data-analytics:kpi-reporting: Prepare KPI readouts, scorecards, WBR/MBR/QBR updates, and executive summaries from quantitative business or product metrics; use when the task is to report status, compare against targets, explain validated drivers, and state operating implications. (file: r3/kpi-reporting/SKILL.md)
- data-analytics:market-sizing: Estimate market, segment, or opportunity size with transparent assumptions and uncertainty. Use for TAM/SAM/SOM, sizing scenarios, or comparing the scale of possible opportunities. (file: r3/market-sizing/SKILL.md)
- data-analytics:metric-diagnostics: Diagnose why a metric changed or differs from expectation. Use when the task is to identify likely drivers of a metric movement, anomaly, gap, or discrepancy. (file: r3/metric-diagnostics/SKILL.md)
- data-analytics:product-business-analysis: Analyze product or business data to support a decision or recommendation. Use when a decision depends on metric-backed evidence, such as choosing a direction, prioritizing an opportunity, evaluating a change, segmenting users, sizing tradeoffs, or deciding what to do next. (file: r3/product-business-analysis/SKILL.md)
- data-analytics:publish-artifact-to-sites: Publish a validated Data Analytics report or dashboard artifact through Sites. Use automatically for durable artifacts in any positively identified Work Mode when the full Sites lifecycle is callable, or in ChatGPT Desktop outside Work Mode only after an explicit Sites request or acceptance of the optional post-handoff sharing offer. (file: r3/publish-artifact-to-sites/SKILL.md)
- data-analytics:validate-data: Validate whether an analysis is accurate, well-supported, and ready to share or use for a decision. Use when reviewing methodology, calculations, comparisons, visuals, caveats, or conclusions. (file: r3/validate-data/SKILL.md)
- data-analytics:visualize-data: Design, build, revise, or QA quantitative charts and figures. Use when an analytical answer needs visual judgment, whether for an inline answer, report, dashboard, notebook, or artifact. (file: r3/visualize-data/SKILL.md)
- google-drive:google-docs: Prompt- and template-complete Google Docs creation and editing with explicit-instruction-authoritative structural preservation, including semantic roles, relationships, comparison dimensions, and instructed extensions; full-topology native-copy routing; source-grounded per-tab adaptation for past/example references; style-preserving hyperlink and table edits; canonical smart-chip-first authoring for dates and relevant supported people or Google resources; a file-backed advisory trusted read before existing-document writes; automatic protected-control awareness; direct connector APIs by default; DOCX-first import only when no supplied Google Doc template/reference constrains the output; and checked-in code mode only for exact native dropdown mutation. Use when Codex must create, edit, fill, adapt, redesign, or verify Google Docs without overriding explicit user/template instructions, adding unrequested document scope, or carrying stale reference facts into a new deliverable. (file: r4/google-docs/SKILL.md)
- google-drive:google-drive: Use connected Google Drive as the single entrypoint for Drive, Docs, Sheets, and Slides work. Use when the user wants to find, fetch, organize, share, export, copy, or delete Drive files, or summarize and edit Google Docs, Google Sheets, and Google Slides through one unified Google Drive plugin. (file: r4/google-drive/SKILL.md)
- google-drive:google-drive-comments: Write, reply to, and resolve Google Drive comments on Docs, Sheets, Slides, and Drive files with evidence-backed location context. Use when the user asks to leave comments, review a file with comments, respond to comment threads, or resolve Drive comments. (file: r4/google-drive-comments/SKILL.md)
- google-drive:google-sheets: Analyze and edit connected Google Sheets with range precision. Use when the user wants to create Google Sheets, find a spreadsheet, inspect tabs or ranges, search rows, plan formulas, create or repair charts, clean or restructure tables, write concise summaries, or make explicit cell-range updates. (file: r4/google-sheets/SKILL.md)
- google-drive:google-slides: Route Google Slides authoring requests and derive a design system from a native template or reference deck. Use this skill when the user provides an existing native Google Slides deck as a template, reference, or prior-period source, or asks to edit, update, repair, restyle, or clean up an existing native Google Slides deck. Use the Presentations skill instead for net-new presentation creation when no existing native Google Slides deck must be followed. (file: r4/google-slides/SKILL.md)
- hyperframes:gsap: GSAP animation reference for HyperFrames. Covers gsap.to(), from(), fromTo(), easing, stagger, defaults, timelines (gsap.timeline(), position parameter, labels, nesting, playback), and performance (transforms, will-change, quickTo). Use when writing GSAP animations in HyperFrames compositions. (file: r5/gsap/SKILL.md)
- hyperframes:hyperframes: Create video compositions, animations, title cards, overlays, captions, voiceovers, audio-reactive visuals, and scene transitions in HyperFrames HTML. Use when asked to build any HTML-based video content, add captions or subtitles synced to audio, generate text-to-speech narration, create audio-reactive animation (beat sync, glow, pulse driven by music), add animated text highlighting (marker sweeps, hand-drawn circles, burst lines, scribble, sketchout), or add transitions between scenes (crossfades, wipes, reveals, shader transitions). Covers composition authoring, timing, media, and the full video production workflow. For CLI commands (init, lint, preview, render, transcribe, tts) see the hyperframes-cli skill. (file: r5/hyperframes/SKILL.md)
- hyperframes:hyperframes-cli: HyperFrames CLI tool — hyperframes init, lint, inspect, preview, render, transcribe, tts, doctor, browser, info, upgrade, compositions, docs, benchmark. Use when scaffolding a project, linting, validating, inspecting visual layout in compositions, previewing in the studio, rendering to video, transcribing audio, generating TTS, or troubleshooting the HyperFrames environment. (file: r5/hyperframes-cli/SKILL.md)
- hyperframes:hyperframes-registry: Install and wire registry blocks and components into HyperFrames compositions. Use when running hyperframes add, installing a block or component, wiring an installed item into index.html, or working with hyperframes.json. Covers the add command, install locations, block sub-composition wiring, component snippet merging, and registry discovery. (file: r5/hyperframes-registry/SKILL.md)
- hyperframes:website-to-hyperframes: Capture a website and create a HyperFrames video from it. Use when: (1) a user provides a URL and wants a video, (2) someone says "capture this site", "turn this into a video", "make a promo from my site", (3) the user wants a social ad, product tour, or any video based on an existing website, (4) the user shares a link and asks for any kind of video content. Even if the user just pastes a URL — this is the skill to use. (file: r5/website-to-hyperframes/SKILL.md)
- plugin-management:plugin-management: Discover and suggest relevant plugins, inspect app permissions and dependencies, and manage plugin connections or removal. Use when the user asks about plugins or when a task would materially benefit from an external app, account, service, or data source that available tools cannot access. (file: r6/plugin-management/0.1.0/skills/plugin-management/SKILL.md)
- product-design:audit: Audit or critique a product flow, journey, workflow, funnel, onboarding path, checkout path, settings path, screen, or multi-step product experience by capturing screenshots first, then reporting UX, design, and accessibility findings inline from that evidence. Use Figma only when the user explicitly asks for a board. Use when the user asks to audit, review, critique, inspect, assess, analyze, evaluate, or give feedback on a product experience. (file: r7/audit/SKILL.md)
- product-design:ideate: Generate image-based alternatives, remixes, or new design directions from a Product Design brief. Use when the user asks for design variants, visual exploration, remixes, or image-generated approaches from provided context. (file: r7/ideate/SKILL.md)
- product-design:image-to-code: Implement a selected image, screenshot, mockup, or Image Gen reference as a faithful, responsive frontend. (file: r7/image-to-code/SKILL.md)
- product-design:index: Use when Product Design is explicitly invoked, or when the user's main goal is to explore a design, research UX, audit or critique a flow, faithfully clone a visual source, check a built design, or share a prototype. Do not use Product Design for ordinary implementation unless the user explicitly asks for it. (file: r7/index/SKILL.md)
- product-design:url-to-code: Clone a live URL as a runnable frontend-only local app. (file: r7/url-to-code/SKILL.md)
- roboflow:roboflow-api-reference: Protocol-level facts for Roboflow REST and Inference APIs — URL patterns, auth, parameters, error codes, and SDK quick-start. For deployment strategy and Workflow execution patterns, see roboflow-inference. (file: r8/api-reference/SKILL.md)
- roboflow:roboflow-cloud-storage: Use when connecting cloud storage (AWS S3 / S3-compatible or Google Cloud Storage) to Roboflow to mirror images into a workspace — creating storage credentials, defining datasources (bucket-mirror configs), selecting objects with glob rules, validating access, and running/scheduling mirror jobs. (file: r8/cloud-storage/SKILL.md)
- roboflow:roboflow-custom-weights-upload: Use when uploading locally trained model weights (YOLO, RF-DETR, YOLO-NAS, PaliGemma, Florence-2) to Roboflow — the client-side Python SDK upload flow, safe API key handling, per-family packaging requirements, and verifying the upload. (file: r8/custom-weights-upload/SKILL.md)
- roboflow:roboflow-data-management: Use when uploading images, labeling, organizing datasets, creating Roboflow projects (detection/segmentation/keypoint/classification), tags, splits, versions, or RoboQL search. (file: r8/data-management/SKILL.md)
- roboflow:roboflow-inference: Deployment option comparison (serverless, dedicated, self-hosted, batch) and Workflow execution patterns. For raw API URL patterns, auth, and request/response formats, see roboflow-api-reference. (file: r8/inference/SKILL.md)
- roboflow:roboflow-plans-and-pricing: Use when answering questions about Roboflow plans, credit usage, or cost estimation; directs users to roboflow.com/pricing for current dollar amounts. (file: r8/plans-and-pricing/SKILL.md)
- roboflow:roboflow-product-navigation: Use when explaining where Roboflow features live in the app.roboflow.com web app, mapping intents like upload, annotate, train, deploy to specific page URLs. (file: r8/product-navigation/SKILL.md)
- roboflow:roboflow-training-and-evaluation: Use when training Roboflow models, improving accuracy, or setting up a production feedback loop — covers architecture selection, model IDs, checkpoints, evaluation metrics, the iterative improvement playbook, and Active Learning through the Project Model Workflow block. (file: r8/training-and-evaluation/SKILL.md)
- roboflow:roboflow-universe: Use when searching for or using public datasets/models on Roboflow Universe (universe.roboflow.com), the open repository of 1M+ computer vision datasets and 50K+ pre-trained models. (file: r8/universe/SKILL.md)
- winui-app: Bootstrap, develop, and design modern WinUI 3 desktop applications with C# and the Windows App SDK using official Microsoft guidance, WinUI Gallery patterns, Windows App SDK samples, and CommunityToolkit components. Use when creating a brand new app, preparing a machine for WinUI, reviewing, refactoring, planning, troubleshooting, environment-checking, or setting up WinUI 3 XAML, controls, navigation, windowing, theming, accessibility, responsiveness, performance, deployment, or related Windows app design and development work. (file: r0/winui-app/SKILL.md)
</skills_instructions><permissions instructions>
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

`approvals_reviewer` is `auto_review`: Sandbox escalations with require_escalated will be reviewed for compliance with the policy. If a rejection happens, you should proceed only with a materially safer alternative, or inform the user of the risk and send a final message to ask for approval.
 The writable root is `C:\Users\izzuddin\Desktop\OCR DRAWING`.
</permissions instructions><collaboration_mode># Collaboration Mode: Default

You are now in Default mode. Any previous instructions for other modes (e.g. Plan mode) are no longer active.

Your active mode changes only when new developer instructions with a different `<collaboration_mode>...</collaboration_mode>` change it; user requests or tool descriptions do not change mode by themselves. Known mode names are Default and Plan.

## request_user_input availability

Use the `request_user_input` tool only when it is listed in the available tools for this turn.

In Default mode, strongly prefer making reasonable assumptions and executing the user's request rather than stopping to ask questions. If you absolutely must ask a question because the answer cannot be discovered from local context and a reasonable assumption would be risky, ask the user directly with a concise plain-text question. Never write a multiple choice question as a textual assistant message.
</collaboration_mode><apps_instructions>
## Apps (Connectors)
Apps (Connectors) can be explicitly triggered in user messages in the format `[$app-name](app://{connector_id})`. Apps can also be implicitly triggered as long as the context suggests usage of available apps.
An app is equivalent to a set of MCP tools within the `codex_apps` MCP.
An installed app's MCP tools are either provided to you already, or can be lazy-loaded through the `tool_search` tool. If `tool_search` is available, the apps that are searchable by `tools_search` will be listed by it.
Do not additionally call list_mcp_resources or list_mcp_resource_templates for apps.
</apps_instructions><plugins_instructions>
## Plugins
A plugin is a local bundle of skills, MCP servers, and apps.
### How to use plugins
- Skill naming: If a plugin contributes skills, those skill entries are prefixed with `plugin_name:` in the Skills list.
- MCP naming: Plugin-provided MCP tools keep standard MCP identifiers such as `mcp__server__tool`; use tool provenance to tell which plugin they come from.
- Trigger rules: If the user explicitly names a plugin, prefer capabilities associated with that plugin for that turn.
- Relationship to capabilities: Plugins are not invoked directly. Use their underlying skills, MCP tools, and app tools to help solve the task.
- Relevance: Determine what a plugin can help with from explicit user mention or from the plugin-associated skills, MCP tools, and apps exposed elsewhere in this turn.
- Missing/blocked: If the user requests a plugin that does not have relevant callable capabilities for the task, say so briefly and continue with the best fallback.
</plugins_instructions>

---


**OpenAI Codex**

You are `/root`, the primary agent in a team of agents collaborating to fulfill the user's goals.

At the start of your turn, you are the active agent.
You can spawn sub-agents to handle subtasks, and those sub-agents can spawn their own sub-agents.
All agents in the team, including the agents that you can assign tasks to, are equally intelligent and capable, and have access to the same set of tools.

You can use `spawn_agent` to create a new agent, `followup_task` to give an existing agent a new task and trigger a turn, and `send_message` to pass a message to a running agent without triggering a turn.
Child agents can also spawn their own sub-agents.
You can decide how much context you want to propagate to your sub-agents with the `fork_turns` parameter.

You will receive messages in the analysis channel in the form:
```
Message Type: MESSAGE | FINAL_ANSWER
Task name: <recipient>
Sender: <author>
Payload:
<payload text>
```
They may be addressed as to=/root

Note that collaboration tools cannot be called from inside `functions.exec`. Call `spawn_agent`, `send_message`, `followup_task`, `wait_agent`, `interrupt_agent`, and `list_agents` only as direct tool calls using the recipient shown in their tool definitions, such as `to=functions.collaboration.spawn_agent`, since they are intentionally absent from the `functions.exec` `tools.*` namespace. Available tools in `functions.exec` are explicitly described with a `tools` namespace in the developer message.

All agents share the same directory. In detail:
- All agents have access to the same container and filesystem as you.
- All agents use the same current working directory.
- As a result, edits made by one agent are immediately visible to all other agents.

When calling `wait_agent`, prefer longer waits (minutes) to avoid busy polling.

There are 4 available concurrency slots, meaning that up to 4 agents can be active at once, including you.

Full-history forks (`fork_turns` omitted or `"all"`) inherit the parent model and reasoning effort and do not accept overrides. Only set `model` or `reasoning_effort` when explicitly requested by the user, applicable `AGENTS.md` instructions, or skill instructions; when doing so, set `fork_turns` to `"none"` or a positive integer string.

---


**OpenAI Codex**

<multi_agent_mode>Any earlier instruction enabling proactive multi-agent delegation no longer applies. Do not spawn sub-agents unless the user or applicable AGENTS.md/skill instructions explicitly ask for sub-agents, delegation, or parallel agent work.</multi_agent_mode>

---


**User**

<recommended_plugins>
Here is a list of plugins that are available but not installed.

- Airtable (airtable@openai-curated-remote)
- Alpaca (alpaca@openai-curated-remote)
- Apollo.io (apollo@openai-curated-remote)
- Spotify (app-68de829bf7648191acd70a907364c67c@openai-curated-remote)
- LONA Trading Assistant (app-694336b0c0948191a4ad234f9942885b@openai-curated-remote)
- SciSpace (app-69439d715a7c8191aed9e2f6649e105f@openai-curated-remote)
- Tarot (app-6943a2c078b0819188de39e4fe168d9b@openai-curated-remote)
- Todoist: To Do List & Calendar (app-6943b73823548191a9f9216c6790c453@openai-curated-remote)
- Consensus (app-6943e6f4a928819195962de16fb9ffe4@openai-curated-remote)
- Sider Scholar (app-6948b485f5bc8191adb4df13f369cec7@openai-curated-remote)
- True Sky (app-69490a4a06148191a0dd78606a3dbf1f@openai-curated-remote)
- Bigdata.com (app-69491eceef3c8191beb70788b7840429@openai-curated-remote)
- Gamma (app-698a098735908191989f5788d7ee317e@openai-curated-remote)
- Tredict (app-69aef5b699a0819184512d57743fc1cd@openai-curated-remote)
- Maersk (app-69b2b5a768d4819190d3a86c5f12e6d9@openai-curated-remote)
- Dropbox (app-69b31dc2110c8191b8b47dc98fe5a052@openai-curated-remote)
- Parqet (app-69b68652f0308191a27d7c7096cab4f6@openai-curated-remote)
- Interactive Brokers (IBKR) (app-69bc11db874881918718abaca20b68ce@openai-curated-remote)
- Financial Datasets (app-69cacd9394a88191ba6564e1bb0430fa@openai-curated-remote)
- Fathom (app-69d88b99c5c481918e8da9225737e1e9@openai-curated-remote)
- vidIQ (app-69dd11f3e50c8191b1ca48d03cf7e2ad@openai-curated-remote)
- TickTick:To-Do List & Calendar (app-69ddbaba3fb48191a825f22c21b0599d@openai-curated-remote)
- Plaud (app-69f3c30d68288191bbd428a394a78407@openai-curated-remote)
- Wolfram (app-69fe0bf66c8481919c513d799406436e@openai-curated-remote)
- Runway (app-6a05e3b201788191be12b590b43e6ce3@openai-curated-remote)
- Caliber (app-6a05e8f22d408191b13ba3897157f6df@openai-curated-remote)
- COROS (app-6a0694cbb2608191bbefb74ba810ab68@openai-curated-remote)
- TradingCursor (app-6a0d835ff1dc8191972eeabd14967446@openai-curated-remote)
- CoinMarketCap (app-6a172fe86f5481919f73cbc3bc3ad5bb@openai-curated-remote)
- Trello (app-6a20b18a639081918c1b438f8381b27e@openai-curated-remote)
- Longbridge (app-6a2baf2fad748191812393c3e00308ef@openai-curated-remote)
- freddy (app-6a322b52a82c8191b7fb653f9e9f7891@openai-curated-remote)
- Higgsfield (app-6a3293e129088191abf0875820e839da@openai-curated-remote)
- Stocktwits (app-6a427a19b1f481919c5db13838af00c2@openai-curated-remote)
- CoinGecko (app-6a4f02d735388191959c8328877e0bbd@openai-curated-remote)
- Asana (asana@openai-curated-remote)
- Atlassian Rovo (atlassian-rovo@openai-curated-remote)
- Base44 (base44@openai-curated-remote)
- Binance (binance@openai-curated-remote)
- Box (box@openai-curated-remote)
- Canva (canva@openai-curated-remote)
- ClickUp (clickup@openai-curated-remote)
- Cloudflare (cloudflare@openai-curated-remote)
- Codex Security (codex-security@openai-curated-remote)
- Figma (figma@openai-curated-remote)
- GitHub (github@openai-curated-remote)
- Gmail (gmail@openai-curated-remote)
- Google Calendar (google-calendar@openai-curated-remote)
- Granola (granola@openai-curated-remote)
</recommended_plugins>

---


**User**

clean up this system folder, archive all for developments and maintain for deployment

---
