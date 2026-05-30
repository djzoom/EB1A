import SwiftUI

/// The headline result: estimated arrival month + fast/median/slow chips.
/// Colors mirror the web: hero number 深绿(--blue), 快=green / 中=深绿 / 慢=orange.
struct HeroCardView: View {
    let result: PredictionResult
    let pd: Date

    var body: some View {
        VStack(spacing: 16) {
            if result.alreadyReached {
                VStack(spacing: 6) {
                    Text("🎉 恭喜！排期已到")
                        .font(.title3).bold().foregroundColor(Theme.primary)
                    Text("当前表A裁定日已越过你的优先日")
                        .font(.subheadline).foregroundColor(Theme.text2)
                }
            } else {
                VStack(spacing: 4) {
                    Text("预计排到")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundColor(Theme.text2)
                    Text(Fmt.dateFull(result.crossings.p50))
                        .font(.system(size: 34, weight: .heavy))
                        .foregroundColor(Theme.primary)
                    Text("距今 \(Fmt.wait(result.crossings.p50))")
                        .font(.system(size: 13))
                        .foregroundColor(Theme.text2)
                }
            }

            HStack(spacing: 8) {
                StatChip(label: "快", value: Fmt.dateShort(result.crossings.p10), tint: Theme.green)
                StatChip(label: "中", value: Fmt.dateShort(result.crossings.p50), tint: Theme.primary, selected: true)
                StatChip(label: "慢", value: Fmt.dateShort(result.crossings.p90), tint: Theme.orange)
            }
        }
        .padding(.vertical, 20)
        .padding(.horizontal, 16)
        .frame(maxWidth: .infinity)
        .background(Theme.card)
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(Theme.border, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }
}

private struct StatChip: View {
    let label: String
    let value: String
    let tint: Color
    var selected: Bool = false

    var body: some View {
        VStack(spacing: 2) {
            Text(label).font(.system(size: 11)).foregroundColor(Theme.text3)
            Text(value)
                .font(.system(size: 14, weight: .bold))
                .foregroundColor(tint)
                .monospacedDigit()
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 10)
        .background(selected ? Theme.bg : Color.clear)
        .clipShape(RoundedRectangle(cornerRadius: 9))
        .shadow(color: selected ? Color.black.opacity(0.05) : .clear, radius: 3, y: 1)
    }
}
