# 兴语 Xingyu

《外星来信》（Message From Aliens）外星文字的同人字体，可变字重 100–900。

- 码位表与试用：[在线使用](https://windlandneko.github.io/xingyu/)
- 字体下载：[`data/Xingyu-VF.ttf`](data/Xingyu-VF.ttf)
- QQ 用：[`data/Xingyu-QQ.ttf`](data/Xingyu-QQ.ttf)，只含外星字，家族名借用 WenQuanYi Micro Hei 以便 QQ 识别，安装后在 QQ 里选这个字体。

## 用法

- 字符位于私用区 U+F7000 起：先是数字；U+F7060 起是带数字的词（序数、变量、人称、分数、幂、多边形、两位数），每行 8 格，数字对齐到同一列；其后按正式版部首的顺序分组，组内意思相近的字相邻，最后是内部记号。字不会排进别的组：新字放在所属组里相近的字旁边，放不下时追加到组末尾，再不行排到 U+F7A00 起的溢出区；游戏移除的字，其码位会由同组的新字回收。v1.1 起码位冻结，此后游戏调整分类时已分配的码位不变。
- 自造字：游戏里没有、本字体按游戏的组字方式补全的字，码位表里以浅色底标出，详情里标为「自造字」。包括数字组里的序数 4–7、反向序数 4–7、第 0 人称、分数 1/0、1/1、1/4–1/7、0、1、4–7 次幂、零边形、二边形、七边形、两位数表补全的格子，五横记号 ht5，以及横线系列补到五横的字（loop4–5、overlord、supreme 等）。
- `ss01`：阿拉伯数字写成七进制兴语数字。
- `ss02`：英文单词换成对应的字；两个字之间有一个空格不占位，多打一个才留空。
- 字符是方块字，竖排时直立居中；CSS 里混排 ss02 英文要加 `text-orientation: upright`。
- 软件不支持 OpenType 特性时，在码位表网页里「复制为 PUA」再粘贴。

## 构建

```sh
uv run --with-requirements requirements.txt python build_font.py  # 读取 source/，生成 data/ 里的 TTF、WOFF2 和码表
uv run --with-requirements requirements.txt python test_font.py data/Xingyu-VF.ttf
cd web && npm install && npm run dev
```

游戏更新时先运行 `prepare.py`，从游戏文件重新生成 `source/words.csv` 和 `source/glyphs.json`。

`python3 update.py` 把整个流程串起来：Steam 有新版本时，从 Parallels 虚拟机同步游戏，然后依次运行 prepare、build、test。码位有增删改时，生成 `.update/diff.html`（绿增、红删、蓝改）和发版说明草稿 `.update/notes.md`，然后停下等人确认，确认后运行 `python3 update.py publish`；码位没有变化时直接提交、打 tag 并发布 Release。

优化只合并轮廓、指令、字宽及全部字重变化数据均相同的字形，保留码位、字形编号和 OpenType 特性；构建时自动执行，也可单独运行 `optimize_font.py`。

网页加载 WOFF2，下载按钮提供 TTF。为继续从字体内部读取搜索与 PUA 转换所需的对应关系，WOFF2 的[标准附加数据区](https://www.w3.org/TR/WOFF2/#Private)内保存 Deflate 压缩的原始 `cmap`、`post` 表，使用浏览器原生解压。

| 目录      | 内容                                      |
| --------- | ----------------------------------------- |
| `source/` | 词表、笔画、单位和码位登记表              |
| `data/`   | 生成的字体和码表                          |
| `web/`    | 码位表网页（Vite），推送到 `main` 后发布 |

## 授权

非官方同人作品，仅限个人非商业使用。字形版权归 Artless Games。
