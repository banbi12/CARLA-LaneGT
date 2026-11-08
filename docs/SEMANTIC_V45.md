# semantic V4.5 与 R3 修订

V4.4.1 的结构 boundary 连接方案正式命名为 V4.5。R1 清理 divider 精确重复和重合端点；R2 加入完整包含片段检查，避免重叠片段制造假分叉；R3 将同类整理扩展至 boundary 和有向 centerline。

核心数值规则见[算法](ALGORITHM.md)和[参数](PARAMETERS.md)。本页只记录版本对应关系。

| 名称 | 含义 |
| --- | --- |
| XODR-only V4.2 | 保留原生道路局部 XYZ 的几何基线，带 divider 连接 |
| semantic V4.5 | V4.2 divider 与结构 boundary；semantic 只支持 boundary 连接 |
| R2 divider | XYZ 重复／完整包含清理与唯一重合端点链 |
| R3 | 保留 R2 divider；boundary 与 centerline 加入同类整理、方向与切分保护 |
| 软件 1.0.0 | 新 MultiTown 源码仓库的独立发布版本 |

R3 在加入 centerline 后、模型采样前统一整理。原始 target 及其 source_refs、parent 和来源链保留。实例整理保持已有完整几何和 semantic 连接。

可选采样调用配置的外部 MapTRv2 `LiDARInstanceLines`。无模型时默认输出完整通用几何；显式采样时保存全部类别的 GT 20 点与 NPZ。

图册数据集身份包含版本和 GT 内容摘要。人工编辑记录只适用于对应版本的图册；重新提取或调整实例后，应在相应图册中继续编辑。
