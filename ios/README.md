# Tapinion for iPad and iPhone

Native app (Swift, WKWebView) with the same behaviour as the Android app:

- finds Tapinion in the Wi-Fi (Bonjour, `_tapinion._tcp`), by QR code or by address;
- shows the kiosk of the computer and keeps every event opened in it for offline use;
- runs the kiosk without the computer and sends the ratings back once the computer is reachable
  again, also at a new address;
- a running kiosk is left with the PIN only; after closing the app it returns into the kiosk.

The offline pages (`android/app/src/main/assets/offline`) and the logo are shared with the
Android app. `Tapinion/bridge.js` provides their `window.TapinionApp` interface in WKWebView.

## Locking the device

iOS does not let an app block the home gesture by itself. The kiosk is locked with
**Guided Access**: Settings → Accessibility → Guided Access → on, set a passcode, then press the
side button (or home button) three times in the running kiosk. On supervised devices (Apple
Configurator or MDM) that allow Tapinion for autonomous single app mode, the app starts and ends
the lock itself with the kiosk PIN.

## Building

Needs a Mac with Xcode 16 and [XcodeGen](https://github.com/yonaskolb/XcodeGen):

```sh
brew install xcodegen
cd ios && xcodegen && open Tapinion.xcodeproj
```

The CI (`.github/workflows/ios.yml`) builds the app on GitHub's macOS runners, runs the kiosk
round trip in the iPad simulator against a real Tapinion (online, offline, sync back) and
produces an unsigned `tapinion-ios-*-unsigned.ipa` (artifact `ios`).

## Installing without the App Store

An iPhone or iPad only runs signed apps. Ways to sign the unsigned `.ipa`:

| Way | Cost | Valid for |
| --- | --- | --- |
| [Sideloadly](https://sideloadly.io) (Windows or Mac) with an Apple ID | free | 7 days, then sign again |
| Xcode on a Mac with an Apple ID ("Personal Team") | free | 7 days |
| Apple Developer Program: TestFlight, ad hoc or App Store | 99 € per year | 90 days (TestFlight), 1 year (ad hoc) |

With a free Apple ID (Sideloadly):

1. Install iTunes (Windows) and Sideloadly; connect the device by USB and trust the computer.
2. Drag the `.ipa` into Sideloadly, enter the Apple ID, Start.
3. On the device: Settings → Privacy & Security → Developer Mode → on (restarts the device).
4. Settings → General → VPN & Device Management → trust the developer profile of the Apple ID.
5. Open Tapinion and allow access to the local network.

Free signing allows at most three such apps per device and expires after seven days; the app
data (offline events and ratings) stays when the app is signed again and reinstalled.
