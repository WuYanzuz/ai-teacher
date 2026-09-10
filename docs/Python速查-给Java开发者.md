# Python 速查 · 给 Java 开发者

> 只讲这个项目里真实出现的语法。例子全部来自本项目源码，可以对着文件看。

---

## 0. 五个心智差异（先看这个）

| | Java | Python |
|---|---|---|
| **代码块** | `{ }` 大括号 | **缩进**（4 个空格），缩进错了就是语法错误 |
| **语句结束** | 分号 `;` | 换行 |
| **类型** | 编译期强制 | 类型标注只是**注释**，运行时不检查 |
| **null** | `null` | `None` |
| **this** | 隐式 | **必须显式写 `self`**，而且是方法的第一个参数 |

第三条最容易踩：

```python
def foo(x: int) -> str:
    return x        # 返回了 int，但类型标注写的 str —— 运行时完全不报错
```

类型标注是给 IDE 和人看的，Python 自己不管。想要检查得装 mypy。

---

## 1. 语法对照表

### 变量和常量

```java
// Java
final String name = "小明";
int count = 0;
List<String> items = new ArrayList<>();
Map<String, Integer> scores = new HashMap<>();
```

```python
# Python
name = "小明"           # 没有 final，全大写是"约定俗成的常量"
count = 0
items = []              # list
scores = {}             # dict
```

### 判断和循环

```java
// Java
if (user.getRole().equals("teacher")) {
    ...
} else if (x > 0) {
    ...
} else {
    ...
}

for (int i = 0; i < 10; i++) { ... }
for (String s : items) { ... }
while (flag) { ... }
```

```python
# Python
if user.role == "teacher":      # 字符串直接用 ==，不用 equals
    ...
elif x > 0:                      # else if 写成 elif
    ...
else:
    ...

for i in range(10): ...          # 0..9
for s in items: ...
while flag: ...
```

**注意**：Python 的 `==` 比较值（相当于 Java 的 `equals`），`is` 才比较引用（相当于 Java 的 `==`）。判空统一用 `is None`。

### 真假判断

Python 里这些都算 false：`None`、`0`、`""`、`[]`、`{}`、`False`

所以项目里大量出现这种写法：

```python
if not text:              # text 是 None 或空串都进这个分支
    return
if not items:             # 列表为空
    return
```

相当于 Java 的 `if (text == null || text.isEmpty())`，但 Python 一个 `not` 就够了。

### 异常

```java
// Java
try {
    doSomething();
} catch (IOException e) {
    log.error("failed", e);
} finally {
    cleanup();
}

throw new IllegalArgumentException("bad input");
```

```python
# Python
try:
    do_something()
except IOException as e:          # catch 写成 except，变量用 as
    log.exception("failed")        # exception() 自动带堆栈
finally:
    cleanup()

raise ValueError("bad input")      # throw 写成 raise
```

项目里常见的「忽略异常」写法：

```python
try:
    db.execute_sql("ALTER TABLE ...")
except Exception:
    pass          # pass = 空语句，相当于 Java 的 { }
```

### 字符串

```java
// Java
String s = "作业 " + id + " 已处理";
String t = String.format("耗时 %.1f 秒", cost);
```

```python
# Python —— f-string，前面加个 f，大括号里直接写表达式
s = f"作业 {id} 已处理"
t = f"耗时 {cost:.1f} 秒"          # 格式化写在冒号后面

# 多行字符串
sql = """
SELECT * FROM homework
WHERE id = 1
"""
```

f-string 是这个项目最常见的字符串写法，看到 `f"..."` 就是它。

---

## 2. 函数

```java
// Java
public String grade(List<Path> images, String transcript) { ... }

// 重载
public String grade(List<Path> images) { return grade(images, null); }
```

```python
# Python —— 没有重载，用默认值代替
def grade(images: list[Path], transcript: str = None) -> str:
    ...

grade(imgs)                          # transcript 用默认值 None
grade(imgs, "小鸟飞来飞去")            # 按位置传
grade(imgs, transcript="小鸟飞来")     # 按名字传（推荐，可读性好）
```

### `*` 强制关键字参数

项目里到处是这个写法：

```python
def send_homework_feedback(
    self,
    *,                              # ← 这个星号是分界线
    child_name: str,
    media_type: str,
    feedback: str,
) -> None:
```

