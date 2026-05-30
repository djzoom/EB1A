import SwiftUI
import Charts

enum ChartMode: String, CaseIterable, Identifiable {
    case trend = "走势"
    case wait = "等待时间"
    var id: String { rawValue }
}

/// Chart card with a 走势 / 等待时间 mode toggle, mirroring the web.
struct ChartCardView: View {
    let result: PredictionResult
    @State private var mode: ChartMode = .trend

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("排期走势预测")
                    .font(.headline).foregroundColor(Theme.text)
                Spacer()
                Picker("", selection: $mode) {
                    ForEach(ChartMode.allCases) { Text($0.rawValue).tag($0) }
                }
                .pickerStyle(.segmented)
                .fixedSize()
            }

            if mode == .trend {
                TrendChart(result: result)
            } else {
                WaitChart(result: result)
            }

            Legend(mode: mode)
        }
        .padding(16)
        .frame(maxWidth: .infinity)
        .background(Theme.card)
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(Theme.border, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .tint(Theme.primary)
    }
}

// MARK: - Trend chart (X = date, Y = cutoff date)

private struct TrendChart: View {
    let result: PredictionResult

    var body: some View {
        Chart {
            ForEach(result.trendBand) { row in
                AreaMark(
                    x: .value("日期", row.x),
                    yStart: .value("慢", row.low),
                    yEnd: .value("快", row.high)
                )
                .foregroundStyle(Theme.chartP50.opacity(0.10))
                .interpolationMethod(.catmullRom)
            }

            ForEach(result.historyBTrend) { row in
                LineMark(x: .value("日期", row.x), y: .value("裁定日", row.y),
                         series: .value("系列", "历史表B"))
                    .foregroundStyle(Theme.chartHistB.opacity(0.75))
                    .lineStyle(StrokeStyle(lineWidth: 1.5, dash: [5, 3]))
            }

            ForEach(result.historyATrend) { row in
                LineMark(x: .value("日期", row.x), y: .value("裁定日", row.y),
                         series: .value("系列", "历史表A"))
                    .foregroundStyle(Theme.chartHistory)
                    .lineStyle(StrokeStyle(lineWidth: 2.5, lineCap: .round, lineJoin: .round))
            }

            ForEach(result.p50Line) { row in
                LineMark(x: .value("日期", row.x), y: .value("裁定日", row.y),
                         series: .value("系列", "预测中位"))
                    .foregroundStyle(Theme.chartP50)
                    .lineStyle(StrokeStyle(lineWidth: 2.5, lineCap: .round, lineJoin: .round))
                    .interpolationMethod(.catmullRom)
            }

            RuleMark(y: .value("你的PD", result.yourPD))
                .foregroundStyle(Theme.chartHistory.opacity(0.8))
                .lineStyle(StrokeStyle(lineWidth: 1.5, dash: [6, 4]))
                .annotation(position: .top, alignment: .leading) {
                    Text("你的优先日").font(.caption2).foregroundColor(Theme.chartHistory)
                }

            RuleMark(x: .value("今天", result.today))
                .foregroundStyle(Theme.chartToday)
                .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 3]))
        }
        .chartXScale(domain: result.trendXDomain)
        .chartYScale(domain: result.trendYDomain)
        .chartYAxis { dateAxis() }
        .chartXAxis { yearAxis() }
        .frame(height: 260)
    }
}

// MARK: - Wait-time chart (X = PD, Y = wait years)

private struct WaitChart: View {
    let result: PredictionResult

