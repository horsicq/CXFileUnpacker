@echo off
setlocal EnableExtensions
rem Build and CPack staging live under TEMP; release contains finished packages.
rem Usage: build_portable_windows.cmd x64 win64
rem Set CMAKE_GENERATOR_NAME=Ninja in an MSVC developer prompt for a Ninja build.

if "%~2"=="" (
    echo Usage: %~nx0 ^<cmake-platform^> ^<package-suffix^>
    echo Example: %~nx0 x64 win64
    exit /b 1
)

set "VALID_PLATFORM="
if /I "%~1"=="x64" if /I "%~2"=="win64" set "VALID_PLATFORM=1"
if /I "%~1"=="Win32" if /I "%~2"=="win32" set "VALID_PLATFORM=1"
if /I "%~1"=="ARM64" if /I "%~2"=="winarm64" set "VALID_PLATFORM=1"
if not defined VALID_PLATFORM (
    echo Unsupported platform/suffix pair: %~1 %~2
    exit /b 1
)

for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"
for %%I in ("%TEMP%") do set "TEMP_ROOT=%%~fI"
set "CMAKE_PLATFORM=%~1"
set "PACKAGE_SUFFIX=%~2"
if "%CMAKE_GENERATOR_NAME%"=="" set "CMAKE_GENERATOR_NAME=Visual Studio 17 2022"

set "WORK_ROOT=%TEMP_ROOT%\xfileunpacker_%PACKAGE_SUFFIX%"
for %%I in ("%WORK_ROOT%\..") do set "WORK_PARENT=%%~fI"
if /I not "%WORK_PARENT%"=="%TEMP_ROOT%" (
    echo Refusing to use a work directory outside TEMP: %WORK_ROOT%
    exit /b 1
)
set "BUILD_DIR=%WORK_ROOT%\build"
set "CPACK_DIR=%WORK_ROOT%\cpack"
set "CPACK_OUTPUT_DIR=%WORK_ROOT%\output"

if not exist "%PROJECT_ROOT%\release_version.txt" (
    echo release_version.txt not found: %PROJECT_ROOT%\release_version.txt
    exit /b 1
)
set /p RELEASE_VERSION=<"%PROJECT_ROOT%\release_version.txt"
set "PACKAGE_NAME=xfileunpacker_%PACKAGE_SUFFIX%_portable_%RELEASE_VERSION%"
set "RELEASE_DIR=%PROJECT_ROOT%\release"
set "PACKAGE_DIR=%RELEASE_DIR%\%PACKAGE_NAME%"
for %%I in ("%PACKAGE_DIR%\..") do set "PACKAGE_PARENT=%%~fI"
if /I not "%PACKAGE_PARENT%"=="%RELEASE_DIR%" (
    echo Refusing to use a package directory outside release: %PACKAGE_DIR%
    exit /b 1
)
set "PACKAGE_ZIP=%RELEASE_DIR%\%PACKAGE_NAME%.zip"

if not exist "%RELEASE_DIR%" mkdir "%RELEASE_DIR%"
if errorlevel 1 exit /b 1
if exist "%WORK_ROOT%" rmdir /s /q "%WORK_ROOT%"
if errorlevel 1 exit /b 1
mkdir "%WORK_ROOT%"
if errorlevel 1 exit /b 1

echo Configuring %PACKAGE_SUFFIX% build...
if /I "%CMAKE_GENERATOR_NAME%"=="Ninja" (
    cmake -S "%PROJECT_ROOT%" -B "%BUILD_DIR%" -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DBUILD_TESTING=OFF -DXXWIDGETS_BUILD_TESTS=OFF
    set "APP_DIR=%BUILD_DIR%"
) else (
    cmake -S "%PROJECT_ROOT%" -B "%BUILD_DIR%" -G "%CMAKE_GENERATOR_NAME%" -A "%CMAKE_PLATFORM%" -DBUILD_SHARED_LIBS=OFF -DBUILD_TESTING=OFF -DXXWIDGETS_BUILD_TESTS=OFF
    set "APP_DIR=%BUILD_DIR%\Release"
)
if errorlevel 1 exit /b 1

echo Building %PACKAGE_SUFFIX% Release...
if /I "%CMAKE_GENERATOR_NAME%"=="Ninja" (
    cmake --build "%BUILD_DIR%" --config Release --parallel 10
) else (
    cmake --build "%BUILD_DIR%" --config Release --parallel 4
)
if errorlevel 1 exit /b 1

for %%A in (xfu.exe XFileUnpacker.exe xfut.exe) do (
    if not exist "%APP_DIR%\%%A" (
        echo Built executable not found: %APP_DIR%\%%A
        exit /b 1
    )
)
set "CPACK_CONFIG=%BUILD_DIR%\CPackConfig.cmake"
if not exist "%CPACK_CONFIG%" (
    echo CPack config not found: %CPACK_CONFIG%
    exit /b 1
)

if exist "%PACKAGE_DIR%" rmdir /s /q "%PACKAGE_DIR%"
if errorlevel 1 exit /b 1
echo Installing portable package folder...
cmake --install "%BUILD_DIR%" --config Release --prefix "%PACKAGE_DIR%"
if errorlevel 1 exit /b 1
for %%A in (xfu.exe XFileUnpacker.exe xfut.exe) do (
    if not exist "%PACKAGE_DIR%\bin\%%A" (
        echo Installed executable not found: %PACKAGE_DIR%\bin\%%A
        exit /b 1
    )
)

echo Creating portable zip with CPack...
cpack --config "%CPACK_CONFIG%" -G ZIP -C Release -B "%CPACK_DIR%" -D "CPACK_OUTPUT_FILE_PREFIX=%CPACK_OUTPUT_DIR%"
if errorlevel 1 exit /b 1
set "CPACK_ZIP=%CPACK_OUTPUT_DIR%\%PACKAGE_NAME%.zip"
if not exist "%CPACK_ZIP%" (
    echo CPack archive not found: %CPACK_ZIP%
    exit /b 1
)
copy /y "%CPACK_ZIP%" "%PACKAGE_ZIP%" >nul
if errorlevel 1 exit /b 1

rmdir /s /q "%WORK_ROOT%"
if errorlevel 1 exit /b 1
echo.
echo Portable package folder created: %PACKAGE_DIR%
echo Portable zip created by CPack: %PACKAGE_ZIP%
endlocal