`*` 后面的参数**必须写参数名**：

```python
notifier.send_homework_feedback(child_name="小明", media_type="image", feedback="...")  # ✅
notifier.send_homework_feedback("小明", "image", "...")                                  # ❌ TypeError
```

好处是调用处一眼看得出每个值是什么，参数多的时候不容易传错位置。Java 没有对应语法。

### `*args` 和 `**kwargs`

```python
def wrapper(*args, **kwargs):
    return fn(*args, **kwargs)
```

- `*args` = 把所有位置参数收成一个元组，≈ Java 的 `Object... args`
- `**kwargs` = 把所有关键字参数收成一个字典，Java 没有

见于 `ai_teacher/utils/retry.py`，作用是「原样转发所有参数」。

---

## 3. 类

```java
// Java
public class QwenVLClient {
    private String model;

    public QwenVLClient(String model) {
        this.model = model;
    }

    public String grade(List<Path> images) {
        return this.model + "...";
    }
}

QwenVLClient c = new QwenVLClient("qwen-vl-plus");
```

```python
# Python
class QwenVLClient:
    def __init__(self, model: str):      # 构造函数固定叫 __init__
        self.model = model                # 字段不用提前声明，赋值即创建

    def grade(self, images: list[Path]) -> str:    # self 必须显式写
        return self.model + "..."

c = QwenVLClient("qwen-vl-plus")          # 不用 new
```

三个要点：
1. 构造函数固定叫 `__init__`
2. **每个实例方法第一个参数必须是 `self`**，调用时不用传（`c.grade(imgs)` 而不是 `c.grade(c, imgs)`）
3. 没有 `private`，前面加下划线 `_foo` 只是「约定为内部使用」，语法上照样能访问

项目里 `_` 开头的函数/变量都是内部用的，比如 `_gen_code()`、`_build_media_url()`。

---

## 4. 装饰器（≈ Java 注解，但强大得多）

看着像注解，本质是**函数包装函数**。

### 用法 1：注册路由（≈ `@PostMapping`）

```python
@router.post("/{hw_id}/ack", response_model=HomeworkOut)
def ack(hw_id: int, user: User = Depends(current_user)):
    ...
```

### 用法 2：加行为（≈ Spring AOP）

```python
@with_retry(max_attempts=3, backoff=2.0)
def grade_images(self, image_paths, prompt):
    ...
```

`grade_images` 失败会自动重试 3 次，指数退避。

**和 Java 注解的本质区别**：Java 注解只是元数据，得靠框架反射去解释。Python 装饰器是**真的把函数替换掉了**：

```python
@with_retry(max_attempts=3)
def foo(): ...

# 完全等价于：
def foo(): ...
foo = with_retry(max_attempts=3)(foo)      # foo 被替换成了包装后的新函数
```

所以装饰器不需要框架支持，纯语言特性。实现见 `ai_teacher/utils/retry.py`。

---

## 5. with 语句（≈ try-with-resources）

```java
// Java
try (InputStream in = Files.newInputStream(path)) {
    read(in);
}   // 自动 close
```

```python
# Python
with path.open("rb") as f:
    data = f.read()
# 自动 close，异常时也会关
```

项目里：

```python
with img_path.open("rb") as f:
    r = requests.post(url, files={"file": f})
```

---

## 6. 列表推导式（这个 Java 没有，但很常见）

```java
// Java Stream
List<ClassOut> result = classes.stream()
    .map(c -> toOut(c, user))
    .collect(Collectors.toList());
```

```python
# Python 列表推导式，一行搞定
result = [_to_out(c, user) for c in classes]
```

带过滤：

```java
// Java
List<Homework> done = all.stream()
    .filter(h -> h.getFeedback() != null)
    .collect(Collectors.toList());
```

```python
# Python
done = [h for h in all if h.feedback is not None]
```

读法：**从中间的 `for` 开始读** —— 「对 all 里的每个 h，如果 h.feedback 不是 None，就把 h 放进结果」。

项目里的真实例子（`backend/routes/classes.py`）：

```python
cs = [m.classroom for m in my_memberships]
```

还有字典推导：

```python
headers = {k: v for k, v in items if v}
```

---

