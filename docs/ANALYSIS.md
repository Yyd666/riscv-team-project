# ENG-03 静态 ELF 分析

ENG-03 使用统一 ProcessRunner 运行 readelf、size、objdump，生成 `.text` 和 `kernel` 的静态指标。分析要求 RV64GC、LP64D、ELF EXEC、静态链接、kernel 位于 `.text`，并逐条用 ELF 原始字节核对反汇编码。

输出包含 ELF 哈希、函数边界、机器指令数、压缩指令数、原始字节核对状态和拒判原因。分析失败不生成成功指标；动态指令、目标周期和宿主耗时不进入结果。

当前实现是独立 ENG-03 入口，后续由 CLI 编排并接入完整实验 Schema。
