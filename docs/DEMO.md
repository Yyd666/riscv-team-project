# CLI-01 / REPORT-01 / ATTR-01 演示脚本

演示在 Linux/WSL2 中执行，使用已登记的真实样例，不使用 mock 代替真实运行。

```sh
python -m optipilot run --benchmark sum_u32 --optimizations O0 O2 Os --output artifacts/demo
python -m optipilot report \
  --experiment artifacts/demo/EXPERIMENT_ID/result.json \
  --output artifacts/demo/EXPERIMENT_ID/report.md \
  --attribution artifacts/demo/EXPERIMENT_ID/attribution/O2-Os/attribution.json
```

演示顺序：先展示三档用例通过与完整 `.text` 推荐，再展示 `kernel` 静态指标、R001/R002 sidecar 证据和报告中的结论边界。随后使用一个失败或拒判记录，说明 `analysis_error`、`partial`/`unavailable` 与非零退出码；失败结果不得被替换成 mock。

真实演示记录应附实验 JSON、报告、归因 sidecar、工具版本、源码/输入/配置哈希和完整命令。当前工作区只保存脚本和说明，不把运行产物纳入版本控制。
