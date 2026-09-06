[Setup]
AppId={{BD95155E-A346-444B-927A-567D0E96AA69}
AppName=MatLens
AppVersion=0.2.0
DefaultDirName={localappdata}\Programs\MatLens
DefaultGroupName=MatLens
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist\installer
OutputBaseFilename=MatLens-Setup-0.2.0-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
UninstallDisplayIcon={app}\MatLens.exe

[Files]
Source: "..\dist\MatLens\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\MatLens"; Filename: "{app}\MatLens.exe"
Name: "{autodesktop}\MatLens"; Filename: "{app}\MatLens.exe"

[Run]
Filename: "{app}\MatLens.exe"; Description: "Launch MatLens"; Flags: nowait postinstall skipifsilent
