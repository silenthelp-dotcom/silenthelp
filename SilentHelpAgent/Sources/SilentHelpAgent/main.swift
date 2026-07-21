//
//  SilentHelp Agent — native macOS background monitor (prototype)
//  ==============================================================
//  A menu-bar (accessory) app that:
//    1. Reads the FOCUSED text field of whatever app you're in, via the
//       macOS Accessibility API (AXUIElement). Native apps (Messages, Notes,
//       Mail) expose this well; Electron apps (Discord) are hit-or-miss.
//    2. Sends that text to the local SilentHelp backend:
//         POST /api/scan   (Layer 1, instant, local)
//         POST /classify   (Layer 2, semantic) only if L1 matched
//    3. Pops up a native alert when a tier-3 crisis phrase fires or the
//       backend routes to a human.
//
//  PRIVACY: the agent reads only the currently focused field, keeps the text
//  in memory for one scan, and sends it to 127.0.0.1 (your machine). The
//  backend itself only forwards to the cloud for the L2 semantic check. Nothing
//  is persisted by the agent. Prototype only — review before any real use.
//
//  Requires: Accessibility permission (System Settings ▸ Privacy & Security ▸
//  Accessibility). The app requests it on launch.
//

import AppKit
import ApplicationServices
import CoreGraphics
import Foundation
import ScreenCaptureKit
import Vision

// MARK: - Config
enum Config {
    static let localBackend = "http://127.0.0.1:5055"
    // Preference order for the hosted app: the real domain first, Render's
    // fallback second (still works while DNS propagates or if the domain lapses).
    static let hostedCandidates = ["https://silenthelp.org", "https://silenthelp.onrender.com"]
    /// The hosted app URL that actually answered at launch (for "Talk it through").
    static var hostedBackend = "https://silenthelp.org"
    /// Resolved at launch: local backend if one is running (the developer's
    /// fully-on-device setup), else the hosted app (a friend's install).
    /// Manual override: put a URL in ~/Library/Application Support/SilentHelp/backend.txt
    static var backend = localBackend
    static let pollSeconds: TimeInterval = 1.5   // how often we read the focused field
    static let minChars = 8                       // ignore very short text
    static let cooldownSeconds: TimeInterval = 90 // after a popup, stay quiet
    static let ocrSeconds: TimeInterval = 1.2     // how often we OCR the screen
    static let ocrCooldown: TimeInterval = 15     // quiet window after an OCR-driven popup
                                                  // (crisis hits BYPASS the cooldown)
    static let ocrMaxDim: CGFloat = 2400          // capture cap — Retina-scale so
                                                  // normal-size document text is
                                                  // big enough for OCR to read
}

// MARK: - Backend resolution (local first, then hosted candidates in order)
private func probe(_ base: String, timeout: TimeInterval) -> Bool {
    guard let url = URL(string: base + "/api/me") else { return false }
    var req = URLRequest(url: url)
    req.timeoutInterval = timeout
    let sem = DispatchSemaphore(value: 0)
    var up = false
    URLSession.shared.dataTask(with: req) { _, resp, _ in
        up = (resp as? HTTPURLResponse)?.statusCode == 200
        sem.signal()
    }.resume()
    _ = sem.wait(timeout: .now() + timeout + 0.5)
    return up
}

func resolveBackend() {
    // Pick the hosted app first (silenthelp.org, else the Render fallback) so
    // "Talk it through" always opens something real.
    for candidate in Config.hostedCandidates where probe(candidate, timeout: 4) {
        Config.hostedBackend = candidate
        break
    }
    // 1. Explicit override file wins for DETECTION traffic.
    let cfgPath = (NSString(string: "~/Library/Application Support/SilentHelp/backend.txt")).expandingTildeInPath
    if let s = try? String(contentsOfFile: cfgPath, encoding: .utf8)
        .trimmingCharacters(in: .whitespacesAndNewlines), s.hasPrefix("http") {
        Config.backend = s
        shLog("backend from config file: \(s)")
        return
    }
    // 2. Local backend if one is running (the developer's private setup).
    let localUp = probe(Config.localBackend, timeout: 1.5)
    Config.backend = localUp ? Config.localBackend : Config.hostedBackend
    shLog("backend resolved: \(Config.backend) (local up: \(localUp), hosted: \(Config.hostedBackend))")
}

