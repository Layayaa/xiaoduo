# 自动回复质量评估流水线

本项目对应题目“0109 · 自动回复质量评估流水线”。目标是把业务方模糊的“准确、有用、语气好、不能瞎编”转成一套可运行、可解释、可验证的自动评估方案。

## 0. 交付物对应关系

| 原题要求 | 本项目对应文件 |
| --- | --- |
| 定义至少 3 个可自动评估指标 | README 第 2 节 |
| 对 20 条自动回复逐条评分 | `outputs/case_scores.csv`、`outputs/evaluation_results.json` |
| 使用 human_ref 验证评估方法 | `outputs/validation_summary.json`、README 第 4 节 |
| 讨论局限性 | README 第 6 节 |
| 输出评估报告 | `outputs/evaluation_report.md`、`outputs/evaluation_report.html` |
| README | `README.md` |
| 开发工具截图 | `screenshots/dev_process.png` |
| 运行结果截图 | `screenshots/run_result.png` |
| 可交互查看 | `index.html`，辅助入口 |

## 1. 运行方式

Windows：

```bash
py -3 evaluate_replies.py --mode mock
```

macOS / Linux：

```bash
python3 evaluate_replies.py --mode mock
```

输入文件：

```text
task3_auto_replies.json   # 20 条用户问题 + 自动回复
task3_eval_criteria.md    # 业务方原始要求
task3_human_ref.json      # 人工参考回复和分析，仅用于验证
```

输出文件：

```text
outputs/evaluation_report.md
outputs/evaluation_report.html
outputs/evaluation_results.json
outputs/validation_summary.json
outputs/case_scores.csv
```

交互查看：

```text
index.html
```

`index.html` 是辅助工具，用来演示输入一条“用户问题 + 自动回复”后如何即时得到质检结果；正式评估结果仍以 `outputs/` 中的批量报告为准。

截图：

```text
screenshots/dev_process.png
screenshots/run_result.png
```

## 2. 指标定义

业务方原话是：回复要“准确、有用、语气好、不能瞎编”。我把它拆成 5 个可自动评估指标。

| 业务要求 | 指标 | 量化方式 | 选择理由 |
| --- | --- | --- | --- |
| 准确 | `problem_fit` 问题匹配度 | 判断用户问题属于物流、订单售后、商品参数、账号安全、投诉等哪类场景；检查回复是否覆盖该场景的关键动作 | 准确不是和人工参考答案长得像，而是有没有回应用户真实诉求 |
| 有用 | `resolution_helpfulness` 解决有用性 | 检查回复是否主动代办、追问订单号/账号/具体商品、给出明确下一步；对“自己去看/联系客服/耐心等待”扣分 | 客服回复的目标是推进解决，不是只解释规则 |
| 不能瞎编 | `context_awareness` 上下文核实意识 | 需要订单、物流、商品、账号等外部事实时，若没有追问或说明需核实则扣分；过度承诺扣分 | 自动回复缺少事实源时不能给确定结论 |
| 语气好 | `tone_empathy` 语气与安抚 | 投诉、等待、故障、账号安全等场景检查道歉、理解、安抚和服务姿态 | 客服场景中，情绪处理会直接影响用户体验 |
| 覆盖决策 | `automation_readiness` 自动化可放行度 | 综合质量和风险，输出 `pass` / `needs_review` / `fail` | 题目背景要求评估结果用于决定是否扩大自动回复覆盖范围 |

权重：

| 指标 | 权重 |
| --- | --- |
| `problem_fit` | 25% |
| `resolution_helpfulness` | 25% |
| `context_awareness` | 20% |
| `tone_empathy` | 15% |
| `automation_readiness` | 15% |

权重理由：客服自动回复首先要答对并解决问题，所以“准确”和“有用”权重最高；“不能瞎编”是上线红线；语气重要但不能替代解决问题；自动化可放行度直接服务业务决策。

## 3. 评估方法

### 3.1 独立评分

评分阶段只使用：

```text
user_question
auto_reply
eval_criteria
```

不使用 `human_ref.json`。这是关键边界：人工参考不能进入评分公式，否则会变成“参考答案相似度”，不是真正可自动运行的评估器。

评分逻辑是离线 mock judge：

1. 识别用户问题场景：物流、订单售后、账号安全、商品参数、投诉反馈等。
2. 判断自动回复是否覆盖该场景需要的动作。
3. 检查是否主动代办或追问必要信息。
4. 检查是否把责任推给用户，例如让用户自己查详情页、订单页、物流页、再联系客服。
5. 检查是否存在过度承诺或安全风险。
6. 输出 5 个指标分、总分、放行决策和问题标签。

### 3.2 human_ref 的使用方式

`human_ref.json` 只用于评分后的验证。

验证方式：

1. 从人工标注中抽取问题类型，例如“泛泛回复”“缺少查询/核实”“把责任推给用户”“缺少必要追问”“安抚不足”。
2. 对比自动评估识别的问题类型和人工问题类型是否一致。
3. 输出 case 级命中率、问题类型召回率和不一致 case。

