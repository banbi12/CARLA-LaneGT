# 当前参数及生效位置

公开最终方案读 config/ACTIVE_SCHEME.json、config/extraction/semantic_policy.json 及 linear_target_policy.json。历史 V4.3／V4.1 字段仍留作兼容；并非每个旧字段都参与当前结构边界连接，数值读取以 semgt/structural_boundary.py 为准。

| 当前 semantic 参数 | 值 |
| --- | --- |
| divider_semantic_supplements_enabled | `false` |
| border_px | `48` |
| structural_boundary_max_gap_m | `8.0` |
| structural_boundary_semantic_fraction | `0.8` |
| structural_boundary_height_tolerance_m | `0.35` |
| structural_boundary_straight_max_gap_m | `30.0` |
| structural_boundary_straight_semantic_fraction | `0.95` |
| structural_boundary_context_max_offset_m | `4.0` |
| boundary_occlusion_enabled | `true` |
| boundary_occlusion_max_run_m | `1.5` |

| target 参数 | 值与生效位置 |
| --- | --- |
| duplicate_tolerance_m | 0.00001m；divider_targets 与 linear_targets 的完整 XYZ 重复／包含检查 |
| endpoint_tolerance_m | 0.00001m；重合端点，不用于补正缺口 |
| max_tangent_bend_deg | 15°；唯一端点连接的方向保护 |
| centerline | 同向；只允许末端接起点，不反转曲线 |
| boundary | 同原 parent 的有意分段不合回 |

boundary 分段策略见 boundary_partition_policy.json。该几何特征切分保留，不以减少实例数抹去急弯。R3 接在实例裁剪、centerline 加入之后、实际采样之前。

默认 BEV [-15,-30,15,30]，高度 [-2,2]。采集模板为 1152×2048、FOV 36°、60m 相对高度；实际高度按完整 XYZ 覆盖检查调整，不能照搬世界 z=0。显存阈值为 7400MB 与物理显存 90% 中较小者，每 100ms 采样。

修改采集参数需重采并重验同步／覆盖；修改提取和 target 参数需写入新输出并重跑；不能回写旧封存结果或强套旧人工操作。MapTR fixed_num=20、shift_v2 padding 和标签语义属于当前适配器契约，改变它们需要同步修改模型侧配置与校验。
