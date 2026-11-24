# 综合高中项目作答的共同与分向评价

业务交接资料为 UTF-8 JSON，每个文件保存一组记录。全部人名、机构、材料与项目均为虚构。
编号在各自资料中使用。保留原文中的省略、转述、标点和异体字，空字段表示交接中没有填值。

## 交接资料

- `data/briefs.json` 保存id、阶段、版本、原文。作业原题和指导书，阶段及版本均由校方登记。

- `data/answers.json` 保存id、学生、分段、序次、日期、引自、文字。去标识的学生作答。引自字段为提交者声明，不代替教师查证。作业序次按同一学生和分段保存。

- `data/rubrics.json` 保存id、要求、版次、层级、原文。共同评价与方向补充规准的教研文本。版次在对应要求内递增。

- `data/marking.json` 保存id、学生、教师、对象、规准、时间、动作、原文。教师原批语、教研组签定和已给学生的回执。意见记录只对应列出的作答和规准版次。

- `data/students.json` 保存id、方向、阶段。校方给学生对应阶段采用的方向。

## 阅读与运行

使用 Python 3.11.2 和标准库。在仓库根目录查看资料目录和一条原始记录。测试检查原文读入及资料关系。

```text
python3 -m corpus
python3 -m corpus answers --id A2
python3 -m unittest discover -s tests -v
```

## 评价整理包 `assessment`

在不改写原始资料的前提下，把分段作答、图表转写、共同/方向规准、教师批语与补交说明
整理成可回查的判断。所有归类只依据显式信号（引自链、算式、校方登记的小组/个人标记），
每条结论带规则编号；来源、归因或支撑程度有歧义一律转教师审原文，不按文风判分。

| 模块 | 对应业务约定 |
| --- | --- |
| `conventions.py` | 校方约定的资料类别、教师分工、观测修订关系、规准澄清性质 |
| `repository.py` | 只读装载、引自来源链、观测表点数抽取（含“修订为 N 个”句式） |
| `fragments.py` | 句子切分与归类：抄题转述/图表转写/计算/方法推理/已实施观察/意图/小组归属/待审 |
| `scoring.py` | 算值与来源表核对、首错只计一次、跟随错误须有可查沿用关系 |
| `evidence.py` | 片段对各规准的支撑（同一片段可证明 R3 但不能证明 R1），待审队列 |
| `judgments.py` | 签定权限与顺序：共同线两教师独立意见、分歧交教研组、方向线负责教师签定 |
| `rubrics.py` | 规准版次澄清登记，区分表述变化与判准变化，扫描已发回结果的复核影响 |
| `resubmission.py` | 补交处理：输入未变则前段签定冻结；观测重订后由后续材料与规准决定 |
| `feedback.py` | 共同反馈＋本方向反馈：已证明能力、可在原推理上继续做什么、待补证据 |
| `stage.py` | 阶段汇入门槛（共同要求全部处理才汇入）与两方向对比视图 |

命令行（缺省学生编号时处理全部学生）：

```text
python3 -m assessment fragments S1   # 分段句子归类与待审原因
python3 -m assessment evidence S1    # 片段—规准支撑与教师待审队列
python3 -m assessment scoring        # 算值核对、首错与跟随错误
python3 -m assessment judgments      # 各要求签定状态与权限提示
python3 -m assessment resubmit       # 补交分段与观测修订处理
python3 -m assessment rubric         # 规准澄清登记与已发回结果复核影响
python3 -m assessment feedback S1    # 发给学生的共同＋方向反馈
python3 -m assessment stage          # 阶段汇入门槛与方向附加待定
python3 -m assessment compare        # 同一份作业两个方向的判断对比
```

处理仓库外不可信资料时，用独立脚本把资料目录作为参数传入，并以隔离模式运行，
避免资料目录里的同名模块被导入：

```text
python3 -I /path/to/run_isolated.py   # 脚本内 Repository("/外部资料目录")
```

