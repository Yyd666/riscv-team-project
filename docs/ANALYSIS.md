# ENG-03 静态 ELF 分析

本模块读取真实 RISC-V ELF 和 GNU binutils 输出，生成 `.text` 及 `kernel` 函数的静态指标。它不统计动态指令、不测量目标周期，也不使用 QEMU 宿主耗时排名。

## 输入与输出

- 输入：编译执行模块生成的 ELF，目标为 RV64GC/LP64D；
- 工具：`readelf -h -A/-sW`、`size -A`、`objdump -d -M no-aliases,numeric --disassemble=kernel`；
- 输出：状态、指标、反汇编文本、函数边界、ELF SHA-256 和拒判原因；
- `analysis_error` 时不生成成功指标；

## 指标

- `elf_file_bytes`：整个 ELF 文件字节数；
- `text_section_bytes`：名称严格为 `.text` 的节大小；
- `kernel_code_bytes`：符号表中 `kernel` 函数的字节范围；
- `kernel_static_instruction_count`：反汇编中覆盖该范围的机器指令数；
- `kernel_compressed_instruction_count`：其中 16 位编码的数量；
- `dynamic_instruction_count`、`target_cycles`：保持 null。

## 拒判规则

缺少或重复的 `kernel` 符号、目标不是 RV64 ELF、`.text` 缺失、反汇编有空洞/重叠、指令编码无法覆盖函数范围，均返回 `analysis_error`。未知字节不推测为指令。

## 当前边界

ENG-03 是独立静态分析入口，尚未接入产品 CLI、完整实验 Schema 或推荐器。正式集成时复用 yyd 的受限执行器，避免重新实现进程限额、取消和证据保存。