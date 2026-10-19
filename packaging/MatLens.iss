; Smoke builds use a separate identity and shortcut folders, never the real install.
#ifndef SmokeRoot
  #define ProductId "{{BD95155E-A346-444B-927A-567D0E96AA69}"
#else
  #define ProductId "{{C3F07250-3FA4-4D71-9CE4-DC7361CF070D}"
#endif

[Setup]
AppId={#ProductId}
AppName=MatLens
AppVersion=0.5.5
DefaultDirName={localappdata}\MatLens
DefaultGroupName=MatLens
UsePreviousAppDir=no
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableWelcomePage=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist\installer
#ifndef SmokeRoot
OutputBaseFilename=MatLens-Setup-0.5.5-x64
#else
OutputBaseFilename=MatLens-Setup-Smoke
#endif
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=no
RestartApplications=no
UninstallFilesDir={app}\uninstall
UninstallDisplayIcon={app}\app\MatLens.exe

[Languages]
Name: "chinesetraditional"; MessagesFile: "languages\ChineseTraditional.isl"

[Tasks]
Name: "desktopicon"; Description: "建立桌面捷徑"; GroupDescription: "捷徑："

[Files]
Source: "..\dist\MatLens\MatLens.exe"; DestDir: "{app}\app"; Flags: ignoreversion
Source: "..\dist\MatLens\MatLensUpdater.exe"; DestDir: "{app}\app"; Flags: ignoreversion
Source: "..\dist\MatLens\_internal\*"; DestDir: "{app}\app\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
#ifndef SmokeRoot
Name: "{userprograms}\MatLens"; Filename: "{app}\app\MatLens.exe"; WorkingDir: "{app}\app"
Name: "{userdesktop}\MatLens"; Filename: "{app}\app\MatLens.exe"; WorkingDir: "{app}\app"; Tasks: desktopicon
#else
Name: "{#SmokeRoot}\shortcuts\Programs\MatLens"; Filename: "{app}\app\MatLens.exe"; WorkingDir: "{app}\app"
Name: "{#SmokeRoot}\shortcuts\Desktop\MatLens"; Filename: "{app}\app\MatLens.exe"; WorkingDir: "{app}\app"; Tasks: desktopicon
#endif

[Run]
Filename: "{app}\app\MatLens.exe"; Description: "啟動 MatLens"; Flags: nowait postinstall skipifsilent

[Code]
function GetFileAttributes(Path: String): Cardinal;
  external 'GetFileAttributesW@kernel32.dll stdcall';

function DataRoot: String;
begin
#ifdef SmokeRoot
  Result := '{#SmokeRoot}\MatLens';
#else
  Result := ExpandConstant('{localappdata}\MatLens');
#endif
end;

function IsRunning: Boolean;
var
  Key: String;
begin
  Key := Copy(GetSHA256OfString(UTF8Encode(Lowercase(DataRoot))), 1, 24);
  Result := CheckForMutexes('Local\MatLens-' + Key);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if CompareText(RemoveBackslashUnlessRoot(ExpandConstant('{app}')), DataRoot) <> 0 then
    Result := '請使用預設的 MatLens 安裝位置。'
  else if ((GetFileAttributes(DataRoot) <> $FFFFFFFF) and
           ((GetFileAttributes(DataRoot) and $400) <> 0)) or
          ((GetFileAttributes(DataRoot + '\app') <> $FFFFFFFF) and
           ((GetFileAttributes(DataRoot + '\app') and $400) <> 0)) then
    Result := '安裝位置不可使用重新導向的資料夾。'
  else if IsRunning then
    Result := '請先儲存案件並關閉 MatLens，再繼續安裝。'
  else if FileExists(DataRoot + '\updates\install.lock') then
    Result := '線上更新尚在進行或需要復原，請先完成更新再安裝。';
end;

function InitializeUninstall: Boolean;
begin
  Result := (not IsRunning) and (not FileExists(DataRoot + '\updates\install.lock'));
  if not Result then
    MsgBox('請先儲存案件並關閉 MatLens，再解除安裝。案件與照片會保留。', mbError, MB_OK);
end;

procedure InitializeWizard;
begin
  WizardForm.DirEdit.Text := DataRoot;
  WizardForm.WelcomeLabel2.Caption :=
    '此精靈會安裝 MatLens，並建立開始功能表及選用的桌面捷徑。' + #13#10 + #13#10 +
    '統一管理位置：' + DataRoot + #13#10 +
    '程式放在 app 子資料夾；既有案件資料庫與照片會保留。' + #13#10 + #13#10 +
    '請先儲存案件並關閉舊版 MatLens，再按「下一步」。';
end;
