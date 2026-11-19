// Copyright (C) 2026 Markus Wilhelm, mw-research
// SPDX-License-Identifier: AGPL-3.0-or-later
import XCTest

/// The kiosk round trip in the simulator, run by the CI in three steps (see .github/workflows/ios.yml):
/// A with Tapinion running, B after it was stopped, C after it was started again.
/// TAPINION_URL is the kiosk address of the test event (PIN 2468), SCREENSHOT_DIR collects screenshots.
final class KioskFlowTests: XCTestCase {
    private let env = ProcessInfo.processInfo.environment
    private var app: XCUIApplication!

    override func setUp() {
        continueAfterFailure = false
    }

    private func launch(_ extra: [String] = []) {
        app = XCUIApplication()
        app.launchArguments = ["-AppleLanguages", "(de)", "-AppleLocale", "de_DE"] + extra
        app.launch()
    }

    private func shot(_ name: String) {
        let s = XCUIScreen.main.screenshot()
        let a = XCTAttachment(screenshot: s)
        a.name = name
        a.lifetime = .keepAlways
        add(a)
        if let dir = env["SCREENSHOT_DIR"] {
            try? s.pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent("\(name).png"))
        }
    }

    private func webButton(_ label: String) -> XCUIElement {
        app.webViews.buttons[label].firstMatch
    }

    private func enterPin() {
        for k in ["2", "4", "6", "8", "OK"] {
            let b = webButton(k)
            XCTAssertTrue(b.waitForExistence(timeout: 10), "PIN key \(k)")
            b.tap()
        }
    }

    private func smiley() -> XCUIElement {
        webButton("Zufrieden")
    }

    func testA_Online() throws {
        let url = try XCTUnwrap(env["TAPINION_URL"], "TAPINION_URL")
        launch(["-reset", "-connect", url])
        XCTAssertTrue(webButton("OK").waitForExistence(timeout: 30), "PIN page of the kiosk")
        XCTAssertTrue(app.buttons["overview"].exists, "the PIN page can still be left")
        shot("01-pin")
        enterPin()
        XCTAssertTrue(smiley().waitForExistence(timeout: 15), "voting page")
        XCTAssertTrue(app.staticTexts["Für offline gespeichert"].waitForExistence(timeout: 15), "kept for offline use")
        shot("02-kiosk-running")
        XCTAssertFalse(app.buttons["overview"].exists, "a running kiosk has no way out but the PIN")
        smiley().tap()
        XCTAssertTrue(app.webViews.staticTexts["Vielen Dank für Ihr Feedback!"].waitForExistence(timeout: 10), "thanks")
        shot("03-thanks")

        // a restart returns into the running kiosk, without the PIN
        app.terminate()
        launch()
        XCTAssertTrue(smiley().waitForExistence(timeout: 30), "kiosk again after a restart")
        XCTAssertFalse(app.buttons["overview"].exists)
        shot("04-after-restart")
    }

    func testB_Offline() throws {
        launch()
        // computer away: the running kiosk continues from the device
        XCTAssertTrue(smiley().waitForExistence(timeout: 45), "offline kiosk")
        shot("05-offline-kiosk")
        smiley().tap()
        shot("06-offline-thanks")
        let exit = webButton("exit")
        XCTAssertTrue(exit.waitForExistence(timeout: 10), "exit button")
        exit.tap()
        enterPin()
        XCTAssertTrue(app.staticTexts["OFFLINE VERFÜGBAR"].waitForExistence(timeout: 15), "overview after the PIN")
        let status = app.staticTexts.containing(NSPredicate(format: "label CONTAINS '1 Bewertungen warten'")).firstMatch
        XCTAssertTrue(status.waitForExistence(timeout: 5), "one rating waits")
        shot("07-overview-pending")
    }

    func testC_Sync() throws {
        launch()
        let overview = app.buttons["overview"]
        XCTAssertTrue(overview.waitForExistence(timeout: 30), "PIN page of the kiosk (not running any more)")
        overview.tap()
        XCTAssertTrue(app.staticTexts["OFFLINE VERFÜGBAR"].waitForExistence(timeout: 10))
        app.buttons["sync"].tap()
        let done = app.staticTexts.containing(NSPredicate(format: "label CONTAINS 'alles übertragen'")).firstMatch
        XCTAssertTrue(done.waitForExistence(timeout: 30), "rating transferred")
        shot("08-synced")
    }
}
