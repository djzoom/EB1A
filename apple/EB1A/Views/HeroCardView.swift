import SwiftUI

/// The headline result: estimated arrival month + fast/median/slow chips.
struct HeroCardView: View {
    let result: PredictionResult
    let pd: Date

    var body: some View {
        VStack(spacing: 16) {
            if result.alreadyReached {
                VStack(spacing: 6) {
                    Text("🎉 恭喜！排期已到").font(.title3).bold()
                    Text("当前表A裁定日已越过你的优先日")
                        .font(.subheadline).foregroundStyle(.secondary)
                }
            } else {
                VStack(spacing: 4) {
                    Text("预计排到").font(.subheadline).foregroundStyle(.secondary)
                    Text(Fmt.dateFull(result.crossings.p50))
                        .font(.system(size: 34, weight: .bold, design: .rounded))
                        .foregroundStyle(.green)
                    Text("距今 \(Fmt.wait(result.crossings.p50))")
                        .font(.subheadline).foregroundStyle(.secondary)
                }
            }

            HStack(spacing: 10) {
                StatChip(label: "快", sub: "P10", value: Fmt.dateShort(result.crossings.p10), tint: .green)
                StatChip(label: "中", sub: "P50", value: Fmt.dateShort(result.crossings.p50), tint: .teal, highlighted: true)
                StatChip(label: "慢", sub: "P90", value: Fmt.dateShort(result.crossings.p90), tint: .orange)
            }
        }
        .padding()
        .frame(maxWidth: .infinity)
        .background(Color(.secondarySystemGroupedBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }
}

private struct StatChip: View {
    let label: String
    let sub: String
    let value: String
    let tint: Color
    var highlighted: Bool = false

    var body: some View {
        VStack(spacing: 4) {
            Text(label).font(.caption).bold().foregroundStyle(tint)
            Text(value).font(.subheadline).bold().monospacedDigit()
            Text(sub).font(.caption2).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .background(highlighted ? tint.opacity(0.12) : Color(.tertiarySystemGroupedBackground))
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(highlighted ? tint.opacity(0.4) : .clear, lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}
