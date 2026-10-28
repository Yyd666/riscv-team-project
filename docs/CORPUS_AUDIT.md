# INTEG-01 语料数值与预期输出复核

## 范围与方法

2026-10-28，在主线 `ac8ba546211eb72f0b32598322275d2edd6e4612` 的语料上，逐个阅读 12 个 C 程序及 36 组登记输入，核对 C 类型、数组边界和中间运算范围，再使用独立整数数学计算复核预期输出。复核由开发助手执行，不登记为新增自然人复核或另一份独立 ELF 标注。

[复核脚本](../scripts/check_corpus_oracles.py) 不导入冻结器、执行引擎、ELF 分析器或产品归因模块，不读取 O0 运行结果生成预期值。滚动哈希使用模多项式求和；直方图使用加权和化简；游程使用等值分组；校验和使用奇数次元素的异或；状态机使用显式转移表；有界解析使用十进制整数取模。其余结果使用精确整数公式，定点除法明确采用 C 的向零截断。

脚本只读输入及现有 `.out`，不修改清单、预期输出或正式批次。校验范围包括 12 份源码、36 份输入、36 份输出及一份许可证，共 85 个文件哈希；预期输出还须与数学计算所得十进制数及末尾 LF 逐字节一致。类型/数值分析覆盖登记用例，不声明任意 stdin 都安全。

## 数值范围

下表的 n 为元素数；32 位有符号整数范围为 −2³¹ 至 2³¹−1。数组最大长度分别为 64 或 32，与程序输入检查一致。

| 程序 | 运算及范围结论 |
| --- | --- |
| sum_u32 | n≤64，元素为 uint32；结果按模 2³² 累加，回绕是定义明确的无符号运算。 |
| dot_i32 | n≤64，元素限制在 ±10000；乘法前转为 int64，每项绝对值≤10⁸，总和绝对值≤6.4×10⁹，无 int64 溢出。 |
| threshold_count | n≤64，元素和阈值限制在 ±10000；只比较并计数，结果≤64。 |
| histogram_count | n≤64，元素为 0…7，合法索引八个桶；总加权值≤512。 |
| run_length | n≤64，元素为 0…15；空输入单独返回 0，其余游程长度≤64，i−1 只在 i≥1 时使用。 |
| rolling_hash | n≤64，元素为 0…255；每轮 hash<1000000007，乘 257 加元素的中间值小于 2.58×10¹¹，远小于 uint64 上限。 |
| xor_checksum | n≤32，元素为 uint32；逐位异或没有有符号溢出。 |
| lookup_switch | n≤32，单项为 −1、3、5 或 7；部分和在 −32…224 内，覆盖全部 int32 元素值。 |
| call_chain | n≤32；C 接收 int32，但平方、减法和累计均为 int32，任意输入并不安全。登记非空用例值在 −10…10，逐项检查平方、减法和累计均在范围内；最大登记结果为 200。 |
| state_machine | n≤32，事件为 uint32；状态始终为 0…3，三种转移的中间值≤7，其他事件不改变状态。 |
| fixed_point_filter | n≤32，元素及阈值为 int32；先转 int64 再乘 3，单项绝对值≤3221225472，总和绝对值≤103079215104。负奇数除 2 必须向零截断。 |
| bounded_parser | n≤32，数字限制为 0…9；旧值≤1000002，乘 10 加数字≤10000029，不发生 uint32 回绕；结果按模 1000003 计算。 |

上述范围排除了登记输入中的越界及有符号溢出。它不证明 scanf 对任意超范围十进制文本的处理安全，也不把 `call_chain` 的未约束值域扩展为安全域。产品只运行登记可信输入，若后续接受任意输入，须单独完善输入转换和数值约束。

## 逐程序结果

36/36 份预期输出与独立计算逐字节一致。下表列出全部登记用例的整数结果；不把三个 stdin 计为三个独立静态程序。

| 划分 | 程序 | 登记用例与结果 |
| --- | --- | --- |
| development | sum_u32 | empty=0；mixed=14；wrap=0 |
| development | dot_i32 | boundary=200000000；empty=0；mixed=4 |
| development | threshold_count | empty=0；mixed=4；negative=4 |
| development | histogram_count | boundary=36；empty=0；mixed=24 |
| development | run_length | boundary=4；empty=0；mixed=3 |
| development | rolling_hash | boundary=521158983；empty=0；mixed=396618739 |
| held_out | xor_checksum | boundary=3989547398；empty=0；mixed=3 |
| held_out | lookup_switch | boundary=21；empty=0；mixed=13 |
| held_out | call_chain | boundary=200；empty=0；mixed=12 |
| held_out | state_machine | boundary=3；empty=0；mixed=0 |
| held_out | fixed_point_filter | boundary=4；empty=0；mixed=26 |
| held_out | bounded_parser | boundary=999972；empty=0；mixed=12345 |

## 来源与隔离边界

按 `git log --follow --diff-filter=A` 逐文件追溯，12 份源码的首次引入提交及作者账号与 [来源与许可登记](CORPUS_LICENSE.md) 一致：最初三个程序为 `74789e0`，新增三个开发程序为 `e0ae4bc`，六个留出程序为 `8cda6c3`，均记录账号 `Yyd666`。当前登记为仓库自编，MIT 原文及其哈希存在；Git 元数据不能验证自然人作者身份或未登记的第三方来源。

源码阅读确认每边各六种登记功能，家族标签没有跨集合重复。但求和、点积、查表及调用链等共享遍历/归约形式；直方图的最终输出也可化简为加权和，滚动哈希与有界解析同属序列递推。不同标签不代表统计独立或任意意义下的算法隔离。

`repository_authored_development` 与 `repository_authored_held_out` 是同一仓库内的分组标签，全部源码共享 Git 作者和生成工作流，不能仅据这两个字符串宣称作者来源独立。当前记录也不足以证明留出集从未用于规则调试。因此只能报告这 12 个仓库内固定样例的机器结果；来源独立性和未接触留出集的过程证据仍缺失，不能将本复核扩展为外部独立泛化验证。不得为了通过门槛改写旧清单的来源标签或历史结果；需要更强独立结论时，应另行登记新来源与冻结过程后运行新批次。

## 复现与检查

在仓库根目录执行，纯 Python 检查不需要编译器、QEMU 或硬件：

```sh
python -B scripts/check_corpus_oracles.py --output artifacts/m2-corpus-audit/numeric-oracle-audit.json
python -B -m unittest discover -s backend/tests -p test_corpus_oracles.py -v
```

本次 Windows 检查结果：12 程序、36 用例、85 个哈希全部通过。原始摘要保存在忽略目录 `artifacts/m2-corpus-audit/numeric-oracle-audit.json`；摘要记录实际清单和检查脚本的 SHA-256，可在新检出目录重建。清单原始字节受 Git 换行设置影响，不能跨平台直接假定摘要中的清单哈希相同。

四项定向检查通过，覆盖真实清单、无符号回绕、负数向零截断、大于 int32 的合法点积、输入数量/范围错误，以及 `call_chain` 单项和累计溢出。另用临时副本验证：源码哈希不符被拒绝；即使同时重算错误 `.out` 的清单哈希，错误数学预期仍被拒绝。没有在本次数值审阅中重新编译或运行正式批次。

本审阅补齐 INTEG-01 的登记用例数值与 oracle 证据，不验证人类身份，不替代已有 ELF 标注或新增第二份人类审阅。最终 REPORT-02、录屏、官方材料和来源隔离限制仍须分别处理，`acceptance_ready` 保持 false。