这样可以验证评估方法是否接近人工判断，同时避免把答案泄漏进评分器。

## 4. 本次评估结果

本次对 20 条自动回复的评估结果：

| 项目 | 结果 |
| --- | --- |
| 样本数 | 20 |
| 整体平均分 | 59.0 / 100 |
| 最低 / 最高分 | 35 / 77 |
| 放行决策 | `fail`: 15，`needs_review`: 5，`pass`: 0 |
| 最差 3 条 | `case_03`、`case_09`、`case_18` |
| 自动评估与人工标注 case 级命中率 | 0.65 |
| 人工问题类型召回率 | 0.444 |

结论：当前自动回复整体不适合直接扩大覆盖。主要问题不是明显“瞎编”，而是大量回复停留在通用说明和自助引导，没有主动查询、追问或代办。涉及退款、退货、物流、故障和投诉的场景应保留人工兜底。

完整报告：

```text
outputs/evaluation_report.md
outputs/evaluation_report.html
```

结构化结果：

```text
outputs/evaluation_results.json
outputs/validation_summary.json
outputs/case_scores.csv
```

## 5. 最差 case 摘要

| case | 问题 | 自动评估结论 |
| --- | --- | --- |
| `case_03` | 退款什么时候能到账 | 用户问的是具体退款状态，自动回复给了通用到账时间，并让用户自己查订单详情，缺少订单核实 |
| `case_09` | 退货邮费谁出 | 回复规则本身有价值，但没有追问退货原因，无法给出针对性判断 |
| `case_18` | 扫地机器人用了两周不工作 | 属于售后故障场景，回复要求用户按地址寄回，没有先确认用户倾向和订单状态，自动放行风险高 |

## 6. 局限性与改进

局限性不是抽象问题，validation 里已经暴露出一些具体误判：

| case | 自动评估结果 | 人工标注问题 | 为什么评不准 |
| --- | --- | --- | --- |
| `case_12` 快递两天没更新 | `overall=61`，识别为 `push_to_user` | 人工认为是 `generic_answer`、`missing_clarification`、`no_lookup` | 自动评估抓到了“让用户自己联系/等待”的问题，但没有充分识别“物流两天没更新”本质上需要订单号和物流查询。原因是规则只看到了“物流/快递”等关键词被覆盖，误以为上下文核实意识足够。 |
| `case_13` 敏感肌要面膜成分表 | `overall=67`，未识别明显问题 | 人工认为是 `missing_clarification`、`no_lookup`、`push_to_user` | 自动评估看到回复提到了“成分表、过敏、小样测试”，认为命中了商品参数场景；但人工判断的关键是“用户皮肤敏感，需要客服主动查成分并个性化确认”，不是让用户自己看详情页。规则缺少对“敏感/过敏”等高关注词的权重。 |
| `case_04` 新买耳机左耳没声音 | `overall=67`，识别为 `push_to_user` | 人工还认为存在 `no_lookup` | 自动评估能发现排查步骤增加用户负担，但没有充分惩罚“才买三天”这个强售后信号。真实客服应优先查订单并给退换方案，而不是先让用户排查。 |
| `case_20` 退货流程太复杂 | `overall=64`，识别到 `missing_clarification` | 人工还认为 `weak_empathy` | 自动评估最终把它判为 fail，但语气分仍偏高，因为回复开头有“抱歉”。人工标注指出用户已经明确表达挫败，重复流程本身就是体验问题，不能只靠道歉词判断语气好。 |

这些误判说明：

- 当前 mock judge 对显式关键词敏感，但对“用户真实意图”理解不足。例如“快递没更新”不是问物流常识，而是要客服查状态。
- 规则会把“提到了相关词”误判为“解决了问题”。例如 case_13 提到成分表，但没有主动给成分。
- 语气评分容易被道歉词骗过。case_20 有道歉，但后续仍重复用户已经看不懂的流程。
- 没有接入订单、商品、物流、账号等真实系统，所以无法验证回复是否真的查到了事实。
- `human_ref.json` 没有数值评分，因此 validation 只能做问题类型一致性，不能做严格相关系数。

改进方向：

- 引入 LLM-as-judge，按同一 rubric 输出 JSON 分数和理由。
- 增加多评委或重复采样，降低 judge 波动。
- 增加人工数值标注，计算 Pearson / Spearman 相关系数。
- 接入业务事实源，验证商品参数、订单状态、物流状态和退款状态。
- 对账号安全、退款金额、售后承诺、敏感信息建立红线规则。
- 针对验证暴露的误判补充规则：物流异常必须追问订单号；敏感肌/过敏场景必须主动查成分；售后强信号如“才买三天/用了两周就坏”应优先给退换方案；语气评分不能只看道歉词，还要看后续是否真正降低用户负担。

## 7. AI 工具使用情况

使用 Codex 辅助完成：

- 审题和指标拆解
- Python 评估脚本
- validation 逻辑
- Markdown / HTML / JSON / CSV 报告生成
- 交互式 `index.html` 辅助查看工具

默认评分模式为本地 mock，不调用外部 API。`human_ref.json` 仅用于评分后的验证，不参与自动评分。
