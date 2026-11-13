; Tapinion setup for Windows (Inno Setup 6).
;   iscc /DAppVersion=1.0.0 packaging\windows\tapinion.iss
; Expects the PyInstaller program folder in dist\Tapinion (see packaging\pyinstaller).

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{8C1B7E52-6F4A-4C3B-9E7D-2A5F0B3C9D41}
AppName=Tapinion
AppVersion={#AppVersion}
AppVerName=Tapinion {#AppVersion}
AppPublisher=mw-research
AppPublisherURL=https://github.com/mw-research/tapinion
AppSupportURL=https://github.com/mw-research/tapinion/issues
DefaultDirName={autopf}\Tapinion
DisableProgramGroupPage=yes
DisableDirPage=auto
; Administrator rights allow the firewall rule for tablets; "just for me" works without them.
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist
OutputBaseFilename=Tapinion-Setup-{#AppVersion}
SetupIconFile=..\pyinstaller\tapinion.ico
UninstallDisplayIcon={app}\Tapinion.exe
UninstallDisplayName=Tapinion
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
CloseApplications=yes
ShowLanguageDialog=auto

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "de"; MessagesFile: "compiler:Languages\German.isl"

[CustomMessages]
en.Firewall=Allow tablets in the network to connect (Windows Firewall, private and company networks)
de.Firewall=Tablets im Netzwerk verbinden lassen (Windows-Firewall, private und Firmennetzwerke)
en.Autostart=Start Tapinion automatically when I log in
de.Autostart=Tapinion beim Anmelden automatisch starten
en.Network=Network:
de.Network=Netzwerk:
en.DeleteData=Also delete all Tapinion data (events, ratings, users, settings)?%n%nChoose No to keep it for a later installation.
de.DeleteData=Auch alle Tapinion-Daten löschen (Veranstaltungen, Bewertungen, Benutzer, Einstellungen)?%n%n„Nein“ behält sie für eine spätere Installation.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "{cm:Autostart}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "firewall"; Description: "{cm:Firewall}"; GroupDescription: "{cm:Network}"; Check: IsAdminInstallMode

[Files]
Source: "..\..\dist\Tapinion\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Tapinion"; Filename: "{app}\Tapinion.exe"
Name: "{autodesktop}\Tapinion"; Filename: "{app}\Tapinion.exe"; Tasks: desktopicon
Name: "{userstartup}\Tapinion"; Filename: "{app}\Tapinion.exe"; Tasks: autostart

[Run]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Tapinion"""; Flags: runhidden; Tasks: firewall
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""Tapinion"" dir=in action=allow program=""{app}\Tapinion.exe"" enable=yes profile=private,domain"; Flags: runhidden; Tasks: firewall
Filename: "{app}\Tapinion.exe"; Description: "{cm:LaunchProgram,Tapinion}"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Tapinion"""; Flags: runhidden; RunOnceId: "RemoveFirewallRule"
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM Tapinion.exe"; Flags: runhidden; RunOnceId: "StopTapinion"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent then
    if MsgBox(CustomMessage('DeleteData'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      DelTree(ExpandConstant('{userappdata}\Tapinion'), True, True, True);
end;
