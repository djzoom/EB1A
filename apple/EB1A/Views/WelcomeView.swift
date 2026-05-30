import SwiftUI

/// First-run screen: collect the user's priority date.
struct WelcomeView: View {
    var onStart: (Date) -> Void
    @State private var date = EBDate.make(2024, 6, 1)

    var body: some View {
        VStack(spacing: 24) {
            Spacer()
            Image(systemName: "chart.line.uptrend.xyaxis")
                .font(.system(size: 56))
                .foregroundColor(Theme.primary)

            VStack(spacing: 8) {
                Text("EB-1A 中国申请人排期预测器")
                    .font(.title2).bold()
                    .foregroundColor(Theme.text)
                Text("基于蒙特卡洛模拟 · 输入你的优先日 (Priority Date)，估算大约何时轮到你。")
                    .font(.subheadline)
                    .foregroundColor(Theme.text2)
                    .multilineTextAlignment(.center)
            }

            DatePicker("优先日", selection: $date, displayedComponents: .date)
                .datePickerStyle(.compact)
                .environment(\.timeZone, TimeZone(identifier: "UTC")!)
                .labelsHidden()

            Button {
                onStart(date)
            } label: {
                Text("开始预测")
                    .bold()
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 4)
            }
            .buttonStyle(.borderedProminent)
            .tint(Theme.primary)

            Spacer()
        }
        .padding(32)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Theme.bg.ignoresSafeArea())
    }
}

/// Sheet to edit the priority date later.
struct EditPDView: View {
    let initial: Date
    var onSave: (Date) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var date: Date

    init(initial: Date, onSave: @escaping (Date) -> Void) {
        self.initial = initial
        self.onSave = onSave
        _date = State(initialValue: initial)
    }

    var body: some View {
        NavigationStack {
            Form {
                DatePicker("优先日 (PD)", selection: $date, displayedComponents: .date)
                    .environment(\.timeZone, TimeZone(identifier: "UTC")!)
            }
            .navigationTitle("修改优先日")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("保存") { onSave(date); dismiss() }
                }
            }
        }
        .tint(Theme.primary)
    }
}
