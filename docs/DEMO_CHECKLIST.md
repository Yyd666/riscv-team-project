# DEMO-01 演示清单

演示使用 Linux/WSL2 的真实编译、QEMU 和归因证据，禁止用 mock 替代真实运行。

## 成功路径

```sh
python -B -m optipilot run --benchmark sum_u32 --optimizations O0 O2 Os --output artifacts/demo-success
python -B -m optipilot report --experiment artifacts/demo-success/EXECUTION_ID/result.json --attribution artifacts/demo-success/EXECUTION_ID/attribution/O2-Os/attribution.json --output artifacts/demo-success/EXECUTION_ID/report.md
```

展示三档用例通过、`.text` 推荐、`is_mock=false`、R001/R002 状态、证据路径和 SHA-256 定位。

## 拒判路径

```sh
python -B -m optipilot run --benchmark sum_u32 --optimizations O0 --require-attribution --output artifacts/demo-missing-reference
python -B scripts/run_attribution_negatives.py --output artifacts/demo-negative/summary.json
```

第一条命令应因缺少 O2 返回 4；第二条覆盖未知编码、截断编码、缺失符号、非 `.text` 函数和证据冲突。工具缺失、编译失败或错误输出不得计为成功拒判。

## 材料清单

- [ ] 成功路径录屏。
- [ ] 失败/拒判录屏。
- [x] 机器评估报告和原始证据归档。
- [x] 12 程序及登记测试数据的 MIT 许可文件与范围登记，见 [语料来源与许可](CORPUS_LICENSE.md)。
- [x] 两位成员独立复核文件与裁决。
- [ ] 官方资格、署名、截止时间和第三方来源核对。

当前命令和真实证据已具备；录屏、签署和最终材料仍待完成。
