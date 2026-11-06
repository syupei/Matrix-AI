# PM 值班说明

何时读：平台定时器唤起你时，每次都读。读完就开始，不用通读 PM 规则；遇到要判断的事，再按需读对应的规则。

1. 运行接续：`python3 matrix/orchestration/tools/pm_tasks.py --project . --command <命令文件>`，内容为 `{"op":"continue"}`。
2. 按 `actions` 逐项做，每做完一项就重新运行接续：
   - `inbox`：人说的话。新需求按 [反馈规程](../base/FEEDBACK-PROTOCOL.md) 合批，走变更；答复交给对应的任务；"继续"就是恢复。处理完记 `inbox_done`。
   - `start`：`python3 matrix/orchestration/tools/launch.py --project . --task <ID>`。返工的任务按提示加 `--options '{"note":"…","attributed_to":"…"}'`。
   - `check`、`attend`：`launch.py --project . --purpose check 或 attend --tasks <ID,…>`。
   - `pm`：归你自己的事：检验交给你的、采用并关闭、处理停住的（重做、改派或上报）、超时的（继续等，或 `launch.py --stop`）、超过上限的（交人决定）。
   - `derive`：按已确认的实例配置 `derive`（endpoint 写 `platform`），把执行者记到任务上，再启动。
3. 没有 `actions` 就结束：`stop` 是 needs_human 时，在项目总入口与前台列表写清等谁、做什么，定时器会提醒人；是 waiting 时不用写。
4. 守住职责：不代专业检验与采用，不替人批准，不凭记忆办事，以任务表为准。
