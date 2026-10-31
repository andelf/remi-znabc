# 智能 ABC · Rime 复原项目

当前可安装版本：**0.1.2**。在 Rime 上实现原样本的基础拼音、音形后缀、纯笔形输入及静态候选排序，采用空格后数字选字的两阶段操作，支持 `v` 前缀临时英文输入。

## 安装测试

前提：已安装 Rime 前端，且包含 **librime-lua**。本方案是 Lua 插件与数据包，无需编译 C++。

使用 `dist/rime-znabc-0.1.2.zip`，解压后进入里面的 `rime-znabc-0.1.2` 目录。
安装器需要 Python 3.8 或以上，仅使用标准库。下面任选符合你的前端的一条命令：

```powershell
py install.py --user-dir "$env:APPDATA\Rime"
```

```sh
python3 install.py --user-dir "$HOME/Library/Rime"
```

```sh
python3 install.py --user-dir "$HOME/.local/share/fcitx5/rime"
```

```sh
python3 install.py --user-dir "$HOME/.config/ibus/rime"
```

以上依次对应小狼毫、鼠须管、fcitx5-rime、ibus-rime 的常见用户目录。
若曾修改过用户目录，以前端菜单打开的“用户文件夹”为准。
安装器会复制方案、Lua 和数据，向已有方案列表追加 `znabc`，并备份覆盖文件到用户目录的 `.znabc-backups/`。
可以先加 `--dry-run` 查看计划。复杂的 `default.custom.yaml` 格式会明确报错并停止写入；此时使用 `--no-enable`，手动加入方案列表。

完成后在前端执行 **重新部署**，打开方案选单，选 **智能 ABC · 复原**。

### 没有 Python 时手动安装

把安装包 `rime/` 里面的以下三个项目复制到 Rime 用户目录根部：

```text
znabc.schema.yaml
lua/
znabc_data/
```

`lua/` 与已有同名目录合并。模块放在 `lua/znabc/`，不需要修改已有 `rime.lua`。
在 `default.custom.yaml` 的现有 `patch:` 下添加以下两行；已有同名补丁键时，应直接在现有方案列表中追加 `schema: znabc`：

```yaml
patch:
  "schema_list/@next":
    schema: znabc
```

不要把第二个 `patch:` 粘贴到已有 `patch:` 的文件末尾。重新部署后切换方案。

## 键位与测试样例

| 按键 | 当前行为 |
| --- | --- |
| 字母 | 输入拼音或声母简拼 |
| `1..8` | 编码阶段输入形码，包括纯数字笔形输入；选单打开后选择对应候选 |
| `'` | 显式音节分隔 |
| 空格 | 第一次结束编码、打开选单，不上屏；选单打开后确认当前高亮候选 |
| `1..9`（选字阶段） | 选择当前页对应候选；无对应候选时保持选单 |
| `Ctrl+1..9` | 选单打开后也可选择当前页对应候选 |
| 上下方向键 | 移动候选高亮 |
| `PageUp` / `PageDown`、`-` / `=` | 翻页 |
| `Backspace` | 删除编码；选单打开时先返回编码阶段 |
| `Esc` | 选单打开时关闭选单、保留编码；编码阶段取消当前输入 |
| 单击 `Shift` | 切换中西文；有编码时先提交编码 |
| `v` + 英文字母或数字 → 空格 | 直接上屏去掉首个 `v` 的内容，保留大小写，不切换中西文 |

编码阶段不显示候选，数字不用于选字。按空格后才产生候选，数字不再追加形码。
选单打开后输入字母或分隔符会返回编码阶段继续输入；没有候选时，空格不会把原始编码上屏。
输入句点等中文标点仍可确认当前首选并输出标点。
临时英文示例：`vlove` → 空格直接上屏 `love`，无需第二次空格；`vLove` → 空格上屏 `Love`。
临时英文支持退格修改和 Esc 取消，提交后继续中文输入。单独 `v` → 空格上屏 `v`，`vv` → 空格也上屏 `v`。

建议实际安装后测试：

