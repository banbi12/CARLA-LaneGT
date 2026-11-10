# semantic V4.5 R3

当前版本以 XODR-only V4.2 为几何基线，结合 semantic 与实测深度拟合结构 boundary 端点连接，并按局部偏移与原生高程对齐 XODR 外缘，并在采样前统一整理线实例。

| 类别 | 当前处理 |
| --- | --- |
| divider | 原生 roadMark 与几何连接；不增加 semantic 补线 |
| boundary | 保留结构候选；局部法向偏移校正连接，原生端点高程／坡度主导 Z，连续部分作为一个 target |
| centerline | 同地图 XODR 车道中心线，保留行驶方向 |
| ped_crossing | 同地图 XODR crosswalk 对象 |

线实例按同类完整 XYZ 检查重复和完整包含，再合并唯一且方向连续的重合端点。原始 target、source_refs、parent 和来源链可追溯；完整几何和已有连接保持。

实例整理位于 centerline 加入之后、模型采样之前。默认输出通用完整几何；可选采样调用配置的外部 MapTRv2 LiDARInstanceLines，并保存 GT 20 点与 NPZ。

图册数据集身份包含版本和 GT 内容摘要。人工编辑记录只适用于对应版本的图册；重新提取或调整实例后，应在相应图册中继续编辑。

数值规则见[算法](ALGORITHM.md)与[参数](PARAMETERS.md)，修订操作见[人工后处理](POSTPROCESSING.md)。

默认 boundary target 不再按曲率或急弯预切分：同一条连续 boundary 在 ROI 内的连续部分作为一个 target，统一采样 20 点。完整 XYZ 保留；真实不相接片段、跨层和分叉不因此强行连接。紧转角可能增加固定点采样的表示偏差。旧数据的显式分段保护仍仅用于已有分段输入，不影响新提取的此规则。
