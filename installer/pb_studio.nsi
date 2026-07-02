; pb_studio.nsi — NSIS installer script for PB Studio v0.5.0
; ============================================================
; Requirements:
;   NSIS 3.x  (https://nsis.sourceforge.io/)
;   makensis.exe must be on PATH
;
; Usage (after PyInstaller build):
;   makensis installer\pb_studio.nsi
;
; Input:
;   dist\pb_studio\        <- built by PyInstaller (pb_studio.spec)
;
; Output:
;   dist\pb_studio_setup_v0.5.0.exe

Unicode True

;--------------------------------
; General attributes
;--------------------------------

!define APP_NAME        "PB Studio"
!define APP_VERSION     "0.5.0"
!define APP_PUBLISHER   "Paperclip / David"
!define APP_URL         "https://github.com/paperclip/pb-studio"
!define APP_EXE         "pb_studio.exe"
!define APP_ICON        "pb_studio.ico"
!define INSTALL_DIR     "$LOCALAPPDATA\PB Studio"
!define UNINSTALL_KEY   "Software\Microsoft\Windows\CurrentVersion\Uninstall\PBStudio"
!define OUTPUT_EXE      "..\dist\pb_studio_setup_v${APP_VERSION}.exe"

Name          "${APP_NAME} ${APP_VERSION}"
OutFile       "${OUTPUT_EXE}"
!ifdef USE_NSISBI
OutFileMode   stub
Target        amd64-unicode
!endif
InstallDir    "${INSTALL_DIR}"
InstallDirRegKey HKCU "${UNINSTALL_KEY}" "InstallLocation"

; Per-user install for free distribution. Avoids admin rights and Program Files.
RequestExecutionLevel user

;--------------------------------
; MUI2 Modern UI
;--------------------------------

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"

; Theme / branding
!define MUI_ICON       "..\resources\pb_studio.ico"
!define MUI_UNICON     "..\resources\pb_studio.ico"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_BITMAP   "..\resources\installer_header.bmp"
!define MUI_WELCOMEFINISHPAGE_BITMAP "..\resources\installer_welcome.bmp"
!define MUI_ABORTWARNING

; Pages — Install
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE   "..\LICENSE.txt"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; Pages — Uninstall
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "German"

;--------------------------------
; Version Info (shown in Explorer)
;--------------------------------

VIProductVersion "${APP_VERSION}.0"
VIAddVersionKey /LANG=${LANG_ENGLISH} "ProductName"      "${APP_NAME}"
VIAddVersionKey /LANG=${LANG_ENGLISH} "ProductVersion"   "${APP_VERSION}"
VIAddVersionKey /LANG=${LANG_ENGLISH} "FileDescription"  "${APP_NAME} Installer"
VIAddVersionKey /LANG=${LANG_ENGLISH} "FileVersion"      "${APP_VERSION}"
VIAddVersionKey /LANG=${LANG_ENGLISH} "CompanyName"      "${APP_PUBLISHER}"
VIAddVersionKey /LANG=${LANG_ENGLISH} "LegalCopyright"   "Copyright 2026 ${APP_PUBLISHER}"

;--------------------------------
; Helper: StrContains
; Usage: ${StrContains} $result "needle" $haystack
;--------------------------------

!macro StrContains ResultVar Needle Haystack
  Push "${Haystack}"
  Push "${Needle}"
  Call StrContainsImpl
  Pop ${ResultVar}
!macroend

Function StrContainsImpl
  Exch $R0  ; needle
  Exch
  Exch $R1  ; haystack
  Push $R2
  Push $R3

  StrLen $R2 $R0  ; needle length
  StrCpy $R3 ""

  loop:
    StrCpy $R3 $R1 $R2
    ${If} $R3 == $R0
      StrCpy $R3 $R0
      Goto done
    ${EndIf}
    StrCpy $R1 $R1 "" 1
    ${If} $R1 == ""
      StrCpy $R3 ""
      Goto done
    ${EndIf}
    Goto loop

  done:
  Pop $R2
  Exch $R1
  Pop $R1
  Exch $R0
  Pop $R0
  Exch $R3
FunctionEnd

;--------------------------------
; GPU Detection Macro
; Checks for NVIDIA GPU via WMI query. Sets $GPU_PRESENT to "1" if found.
;--------------------------------

!macro DetectNvidiaGPU
  nsExec::ExecToStack 'wmic path win32_VideoController get Name /format:list'
  Pop $0  ; return code
  Pop $1  ; stdout

  ${If} $1 != ""
    !insertmacro StrContains $2 "NVIDIA" $1
    ${If} $2 != ""
      StrCpy $GPU_PRESENT "1"
    ${EndIf}
  ${EndIf}
!macroend

;--------------------------------
; Installer Sections
;--------------------------------

Var GPU_PRESENT

Section "PB Studio (required)" SecMain
  SectionIn RO  ; Cannot be deselected

  SetOutPath "$INSTDIR"

  ; --- Copy the entire PyInstaller build folder ---
  File /r "..\dist\pb_studio\*.*"

  ; --- Write uninstall registry keys ---
  WriteRegStr   HKCU "${UNINSTALL_KEY}" "DisplayName"          "${APP_NAME}"
  WriteRegStr   HKCU "${UNINSTALL_KEY}" "DisplayVersion"       "${APP_VERSION}"
  WriteRegStr   HKCU "${UNINSTALL_KEY}" "Publisher"            "${APP_PUBLISHER}"
  WriteRegStr   HKCU "${UNINSTALL_KEY}" "InstallLocation"      "$INSTDIR"
  WriteRegStr   HKCU "${UNINSTALL_KEY}" "UninstallString"      '"$INSTDIR\Uninstall.exe"'
  WriteRegStr   HKCU "${UNINSTALL_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegStr   HKCU "${UNINSTALL_KEY}" "DisplayIcon"          "$INSTDIR\${APP_EXE}"
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoModify"             1
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoRepair"             1
  WriteRegStr   HKCU "${UNINSTALL_KEY}" "URLInfoAbout"         "${APP_URL}"

  ; --- Write uninstaller ---
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  ; --- GPU detection ---
  StrCpy $GPU_PRESENT "0"
  !insertmacro DetectNvidiaGPU

  ${If} $GPU_PRESENT == "0"
    IfSilent gpu_warning_done 0
    MessageBox MB_ICONEXCLAMATION|MB_OK \
      "No NVIDIA GPU detected. $\n$\nPB Studio requires an NVIDIA GPU with CUDA support (target: GTX 1060 / CUDA 11.3). \
$\nCPU-only mode is not supported. $\nPlease install NVIDIA drivers from: https://www.nvidia.com/drivers"
    gpu_warning_done:
  ${EndIf}

SectionEnd
Section "Desktop Shortcut" SecDesktop
  CreateShortCut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0
SectionEnd
Section "Start Menu Entry" SecStartMenu
  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortCut  "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"       "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0
  CreateShortCut  "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk"          "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Download AI Models (requires internet)" SecModels
  IfSilent models_done 0
  DetailPrint "Pre-caching AI models... This may take several minutes."
  nsExec::ExecToLog '"$INSTDIR\${APP_EXE}" --pre-cache'
  models_done:
SectionEnd

;--------------------------------
; Section descriptions
;--------------------------------

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMain}      "PB Studio application files (required)"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop}   "Add a shortcut to the Desktop"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecStartMenu} "Add entries to the Start Menu"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecModels}    "Download and cache AI models now (Demucs, SigLIP, Moondream2, beat_this) to enable offline use and faster first start."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

;--------------------------------
; Uninstaller Section
;--------------------------------

Section "Uninstall"

  ; Remove installed files
  RMDir /r "$INSTDIR"

  ; Remove Start Menu
  RMDir /r "$SMPROGRAMS\${APP_NAME}"

  ; Remove Desktop shortcut
  Delete "$DESKTOP\${APP_NAME}.lnk"

  ; Remove registry keys
  DeleteRegKey HKCU "${UNINSTALL_KEY}"

SectionEnd
