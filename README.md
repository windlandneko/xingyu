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
pip install -r requirements.txt
python3 build_font.py                         # 读取 private/，写入 data/
python3 test_font.py data/XingyuDemo-VF.ttf
cd web && npm ci && npm run dev
```

发布：在 `web/` 执行 `pnpm build`，自动复制并检查 Demo 字体和码表。完整版仅供本地开发使用。网页搜索和 PUA 转换读取字体中的对应关系；公开 JSON 不含词名、词名哈希或英文释义。

| 目录 | 内容 |
| --- | --- |
| `data/` | 字体和网页数据。仓库里只有 Demo 版，完整版只在本地生成 |
| `private/` | 输入数据和完整的码位登记表，不提交 |
| `web/` | 码位表网页（Vite），推送到 `main` 后由 Actions 发布 |

## 授权

非官方同人作品，仅限个人非商业使用。字形版权归 Artless Games。
