; Only generated metadata contains version/product identity.
#include "..\..\build\packaging\installer-defines.iss"

[Setup]
AppId={{#StableAppId}
AppName={#ProductName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#ProjectUrl}
AppCopyright={#AppCopyright}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#ProductName}
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
UsePreviousAppDir=yes
UsePreviousTasks=yes
DisableProgramGroupPage=yes
OutputDir=..\..\dist\artifacts
OutputBaseFilename={#SetupBaseName}
SetupIconFile=..\..\assets\app.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#ProductName}
VersionInfoVersion={#NumericVersion}
VersionInfoTextVersion={#AppVersion}
VersionInfoProductName={#ProductName}
VersionInfoProductVersion={#NumericVersion}
VersionInfoProductTextVersion={#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\..\dist\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#ProductName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#ProductName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#ProductName}"; Flags: nowait postinstall skipifsilent runasoriginaluser

; Deliberately no [UninstallDelete]: only files installed by Setup are removed.
; Per-user AppState/templates/logs and customer exports are never installed here.