// MARK: - Diagnostic log (/tmp/silenthelp-agent.log)
func shLog(_ msg: String) {
    let ts = ISO8601DateFormatter().string(from: Date())
    let line = "\(ts)  \(msg)\n"
    let path = "/tmp/silenthelp-agent.log"
    if let fh = FileHandle(forWritingAtPath: path) {
        fh.seekToEndOfFile(); fh.write(Data(line.utf8)); fh.closeFile()
    } else {
        try? line.write(toFile: path, atomically: true, encoding: .utf8)
    }
}

// MARK: - Backend client
struct Decision {
    let tier3: Bool
    let matched: Bool
    let routeToHuman: Bool
    let level: String
}

enum Backend {
    /// One call: runs L1+L2, RECORDS the event for trend gating, returns the
    /// gating decision. The running SilentHelp app polls /api/gating and surfaces
    /// the same gentle/urgent screens — so the agent drives the real UI too.
    static func monitor(_ text: String, _ done: @escaping ([String: Any]?) -> Void) {
        post("/api/monitor", ["text": text], done)
    }

    /// Layer 1 only — instant local keyword scan (~15ms, no model). Used for the
    /// OCR screen path so detection is immediate and high-precision.
    static func scan(_ text: String, _ done: @escaping ([String: Any]?) -> Void) {
        post("/api/scan", ["text": text], done)
    }

    /// Layer 3 — behavioral signals (no text). Posts the computed rhythm to the
    /// backend so the dashboard / findings reflect real on-device behavior.
    static func log(_ signals: [String: Any]) {
        post("/api/behavioral/log", signals) { _ in }
    }

    static func get(_ path: String, _ done: @escaping ([String: Any]?) -> Void) {
        guard let url = URL(string: Config.backend + path) else { done(nil); return }
        var req = URLRequest(url: url)
        req.timeoutInterval = 8
        URLSession.shared.dataTask(with: req) { d, _, _ in
            guard let d, let json = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { done(nil); return }
            done(json)
        }.resume()
    }

    private static func post(_ path: String, _ body: [String: Any], _ done: @escaping ([String: Any]?) -> Void) {
        guard let url = URL(string: Config.backend + path),
              let data = try? JSONSerialization.data(withJSONObject: body) else { done(nil); return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = data
        req.timeoutInterval = 8
        URLSession.shared.dataTask(with: req) { d, _, _ in
            guard let d, let json = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { done(nil); return }
            done(json)
        }.resume()
    }
}

// MARK: - Accessibility reader
enum AXReader {
    /// Read the text of the currently focused UI element across the whole system.
    static func focusedText() -> String? {
        let system = AXUIElementCreateSystemWide()
        var focused: AnyObject?
        guard AXUIElementCopyAttributeValue(system, kAXFocusedUIElementAttribute as CFString, &focused) == .success,
              let element = focused else { return nil }
        let el = element as! AXUIElement

        // Prefer the full value; fall back to selected text.
        for attr in [kAXValueAttribute, kAXSelectedTextAttribute] {
            var v: AnyObject?
            if AXUIElementCopyAttributeValue(el, attr as CFString, &v) == .success,
               let s = v as? String, !s.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                return s
            }
        }
        return nil
    }
}

// MARK: - Snooze ("ignore for a while")
// User-controlled quiet period: no scanning-driven popups until it expires.
// Set from the popup's "Ignore 1h / 2h" buttons or the menu-bar items.
enum Snooze {
    static var until = Date.distantPast
    static var isActive: Bool { Date() < until }
    static func set(hours: Double) {
        until = Date().addingTimeInterval(hours * 3600)
        shLog("SNOOZE until \(ISO8601DateFormatter().string(from: until))")
    }
    static func clear() { until = Date.distantPast; shLog("SNOOZE cleared") }
}

// MARK: - Popup
final class Popup {
    static let shared = Popup()
    private var panel: NSPanel?
    private var currentMessage = ""
    private var currentCrisis = false
    private var lastShowAt = Date.distantPast

    func show(title: String, message: String, crisis: Bool) {
        DispatchQueue.main.async { self._show(title: title, message: message, crisis: crisis) }
    }

