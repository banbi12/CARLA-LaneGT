# 问题排查

| 现象 | 检查 |
| --- | --- |
| 缺少配置／map_profile | 先 prepare_map，再 configure --output config/paths.<town>.local.json；所有命令显式 --paths |
| 指纹或地图不匹配 | 真实 CARLA 导出、profile、缓存、顶视 metadata 必须属于同一地图版本；不要改摘要绕过 |
| 非 Town05 reference 被拒绝 | reference 使用 `<Town>_` 前缀；目录名、metadata.case_id 和清单一致 |
| 顶视覆盖失败 | 检查完整姿态、ego 高度、K、FOV、安全边缘与完整 XYZ 棱柱；不要按 z=0 估算 |
| boundary 缺失或未接通 | 可能缺少结构锚点、同层观测、正确分类或超出连接规则；人工检查原始 XODR 和顶视 |
| 人行道背侧被标为 boundary | 基础单向参考线候选可能有此问题；已知实例保留人工处理 |
| 多端点／分叉 | 核对是否真实分叉、有意 boundary 切分、ROI 边界或严格容差以外的几何；不要无限扩大合并距离 |
| centerline 合并后采样更粗 | 比较完整曲线与固定 20 点；偏差是模型表示代价，非原几何丢失 |
| 没有 NPZ／points 为 null | 默认通用几何不采样，配置模型环境并显式 --sampler maptr 或 export-maptr |
| CXXABI / libstdc++ 导入错误 | 使用 run.py 选择模型解释器与其库；不要用系统库覆盖整个环境 |
| 图册空白／数据未加载 | 使用 Firefox，保留目录结构和被链接输入；确认每帧 COMPLETE、audit_data.js 与 GT 摘要 |
| 人工 JSON 不匹配 | 源图册版本、GT 摘要、数据集身份不可混用；审核 JSON 和几何补线 JSON 入口不同 |
| GPU／服务已占用 | 不启动第二个采集服务；只清理本次创建的服务和进程，检查显存记录 |

原始数据不随源码包提供。首次安装只能验证工具、接口和合成测试；真实提取需要自己的匹配资源。