    var body: some View {
        Chart {
            ForEach(result.historyWait) { row in
                LineMark(x: .value("优先日", row.pd), y: .value("等待", row.wait),
                         series: .value("系列", "历史"))
                    .foregroundStyle(Theme.chartHistory)
                    .lineStyle(StrokeStyle(lineWidth: 2.5, lineCap: .round, lineJoin: .round))
            }

            ForEach(result.p10Wait) { row in
                LineMark(x: .value("优先日", row.pd), y: .value("等待", row.wait),
                         series: .value("系列", "快"))
                    .foregroundStyle(Theme.chartP10.opacity(0.6))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 3]))
            }
            ForEach(result.p90Wait) { row in
                LineMark(x: .value("优先日", row.pd), y: .value("等待", row.wait),
                         series: .value("系列", "慢"))
                    .foregroundStyle(Theme.chartP90.opacity(0.6))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 3]))
            }
            ForEach(result.p50Wait) { row in
                LineMark(x: .value("优先日", row.pd), y: .value("等待", row.wait),
                         series: .value("系列", "预测中位"))
                    .foregroundStyle(Theme.chartP50)
                    .lineStyle(StrokeStyle(lineWidth: 2.5, lineCap: .round, lineJoin: .round))
                    .interpolationMethod(.catmullRom)
            }

            RuleMark(x: .value("你的PD", result.yourPD))
                .foregroundStyle(Theme.chartHistory.opacity(0.8))
                .lineStyle(StrokeStyle(lineWidth: 1.5, dash: [6, 4]))

            if let w = result.medianWaitYears {
                PointMark(x: .value("你的PD", result.yourPD), y: .value("等待", w))
                    .foregroundStyle(Theme.chartP50)
                    .symbolSize(120)
                    .annotation(position: .top) {
                        Text(String(format: "%.1f年", w))
                            .font(.caption2).bold().foregroundColor(Theme.chartP50)
                    }
            }
        }
        .chartXScale(domain: result.waitXDomain)
        .chartYAxis {
            AxisMarks(values: .stride(by: 1)) { value in
                AxisGridLine().foregroundStyle(Color(hex: 0xF0F0F0))
                AxisValueLabel {
                    if let v = value.as(Double.self) {
                        Text("\(Int(v))年").foregroundColor(Theme.text3)
                    }
                }
            }
        }
        .chartXAxis { yearAxis() }
        .frame(height: 260)
    }
}

// MARK: - Shared axis builders

@AxisContentBuilder
private func dateAxis() -> some AxisContent {
    AxisMarks { value in
        AxisGridLine().foregroundStyle(Color(hex: 0xF0F0F0))
        AxisValueLabel {
            if let d = value.as(Date.self) {
                Text(yearString(d)).foregroundColor(Theme.text3)
            }
        }
    }
}

@AxisContentBuilder
private func yearAxis() -> some AxisContent {
    AxisMarks(values: .stride(by: .year)) { value in
        AxisGridLine().foregroundStyle(Color(hex: 0xF0F0F0))
        AxisValueLabel {
            if let d = value.as(Date.self) {
                Text(yearString(d)).foregroundColor(Theme.text3)
            }
        }
    }
}

private func yearString(_ d: Date) -> String {
    let c = EBDate.utc.dateComponents([.year], from: d)
    return "\(c.year ?? 0)"
}

// MARK: - Legend

private struct Legend: View {
    let mode: ChartMode
    var body: some View {
        HStack(spacing: 14) {
            if mode == .trend {
                LegendItem(color: Theme.chartHistory, text: "历史表A")
                LegendItem(color: Theme.chartHistB, text: "历史表B")
                LegendItem(color: Theme.chartP50, text: "预测中位")
                LegendItem(color: Theme.chartP50.opacity(0.35), text: "P10–P90 区间")
            } else {
                LegendItem(color: Theme.chartHistory, text: "历史等待")
                LegendItem(color: Theme.chartP50, text: "预测中位")
                LegendItem(color: Theme.chartP10, text: "快(P10)")
                LegendItem(color: Theme.chartP90, text: "慢(P90)")
            }
        }
        .font(.caption2)
        .foregroundColor(Theme.text3)
    }
}

private struct LegendItem: View {
    let color: Color
    let text: String
    var body: some View {
        HStack(spacing: 4) {
            RoundedRectangle(cornerRadius: 2).fill(color).frame(width: 12, height: 4)
            Text(text)
        }
    }
}
