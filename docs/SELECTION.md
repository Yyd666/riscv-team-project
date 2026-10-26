# ENG-04 有限候选配置推荐

状态：已实现，待 CLI-01 集成验收。

ENG-04 只比较当前基线登记的 O0、O2、Os。它不扩展编译参数，不把宿主耗时作为性能指标，也不声称实现自研编译优化算法。

只有 status 为 passed 且存在合法正整数 metrics.text_section_bytes 的方案才进入候选集合。其他方案会被排除并保留原因；选择器不重新编译、不运行 QEMU，也不修改实验记录。

目标固定为 min_text_section_bytes，按 .text 静态节大小升序选择，平局使用 O2、Os、O0 顺序。输出证据类型为 static_size_only。没有可行候选时返回 unavailable 和 no_correctness_passed_candidate。

测试覆盖最小体积、平局、失败方案排除、无可行候选、缺失指标、重复档位、非法指标和宿主耗时隔离。CLI-01 接入真实执行和 ENG-03 分析结果后，才能完成 ENG-04 的端到端验收。
