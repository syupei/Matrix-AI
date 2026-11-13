# 平台运行

何时读：配置本机调度命令、启动或停止运行。调用前置与其余操作见[原入口](../../START.md)。

## 平台运行

宿主有非交互运行命令（读入提示后运行一次再退出）时，可以让实例由平台拉起、PM 统一调度（规则见 `matrix/orchestration/TEAM-RUNTIME.md` 平台运行）。

1. 在项目里写 `management/runtime/platform.json`，内容是宿主命令的模板。权限写在这里，由你确认后再用：

   ```json
   {
     "launch": ["<宿主命令>", "<非交互运行>", "<指定模型>", "{model}", "<指定会话编号>", "{session}",
                "<只允许这些工具>", "读取类工具,{write_permissions},<运行 matrix/orchestration/tools/pm_tasks.py>", "<禁止联网类工具>"],
     "write_patterns": ["<写入工具>({root}/**)"],
     "pm": {"launch": ["…同上，另允许运行 matrix/orchestration/tools/launch.py，模型写 PM 用的模型…"],
            "resume": ["<宿主命令>", "<非交互运行>", "<按会话编号续接>", "{session}", "…权限同上…"]},
     "models": {"<实例配置里的模型名>": "<宿主认得的模型名>"},
     "notify": ["<本机提醒命令>", "{message}"]
   }
   ```

   - 宿主命令须能：从标准输入读提示；指定模型；指定会话编号，PM 的命令还要能按编号续接；只允许列出的工具，没列出的直接拒绝而不弹窗询问。
   - `{write_permissions}` 按 `write_patterns` 展开成该实例每个写入范围的写权限；不要用跳过全部权限的方式。
   - 可选的数值：`check_seconds`（60）、`patrol_minutes`（60）、`pm_timeout_minutes`（20）、`resume_limit`（20）、`resume_idle_minutes`（60）。
   - 可选的数值：`settle_seconds`（60，变化后等多久再唤起 PM）、`max_wait_seconds`（300）。
   - 宿主的沙箱不让会话的子进程联网时，加 `"spawn": "scheduler"`。
   - 省用量的宿主设置：PM 的推理强度可以设低一档（日常值班以执行接续为主）；宿主支持按会话编号续接时，给 PM 配上 `resume`。
2. 选择运行方式：
   - 终端常驻：`python3 matrix/orchestration/tools/scheduler.py --project .`；Ctrl-C 停止调度检查。
   - 手动检查一次：加 `--once`，不安排下一次检查。
   - 系统管理：加 `--service launchd`、`--service systemd` 或 `--service cron`，只输出 JSON 中的文件内容、安装命令与停止命令，不写文件或安装服务。审阅后由人执行；cron 需把生成的一行追加到个人 crontab，保留其他任务。cron 每分钟检查一次，其他方式可用 `--interval` 指定不少于 5 秒的间隔。用户服务依赖登录会话；宿主命令的 PATH、非交互凭证和访问范围需实际核对。
3. 停下：告诉前台“暂停项目”阻止继续拉起；停止常驻终端、用生成的停止命令禁用服务或移除该项目 cron 行，停止后续调度检查。停止调度器不等于停止已经启动的实例，需按任务停止流程取得回执。再启动时从任务表接续，不重建任务库。
4. 查停滞：任务工具 `continue` 返回 `scheduler_health`，总览和项目视图也显示诊断。每次调度检查记录心跳；距最近记录超过两倍检查间隔时提示“调度器可能已停，按 START.md 重启”。缺记录写未知，检查出错与过期分别显示；近期心跳不证明任务在执行。前台查当前诊断或刷新视图，不能用旧快照确认调度器仍在线。

平台接入与自带专家：按需读 [平台 guide](PLATFORM-GUIDE.md) 和 [专家接入](EXPERT-IMPORT.md)。
