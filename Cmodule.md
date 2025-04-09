
# Cmodule.py 模块文档

## 概述
- `Cmodule` 类提供了一个用于解析和操作 C代码项目的工具，支持处理宏定义、函数调用、类型定义等多方面的代码分析功能。
- 该模块依赖于 `tree_sitter` 语法树解析库来分析代码。

- `tree_sitter`需要为目标语言语言编译一个库(此处是C语言)，如[`SPM/tree_sitter/make_li.py`](tree_sitter/make_lib.py)所示。

## 类和方法

### 类 `Cmodule`

#### 构造函数
- **`__init__(self, input:str, project_dir:str = "")`**
  - **参数**:
    - `input`: 字符串，可以是文件路径或直接的代码字符串。
    - `project_dir`: 字符串，可选，指定项目的根目录路径。
  - **功能**:
    - 初始化类实例，加载文件或代码，解析文件路径，处理项目目录。
    - 读取并解码文件内容（如果 `input` 是路径），或直接使用提供的代码字符串。
    - 清除代码中的注释，并构建代码行映射。

#### 方法

- **`clear_code(self)`**
  - 清除源代码中的所有注释，并更新行映射，以便后续分析时能正确关联到源代码的行号。

- **`find_path_in_project(self, partial_path)`**
  - 在指定的项目目录中搜索包含给定部分路径的文件，返回完整路径。
  - 这里采取的方法就是直接在项目中遍历，由于C语言固有的找依赖挑战，在没有编译的情况下，只能使用者笨方法

- **`get_all_headers(self)`**
  - 提取当前代码文件中所有包含的头文件路径。

- **`get_header_path(self, header)`**
  - 根据头文件的相对路径或名称获取完整路径。

- **`is_macro_definition(self, s)`**
  - 检查指定字符串是否为宏定义。
  - 默认全大写且使用该函数进行判断就是宏定义，`tree_sitter`只能判断出这是个`identifier`

- **`get_all_preproc_defs(self)`**
  - 获取文件中所有预处理宏定义的节点。

- **`get_preproc_def_text(self,identifier:str)`**
  - 获取宏定义节点的text格式

- **`get_preproc_def(self, identifier)`**
  - 获取指定标识符的宏定义。

- **`get_preproc_def_include_line_index(self, new_line_index: int)`**
  - 获取包含指定行（从0开始）的宏定义节点

- **`get_enum_def(self, identifier)`**
  - 获取指定枚举类型的定义。

- **`dosomething_in_headers(self, func_name, *args, **kwargs)`**
  - 在所有头文件中递归执行指定函数，用于跨文件分析和处理。
  - 使用线程本地存储来管理递归深度
  ```python
  import threading
  # 使用线程本地存储来管理递归深度
  depth_tracker = threading.local()
  depth_tracker.value = 0
  MAX_DEPTH = 6
  ```

- **`get_function_include_line_index(self, new_line_index:int)`**
  - 获取包含指定行（从0开始）的函数节点

- **`get_all_function_nodes(self)`**
  - 获取当前文件中所有函数定义的节点。

- **`get_all_function_declaration_nodes(self)`**
  - 获取所有函数声明节点。

- **`get_function_names(self, function_nodes:list[Node]) -> list[str]`**
  - 获取函数节点列表中全部函数的全部函数名

- **`get_function_node(self, function_id)`**
  - 根据函数名称获取对应的函数节点。

- **`get_function_signature(self, function_id)`**
  - 获取指定函数的完整签名，包括存储类说明符、返回类型和函数声明。

- **`get_call_func_in_line(self, new_line_number)`**
  - 获取指定行号中的所有函数调用。

- **`get_all_call_functions(self) -> list[Node]`**
  - 获取全部的函数调用

- **`get_typedef_ids_from_node(self, node)`**
  - 从给定节点中提取所有类型定义的标识符

- **`check_header_used(self, header)`**
  - 检查指定的头文件是否在当前文件中被使用

- **`get_all_preproc_def_ids_in_node(self, n:Node) -> list[str]`**
  - 获取节点中定义的所有预处理宏的标识符

- **`get_all_extern_gloabal_vars(self)`**
  - 获取所有外部（extern）全局变量的声明。

- **`get_all_global_vars_init_and_declaration(self)`**
  - 获取所有全局变量的初始化和声明。

- **`get_node_in_line(self, new_line_number:int)`**
  - 根据行号（删除comments后的行号）获取对应的语法树节点。

- **`get_vars_in_line(self, new_line_number:int)`**
  - 获取指定行中的所有变量标识符。

- **`get_local_var_def(self, func_node:Node, identifier:str)`**
  - 获取指定函数节点中的局部变量定义。

- **`get_var_init_and_declaration_nodes_from_node(self, node:Node, identifier:str)`**
  - 获取指定节点中变量的所有初始化和声明节点。

- **`get_local_var_def_new(self, func_node:Node, identifier:str)`**
  - 获取局部变量的定义，包括声明和初始化。

- **`get_struct_def(self, type_identifier:str) -> list[Node]`**
  - 根据类型标识符获取结构或类型的定义。

- **`get_all_struct_nodes(self) -> list[Node]`**
  - 获取所有结构、枚举和类型定义的节点。

- **`get_field_type_in_struct(self, struct_type:str, field_identifier)`**
  - 在给定的结构类型中找到字段的类型。

- **`get_switch_lines(self, new_line_index:int)`**
  - 获取包含指定行的 switch 语句的开始和结束行号。