## 7. dict 和 list（≈ Map 和 List）

```python
# dict ≈ HashMap
d = {"name": "小明", "age": 6}
d["name"]                    # 取值，key 不存在会抛 KeyError
d.get("name")                # 取值，key 不存在返回 None（推荐）
d.get("name", "默认值")       # 带默认值
d["email"] = "x@y.com"       # 赋值即新增
"name" in d                  # 判断 key 存在，≈ containsKey

for k, v in d.items():       # 遍历，≈ entrySet()
    print(k, v)
```

```python
# list ≈ ArrayList
lst = [1, 2, 3]
lst.append(4)                # ≈ add()
lst[0]                       # 第一个
lst[-1]                      # 最后一个（负数从后往前，Java 没有）
lst[1:3]                     # 切片，取索引 1、2（≈ subList(1,3)）
len(lst)                     # ≈ size()
```

项目里高频用法：

```python
result.get("error")                    # 安全取值，见 ai_pipeline.py
cfg.get("temperature", 0.4)            # 带默认值，见各个 client
"\n".join(parts)                       # 拼接列表为字符串，见 grader.py
```

---

## 8. 模块和导入（≈ package 和 import）

文件路径就是包路径，一个 `.py` 文件就是一个模块。

```python
from ai_teacher.utils.config import get_settings    # 导入具体函数
from ai_teacher.storage import db as storage_db     # 导入模块并起别名
from .models import User                            # . = 当前包（相对导入）
from ..utils.logger import get_logger               # .. = 上一级包
import requests                                     # 导入整个第三方库
```

对照：
```java
import com.example.utils.Config;         // ≈ from ... import ...
import static com.example.Utils.getSettings;
```

`__init__.py` 是包的标记文件，相当于告诉 Python「这个目录是个包」。项目里大多是空的或只有一行注释。

**函数内 import**：项目里有些 import 写在函数里面，比如

```python
def looks_like_homework(self, image_path):
    from .vision_router import get_vision_client     # 在函数里 import
    return get_vision_client().is_homework_image(image_path)
```

这是为了**避免循环导入**（A 导入 B，B 又导入 A）。Java 没这问题，Python 有。

---

## 9. async / await

```python
@router.post("/wx_login")
async def wx_login(req: WxLoginReq):      # async 修饰的是协程函数
    ...
```

概念上接近 Java 的 `CompletableFuture`，但语法上顺序得多。

**这个项目里你基本不用关心**：绝大多数接口都是普通 `def`，FastAPI 会自动把它们丢到线程池跑。只有 `backend/routes/auth.py` 里的 `current_user` 用了 `async def`。

规则很简单：
- 函数标了 `async`，调用时要 `await`
- 没标就正常调

小程序前端的 JS 也有 async/await，语义一样。

---

## 10. FastAPI ↔ Spring Boot 全表对照

| Spring Boot | FastAPI | 本项目位置 |
|---|---|---|
| `@SpringBootApplication` | `app = FastAPI()` | `backend/main.py` |
| `@RestController` | `router = APIRouter()` | 各 `routes/*.py` |
| `@RequestMapping("/api/x")` | `APIRouter(prefix="/api/x")` | 同上 |
| `@GetMapping` / `@PostMapping` | `@router.get` / `@router.post` | |
| `@PathVariable Long id` | `id: int`（名字对上路径占位符） | |
| `@RequestBody Dto d` | `d: Dto`（Dto 继承 BaseModel） | |
| `@RequestParam String q` | `q: str = ""`（函数参数带默认值） | |
| `@RequestPart MultipartFile` | `file: UploadFile = File(...)` | `homework.py` |
| DTO + Bean Validation | `class Xxx(BaseModel)` | 各 routes 顶部 |
| `@Autowired` / 构造注入 | `= Depends(xxx)` | `Depends(current_user)` |
| `@AuthenticationPrincipal` | `user: User = Depends(current_user)` | `backend/auth.py` |
| `throw new ResponseStatusException` | `raise HTTPException(404, "...")` | |
| `@Async` | `BackgroundTasks.add_task()` | `homework.py` |
| `@Value("${x}")` | `os.getenv("X")` | `backend/config.py` |
| `application.yml` | `config.yaml` + `.env` | |
| Swagger 注解 | 自动生成，直接看 `/docs` | |
| `@Entity` | `class X(Model)` (peewee) | `backend/models.py` |
| Repository | 模型类上的静态方法 | `Homework.select()...` |

