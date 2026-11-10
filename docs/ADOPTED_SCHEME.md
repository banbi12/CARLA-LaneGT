# 默认提取方案

MultiTown 默认使用 **semantic V4.5 R3 + XODR 外缘对齐 v2**。软件版本为 1.1.1。

| 类别 | 来源与处理 |
| --- | --- |
| divider | XODR-only V4.2，关闭 semantic 补线；进行同类重复／包含片段及重合端点整理 |
| boundary | 保留 V4.2 结构；semantic／depth 引导连接并按局部偏移对齐 XODR 外缘；Z 沿用原生端点和坡度；连续部分作为一个 target |
| centerline | 同地图 XODR，使用有向 R3 target 整理 |
| ped_crossing | 同地图 XODR crosswalk 对象 |

部分断线、漏线、误线及歧义连接可通过[人工后处理](POSTPROCESSING.md)修订。算法与实例组织见[算法说明](ALGORITHM.md)，地图接入见[跨地图说明](MULTITOWN.md)。

默认 boundary target 不再按曲率或急弯预切分：同一条连续 boundary 在 ROI 内的连续部分作为一个 target，统一采样 20 点。完整 XYZ 保留；真实不相接片段、跨层和分叉不因此强行连接。紧转角可能增加固定点采样的表示偏差。旧数据的显式分段保护仍仅用于已有分段输入，不影响新提取的此规则。
