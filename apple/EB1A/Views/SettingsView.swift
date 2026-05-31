import SwiftUI

struct SettingsView: View {
    @ObservedObject var vm: PredictionViewModel
    @AppStorage("eb1a_notify") private var notify = true
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("预测情景") {
                    Picker("情景", selection: $vm.preset) {
                        ForEach(Preset.allCases) { p in
                            Text(p.label).tag(p)
                        }
                    }
                    .pickerStyle(.segmented)
                    Text(presetHint)
                        .font(.caption).foregroundStyle(.secondary)
                    Button {
                        vm.preset = .realistic   // 重置为默认情景
                    } label: {
                        Label("重置为默认", systemImage: "arrow.counterclockwise")
                    }
                    .disabled(vm.preset == .realistic)
                }

                Section("签证公告通知") {
                    Toggle("新公告发布时通知我", isOn: $notify)
                    Text("App 启动及回到前台时，会检查仓库的最新签证公告；发现新一期时发本地通知。")
                        .font(.caption).foregroundStyle(.secondary)
                }

                Section("关于") {
                    Text("EB-1A 中国大陆排期预测 · 原生 iOS 版")
                        .font(.subheadline)
                    Text("预测仅供参考，以美国国务院签证公告为准。")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            .navigationTitle("设置")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("完成") { dismiss() }
                }
            }
        }
        .tint(Theme.primary)
    }

    private var presetHint: String {
        switch vm.preset {
        case .realistic: return "现实：基于近年实际推进速度校准的默认情景。"
        case .optimistic: return "乐观：溢出配额充裕、排队密度较低。"
        case .pessimistic: return "悲观：溢出收紧、印度竞争加剧、密度偏高。"
        }
    }
}