    private func _show(title: String, message: String, crisis: Bool) {
        // A popup of the same severity is ALREADY on screen and fresh — one
        // moment, one popup, even when several detection paths fire at once.
        // Dismissing it re-arms immediately.
        if let p = panel, p.isVisible {
            if currentMessage == title + message { return }
            if crisis == currentCrisis && Date() < lastShowAt.addingTimeInterval(30) { return }
        }
        currentMessage = title + message
        currentCrisis = crisis
        lastShowAt = Date()
        panel?.close()

        let w: CGFloat = 380
        let pad: CGFloat = 20
        let innerW = w - pad * 2
        let btnH: CGFloat = 30

        let accent = crisis ? NSColor(calibratedRed: 1, green: 0.33, blue: 0.44, alpha: 1)
                            : NSColor(calibratedRed: 0.18, green: 0.89, blue: 0.69, alpha: 1)

        // Build labels first and measure them so the window is sized to fit.
        let head = NSTextField(wrappingLabelWithString: title)
        head.font = .systemFont(ofSize: 15, weight: .bold)
        head.textColor = accent
        head.preferredMaxLayoutWidth = innerW
        let hH = head.sizeThatFits(NSSize(width: innerW, height: .greatestFiniteMagnitude)).height

        let body = NSTextField(wrappingLabelWithString: message)
        body.font = .systemFont(ofSize: 13)
        body.textColor = NSColor(white: 0.86, alpha: 1)
        body.preferredMaxLayoutWidth = innerW
        let bH = body.sizeThatFits(NSSize(width: innerW, height: .greatestFiniteMagnitude)).height

        let total = pad + hH + 12 + bH + 16 + btnH + 8 + btnH + pad

        // Lay out bottom-up (AppKit y grows upward). Bottom row: snooze buttons.
        let third = (innerW - 16) / 3
        let snooze1 = NSButton(title: "Ignore 1h", target: self, action: #selector(ignore1h))
        snooze1.bezelStyle = .rounded
        snooze1.frame = NSRect(x: pad, y: pad, width: third, height: btnH)

        let snooze2 = NSButton(title: "Ignore 2h", target: self, action: #selector(ignore2h))
        snooze2.bezelStyle = .rounded
        snooze2.frame = NSRect(x: pad + third + 8, y: pad, width: third, height: btnH)

        let dismiss = NSButton(title: "Dismiss", target: self, action: #selector(close))
        dismiss.bezelStyle = .rounded
        dismiss.frame = NSRect(x: pad + (third + 8) * 2, y: pad, width: third, height: btnH)

        // Main action row above the snooze row.
        let talk = NSButton(title: crisis ? "Get support" : "Talk it through", target: self, action: #selector(openChat))
        talk.bezelStyle = .rounded
        talk.frame = NSRect(x: pad, y: pad + btnH + 8, width: innerW, height: btnH)
        talk.keyEquivalent = "\r"

        body.frame = NSRect(x: pad, y: pad + btnH + 8 + btnH + 16, width: innerW, height: bH)
        head.frame = NSRect(x: pad, y: pad + btnH + 8 + btnH + 16 + bH + 12, width: innerW, height: hH)

        let content = NSView(frame: NSRect(x: 0, y: 0, width: w, height: total))
        content.wantsLayer = true
        content.layer?.backgroundColor = NSColor(calibratedRed: 0.05, green: 0.07, blue: 0.08, alpha: 1).cgColor
        content.layer?.cornerRadius = 16
        content.layer?.borderWidth = 1
        content.layer?.borderColor = NSColor(white: 1, alpha: 0.08).cgColor
        content.addSubview(head); content.addSubview(body)
        content.addSubview(talk); content.addSubview(dismiss)
        content.addSubview(snooze1); content.addSubview(snooze2)

        let panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: w, height: total),
                            styleMask: [.borderless, .nonactivatingPanel],
                            backing: .buffered, defer: false)
        panel.isFloatingPanel = true
        panel.level = .screenSaver                  // above almost everything
        // Show over full-screen apps and on every Space (Google Docs / browser fullscreen).
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = true
        panel.hidesOnDeactivate = false
        panel.contentView = content

        if let screen = NSScreen.main {
            let f = screen.visibleFrame
            panel.setFrameOrigin(NSPoint(x: f.maxX - w - 22, y: f.maxY - total - 22))
        }
        panel.orderFrontRegardless()
        self.panel = panel
        NSSound(named: "Glass")?.play()
        shLog("POPUP shown crisis=\(crisis)")
    }

    @objc private func openChat() {
        // Always open the HOSTED app for the human-facing chat — a localhost
        // page means nothing to whoever is sitting at the popup. Detection
        // still talks to Config.backend (local when available, private).
        if let url = URL(string: Config.hostedBackend + "/chat") { NSWorkspace.shared.open(url) }
        close()
    }
    @objc private func ignore1h() { Snooze.set(hours: 1); close() }
    @objc private func ignore2h() { Snooze.set(hours: 2); close() }
    @objc private func close() { panel?.close(); panel = nil; currentMessage = "" }
}

// MARK: - Monitor
final class Monitor {
    private var timer: Timer?
    private var lastScanned = ""
    private var quietUntil = Date.distantPast
    private var crisisQuietUntil = Date.distantPast   // crisis re-pop limiter
    private(set) var lastApp = ""

    // "Wait till the user sends" — don't react mid-typing. We only scan text
    // once it has STOPPED changing (the user paused or sent), not on every
    // keystroke. `pending` holds the last-seen text and when it first appeared.
    private var pending = ""
    private var pendingSince = Date.distantPast
    private let settleSeconds: TimeInterval = 1.1   // pause that counts as "done"

    func start() {
        timer = Timer.scheduledTimer(withTimeInterval: Config.pollSeconds, repeats: true) { [weak self] _ in
            self?.tick()
        }
    }

    private func tick() {
        guard !Snooze.isActive else { return }
        guard let text = AXReader.focusedText() else { return }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count >= Config.minChars else { pending = ""; return }

        // Still typing? Text changed since last tick → reset the settle timer.
        if trimmed != pending {
            pending = trimmed
            pendingSince = Date()
            return
        }
        // Text unchanged but hasn't settled long enough yet → keep waiting.
        guard Date().timeIntervalSince(pendingSince) >= settleSeconds else { return }
        // Settled, and not already scanned → this is a completed message.
        guard trimmed != lastScanned else { return }
        lastScanned = trimmed
        lastApp = NSWorkspace.shared.frontmostApplication?.localizedName ?? "an app"

        Backend.monitor(trimmed) { [weak self] res in
            guard let self, let res else { return }
            let l1 = res["l1"] as? [String: Any] ?? [:]
            let action = res["action"] as? [String: Any] ?? [:]
            let gating = res["gating"] as? [String: Any] ?? [:]
            let judgment = res["judgment"] as? [String: Any] ?? [:]

            _ = action; _ = gating
            let tier3 = l1["tier3"] as? Bool ?? false
            // The backend read the CONTEXT (joke vs genuine) and set the popup
            // policy: urgent = crisis/high · gentle = moderate · none = low
            // (still logged for trends — just no interruption) or nothing.
            let surface = judgment["surface"] as? String ?? "none"

            let quiet = Date() < self.quietUntil
            if surface == "urgent" || tier3 {
                guard Date() >= self.crisisQuietUntil else { return }
                self.crisisQuietUntil = Date().addingTimeInterval(30)
                self.fire(crisis: true)
            } else if surface == "gentle" && !quiet {
                self.fire(crisis: false)
            }
        }
    }

    private func fire(crisis: Bool) {
        quietUntil = Date().addingTimeInterval(Config.cooldownSeconds)
        if crisis {
            Popup.shared.show(
                title: "SilentHelp — let’s loop someone in",
                message: "Something you just wrote suggests you’re in real pain. You don’t have to carry it alone. If it’s urgent, call or text 988.",
                crisis: true)
        } else {
            Popup.shared.show(
                title: "SilentHelp noticed something",
                message: "The last little while has leaned harder than your usual. Want to take a breath or talk it through?",
                crisis: false)
        }
    }
}

// MARK: - ScreenReader (OCR — works in ANY app/browser, incl. Google Docs)
//
// Captures the screen on-device (ScreenCaptureKit), runs Apple's Vision text
// recognition over it, and feeds the recognized text to the detection backend.
// Because it reads pixels, it sees text that the Accessibility API can't —
// canvas editors like Google Docs, Notion, Figma, and any browser. The image
// and text never leave the machine (only the local backend is contacted).
@available(macOS 14.0, *)
final class ScreenReader {
    private var timer: Timer?
    private var lastText = ""
    private var quietUntil = Date.distantPast
    private var busy = false
    // Re-fire guard: the SAME detected phrase can't pop again for 2 minutes —
    // crisis text sitting on screen must not re-pop on every OCR pass.
    private var lastPopPhrase = ""
    private var lastPopAt = Date.distantPast

    func start() {
        timer = Timer.scheduledTimer(withTimeInterval: Config.ocrSeconds, repeats: true) { [weak self] _ in
            guard let self, !self.busy else { return }
            Task { await self.tick() }
        }
    }

    private func tick() async {
        guard !Snooze.isActive else { return }
        // No Screen Recording permission → do NOT attempt capture. Every failed
        // attempt makes macOS re-show the permission dialog — that's the
        // "asking again and again" spam. We wait silently; the menu-bar icon
        // shows the missing permission instead.
        guard CGPreflightScreenCaptureAccess() else { return }
        // NOTE: we keep scanning during the post-popup cooldown — handle() only
        // MUTES non-crisis popups in that window. A crisis always breaks through.
        // Never OCR our own agent's UI.
        if NSWorkspace.shared.frontmostApplication?.bundleIdentifier == "com.silenthelp.agent" { return }
        busy = true
        defer { busy = false }
        do {
            let content = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: true)
            let cfg = SCStreamConfiguration()
            cfg.showsCursor = false
            var image: CGImage
            // Prefer the FRONTMOST WINDOW (the app you're actually typing in, e.g.
            // the Google Doc) — far less noise than the whole screen.
            if let pid = NSWorkspace.shared.frontmostApplication?.processIdentifier,
               let win = content.windows.first(where: {
                   $0.owningApplication?.processID == pid && $0.isOnScreen
                   && $0.frame.width > 200 && $0.frame.height > 200 }) {
                // Window frames are in POINTS — capture at 2x (Retina) so 12pt
                // text is ~24px tall and OCR can actually read it.
                let sc = min(2.0, Config.ocrMaxDim / max(win.frame.width, win.frame.height))
                cfg.width = max(1, Int(win.frame.width * sc))
                cfg.height = max(1, Int(win.frame.height * sc))
                let filter = SCContentFilter(desktopIndependentWindow: win)
                image = try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: cfg)
            } else if let display = content.displays.first {
                let sc = min(2.0, Config.ocrMaxDim / CGFloat(max(display.width, display.height)))
                cfg.width = max(1, Int(CGFloat(display.width) * sc))
                cfg.height = max(1, Int(CGFloat(display.height) * sc))
                // Exclude our OWN windows — the popup shows the detected phrase
                // and must never be read back as a fresh detection.
                let mine = content.windows.filter { $0.owningApplication?.processID == ProcessInfo.processInfo.processIdentifier }
                let filter = SCContentFilter(display: display, excludingWindows: mine)
                image = try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: cfg)
            } else { return }
            shLog("OCR captured \(image.width)x\(image.height)")
            recognize(image)
        } catch {
            shLog("OCR capture FAILED (likely Screen Recording not granted): \(error.localizedDescription)")
        }
    }

    private func recognize(_ cgImage: CGImage) {
        let request = VNRecognizeTextRequest { [weak self] req, _ in
            guard let self,
                  let results = req.results as? [VNRecognizedTextObservation] else { return }
            let text = results.compactMap { $0.topCandidates(1).first?.string }.joined(separator: " ")
            self.handle(text)
        }
        request.recognitionLevel = .accurate   // reads normal document text reliably
        request.usesLanguageCorrection = false
        request.recognitionLanguages = ["en-US"]
        request.minimumTextHeight = 0.006   // don't skip regular-size text
        let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
        try? handler.perform([request])
    }

    private func handle(_ raw: String) {
        var text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if text.count > 4000 { text = String(text.prefix(4000)) }
        guard text.count >= 14, text != lastText else { return }
        lastText = text

        // Don't scan our OWN web app's screen — the dashboard/chat contain the
        // very phrases we detect, which caused popup feedback loops that ate
        // the cooldown and made real apps look "not detected".
        if text.contains("SilentHelp") &&
           (text.contains("Coping Chat") || text.contains("Mental Battery")
            || text.contains("Surface conditions") || text.contains("Moments")) {
            return
        }

        // Two-stage detection with CONTEXT:
        //   1. Instant local keyword scan finds candidates (~15ms).
        //   2. Explicit tier-3 crisis pops immediately. Anything softer goes to
        //      the semantic layer, which reads intent — "jump on a trampoline"
        //      and "this is killing me 😂" die there; real distress comes back
        //      as gentle/urgent.
        Backend.scan(text) { [weak self] res in
            guard let self, let res else { return }
            let tier3 = res["tier3"] as? Bool ?? false
            let level = res["level"] as? Int ?? 0
            guard level >= 1 else { return }

            // Pull the exact phrase that matched, to show in the popup.
            //
            // Whole-screen OCR routinely matches several phrases at once (a
            // crisis line in one window, everyday stress in another). `hits` is
            // ordered by database, not severity, so hits.first can be a level-1
            // phrase even when tier-3 fired — which would tell someone we
            // detected a crisis and then quote unrelated text at them. When
            // tier-3 is what triggered this popup, quote the tier-3 hit.
            let hits = res["hits"] as? [[String: Any]] ?? []
            let tier3Phrase = hits.first { ($0["tier"] as? String) == "3" }?["phrase"] as? String
            let phrase = (tier3 ? (tier3Phrase ?? hits.first?["phrase"] as? String)
                                : hits.first?["phrase"] as? String) ?? ""

            // Same phrase still on screen? One popup, not one per OCR pass.
            if phrase == self.lastPopPhrase && Date() < self.lastPopAt.addingTimeInterval(40) { return }

            if !tier3 {
                // Not explicit crisis — ask the semantic layer what it MEANS.
                if Date() < self.quietUntil { return }
                Backend.monitor(text) { [weak self] mres in
                    guard let self, let mres else { return }
                    let judgment = mres["judgment"] as? [String: Any] ?? [:]
                    let surface = judgment["surface"] as? String ?? "none"
                    let riskLevel = judgment["risk_level"] as? String ?? "none"
                    guard surface != "none" else {
                        shLog("OCR candidate (\(phrase)) judged \(riskLevel) in context → no popup")
                        return
                    }
                    self.lastPopPhrase = phrase
                    self.lastPopAt = Date()
                    self.quietUntil = Date().addingTimeInterval(Config.ocrCooldown)
                    let crisis = surface == "urgent"
                    let title = crisis ? "SilentHelp — let's loop someone in"
                                       : "SilentHelp — a quiet check-in"
                    var message = crisis
                        ? "What you're writing sounds really heavy. You don't have to carry it alone. If it's urgent, call or text 988."
                        : "Looks like a lot on you right now. Want to take a breath together?"
                    if !phrase.isEmpty { message += "\n\nNoticed: \u{201C}\(phrase)\u{201D}" }
                    shLog("OCR \(riskLevel) confirmed in context (\(phrase)) → popup (crisis=\(crisis))")
                    Popup.shared.show(title: title, message: message, crisis: crisis)
                }
                return
            }

            // Explicit tier-3 crisis: no waiting, no second-guessing.
            self.lastPopPhrase = phrase
            self.lastPopAt = Date()
            self.quietUntil = Date().addingTimeInterval(Config.ocrCooldown)

            var message = "Something you wrote matched a crisis signal. You don't have to carry it alone. If it's urgent, call or text 988."
            if !phrase.isEmpty {
                message += "\n\nDetected: \u{201C}\(phrase)\u{201D}"
            }
            shLog("OCR tier-3 crisis (\(phrase)) → popup")
            Popup.shared.show(title: "SilentHelp — let's loop someone in", message: message, crisis: true)
        }
    }
}