| 输入 | 预期 |
| --- | --- |
| `nihao`、`ni32hao63`、`ni3hao6` | 第一次空格显示首选“你好”，再按空格或 `1` 上屏 |
| `nihao32`、`ni32hao43` | 不应出现词条“你好”；可先选前面的单字，后面的编码继续保留 |
| `shi81` | 包含“时、是、匙”；排序由原始字频及内部码决定 |
| `ni32` | 包含“你、倪、伲”；形码后缀不保证唯一候选 |
| `ke18` / `ke15` | 前者包含“可”，后者不包含“可” |
| `3235` | 空格后候选依次“仂、你、仍”，按 `2` 选择“你” |
| `ni32` → 空格 → `2` | 上屏“倪”，数字 `2` 不追加到编码 |
| `xian` / `xi'an` | 前者按 xian 查询；后者显示 xi、an 两个音节 |
| `changan` / `chang'an` | 前者切 chan + gan；后者切 chang + an |

候选词只覆盖输入前半段时，选中后保留剩余编码并返回编码阶段；再次按空格打开剩余编码的选单。本版不自动把多个短词拼成一个整句候选。

反馈时请提供：前端及系统、原始按键串、候选顺序、实际上屏结果、期望结果；出错时附前端日志中的 `znabc` / `Lua` 信息。

## 数据与兼容范围

使用已有逆向结果直接生成：

- 75,705 条基础词记录，保留原始内部字码、权重和词库顺序。
- 7,231 条有读音的单字记录，包含多音字的独立读音码。
- 7,787 条正常基础笔形关系；不可输入的异常标记不进入运行数据。
- 拼音形码后缀使用专用摘要表，不以完整笔形码前两位替代。
- 单字频度从原 OVL 的频度区恢复，未覆盖的字按原函数回退值处理。
- 词候选先取最长有结果的词长，同词长按权重降序、同分保留词库顺序。
- 单字按权重降序，同分按内部字码升序；纯笔形按原表顺序。

本版本只接入基础词库。扩展字库、用户自造词、选择历史、临时词三次晋升、特殊输入模式及原界面交互尚未接入。
运行时不写学习数据，因此本轮实际测试的候选顺序可重复。
原样本的非官方版本标识和适用范围见上级 `analysis/znabc-analysis.txt`。

## 开发

目录结构：

```text
rime/znabc.schema.yaml       Rime 方案与键位
rime/lua/znabc_processor.lua 编码与选字状态、空格和数字按键
rime/lua/znabc_translator.lua 候选区间、预编辑与 Rime 适配
rime/lua/znabc/parser.lua    移植的连续输入解析
rime/lua/znabc/engine.lua    查询、过滤和排序
rime/lua/znabc/dictionary.lua 数据加载与分桶缓存
tools/build_data.py         从已有样本生成数据
tools/install.py            复制安装及配置追加、备份
tools/package.py            构建完整安装 ZIP
tests/                      Lua、原 x86 对照和真实 Rime API 测试
```

从当前工作区构建：

```sh
python3 tools/build_data.py
python3 tools/package.py
```

生成数据会引用上级 `analysis/znabc_formats.py` 和已解压的样本；安装包运行不依赖它们或 Python。
词库按前两字首字母分成 516 个桶，按需读取并缓存，避免每次按键全表扫描。

有 Lua 5.4 时执行内核测试：

```sh
lua5.4 tests/test_engine.lua .
python3 -m unittest discover -s tests -p 'test_installer.py' -v
```

原 x86 对照测试还需要已有的 `uv`、Unicorn 和上级分析文件：

```sh
uv run --no-project --python /usr/bin/python3 --with unicorn python tests/test_native_compat.py --lua /absolute/path/to/lua5.4
```

`tests/rime_smoke.cc` 通过真实 `librime` 与 `librime-lua` 测试部署、逐键输入、选词上屏、部分消费和西文模式；Linux 下需要 Rime 开发头文件及库。
本工作区的依赖只解压在 `.cache/runtime/`，没有改动系统 Rime 安装。
验证范围与版本记录见 `VERIFICATION.txt`。Windows / macOS 前端的实际界面仍由本轮人工安装验证。
