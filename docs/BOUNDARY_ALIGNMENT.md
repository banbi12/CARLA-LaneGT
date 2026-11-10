# Boundary：XODR 外缘与语义引导连接

默认 semantic 方案使用 `config/extraction/semantic_policy.json`，启用 `boundary_route_enabled` 与 `boundary_route_align_to_xodr`。直接运行 `extract` 即生效。输出标识包含 `+boundary_route_xodr_aligned_trial_v2`；后缀保留以维持已有输出及浏览器编辑空间的版本身份。

## 几何定义

XODR `surface_outer_edge` 与可见 Roads / Sidewalks、Terrain 界面可能对应不同的物理边缘，例如包含路肩外侧的结构边界。默认保留 V4.2 原生结构坐标，只利用语义和实测深度确定连接走势。连接与原生段统一到 XODR 外缘定义，因此可以整体偏离可见路沿；不能把所有地图固定平移某个肩宽。

1. 在完整实测参考范围内获取结构端点，按 XODR 道路／路口拓扑、端点方向和层高生成多组 Hermite 候选；最终输出再裁到原 BEV。
2. 在两端原生线尾约 3m 的可见上下文内，匹配经标定深度重建的道路／非道路界面。独立估计有符号法向偏移及实测高度差；方向一致性、最小样本数和稳健离散度检查保护估计。
3. 平滑插值两端局部偏移，把候选放入语义界面坐标。通过法向动态规划跟随实测界面，检查道路两侧角色、可见地面、当前层高及受限细杆遮挡。安全边界以外的线尾不参与支持率计算。
4. 使用相同的参考法向及局部偏移将语义引导曲线移回 XODR 逻辑外缘。连接端点固定，所有原生结构顶点逐点保留。输出 Z 由原生端点高度和坡度的 Hermite 剖面决定；观测地面或人行道顶部高度不直接写入连接 Z。
5. 按语义引导曲线的证据与贴合评分选取候选，并检查输出自交、已有结构相交和端点歧义。两端不能可靠测偏移时，只考虑通过原有证据检查的原生端点候选，不切回直接贴路沿的混合定义。

## 参数与审计

默认 `boundary_route_search_max_gap_m: null`，不设固定米数上限；仍受可观测安全视野、拓扑和语义／深度证据约束。可设置正数恢复显式搜索上限。旧 `structural_boundary_max_gap_m` / `structural_boundary_straight_max_gap_m` 只在关闭 route 模式时限定旧路径。

拟合步长 0.15m、法向搜索宽度 1.5m；局部偏移最多 1.0m、实测高度差最多 0.4m、至少 4 个可靠采样站、偏移 MAD 最多 0.12m。其他保护见[参数](PARAMETERS.md)。扩大参考视野时应重新采集并检查分辨率和完整 XYZ 覆盖，GT 的 BEV 范围不必扩大。

审计的 `points_xyz` 是输出曲线，`semantic_guide_xyz` 是证据曲线；同时记录 `semantic_fitting.local_bias`、`guide_interface_distance`、偏移失败或回退原因。输出到可见路沿的距离不能单独作为此定义下的精度评分。

## 使用边界

不产生独立 semantic boundary，divider 仍完全来自 XODR-only V4.2，R3 实例整理与模型采样保持独立。紧转角、遮挡、缺少可靠锚点或 XODR 本身错分仍需人工审核；连通性和数据接口通过不代表每条曲线都准确。人工补线可使用[两线圆角及 CAD 后处理](POSTPROCESSING.md)。

默认 boundary target 不再按曲率或急弯预切分：同一条连续 boundary 在 ROI 内的连续部分作为一个 target，统一采样 20 点。完整 XYZ 保留；真实不相接片段、跨层和分叉不因此强行连接。紧转角可能增加固定点采样的表示偏差。旧数据的显式分段保护仍仅用于已有分段输入，不影响新提取的此规则。