**依赖注入的差异**：Spring 靠容器扫描注册 Bean，FastAPI 的 `Depends(f)` 就是「调用请求前先执行函数 f，把返回值传进来」，没有容器，更直白也更弱。

---

## 11. Java 开发者常踩的坑

### 缩进就是语法

```python
if x:
    do_a()
    do_b()      # 在 if 里面
do_c()          # 在 if 外面
```

少一层缩进语义就变了，编辑器一定要设成「4 空格，禁用 Tab」。

### 可变默认参数

```python
def f(items=[]):        # ❌ 坑！默认值只创建一次，所有调用共享同一个 list
    items.append(1)
    return items

f()   # [1]
f()   # [1, 1]  ← 上次的还在！

def f(items=None):      # ✅ 正确写法
    if items is None:
        items = []
```

### 赋值是引用，不是拷贝

```python
a = [1, 2, 3]
b = a           # b 和 a 指向同一个 list
b.append(4)
print(a)        # [1, 2, 3, 4]  ← a 也变了

b = a.copy()    # 要拷贝得显式写
```

跟 Java 对象引用一样，但因为没有 `new`，容易忘。

### 整数除法

```python
7 / 2       # 3.5   ← 结果是浮点数
7 // 2      # 3     ← 整除要用双斜杠
```

Java 里 `7/2` 是 3，Python 里是 3.5，这个差异会造成静默的 bug。

### 没有 switch

用 `if/elif` 或字典：

```python
# 项目里的写法（backend/routes/homework.py）
def _media_kind(suffix: str) -> str:
    s = suffix.lower()
    if s in (".jpg", ".jpeg", ".png"):
        return "image"
    if s in (".mp4", ".mov"):
        return "video"
    return "file"

# 或者用字典（notifier.py）
return {"image": "📷", "voice": "🎤", "video": "🎬"}.get(t, "📄")
```

### 字符串不可变

跟 Java 的 String 一样，`s.replace(...)` 返回新串，不改原串。

---

## 12. 常用命令

```powershell
# 装依赖（≈ mvn install）
pip install -r requirements.txt

# 装单个包（≈ 加一条 dependency）
pip install requests

# 看装了什么
pip list

# 跑脚本
python scripts\demo_pipeline.py test\x.jpg

# 跑一行代码（调试神器）
python -c "print(1+1)"

# 起服务（≈ mvn spring-boot:run）
python -m uvicorn backend.main:app --reload

# 跑测试（≈ mvn test）
python -m pytest ai_teacher/tests/ -v
```

**关于虚拟环境**：Python 没有 Maven 那样的项目级依赖隔离，默认所有包装在全局。规范做法是用虚拟环境（`python -m venv .venv`），相当于给每个项目一个独立的 `~/.m2`。这个项目目前是直接装全局的，能跑，但换机器时容易出版本冲突。

---

## 13. 看代码时的速查

遇到看不懂的符号，对照这个：

| 符号 | 含义 |
|---|---|
| `def f():` | 定义函数 |
| `class A:` | 定义类 |
| `self` | this |
| `None` | null |
| `True` / `False` | true / false（首字母大写） |
| `and` / `or` / `not` | `&&` / `\|\|` / `!` |
| `elif` | else if |
| `pass` | 空语句 `{}` |
| `raise` | throw |
| `except` | catch |
| `f"{x}"` | 字符串模板 |
| `@foo` | 装饰器 |
| `*` (参数列表里) | 后面的参数必须写名字 |
| `*args` | 可变位置参数 |
| `**kwargs` | 可变关键字参数 |
| `_foo` | 约定为内部使用（无强制） |
| `__init__` | 构造函数 |
| `x if c else y` | 三元运算符 `c ? x : y` |
| `a[1:3]` | 切片，取索引 1、2 |
| `a[-1]` | 最后一个元素 |
| `str \| None` | 类型可以是 str 或 None（≈ `@Nullable String`） |
| `-> str` | 返回值类型标注 |
| `# ...` | 单行注释 |
| `"""..."""` | 文档注释（≈ Javadoc） |
