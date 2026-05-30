import SwiftUI

struct ContentView: View {
    @AppStorage("eb1a_pd") private var pdInterval: Double = 0
    @AppStorage("eb1a_notify") private var notify = true
    @Environment(\.scenePhase) private var phase
    @EnvironmentObject private var watcher: BulletinWatcher
    @StateObject private var vm = PredictionViewModel()

    @State private var showEdit = false
    @State private var showSettings = false

    private var pd: Date? { pdInterval > 0 ? Date(timeIntervalSince1970: pdInterval) : nil }

    var body: some View {
        NavigationStack {
            Group {
                if let pd {
                    MainView(pd: pd, vm: vm)
                } else {
                    WelcomeView { newPD in pdInterval = newPD.timeIntervalSince1970 }
                }
            }
            .navigationTitle("EB1A 排期预测")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                if pd != nil {
                    ToolbarItem(placement: .navigationBarTrailing) {
                        Button { showEdit = true } label: { Image(systemName: "calendar") }
                    }
                    ToolbarItem(placement: .navigationBarLeading) {
                        Button { showSettings = true } label: { Image(systemName: "slider.horizontal.3") }
                    }
                }
            }
        }
        .sheet(isPresented: $showEdit) {
            EditPDView(initial: pd ?? EBDate.make(2024, 6, 1)) { newPD in
                pdInterval = newPD.timeIntervalSince1970
            }
        }
        .sheet(isPresented: $showSettings) {
            SettingsView(vm: vm)
        }
        .task {
            await watcher.requestAuthorization()
            if let pd { vm.run(pd: pd) }
            await watcher.check(notify: notify)
        }
        .onChange(of: pdInterval) { _ in
            if let pd { vm.run(pd: pd) }
        }
        .onChange(of: phase) { newPhase in
            if newPhase == .active {
                Task { await watcher.check(notify: notify) }
            }
        }
    }
}

/// The main result screen once a PD is set.
private struct MainView: View {
    let pd: Date
    @ObservedObject var vm: PredictionViewModel
    @EnvironmentObject private var watcher: BulletinWatcher

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                if let latest = watcher.latest {
                    BulletinBanner(entry: latest)
                }

                if let result = vm.result {
                    HeroCardView(result: result, pd: pd)
                    ForecastChartView(result: result, pd: pd)
                } else {
                    ProgressView("正在模拟 500 条路径…")
                        .frame(maxWidth: .infinity, minHeight: 200)
                }

                DisclaimerView()
            }
            .padding()
        }
        .background(Color(.systemGroupedBackground))
        .overlay(alignment: .top) {
            if vm.isRunning && vm.result != nil {
                ProgressView().padding(8)
            }
        }
    }
}

private struct BulletinBanner: View {
    let entry: ReleaseLogEntry
    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "bell.badge.fill").foregroundStyle(.orange)
            VStack(alignment: .leading, spacing: 2) {
                Text("最新公告 · \(entry.bulletin)").font(.subheadline).bold()
                if let fad = entry.fad, let dff = entry.dff {
                    Text("表A \(fad) · 表B \(dff)")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            Spacer()
        }
        .padding()
        .background(Color(.secondarySystemGroupedBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}

private struct DisclaimerView: View {
    var body: some View {
        Text("本预测基于公开数据与统计模型，仅供参考，不构成移民或法律建议。实际排期以美国国务院签证公告为准。")
            .font(.caption2)
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.top, 4)
    }
}
