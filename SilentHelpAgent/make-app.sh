#!/bin/bash
# Build SilentHelp Agent into a proper .app bundle.
# A stable bundle identity makes the macOS Accessibility permission "stick"
# (a raw `swift run` binary changes path on rebuild and loses the grant).
set -e
cd "$(dirname "$0")"

echo "Building release…"
swift build -c release

APP="SilentHelpAgent.app"
BIN=".build/release/SilentHelpAgent"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/SilentHelpAgent"

# Bundle the SilentHelp emblem: the Finder/Dock app icon (.icns) and the
# menu-bar images (menubar.png / @2x / @3x, loaded at runtime).
[ -f AppIcon.icns ] && cp AppIcon.icns "$APP/Contents/Resources/AppIcon.icns"
for f in menubar.png menubar@2x.png menubar@3x.png; do
  [ -f "$f" ] && cp "$f" "$APP/Contents/Resources/$f"
done

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>SilentHelp Agent</string>
  <key>CFBundleDisplayName</key><string>SilentHelp Agent</string>
  <key>CFBundleIdentifier</key><string>com.silenthelp.agent</string>
  <key>CFBundleVersion</key><string>0.1</string>
  <key>CFBundleShortVersionString</key><string>0.1</string>
  <key>CFBundleExecutable</key><string>SilentHelpAgent</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSUIElement</key><true/>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>NSHumanReadableCopyright</key><string>SilentHelp prototype</string>
  <!-- Registers this app as the handler for silenthelp:// links, so the
       web app's /pair-agent page can hand back a pairing token with a
       single click instead of a copy-pasted code (see DeviceAuth in
       main.swift). -->
  <key>CFBundleURLTypes</key>
  <array>
    <dict>
      <key>CFBundleURLName</key><string>com.silenthelp.agent.pairing</string>
      <key>CFBundleURLSchemes</key>
      <array><string>silenthelp</string></array>
    </dict>
  </array>
</dict>
</plist>
PLIST

# Sign with the STABLE "SilentHelp Dev" identity so macOS permission grants
# (Accessibility / Screen Recording) survive rebuilds. Ad-hoc signatures change
# with every build — that's what made macOS re-ask for permissions each update.
if security find-identity -v -p codesigning 2>/dev/null | grep -q "SilentHelp Dev"; then
  codesign --force --deep --sign "SilentHelp Dev" "$APP" && echo "Signed with SilentHelp Dev (stable identity)"
else
  codesign --force --deep --sign - "$APP" 2>/dev/null || true
  echo "WARNING: ad-hoc signed — permissions will reset on next rebuild"
fi

# Package a downloadable zip for the website's "Download for Mac" button.
DIST="../dist"
mkdir -p "$DIST"
rm -f "$DIST/SilentHelpAgent.zip"
ditto -c -k --keepParent "$APP" "$DIST/SilentHelpAgent.zip"
echo "Packaged $DIST/SilentHelpAgent.zip"

echo "Built $APP"
echo "Run it:  open $APP    (or double-click in Finder)"
echo "First launch: grant Accessibility in System Settings, then relaunch."
