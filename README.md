# 兴语 Xingyu

《外星来信》（Message From Aliens）外星文字的同人字体，可变字重 100–900。

- 码位表与试用：[在线使用](https://windlandneko.github.io/xingyu/)
- 字体下载：[`data/XingyuDemo-VF.ttf`](data/XingyuDemo-VF.ttf)

## 用法

- 字符位于私用区 U+F7000 起，按游戏字典的类别排列；已分配的码位不会再变。
- `ss01`：阿拉伯数字写成七进制兴语数字。
- `ss02`：英文单词换成对应的字；两个字之间的空格不显示，多打一个才留空。
- 软件不支持 OpenType 特性时，在码位表网页里「复制为 PUA」再粘贴。

## 构建

```sh
uv run --with-requirements requirements.txt python build_font.py  # 读取 private/，生成 TTF、WOFF2 和码表
cd web && pnpm install && pnpm dev
```

已有 TTF 可原地优化并生成 WOFF2，不需要 `private/`：

```sh
uv run --with-requirements requirements.txt python optimize_font.py
# 也可以在命令末尾指定一个或多个 TTF 路径
```

优化只合并轮廓、指令、字宽及全部字重变化数据均相同的字形，保留码位、字形编号和 OpenType 特性。Demo TTF 从 1,582,116 字节降至 1,112,512 字节（减少 29.7%）。可重复执行。

网页加载 WOFF2，下载按钮提供 TTF。为继续从字体内部读取搜索与 PUA 转换所需的对应关系，WOFF2 的[标准附加数据区](https://www.w3.org/TR/WOFF2/#Private)内保存 Deflate 压缩的原始 `cmap`、`post` 表，使用浏览器原生解压；内容均来自公开 TTF。

发布：在 `web/` 执行 `pnpm build`，自动复制并检查 Demo TTF、WOFF2 和码表，并核对两种字体的对应关系。完整版仅供本地开发使用。公开 JSON 不含词名、词名哈希或英文释义。

| 目录 | 内容 |
| --- | --- |
| `data/` | 字体和网页数据。仓库里只有 Demo 版，完整版只在本地生成 |
| `private/` | 输入数据和完整的码位登记表，不提交 |
| `web/` | 码位表网页（Vite），推送到 `main` 后由 Actions 发布 |

## 授权

非官方同人作品，仅限个人非商业使用。字形版权归 Artless Games。
