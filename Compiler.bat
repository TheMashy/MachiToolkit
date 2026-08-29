@echo off
setlocal
title Machi Tool - compilation
cd /d "%~dp0"
color 0D

echo.
echo   ================================================
echo      COMPILATION DE L'EXE
echo   ================================================
echo.
echo   A faire une seule fois. Duree : 3 a 6 minutes.
echo   Resultat : dist\MachiTool.exe
echo.

if not exist "%~dp0machi_tool.py" (
    echo   ERREUR : machi_tool.py est introuvable.
    echo   Les deux fichiers doivent etre dans le meme dossier.
    echo.
    pause
    exit /b 1
)

REM ---------- 1. Python ----------
echo   [1/4] Recherche de Python...

set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (
    python --version >nul 2>&1 && set "PY=python"
)

if not defined PY (
    echo         Python absent. Installation via winget...
    echo.
    winget install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo.
        echo   Installation automatique impossible.
        echo   Installe Python depuis https://www.python.org/downloads/
        echo   en cochant "Add python.exe to PATH", puis relance ce fichier.
        echo.
        pause
        exit /b 1
    )
    for /f "delims=" %%P in ('dir /b /s "%LOCALAPPDATA%\Programs\Python\python.exe" 2^>nul') do set "PY=%%P"
    if not defined PY (
        for /f "delims=" %%P in ('dir /b /s "%ProgramFiles%\Python*\python.exe" 2^>nul') do set "PY=%%P"
    )
)

if not defined PY (
    echo.
    echo   Python installe mais introuvable dans cette fenetre.
    echo   Ferme-la et relance ce fichier : ca passera.
    echo.
    pause
    exit /b 1
)

echo         Trouve.
echo.

REM ---------- 2. dependances ----------
echo   [2/4] Installation des bibliotheques (1 a 3 minutes)...
echo         liste tenue dans requirements.txt
echo.

%PY% -m pip install --upgrade --quiet --disable-pip-version-check pip
%PY% -m pip install --quiet --disable-pip-version-check -r "%~dp0requirements.txt" pyinstaller
if errorlevel 1 (
    echo.
    echo   Echec. Clic droit sur ce fichier ^> "Executer en tant qu'administrateur".
    echo.
    pause
    exit /b 1
)

%PY% -c "import tkinter" >nul 2>&1
if errorlevel 1 (
    echo   ATTENTION : tkinter manque dans cette installation de Python.
    echo   Reinstalle Python depuis python.org en gardant l'option "tcl/tk".
    echo.
    pause
    exit /b 1
)

echo         Pretes.
echo.

REM ---------- 3. icone ----------
echo   [3/4] Generation de l'icone...
%PY% "%~dp0machi_tool.py" --icone
echo.

REM ---------- 4. compilation ----------
echo   [4/4] Compilation. Longue etape, ne ferme pas la fenetre.
echo.
echo         Recette : MachiTool.spec, la meme que celle du
echo         workflow GitHub. Les deux sortent donc le meme exe.
echo.

%PY% -m PyInstaller --noconfirm --clean "%~dp0MachiTool.spec"

if not exist "%~dp0dist\MachiTool.exe" (
    echo.
    echo   La compilation a echoue. Colle les dernieres lignes rouges
    echo   ci-dessus pour qu'on regarde ce qui manque.
    echo.
    pause
    exit /b 1
)

echo.
echo   ================================================
echo      TERMINE
echo   ================================================
echo.
echo   Ton fichier : dist\MachiTool.exe
echo.
echo   Double-clic dessus pour installer. Il se copie dans
echo   %%LOCALAPPDATA%%\MachiTool, s'ajoute au demarrage
echo   de Windows et se lance.
echo.
echo   Une fois installee, l'application se met a jour toute seule :
echo   elle surveille les publications du depot GitHub et propose la
echo   nouvelle version depuis son icone. Compiler a la main ne sert
echo   plus qu'a tester une version pas encore publiee.
echo.

start "" explorer "%~dp0dist"
pause
