from tree_sitter import Language, Parser, Node
import tree_sitter_c
import re, os
import chardet
# 加载C语言的解析器库
C_LANGUAGE = Language(tree_sitter_c.language())
parser = Parser(C_LANGUAGE)

# 跨文件相关
import threading
# 使用线程本地存储来管理递归深度
depth_tracker = threading.local()
depth_tracker.value = 0
MAX_DEPTH = 6

class Cmodule():
    def __init__(self, input:str, project_dir:str = "") -> None:
        self.project_dir = project_dir
        self.clear_comments_line_map = {}
        self.is_path = False 
        if os.path.exists(input) and (input.endswith('.c') or input.endswith('.h')):
            raw_data = open(input,'rb').read()
            encoding = chardet.detect(raw_data)['encoding']
            self.code = self.original_code = raw_data.decode(encoding)
            self.path = input
            if not project_dir:
                projects_dir = '/public/github_repos/github_repos_c'
                if input.startswith(projects_dir):
                    dir = input[len(projects_dir):].split('/')[1]
                    self.project_dir = f'{projects_dir}/{dir}'
                    # print("文件在默认路径中，project_dir为",self.project_dir)
                    self.is_path = True # 可以跨文件
            elif not input.startswith(project_dir):
                print("文件不在项目中！")
            else:
                self.is_path = True # 可以跨文件
        else:
            self.code = input
            self.is_path = False # 不可跨文件
            self.path = ""
            print("未给出路径，不可跨文件查找！")
        # 清除代码中的comments,且得到
        # self.clear_comments_line_map 一个从清除前代码行到清楚后代码行的映射（如果清除前是comment或者空行则会报错）
        self.clear_code()
        tree = parser.parse(bytes(self.code,'utf8'))
        self.root_node = tree.root_node
        self.libs = {} # 缓存， 之后可以改成同一项目所有文件共享一个缓存，也许可以设置一个缓存文件
        self.all_function_nodes = []
        self.all_function_declaration_nodes = []
        
    def clear_code(self):
        def replace_multiline_comment(match):
            comment = match.group(0)
            lines = comment.count('\n')
            return '\n' * lines
        code = self.code
        # 旧行
        old_code = re.sub(r'/\*[\s\S]*?\*/', replace_multiline_comment, code)
        old_code = re.sub(r'//.*', '', old_code)
        old_lines = old_code.splitlines()
        # 移除空行, 得到新行
        new_lines = [line for line in old_lines if line.strip()]
        # 计算新的行号
        new_line = 0
        old_line = 0
    
        while old_line < len(old_lines) and new_line < len(new_lines):
            if old_lines[old_line].strip() == new_lines[new_line].strip():
                self.clear_comments_line_map[old_line + 1] = new_line + 1
                old_line += 1
                new_line += 1
            else: 
                old_line += 1
        self.code = '\n'.join(new_lines)
    
    # 这是个笨方法，如果能够缩小遍历范围更快
    # 在项目目录中查找文件，对于系统库的情况，暂不考虑
    def find_path_in_project(self, partial_path):
        # Examples：
        # onlplib/file.h
        # onlp/platformi/thermali.h
        # platform_lib.h
        if partial_path in self.libs.keys():
            return self.libs[partial_path]
        for root, _, files in os.walk(self.project_dir):
            for file in files:
                # 计算文件的相对路径
                path = os.path.join(root, file)
                # 检查相对路径是否以指定的部分路径结尾
                if path.endswith(partial_path):
                    result = os.path.abspath(os.path.join(root, file))
                    # 如果是头文件则存入缓存
                    if result.endswith('.h'):
                        self.libs[partial_path] = result
                    return result
        return ""
    
    # 获取当前文件所有头文件
    def get_all_headers(self):
        res = []
        # 前者匹配 "platform_lib.h"
        # 后者匹配 <onlp/platformi/thermali.h>
        query = C_LANGUAGE.query("""
        (
            (preproc_include
                (string_literal) @header)
            )
            (
            (preproc_include
                (system_lib_string) @header_lib)
            )
        """)

        captures = query.captures(self.root_node)
        headers = []
        for header_file, nodes in captures.items():
            for node in nodes:
                header_patial_path = node.text.decode()
                headers.append(header_patial_path)
        return headers
    
    def get_header_path(self, header:str):
        # Examples：
        # <onlplib/file.h>
        # <onlp/platformi/thermali.h>
        # "platform_lib.h"
        header_clean = header.strip('"<>')
        if header_clean in self.libs.keys():
            return self.libs[header_clean]
        if header.endswith('"') and self.is_path:
            parent_dir = os.path.dirname(self.path)
            abs_path = os.path.join(parent_dir, header_clean)
            if os.path.exists(abs_path):
                return abs_path
        return self.find_path_in_project(header_clean)
    
    def is_macro_definition(self, s):
        if not s:
            return False
        # 判断字符串是否全为大写字母或下划线
        return s.isupper() and all(c.isupper() or c == '_' for c in s)
    
    # 获得当前文件所有的宏定义
    def get_all_preproc_defs(self) -> dict[str:Node]:
        query = C_LANGUAGE.query(f"""
        (preproc_def
            name: (identifier) @macro_def
        ) 
        (preproc_function_def
            name: (identifier) @macro_def
        ) 
        """)
        captures = query.captures(self.root_node)
        res = {}
        for _, nodes in captures:
            for node in nodes:
                res[node.text.decode()] = node.parent
        return res
    
    
    def get_preproc_def_text(self,identifier:str):
        res = self.get_preproc_def(identifier)
        return '\n'.join([f"{node.text.decode()}"for node in res])
    
    # 获取当前文件指定宏定义
    def get_preproc_def(self,identifier:str) -> list[Node]:
        query = C_LANGUAGE.query(f"""
        (preproc_def 
            name: (identifier) @macro_name 
            (#eq? @macro_name "{identifier}")
        ) @macro_def
        (preproc_function_def
            name: (identifier) @macro_name 
            (#eq? @macro_name "{identifier}")
        ) @macro_def
        """)
        captures = query.captures(self.root_node)
        results = []
        for node in captures["macro_def"]:
            results.append(node)
        
        if results:
            return results
        # 本文件中找不到宏定义，获取所有头文件
        # 只有input为路径才能跨文件找
        if self.is_path:
            Cross_file_res = self.dosomething_in_headers('get_preproc_def', identifier)
            if Cross_file_res:
                return Cross_file_res
        # 都没找到
        return []
    
    def get_preproc_def_include_line_index(self, new_line_index: int):
        query = C_LANGUAGE.query(f"""
        (preproc_def
            name: (identifier) @macro_def
        ) 
        (preproc_function_def
            name: (identifier) @macro_def
        ) 
        """)
        captures = query.captures(self.root_node)
        all_preproc_def_nodes = [node.parent for node in captures["macro_def"]]
        
        # 遍历节点，找到包含指定行号的节点
        for preproc_def_node in all_preproc_def_nodes:
            if preproc_def_node.start_point[0] <= new_line_index and new_line_index < preproc_def_node.end_point[0]:
                return preproc_def_node
        
        return None
    
    def get_enum_def(self, identifier:str):
        query = C_LANGUAGE.query(f"""        
        (enum_specifier
            (enumerator_list
                (enumerator
                    name: (identifier) @enum_name
                    (#eq? @enum_name "{identifier}")
                )
            )
        )""")
        captures = query.captures(self.root_node)
        results = []
        for node in captures["enum_name"]:
            results.append(node.parent.parent.parent)
        if results:
            return results
        # 本文件中找不到，获取所有头文件
        # 只有input为路径才能跨文件找
        if self.is_path:
            Cross_file_res = self.dosomething_in_headers('get_enum_def', identifier)
            if Cross_file_res:
                return Cross_file_res
        # 都没找到
        return []
    
    # 跨文件执行指定函数
    def dosomething_in_headers(self, func_name, *args, **kwargs):
        if depth_tracker.value >= MAX_DEPTH:
            return None
        if self.is_path:
            headers = self.get_all_headers()
            # 得到所有头文件路径
            header_paths = [self.get_header_path(header) for header in headers]
            for header_path in header_paths:
                # 在头文件中查找
                if not header_path:
                    continue
                depth_tracker.value += 1
                header_module = Cmodule(header_path, self.project_dir)
                # 获取新实例上的同名方法
                method_to_call = getattr(header_module, func_name, None)
                if method_to_call is None or not callable(method_to_call):
                    raise AttributeError(f"方法 '{func_name}' 不存在或不可调用")
                Cross_file_res = method_to_call(*args, **kwargs)
                
                # 缓存
                ###################
                
                # 如果该头文件中找到了，就返回
                if Cross_file_res:
                    depth_tracker.value -= 1
                    return Cross_file_res 
        depth_tracker.value -= 1
        return None
    
    # # 获取指定节点的identifier，通常是name
    # def get_node_identifier(self, node:Node):
    #     # 检查是否有子节点，通常 name 会是 identifier 类型的子节点
    #     for child in node.named_children:
    #         if child.type == 'identifier':
    #             return child.text  # 返回宏定义的名称
    #     return None

    # new_line = self.clear_comments_line_map[old_line]
    def get_function_include_line_index(self, new_line_index:int):
        all_functions_nodes = self.get_all_function_nodes()
        for function_node in all_functions_nodes:
            if function_node.start_point[0] <= new_line_index <= function_node.end_point[0]:
                return function_node
        return None
    
    def get_all_function_nodes(self) -> list[Node]:
        if self.all_function_nodes:
            return self.all_function_nodes
        query = C_LANGUAGE.query(f"""(function_definition)@function""")
        captures = query.captures(self.root_node)
        self.all_function_nodes = captures["function"]
        return self.all_function_nodes
            
    def get_all_function_declaration_nodes(self) -> list[Node]:
        if self.all_function_declaration_nodes:
            return self.all_function_declaration_nodes
        query = C_LANGUAGE.query(f"""
        (declaration
            declarator: (function_declarator) @function_declarator
        )
        """)
        captures = query.captures(self.root_node)
        for node in captures["function_declarator"]:
            self.all_function_declaration_nodes.append(node.parent)
        return self.all_function_declaration_nodes
    
    def get_function_names(self, function_nodes:list[Node]) -> list[str]:
        res = []
        for node in function_nodes:
            if not node:
                continue
            function_declarator = node.child_by_field_name('declarator')
            # if not function_declarator:
            #     print()
            func_id_node = function_declarator.child_by_field_name('declarator') 
            res.append(func_id_node.text.decode())
        return res
        
    
    def get_function_node(self, function_id):
        query = C_LANGUAGE.query(f"""
        (function_definition
            (function_declarator 
                (identifier) @function_id 
                (#eq? @function_id "{function_id}")
            )
        )""")
        captures = query.captures(self.root_node)
        if captures:
            return captures["function_id"][0].parent.parent
        preproc_def_nodes =  self.get_preproc_def(function_id)
        if preproc_def_nodes:
            for preproc_def_node in preproc_def_nodes:
                if preproc_def_node.type == "preproc_function_def":
                    return preproc_def_node
        return None

    def get_function_signature(self,function_id):
        function_node = self.get_function_node(function_id)
        if not function_node:
            return None
        query = C_LANGUAGE.query("""
        (function_definition
            (storage_class_specifier)* @storage_class_specifier
            type:(_) @ret
            declarator:(function_declarator) @function_declarator
        )
        """)
        res = {
            "storage_class_specifier":[],
            "ret" : "",
            "function_declarator" : ""
        }
        for capture, nodes in query.captures(function_node).items():
            if capture == "storage_class_specifier":
                res[capture].extend([node.text.decode() for node in nodes])
            else:
                res[capture] = [node.text.decode() for node in nodes]
        static = "\n".join(res['storage_class_specifier'])
        ret = res["ret"]
        function_declarator = res["function_declarator"]
        return f"""{static} {ret} {function_declarator}""" 
    
    def get_call_func_in_line(self, new_line_number:int):
        # 首先找到这一行所在的node
        target_node = self.get_node_in_line(new_line_number)
        if not target_node:
            return None
        # 再在node中查询call_expression
        query = C_LANGUAGE.query(f"""
        (call_expression
            function: (identifier)@identifier
        )""")
        res = []
        captures = query.captures(target_node)
        for node in captures["identifier"]:
            res.append(node.text.decode())
        return res
    
    def get_all_call_functions(self) -> list[Node]:
        query = C_LANGUAGE.query(f"""
        (call_expression
            function: (identifier)@identifier
        )""")
        call_functions = []
        captures = query.captures(self.root_node)
        for node in captures["identifier"]:
            call_functions.append(node)
        return call_functions
    
    # def get_external_call_functions(self) -> list[Node]:
    #     if not self.is_path or not self.project_dir:
    #         raise AssertionError("没有文件或项目路径信息，无法获得外部函数")
    #     all_call_functions = self.get_all_call_functions()
    #     functions_defined_in_file = self.get_all_function_nodes()
    #     external_functions = [func_node for func_node in all_call_functions if func_node not in functions_defined_in_file]
    #     return external_functions
    
    def get_typedef_ids_from_node(self, node:Node) -> list[str]:
        query = C_LANGUAGE.query(f"""(type_identifier) @type_identifier""")
        type_ids = []
        for node in query.captures(node)["type_identifier"]:
            type_ids.append(node.text.decode())
        return type_ids
    
    def check_header_used(self, header:str):
        if not self.is_path or not self.project_dir or not header:
            raise AssertionError("没有文件或项目路径信息，无法获得外部函数")
        path = self.get_header_path(header) 
        if not path:
            # 没有找到路径，可能是标准库，也有可能不在项目中
            return f"没有在项目中找到头文件{header}, 可能是标准库"
        header_module = Cmodule(input=path,project_dir=self.project_dir)
        ################################################################################
        # 函数
        ## 当前文件的调用函数
        call_func_nodes = self.get_all_call_functions()
        call_func_names = set([node.text.decode() for node in call_func_nodes if node])
        if call_func_names:
            ## header中的函数定义和函数声明
            header_func_nodes = header_module.get_all_function_nodes() \
                + header_module.get_all_function_declaration_nodes()
            # 去重
            header_func_nodes = list(set(header_func_nodes))
            header_func_names = set(header_module.get_function_names(header_func_nodes))
            intersection_funcs = header_func_names.intersection(call_func_names)
            if intersection_funcs:
                # res = {}
                # for func_name in intersection_funcs:
                #     res[func_name] = header_module.get_function_node(func_name)
                # return res
                return True
        ################################################################################
        # 数据类型
        ## 当前文件的数据类型, 需要删去本文件中有的的定义的类型
        type_ids = set(self.get_typedef_ids_from_node(self.root_node))
        type_def_nodes = self.get_all_struct_nodes()
        type_def_ids = set()
        for node in type_def_nodes:
            if node.type == 'type_definition':
                id = node.child_by_field_name('declarator').text.decode()
            elif node.type == 'enum_specifier':
                type_id = node.child_by_field_name('name')
                if type_id:
                    id = type_id.text.decode()
                else:
                    continue
                    # type_id = "anonymous_enum"
            else:
                id = node.child_by_field_name('name').text.decode()
            type_def_ids.add(id)
        type_ids = type_ids - type_def_ids
        if type_ids:
            ## header中对应的声明和定义
            header_typedef_nodes = header_module.get_all_struct_nodes()
            header_typedef_dict = {}
            for node in header_typedef_nodes:
                if node.type == 'type_definition':
                    id = node.child_by_field_name('declarator').text.decode()
                else:
                    id = node.child_by_field_name('name').text.decode()
                header_typedef_dict[id] = node
            header_typedef_ids = set(header_typedef_dict.keys())
            intersection_type_ids = header_typedef_ids.intersection(type_ids)
            if intersection_type_ids:
                # return {type_id : header_typedef_dict[type_id] for type_id in intersection_type_ids}
                return True
        ################################################################################
        # 宏
        ## 当前文件直接使用的宏
        macro_defs = self.get_all_preproc_def_ids_in_node(self.root_node)
        ## 当前文件定义的宏删去
        macro_defs_defined = self.get_all_preproc_defs()
        macro_defs_defined_set = set(macro_defs_defined.keys())
        # 删去
        macro_defs_set = set(macro_defs) - macro_defs_defined_set
        if macro_defs_set:
            ## header中对应的定义
            header_macro_defs_defined_dict = header_module.get_all_preproc_defs()
            header_macro_defs_defined_set = set(header_macro_defs_defined_dict.keys())
            intersection_macro_defs = header_macro_defs_defined_set.intersection(macro_defs_set)
            if intersection_macro_defs:
                # return {macro_def : header_macro_defs_defined_dict[macro_def] for macro_def in intersection_macro_defs}
                return True
        ################################################################################
        # 变量
        ## 当前文件的extern全局变量
        extern_vars_dict = self.get_all_extern_gloabal_vars()
        var_type_set = set([f"{var}@@@{type_v}" for var, (type_v, _) in extern_vars_dict.items()])
        if var_type_set:
            ## header中对应的声明和定义
            header_global_vars_dict = header_module.get_all_global_vars_init_and_declaration()
            header_var_type_set = set([f"{var}@@@{type_v}" for var, (type_v, _) in header_global_vars_dict.items()])
            intersection_var_type = header_var_type_set.intersection(var_type_set)
            if intersection_var_type:
                # return { var_type.split('@@@')[0] : header_global_vars_dict[var_type.split('@@@')[0]][1] for var_type in intersection_var_type}
                return True
        return False
    
    def get_all_preproc_def_ids_in_node(self, n:Node) -> list[str]:
        query = C_LANGUAGE.query(f"""
        ((identifier) @macro_def
        (#match? @macro_def "^[A-Z_]+$")
        )""")
        captures = query.captures(n)
        return [node.text.decode()
            for node in captures["macro_def"] if node]
    
    
    def get_all_extern_gloabal_vars(self):
        query = C_LANGUAGE.query(f"""
        (declaration
            (storage_class_specifier) @storage_class_specifier
            (#eq? @storage_class_specifier "extern")
            type:(_)
            declarator: (identifier) @identifier
        )""")
        captures = query.captures(self.root_node)
        return { node.text.decode() : (node.parent.child_by_field_name('type'), node.parent)
            for node in captures["identifier"]}
        
    def get_all_global_vars_init_and_declaration(self):
        query = C_LANGUAGE.query(f"""
        (declaration
            type:(_)
            declarator: (identifier)@decl
        )
        (declaration
            type:(_)
            (init_declarator) @init
        )""")
        temp_nodes = []
        captures = query.captures(self.root_node)
        for node in captures["decl"]:
            temp = node.parent
            tt = temp.child_by_field_name('storage_class_specifier')
            if tt and tt.text.decode() == 'extern':
                continue
            temp_nodes.append(temp)
        for node, capture in captures["init"]:
            temp_nodes.append
        q = C_LANGUAGE.query(f"""declarator: ((identifier) @id)""")
        res = {}
        for node in temp_nodes:
            for n in q.captures(node)["id"]:
                temp = n
                while(temp.type != 'declaration' and temp != self.root_node):
                    temp = temp.parent
                type_n = temp.child_by_field_name('type').text.decode()
                res[n.text.decode()] = type_n, temp
        return res
    
    def get_node_in_line(self, new_line_number:int):
        # if old_line_number not in self.clear_comments_line_map.keys():
        #     KeyError(f'源文件中{old_line_number}行可能为空！')
        # new_line = self.clear_comments_line_map[old_line_number]
        new_line_index = new_line_number - 1
        temp = self.root_node
        last_temp = temp
        last_flag = flag = False
        while(temp):
            # flag：标志这个for循环中，temp有没有往下深入一层
            flag = False
            for node in temp.named_children:
                start = node.start_point[0]
                end = node.end_point[0]
                if start <= new_line_index <= end:
                    flag = True
                    if start == end:
                        # 如果是以下几种情况，可能需要获得父节点
                        if node.parent.type in [
                            'preproc_def',
                            'preproc_function_def',
                            'call_expression',
                        ]:
                            return node.parent
                        return node
                    last_temp == temp
                    temp = node
                    break
            # 如果该行本来被被包括在一个node中
            # 但是这个node的named children中都没有
            # 说明不是这个node的named children，例如 };，);这种
            if last_flag and not flag:
                if temp.parent.type in [
                    'if_statement',
                    'while_statement',
                    'switch_statement'
                ]:
                    return temp.parent
                return temp
            # 如果一轮下来temp没有变化，那么就永远不会变化
            if last_temp == temp:
                break
            last_flag = flag
        return None
    
    # 可能得到变量和宏定义，这两者无法区分，
    # 也许可以用全大写来判别宏定义？
    # 如果是 info[1].hdr.id 或者 student1.age.a.a.a.a.a = 20;语句，也会直接获得 info 和 student1这两个id
    def get_vars_in_line(self, new_line_number:int):
        # 首先找到这一行所在的node
        target_node = self.get_node_in_line(new_line_number)
        if not target_node:
            return None
        if target_node.type == 'function_definition' and \
            target_node.end_point[0] + 1 == new_line_number:
            return []
        # 再在node中查询identifier
        query = C_LANGUAGE.query(f"""(identifier)@id""")
        res = []
        captures = query.captures(target_node)
        for node in captures["id"]:
            if node.parent.type in [
                'call_expression',
                'enumerator',
                'preproc_def',
                'preproc_function_def'
            ]:
                continue
            res.append(node.text.decode())
        return res
    
    # 在已知func_node之中找变量identifier的定义
    # 得到初始化或者声明
    # 指针类型仅加了一层指针在左侧
    # 如果类型不是一般数据类型，则去找该类型的定义
    # 注意，形如 a.b.c 或者 a->b.c 中的 b 和 c 并不是 identifier，而是 field_identifier 
    # 不应该在全局找，而是先找到上级变量的类型的定义，再去定义里面找
    def get_local_var_def(self, func_node:Node, identifier:str):
        # # 获取函数node
        # func_node = self.get_function_node(func_id)
        qs = []
        # 1. 仅声明
        qs.append(f"""
        (declaration
            declarator: (identifier) @decl_id
            (#eq? @decl_id "{identifier}")
        )""")
        ## 指针类型
        qs.append(f"""
        (declaration
            (pointer_declarator
                declarator: (identifier) @decl_pointer_id
                (#eq? @decl_pointer_id "{identifier}")
            )
        )""")
        # 2. 初始化变量
        qs.append(f"""
        (declaration
            (init_declarator
                declarator: (identifier) @decl_init_id
                (#eq? @decl_init_id "{identifier}")
            )
        )""")
        ## 指针类型
        qs.append(f"""
        (declaration
            (init_declarator
                (pointer_declarator
                    declarator: (identifier) @decl_init_pointer_id
                    (#eq? @decl_init_pointer_id "{identifier}")
                )
            )
        )""")
        # 3. 参数内变量
        qs.append(f"""
        (parameter_declaration
            declarator: (identifier) @param_id
            (#eq? @param_id "{identifier}")
        )""")
        # 指针类型
        qs.append(f"""
        (parameter_declaration
            (pointer_declarator
                declarator: (identifier) @param_pointer_id
                (#eq? @param_pointer_id "{identifier}")
            )
        )""")
        # 5. 特殊类型，如 数组 等以多个部分(且不并列)组成的
        qs.append(f"""
        (declaration
            (array_declarator
                declarator: (identifier) @decl_array_id
                (#eq? @decl_array_id "{identifier}")
            )
        )
        (declaration
            (init_declarator
                (array_declarator
                    declarator: (identifier) @decl_init_array_id
                    (#eq? @decl_init_array_id "{identifier}")
                )
            )
        )""")
        ## 指针类型
        qs.append(f"""
        (declaration
            (pointer_declarator
                (array_declarator
                    declarator: (identifier) @decl_pointer_array_id
                    (#eq? @decl_pointer_array_id "{identifier}")
                )
            )
        )
        (declaration
            (init_declarator
                (pointer_declarator
                    (array_declarator
                        declarator: (identifier) @decl_init_pointer_array_id
                        (#eq? @decl_init_pointer_array_id "{identifier}")
                    )
                )
            )
        )""")
        query = C_LANGUAGE.query('\n'.join(qs))
        captures = query.captures(func_node)
        # 如果当前func_node中没找到（通常func_node认为是函数）
        # 则在全局中找
        if not captures:
            captures = query.captures(self.root_node)
        res = []
        for capture_name, nodes in captures.items():
            for node in nodes:
                temp = node
                # 往上找父节点，目的是type是子节点
                for _ in range(len(capture_name.split('_')) - 1):
                    temp = temp.parent
                # node中第一次出现
                res.append(f'{temp.text.decode()}')
                # 如果不是常规类型，则需要查看type的具体定义
                var_type_node  = temp.child_by_field_name('type')
                type_type = var_type_node.type
                # typedef
                if type_type == 'type_identifier':
                    type_id = var_type_node.text.decode()
                    type_type = 'type_definition'
                # struct, enum, union之类的
                elif type_type in [
                    'struct_specifier',
                    'union_specifier',
                ]:
                    type_id = var_type_node.child_by_field_name('name').text.decode()
                elif type_type =='enum_specifier':
                    type_id = var_type_node.child_by_field_name('name')
                    if type_id:
                        type_id = type_id.text.decode()
                    else:
                        type_id = "anonymous_enum"
                else:
                    continue
                global_def_nodes = self.get_struct_def(type_id)
                if global_def_nodes:
                    res.extend([global_def_node.text.decode() 
                        for global_def_node in global_def_nodes 
                            if global_def_node])
                if res:
                    break
        if not res:
            preproc_defs:list[Node] = self.get_preproc_def(identifier)
            res = [f'{preproc_def.text.decode()}' for preproc_def in preproc_defs]
        if res:
            return '\n'.join(res)
        
        return None
        
    def get_var_init_and_declaration_nodes_from_node(self, node:Node, identifier:str):
        # 1. 仅声明
        # 2. 初始化变量
        # 3. 参数内变量
        # 4. 指针类型
        # 5. 特殊类型，如 数组 等以多个部分(且不并列)组成的
        query1 = C_LANGUAGE.query(f"""
        (declaration
            type:(_)
            declarator: (_) @declarator
        )
        (parameter_declaration
            type:(_)
            declarator: (_) @declarator
        )
        """)
        init_and_declaration_nodes = [node.parent for node in query1.captures(node)["declarator"]] 
        query2 = C_LANGUAGE.query(f"""
        declarator: (
            (identifier) @id
            (#eq? @id "{identifier}")
        )
        """)
        res_nodes = []
        for init_and_declaration_node in init_and_declaration_nodes:
            if "id" in query2.captures(init_and_declaration_node).keys():
                res_nodes.append(init_and_declaration_node)
        return res_nodes
    
    def get_local_var_def_new(self, func_node:Node, identifier:str):
        # # 获取函数node
        # func_node = self.get_function_node(func_id)
        
        # 获取当前node下identifier的所有变量声明和定义
        # 返回结构为list[完整node， id_node]
        var_init_and_declaration_nodes = self.get_var_init_and_declaration_nodes_from_node(func_node, identifier)
        # 如果当前func_node中没找到（通常func_node认为是函数）
        # 则在全局中找
        if not var_init_and_declaration_nodes:
            var_init_and_declaration_nodes = self.get_var_init_and_declaration_nodes_from_node(self.root_node, identifier)
        res = []
        for node in var_init_and_declaration_nodes:
            # node中第一次出现
            res.append(f'{node.text.decode()}')
            # 如果不是常规类型，则需要查看type的具体定义
            var_type_node  = node.child_by_field_name('type')
            type_type = var_type_node.type
            # typedef
            if type_type == 'type_identifier':
                type_id = var_type_node.text.decode()
                type_type = 'type_definition'
            # struct, enum, union之类的
            elif type_type in [
                'struct_specifier',
                'union_specifier',
                'enum_specifier',
            ]:
                type_id = var_type_node.child_by_field_name('name')
                if type_id:
                    type_id = type_id.text.decode()
                else:
                    type_id = f"anonymous_{type_type}"
            else:
                continue
            global_def_nodes = self.get_struct_def(type_id)
            if global_def_nodes:
                res.extend([global_def_node.text.decode()
                    for global_def_node in global_def_nodes 
                        if global_def_node])
            if res:
                break
        if not res:
            preproc_defs:list[Node] = self.get_preproc_def(identifier)
            res = [f'{preproc_def.text.decode()}' for preproc_def in preproc_defs]
        if res:
            return res
        return []

    # 通过数据类型名找数据类型定义
    def get_struct_def(self, type_identifier:str) -> list[Node]:
        query = C_LANGUAGE.query(f"""
        ( _
            name: (type_identifier) @type_identifier
            body: (field_declaration_list)
            (#eq? @type_identifier "{type_identifier}")
        )
        (type_definition
            type: ( _ )
            declarator: (type_identifier)@type_identifier
            (#eq? @type_identifier "{type_identifier}")
        )
        """)
        
        # body: (field_declaration_list)    
        res = []
        for node in query.captures(self.root_node)["type_identifier"]:
            temp = node.parent
            res.append(temp)
            if temp == "type_definition":
                type_node = temp.child_by_field_name('type')
                # 需要继续往下找下去
                # 形如 typedef a b;
                if type_node.type == 'type_identifier':
                    type_def_id = type_node.text.decode() 
                    res.extend(self.get_struct_def(type_def_id))
            return res
        # 没有搜到，则跨文件
        if self.is_path:
            Cross_file_res = self.dosomething_in_headers('get_struct_def', type_identifier)
            if Cross_file_res:
                return Cross_file_res
        return None
    
    def get_all_struct_nodes(self) -> list[Node]:
        query = C_LANGUAGE.query(f"""
        ( _
            name: (type_identifier) @type_identifier
            body: (field_declaration_list)
        )
        (type_definition
            type: ( _ )
            declarator: (type_identifier)@type_identifier
        )
        (enum_specifier
            body: (enumerator_list) @enumerator_list
        )
        """)
        captures = query.captures(self.root_node)
        res = []
        for _, nodes in captures.items():
            if nodes:
                for node in nodes:
                    res.append(node.parent)
        return res
    
    # 从数据结构找某个field_identifier的类型
    def get_field_type_in_struct(self, struct_type:str, field_identifier):
        struct_def_node = self.get_struct_def(struct_type)[-1]
        query = C_LANGUAGE.query(f"""
        (field_identifier) @field_name
        (#eq? @field_name "{field_identifier}")
        """)
        for node in query.captures(struct_def_node)["field_name"]:
            if node.text.decode() != field_identifier:
                continue
            temp = node
            while(temp.type != 'field_declaration'): 
                temp = temp.parent
            type_node = temp.child_by_field_name('type')
            return type_node.text.decode()
        return None

    def get_switch_lines(self, new_line_index:int):
        target_line = new_line_index - 1
        root_node = self.root_node
        temp = root_node
        start_line = 0
        end_line = len(self.code.splitlines()) - 1
        last_switch_node = None
        while temp.start_point[0] <= target_line:
            found_child = False
            for node in temp.named_children:
                start_line = node.start_point[0]
                end_line = node.end_point[0]
                if start_line <= target_line <= end_line:
                    if node.type == 'switch_statement':
                        last_switch_node = node
                    temp = node
                    found_child = True
                    break
            if not found_child:
                break
        if last_switch_node:
            start_line = last_switch_node.start_point[0]
            end_line = last_switch_node.end_point[0]
        return start_line, end_line

