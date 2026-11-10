# 当前参数及生效位置

默认方案由 `config/ACTIVE_SCHEME.json`、`config/extraction/semantic_policy.json` 及 target 策略定义。boundary 候选／拟合位于 `semgt/boundary_routes.py`，局部偏移校正位于 `semgt/boundary_alignment.py`。详见 [boundary 对齐](BOUNDARY_ALIGNMENT.md)。

| 默认 semantic 参数 | 值／用途 |
| --- | --- |
| divider_semantic_supplements_enabled | `false`；divider 采用 XODR-only V4.2 |
| boundary_route_enabled / boundary_route_align_to_xodr | `true` / `true` |
| boundary_route_search_max_gap_m | `null`；无固定米数搜索上限，仍受实测视野、拓扑和证据约束 |
| boundary_route_sample_step_m | 0.15m |
| boundary_route_fit_width_m | 1.5m 法向走廊 |
| boundary_route_max_interface_distance_m | 1.25m |
| boundary_route_max_curve_ratio | 1.8 倍端点弦长 |
| boundary_route_alignment_max_offset_m | 1.0m；局部实测值，不是固定平移量 |
| boundary_route_alignment_max_height_bias_m | 0.4m；只用于证据，不替换输出高程 |
| boundary_route_alignment_min_samples | 4 |
| boundary_route_alignment_max_mad_m | 0.12m |
| boundary_route_occlusion_max_run_m | 2.0m；route 模式的连续遮挡上限 |
| boundary_route_static_occluder_max_diagonal_m | 4.0m；紧凑且高于地面的 Static/Other 道具可作为遮挡，深度不当作地面 |
| structural_boundary_semantic_fraction / structural_boundary_straight_semantic_fraction | 0.8 / 0.95 |
| structural_boundary_height_tolerance_m | 0.35m |
| structural_boundary_context_max_offset_m | 4.0m；仅显式非道路前缀允许扩大探测 |
| border_px | 48 |

旧 `structural_boundary_max_gap_m=8.0` / `structural_boundary_straight_max_gap_m=30.0` 只作用于关闭 `boundary_route_enabled` 的旧候选路径。历史 V4.3／V4.1 字段保留兼容，不能据此推断当前生效规则。

| target 参数 | 值与生效位置 |
| --- | --- |
| duplicate_tolerance_m | 0.00001m；同类完整 XYZ 重复／包含检查 |
| endpoint_tolerance_m | 0.00001m；重合端点，不用于补正缺口 |
| max_tangent_bend_deg | 15°；唯一端点连接的方向保护 |
| centerline | 同向；只允许末端接起点，不反转曲线 |
| boundary | 同原 parent 的有意分段不合回 |

boundary 分段策略见 `boundary_partition_policy.json`。R3 位于实例裁剪、centerline 加入之后、实际采样之前。默认 BEV 为 [-15,-30,15,30]，高度 [-2,2]。采集模板为 1152×2048、FOV 36°、60m 相对高度；实际高度按完整 XYZ 覆盖与端点上下文调整，不以世界 z=0 投影。显存停止阈值为 7400MB 与物理显存 90% 中较小者，每 100ms 采样。

修改采集参数需重新验证同步和覆盖；修改提取或 target 参数需生成新结果。固定 20 点、shift_v2 padding 和标签语义属于 MapTR 适配器契约，修改时需同步模型侧配置。
