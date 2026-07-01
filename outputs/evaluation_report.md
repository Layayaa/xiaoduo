# 客服自动回复质量评估报告

## 1. 方法边界

- 评分阶段只使用 `user_question` 和 `auto_reply`，不读取人工参考答案。

- `human_ref.json` 只在评分完成后用于 validation，检查自动评估发现的问题是否接近人工标注。

- 默认模式是离线 mock judge，适合复现；线上可替换为 LLM-as-judge，但仍应保持同样的数据隔离。

## 2. 整体结论

- 样本数：20 条

- 整体平均分：59.0 / 100

- 最低/最高分：35 / 77

- 放行决策分布：{"fail": 15, "needs_review": 5}

- 判断：当前自动回复可覆盖部分规则清晰的低风险问题，但凡涉及订单、物流、商品参数、投诉情绪和账号安全，都应保留人工兜底或强制追问。

## 3. 指标分布

| metric | avg | min | max | distribution |
| --- | --- | --- | --- | --- |
| problem_fit | 65.0 | 40 | 80 | <65 人工兜底: 10, 80-100 可自动放行: 10 |
| resolution_helpfulness | 43.0 | 20 | 80 | <65 人工兜底: 18, 80-100 可自动放行: 2 |
| context_awareness | 74.0 | 40 | 80 | 80-100 可自动放行: 16, <65 人工兜底: 4 |
| tone_empathy | 59.0 | 40 | 80 | <65 人工兜底: 16, 80-100 可自动放行: 4 |
| automation_readiness | 56.0 | 20 | 80 | <65 人工兜底: 16, 80-100 可自动放行: 4 |
| overall | 59.0 | 35 | 77 | <65 人工兜底: 15, 65-79 需抽检优化: 5 |

## 4. 逐条评分

| case_id | overall | decision | problem_fit | resolution_helpfulness | context_awareness | tone_empathy | automation_readiness | auto_issue_types |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| case_01 | 51 | fail | 40 | 40 | 80 | 60 | 40 | generic_answer、missing_clarification、no_lookup、push_to_user |
| case_02 | 56 | fail | 60 | 40 | 80 | 40 | 60 | generic_answer、push_to_user |
| case_03 | 35 | fail | 40 | 20 | 40 | 40 | 40 | generic_answer、missing_clarification、no_lookup、push_to_user |
| case_04 | 67 | needs_review | 80 | 40 | 80 | 80 | 60 | push_to_user |
| case_05 | 51 | fail | 40 | 60 | 40 | 80 | 40 | missing_clarification、no_lookup |
| case_06 | 55 | fail | 60 | 40 | 60 | 60 | 60 | generic_answer、push_to_user |
| case_07 | 69 | needs_review | 60 | 80 | 80 | 40 | 80 | generic_answer、weak_empathy |
| case_08 | 64 | fail | 80 | 40 | 80 | 60 | 60 | push_to_user |
| case_09 | 43 | fail | 40 | 20 | 80 | 40 | 40 | generic_answer、missing_clarification、no_lookup、push_to_user |
| case_10 | 72 | needs_review | 80 | 60 | 80 | 60 | 80 | none |
| case_11 | 64 | fail | 80 | 40 | 80 | 60 | 60 | push_to_user |
| case_12 | 61 | fail | 80 | 40 | 80 | 40 | 60 | push_to_user |
| case_13 | 67 | needs_review | 80 | 40 | 80 | 60 | 80 | none |
| case_14 | 63 | fail | 80 | 40 | 60 | 80 | 60 | none |
| case_15 | 61 | fail | 80 | 40 | 80 | 60 | 40 | missing_clarification |
| case_16 | 64 | fail | 80 | 40 | 80 | 60 | 60 | push_to_user |
| case_17 | 77 | needs_review | 80 | 80 | 80 | 60 | 80 | none |
| case_18 | 43 | fail | 40 | 20 | 80 | 60 | 20 | missing_clarification、no_lookup、push_to_user |
| case_19 | 54 | fail | 60 | 20 | 80 | 60 | 60 | generic_answer、missing_clarification、no_lookup |
| case_20 | 64 | fail | 60 | 60 | 80 | 80 | 40 | missing_clarification、no_lookup、push_to_user |

## 5. 最差 3 条 case

### case_03 | overall=35 | fail

- 用户问题：退款什么时候能到账
- 自动回复：退款到账时间取决于退款方式和银行处理速度。一般情况下：原路退回（支付宝/微信）1-3个工作日，银行卡退款3-7个工作日，信用卡退款5-15个工作日。您可以在订单详情页查看退款进度。如果超时未到账，请联系客服。
- 自动评估原因：需要核实的信息未覆盖：需要订单/售后状态核实；回复偏自助说明，把操作负担留给用户；回复偏通用解释，缺少针对当前 case 的判断
- 自动识别问题：generic_answer、missing_clarification、no_lookup、push_to_user
- 人工标注问题类型（仅验证用）：generic_answer、missing_clarification、no_lookup
- 人工分析（仅验证用）：用户问的是'我的退款'，是个具体问题，需要查具体订单。自动回复给了通用说明但没有帮用户查实际状态。人工回复会先查订单再给具体信息。自动回复的通用信息本身是准确的。

### case_09 | overall=43 | fail

