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
        Group {
            if let pd {
                MainView(pd: pd, vm: vm, showEdit: $showEdit, showSettings: $showSettings)
            } else {
                WelcomeView { newPD in pdInterval = newPD.timeIntervalSince1970 }
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

/// The main result screen once a PD is set. Layout mirrors the web topbar →
/// cards → footer structure.
private struct MainView: View {
    let pd: Date
    @ObservedObject var vm: PredictionViewModel
    @Binding var showEdit: Bool
    @Binding var showSettings: Bool
    @EnvironmentObject private var watcher: BulletinWatcher

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                TopBar(pd: pd, showEdit: $showEdit, showSettings: $showSettings)

                if let latest = watcher.latest {
                    BulletinBanner(entry: latest)
                }

                if let result = vm.result {
                    HeroCardView(result: result, pd: pd)
                    ForecastChartView(result: result, pd: pd)
                } else {
                    ProgressView("正在运行 500 次蒙特卡洛模拟…")
                        .frame(maxWidth: .infinity, minHeight: 200)
                }

                FooterView()
            }
            .padding(16)
        }
        .background(Theme.bg.ignoresSafeArea())
        .overlay(alignment: .top) {
            if vm.isRunning && vm.result != nil {
                ProgressView().padding(8)
            }
        }
    }
}

/// Web-style topbar: stacked title + subtitle, then PD info + pill buttons.
private struct TopBar: View {
    let pd: Date
    @Binding var showEdit: Bool
    @Binding var showSettings: Bool

    private var pdLabel: String { Fmt.dateShort(pd.timeIntervalSince1970) }
    private var distanceDays: Int {
        Int((pd.timeIntervalSince1970 - VisaData.currentCutoffA.timeIntervalSince1970) / 86_400)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("EB-1A 中国申请人排期预测器")
                .font(.system(size: 19, weight: .bold))
                .foregroundColor(Theme.text)
            Text("基于蒙特卡洛模拟")
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(Theme.text3)

            HStack(spacing: 8) {
                HStack(spacing: 6) {
                    Text("PD \(pdLabel)")
                        .font(.system(size: 12.5))
                        .foregroundColor(Theme.text2)
                    Text(distanceDays >= 0 ? "+\(distanceDays)天" : "\(distanceDays)天")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(Theme.orange)
                }
                Spacer()
                PillButton(title: "编辑") { showEdit = true }
                PillButton(title: "设置", filled: true) { showSettings = true }
            }
            .padding(.top, 2)
        }
    }
}

/// Mirrors the web .text-btn pill (border, dark-green text; filled variant).
private struct PillButton: View {
    let title: String
    var filled: Bool = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 12.5, weight: .semibold))
                .foregroundColor(Theme.primary)
                .padding(.horizontal, 12)
                .padding(.vertical, 7)
                .background(filled ? Theme.primaryBg : Color.clear)
                .overlay(
                    Capsule().stroke(filled ? Theme.primaryLight : Theme.border, lineWidth: 1)
                )
                .clipShape(Capsule())
        }
        .buttonStyle(.plain)
    }
}

private struct BulletinBanner: View {
    let entry: ReleaseLogEntry
    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "bell.badge.fill").foregroundColor(Theme.orange)
            VStack(alignment: .leading, spacing: 2) {
                Text("最新公告 · \(entry.bulletin)")
                    .font(.subheadline).bold().foregroundColor(Theme.text)
                if let fad = entry.fad, let dff = entry.dff {
                    Text("表A \(fad) · 表B \(dff)")
                        .font(.caption).foregroundColor(Theme.text2)
                }
            }
            Spacer()
        }
        .padding()
        .background(Theme.card)
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Theme.border, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}

/// Footer mirroring the web: open-source (MIT + GitHub) + legal + copyright.
private struct FooterView: View {
    private let repoURL = URL(string: "https://github.com/djzoom/EB1A")!

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("EB-1A 中国大陆排期预测 · 自动同步最新签证公告 · 数据源 USCIS / DOS")
            HStack(spacing: 4) {
                Text("本项目开源 · MIT 协议 · 源码")
                Link("github.com/djzoom/EB1A", destination: repoURL)
                    .foregroundColor(Theme.primary)
            }
            Text("法律声明：本工具仅为基于公开数据的统计估算，不构成法律或移民建议，亦不对预测准确性作任何保证。实际排期受配额、政策、立法及个人情况影响，请以美国国务院官方签证公告为准，并咨询持牌移民律师。你输入的信息仅存于本机，绝不上传。")
            Text("© 2026 djzoom")
        }
        .font(.system(size: 11))
        .foregroundColor(Theme.text3)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.top, 6)
    }
}
