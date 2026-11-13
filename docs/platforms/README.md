# Platform adapters

Matrix owns task decisions and approvals. The authenticated controller owns processes and credentials. The installed [platform guide](../../src/orchestration/PLATFORM-GUIDE.md) describes the neutral contract. A platform is supported only for its tested CLI, operating system, model and permissions configuration.

## Dated role/model observations: 2026-11-13 (0.33 evidence)

The 0.33 validation recorded the observations below using Sol 6.1 medium and Luna medium. These are dated results, not a permanent model support list. Projects assess current versions using [model-fit evidence and review conditions](../../src/orchestration/MODEL-FIT.md).

| Configuration | Actual evidence and limit |
| --- | --- |
| Sol 6.1 medium, complex engineering lead | Same dispatch scenario: baseline and candidate each 4/4, flagged criterion recheck agrees; one scenario, no live staffing or launch approval |
| Luna medium, execution instance | Bounded worker/handoff scenarios and a real concurrent built-in code worker; two resulting functions separately checked against 781 inputs each, still awaiting task acceptance |
| Luna medium, complex engineering lead | That run retained 2 failed criteria, including one 1→0 regression; Sol results do not erase these failures |
| Claude Sonnet 4.6 medium | Actual bounded import/admission and product-to-engineering handoff only; not certified for complex lead scheduling |
| Other models, hosts or role combinations | Unknown until relevant platform and professional behavior are validated |

The original selected set remains **43/45**, with the additional Sol dispatch **4/4 reported separately**. Changing a model mapping does not confer approval, professional grade or automatic task readiness. See the [release notes](../../release-notes/matrix-ai-v0.33.md) for omitted scenarios and actual source epochs.

## Codex CLI

The reference `codex-native` adapter uses Codex CLI 0.167.0 on macOS, launches in the stable instance workspace, selects the mapped model explicitly, and sets `workspace-write` with approval policy `never`. Temporary writable roots and additional writable roots are excluded. User config/rules, apps, plugins, hooks, browser/computer tools, subagent spawning and automatic host skill discovery are disabled for this dedicated worker. It reads the exact Matrix entry named in the task packet. Models used for comparison are `gpt-6.1-sol` and `gpt-6-luna`, both medium.

An outer process-wide write-deny policy prevented this CLI's own app-server initialization. The adapter therefore uses the CLI's native file/tool enforcement while the trusted controller remains outside. Native shell, direct file editing and descendant escape tests must be checked on the actual version. Do not interpret successful startup alone as isolation evidence. See the [official configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference) for workspace and permission settings.

Runner fragment (capability evidence is supplied by the deploying platform after validation):

```json
{"adapter":"codex-native","version":"0.167.0","models":{"Sol":"gpt-6.1-sol","Luna":"gpt-6-luna"},"capabilities":{"launch":{"state":"unknown"},"write_isolation":{"state":"unknown"},"model_selection":{"state":"unknown"}}}
```

The native adapter constructs the command itself; it does not accept task-provided command overrides. Existing local `launch.py` templates remain for built-in experts; imported experts use the managed controller.

## Claude Code CLI

Tested CLI: 2.1.72 on macOS; configured model `claude-sonnet-4-6`, effort medium. The reference controller wraps the entire CLI process tree in the kernel write boundary, allowing only the selected instance workspace. Run with `--setting-sources ""`, strict MCP configuration, explicit Read/Write/Bash tools, no persisted session, and `disableAllHooks`. Authentication belongs to the CLI/platform. If OAuth fails, reauthorize that CLI with `claude auth login`; browser login and `auth status` alone do not prove the service accepts its token.

```json
{"adapter":"kernel","version":"2.1.72","models":{"Sonnet":"claude-sonnet-4-6"},"argv":["claude","-p","--model","{model}","--effort","medium","--output-format","stream-json","--verbose","--no-session-persistence","--setting-sources","","--strict-mcp-config","--disable-slash-commands","--tools","Read,Write,Bash","--allowedTools","Read,Write,Bash","--settings","{\"disableAllHooks\":true}"],"capabilities":{"launch":{"state":"unknown"},"write_isolation":{"state":"unknown"},"model_selection":{"state":"unknown"}}}
```

Empty argv elements are valid and must be preserved; they are not shell text. Review the [official headless documentation](https://code.claude.com/docs/en/headless) and the installed CLI's help when upgrading.

## Other shells

A trusted platform can consume `actions.plan`, atomically `actions.claim`, start its own process/container and report `runs.event`. `local` and `external` identify the execution mode, not two simultaneously active schedulers. The local `reference_worker.py` demonstrates this contract without an AI scheduler; any executable argv can be used under the tested kernel boundary. Other operating systems need equivalent actual isolation and conformance evidence. No S3 or distributed SQLite mode is implemented.

Use the repository's `test_expert_packages.py` and `test_write_boundary.py` against a built kit for protocol and boundary checks. They are explicitly simulated for identities/models; OS process and write attempts are real. Real model integration is exercised separately by `evals/platform_v033.py` (`prepare` stops for an actual artifact review; `continue-reviewed` requires a validated, enabled package); its synthetic task decisions are not human product approvals. Test reports must distinguish preservation of methods, write isolation, handoff transport and professional quality. A successful process or file containing the expected keywords is insufficient for expert admission.

The public release notes will state the exact final verification scope and unresolved limits. Raw local project names, authentication logs and test workspaces are not distribution contents.

The controller imports one facade per process. Its short database requests are serialized within that process; model work remains parallel and separate controllers use SQLite transactions. This avoids the observed macOS system SQLite `SQLITE_IOERR_LOCK`/`EBADF` during mixed concurrent read/write connection lifetimes. Regression checks include threaded and separate-process workers, start callbacks, handovers and database integrity.