// MARK: - Behavioral (Layer 3 — rhythm only, reads NO text)
final class Behavioral {
    private var keys = 0, backs = 0, switches = 0
    private var lastSwitch = Date(), longest: TimeInterval = 0
    private var lateMs: TimeInterval = 0, lastTick = Date()
    private let started = Date()
    private var keyMonitor: Any?

    func start() {
        // App switches = the "tab switching" signal at the OS level.
        NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.didActivateApplicationNotification, object: nil, queue: .main
        ) { [weak self] _ in
            guard let self else { return }
            self.switches += 1
            let now = Date()
            self.longest = max(self.longest, now.timeIntervalSince(self.lastSwitch))
            self.lastSwitch = now
        }
        // Keystroke rhythm: we look only at the key CODE (count + backspaces),
        // never the characters. keyCode 51 = delete, 117 = forward-delete.
        keyMonitor = NSEvent.addGlobalMonitorForEvents(matching: .keyDown) { [weak self] e in
            guard let self else { return }
            self.keys += 1
            if e.keyCode == 51 || e.keyCode == 117 { self.backs += 1 }
        }
        // Late-night accrual.
        Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in
            guard let self else { return }
            let now = Date(); let dt = now.timeIntervalSince(self.lastTick); self.lastTick = now
            let h = Calendar.current.component(.hour, from: now)
            if h >= 0 && h < 5 { self.lateMs += dt }
        }
        // Report to the backend every 45s.
        Timer.scheduledTimer(withTimeInterval: 45, repeats: true) { [weak self] _ in self?.report() }
    }

    private func report() {
        let activeMin = Date().timeIntervalSince(started) / 60.0
        let activeHr = max(activeMin / 60.0, 0.08)
        let tab = min(120.0, Double(switches) / activeHr)
        let signals: [String: Any] = [
            "tab_switches": tab,
            "interruptions": tab * 0.7,
            "avg_session_min": switches == 0 ? 50.0 : longest / 60.0,
            "backspace_rate": keys > 0 ? Double(backs) / Double(keys) : 0.0,
            "late_night_min": lateMs / 60.0,
            "active_minutes": activeMin,
        ]
        Backend.log(signals)
    }
}

