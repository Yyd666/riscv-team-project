# DEMO-01 真实演示录制脚本

本脚本用于录制真实 Linux/WSL2 操作。每条路径都要保存完整命令、退出码、stdout、stderr、结果 JSON、报告和 SHA-256 清单；不得用 mock 代替真实执行。录制完成前，清单中的视频项保持未勾选。

## 环境画面

录制开始时展示：

```sh
uname -a
python --version
riscv64-linux-gnu-gcc --version
riscv64-linux-gnu-readelf --version
riscv64-linux-gnu-objdump --version
qemu-riscv64 --version
git rev-parse HEAD
```

随后展示仓库版本、`benchmarks/manifest.json` 和输出目录为空。输出目录必须位于 Linux/WSL2 后端，不能使用 Windows 本机编译器或 QEMU。

## 成功路径

```sh
python -B -m optipilot run \
  --benchmark sum_u32 \
  --optimizations O0 O2 Os \
  --output artifacts/demo-success
```

录制结果 JSON 中的 `is_mock=false`、三个方案状态、全部登记用例通过、`.text` 推荐、`compile_argv`、`run_argv`、`analysis_argv` 和 ELF 哈希。随后运行：

```sh
python -B -m optipilot report \
  --experiment artifacts/demo-success/EXECUTION_ID/result.json \
  --attribution artifacts/demo-success/EXECUTION_ID/attribution/O2-Os/attribution.json \
  --output artifacts/demo-success/EXECUTION_ID/report.md
```

展示 Markdown 报告中的静态推荐、R001/R002 状态、证据路径和限制文字。退出码应为 0。

## 缺少参考配置的拒判路径

```sh
python -B -m optipilot run \
  --benchmark sum_u32 \
  --optimizations O0 \
  --require-attribution \
  --output artifacts/demo-missing-reference
```

该命令应返回退出码 4，并明确记录缺少 O2 的归因不可用原因；不得自动增加 O2、生成伪造 sidecar 或回退 mock。录制终端中的退出码和 stderr。

## 真实负例拒判路径

```sh
python -B scripts/run_attribution_negatives.py \
  --output artifacts/demo-negative/summary.json
```

展示未知 16/32 位编码、截断编码、缺失符号、函数不在 `.text` 和证据冲突的状态及证据引用。工具缺失、编译失败或错误 oracle 不得被剪辑成成功拒判；summary 中的 `is_mock` 和失败原因要保留。

## 录制后核对

录制者应保存：

1. 成功路径视频及其 SHA-256；
2. 缺少 O2 的拒判视频及其 SHA-256；
3. 负例 summary、终端日志和实际退出码；
4. 录制使用的 Git 提交、工具版本和输出目录清单。

当前状态：脚本和真实命令已复核，视频文件尚未提供。视频完成后更新 [DEMO_CHECKLIST.md](DEMO_CHECKLIST.md)，并在 REPORT-02 中加入视频哈希和可访问路径。