- 用户问题：退货邮费谁出
- 自动回复：退货运费承担规则如下：质量问题导致的退货，运费由商家承担；非质量问题（如不喜欢、买错了等）的退货，运费由买家承担。具体判定标准请参考我们的退换货政策。如有疑问请联系客服。
- 自动评估原因：需要核实的信息未覆盖：需要订单/售后状态核实；回复偏自助说明，把操作负担留给用户；回复偏通用解释，缺少针对当前 case 的判断
- 自动识别问题：generic_answer、missing_clarification、no_lookup、push_to_user
- 人工标注问题类型（仅验证用）：generic_answer、missing_clarification
- 人工分析（仅验证用）：自动回复的规则说明是正确的，但没有追问用户的具体情况来给针对性回答。人工回复会在给出规则后追问具体场景。不过作为自动回复，给出规则本身也有价值。

### case_18 | overall=43 | fail

- 用户问题：那个扫地机器人用了两周就不工作了
- 自动回复：抱歉给您带来不便。扫地机器人使用两周就出现故障，属于质量问题。您的订单在30天质保期内，可以选择退货退款或者换新。请按照退货地址寄回商品，退货运费由我们承担。如有其他问题请联系客服。
- 自动评估原因：需要核实的信息未覆盖：需要投诉安抚和人工兜底；回复偏自助说明，把操作负担留给用户
- 自动识别问题：missing_clarification、no_lookup、push_to_user
- 人工标注问题类型（仅验证用）：missing_clarification
- 人工分析（仅验证用）：自动回复基本正确，给出了质保期信息和解决方案。但人工回复会先追问用户倾向哪种方案再操作，自动回复没有做这一步确认。整体来说自动回复质量尚可。

## 6. 使用 human_ref 的验证结果

- case 级命中率：0.65（自动评估识别到至少一个人工问题类型的比例）

- 人工问题类型召回率：0.444

- 自动最低 5 条与人工负面 case 重合：case_01, case_03, case_05, case_09, case_18

| case_id | overall | auto issues | human issues | matched | missed |
| --- | --- | --- | --- | --- | --- |
| case_01 | 51 | generic_answer、missing_clarification、no_lookup、push_to_user | missing_clarification、push_to_user | missing_clarification、push_to_user | none |
| case_02 | 56 | generic_answer、push_to_user | generic_answer、no_lookup、push_to_user | generic_answer、push_to_user | no_lookup |
| case_03 | 35 | generic_answer、missing_clarification、no_lookup、push_to_user | generic_answer、missing_clarification、no_lookup | generic_answer、missing_clarification、no_lookup | none |
| case_04 | 67 | push_to_user | no_lookup、push_to_user | push_to_user | no_lookup |
| case_05 | 51 | missing_clarification、no_lookup | missing_clarification、push_to_user、weak_empathy | missing_clarification | push_to_user、weak_empathy |
| case_06 | 55 | generic_answer、push_to_user | generic_answer、missing_clarification、no_lookup | generic_answer | missing_clarification、no_lookup |
| case_07 | 69 | generic_answer、weak_empathy | missing_clarification、no_lookup、push_to_user、weak_empathy | weak_empathy | missing_clarification、no_lookup、push_to_user |
| case_08 | 64 | push_to_user | push_to_user | push_to_user | none |
| case_09 | 43 | generic_answer、missing_clarification、no_lookup、push_to_user | generic_answer、missing_clarification | generic_answer、missing_clarification | none |
| case_10 | 72 | none | missing_clarification、push_to_user | none | missing_clarification、push_to_user |
| case_11 | 64 | push_to_user | generic_answer、missing_clarification | none | generic_answer、missing_clarification |
| case_12 | 61 | push_to_user | generic_answer、missing_clarification、no_lookup | none | generic_answer、missing_clarification、no_lookup |
| case_13 | 67 | none | missing_clarification、no_lookup、push_to_user | none | missing_clarification、no_lookup、push_to_user |
| case_14 | 63 | none | missing_clarification | none | missing_clarification |
| case_15 | 61 | missing_clarification | weak_empathy | none | weak_empathy |
| case_16 | 64 | push_to_user | missing_clarification、push_to_user | push_to_user | missing_clarification |
| case_17 | 77 | none | missing_clarification、push_to_user | none | missing_clarification、push_to_user |
| case_18 | 43 | missing_clarification、no_lookup、push_to_user | missing_clarification | missing_clarification | none |
| case_19 | 54 | generic_answer、missing_clarification、no_lookup | generic_answer、missing_clarification、no_lookup | generic_answer、missing_clarification、no_lookup | none |
| case_20 | 64 | missing_clarification、no_lookup、push_to_user | missing_clarification、weak_empathy | missing_clarification | weak_empathy |

## 7. 业务要求原文

# 自动回复质量评估标准

## 业务方原始需求（原文）

> "我们上了一个自动回复功能，现在想看看回复质量怎么样。
> 要求就是：回复要**准确**、**有用**、**语气好**，**不能瞎编**。
> 具体怎么评估你们自己看着办吧，反正要能说明白哪些回复好、哪些不好。"

## 补充背景

- 自动回复功能上线两周，覆盖在线客服场景
- 目前还没有评估机制，不确定整体质量水平
- 评估结果会用于：决定是否继续扩大自动回复的覆盖范围
- 如果评估方法靠谱，后续会做成定期跑的自动化流程

## 你需要回答的问题

1. "准确"是什么意思？怎么量化？
2. "有用"是什么意思？怎么量化？
3. "语气好"是什么意思？怎么量化？
4. "不瞎编"是什么意思？怎么量化？
5. 这些指标之间有优先级吗？如果有，怎么排？
6. 你的评估方法有哪些局限性？哪些 case 可能评不准？