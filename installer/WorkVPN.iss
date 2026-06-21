#ifndef AppVersion
#define AppVersion "1.0.0"
#endif
#ifndef AppArch
#define AppArch "amd64"
#endif
#ifndef SourceExe
#define SourceExe "..\dist\WorkVPN.exe"
#endif
#ifndef AppArchMode
#define AppArchMode "x64compatible"
#endif
#ifndef OutputDir
#define OutputDir "..\release"
#endif
#ifndef OutputBaseFilename
#define OutputBaseFilename "WorkVPN-Setup-" + AppVersion + "-windows-" + AppArch
#endif

#define AppName "WorkVPN"
#define AppPublisher "WorkVPN"
#define AppExeName "WorkVPN.exe"
#define AppIdBase "WorkVPN"

[Setup]
AppId={#AppIdBase}-{#AppArch}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename={#OutputBaseFilename}
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed={#AppArchMode}
ArchitecturesInstallIn64BitMode={#AppArchMode}
PrivilegesRequired=admin
SetupIconFile=..\assets\vpn_icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
WizardStyle=modern
LanguageDetectionMethod=uilanguage
ShowLanguageDialog=yes
CloseApplications=yes
RestartIfNeededByRun=no
AlwaysRestart=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[CustomMessages]
english.CreateDesktopShortcut=Create a desktop shortcut
russian.CreateDesktopShortcut=Создать ярлык на рабочем столе
english.AdditionalIcons=Additional icons:
russian.AdditionalIcons=Дополнительные значки:
english.UninstallApp=Uninstall WorkVPN
russian.UninstallApp=Удалить WorkVPN
english.LaunchApp=Launch WorkVPN
russian.LaunchApp=Запустить WorkVPN

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopShortcut}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
Source: "{#SourceExe}"; DestDir: "{app}"; DestName: "{#AppExeName}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallApp}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent unchecked runascurrentuser

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\WorkVPN"