if __name__ == '__main__': 
    cm = Cmodule(
        input='/public/github_repos/github_repos_c/dentOS/packages/platforms/accton/x86-64/minipack/onlp/builds/x86_64_accton_minipack/module/src/thermali.c',
        # input='/public/github_repos/github_repos_c/u-boot/include/axp_pmic.h',
        # project_dir='/public/github_repos/github_repos_c/dentOS',
    )
    
    # print(cm.get_local_var_def(cm.get_function_node('onlp_thermali_init'),'linfo'))
    a = cm.get_struct_def('onlp_thermal_info_t')
    print(a[0].text.decode())
    
    # for n in cm.get_preproc_def('AXP_PMIC_MODE_REG'):
    #     print(n.text.decode())
    # for n in cm.get_enum_def('AXP313_ID'):
    #     print(n.text.decode())
        
    # header = '"platform_lib.h"'
    # res = cm.get_header_path(header)
    # print(res)
    # print(cm.check_header_used(header))
    
    # a = cm.get_function_node('_is_set')
    # if a:
    #     print(a.text.decode())
    #     print('------------------------------------------------------')
    # b = cm.get_local_var_def(a, 'info')
    # print(b)


    # line = 120
    # print(cm.original_code.splitlines()[line-1])
    # print(cm.code.splitlines()[cm.clear_comments_line_map[line]-1])

    # res = cm.get_struct_def('onlp_thermal_info_t')
    # for node in res:
    #     print(node.text.decode())

    # res:list[Node] = cm.get_preproc_def('__ONLPLIB_FILE_H__')
    # for node in res:
    #     print(node.text.decode())

    # old_start_line = 129
    # new_start_line = cm.clear_comments_line_map[old_start_line]
    # vars = cm.get_vars_in_line(new_start_line)
    # print(vars)
    # print('------------------------------------------------------')
    # vars_def = []
    # function_node = cm.get_function_include_line_index(new_start_line - 1)
    # # 定位行在函数中
    # if not function_node:
    #     # 定位行不在函数中，从全局中搜素
    #     function_node = cm.root_node
    # for var in vars:
    #     vars_def.append(cm.get_local_var_def(function_node,var))
    # for a in vars_def:
    #     if a:
    #         print(a)
    #         print('------------------------------------------------------')
        
