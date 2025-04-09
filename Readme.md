# Tree-sitter的简单教程

## 安装 & 简单用法
- 安装tree-sitter
```sh
pip install tree-sitter==0.23.2
pip install tree-sitter-c==0.23.4
```
- 初始化
```python
from tree_sitter import Language, Parser, Node
import tree_sitter_c
# 加载语言库
language = Language(tree_sitter_c.language())
parser = Parser(language)

Code = """ 
...
"""
tree = parser.parse(bytes(Code,'utf8'))
root_node = tree.root_node
```
- 简单用法

见 [test.ipynb](test.ipynb)

## 复杂用法
- 见 [Cmodule.py](Cmodule.py) ,里面涉及获取代码中的各种结构的代码，包括函数、数据结构、宏定义等，还能搜索目录下的头文件、以及其中的相关数据结构定义（不过最好是同目录下的，设置了搜索深度，无法搜索太多层）
- [Cmodule.md](Cmodule.md) 中描述了 Cmodule.py 的功能，但由于是从老版本的tree-sitter直接转成新版本，一些用法可能存在差异，修改结果不一定完全正确
- 主要的差异在于：
    - 老版本：
    ```python
    for node, capture in captures:
        ...
    ```
    - 新版本：
    ```python
    for capture, node_list in captures:
        for node in node_list:
            ...
    ```
    或者
    ```python
    for node in captures["capture"]:
        ...
    ```