// MARK: - App
final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private var statusMenuItem: NSMenuItem!
    private let monitor = Monitor()
    private let behavioral = Behavioral()
    private let screenReader = ScreenReader()
    private var lastUrgent = false
    private var lastGentle = false
    private var gatingBaselined = false   // first poll sets state, never pops
    private var monitoringStarted = false
    private var screenStarted = false

    /// The SilentHelp emblem sized for the menu bar. Loaded from the app
    /// bundle's Resources (menubar.png / @2x / @3x). isTemplate=false so it
    /// keeps the logo's colors instead of being tinted to monochrome.
    static func menubarEmblem() -> NSImage? {
        let name = "menubar"
        var img: NSImage?
        if let path = Bundle.main.path(forResource: name, ofType: "png") {
            img = NSImage(contentsOfFile: path)
        }
        if img == nil { img = NSImage(named: name) }
        img?.size = NSSize(width: 20, height: 20)   // fits the ~22pt menu bar
        img?.isTemplate = false
        return img
    }

    /// Repaint the small status dot next to the emblem + the menu's status line.
    func setStatus() {
        let trusted = AXIsProcessTrusted()
        let screenOK = CGPreflightScreenCaptureAccess()
        let dot: String
        let line: String
        if Snooze.isActive {
            dot = " 💤"; line = "SilentHelp — paused"
        } else if !trusted {
            dot = " 🔴"; line = "⚠ Grant Accessibility in System Settings"
        } else if !screenOK {
            dot = " 🟡"; line = "⚠ Grant Screen Recording in System Settings"
        } else {
            dot = " 🟢"; line = "SilentHelp — watching over you"
        }
        statusItem?.button?.title = dot
        statusMenuItem?.title = line
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory) // menu-bar only, no dock icon
        resolveBackend()  // local backend if running, else the hosted app
        shLog("LAUNCH path=\(Bundle.main.bundlePath) ax=\(AXIsProcessTrusted()) screen=\(CGPreflightScreenCaptureAccess())")

        // Gatekeeper "app translocation": launched from a randomized quarantine
        // path (e.g. straight out of the Downloads zip). Permissions can NEVER
        // stick to that path — tell the user how to fix it instead of failing
        // silently forever.
        if Bundle.main.bundlePath.contains("/AppTranslocation/") {
            shLog("TRANSLOCATED — asking user to move to /Applications")
            let a = NSAlert()
            a.messageText = "Move SilentHelp Agent to Applications first"
            a.informativeText = "macOS is running this copy from a temporary location, so permissions can't be saved.\n\n1. Quit this app.\n2. Drag SilentHelpAgent.app into the Applications folder (use Finder).\n3. Open it from Applications.\n\nThen Accessibility and Screen Recording will stick."
            a.addButton(withTitle: "Quit")
            a.runModal()
            NSApp.terminate(nil)
            return
        }

        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        // The SilentHelp emblem in the menu bar, followed by a small colored
        // status dot (green=watching, yellow=needs Screen Recording, red=needs
        // Accessibility, 💤=snoozed). The dot keeps the at-a-glance status the
        // old text icon gave, since the emblem itself can't color-tint.
        if let btn = statusItem.button {
            btn.image = Self.menubarEmblem()
            btn.imagePosition = .imageLeft
        }
        setStatus()  // paints the status dot for the first time
        let menu = NSMenu()
        statusMenuItem = NSMenuItem(title: "SilentHelp — monitoring", action: nil, keyEquivalent: "")
        menu.addItem(statusMenuItem)
        menu.addItem(.separator())
        menu.addItem(NSMenuItem(title: "Send test alert", action: #selector(testAlert), keyEquivalent: "t"))
        menu.addItem(NSMenuItem(title: "Open dashboard", action: #selector(openDash), keyEquivalent: "d"))
        menu.addItem(NSMenuItem(title: "Re-check permission", action: #selector(checkPerm), keyEquivalent: "p"))
        menu.addItem(.separator())
        menu.addItem(NSMenuItem(title: "Ignore for 1 hour", action: #selector(snooze1h), keyEquivalent: "1"))
        menu.addItem(NSMenuItem(title: "Ignore for 2 hours", action: #selector(snooze2h), keyEquivalent: "2"))
        menu.addItem(NSMenuItem(title: "Resume monitoring", action: #selector(resumeNow), keyEquivalent: "r"))
        menu.addItem(.separator())
        menu.addItem(NSMenuItem(title: "Quit", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))
        statusItem.menu = menu

        // The gating poll runs ALWAYS — even before Accessibility is granted — so
        // the running web app (or a demo moment) can surface the native popup.
        startGatingPoll()

        // Prompt only when actually needed — a granted user is never re-asked.
        // The trust poll flips the icon green the moment permission is toggled.
        let axTrusted = AXIsProcessTrusted()
        if !axTrusted { _ = requestAccessibility() }
        startTrustPoll()
        startScreen()                         // OCR screen reading (Screen Recording perm)
        // The explainer alert shows at most once per install, not every launch.
        let defaults = UserDefaults.standard
        if !axTrusted && !defaults.bool(forKey: "sh.axAlertShown") {
            defaults.set(true, forKey: "sh.axAlertShown")
            notifyPermission()
        }
    }

    private func startScreen() {
        if screenStarted { return }
        screenStarted = true
        // Only ask if not already granted — never re-prompt a granted user.
        if !CGPreflightScreenCaptureAccess() {
            CGRequestScreenCaptureAccess()    // prompts for Screen Recording once
        }
        screenReader.start()                  // ticks fail gracefully until granted
    }

    private func startTrustPoll() {
        setStatus()
        Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in
            guard let self else { return }
            let trusted = AXIsProcessTrusted()
            self.setStatus()  // emblem stays; the status dot + menu line update
            if trusted && !self.monitoringStarted {
                self.monitoringStarted = true
                self.monitor.start()
                self.behavioral.start()
                shLog("AX GRANTED → focused-field + behavioral monitoring started")
            }
        }
    }

    @objc private func testAlert() {
        Popup.shared.show(
            title: "SilentHelp is watching over you",
            message: "If you can read this, the popup works. Real check-ins appear here the moment something surfaces in what you're writing.",
            crisis: false)
    }

    private func startGatingPoll() {
        Timer.scheduledTimer(withTimeInterval: 8, repeats: true) { [weak self] _ in
            guard !Snooze.isActive else { return }
            Backend.get("/api/gating") { g in
                guard let self, let g else { return }
                let urgent = g["urgent"] as? Bool ?? false
                let gentle = g["gentle"] as? Bool ?? false
                // First poll: adopt the current state WITHOUT popping — a gate
                // left "urgent" from earlier must not fire on every launch.
                if !self.gatingBaselined {
                    self.gatingBaselined = true
                    self.lastUrgent = urgent
                    self.lastGentle = gentle
                    return
                }
                if urgent && !self.lastUrgent {
                    Popup.shared.show(
                        title: "SilentHelp — let's loop someone in",
                        message: "A pattern crossed a line we don't ignore. You don't have to carry it alone. If it's urgent, call or text 988.",
                        crisis: true)
                } else if gentle && !self.lastGentle {
                    Popup.shared.show(
                        title: "SilentHelp noticed something",
                        message: "The last little while has leaned harder than your usual. Want to take a breath or talk it through?",
                        crisis: false)
                }
                self.lastUrgent = urgent
                self.lastGentle = gentle
            }
        }
    }

    @discardableResult
    private func requestAccessibility() -> Bool {
        let opt = kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String
        return AXIsProcessTrustedWithOptions([opt: true] as CFDictionary)
    }

    private func notifyPermission() {
        let a = NSAlert()
        a.messageText = "Accessibility permission needed"
        a.informativeText = "Grant SilentHelp Agent access in System Settings ▸ Privacy & Security ▸ Accessibility, then quit and relaunch."
        a.addButton(withTitle: "Open Settings")
        a.addButton(withTitle: "Later")
        if a.runModal() == .alertFirstButtonReturn,
           let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility") {
            NSWorkspace.shared.open(url)
        }
    }

    @objc private func openDash() {
        if let url = URL(string: Config.backend + "/") { NSWorkspace.shared.open(url) }
    }
    @objc private func snooze1h() { Snooze.set(hours: 1) }
    @objc private func snooze2h() { Snooze.set(hours: 2) }
    @objc private func resumeNow() { Snooze.clear() }
    @objc private func checkPerm() {
        if requestAccessibility() && !monitoringStarted {
            monitoringStarted = true
            setStatus()
            monitor.start(); behavioral.start()
        }
        // Screen Recording missing? Take the user straight to the toggle.
        if !CGPreflightScreenCaptureAccess(),
           let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture") {
            NSWorkspace.shared.open(url)
        }
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
