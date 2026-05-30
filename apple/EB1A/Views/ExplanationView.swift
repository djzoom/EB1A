import SwiftUI

/// Collapsible 算法说明 + 关于本工具, mirroring the web accordions.
struct ExplanationView: View {
    let result: PredictionResult
    let params: ModelParams

    @State private var showAlgo = false
    @State private var showAbout = false

    var body: some View {
        VStack(spacing: 10) {
            Card {
                DisclosureGroup(isExpanded: $showAlgo) {
                    AlgorithmText(result: result, params: params)
                        .padding(.top, 8)
                } label: {
                    Text("算法说明").font(.subheadline).bold().foregroundColor(Theme.text)
                }
            }
            Card {
                DisclosureGroup(isExpanded: $showAbout) {
                    AboutText().padding(.top, 8)
                } label: {
                    Text("关于本工具").font(.subheadline).bold().foregroundColor(Theme.text)
                }
            }
        }
        .tint(Theme.primary)
    }
}

private struct Card<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        content
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.card)
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(Theme.border, lineWidth: 1))
            .clipShape(RoundedRectangle(cornerRadius: 14))
    }
}

// MARK: - Algorithm explanation (ports renderExplanation ① ② ③ ④)

private struct AlgorithmText: View {
    let result: PredictionResult
    let params: ModelParams

    var body: some View {
        let cutoff = result.currentCutoff.timeIntervalSince1970
        let pd = result.yourPD.timeIntervalSince1970
        let gapDays = Int(((pd - cutoff) / 86_400).rounded())

        if gapDays <= 0 {
            Text("当前排期已推进到 **\(Fmt.dateShort(cutoff))**，已达到或超过你的优先日 **\(Fmt.dateShort(pd))**——也就是说你的排期理论上已经 current。一切仍以官方签证公告为准。")
                .font(.system(size: 13)).foregroundColor(Theme.text2)
        } else {
            let totalSupply = params.chinaBaseQuota + params.spilloverROW + params.spilloverIndia + params.eb4eb5Spillover
            let mainPerYear = Int((totalSupply / params.familyMultiplier).rounded())
            let eng = SimulationEngine(params: params, cutoffStart: result.currentCutoff,
                                       yourPD: result.yourPD, today: result.today,
                                       generator: SplitMix64(seed: 1))
            let avgDensity = eng.getPDDensity((cutoff + pd) / 2)
            let densityRound = max(1, Int(avgDensity.rounded()))
            let queueAhead = Int((Double(gapDays) * avgDensity).rounded())
            let yearsEst = mainPerYear > 0 ? Double(queueAhead) / Double(mainPerYear) : 0
            let spillTotal = Int(totalSupply - params.chinaBaseQuota)
            let spillStr = (spillTotal >= 0 ? "＋ " : "－ ") + abs(spillTotal).formatted()
            let fm = String(format: "%.1f", params.familyMultiplier)

            VStack(alignment: .leading, spacing: 12) {
                Text("**这个时间是怎么推算出来的？** 工具不是去拟合一条趋势线，而是还原签证发放的真实供需过程，分四步：")
                    .font(.system(size: 13)).foregroundColor(Theme.text2)

                Step(title: "① 你前面还排着多少人",
                     text: "当前排期排到 **\(Fmt.dateShort(cutoff))**，你的优先日是 **\(Fmt.dateShort(pd))**，相差 **\(gapDays.formatted()) 天**。按这段优先日时期每天约 \(densityRound) 个中国大陆申请人估算，你前面大约还有 **\(queueAhead.formatted()) 名主申请人**。")

                Step(title: "② 每年能消化多少人",
                     text: "EB-1 中国大陆每年可用签证号 ≈ 法定配额 \(Int(params.chinaBaseQuota).formatted()) \(spillStr) 个溢出 = **\(Int(totalSupply).formatted()) 个**。一个签证号覆盖全家（平均 \(fm) 人），换算成主申请人约 **\(mainPerYear.formatted()) 人/年**。")

                Step(title: "③ 相除得到大致年数",
                     text: "\(queueAhead.formatted()) 人 ÷ \(mainPerYear.formatted()) 人/年 ≈ **\(String(format: "%.1f", yearsEst)) 年**，这是一个粗略的中心估计。")

                Step(title: "④ 加入真实节奏与不确定性",
                     text: "实际发放并不匀速：财年前几个月发得猛、后段收紧；每年 10 月新财年配额释放时排期常出现\u{201C}跳进\u{201D}；再叠加随机波动。工具据此跑 **500 次蒙特卡洛模拟**，取排期追上你 PD 的时间分布，得到 **快 / 中 / 慢** 三档与置信区间。")

                Text("以上为基于公开数据的统计估算，非官方、非法律意见。配额政策、行政命令或申请人行为变化都会改变真实结果。")
                    .font(.system(size: 11)).foregroundColor(Theme.text3)
            }
        }
    }
}

/// Render a runtime string containing inline **markdown** (literal-string
/// markdown parsing in Text only works for compile-time literals).
private func md(_ s: String) -> Text {
    if let a = try? AttributedString(markdown: s,
        options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)) {
        return Text(a)
    }
    return Text(s)
}

private struct Step: View {
    let title: String
    let text: String
    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title).font(.system(size: 12.5, weight: .bold)).foregroundColor(Theme.primary)
            md(text).font(.system(size: 13)).foregroundColor(Theme.text2)
        }
    }
}

// MARK: - About (ports the 关于本工具 accordion)

private struct AboutText: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Para("**怎么预测**", "不外推历史趋势线，而是还原签证发放背后的供需逻辑：用\u{201C}排期间隔 × 排队密度\u{201D}估算前方人数，用\u{201C}每年可用签证 ÷ 家庭系数\u{201D}估算年消化量，相除得大致年数，再跑 500 次蒙特卡洛模拟给出快/中/慢三档。")
            Para("**表 A 与 表 B**", "表 A（最终裁定日）决定何时真正获批绿卡；表 B（递交日期）决定何时可递交 I-485。本工具同时呈现两者。")
            Para("**第一时间获取最新公告**", "App 启动及回到前台时检查仓库的最新签证公告，发现新一期会发本地通知。")
            Para("**隐私与数据**", "你的优先日仅保存在本机，绝不上传。底层数据均取自 USCIS 与 DOS 的公开来源。")
            Para("**作者**", "由 0xGarfield · @DJWZ 制作。")
            Text("本工具仅为基于公开数据的统计估算，不构成法律建议。请以官方签证公告为准，并咨询持牌移民律师。")
                .font(.system(size: 11)).foregroundColor(Theme.text3)
        }
    }
}

private struct Para: View {
    let head: String
    let text: String
    init(_ head: String, _ text: String) { self.head = head; self.text = text }
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            md(head).font(.system(size: 13)).foregroundColor(Theme.text)
            Text(text).font(.system(size: 13)).foregroundColor(Theme.text2)
        }
    }
}
