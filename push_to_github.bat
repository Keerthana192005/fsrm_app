@echo off
set GIT=C:\2025.1\tps\win64\git-2.46.0\bin\git.exe
%GIT% init
%GIT% config user.email "keerthana@example.com"
%GIT% config user.name "Keerthana192005"
%GIT% add .
%GIT% commit -m "Initial commit"
%GIT% branch -M main
%GIT% remote add origin https://github.com/Keerthana192005/farm_app.git
%GIT% push -u origin main
