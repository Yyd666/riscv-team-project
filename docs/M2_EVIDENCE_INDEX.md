# M2 证据索引

状态：技术结果和候选材料索引，供团队审查和最终打包使用；技术最终报告已定稿，但在录屏、官方回执、来源独立性确认、人员身份确认和证据归档完成前，不改变 `acceptance_ready=false`。

## 正式批次与独立复现

- 正式批次：`evaluation-23d0fbc17db84a1d8379bbc0ca0d2ddf`。
- 批次 `batch.json` SHA-256：`0659a3ec8bef9c0a0d2a5d3efc1e8036bdc6eaedd7e3ce9b9c3b7360d7f0b60d`。
- 正式批次清单 SHA-256：`50df975ee2e0c5ac4aaf2bc1724c2371e131d3aef63bf0ed90aa0bd9b506bc22`。
- 独立 Ubuntu 复现：[Actions 工作流 40464387344](https://github.com/Yyd666/riscv-team-project/actions/runs/40464387344)；归档名称为 `m2-formal-evidence-adbc46cc435b159cd531e02096b62966ebfc9de6`。
- 已记录的机器结果：12 个程序、36 个 O0/O2/Os 配置、108 个 QEMU 用例、24 个 O2→候选比较；独立 ELF 字节误差 24/24 为 0，R001/R002 独立核对 24/24 通过。

CI 归档和正式批次原始目录属于可下载的证据来源；本地 WSL2 路径仅作生成位置，不能单独作为最终报告的可访问证据。提交前应重新下载归档，核对文件哈希，并把归档链接、下载时间和哈希写入最终材料包。

## 双人复核与语料审计

- SJS 标注：[PR #26](https://github.com/Yyd666/riscv-team-project/pull/26)。
- YYD 标注：[PR #28](https://github.com/Yyd666/riscv-team-project/pull/28)。
- 裁决：[PR #29](https://github.com/Yyd666/riscv-team-project/pull/29)；YYD 签字补充先合并到 sjs 的 [PR #30](https://github.com/Yyd666/riscv-team-project/pull/30)。
- 数值/oracle 审计：[CORPUS_AUDIT.md](CORPUS_AUDIT.md)，对应 [PR #34](https://github.com/Yyd666/riscv-team-project/pull/34)。

这些文件证明机器证据和声明结构通过校验，不证明真实人员身份，也不能证明 12 个程序具有独立外部来源。

## 报告、演示与官方要求

- 技术最终报告：[REPORT-02.md](REPORT-02.md)。
- 演示脚本：[DEMO_RECORDING.md](DEMO_RECORDING.md)；清单：[DEMO_CHECKLIST.md](DEMO_CHECKLIST.md)。
- 官方要求与截止时间：[OFFICIAL_MATERIALS.md](OFFICIAL_MATERIALS.md)。
- 状态与验收：[STATUS.md](STATUS.md)、[ACCEPTANCE.md](ACCEPTANCE.md)。

## 仍需加入最终材料包的证据

1. 真实成功路径视频、真实拒判路径视频、各自 SHA-256、录制环境和对应 Git 提交。
2. 团队资格、牵头人/单位、唯一赛题、报名回执、署名及第三方来源核对记录。
3. 来源独立性和留出集未参与规则调试的团队确认；若无法补齐，应在报告中明确限制，不宣称一般化效果。
4. 最终报告的可访问归档链接和下载后哈希。

在上述材料完成前，本索引只用于追踪证据，不构成最终 M2 验收。
\n