; debutkit Windows 설치 프로그램 (Inno Setup 6.1 이상)
;
; python packaging/build_windows.py --installer 로 만든다(ISCC.exe가 PATH나 Program Files에 있어야 함).
; - 현재 사용자 계정에 설치, 관리자 권한 불필요
; - 시작 메뉴 바로 가기, 바탕 화면 바로 가기(선택)
; - ffmpeg는 포함하지 않음. 자동 클립을 쓸 경우 선택 작업으로 고정 빌드를 다운로드하고(SHA-256 확인)
;   설치한 debutkit.exe가 사용자 캐시 폴더에 넣는다. 연결이 없어도 프로그램 설치는 계속 진행
; - 다운로드한 ffmpeg는 다른 프로그램과 같이 쓰는 폴더에 있으므로 제거할 때 지우지 않음

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\debutkit"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif
#ifndef OutputName
  #define OutputName "debutkit-" + AppVersion + "-windows-x64-setup"
#endif
#ifndef FfmpegUrl
  #error ffmpeg 빌드 정보 없음: packaging/build_windows.py 로 만들기(/DFfmpegUrl, /DFfmpegFile, /DFfmpegSha256, /DFfmpegSize 전달)
#endif

[Setup]
AppId={{B0BD66EB-12CF-41E4-BB56-15BE91830796}
AppName=debutkit
AppVersion={#AppVersion}
AppPublisher=debutkit
AppPublisherURL=https://budongjw.github.io/debutkit/
AppSupportURL=https://github.com/BudongJW/debutkit/issues
AppUpdatesURL=https://github.com/BudongJW/debutkit/releases/latest
DefaultDirName={autopf}\debutkit
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename={#OutputName}
SetupIconFile=..\assets\brand\app-icon\debutkit.ico
UninstallDisplayIcon={app}\debutkit-gui.exe
UninstallDisplayName=debutkit {#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
#if FileExists(CompilerPath + "Languages\Korean.isl")
Name: "ko"; MessagesFile: "compiler:Languages\Korean.isl"
#else
; 한국어 메시지 파일이 없는 Inno Setup: 설치 화면 기본 문구는 영어, 아래 직접 쓴 문구는 한국어
Name: "ko"; MessagesFile: "compiler:Default.isl"
#endif

[CustomMessages]
ko.DesktopShortcut=바탕 화면에 바로 가기 만들기
ko.StartApp=debutkit 설정 마법사 실행
ko.FfmpegTask=ffmpeg 다운로드(자동 클립에만 필요, {#FfmpegSize} MB)
ko.FfmpegPage=ffmpeg 다운로드 중
ko.FfmpegPageNote=ffmpeg.org가 안내하는 Windows용 빌드를 GitHub에서 다운로드합니다. 인터넷 속도에 따라 몇 분이 걸릴 수 있습니다.
ko.FfmpegInstalling=ffmpeg 설치 중
ko.FfmpegFailed=ffmpeg를 다운로드하지 못했습니다. 프로그램 설치는 계속 진행합니다. 설치 후 설정 마법사 PC 점검 화면의 ffmpeg 다운로드 버튼으로 다시 시도할 수 있습니다.

[Tasks]
Name: "ffmpeg"; Description: "{cm:FfmpegTask}"; Check: FfmpegMissing; Flags: unchecked
Name: "desktopicon"; Description: "{cm:DesktopShortcut}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\debutkit"; Filename: "{app}\debutkit-gui.exe"
Name: "{autodesktop}\debutkit"; Filename: "{app}\debutkit-gui.exe"; Tasks: desktopicon

[Run]
; 설치한 프로그램이 압축 파일의 SHA-256을 한 번 더 확인하고 ffmpeg, ffprobe를 꺼낸다
Filename: "{app}\debutkit.exe"; Parameters: "setup --ffmpeg --from ""{tmp}\{#FfmpegFile}"""; StatusMsg: "{cm:FfmpegInstalling}"; Flags: runhidden; Tasks: ffmpeg; Check: FfmpegFetched
Filename: "{app}\debutkit-gui.exe"; Description: "{cm:StartApp}"; Flags: nowait postinstall skipifsilent

[Code]
var
  DownloadPage: TDownloadWizardPage;
  FfmpegArchiveReady: Boolean;

function FfmpegMissing: Boolean;
begin
  { debutkit이 ffmpeg를 찾는 곳: PATH, 다운로드 폴더 }
  Result := (FileSearch('ffmpeg.exe', GetEnv('PATH')) = '')
    and not FileExists(ExpandConstant('{%USERPROFILE}\.cache\stream2clip\tools\ffmpeg.exe'));
end;

function FfmpegFetched: Boolean;
begin
  Result := FfmpegArchiveReady;
end;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage(CustomMessage('FfmpegPage'), CustomMessage('FfmpegPageNote'), nil);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = wpReady) and WizardIsTaskSelected('ffmpeg') then
  begin
    DownloadPage.Clear;
    DownloadPage.Add('{#FfmpegUrl}', '{#FfmpegFile}', '{#FfmpegSha256}');
    DownloadPage.Show;
    try
      try
        DownloadPage.Download;
        FfmpegArchiveReady := True;
      except
        { 연결 없음, 다른 파일, 취소: 프로그램 설치는 그대로 진행 }
        Log('ffmpeg was not downloaded: ' + GetExceptionMessage);
        if not DownloadPage.AbortedByUser then
          SuppressibleMsgBox(CustomMessage('FfmpegFailed') + #13#10 + #13#10 + AddPeriod(GetExceptionMessage), mbInformation, MB_OK, IDOK);
      end;
    finally
      DownloadPage.Hide;
    end;
  end;
end;
