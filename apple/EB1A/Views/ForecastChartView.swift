import SwiftUI
import Charts

/// Trend chart: X = calendar date, Y = cutoff date (the date the bulletin has
/// reached). Shows Table A history, the p10–p90 confidence band, the p50
/// median path, the user's PD, and today.
struct ForecastChartView: View {
    let result: PredictionResult
    let pd: Date

    private var today: Date { Date() }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("排期走势预测").font(.headline)

            Chart {
                // p10–p90 confidence band.
                ForEach(result.band) { row in
                    AreaMark(
                        x: .value("日期", row.x),
                        yStart: .value("慢", row.low),
                        yEnd: .value("快", row.high)
                    )
                    .foregroundStyle(Color.green.opacity(0.12))
                    .interpolationMethod(.catmullRom)
                }

                // Historical Table A.
                ForEach(result.historyA) { row in
                    LineMark(
                        x: .value("日期", row.x),
                        y: .value("裁定日", row.y),
                        series: .value("系列", "历史表A")
                    )
                    .foregroundStyle(.orange)
                    .lineStyle(StrokeStyle(lineWidth: 2))
                }

                // p50 median prediction.
                ForEach(result.p50Line) { row in
                    LineMark(
                        x: .value("日期", row.x),
                        y: .value("裁定日", row.y),
                        series: .value("系列", "预测中位")
                    )
                    .foregroundStyle(.teal)
                    .lineStyle(StrokeStyle(lineWidth: 2, dash: [5, 4]))
                    .interpolationMethod(.catmullRom)
                }

                // Your priority date (horizontal) and today (vertical).
                RuleMark(y: .value("你的PD", pd))
                    .foregroundStyle(.orange.opacity(0.7))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 4]))
                    .annotation(position: .top, alignment: .leading) {
                        Text("你的优先日").font(.caption2).foregroundStyle(.orange)
                    }

                RuleMark(x: .value("今天", today))
                    .foregroundStyle(.gray.opacity(0.5))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [2, 3]))
            }
            .chartYAxis {
                AxisMarks { value in
                    AxisGridLine()
                    AxisValueLabel {
                        if let d = value.as(Date.self) {
                            Text(yearLabel(d))
                        }
                    }
                }
            }
            .chartXAxis {
                AxisMarks(values: .stride(by: .year)) { value in
                    AxisGridLine()
                    AxisValueLabel {
                        if let d = value.as(Date.self) {
                            Text(yearLabel(d))
                        }
                    }
                }
            }
            .frame(height: 260)

            Legend()
        }
        .padding()
        .frame(maxWidth: .infinity)
        .background(Color(.secondarySystemGroupedBackground))
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
            LegendItem(color: .orange, text: "历史表A")
            LegendItem(color: .teal, text: "预测中位")
            LegendItem(color: .green.opacity(0.4), text: "P10–P90 区间")
        }
        .font(.caption2)
        .foregroundStyle(.secondary)
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
