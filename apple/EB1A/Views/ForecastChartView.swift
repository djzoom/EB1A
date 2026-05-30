import SwiftUI
import Charts

/// Trend chart: X = calendar date, Y = cutoff date. Shows Table A history,
/// the p10–p90 band, p10/p50/p90 lines, the user's PD and today. Colors match
/// the web drawForecastChart.
struct ForecastChartView: View {
    let result: PredictionResult
    let pd: Date

    private var today: Date { Date() }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("排期走势预测")
                .font(.headline).foregroundColor(Theme.text)

            Chart {
                // p10–p90 confidence band (dark-green tint).
                ForEach(result.band) { row in
                    AreaMark(
                        x: .value("日期", row.x),
                        yStart: .value("慢", row.low),
                        yEnd: .value("快", row.high)
                    )
                    .foregroundStyle(Theme.chartP50.opacity(0.10))
                    .interpolationMethod(.catmullRom)
                }

                // Historical Table A (amber).
                ForEach(result.historyA) { row in
                    LineMark(
                        x: .value("日期", row.x),
                        y: .value("裁定日", row.y),
                        series: .value("系列", "历史表A")
                    )
                    .foregroundStyle(Theme.chartHistory)
                    .lineStyle(StrokeStyle(lineWidth: 2.5, lineCap: .round, lineJoin: .round))
                }

                // p50 median prediction (dark green).
                ForEach(result.p50Line) { row in
                    LineMark(
                        x: .value("日期", row.x),
                        y: .value("裁定日", row.y),
                        series: .value("系列", "预测中位")
                    )
                    .foregroundStyle(Theme.chartP50)
                    .lineStyle(StrokeStyle(lineWidth: 2.5, lineCap: .round, lineJoin: .round))
                    .interpolationMethod(.catmullRom)
                }

                // Your PD (horizontal, amber) + today (vertical, gray).
                RuleMark(y: .value("你的PD", pd))
                    .foregroundStyle(Theme.chartHistory.opacity(0.8))
                    .lineStyle(StrokeStyle(lineWidth: 1.5, dash: [6, 4]))
                    .annotation(position: .top, alignment: .leading) {
                        Text("你的优先日")
                            .font(.caption2).foregroundColor(Theme.chartHistory)
                    }

                RuleMark(x: .value("今天", today))
                    .foregroundStyle(Theme.chartToday)
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 3]))
            }
            .chartYAxis {
                AxisMarks { value in
                    AxisGridLine().foregroundStyle(Color(hex: 0xF0F0F0))
                    AxisValueLabel {
                        if let d = value.as(Date.self) {
                            Text(yearLabel(d)).foregroundColor(Theme.text3)
                        }
                    }
                }
            }
            .chartXAxis {
                AxisMarks(values: .stride(by: .year)) { value in
                    AxisGridLine().foregroundStyle(Color(hex: 0xF0F0F0))
                    AxisValueLabel {
                        if let d = value.as(Date.self) {
                            Text(yearLabel(d)).foregroundColor(Theme.text3)
                        }
                    }
                }
            }
            .frame(height: 260)

            Legend()
        }
        .padding(16)
        .frame(maxWidth: .infinity)
        .background(Theme.card)
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(Theme.border, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    private func yearLabel(_ d: Date) -> String {
        let c = EBDate.utc.dateComponents([.year], from: d)
        return "\(c.year ?? 0)"
    }
}

private struct Legend: View {
    var body: some View {
        HStack(spacing: 14) {
            LegendItem(color: Theme.chartHistory, text: "历史表A")
            LegendItem(color: Theme.chartP50, text: "预测中位")
            LegendItem(color: Theme.chartP50.opacity(0.35), text: "P10–P90 区间")
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
