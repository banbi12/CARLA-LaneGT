# 配置与地图资源

每张地图必须使用自己的 `map_profile` 与本地 paths JSON，不从名称推断可以混用。JSON 内部路径使用绝对路径；不会展开 `~` 或 shell 变量。

默认 `extract` 使用 `config/extraction/semantic_policy.json` 中的 XODR 外缘对齐连接；无需额外选择试验策略。可用 `--policy /data/custom-policy.json` 显式覆盖，输出版本身份随实际路径确定，详见 [boundary 对齐](BOUNDARY_ALIGNMENT.md)。

## 地图资源

```bash
python tools/prepare_map.py --map Town03 --xodr /data/maps/server_Town03.xodr
# 可选：--world /data/cache/town03_world_v42.json
```

输出包含 `.local/maps/<Town>_<XODR摘要>/profile.json`、`nonboundary_v42.json`、`capture.json` 及 `PREPARATION.json`；资源存放于 `assets/capture/` 和 `assets/maps/` 的同名独立空间。地图原文、世界缓存、非 boundary 基线均记录摘要。工具不会覆盖已有空间；已有资源应复用对应 profile。

`--world` 缓存须声明正确地图、XODR 指纹与 V4.2 保留几何审计。未提供缓存时离线调用原生、多 laneSection、完整 XYZ 的 V4.2 构建链。此步骤不是实测 CARLA waypoint 验证；后续捕获还会检查真实服务的地图名和精确 XODR 指纹。

配置文件只绑定地图资源，不能通过重新计算摘要来使不匹配的数据变得正确。新地图／新 CARLA 版本仍需真实采集和视觉检查。

## 每地图运行配置

```bash
cp config/paths.example.json /tmp/town03-paths.json
# 修改以下实际字段，然后生成不被 Git 跟踪的配置：
python tools/configure.py --from-json /tmp/town03-paths.json \
  --output config/paths.town03.local.json
```

| 字段 | 用途 |
| --- | --- |
| `map_profile` | prepare_map 输出的 profile，必需 |
| `frame_manifest` | 逐帧 JSON 清单，必需 |
| `topdown_root` | `<reference>/rgb.png` 等的父目录；semantic 必需 |
| `data_root` | 工作数据根目录及输出保护范围 |
| `capture_config` / `cases` | 重新采集时必需，已有自包含顶视数据可省略 |
| `camera_metadata` / `camera_images` | 六相机审核；纯顶视可省略 |
| `centerline_labels` | 仅 `--centerline provided` |
| `runtime_python` | CPU 几何解释器；省略时为配置工具的 Python |
| `model_root` / `maptr_python` | 可选 MapTRv2 仓库与解释器 |
| `carla_root` / `carla_python` | 仅采集时使用的 CARLA 安装与 API 环境 |
| `review60` | 默认图册位置，保留历史字段名，不限制为 60 帧 |
| `protected_output_roots` | 禁止写入的输入或历史结果路径 |

配置工具补全 `project_root` / `dataset_adapter_root`，将新相机字段映射为内部 `native_metadata` / `native_images` / `native_labels`。两套字段同时提供且不同会拒绝。缺省相机和标签路径指向禁写占位目录；不意味着已提供对应数据。

配置目标须以 `.local.json` 结尾且不存在。不覆盖本机现有配置。仅部署 XODR 基线时可加 `--xodr-only`，免除 topdown_root 必填；仍需 map_profile 和帧位姿。

```bash
python run.py --paths config/paths.town03.local.json doctor --topdown-only
python run.py --paths config/paths.town03.local.json doctor --topdown-only --xodr-only
```

doctor 检查所选输入和地图绑定，不启动 GPU，也不代替逐帧同步、覆盖与视觉检查。所有新结果目录须不存在，并避开代码、资源、输入和原有图册。

后处理优先读取源图册携带的 `config/paths.json`；源图册及外部原图／顶视数据应保留。`src/postprocessing/project.json` 若手工创建，仅作本地覆盖，不能加入发布包。
